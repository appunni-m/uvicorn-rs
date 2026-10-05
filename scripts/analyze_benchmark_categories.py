#!/usr/bin/env python3
"""Analyze recorded category JSON without importing or executing either server.

Only three or more matching, individually valid repetitions with an available
recorded metadata pair gate can produce medians or ratios. Raw reports and
unfinished checkpoints are never modified. This is local experiment analysis,
not a statistical significance test or a release performance attestation.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


MINIMUM_MATCHES = 3
CATEGORIES = {
    "http1": {
        "reference": "uvicorn-uvloop-httptools",
        "workloads": [
            "fixed", "large-response", "many-response-chunks", "small-response-chunks",
            "request-upload", "request-upload-small-chunks", "slow-reader-backpressure",
            "scope-32-headers", "contextvars", "sync-callable-awaitable",
            "exception-to-500", "starlette-rs-route",
        ],
    },
    "http2": {
        "reference": "hypercorn-uvloop",
        "workloads": [
            "protocol-scope", "fixed", "large-response", "many-response-chunks",
            "request-upload", "request-upload-small-chunks", "slow-reader-backpressure",
        ],
    },
    "http3": {
        "reference": "hypercorn-uvloop",
        "workloads": [
            "protocol-scope-consumed-request", "protocol-scope", "fixed", "large-response", "many-response-chunks",
            "request-upload", "slow-reader-backpressure",
        ],
    },
    "websocket": {
        "reference": "uvicorn-uvloop-websockets",
        "workloads": ["connection-handshake", "text-echo", "binary-64k-echo"],
    },
    "lifecycle": {"reference": "uvicorn-uvloop-httptools", "workloads": ["lifecycle"]},
}
CANDIDATE = "uvicorn-rs-uvloop"
SUSTAINED_METRICS = {
    "p50_ms": "p50_ms", "p95_ms": "p95_ms", "p99_ms": "p99_ms",
    "server_cpu_seconds": "server_cpu_seconds",
    "server_cpu_percent_elapsed": "server_cpu_percent_elapsed",
    "server_cpu_microseconds_per_operation": "server_cpu_microseconds_per_request",
    "server_rss_sampled_peak_mib": "server_rss_peak_mib",
    "client_rss_sampled_peak_mib": "client_rss_peak_mib",
    "runner_cpu_seconds": "runner_cpu_seconds", "monitor_cpu_seconds": "monitor_cpu_seconds",
}
LIFECYCLE_METRICS = (
    "cold_start_to_first_lifespan_request_ms", "idle_sigterm_to_process_exit_ms",
    "active_sigterm_to_process_exit_ms", "idle_phase_server_cpu_seconds",
    "active_phase_server_cpu_seconds", "idle_phase_server_cpu_percent_elapsed",
    "active_phase_server_cpu_percent_elapsed", "idle_phase_server_rss_peak_mib",
    "active_phase_server_rss_peak_mib",
)
LIMITATIONS = [
    "Three valid matching repetitions are a descriptive gate, not evidence of statistical significance.",
    "Medians of per-run latency percentiles are not pooled request latency percentiles.",
    "Throughput ratios use matching repetitions only; no overall winner or cross-protocol ranking is produced.",
    "Recorded H1, H2, H3, and WebSocket client clocks/setup/drain boundaries differ and cannot be compared across protocols.",
    "Closed-loop same-host load has no coordinated-omission correction or open-loop offered-rate evidence.",
    "Sustained server CPU is observed live process-tree cpu_times deltas over the recorded load/monitor boundary; complete reaped-child accounting is not inferred.",
    "Client CPU is complete reaped-child RUSAGE_CHILDREN accounting across setup/load/drain/report only when each row explicitly asserts client_cpu_complete.",
    "RSS is sampled process-tree RSS; the reported value is a median of matched runs' sampled peaks, not allocator peak, PSS, or private memory.",
    "Lifecycle complete CPU covers the spawned and reaped server process lifetime (startup/readiness/shutdown); the separate elapsed and cold-start boundaries additionally include observer/free-port/environment preparation, and differ from sustained request CPU.",
    "Lifecycle startup is preparation-to-observed-valid-response, an upper bound affected by polling and observer work; no sub-poll precision is claimed.",
    "Exception diagnostic policies differ and exception-to-500 timing remains unrankable; H3 uploads have no live qualifying Hypercorn performance pair.",
    "The analyzer checks recorded identities and gates; it does not independently attest compilation or reconstruct the measured processes.",
]


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def repetition(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def row_key(row):
    if not isinstance(row, dict) or not isinstance(row.get("workload"), str) or not isinstance(row.get("server"), str) or not repetition(row.get("repetition")):
        return None
    return row["workload"], row["server"], row["repetition"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reject_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def decode(data):
    return json.loads(data, parse_constant=reject_constant)


def load_category(directory, category):
    final = directory / f"{category}.json"
    failure = directory / f"{category}.failure.json"
    checkpoint = directory / f"{category}.jsonl"
    result = {"category": category, "source": str(final), "complete_report_present": False,
              "metadata": {}, "rows": [], "input_errors": [], "input_sha256": None}
    path = final if final.exists() else failure if failure.exists() else None
    if path is not None:
        try:
            data = path.read_bytes()
            report = decode(data)
            if not isinstance(report, dict) or not isinstance(report.get("metadata"), dict) or not isinstance(report.get("rows"), list):
                raise ValueError("report must contain metadata object and rows array")
            result.update(source=str(path), input_sha256=digest(data),
                          metadata=report["metadata"], rows=report["rows"],
                          complete_report_present=path == final)
            return result
        except (OSError, ValueError) as error:
            result["input_errors"].append({"path": str(path), "message": str(error)})
    if checkpoint.exists():
        result["source"] = str(checkpoint)
        data = checkpoint.read_bytes()
        result["input_sha256"] = digest(data)
        for number, line in enumerate(data.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = decode(line)
                if not isinstance(row, dict):
                    raise ValueError("checkpoint row must be an object")
                result["rows"].append(row)
            except ValueError as error:
                result["input_errors"].append({"path": str(checkpoint), "line": number, "message": str(error)})
        sidecar = checkpoint.with_suffix(".jsonl.meta.json")
        if sidecar.exists():
            try:
                metadata = decode(sidecar.read_bytes())
                if not isinstance(metadata, dict):
                    raise ValueError("checkpoint metadata must be an object")
                result["metadata"] = metadata
            except (OSError, ValueError) as error:
                result["input_errors"].append({"path": str(sidecar), "message": str(error)})
    return result


def row_reasons(row, lifecycle=False):
    if not isinstance(row, dict):
        return ["malformed_row"]
    reasons = {str(reason) for reason in row.get("timing_invalid_reasons", [])} if isinstance(row.get("timing_invalid_reasons", []), list) else {"malformed_timing_invalid_reasons"}
    if row.get("timing_valid") is not True:
        reasons.add("timing_valid_false_or_missing")
    failures = row.get("failures")
    if not isinstance(failures, int) or isinstance(failures, bool) or failures != 0:
        reasons.add("failures_nonzero_or_missing")
    if "correctness_valid" in row and row["correctness_valid"] is not True:
        reasons.add("correctness_valid_false")
    if row.get("server_lifecycle_gate") != "passed":
        reasons.add("server_lifecycle_gate_failed_or_missing")
    for key in ("unexpected_panic_events", "unexpected_native_errors"):
        if row.get(key) != 0:
            reasons.add(f"{key}_nonzero_or_missing")
    if not repetition(row.get("repetition")):
        reasons.add("invalid_repetition")
    if row_key(row) is None:
        reasons.add("malformed_workload_server_repetition")
    if lifecycle:
        if row.get("active_asgi_task_started") is not True or row.get("active_asgi_task_cancelled") is not True:
            reasons.add("held_application_entry_or_cancellation_unproven")
        phases = row.get("phase_measurements", {})
        for phase in ("idle", "active"):
            measurement = phases.get(phase, {}) if isinstance(phases, dict) else {}
            if not isinstance(measurement, dict):
                reasons.add(f"{phase}_phase_malformed")
                continue
            if measurement.get("correctness_valid") is not True or measurement.get("timing_valid") is not True or measurement.get("lifespan_shutdown_complete") is not True:
                reasons.add(f"{phase}_phase_gate_failed_or_missing")
    else:
        requests = row.get("requests")
        if not repetition(requests):
            reasons.add("no_completed_operations")
        throughput = row.get("requests_per_second", row.get("messages_per_second"))
        if not numeric(throughput) or throughput <= 0:
            reasons.add("throughput_nonpositive_or_missing")
        if any(not numeric(row.get(key)) or row[key] < 0 for key in ("p50_ms", "p95_ms", "p99_ms")):
            reasons.add("latency_percentiles_malformed_or_missing")
    return sorted(reasons)


def measurement_reasons(row, metadata, lifecycle):
    if not isinstance(row, dict):
        return []
    before = metadata.get("identity_before", {})
    if not isinstance(before, dict):
        return ["category_measurement_identity_missing"]
    measurements = [("sample", row)]
    if lifecycle:
        phases = row.get("phase_measurements", {})
        measurements = [(phase, phases.get(phase, {})) for phase in ("idle", "active")] if isinstance(phases, dict) else []
    reasons = []
    expected = {
        "source_sha256": before.get("source_sha256"),
        "native_sha256": before.get("native_extension", {}).get("sha256"),
        "client_sha256": before.get("clients"),
    }
    for phase, measurement in measurements:
        identity = measurement.get("measurement_identity") if isinstance(measurement, dict) else None
        if not isinstance(identity, dict):
            reasons.append(f"{phase}_measurement_identity_missing")
            continue
        for key, value in expected.items():
            if value is None or identity.get(key + "_before") != value or identity.get(key + "_after") != value:
                reasons.append(f"{phase}_{key}_not_bound_to_category_identity")
    return reasons


def metadata_reasons(metadata, driver):
    reasons = []
    if metadata.get("modified_or_unrecorded_dependencies"):
        reasons.append("modified_or_unrecorded_dependency_prevents_stock_reference_pair")
    if metadata.get("identity_stable") is not True:
        reasons.append("recorded_identity_not_stable_or_missing")
    before, after = metadata.get("identity_before"), metadata.get("identity_after")
    if not isinstance(before, dict) or not before or before != after:
        reasons.append("recorded_source_native_client_identities_differ_or_missing")
    dependencies = metadata.get("installed_dependencies_before")
    if not isinstance(dependencies, dict) or not dependencies or dependencies != metadata.get("installed_dependencies_after"):
        reasons.append("recorded_dependency_identities_differ_or_missing")
    if not metadata.get("finished_at"):
        reasons.append("category_completion_metadata_missing")
    if driver is not None:
        driver_before, driver_after = driver.get("identity_before"), driver.get("identity_after")
        if not isinstance(driver_before, dict) or not driver_before or driver_before != driver_after:
            reasons.append("driver_recorded_identities_differ_or_missing")
        if not driver.get("finished_at"):
            reasons.append("driver_completion_metadata_missing")
        parity = driver.get("public_parity_gate")
        if not isinstance(parity, dict) or parity.get("status") != "passed":
            reasons.append("driver_complete_public_parity_gate_missing_or_failed")
        expected = driver.get("identity_before", {})
        if isinstance(before, dict) and isinstance(expected, dict) and expected:
            if before.get("native_extension", {}).get("sha256") != expected.get("native"):
                reasons.append("category_native_differs_from_driver_freeze")
            if before.get("source_files", {}).get("src/lib.rs") != expected.get("source"):
                reasons.append("category_source_differs_from_driver_freeze")
            for group in ("harness", "examples"):
                for path, value in expected.get(group, {}).items():
                    recorded = before.get("source_files", {}).get(path)
                    if recorded is not None and recorded != value:
                        reasons.append(f"category_{group}_differs_from_driver_freeze")
                        break
    return sorted(set(reasons))


def driver_category_reasons(loaded, driver):
    """Require the driver's successful execution receipt for this category only."""
    if driver is None:
        return []
    entries = driver.get("category_runs")
    matches = [entry for entry in entries if isinstance(entry, dict)
               and entry.get("category") == loaded["category"]] if isinstance(entries, list) else []
    if len(matches) != 1:
        return ["driver_category_receipt_missing_or_duplicate"]
    entry = matches[0]
    reasons = []
    if type(entry.get("exit_code")) is not int or entry["exit_code"] != 0:
        reasons.append("driver_category_exit_not_successful")
    if not entry.get("finished_at") or any(entry.get(key) for key in ("error", "cleanup_error")):
        reasons.append("driver_category_execution_or_cleanup_failed_or_incomplete")
    if entry.get("exact_planned_rows_present") is not True or entry.get("category_identity_stable") is not True:
        reasons.append("driver_category_plan_or_identity_gate_missing_or_failed")
    if type(entry.get("correctness_failures")) is not int or entry["correctness_failures"] != 0:
        reasons.append("driver_category_correctness_gate_missing_or_failed")
    if any(type(entry.get(key)) is not int or entry[key] != len(loaded["rows"])
           for key in ("rows", "expected_rows")):
        reasons.append("driver_category_row_count_differs_or_missing")
    if entry.get("report_sha256") != loaded["input_sha256"] or loaded["input_sha256"] is None:
        reasons.append("driver_category_report_hash_differs_or_missing")
    cleanup = entry.get("owned_process_cleanup")
    if (not isinstance(cleanup, dict) or cleanup.get("forced") is not False
            or type(cleanup.get("returncode")) is not int or cleanup["returncode"] != 0
            or cleanup.get("owned_live_pids") != []):
        reasons.append("driver_category_clean_owned_process_exit_missing_or_failed")
    return sorted(set(reasons))


