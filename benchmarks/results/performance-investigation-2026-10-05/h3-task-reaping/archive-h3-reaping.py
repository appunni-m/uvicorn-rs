"""Losslessly archive recorded H3 diagnostics; never run either server."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/performance-2026-10-05"
OUT = ROOT / "benchmarks/results/performance-investigation-2026-10-05"
ORIGINALS = {}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"refusing to overwrite an archive artifact: {destination}")
    before = digest(source)
    shutil.copy2(source, destination)
    if digest(source) != before or digest(destination) != before:
        raise RuntimeError(f"source changed during lossless copy: {source}")
    ORIGINALS[destination] = source


def copy_tree(source, destination, exclude=()):
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name not in exclude:
            copy(path, destination / path.relative_to(source))


def manifest(directory, **metadata):
    files = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path == directory / "archive-manifest.json":
            continue
        source = ORIGINALS.get(path)
        files[str(path.relative_to(directory))] = {
            "bytes": path.stat().st_size, "sha256": digest(path),
            "original_path": str(source) if source else None,
            "byte_identical": source.read_bytes() == path.read_bytes() if source else None,
            "kind": "byte-identical original" if source else "derived analysis/documentation",
        }
    dump(directory / "archive-manifest.json", {
        "schema": "uvicorn-rs-lossless-benchmark-archive@1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "raw_copy_policy": "byte-identical originals and empty logs; original paths retained; no binaries",
        "files": files, **metadata,
    })
    for name, receipt in files.items():
        if digest(directory / name) != receipt["sha256"] or receipt["byte_identical"] is False:
            raise RuntimeError(f"archive verification failed: {directory / name}")
    return len(files)


def correct(row):
    return (isinstance(row, dict) and row.get("failures") == 0
            and row.get("server_lifecycle_gate") == "passed"
            and row.get("unexpected_panic_events") == 0
            and row.get("unexpected_native_errors") == 0
            and row.get("requests", 0) > 0
            and row.get("server_shutdown", {}).get("returncode") == 0
            and row.get("server_shutdown", {}).get("forced") is False)


def summarize(report, source_path):
    rows = report["rows"]
    metadata = report["metadata"]
    selected = [row for row in rows if correct(row)]
    peaks = [row["server_rss_peak_mib"] for row in selected]
    valid = sorted(row["repetition"] for row in selected if row["timing_valid"] is True)
    reasons = Counter(reason for row in rows for reason in set(row["timing_invalid_reasons"]))
    return {
        "report": str(source_path.relative_to(OUT)), "report_sha256": digest(source_path),
        "rows": len(rows), "correct_response_and_shutdown_rows": len(selected),
        "timing_valid_repetitions": valid, "timing_valid_rows": len(valid),
        "timing_invalid_rows": sum(row["timing_valid"] is not True for row in rows),
        "timing_invalid_reason_row_counts": dict(reasons),
        "rss_descriptive_all_correct_runs_mib": {"definition": "median/min/max of sampled process-tree peak RSS across every correct run, including timing-invalid runs; not a qualified speed metric",
                                                "count": len(peaks), "median": statistics.median(peaks),
                                                "min": min(peaks), "max": max(peaks)},
        "requests_completed_range": {"min": min(row["requests"] for row in selected),
                                     "max": max(row["requests"] for row in selected)},
        "source_sha256": metadata["identity_before"]["source_files"]["src/lib.rs"],
        "native_extension": metadata["identity_before"]["native_extension"],
        "client_sha256": metadata["identity_before"]["clients"],
        "identity_stable": metadata["identity_stable"],
        "installed_dependencies_stable": metadata["installed_dependencies_before"] == metadata["installed_dependencies_after"],
        "dirty_target": metadata["dirty_target"], "runtime_diagnostics": metadata["runtime_diagnostics"],
        "performance_evidence_status": metadata["performance_evidence_status"],
        "started_at": metadata["started_at"], "finished_at": metadata["finished_at"],
        "row_observations": [{key: row[key] for key in ("repetition", "requests", "server_rss_peak_mib", "timing_valid",
                                                         "timing_invalid_reasons", "failures", "server_lifecycle_gate",
                                                         "unexpected_panic_events", "unexpected_native_errors")}
                             for row in rows],
    }


def main():
    task = OUT / "h3-task-reaping"
    normal = OUT / "current-normal-h3-reaping"
    diagnostic = OUT / "h3-diagnostics"
    reproducibility = OUT / "reproducible-runner"
    for directory in (task, normal, diagnostic, reproducibility):
        directory.mkdir(exist_ok=False)
    reports = {}
    for arm in ("before", "after"):
        directory = task / arm
        directory.mkdir()
        prefix = BUILD / f"h3-retention-{arm}"
        for suffix in (".json", ".jsonl", ".jsonl.meta.json", ".log"):
            copy(Path(str(prefix) + suffix), directory / (prefix.name + suffix))
        copy_tree(Path(str(prefix) + ".artifacts"), directory / (prefix.name + ".artifacts"))
        reports[arm] = json.loads((directory / (prefix.name + ".json")).read_text())
        report = reports[arm]
        assert report["metadata"]["identity_stable"] is True
        assert report["metadata"]["identity_before"] == report["metadata"]["identity_after"]
        assert len(report["rows"]) == 5 and all(correct(row) for row in report["rows"])
        assert report["rows"] == [json.loads(line) for line in (directory / (prefix.name + ".jsonl")).read_text().splitlines()]
        for name, expected in report["metadata"]["identity_before"]["source_files"].items():
            choices = [ROOT / name, OUT / "categories-error-logs/evidence-snapshot" / name]
            if name == "src/lib.rs":
                choices.insert(0, OUT / "current-normal/src/lib.rs" if arm == "before" else BUILD / "h3-reaping-normal/src/lib.rs")
            source = next((path for path in choices if path.is_file() and digest(path) == expected), None)
            if source is None:
                raise RuntimeError(f"no byte-matching measured source snapshot: {arm}/{name}")
            copy(source, directory / "measured-source-snapshot" / name)

    before, after = (reports[name]["metadata"] for name in ("before", "after"))
    common_keys = ("python", "rustc", "platform", "machine", "cpu_model", "concurrency", "duration_seconds",
                   "warmup_seconds", "workload_concurrency", "load_model", "h3_client", "seed", "workloads", "servers")
    comparisons = {key: before[key] == after[key] for key in common_keys}
    assert all(comparisons.values())
    assert before["identity_before"]["clients"] == after["identity_before"]["clients"]
    assert before["installed_dependencies_before"] == after["installed_dependencies_before"]
    changed_sources = [name for name in before["identity_before"]["source_files"]
                       if before["identity_before"]["source_files"][name] != after["identity_before"]["source_files"][name]]
    assert changed_sources == ["src/lib.rs"]
    summaries = {arm: summarize(reports[arm], task / arm / f"h3-retention-{arm}.json") for arm in reports}
    matching = sorted(set(summaries["before"]["timing_valid_repetitions"]) & set(summaries["after"]["timing_valid_repetitions"]))
    limitations = [
        "Target-only before/after memory diagnostic; no stock-reference performance comparison is present.",
        "All before runs preceded all after runs; arms were not interleaved or randomized.",
        "Fixed elapsed closed-loop windows completed differing request counts; this is not equal-work or fixed-offered-rate evidence.",
        "RSS summaries include every correct run, including timing-invalid rows; host contention remains explicitly recorded.",
        "RSS is sampled process-tree resident memory, not allocator live/peak bytes, PSS, private memory, or proof of a Python payload leak.",
        "The source-level JoinSet ownership mechanism explains task-allocation retention, while the RSS measurements do not isolate allocator arenas or Python/native heap contributions.",
        "No qualified throughput, latency, CPU gain, overall speedup, or statistical-significance claim is made.",
        "Both arms are frozen dirty local normal-release builds, not release or published-package performance proof.",
        "Clients, server and observer share the host; no open-loop test or coordinated-omission correction is available.",
    ]
    analysis = {
        "schema": "uvicorn-rs-h3-task-reaping-memory-diagnostic@1",
        "status": "descriptive_memory_observation_only_speed_not_proven",
        "analysis_script_sha256": digest(Path(__file__)),
        "arms": summaries, "recorded_configuration": {key: before[key] for key in common_keys},
        "configuration_equal_before_after": comparisons,
        "same_client_binary": True, "same_installed_dependencies": True,
        "changed_measured_source_files": changed_sources,
        "normal_release_build_receipts": {"before": "../current-normal/identity.json", "after": "../current-normal-h3-reaping/identity.json"},
        "speed_gate": {"required_matching_valid_repetitions": 3, "matching_valid_repetitions": matching,
                       "qualified_matching_valid_speed_pairs": 0, "qualified_speed_metrics": {},
                       "reason": "Before has two valid timing repetitions; after has none; no speed pair qualifies. Sequential before/after labels are not an interleaved stock-reference comparison."},
        "source_mechanism": {"before": "requests JoinSet joined only after acceptance ended; completed task allocations could remain owned during persistent connections",
                             "after": "requests.join_next() is selected during acceptance; completed tasks are observed and reaped while connections remain open",
                             "preserved_structure": "server cancellation remains the first biased branch, final request-task drain remains, and JoinError reporting is shared"},
        "limitations": limitations,
    }
    dump(task / "analysis.json", analysis)
    lines = ["# HTTP/3 request-task reaping memory diagnostic", "",
             "**Memory observation only; speed improvement is not proven.** This compares two Rust builds, without a stock reference.", "",
             "| Arm | Correct runs | Timing-valid runs | Sampled peak RSS median (MiB) | Sampled peak RSS range (MiB) | Completed request range |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for arm, summary in summaries.items():
        rss = summary["rss_descriptive_all_correct_runs_mib"]; requests = summary["requests_completed_range"]
        lines.append(f"| {arm} | {summary['correct_response_and_shutdown_rows']}/5 | {summary['timing_valid_rows']}/5 | {rss['median']:.3f} | {rss['min']:.3f}–{rss['max']:.3f} | {requests['min']:,}–{requests['max']:,} |")
    lines += ["", "RSS summaries use all ten correct runs, including eight timing-invalid rows. The matching valid speed-pair count is zero. No throughput, latency or CPU medians/ratios are derived.",
              "", "## Raw per-run observations", "",
              "| Arm / repetition | Completed requests | Sampled peak RSS (MiB) | Timing valid | Raw invalid reason |",
              "| --- | ---: | ---: | --- | --- |"]
    for arm, summary in summaries.items():
        for row in summary["row_observations"]:
            lines.append(f"| {arm} / {row['repetition']} | {row['requests']:,} | {row['server_rss_peak_mib']:.3f} | {str(row['timing_valid']).lower()} | {', '.join(row['timing_invalid_reasons']) or '—'} |")
    lines += ["", "## Matched configuration and mechanism", "",
              "Both arms used the identical `examples.bench_matrix_asgi:app` protocol-scope workload, Python 3.12.13, uvloop 0.23.0, Rust 1.98.1, normal release mode, the same QUIC client binary, concurrency 64 over four multiplexed connections, one-second warmup and five-second load windows on an Apple M3 Pro. Every response status and byte passed validation; all server exits were clean without unexpected native errors or panics. Measured source records differ only at `src/lib.rs`; complete snapshots and identities are retained.",
              "", "The prior connection-level `JoinSet` accumulated request tasks and joined them after acceptance ended. The change joins completed request tasks during acceptance and keeps cancellation priority, final draining and shared JoinError reporting. This source-level ownership change is consistent with the lower observed RSS. RSS alone does not identify heap allocations, allocator retention or a Python payload leak.",
              "", "All before repetitions ran before all after repetitions. Closed-loop windows completed different amounts of work; no fixed-request-count, interleaved or equal-offered-rate comparison was run.",
              "", "## Interpretation limits", ""]
    lines.extend("- " + item for item in limitations)
    (task / "analysis.md").write_text("\n".join(lines) + "\n")
    (task / "README.md").write_text("""# HTTP/3 request-task reaping evidence

