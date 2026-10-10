#!/usr/bin/env python3
"""Run the maintained ASGI benchmark categories against stock live references.

Build the normal server and Rust clients before invoking this wrapper. Capture
an identity, run the complete public parity suite on that binary, then supply
both artifacts. Every category runs sequentially and retains its original
JSON, JSONL, server logs, and failure observations. No package is published.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid


CATEGORIES = (
    ("http1", "run_http_category_bench.py", (
        ("asyncio", "uvicorn-asyncio-httptools", "uvicorn-rs-asyncio"),
        ("uvloop", "uvicorn-uvloop-httptools", "uvicorn-rs-uvloop"),
    )),
    ("http2", "run_h2_category_bench.py", (
        ("asyncio", "hypercorn-asyncio", "uvicorn-rs-asyncio"),
        ("uvloop", "hypercorn-uvloop", "uvicorn-rs-uvloop"),
    )),
    ("http3", "run_h3_category_bench.py", (
        ("asyncio", "hypercorn-asyncio", "uvicorn-rs-asyncio"),
        ("uvloop", "hypercorn-uvloop", "uvicorn-rs-uvloop"),
    )),
    ("websocket", "run_websocket_category_bench.py", (
        ("asyncio", "uvicorn-asyncio-websockets", "uvicorn-rs-asyncio"),
        ("uvloop", "uvicorn-uvloop-websockets", "uvicorn-rs-uvloop"),
    )),
    ("lifecycle", "run_lifecycle_bench.py", (
        ("asyncio", "uvicorn-asyncio-httptools", "uvicorn-rs-asyncio"),
        ("uvloop", "uvicorn-uvloop-httptools", "uvicorn-rs-uvloop"),
    )),
)
PROBE_NAMES = ("http2", "bench", "websocket", "parity-http3")
LIMITATIONS = (
    "Same-host closed-loop load couples client, server, and observer CPU.",
    "Three matching valid repetitions are descriptive evidence, not statistical significance.",
    "Host contention and incomplete/invalid rows remain excluded; guards are never relaxed.",
    "HTTP/3 uses its separately recorded low-load concurrency because higher same-host load caused Hypercorn reference timeouts.",
    "Protocol-specific latency/setup/drain clocks cannot be compared across protocols.",
    "H3 uploads have no qualifying Hypercorn performance pair; deliberate exceptions remain unrankable.",
    "Dirty target evidence is local and provisional; no source-to-binary attestation is inferred from hashes alone.",
    "RSS is sampled process-tree RSS, and sustained server CPU differs from complete client/lifecycle CPU accounting.",
)


def repository_root():
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "Cargo.toml").is_file() and (candidate / "pyproject.toml").is_file() and (candidate / "scripts/benchmark_evidence.py").is_file():
            return candidate
    raise RuntimeError("place this command in a uvicorn-rs checkout")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".next")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def nonnegative_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and nonnegative")
    return number


def positive_integer(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def sha_argument(value):
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("must be a lowercase SHA-256 digest")
    return value


def workload_names(path):
    for statement in ast.parse(path.read_text()).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "WORKLOADS" for target in statement.targets):
            if not isinstance(statement.value, ast.Dict):
                raise ValueError(f"{path}: WORKLOADS must be a literal dictionary")
            names = [ast.literal_eval(key) for key in statement.value.keys]
            if not names or not all(isinstance(name, str) for name in names) or len(names) != len(set(names)):
                raise ValueError(f"{path}: missing or duplicate workload names")
            return names
    raise ValueError(f"{path}: no WORKLOADS dictionary")


def expected_rows(path, label, selected_servers, repetitions, selected_workloads=None):
    if label == "lifecycle":
        return {(label, name, number) for name in selected_servers
                for number in range(1, repetitions + 1)}
    statement = next(statement for statement in ast.parse(path.read_text()).body
                     if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name)
                         and target.id == "WORKLOADS" for target in statement.targets))
    expected = set()
    selected = set(selected_workloads) if selected_workloads is not None else None
    for key, definition in zip(statement.value.keys, statement.value.values):
        name = ast.literal_eval(key)
        if selected is not None and name not in selected:
            continue
        servers = tuple(selected_servers)
        if not isinstance(definition, ast.Dict):
            raise ValueError(f"{path}: workload {name} must use a literal dictionary")
        for field, value in zip(definition.keys, definition.values):
            if ast.literal_eval(field) == "servers":
                permitted = ast.literal_eval(value)
                servers = tuple(server for server in servers if server in permitted)
        expected.update((name, server, number) for server in servers
                        for number in range(1, repetitions + 1))
    return expected


def report_receipt(path, planned, label):
    report = json.loads(path.read_text())
    rows, metadata = report["rows"], report["metadata"]
    if not isinstance(rows, list) or not isinstance(metadata, dict):
        raise ValueError("category report needs rows and metadata")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("category rows must be JSON objects")
    observed = [(row.get("workload"), row.get("server"), row.get("repetition")) for row in rows]
    def zero_counter(row, name):
        value = row.get(name)
        return isinstance(value, int) and not isinstance(value, bool) and value == 0
    malformed = [number for number, row in enumerate(rows, 1)
                 if not zero_counter(row, "failures")
                 or row.get("correctness_valid", True) is not True
                 or row.get("server_lifecycle_gate") != "passed"
                 or not zero_counter(row, "unexpected_panic_events")
                 or not zero_counter(row, "unexpected_native_errors")
                 or not isinstance(row.get("repetition"), int) or isinstance(row.get("repetition"), bool)
                 or not isinstance(row.get("timing_valid"), bool)]
    if label == "lifecycle":
        for number, row in enumerate(rows, 1):
            phases = row.get("phase_measurements", {})
            if (row.get("active_asgi_task_started") is not True or row.get("active_asgi_task_cancelled") is not True
                    or not isinstance(phases, dict) or any(not isinstance(phases.get(phase), dict)
                        or phases[phase].get("correctness_valid") is not True
                        or phases[phase].get("lifespan_shutdown_complete") is not True for phase in ("idle", "active"))):
                malformed.append(number)
        malformed = sorted(set(malformed))
    complete = len(observed) == len(planned) and len(set(observed)) == len(observed) and set(observed) == planned
    return {
        "report_sha256": sha256(path), "rows": len(rows), "expected_rows": len(planned),
        "exact_planned_rows_present": complete,
        "correctness_failures": len(malformed), "failed_row_numbers": malformed,
        "timing_valid_rows": sum(row.get("timing_valid") is True for row in rows),
        "performance_evidence_status": metadata.get("performance_evidence_status", "not_proven"),
        "category_identity_stable": metadata.get("identity_stable") is True,
    }


def checked_tool(argv, root):
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=True, timeout=30)
    return (result.stdout or result.stderr).strip()


def source_paths(root):
    fixed = ["Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock", "tools/http3-probe/Cargo.toml", "tools/http3-probe/Cargo.lock"]
    trees = (("src", {".rs"}), ("python", {".py"}), ("scripts", {".py", ".mjs", ".c"}),
             ("examples", {".py"}), ("tools/http3-probe/src", {".rs"}), ("tests/parity", {".py", ".json"}))
    for directory, extensions in trees:
        fixed.extend(str(path.relative_to(root)) for path in (root / directory).rglob("*")
                     if path.is_file() and path.suffix in extensions and "__pycache__" not in path.parts
                     and str(path.relative_to(root)) != "examples/starlette_rs_asgi.py")
    fixed.append(str(Path(__file__).resolve().relative_to(root)))
    return sorted(set(fixed))


def normal_binary(path):
    if not path.is_file():
        raise RuntimeError(f"prebuild the normal release client: {path}")
    contents = path.read_bytes()
    markers = (b"coverage-injected", b"UVICORN_RS_COVERAGE_", b"__llvm_profile", b"__llvm_covmap", b"uvicorn-rs-runtime-diagnostics ")
    if any(marker in contents for marker in markers):
        raise RuntimeError(f"coverage/fault/diagnostic instrumentation is present: {path}")


def capture_identity(root, python, evidence_class):
    from benchmark_evidence import FASTAPI_BENCHMARK_DISTRIBUTIONS

    clients = [root / "tools/http3-probe/target/release" / name for name in PROBE_NAMES]
    for path in clients:
        normal_binary(path)
    extra_dependencies = {"uvicorn-rs": ["uvicorn_rs"]}
    try:
        importlib.metadata.distribution("fastapi")
    except importlib.metadata.PackageNotFoundError:
        fastapi_selected = False
        fastapi_reason = "optional fastapi-benchmark dependency group is not installed"
    else:
        fastapi_selected = True
        fastapi_reason = None
        extra_dependencies.update(FASTAPI_BENCHMARK_DISTRIBUTIONS)
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-benchmark-identity-") as directory:
        evidence = evidence_class(root, python, source_paths(root), clients,
                                  artifacts_dir=Path(directory),
                                  extra_dependencies=extra_dependencies)
        dependencies = evidence.dependencies_before
        required = {"uvicorn", "hypercorn", "h11", "h2", "aioquic", "uvloop", "httptools", "websockets", "uvicorn-rs"}
        if fastapi_selected:
            required.update(FASTAPI_BENCHMARK_DISTRIBUTIONS)
        if missing := sorted(required - dependencies.keys()):
            raise RuntimeError(f"frozen benchmark dependencies are missing: {missing}")
        modified = [name for name, value in dependencies.items() if name != "uvicorn-rs" and
                    (value["record_content_mismatches"] or value["unrecorded_source_files"] or
                     (value["direct_url"] and value["direct_url"].get("dir_info", {}).get("editable")))]
        if modified:
            raise RuntimeError(f"stock references and coherent benchmark dependencies required; modified/editable distributions: {modified}")
        snapshot = evidence.before
        return {
            "source": snapshot["source_files"]["src/lib.rs"],
            "native": snapshot["native_extension"]["sha256"],
            "optional_workloads": {"fastapi": {"selected": fastapi_selected, "reason": fastapi_reason}},
            "harness": {name: value for name, value in snapshot["source_files"].items() if name.startswith("scripts/")},
            "examples": {name: value for name, value in snapshot["source_files"].items() if name.startswith("examples/")},
            "snapshot": snapshot, "dependencies": dependencies,
            "python_runtime": evidence.runtime, "git_revision": evidence.git_revision,
            "dirty_target": evidence.dirty, "tracked_worktree_changes": evidence.git_changes,
            "wrapper_sha256": sha256(Path(__file__).resolve()),
        }


def validate_parity(root, before_path, parity_path, current, expected_count):
    from run_parity import load_contract, validate_result_shape

    before = json.loads(before_path.read_text())
    if before.get("schema") != "uvicorn-rs-benchmark-freeze@2" or before.get("identity") != current:
        raise RuntimeError("current source/native/apps/harness/dependencies differ from the before-parity freeze")
    manifest, inputs, paths = load_contract()
    selected = [case for case in inputs["cases"] if case.get("verification", "oracle-parity") != "fault-contract"]
    if expected_count is not None and len(selected) != expected_count:
        raise RuntimeError(f"review the public parity denominator: expected {expected_count}, found {len(selected)}")
    result = json.loads(parity_path.read_text())
    validate_result_shape(result, selected, manifest)
    summary = result["summary"]
    if result["status"] != "completed" or summary["selected"] != len(selected) or summary["executed"] != len(selected) or summary["passed"] != len(selected) or any(summary[key] != 0 for key in ("failed", "not_run", "infrastructure_failed")) or result["infrastructure_errors"]:
        raise RuntimeError("all currently indexed public parity cases must pass without infrastructure failures")
    target = result["run"]["target"]
    if target["native_extension"]["sha256"] != current["native"] or target["cargo_lock_sha256"] != sha256(root / "Cargo.lock") or target["revision"] != current["git_revision"]:
        raise RuntimeError("parity did not execute this exact native binary, Cargo.lock, and Git revision")
    harness = result["run"]["harness"]
    parity_http3 = harness.get("http3_client")
    frozen_http3_path = str(root / "tools/http3-probe/target/release/parity-http3")
    frozen_http3_sha256 = current["snapshot"]["clients"].get(frozen_http3_path)
    if (not isinstance(parity_http3, dict)
            or parity_http3.get("sha256") != frozen_http3_sha256):
        raise RuntimeError("public parity did not use the frozen HTTP/3 client binary")
    checks = [(root / result["run"]["manifest"]["path"], result["run"]["manifest"]["sha256"]),
              (root / harness["runner"], harness["runner_sha256"]),
              (root / harness["fixture_app"], harness["fixture_app_sha256"])]
    checks.extend((root / item["path"], item["sha256"]) for item in result["run"]["inputs"])
    if harness["http3_client"]:
        checks.append((root / harness["http3_client"]["path"], harness["http3_client"]["sha256"]))
    for path, expected in checks:
        if sha256(path) != expected:
            raise RuntimeError(f"parity input, runner, fixture, or client changed: {path}")
    if {str(path.relative_to(root)) for path in paths} != {item["path"] for item in result["run"]["inputs"]}:
        raise RuntimeError("parity result does not cover the exact current indexed input files")
    if result["run"]["environment"]["python"] != current["python_runtime"]["version"].split()[0]:
        raise RuntimeError("parity used a different Python version")
    return {"status": "passed", "public_cases": len(selected), "parity_report": str(parity_path),
            "parity_report_sha256": sha256(parity_path), "before_parity_identity": str(before_path),
            "before_parity_identity_sha256": sha256(before_path), "native_sha256": current["native"]}


def main():
    root = repository_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, help="checkout .venv/bin/python used by every maintained category")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--duration", type=positive_seconds, default=5.0)
    parser.add_argument("--warmup", type=nonnegative_seconds, default=1.0)
    parser.add_argument("--concurrency", type=positive_integer, default=64)
    parser.add_argument("--h3-concurrency", type=positive_integer, default=1,
                        help="HTTP/3 comparison concurrency; recorded separately from other categories")
    parser.add_argument("--repetitions", type=positive_integer, default=3)
    parser.add_argument("--seed", type=int, default=20261005)
    # Five repeats of the expanded HTTP/1 workload plan can exceed 20 minutes
    # before host startup, shutdown, and resource sampling overhead is counted.
    # Keep the category bounded while allowing the planned rows to finish.
    parser.add_argument("--category-timeout", type=positive_seconds, default=5400.0)
    parser.add_argument("--category", action="append", choices=[label for label, _, _ in CATEGORIES],
                        help="run selected category only; repeat to select more than one (default: all categories)")
    parser.add_argument("--workloads", nargs="+",
                        help="run only these workloads in one selected protocol category")
    parser.add_argument("--expected-source-sha256", type=sha_argument)
    parser.add_argument("--expected-native-sha256", type=sha_argument)
    parser.add_argument("--expected-public-cases", type=positive_integer)
    parser.add_argument("--capture-identity", type=Path, help="capture normal prebuilt identities before public parity; runs no benchmarks")
    parser.add_argument("--parity-before-identity", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--skip-analysis", action="store_true", help="retain only category artifacts; default runs the pure-JSON analyzer")
    args = parser.parse_args()
    if args.repetitions < 3:
        parser.error("the full comparison wrapper requires at least three repetitions")
    if args.category and len(args.category) != len(set(args.category)):
        parser.error("each category may be selected at most once")
    if args.workloads:
        if not args.category or len(args.category) != 1:
            parser.error("--workloads requires exactly one selected --category")
        selected_category = args.category[0]
        if selected_category == "lifecycle":
            parser.error("lifecycle is a single scenario and does not accept --workloads")
        selected_script = dict((label, name) for label, name, _ in CATEGORIES)[selected_category]
        known_workloads = set(workload_names(root / "scripts" / selected_script))
        unknown_workloads = sorted(set(args.workloads) - known_workloads)
        if unknown_workloads:
            parser.error(f"unknown workload names: {unknown_workloads}")
        if len(args.workloads) != len(set(args.workloads)):
            parser.error("--workloads cannot contain duplicates")
        if selected_category == "http1":
            non_fastapi = sorted(name for name in args.workloads if not name.startswith("fastapi-"))
            if non_fastapi:
                parser.error("the maintained cross-category comparison accepts upstream FastAPI workloads only: "
                             + ", ".join(non_fastapi))
    if args.capture_identity and (args.output_dir or args.parity_before_identity or args.parity_report):
        parser.error("capture mode cannot also run the suite")
    if not args.capture_identity and (not args.parity_before_identity or not args.parity_report):
        parser.error("supply --parity-before-identity and --parity-report for the complete public parity gate")
    python = (args.python or root / ".venv/bin/python").absolute()
    if not python.is_file():
        parser.error(f"Python interpreter does not exist: {python}")
    if python != (root / ".venv/bin/python").absolute():
        parser.error("maintained categories use the checkout .venv/bin/python; --python must name that interpreter")
    sys.path.insert(0, str(root / "scripts"))
    from benchmark_evidence import (BenchmarkEvidence, _refresh_owned, assert_clean_coverage_environment,
                                    owned_process, stop_owned)

    assert_clean_coverage_environment()
    before = capture_identity(root, python, BenchmarkEvidence)
    if not before["optional_workloads"]["fastapi"]["selected"]:
        raise RuntimeError("the maintained cross-category comparison requires the locked upstream fastapi-benchmark dependency group")
    requested_categories = set(args.category or (label for label, _, _ in CATEGORIES))
    selected_categories = [label for label, _, _ in CATEGORIES if label in requested_categories]
    omitted_categories = [label for label, _, _ in CATEGORIES if label not in requested_categories]
    for expected, observed, label in ((args.expected_source_sha256, before["source"], "source"),
                                      (args.expected_native_sha256, before["native"], "native")):
        if expected and expected != observed:
            raise RuntimeError(f"unexpected {label} SHA-256: {observed}")
    if args.capture_identity:
        destination = args.capture_identity.absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x") as output:
            json.dump({"schema": "uvicorn-rs-benchmark-freeze@2", "captured_at": utc_now(), "identity": before}, output, indent=2)
            output.write("\n")
        print(json.dumps({"identity": str(destination), "source_sha256": before["source"], "native_sha256": before["native"]}))
        return 0

    parity = validate_parity(root, args.parity_before_identity.absolute(), args.parity_report.absolute(), before, args.expected_public_cases)
    out = args.output_dir.absolute() if args.output_dir else root / "target/benchmark-categories" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
    out.mkdir(parents=True, exist_ok=False)
    record = {
        "schema": "uvicorn-rs-sequential-category-run@2", "started_at": utc_now(),
        "status": "running_not_proven", "identity_before": before, "category_runs": [],
        "category_scope": "complete" if not omitted_categories else "selected_subset",
        "workload_scope": "selected_subset" if args.workloads else "upstream_fastapi_only",
        "application_scope": {
            "framework": "upstream FastAPI and its locked Starlette/Pydantic dependencies",
            "http1_websocket_app": "examples.bench_fastapi:app",
            "lifecycle_app": "examples.bench_fastapi_lifecycle:app",
            "fastapi_rs": False,
            "starlette_rs": False,
        },
        "selected_categories": selected_categories, "omitted_categories": omitted_categories,
        "workload_exclusions": [],
        "public_parity_gate": parity, "limitations": list(LIMITATIONS),
        "parameters": {"duration": args.duration, "warmup": args.warmup, "concurrency": args.concurrency,
                       "h3_concurrency": args.h3_concurrency,
                       "repetitions": args.repetitions, "seed": args.seed, "category_timeout_seconds": args.category_timeout,
                       "comparison_pairs": {label: [
                           {"loop": loop, "reference": reference, "candidate": candidate}
                           for loop, reference, candidate in comparisons
                       ] for label, _, comparisons in CATEGORIES if label in selected_categories}},
        "tools": {},
    }
    checkpoint = out / "run.json"
    events = (out / "events.jsonl").open("x")
    process = None
    failed = False
    previous_term = signal.getsignal(signal.SIGTERM)

    def event(value):
        events.write(json.dumps(value) + "\n")
        events.flush()
        print(json.dumps(value), flush=True)

    def terminate(signum, frame):
        raise KeyboardInterrupt(f"benchmark suite received signal {signum}")

    signal.signal(signal.SIGTERM, terminate)
    atomic_json(checkpoint, record)
    try:
        for name, command in (("rustc", ["rustc", "--version"]), ("node", ["node", "--version"]),
                              ("cc", ["cc", "--version"]), ("curl", ["curl-config", "--version"]),
                              ("openssl", ["openssl", "version"])):
            record["tools"][name] = checked_tool(command, root).splitlines()[0]
            atomic_json(checkpoint, record)
        for label, name, comparisons in CATEGORIES:
            if label not in selected_categories:
                continue
            script = root / "scripts" / name
            output = out / f"{label}.json"
            servers = tuple(dict.fromkeys(
                server for _, reference, candidate in comparisons for server in (reference, candidate)
            ))
            command = [str(python), str(script), "--servers", *servers,
                       "--repetitions", str(args.repetitions), "--seed", str(args.seed), "--output", str(output)]
            workloads = ["lifecycle"]
            if label != "lifecycle":
                workloads = workload_names(script)
                if args.workloads and args.category == [label]:
                    workloads = list(dict.fromkeys(args.workloads))
                elif label == "http1":
                    workloads = [workload for workload in workloads if workload.startswith("fastapi-")]
                category_concurrency = args.h3_concurrency if label == "http3" else args.concurrency
                command += ["--workloads", *workloads, "--duration", str(args.duration),
                            "--warmup", str(args.warmup), "--concurrency", str(category_concurrency)]
            planned = expected_rows(
                script, label, servers, args.repetitions,
                selected_workloads=workloads if label != "lifecycle" else None,
            )
            entry = {"category": label, "command": command, "workloads": workloads,
                     "servers": list(servers),
                     "comparison_pairs": [
                         {"loop": loop, "reference": reference, "candidate": candidate}
                         for loop, reference, candidate in comparisons
                     ],
                     "expected_rows": len(planned), "started_at": utc_now(), "log": str(out / f"{label}.log")}
            record["category_runs"].append(entry)
            atomic_json(checkpoint, record)
            event({"event": "starting", **entry})
            process = None
            try:
                with (out / f"{label}.log").open("x") as log:
                    process = owned_process(command, cwd=root, env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT, text=True)
                    deadline = time.monotonic() + args.category_timeout
                    while True:
                        _refresh_owned(process)
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(f"category exceeded its {args.category_timeout:g}s wall limit")
                        try:
                            entry["exit_code"] = process.wait(timeout=min(0.25, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            continue
                entry["finished_at"] = utc_now()
                if output.exists():
                    entry.update(report_receipt(output, planned, label))
                    if entry["correctness_failures"] or not entry["exact_planned_rows_present"] or not entry["category_identity_stable"]:
                        failed = True
                else:
                    entry["report_state"] = "incomplete; category JSONL/log/failure checkpoints retained"
                    failed = True
                failed |= entry["exit_code"] != 0
            except Exception as caught:
                entry["error"] = {"type": type(caught).__name__, "message": str(caught)}
                failed = True
            finally:
                try:
                    entry["owned_process_cleanup"] = stop_owned(process, graceful=True)
                    if entry["owned_process_cleanup"]["forced"] or entry["owned_process_cleanup"]["returncode"] not in (None, 0):
                        failed = True
                except Exception as caught:
                    entry["cleanup_error"] = {"type": type(caught).__name__, "message": str(caught)}
                    failed = True
                process = None
                entry.setdefault("finished_at", utc_now())
                atomic_json(checkpoint, record)
            if capture_identity(root, python, BenchmarkEvidence) != before:
                raise RuntimeError("source/native/apps/harness/client/dependency identity changed during categories")
            atomic_json(checkpoint, record)
            event({"event": "finished", **entry})
        record["status"] = "completed_with_failures" if failed else "completed_correctness_gated"
    except KeyboardInterrupt as caught:
        record["status"] = "interrupted_not_proven"
        record["error"] = {"type": type(caught).__name__, "message": str(caught)}
        failed = True
    except Exception as caught:
        record["status"] = "failed_not_proven"
        record["error"] = {"type": type(caught).__name__, "message": str(caught)}
        failed = True
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        if process is not None:
            try:
                record["final_cleanup"] = stop_owned(process, graceful=True)
            except Exception as caught:
                record["final_cleanup_error"] = {"type": type(caught).__name__, "message": str(caught)}
                failed = True
        record["finished_at"] = utc_now()
        try:
            record["identity_after"] = capture_identity(root, python, BenchmarkEvidence)
            if record["identity_after"] != before:
                record["status"] = "failed_not_proven"
                failed = True
        except Exception as caught:
            record["post_run_identity_error"] = {"type": type(caught).__name__, "message": str(caught)}
            record["status"] = "failed_not_proven"
            failed = True
        atomic_json(checkpoint, record)
        if not args.skip_analysis:
            analyzer = root / "scripts/analyze_benchmark_categories.py"
            if not analyzer.is_file():
                # Allows reviewing both candidates together before promotion.
                analyzer = Path(__file__).with_name("analyze_benchmark_categories.py")
            record["analysis"] = {"command": [str(python), str(analyzer), "--input-dir", str(out)],
                                  "started_at": utc_now()}
            atomic_json(checkpoint, record)
            try:
                with (out / "analysis.log").open("x") as log:
                    result = subprocess.run(record["analysis"]["command"], cwd=root, stdout=log,
                                            stderr=subprocess.STDOUT, text=True, timeout=120)
                record["analysis"].update(exit_code=result.returncode, finished_at=utc_now())
                if result.returncode != 0:
                    failed = True
                    record["status"] = "failed_not_proven"
            except Exception as caught:
                record["analysis"]["error"] = {"type": type(caught).__name__, "message": str(caught)}
                record["status"] = "failed_not_proven"
                failed = True
            atomic_json(checkpoint, record)
        event({"event": "suite_finished", "status": record["status"], "output_directory": str(out)})
        events.close()
    return 130 if record["status"] == "interrupted_not_proven" else 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"benchmark preparation failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
