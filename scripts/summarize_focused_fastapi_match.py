#!/usr/bin/env python3
"""Validate and summarize one normal-build FastAPI comparison report."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

PAIRS = (
    ("asyncio", "uvicorn-asyncio-httptools", "uvicorn-rs-asyncio"),
    ("uvloop", "uvicorn-uvloop-httptools", "uvicorn-rs-uvloop"),
)
METRICS = {
    "requests_per_second": ("requests/s", True),
    "p50_ms": ("p50 ms", True),
    "p95_ms": ("p95 ms", True),
    "p99_ms": ("p99 ms", True),
    "server_cpu_microseconds_per_request": ("server CPU µs/request", True),
    "server_rss_peak_mib": ("server RSS MiB", True),
    "client_cpu_microseconds_per_request": ("client CPU µs/request", False),
    "client_rss_peak_mib": ("client RSS MiB", False),
}


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def stable_identity(row: dict[str, Any]) -> bool:
    identity = row.get("measurement_identity")
    if not isinstance(identity, dict):
        return False
    for key in ("source_sha256", "native_sha256", "client_sha256"):
        before, after = identity.get(f"{key}_before"), identity.get(f"{key}_after")
        if before != after:
            return False
        if key == "source_sha256" and (not isinstance(before, str) or len(before) != 64):
            return False
        if key == "native_sha256" and row.get("server", "").startswith("uvicorn-rs-"):
            if not isinstance(before, str) or len(before) != 64:
                return False
        if key == "client_sha256" and (
            not isinstance(before, dict)
            or not before
            or any(not isinstance(value, str) or len(value) != 64 for value in before.values())
        ):
            return False
    return True


def valid_row(row: dict[str, Any]) -> bool:
    return (
        row.get("timing_valid") is True
        and row.get("failures") == 0
        and row.get("server_lifecycle_gate") == "passed"
        and row.get("unexpected_panic_events") == 0
        and row.get("unexpected_native_errors") == 0
        and stable_identity(row)
        and all(finite_number(row.get(name)) for name, (_, required) in METRICS.items() if required)
    )


def summarize(report: dict[str, Any], workload: str) -> tuple[dict[str, Any], str]:
    metadata, rows = report.get("metadata", {}), report.get("rows", [])
    errors: list[str] = []
    expected_servers = {server for _, ref, rust in PAIRS for server in (ref, rust)}
    repetitions = metadata.get("repetitions")
    if report.get("status") != "completed":
        errors.append(f"benchmark status is {report.get('status')!r}, not completed")
    if metadata.get("workloads") != [workload]:
        errors.append(f"expected only workload {workload!r}")
    servers = metadata.get("servers")
    if not isinstance(servers, dict) or set(servers) != expected_servers:
        errors.append("the four maintained Uvicorn/Rust asyncio and uvloop servers are required")
    if metadata.get("runtime_diagnostics_required") is not False:
        errors.append("runtime-diagnostics must be disabled")
    if metadata.get("asgi_stage_diagnostics") is not False or metadata.get("diagnostic_only") is True:
        errors.append("ASGI stage instrumentation must be disabled")
    correctness = "every measured response status and complete body exactly matches the workload oracle"
    if metadata.get("correctness_gate") != correctness:
        errors.append("exact response correctness gate is missing")
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 3:
        errors.append("at least three repetitions must be planned")
        repetitions = 0

    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            errors.append("benchmark rows must be JSON objects")
            continue
        server, number = row.get("server"), row.get("repetition")
        key = (server, number)
        if row.get("workload") != workload or server not in expected_servers:
            errors.append(f"unexpected row: {key!r}")
        elif not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= repetitions:
            errors.append(f"invalid repetition: {key!r}")
        elif key in indexed:
            errors.append(f"duplicate row: {key!r}")
        else:
            indexed[key] = row
    expected = {(server, n) for server in expected_servers for n in range(1, repetitions + 1)}
    if set(indexed) != expected:
        errors.append(f"expected {len(expected)} distinct rows; found {len(indexed)}")
    source_hashes = {
        row.get("measurement_identity", {}).get("source_sha256_before")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("measurement_identity"), dict)
    }
    if len(source_hashes) != 1 or None in source_hashes:
        errors.append("source identity is missing or changed between rows")

    pair_results = []
    for loop, reference, candidate in PAIRS:
        reference_rows = {
            n: indexed[(reference, n)] for n in range(1, repetitions + 1)
            if (reference, n) in indexed and valid_row(indexed[(reference, n)])
        }
        candidate_rows = {
            n: indexed[(candidate, n)] for n in range(1, repetitions + 1)
            if (candidate, n) in indexed and valid_row(indexed[(candidate, n)])
        }
        matching = sorted(reference_rows.keys() & candidate_rows.keys())
        if len(matching) < 3:
            errors.append(f"{loop}: only {len(matching)} timing-valid matching repetitions")
        metrics: dict[str, Any] = {}
        for name, (label, required) in METRICS.items():
            pairs = [(reference_rows[n].get(name), candidate_rows[n].get(name)) for n in matching]
            if not pairs:
                metrics[name] = {"label": label, "reference": None, "rust": None}
                continue
            if not all(all(finite_number(value) for value in pair) for pair in pairs):
                metrics[name] = {"label": label, "reference": None, "rust": None}
                if required and matching:
                    errors.append(f"{loop}: required metric {name} is missing")
                continue
            ref_values, rust_values = [pair[0] for pair in pairs], [pair[1] for pair in pairs]
            metrics[name] = {
                "label": label,
                "reference": statistics.median(ref_values),
                "rust": statistics.median(rust_values),
            }
            if name == "requests_per_second" and all(value > 0 for value in ref_values):
                metrics[name]["rust_over_reference_median_of_matched_ratios"] = statistics.median(
                    rust / ref for ref, rust in pairs
                )
        pair_results.append({
            "loop": loop,
            "reference": reference,
            "candidate": candidate,
            "valid_matched_repetitions": matching,
            "metrics": metrics,
        })

    status = "qualified_matched_pairs" if not errors else "incomplete_or_unqualified"
    result = {
        "schema": "uvicorn-rs-focused-fastapi-match@1",
        "status": status,
        "workload": workload,
        "source_sha256": next(iter(source_hashes)) if len(source_hashes) == 1 else None,
        "system": {key: metadata.get(key) for key in (
            "platform", "machine", "cpu_model", "logical_cpus", "python_environment"
        )},
        "parameters": {key: metadata.get(key) for key in (
            "concurrency", "duration_seconds", "warmup_seconds", "repetitions"
        )},
        "recorded_rows": len(rows),
        "correctness_gate": metadata.get("correctness_gate"),
        "errors": sorted(set(errors)),
        "pairs": pair_results,
        "limitations": [
            "Three matching valid repetitions are descriptive, not a statistical-significance claim.",
            "The client and server share one hosted runner; client and observer CPU are reported.",
            "This is one workload on one runner, not a cross-system or whole-server claim.",
        ],
    }
    lines = [
        f"## Focused FastAPI matched benchmark: `{workload}`",
        "",
        f"Status: `{status}`; source `{result['source_sha256'] or 'unavailable'}`.",
        "",
        "| Loop | Matches | Metric | Uvicorn | uvicorn-rs | Rust/reference |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for pair in pair_results:
        for name, (label, _) in METRICS.items():
            values = pair["metrics"][name]
            ratio = values.get("rust_over_reference_median_of_matched_ratios")
            ref = values.get("reference")
            rust = values.get("rust")
            ref_text = f"{ref:.3f}" if finite_number(ref) else "—"
            rust_text = f"{rust:.3f}" if finite_number(rust) else "—"
            ratio_text = f"{ratio:.3f}x" if finite_number(ratio) else "—"
            lines.append(
                f"| {pair['loop']} | {len(pair['valid_matched_repetitions'])} | {label} | "
                f"{ref_text} | {rust_text} | {ratio_text} |"
            )
    if errors:
        lines.extend(["", "### Qualification errors", "", *(f"- {error}" for error in sorted(set(errors)))])
    lines.append("")
    markdown = "\n".join(lines)
    return result, markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--workload", default="fastapi-validated-route")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = json.loads(args.input.read_text(encoding="utf-8"))
        if (
            not isinstance(report, dict)
            or not isinstance(report.get("metadata"), dict)
            or not isinstance(report.get("rows"), list)
        ):
            raise ValueError("report must contain metadata and rows")
        result, markdown = summarize(report, args.workload)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "summary.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        (args.output_dir / "summary.md").write_text(markdown, encoding="utf-8")
        print(json.dumps({"status": result["status"], "summary": str(args.output_dir / "summary.json")}))
        return 0 if result["status"] == "qualified_matched_pairs" else 1
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
        print(f"focused FastAPI report validation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