def median_pair(reference_rows, candidate_rows, key, predicate=None, minimum=MINIMUM_MATCHES):
    available = [number for number in sorted(reference_rows.keys() & candidate_rows.keys())
                 if numeric(reference_rows[number].get(key)) and numeric(candidate_rows[number].get(key))
                 and reference_rows[number][key] >= 0 and candidate_rows[number][key] >= 0
                 and (predicate is None or (predicate(reference_rows[number]) and predicate(candidate_rows[number])))]
    result = {"matched_repetitions": available, "minimum_required": minimum, "reference": None, "rust": None}
    if len(available) >= minimum:
        result.update(reference=statistics.median(reference_rows[number][key] for number in available),
                      rust=statistics.median(candidate_rows[number][key] for number in available))
    return result


def analyze_category(loaded, driver):
    category = loaded["category"]
    metadata, rows = loaded["metadata"], loaded["rows"]
    spec = CATEGORIES[category]
    reference, candidate = spec["reference"], CANDIDATE
    workloads = metadata.get("workloads", spec["workloads"])
    if category == "lifecycle":
        workloads = ["lifecycle"]
    if not isinstance(workloads, list) or not all(isinstance(name, str) for name in workloads):
        workloads = spec["workloads"]
    workloads = list(dict.fromkeys(workloads))
    planned_repetitions = metadata.get("repetitions", MINIMUM_MATCHES)
    if not repetition(planned_repetitions):
        planned_repetitions = MINIMUM_MATCHES
    exclusions = metadata.get("excluded_servers_by_workload", {})
    target_only = {"request-upload"} if category == "http3" else set()
    identities = Counter(key for row in rows if (key := row_key(row)) is not None)
    missing = []
    for workload in workloads:
        for server in (reference, candidate):
            if server == reference and workload in target_only:
                continue
            for number in range(1, planned_repetitions + 1):
                if identities[(workload, server, number)] != 1:
                    missing.append({"workload": workload, "server": server, "repetition": number,
                                    "row_count": identities[(workload, server, number)]})
    complete = loaded["complete_report_present"] and not loaded["input_errors"] and not missing
    gate_reasons = metadata_reasons(metadata, driver)
    gate_reasons.extend(driver_category_reasons(loaded, driver))
    if not complete:
        gate_reasons.append("category_incomplete")
    invalid_counts, raw_invalid_counts, invalid_receipts, eligible = Counter(), Counter(), [], {}
    exclusions_counts = Counter()
    for row_index, row in enumerate(rows, 1):
        if isinstance(row, dict) and isinstance(row.get("timing_invalid_reasons"), list):
            raw_invalid_counts.update({str(reason) for reason in row["timing_invalid_reasons"]})
        reasons = row_reasons(row, category == "lifecycle")
        reasons.extend(measurement_reasons(row, metadata, category == "lifecycle"))
        key = row_key(row)
        if key is not None and identities[key] != 1:
            reasons.append("duplicate_workload_server_repetition")
        if reasons:
            invalid_counts.update(set(reasons))
            invalid_receipts.append({"raw_row_index": row_index,
                                     "workload": row.get("workload") if isinstance(row, dict) else None,
                                     "server": row.get("server") if isinstance(row, dict) else None,
                                     "repetition": row.get("repetition") if isinstance(row, dict) else None,
                                     "reasons": sorted(set(reasons)),
                                     "raw_timing_invalid_reasons": row.get("timing_invalid_reasons") if isinstance(row, dict) else None,
                                     "raw_timing_valid": row.get("timing_valid") if isinstance(row, dict) else None,
                                     "raw_correctness_valid": row.get("correctness_valid") if isinstance(row, dict) else None,
                                     "raw_failures": row.get("failures") if isinstance(row, dict) else None})
        elif key is not None:
            eligible[key] = row
        if isinstance(row, dict) and row.get("workload") in target_only and row.get("server") == candidate:
            exclusions_counts["target_only_no_live_reference_pair"] += 1
    gates = metadata.get("paired_timing_repetitions", [])
    pairs = []
    for workload in workloads:
        reference_rows = {number: row for (name, server, number), row in eligible.items() if name == workload and server == reference}
        candidate_rows = {number: row for (name, server, number), row in eligible.items() if name == workload and server == candidate}
        reasons = list(gate_reasons)
        matching = sorted(reference_rows.keys() & candidate_rows.keys())
        gate_matches = [gate for gate in gates if isinstance(gate, dict) and gate.get("workload") == workload
                        and gate.get("baseline") == reference and gate.get("candidate") == candidate] if isinstance(gates, list) else []
        if len(gate_matches) != 1:
            reasons.append("recorded_pair_gate_missing_or_duplicate")
            gate = None
        else:
            gate = gate_matches[0]
            if gate.get("outcome") != "available":
                reasons.append("recorded_pair_gate_not_available")
            recorded_matches = gate.get("valid_matching_repetitions", [])
            if not isinstance(recorded_matches, list) or not all(repetition(number) for number in recorded_matches):
                reasons.append("recorded_pair_repetitions_malformed")
                matching = []
            else:
                matching = sorted(set(matching) & set(recorded_matches))
        minimum = max(MINIMUM_MATCHES, metadata.get("minimum_valid_paired_repetitions", MINIMUM_MATCHES) if repetition(metadata.get("minimum_valid_paired_repetitions")) else MINIMUM_MATCHES,
                      gate.get("required", MINIMUM_MATCHES) if gate and repetition(gate.get("required")) else MINIMUM_MATCHES)
        if len(matching) < minimum:
            reasons.append("fewer_than_required_matching_valid_repetitions")
        if workload in target_only:
            reasons.append("target_only_no_live_reference_pair")
        if workload == "exception-to-500":
            reasons.append("unequal_exception_diagnostic_policy")
        pair = {"workload": workload, "reference": reference, "candidate": candidate,
                "valid_reference_repetitions": sorted(reference_rows), "valid_rust_repetitions": sorted(candidate_rows),
                "matched_repetitions": matching, "minimum_required": minimum,
                "recorded_pair_gate": gate, "qualified": not reasons,
                "exclusion_reasons": sorted(set(reasons)), "metrics": {},
                "excluded_reference_details": exclusions.get(workload, {}) if isinstance(exclusions, dict) else {}}
        if pair["qualified"]:
            reference_rows = {number: reference_rows[number] for number in matching}
            candidate_rows = {number: candidate_rows[number] for number in matching}
            if category == "lifecycle":
                for key in LIFECYCLE_METRICS:
                    predicate = None
                    if "server_cpu" in key:
                        phase = "idle" if key.startswith("idle_") else "active"
                        predicate = lambda row, phase=phase: row.get("phase_measurements", {}).get(phase, {}).get("server_cpu_complete") is True
                    pair["metrics"][key] = median_pair(reference_rows, candidate_rows, key, predicate, minimum)
                pair["operation_unit"] = "two independent process lifetimes: idle and active"
                pair["cpu_accounting"] = "explicit complete reaped-server lifetime CPU; different boundary from sustained requests"
            else:
                throughput = "messages_per_second" if category == "websocket" else "requests_per_second"
                pair["operation_unit"] = "completed handshakes" if category == "websocket" and workload == "connection-handshake" else "completed echoed messages" if category == "websocket" else "completed HTTP requests"
                pair["metrics"]["operations_per_second"] = median_pair(reference_rows, candidate_rows, throughput, minimum=minimum)
                for name, key in SUSTAINED_METRICS.items():
                    pair["metrics"][name] = median_pair(reference_rows, candidate_rows, key, minimum=minimum)
                for name, key in (("client_cpu_seconds_complete", "client_cpu_seconds"),
                                  ("client_cpu_percent_elapsed_complete", "client_cpu_percent_elapsed"),
                                  ("client_cpu_microseconds_per_operation_complete", "client_cpu_microseconds_per_request")):
                    pair["metrics"][name] = median_pair(reference_rows, candidate_rows, key, lambda row: row.get("client_cpu_complete") is True, minimum)
                ratio_repetitions = [number for number in matching if numeric(reference_rows[number].get(throughput)) and reference_rows[number][throughput] > 0 and numeric(candidate_rows[number].get(throughput)) and candidate_rows[number][throughput] > 0]
                pair["throughput_ratio"] = {"definition": "median of same-repetition Rust/reference throughput ratios",
                                            "matched_repetitions": ratio_repetitions,
                                            "rust_over_reference": statistics.median(candidate_rows[number][throughput] / reference_rows[number][throughput] for number in ratio_repetitions) if len(ratio_repetitions) >= minimum else None}
                pair["cpu_accounting"] = {"server": "observed live process-tree CPU deltas; no complete reaped-child accounting inferred",
                                          "client": "complete RUSAGE_CHILDREN accounting only for explicitly marked paired rows"}
                pair["raw_server_cpu_complete_markers"] = {"reference": [reference_rows[number].get("server_cpu_complete") for number in matching],
                                                           "rust": [candidate_rows[number].get("server_cpu_complete") for number in matching]}
        pairs.append(pair)
    qualified_count = sum(pair["qualified"] for pair in pairs)
    dirty = metadata.get("dirty_target")
    status = "incomplete_category" if not complete else "no_qualified_pairs" if not qualified_count else "qualified_local_pairs"
    return {
        "category": category, "status": status, "source": loaded["source"], "input_sha256": loaded["input_sha256"],
        "complete_report_present": loaded["complete_report_present"], "rows": len(rows),
        "eligible_rows": len(eligible), "invalid_rows": len(invalid_receipts),
        "invalid_reason_row_counts": dict(sorted(invalid_counts.items())),
        "raw_timing_invalid_reason_row_counts": dict(sorted(raw_invalid_counts.items())),
        "pair_exclusion_row_counts": dict(sorted(exclusions_counts.items())),
        "raw_invalid_row_receipts": invalid_receipts, "input_errors": loaded["input_errors"],
        "missing_or_duplicate_expected_rows": missing, "metadata_gate_reasons": sorted(set(gate_reasons)),
        "qualified_pairs": qualified_count, "pairs": pairs,
        "evidence_scope": "frozen dirty local evidence; not a release performance proof" if dirty is True else "recorded frozen checkout evidence; no compilation attestation inferred" if dirty is False else "evidence scope unavailable from incomplete metadata",
        "dirty_target": metadata.get("dirty_target"), "git_revision": metadata.get("git_revision"),
        "recorded_performance_evidence_status": metadata.get("performance_evidence_status"),
        "modified_or_unrecorded_dependencies": metadata.get("modified_or_unrecorded_dependencies", []),
        "recorded_identity_before": metadata.get("identity_before"),
        "recorded_identity_after": metadata.get("identity_after"),
        "reference_logging_policy": metadata.get("reference_logging_policy", metadata.get("cancellation_diagnostic_normalization")),
        "lifespan_policy": metadata.get("lifespan_policy"),
        "recorded_cpu_resource_boundary": metadata.get("resource_boundary"),
        "recorded_latency_limitations": metadata.get("latency_limitations"),
    }


