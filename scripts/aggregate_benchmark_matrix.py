#!/usr/bin/env python3
"""Validate independent runner artifacts and render a system-by-system report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tarfile


EXPECTED_SYSTEMS = {
    "linux-x86_64": {"runner": "ubuntu-24.04", "architecture": "x86_64", "os": "Linux"},
    "linux-aarch64": {"runner": "ubuntu-24.04-arm", "architecture": "aarch64", "os": "Linux"},
    "macos-arm64": {"runner": "macos-15", "architecture": "arm64", "os": "Darwin"},
}
SYSTEMS = tuple(EXPECTED_SYSTEMS)
CATEGORIES = ("http1", "http2", "http3", "websocket", "lifecycle")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def load_system(artifact: Path, system_id: str, expected_commit: str) -> dict:
    preparation = artifact / "benchmark-preparation"
    results = artifact / "benchmark-categories"
    environment = read_json(preparation / "environment.json")
    run = read_json(results / "run.json")
    analysis = read_json(results / "analysis.json")

    if environment.get("system_id") != system_id:
        raise ValueError(f"{artifact.name}: system ID does not match its artifact name")
    if run.get("schema") != "uvicorn-rs-sequential-category-run@2":
        raise ValueError(f"{artifact.name}: unsupported benchmark driver schema")
    if run.get("status") != "completed_correctness_gated":
        raise ValueError(f"{artifact.name}: benchmark driver did not finish behind the correctness gate")
    identity = run.get("identity_before")
    if not isinstance(identity, dict) or identity.get("git_revision") != expected_commit:
        raise ValueError(f"{artifact.name}: benchmark source revision differs from the workflow commit")
    if identity.get("dirty_target") is not False:
        raise ValueError(f"{artifact.name}: benchmark target was not a clean checkout")
    parity = run.get("public_parity_gate")
    if (not isinstance(parity, dict) or parity.get("status") != "passed"
            or not isinstance(parity.get("public_cases"), int) or parity["public_cases"] <= 0):
        raise ValueError(f"{artifact.name}: public parity gate did not pass")
    if analysis.get("schema") != "uvicorn-rs-paired-category-analysis@2":
        raise ValueError(f"{artifact.name}: unsupported analysis schema")
    if analysis.get("status") not in {"qualified_local_pairs", "no_qualified_pairs"}:
        raise ValueError(f"{artifact.name}: analysis is incomplete")
    if analysis.get("driver_record", {}).get("status") != run.get("status"):
        raise ValueError(f"{artifact.name}: analyzer and driver status disagree")

    categories = analysis.get("categories")
    if not isinstance(categories, list):
        raise ValueError(f"{artifact.name}: missing category analyses")
    by_name = {item.get("category"): item for item in categories if isinstance(item, dict)}
    if set(by_name) != set(CATEGORIES):
        raise ValueError(f"{artifact.name}: category inventory differs from the maintained matrix")
    if any(item.get("status") == "incomplete_category" for item in by_name.values()):
        raise ValueError(f"{artifact.name}: at least one category is incomplete")

    runtime = identity.get("python_runtime")
    dependencies = identity.get("dependencies")
    if not isinstance(runtime, dict) or not isinstance(dependencies, dict):
        raise ValueError(f"{artifact.name}: measured Python/dependency identity is missing")
    system = {
        "system_id": system_id,
        "runner": environment.get("runner_label"),
        "architecture": environment.get("architecture"),
        "os": environment.get("os"),
        "platform": environment.get("platform"),
        "cpu_model": environment.get("cpu_model"),
        "logical_cpu_count": environment.get("logical_cpu_count"),
        "physical_cpu_count": environment.get("physical_cpu_count"),
        "memory_total_bytes": environment.get("memory_total_bytes"),
        "hosted_runner": environment.get("hosted_runner"),
        "python": runtime.get("version", "").split()[0],
        "dependencies": {name: item.get("version") for name, item in dependencies.items()
                         if isinstance(item, dict)},
        "source_sha256": identity.get("source"),
        "harness": identity.get("harness"),
        "examples": identity.get("examples"),
        "optional_workloads": {name: item.get("selected")
                                for name, item in identity.get("optional_workloads", {}).items()
                                if isinstance(item, dict)},
        "framework_revision": environment.get("framework_revision"),
        "driver_status": run.get("status"),
        "analysis_status": analysis.get("status"),
        "qualified_pairs": analysis.get("qualified_pairs"),
        "categories": by_name,
        "artifact": artifact.name,
    }
    expected_system = EXPECTED_SYSTEMS[system_id]
    if any(system[key] != expected for key, expected in expected_system.items()):
        raise ValueError(f"{artifact.name}: runner label or architecture does not match {system_id}")
    if not isinstance(system["memory_total_bytes"], int) or system["memory_total_bytes"] <= 0:
        raise ValueError(f"{artifact.name}: total system memory is missing")
    if not isinstance(system["logical_cpu_count"], int) or system["logical_cpu_count"] <= 0:
        raise ValueError(f"{artifact.name}: logical CPU count is missing")
    if not isinstance(system["qualified_pairs"], int):
        raise ValueError(f"{artifact.name}: missing qualified-pair count")
    return system


def assert_common_identity(systems: list[dict]) -> None:
    first = systems[0]
    for system in systems[1:]:
        for key in ("python", "dependencies", "source_sha256", "harness", "examples",
                    "optional_workloads", "framework_revision"):
            if system[key] != first[key]:
                raise ValueError(f"runner software identity differs for {key}: {first['system_id']} vs {system['system_id']}")


def archive_system_evidence(artifact: Path, destination: Path) -> None:
    """Keep machine-readable measurements and identity receipts beyond artifact expiry."""
    preparation = artifact / "benchmark-preparation"
    results = artifact / "benchmark-categories"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(results.rglob("*")):
            if path.is_file() and path.suffix != ".log":
                archive.add(path, arcname=path.relative_to(artifact))
        for name in ("environment.json", "system-packages.txt", "parity-before.json",
                     "parity.json", "wheel-build-record.json", "framework-revision.txt"):
            path = preparation / name
            if path.is_file():
                archive.add(path, arcname=path.relative_to(artifact))


def metric(pair: dict, name: str, side: str) -> str:
    value = pair.get("metrics", {}).get(name, {}).get(side)
    return "—" if not isinstance(value, (int, float)) else f"{value:.3f}"


def workload_rows(system: dict, *, resources: bool = False) -> list[str]:
    lines = []
    for category in CATEGORIES:
        if category == "lifecycle":
            continue
        for pair in system["categories"][category].get("pairs", []):
            if pair.get("qualified") is not True:
                continue
            candidate = pair.get("candidate", "")
            profile = "uvloop" if "-uvloop" in candidate else "asyncio"
            matched = len(pair.get("matched_repetitions", []))
            workload = pair.get("workload", "unknown")
            if resources:
                lines.append(
                    f"| {category} | {workload} | {profile} | "
                    f"{metric(pair, 'server_cpu_percent_elapsed', 'reference')} / "
                    f"{metric(pair, 'server_cpu_percent_elapsed', 'rust')} | "
                    f"{metric(pair, 'client_cpu_percent_elapsed_complete', 'reference')} / "
                    f"{metric(pair, 'client_cpu_percent_elapsed_complete', 'rust')} | "
                    f"{metric(pair, 'server_rss_sampled_peak_mib', 'reference')} / "
                    f"{metric(pair, 'server_rss_sampled_peak_mib', 'rust')} | "
                    f"{metric(pair, 'client_rss_sampled_peak_mib', 'reference')} / "
                    f"{metric(pair, 'client_rss_sampled_peak_mib', 'rust')} |"
                )
            else:
                ratio = pair.get("throughput_ratio", {}).get("rust_over_reference")
                ratio_text = "—" if not isinstance(ratio, (int, float)) else f"{ratio:.3f}×"
                lines.append(
                    f"| {category} | {workload} | {profile} | "
                    f"{pair.get('reference', 'unknown')} / {candidate or 'unknown'} | {matched} | "
                    f"{metric(pair, 'operations_per_second', 'reference')} / "
                    f"{metric(pair, 'operations_per_second', 'rust')} | "
                    f"{metric(pair, 'p50_ms', 'reference')} / {metric(pair, 'p50_ms', 'rust')} | "
                    f"{metric(pair, 'p95_ms', 'reference')} / {metric(pair, 'p95_ms', 'rust')} | "
                    f"{metric(pair, 'p99_ms', 'reference')} / {metric(pair, 'p99_ms', 'rust')} | {ratio_text} |"
                )
    return lines


def lifecycle_rows(system: dict) -> list[str]:
    lines = []
    keys = (
        "cold_start_to_first_lifespan_request_ms",
        "idle_sigterm_to_process_exit_ms",
        "active_sigterm_to_process_exit_ms",
        "idle_phase_server_cpu_seconds",
        "active_phase_server_cpu_seconds",
        "idle_phase_server_rss_peak_mib",
        "active_phase_server_rss_peak_mib",
    )
    for pair in system["categories"]["lifecycle"].get("pairs", []):
        if pair.get("qualified") is not True:
            continue
        candidate = pair.get("candidate", "")
        profile = "uvloop" if "-uvloop" in candidate else "asyncio"
        values = [metric(pair, key, side) for key in keys for side in ("reference", "rust")]
        lines.append(
            f"| {profile} | {pair.get('reference', 'unknown')} / {candidate or 'unknown'} | "
            f"{len(pair.get('matched_repetitions', []))} | " + " / ".join(values) + " |"
        )
    return lines


def render_markdown(report: dict) -> str:
    run_url = report["workflow_run_url"]
    lines = [
        "<!-- Generated by scripts/aggregate_benchmark_matrix.py; update through the benchmark docs workflow. -->",
        "# Multi-system benchmark results",
        "",
        f"Run: [{report['run_id']} (attempt {report['run_attempt']})]({run_url})  ",
        f"Commit: [`{report['commit']}`](https://github.com/{report['repository']}/commit/{report['commit']})  ",
        f"Generated: {report['generated_at']}",
        "",
        "The matrix uses independent hosted systems. Results are reported per system; rates and latencies are never averaged across architectures. A row appears below only when its correctness, identity, timing, and matching-repetition gates qualify. No qualified row means the run makes no performance claim for that workload.",
        "",
        "The workflow runs five repetitions by default and requires at least three matching valid repetitions. Invalid or incomplete rows remain in the downloadable raw artifacts and are excluded from ratios. These measurements include the Python ASGI boundary and the closed-loop client; see [benchmark methodology](benchmarks.md) for scope and limitations.",
        "",
        "## Runner summary",
        "",
        "| System | Runner | CPU / cores | Memory | Python | Analysis status | Qualified pairs | Raw artifact |",
        "|---|---|---|---:|---|---|---:|---|",
    ]
    for system in report["systems"]:
        artifact = system["artifact"]
        cpu = (f"{system['cpu_model']} ({system['logical_cpu_count']} logical / "
               f"{system['physical_cpu_count']} physical)")
        memory_gib = system["memory_total_bytes"] / 1024**3
        lines.append(
            f"| {system['system_id']} ({system['architecture']}) | {system['runner']} | "
            f"{cpu} | {memory_gib:.1f} GiB | {system['python']} | {system['analysis_status']} | "
            f"{system['qualified_pairs']} | `{artifact}` |"
        )
    for system in report["systems"]:
        lines += [
            "",
            f"## {system['system_id']} ({system['architecture']})",
            "",
            f"Runner: `{system['runner']}`; CPU: {system['cpu_model']} "
            f"({system['logical_cpu_count']} logical, {system['physical_cpu_count']} physical); "
            f"memory: {system['memory_total_bytes'] / 1024**3:.1f} GiB; platform: `{system['platform']}`.",
            "",
            "Throughput and latency:",
            "",
            "| Category | Workload | Loop | Reference / Rust | Valid matches | Ops/s ref / Rust | p50 ms ref / Rust | p95 ms ref / Rust | p99 ms ref / Rust | Rate ratio |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        rows = workload_rows(system)
        lines.extend(rows or ["| No qualified pairs | — | — | — | — | — | — | — | — | — |"])
        lines += [
            "",
            "Resource measurements:",
            "",
            "| Category | Workload | Loop | Server CPU % ref / Rust | Client CPU % ref / Rust | Server RSS MiB ref / Rust | Client RSS MiB ref / Rust |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        resource_rows = workload_rows(system, resources=True)
        lines.extend(resource_rows or ["| No qualified pairs | — | — | — | — | — | — |"])
        lines += [
            "",
            "Category qualification counts:",
            "",
            "| Category | Status | Qualified pairs |",
            "|---|---|---:|",
        ]
        for category in CATEGORIES:
            item = system["categories"][category]
            lines.append(f"| {category} | {item['status']} | {item['qualified_pairs']} |")
        lines += [
            "",
            "Lifecycle phase measurements:",
            "",
            "| Loop | Reference / Rust | Valid matches | Startup ms ref / Rust | Idle exit ms ref / Rust | Active exit ms ref / Rust | Idle CPU s ref / Rust | Active CPU s ref / Rust | Idle RSS MiB ref / Rust | Active RSS MiB ref / Rust |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        lines.extend(lifecycle_rows(system) or ["| No qualified lifecycle pairs | — | — | — | — | — | — | — | — | — |"])
        lines += [
            "",
            f"Download `{system['artifact']}` from the [workflow run]({run_url}) for raw rows, logs, environment receipts, and the complete per-run analysis.",
            f"Archived machine-readable evidence: [matrix results](../benchmarks/results/hosted/{report['archive_key']}/matrix.json) and [raw system bundle](../benchmarks/results/hosted/{report['archive_key']}/{system['system_id']}-evidence.tar.gz).",
            f"Verify archived files with the [SHA-256 manifest](../benchmarks/results/hosted/{report['archive_key']}/SHA256SUMS).",
        ]
    lines += [
        "",
        "## Interpretation",
        "",
        "- A rate above 1× is a measured Rust/reference ratio for that workload and runner only; it does not establish a universal speedup or statistical significance.",
        "- HTTP/2 and HTTP/3 compare against Hypercorn because Uvicorn does not provide those protocol servers.",
        "- This report identifies each platform's hosted runner image and CPU. Hosted hardware and neighboring load can change between runs; inspect the raw environment and timing-valid rows before comparing revisions.",
        "- The Rust server still invokes Python for ASGI callables, event-loop tasks, and ASGI message construction/dispatch. These end-to-end results include that integration boundary.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("--commit must be a full lowercase Git commit SHA")
    found = {}
    artifact_paths = {}
    for artifact in sorted(args.artifacts.glob("asgi-category-benchmarks-*")):
        system_id = artifact.name.removeprefix("asgi-category-benchmarks-")
        if system_id not in SYSTEMS:
            raise ValueError(f"unexpected benchmark artifact: {artifact.name}")
        if system_id in found:
            raise ValueError(f"duplicate artifact for {system_id}")
        found[system_id] = load_system(artifact, system_id, args.commit)
        artifact_paths[system_id] = artifact
    if set(found) != set(SYSTEMS):
        missing = sorted(set(SYSTEMS) - set(found))
        raise ValueError(f"missing system benchmark artifacts: {missing}")
    systems = [found[name] for name in SYSTEMS]
    assert_common_identity(systems)

    report = {
        "schema": "uvicorn-rs-benchmark-matrix@1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": args.commit,
        "repository": args.repository,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "archive_key": f"{args.run_id}-attempt-{args.run_attempt}",
        "workflow_run_url": f"https://github.com/{args.repository}/actions/runs/{args.run_id}",
        "systems": systems,
        "system_ids": list(SYSTEMS),
        "aggregation_policy": "systems remain independent; no cross-system pooling or ranking",
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "matrix.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (args.output_dir / "report.md").write_text(render_markdown(report))
    evidence_dir = args.output_dir / "evidence"
    evidence_dir.mkdir()
    for system in systems:
        archive_system_evidence(
            artifact_paths[system["system_id"]],
            evidence_dir / f"{system['system_id']}-evidence.tar.gz",
        )
    print(json.dumps({"status": "validated", "systems": list(SYSTEMS),
                      "qualified_pairs_by_system": {item["system_id"]: item["qualified_pairs"] for item in systems},
                      "output": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"benchmark matrix aggregation failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