`before/` and `after/` retain every original report, JSONL row, provenance
sidecar, runner log and individual server log as byte-identical copies, with
original paths preserved in `archive-manifest.json`. Each arm additionally has
a source snapshot checked against every measured source-file SHA. Binaries are
identified by SHA but are not stored here. The original files remain unchanged.

Read [analysis.md](analysis.md) for descriptive sampled-RSS observations and
[analysis.json](analysis.json) for exact values, request counts, raw timing flags,
identities and limitations. All ten Rust runs passed response and graceful exit
checks. The two before timing-valid rows and zero after timing-valid rows yield
zero qualified matching speed pairs. The RSS medians include timing-invalid
runs explicitly; they are not throughput, latency or CPU evidence.

This is a target-only memory diagnostic. Before ran entirely before after and
the fixed-duration closed-loop windows completed different request counts. The
source mechanism is completed `JoinSet` task allocations retained until joining;
the change reaps them during acceptance. RSS is not a heap allocation profile,
an allocator-peak measurement, or proof of a Python-payload leak.

The before normal release identity is in `../current-normal/`; the changed
normal release identity/source/build/fmt/Clippy logs are in
`../current-normal-h3-reaping/`. Public parity for that changed binary is pending
in this archive until its owner appends the completed exact-binary gate. The
separate `../h3-diagnostics/` preserves stock Hypercorn failures and a low-load
functional observation without converting them into benchmark rankings.