def cell(value):
    return "—" if value is None else f"{value:,.3f}" if abs(value) < 100 else f"{value:,.1f}"


def paired_cell(pair, key):
    value = pair["metrics"].get(key, {})
    return f"{cell(value.get('reference'))} / {cell(value.get('rust'))}"


def escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(report):
    lines = ["# Recorded benchmark analysis", "", f"Status: **{report['status']}**. All metric cells use reference / Rust values from matching valid repetitions.",
             "", "| Category | Status | Rows / invalid | Qualified pairs | Evidence |",
             "| --- | --- | ---: | ---: | --- |"]
    for category in report["categories"]:
        lines.append(f"| {category['category']} | {category['status']} | {category['rows']} / {category['invalid_rows']} | {category['qualified_pairs']} | {escape(category['evidence_scope'])} |")
    lines += ["", "## Matched throughput and latency", "",
              "HTTP rate is requests/s; WebSocket rate is completed messages/s or handshakes/s. Latency cells are p50 / p95 / p99 in ms, separately for each server.",
              "", "| Category / workload | Pairs | Rate ref / Rust | Latency ref | Latency Rust | Rust/ref rate |",
              "| --- | ---: | ---: | --- | --- | ---: |"]
    qualified = [(category["category"], pair) for category in report["categories"] if category["category"] != "lifecycle" for pair in category["pairs"] if pair["qualified"]]
    for name, pair in qualified:
        reference_latency = " / ".join(cell(pair["metrics"][key]["reference"]) for key in ("p50_ms", "p95_ms", "p99_ms"))
        rust_latency = " / ".join(cell(pair["metrics"][key]["rust"]) for key in ("p50_ms", "p95_ms", "p99_ms"))
        lines.append(f"| {name} / {escape(pair['workload'])} | {len(pair['matched_repetitions'])} | {paired_cell(pair, 'operations_per_second')} | {reference_latency} | {rust_latency} | {cell(pair['throughput_ratio']['rust_over_reference'])} |")
    if not qualified:
        lines.append("| No qualified matching pairs | — | — | — | — | — |")
    lines += ["", "## Matched resource metrics", "",
              "Server CPU is observed live process-tree CPU µs/op over its recorded boundary. Client CPU is complete reaped-child CPU µs/op only when explicitly marked. RSS cells are medians of sampled peak MiB.",
              "", "| Category / workload | Server CPU µs/op ref / Rust | Server RSS ref / Rust | Client CPU µs/op ref / Rust | Client RSS ref / Rust |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for name, pair in qualified:
        lines.append(f"| {name} / {escape(pair['workload'])} | {paired_cell(pair, 'server_cpu_microseconds_per_operation')} | {paired_cell(pair, 'server_rss_sampled_peak_mib')} | {paired_cell(pair, 'client_cpu_microseconds_per_operation_complete')} | {paired_cell(pair, 'client_rss_sampled_peak_mib')} |")
    if not qualified:
        lines.append("| No qualified matching pairs | — | — | — | — |")
    lines += ["", "## Lifecycle", "",
              "Startup is a preparation-to-observed-response upper bound. CPU is complete reaped-server lifetime seconds, with idle and active phases kept separate.",
              "", "| Pairs | Startup ms ref / Rust | Idle exit ms ref / Rust | Held exit ms ref / Rust | Idle CPU s ref / Rust | Active CPU s ref / Rust | Idle RSS MiB ref / Rust | Active RSS MiB ref / Rust |",
              "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    lifecycle = [pair for category in report["categories"] if category["category"] == "lifecycle" for pair in category["pairs"] if pair["qualified"]]
    for pair in lifecycle:
        keys = ("cold_start_to_first_lifespan_request_ms", "idle_sigterm_to_process_exit_ms", "active_sigterm_to_process_exit_ms",
                "idle_phase_server_cpu_seconds", "active_phase_server_cpu_seconds", "idle_phase_server_rss_peak_mib", "active_phase_server_rss_peak_mib")
        lines.append(f"| {len(pair['matched_repetitions'])} | " + " | ".join(paired_cell(pair, key) for key in keys) + " |")
    if not lifecycle:
        lines.append("| No qualified matching lifecycle pairs | — | — | — | — | — | — | — |")
    lines += ["", "## Exclusions and incomplete inputs", ""]
    for category in report["categories"]:
        counts = category["invalid_reason_row_counts"]
        if counts:
            lines.append(f"- {category['category']} invalid row reasons: " + "; ".join(f"{escape(reason)}={count}" for reason, count in counts.items()) + ".")
        if category["pair_exclusion_row_counts"]:
            lines.append(f"- {category['category']} target-only exclusions: {category['pair_exclusion_row_counts']}.")
        for pair in category["pairs"]:
            if not pair["qualified"]:
                lines.append(f"- {category['category']}/{escape(pair['workload'])}: {len(pair['matched_repetitions'])} matching valid repetitions; " + "; ".join(escape(reason) for reason in pair["exclusion_reasons"]) + ".")
    lines += ["", "## Interpretation limits", ""]
    lines += [f"- {value}" for value in report["limitations"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="directory containing run.json and category JSON/JSONL artifacts")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args()
    directory = args.input_dir.resolve()
    driver, driver_error = None, None
    driver_path = directory / "run.json"
    if driver_path.exists():
        try:
            driver = decode(driver_path.read_bytes())
            if not isinstance(driver, dict):
                raise ValueError("driver record must be an object")
        except (OSError, ValueError) as error:
            driver_error = str(error)
            driver = None
    categories = [analyze_category(load_category(directory, name), driver) for name in CATEGORIES]
    qualified_count = sum(category["qualified_pairs"] for category in categories)
    driver_incomplete = driver_error is not None or (driver is not None and driver.get("status") not in {"completed_correctness_gated", "completed_with_failures"})
    incomplete = driver_incomplete or any(category["status"] == "incomplete_category" for category in categories)
    report = {
        "schema": "uvicorn-rs-paired-category-analysis@1",
        "analyzer_sha256": digest(Path(__file__).read_bytes()), "input_directory": str(directory),
        "status": "incomplete_categories" if incomplete else "no_qualified_pairs" if not qualified_count else "qualified_local_pairs",
        "minimum_matching_valid_repetitions": MINIMUM_MATCHES,
        "evidence_scope": "frozen dirty local evidence; no release or published-package performance proof" if any(category["dirty_target"] is True for category in categories) else "recorded local evidence; inspect category completeness and dependency identities",
        "eligibility_policy": "timing_valid=true, failures=0, correctness_valid=true when present, strict server lifecycle/panic/native-error gates; lifecycle phases also complete; only intersection with an available recorded metadata pair gate can produce metrics",
        "correctness_field_compatibility": "Sustained rows lack a dedicated correctness_valid field; failures=0 and server_lifecycle_gate=passed are required. Explicit correctness_valid=false always fails.",
        "metric_policy": "each metric requires at least three matching finite values; complete client/lifecycle CPU additionally requires explicit completeness on both servers' matching rows",
        "ratio_policy": "median same-repetition Rust/reference rate ratios; no aggregate winner or significance claim",
        "driver_record": {"path": str(driver_path), "status": driver.get("status") if driver else None,
                          "incomplete": driver_incomplete,
                          "input_error": driver_error, "identity_before": driver.get("identity_before") if driver else None,
                          "identity_after": driver.get("identity_after") if driver else None,
                          "public_parity_gate": driver.get("public_parity_gate") if driver else None},
        "qualified_pairs": qualified_count, "categories": categories, "limitations": LIMITATIONS,
    }
    outputs = (args.output_json or directory / "analysis.json", args.output_markdown or directory / "analysis.md")
    if outputs[0].resolve() == outputs[1].resolve():
        raise ValueError("analysis JSON and Markdown output paths must differ")
    for path in outputs:
        if path.resolve() == driver_path.resolve() or path.name in {f"{name}{suffix}" for name in CATEGORIES for suffix in (".json", ".jsonl", ".failure.json", ".jsonl.meta.json", ".phases.jsonl", ".phases.jsonl.meta.json")}:
            raise ValueError(f"refusing to overwrite a raw input artifact: {path}")
    for path, content in zip(outputs, (json.dumps(report, indent=2, allow_nan=False) + "\n", markdown(report))):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".next")
        temporary.write_text(content)
        temporary.replace(path)
    print(json.dumps({"status": report["status"], "qualified_pairs": qualified_count,
                      "analysis_json": str(outputs[0]), "analysis_markdown": str(outputs[1])}))


if __name__ == "__main__":
    main()
