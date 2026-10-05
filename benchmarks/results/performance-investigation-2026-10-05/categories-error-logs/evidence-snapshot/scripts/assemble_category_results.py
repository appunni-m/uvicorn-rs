"""Merge corrected protocol rows and validate the category result bundle."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
H1_PATH = RESULTS / "http-categories-2026-10-02.json"
H2_PATH = RESULTS / "http2-categories-2026-10-02.json"
H2_SCOPE_REFRESH = RESULTS / "http2-protocol-scope-refreshed-2026-10-02.json"
H2_SLOW_READER = RESULTS / "http2-slow-reader-rate-paced-2026-10-02.json"
H3_PATH = RESULTS / "http3-categories-2026-10-02.json"
WEBSOCKET_PATH = RESULTS / "websocket-categories-2026-10-02.json"
LIFECYCLE_PATH = RESULTS / "lifecycle-categories-2026-10-02.json"
SUMMARY_PATH = RESULTS / "category-summary-2026-10-02.json"
H3_MULTIPLEXED_PATH = RESULTS / "http3-fixed-multiplexed-concurrency16-2026-10-02.json"
H3_MULTIPLEXED_BASELINE_LOG = RESULTS / "http3-hypercorn-fixed-concurrency16-gate-2026-10-02.log"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def median_summaries(rows: list[dict], metric_names: tuple[str, ...]) -> dict:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["workload"], row["server"])].append(row)
    result: dict[str, dict] = {}
    for (workload, server), group in sorted(groups.items()):
        metrics = {}
        for metric in metric_names:
            values = [row[metric] for row in group if row.get(metric) is not None]
            metrics[metric] = statistics.median(values) if values else None
        result.setdefault(workload, {})[server] = metrics
    return result


def merge_h2() -> dict:
    base = read_json(H2_PATH)
    scope_refresh = read_json(H2_SCOPE_REFRESH)
    slow_reader = read_json(H2_SLOW_READER)
    rows = [
        row for row in base["rows"]
        if row["workload"] not in {"protocol-scope", "slow-reader-backpressure"}
    ]
    rows.extend(scope_refresh["rows"])
    rows.extend(slow_reader["rows"])
    assert len(rows) == 84, f"expected 84 H2 rows, got {len(rows)}"
    keys = [(row["workload"], row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == len(keys), "duplicate H2 workload/server/repetition rows"
    assert all(row["failures"] == 0 for row in rows), "H2 correctness failure found"

    metadata = dict(base["metadata"])
    base_fingerprints = metadata.get("source_sha256_by_workload", {})
    base_digest = metadata.get("source_sha256")
    metadata["source_sha256"] = None
    metadata["source_sha256_by_workload"] = {
        workload: digest
        for workload, digest in {
            **{
                name: base_fingerprints.get(name, base_digest)
                for name in base["metadata"]["workloads"]
                if name not in {"protocol-scope", "slow-reader-backpressure"}
            },
            "protocol-scope": scope_refresh["metadata"]["source_sha256"],
            "slow-reader-backpressure": slow_reader["metadata"]["source_sha256"],
        }.items()
    }
    metadata["protocol_scope_fixture"] = "refreshed to consume its request event before responding"
    metadata["slow_reader_client"] = "4 MiB/s byte-rate pacing; flow-control credit returned after pacing"
    metadata["workload_concurrency"] = {
        workload: max(row.get("concurrency", metadata["concurrency"]) for row in rows if row["workload"] == workload)
        for workload in metadata["workloads"]
    }
    report = {
        "metadata": metadata,
        "summaries_median": median_summaries(
            rows,
            (
                "requests_per_second", "application_bytes_per_second", "p50_ms", "p95_ms", "p99_ms",
                "server_cpu_percent_mean", "server_rss_peak_mib", "client_cpu_percent_mean",
            ),
        ),
        "rows": rows,
        "row_sources": {
            "base": H2_PATH.name,
            "protocol-scope": H2_SCOPE_REFRESH.name,
            "slow-reader-backpressure": H2_SLOW_READER.name,
        },
    }
    H2_PATH.write_text(json.dumps(report, indent=2) + "\n")
    return report


def validate_report(name: str, report: dict, expected_rows: int, metric: str) -> dict:
    rows = report["rows"]
    assert len(rows) == expected_rows, f"{name}: expected {expected_rows} rows, got {len(rows)}"
    assert all(row.get("failures", 0) == 0 for row in rows), f"{name}: correctness failure found"
    keys = [(row.get("workload"), row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == len(keys), f"{name}: duplicate workload/server/repetition rows"
    workloads = sorted({row.get("workload", "lifecycle") for row in rows})
    summaries = median_summaries(
        rows,
        (
            metric, "p50_ms", "p95_ms", "p99_ms", "server_cpu_percent_mean",
            "server_rss_peak_mib", "client_cpu_percent_mean",
        ),
    )
    return {
        "file": report["_file"],
        "rows": len(rows),
        "workloads": workloads,
        "source_sha256": report.get("metadata", {}).get("source_sha256"),
        "source_sha256_by_workload": report.get("metadata", {}).get("source_sha256_by_workload"),
        "summaries_median": summaries,
    }


def main() -> None:
    h2 = merge_h2()
    reports = {}
    for name, path, expected_rows, metric in (
        ("http1", H1_PATH, 144, "requests_per_second"),
        ("http2", H2_PATH, 84, "requests_per_second"),
        ("http3", H3_PATH, 66, "requests_per_second"),
        ("websocket", WEBSOCKET_PATH, 36, "messages_per_second"),
    ):
        report = h2 if name == "http2" else read_json(path)
        report["_file"] = path.name
        reports[name] = validate_report(name, report, expected_rows, metric)

    lifecycle = read_json(LIFECYCLE_PATH)
    lifecycle_rows = lifecycle["rows"]
    assert len(lifecycle_rows) == 20, f"expected 20 lifecycle rows, got {len(lifecycle_rows)}"
    assert all(row["active_asgi_task_cancelled"] for row in lifecycle_rows), "lifecycle cancellation gate failed"
    assert all(row["idle_sigterm_to_process_exit_ms"] >= 0 for row in lifecycle_rows)
    reports["lifecycle"] = {
        "file": LIFECYCLE_PATH.name,
        "rows": len(lifecycle_rows),
        "workloads": ["startup-state", "idle-sigterm", "active-request-cancellation"],
        "source_sha256": lifecycle["metadata"]["source_sha256"],
        "summaries_median": median_summaries(
            [{"workload": "lifecycle", **row} for row in lifecycle_rows],
            (
                "cold_start_to_first_lifespan_request_ms", "idle_sigterm_to_process_exit_ms",
                "active_sigterm_to_process_exit_ms", "sampled_server_rss_mib",
            ),
        ),
    }

    h3_multiplexed = read_json(H3_MULTIPLEXED_PATH)
    assert len(h3_multiplexed["rows"]) == 6
    assert all(row["failures"] == 0 for row in h3_multiplexed["rows"])
    reports["h3_multiplexed_candidate_only"] = {
        "file": H3_MULTIPLEXED_PATH.name,
        "rows": len(h3_multiplexed["rows"]),
        "workloads": ["fixed-response"],
        "configuration": "16 workers over four QUIC connections, four streams per connection target",
        "baseline_gate_log": H3_MULTIPLEXED_BASELINE_LOG.name,
        "baseline_result": "Hypercorn uvloop failed the same gate with 16 timed-out H3 response streams; no 16-worker performance comparison is reported",
        "summaries_median": median_summaries(
            h3_multiplexed["rows"],
            (
                "requests_per_second", "p50_ms", "p95_ms", "p99_ms",
                "server_cpu_percent_mean", "server_rss_peak_mib", "client_cpu_percent_mean",
            ),
        ),
    }

    summary = {
        "metadata": {
            "date": date.today().isoformat(),
            "environment": read_json(H1_PATH)["metadata"],
            "correctness": "all timed HTTP, H2, H3, and WebSocket rows passed their response/body gates; all lifecycle cancellations passed",
            "live_probes": {
                "probe_http.py": "passed: request/response, loop ownership, caller context, and exception-to-500",
                "probe_http2.py": "passed: cleartext/TLS HTTP/1.1, HTTP/2 ALPN, and HTTP/3 scope version",
                "probe_streaming.py": "passed: incremental upload, early response, and ordered response chunks",
                "probe_websocket.py": "passed: handshake, subprotocol, text/binary messages, and pre-accept denial",
                "probe_cancellation.py": "passed: http.disconnect, send-after-disconnect OSError, and shutdown Task cancellation",
                "probe_lifespan.py": "passed: startup state, per-request shallow copies, and SIGTERM shutdown",
                "probe_starlette_rs.py": "passed: separately installed framework served without a runtime dependency",
            },
            "full_asgi_conformance_suite": "not_run; the live probes are targeted black-box cases, not the complete official suite",
        },
        "sections": reports,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote {H2_PATH}")
    print(f"Wrote {SUMMARY_PATH}")
    for name, section in reports.items():
        print(f"{name}: {section['rows']} rows; {len(section['workloads'])} workloads")


if __name__ == "__main__":
    main()