`archive-h3-reaping.py` is the original stdlib-only archive/derivation command,
retained for inspection. It copies and hashes existing artifacts only and was
not used to execute an application, benchmark, build or probe.
""")
    copy(Path(__file__), task / "archive-h3-reaping.py")

    original_normal = BUILD / "h3-reaping-normal"
    if "Finished `dev` profile" not in (original_normal / "clippy.log").read_text():
        raise RuntimeError("wait for the original Clippy log to finish before archiving")
    copy_tree(original_normal, normal, exclude=("_native.abi3.so",))
    normal_identity = json.loads((normal / "identity.json").read_text())
    assert digest(normal / "src/lib.rs") == normal_identity["source_sha256"] == summaries["after"]["source_sha256"]
    assert normal_identity["native_sha256"] == summaries["after"]["native_extension"]["sha256"]
    (normal / "README.md").write_text("""# Normal release after HTTP/3 request-task reaping

Source, Cargo manifests/lockfile, build identity, completed release build log,
formatting log and completed Clippy log are byte-identical copies from the
original build directory. The identity records the exact source and installed
native SHA, compiler, build arguments, link flags and zero instrumentation
marker counts. No native binary is committed. The empty formatting log is
preserved without fabricating output; existing build/check logs were read,
not rerun by the archival command.

This binary produced the `../h3-task-reaping/after/` memory diagnostic. Those
five response/shutdown observations passed, while every timing row was invalid
due to host contention. This build identity alone is not a full public ASGI
parity gate or speed proof. Its owner will append the completed public
exact-binary gate separately; archive manifests then require refreshing.
""")

    copy_tree(BUILD / "h3-diagnostics", diagnostic)
    cases = []
    for directory in sorted(diagnostic.iterdir()):
        if not directory.is_dir():
            continue
        metadata = json.loads((directory / "report.jsonl.meta.json").read_text())
        deps = metadata["installed_dependencies_before"]
        assert all(not item["record_content_mismatches"] and not item["unrecorded_source_files"]
                   and not (item["direct_url"] and item["direct_url"].get("dir_info", {}).get("editable")) for item in deps.values())
        logs = list(directory.rglob("*-server.log"))
        text = "\n".join(path.read_text() for path in logs)
        case = {"directory": directory.name, "final_report_present": (directory / "report.json").exists(),
                "server_log_files": len(logs), "hypercorn_version": deps["hypercorn"]["version"],
                "aioquic_version": deps["aioquic"]["version"], "uvloop_version": deps["uvloop"]["version"],
                "stock_dependency_record_checks_passed": True,
                "key_error_72_terminal_events": len(re.findall(r"KeyError: 72", text)),
                "exception_group_contains_key_error_72": "KeyError(72)" in text}
        if directory.name.startswith("c1-") and not case["final_report_present"]:
            case["outcome"] = "infrastructure failure finding TCP/UDP port under sandbox; no server/load observation"
        elif directory.name.startswith("c1-"):
            report = json.loads((directory / "report.json").read_text())
            row = report["rows"][0]
            case.update(outcome="low-concurrency functional observation only", requests=row["requests"], failures=row["failures"],
                        timing_valid=row["timing_valid"], timing_invalid_reasons=row["timing_invalid_reasons"],
                        server_lifecycle_gate=row["server_lifecycle_gate"])
        else:
            case["outcome"] = "concurrency-16 client correctness timeout and stock Hypercorn UDP task ExceptionGroup containing KeyError(72)"
        cases.append(case)
    dump(diagnostic / "summary.json", {"schema": "uvicorn-rs-stock-h3-functional-diagnostics@1", "cases": cases,
                                      "performance_evidence_status": "not_proven",
                                      "scope": "stock unmodified reference diagnostic; no benchmark gain or fabricated successful row"})
    (diagnostic / "README.md").write_text("""# Unmodified Hypercorn HTTP/3 diagnostics

All original directories, empty checkpoints, metadata, complete reports,
runner logs and server error logs are retained byte for byte. Package source
and native files were checked against their installed RECORD hashes in the
original evidence; no edited or editable reference distribution is recorded.
The reference was Hypercorn 0.18.0 with aioquic 1.3.0 and uvloop 0.23.0.

- `c1-1s-warm0-20261005-a`: sandbox/infrastructure failure finding a numeric
  port available to TCP and UDP; no load or server outcome was recorded.
- `c1-1s-warm0-20261005-b`: concurrency-one functional observation passed its
  response/lifecycle checks, with an empty server log. Its timing remained
  invalid due to unrelated host CPU activity and is not a speed comparison.
- `c16-1s-warm0-20261005-a`: the client timed out awaiting H3 response headers;
  its partial report records 69 completed requests and 16 failures. The full
  post-shutdown server log contains an unhandled UDP-task ExceptionGroup with
  `KeyError(72)` and the terminal `KeyError: 72`, along with the task-group
  shutdown error. `72` is the stream key, not a count of 72 errors. The category
  deliberately has no successful final report or fabricated successful row.

These functional diagnostics do not prove an upstream root cause and do not
justify altering the stock reference or reducing the concurrency of a purported
matched performance comparison. `summary.json` classifies the recorded outcomes;
the raw logs remain authoritative and unchanged.
""")

    copy_tree(BUILD / "reproducible-runner", reproducibility)
    tracked = {"run_benchmark_categories.py": "scripts/run_benchmark_categories.py",
               "analyze_benchmark_categories.py": "scripts/analyze_benchmark_categories.py",
               "benchmark-categories.yml": ".github/workflows/benchmark-categories.yml"}
    for name, path in tracked.items():
        assert digest(ROOT / path) == digest(reproducibility / name)
    check = json.loads((reproducibility / "analysis-check.json").read_text())
    assert check["status"] == "incomplete_categories" and check["qualified_pairs"] == 0
    dump(reproducibility / "promotion-receipt.json", {
        "schema": "uvicorn-rs-reproducible-benchmark-promotion@1",
        "tracked_files": {path: {"sha256": digest(ROOT / path), "byte_identical_to_candidate": True} for path in tracked.values()},
        "verification": {"driver_help_log": "driver-help.log", "analysis_check_status": check["status"],
                         "analysis_check_qualified_pairs": check["qualified_pairs"],
                         "analysis_input_directory": check["input_directory"],
                         "original_reports_unchanged": "root owner reported unchanged raw inputs; copies verified against their original candidate files"},
        "workflow_execution": "not dispatched or executed on Linux; no publishing",
        "anonymous_repository_readability": "root owner verified anonymous ls-remote HEAD; exact frozen framework revision reachability not verified",
        "archival_runtime_policy": "stdlib-only reads, JSON analysis, copies and hashes; no project/native imports, application execution, tests, builds, probes or benchmarks",
    })
    (reproducibility / "ARCHIVE.md").write_text("""# Reproducible runner promotion receipt

The candidates and original proposal README are retained as byte-identical
historical files. Root subsequently added the identical driver/analyzer and
manual workflow at the tracked paths in `promotion-receipt.json`. The original
README describes the earlier candidate state; this receipt records promotion.

The driver CLI help check passed and its complete output is retained.
The pure-JSON analyzer ran on the earlier partial category artifacts and
correctly reported `incomplete_categories` with zero qualified pairs; derived
JSON/Markdown are retained and original raw reports were unchanged. No Linux
workflow has run, no workflow was dispatched, and no package was published.

Anonymous public repository HEAD readability was checked by the root owner;
reachability of the frozen framework revision is still unverified. The fresh
Linux build, exact public parity gate, functional smoke, and full manual
timings/artifact review remain required before making performance claims.
""")
    counts = {
        "h3-task-reaping": manifest(task, summary={"correct_runs": 10, "timing_valid_before": 2, "timing_valid_after": 0, "qualified_speed_pairs": 0}),
        "current-normal-h3-reaping": manifest(normal, omitted_native_binary=str(original_normal / "_native.abi3.so"), native_sha256=normal_identity["native_sha256"], public_parity_gate="pending owner append"),
        "h3-diagnostics": manifest(diagnostic, summary=cases),
        "reproducible-runner": manifest(reproducibility, workflow_execution="not executed; no dispatch/publishing"),
    }
    print(json.dumps({"archive_file_counts": counts,
                      "memory_descriptive_medians_mib": {arm: summaries[arm]["rss_descriptive_all_correct_runs_mib"]["median"] for arm in summaries},
                      "qualified_speed_pairs": 0, "byte_identity_verified": True}, indent=2))


if __name__ == "__main__":
    main()
