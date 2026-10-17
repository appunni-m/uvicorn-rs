#!/usr/bin/env python3
"""Validate parity and coverage evidence, replaying retained LLVM profiles offline.

Offline validation does not import or execute the server, parity clients, or
reference packages. Coverage validation invokes the exact recorded Rust/LLVM
toolchain to independently reconstruct each case's covered source regions.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from functools import lru_cache
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from coverage_contract import pending_coverage_mcp_request
from coverage_toolchain import ToolchainError, validate_coverage_tools


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests/parity/manifest.json"
UNIFIED_SCHEMA = "uvicorn-rs-coverage/unified@8"
PRODUCTION_SOURCE_SET = (
    "src/lib.rs",
    "crates/uvicorn-rs/src/lib.rs",
    "crates/uvicorn-rs/src/http3.rs",
    "crates/uvicorn-rs/src/http3/transport.rs",
    "crates/uvicorn-rs/src/websocket.rs",
    "crates/uvicorn-rs/src/peer_read.rs",
    "crates/native-app-contract/src/lib.rs",
)
EXECUTABLE_SOURCE_SET = PRODUCTION_SOURCE_SET[:-1]
NO_COUNTER_SOURCE_SET = (PRODUCTION_SOURCE_SET[-1],)
COVERAGE_SUPPORT_SOURCE_SET = (
    "crates/uvicorn-rs/src/coverage.rs",
    "crates/uvicorn-rs/src/http3/coverage.rs",
)
NATIVE_FAULT_CONTRACTS = {
    "http1.upgrade.receiver-closed": {
        "operation": "native-http1-upgrade-session",
        "scenario": "receiver-closed",
    },
    "http1.peer-read.receiver-closed": {
        "operation": "native-http1-peer-read-receiver-closed",
        "scenario": "receiver-closed",
    },
    "http1.peer-read.failure-after-data": {
        "operation": "native-http1-peer-read-error-response-cancel",
        "scenario": "failure-after-data",
    },
    "http1.response-body-activity.watch-outcomes": {
        "operation": "native-http1-peer-read-activity-watch-outcomes",
        "scenario": "watch-outcomes",
    },
    "connection-error.source-variants": {
        "operation": "native-connection-error-source-contract",
        "scenario": "source-variants",
    },
    "http3.request-body.trailers-pending-once": {
        "operation": "http3-request-trailers",
        "scenario": "trailers-pending",
    },
    "native.request-lifetime.body-missing-guard": {
        "operation": "native-request-lifetime-body-missing-guard",
        "scenario": "guard-missing",
    },
    "http3.peer-stop-observer.unavailable": {
        "operation": "http3-peer-stop-observer-unavailable",
        "scenario": "observer-unavailable",
    },
    "http3.peer-stop-observer.error": {
        "operation": "http3-peer-stop-observer-error",
        "scenario": "observer-error",
    },
    "http3.peer-stop-observer.local-retirement": {
        "operation": "http3-peer-stop-local-retirement",
        "scenario": "local-retirement",
    },
    "http3.client-adapter.read-closed-stream": {
        "operation": "native-http3-client-adapter-read-closed-stream",
        "scenario": "read-closed-stream",
    },
    "http3.client-adapter.write-closed-stream": {
        "operation": "native-http3-client-adapter-write-closed-stream",
        "scenario": "write-closed-stream",
    },
    "http3.response-send.frame-error": {
        "operation": "native-http3-response-send-failure",
        "scenario": "response-frame-send-failure",
    },
    "http3.response-finish.error": {
        "operation": "native-http3-response-send-failure",
        "scenario": "response-finish-failure",
    },
    "http3.response-fallback.start-error": {
        "operation": "native-http3-response-send-failure",
        "scenario": "response-fallback-start-failure",
    },
    "http3.response-fallback.finish-error": {
        "operation": "native-http3-response-send-failure",
        "scenario": "response-fallback-finish-failure",
    },
    "http3.transport.stream-id.out-of-range": {
        "operation": "native-http3-transport-adapter-edge-case",
        "scenario": "stream-id-out-of-range",
    },
    "http3.transport.send-data-pending": {
        "operation": "native-http3-transport-adapter-edge-case",
        "scenario": "send-data-before-ready",
    },
    "http3.transport.finish-after-reset": {
        "operation": "native-http3-transport-adapter-edge-case",
        "scenario": "finish-after-reset",
    },
    "websocket.accept-key.header-value-error": {
        "operation": "native-http1-websocket",
        "scenario": "accept-key-header-value-error",
    },
    "websocket.receive.close-reply.flush": {
        "operation": "native-http1-websocket",
        "scenario": "close-reply-flush-failure",
    },
    "websocket.receive.close-reply.cancel": {
        "operation": "native-http1-websocket",
        "scenario": "close-receive-cancellation",
    },
    "server.graceful-shutdown.deadline-overflow": {
        "operation": "native-server-graceful-deadline-overflow",
        "scenario": "deadline-overflow",
    },
    "server.listener.accept-error": {
        "operation": "native-server-listener-accept-error",
        "scenario": "accept-error",
    },
    "server.listener.admission-closed": {
        "operation": "native-server-listener-admission-closed",
        "scenario": "admission-closed",
    },
    "server.http3.admission-closed": {
        "operation": "native-server-http3-admission-closed",
        "scenario": "http3-admission-closed",
    },
}
PYTHON_SOURCE_SET = (
    "python/uvicorn_rs/__init__.py",
    "python/uvicorn_rs/__main__.py",
    "python/uvicorn_rs/_bridge.py",
    "python/uvicorn_rs/cli.py",
    "python/uvicorn_rs/server.py",
)


class EvidenceError(RuntimeError):
    """A retained report does not establish the required current gate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    def unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        fields = {}
        for name, item in pairs:
            require(name not in fields, f"duplicate JSON field in {path}: {name}")
            fields[name] = item
        return fields

    def reject_constant(value: str) -> None:
        raise EvidenceError(f"nonfinite JSON number in {path}: {value}")

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields,
                       parse_constant=reject_constant)
    require(isinstance(value, dict), f"expected a JSON object: {path}")
    return value


@lru_cache(maxsize=128)
def _literal_constants(path: str, modified: int, size: int) -> dict[str, Any]:
    del modified, size  # File state is part of the cache key.
    constants = {}
    for statement in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign):
            try:
                value = ast.literal_eval(statement.value)
            except (ValueError, TypeError):
                node = statement.value
                if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                        and node.value.id in constants):
                    try:
                        subscript = node.slice
                        if isinstance(subscript, ast.Slice):
                            lower = ast.literal_eval(subscript.lower) if subscript.lower is not None else None
                            upper = ast.literal_eval(subscript.upper) if subscript.upper is not None else None
                            step = ast.literal_eval(subscript.step) if subscript.step is not None else None
                            subscript = slice(lower, upper, step)
                        else:
                            subscript = ast.literal_eval(subscript)
                        value = constants[node.value.id][subscript]
                    except (ValueError, TypeError, KeyError, IndexError):
                        continue
                else:
                    continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value
    return constants


def source_constant(path: Path, name: str) -> Any:
    """Read literal contract constants without importing an executable runner."""
    state = path.stat()
    constants = _literal_constants(str(path), state.st_mtime_ns, state.st_size)
    require(name in constants, f"missing literal {name} in {path.relative_to(ROOT)}")
    return constants[name]


def exact_keys(value: Any, keys: set[str], label: str) -> None:
    require(isinstance(value, dict) and set(value) == keys, f"invalid {label} envelope")


def repo_path(relative: str) -> Path:
    require(isinstance(relative, str), "repository path must be a string")
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, f"unsafe repository path: {relative!r}")
    resolved = (ROOT / path).resolve()
    require(resolved.is_relative_to(ROOT), f"repository path escapes checkout: {relative!r}")
    return resolved


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=True, timeout=20,
    ).stdout.strip()


def valid_digest(value: Any, label: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"invalid SHA-256 identity: {label}")
    return value


def load_contract() -> tuple[dict[str, Any], list[dict[str, Any]], list[Path]]:
    manifest = read_json(MANIFEST_PATH)
    runner = ROOT / "scripts/run_parity.py"
    require(manifest.get("schema") == source_constant(runner, "MANIFEST_SCHEMA"), "unsupported manifest schema")
    require(manifest.get("result_schema") == source_constant(runner, "RESULT_SCHEMA"), "unsupported result schema")
    index = manifest.get("inputs")
    require(isinstance(index, list) and bool(index), "manifest has no indexed inputs")
    require(all(isinstance(item, str) for item in index) and len(index) == len(set(index)), "invalid input index")
    paths = []
    for item in index:
        require(item.startswith("inputs/"), f"input is outside the input directory: {item}")
        paths.append(repo_path("tests/parity/" + item))
    require(set(paths) == set((ROOT / "tests/parity/inputs").rglob("*.json")), "input index is incomplete or stale")
    cases = []
    input_schema = source_constant(runner, "INPUT_SCHEMA")
    operations = {operation["id"] for operation in manifest["operations"]}
    profiles = {profile["id"] for profile in manifest["profiles"]}
    for path in paths:
        document = read_json(path)
        require(document.get("schema") == input_schema, f"unsupported input schema: {path}")
        require(isinstance(document.get("cases"), list), f"input has no cases: {path}")
        for case in document["cases"]:
            require(isinstance(case, dict) and isinstance(case.get("case_id"), str), f"invalid case in {path}")
            require(case.get("profile") in profiles and case.get("operation") in operations,
                    f"unindexed case profile or operation: {case['case_id']}")
            require(case.get("verification", "oracle-parity") in {"oracle-parity", "fault-contract"},
                    f"invalid verification policy: {case['case_id']}")
            cases.append(case)
    ids = [case["case_id"] for case in cases]
    require(bool(ids) and len(ids) == len(set(ids)), "case index is empty or duplicated")
    return manifest, cases, paths


def require_summary(summary: dict[str, Any], count: int) -> None:
    expected = {"selected": count, "executed": count, "passed": count,
                "failed": 0, "infrastructure_failed": 0, "not_run": 0}
    require(isinstance(summary, dict) and all(type(value) is int for value in summary.values())
            and summary == expected, f"incomplete or failing result summary: {summary}")


def validate_case_metadata(row: dict[str, Any], case: dict[str, Any]) -> None:
    for field, source_field in (("profile", "profile"), ("operation", "operation"),
                                ("requirements", "covers"), ("fault", "fault")):
        require(row.get(field) == case.get(source_field), f"case contract differs: {case['case_id']} ({field})")
    require(row.get("verification") == case.get("verification", "oracle-parity"),
            f"case verification policy differs: {case['case_id']}")
    require(row.get("status") == "passed", f"case did not pass: {case['case_id']}")


def validate_observations(row: dict[str, Any], case: dict[str, Any], manifest: dict[str, Any]) -> None:
    exact_keys(row, {"case_id", "profile", "operation", "requirements", "verification", "fault", "status",
                     "oracle_observation", "target_observation", "server_exit_codes", "difference"},
               f"case {case['case_id']}")
    exact_keys(row["server_exit_codes"], {"oracle", "target"}, f"case {case['case_id']} server exits")
    operation = next(item for item in manifest["operations"] if item["id"] == case["operation"])
    target = row.get("target_observation")
    oracle = row.get("oracle_observation")
    require(isinstance(target, dict) and set(target) == set(operation["observe"]),
            f"target observation envelope differs: {case['case_id']}")
    require(row.get("difference") is None, f"passing case carries a difference: {case['case_id']}")
    if case.get("verification", "oracle-parity") == "oracle-parity":
        require(isinstance(oracle, dict), f"oracle observation is missing: {case['case_id']}")
        compare = operation.get("compare", operation["observe"])
        require(isinstance(compare, list) and bool(compare)
                and len(compare) == len(set(compare))
                and set(compare).issubset(operation["observe"]),
                f"invalid comparison fields: {case['case_id']}")
        require(all(target[field] == oracle[field] for field in compare),
                f"live observations differ on declared comparison fields: {case['case_id']}")
        for field, expected in operation.get("required_observations", {}).items():
            require(target.get(field) == expected, f"required observation differs: {case['case_id']} ({field})")
        for field, expected in operation.get("target_requirements", {}).items():
            require(target.get(field) == expected, f"target requirement differs: {case['case_id']} ({field})")
    else:
        require(oracle is None, f"target-only contract contains oracle observations: {case['case_id']}")


def validate_parity(
    result: dict[str, Any], *, expected_cases: list[dict[str, Any]] | None = None,
    expected_native_sha256: str | None = None, offline: bool = True,
    _current_revision: str | None = None, expected_coverage_profile_dir: Path | None = None,
) -> dict[str, Any]:
    """Check exact indexed cases; callers may bind evidence to a shipping native hash."""
    manifest, all_cases, input_paths = load_contract()
    if expected_cases is None:
        expected_cases = [case for case in all_cases if case.get("verification", "oracle-parity") == "oracle-parity"]
    expected = {case["case_id"]: case for case in expected_cases}
    require(len(expected) == len(expected_cases) and bool(expected), "expected parity case selection is empty or duplicated")
    exact_keys(result, {"schema", "status", "run", "summary", "cases", "infrastructure_errors"}, "parity report")
    require(result.get("schema") == manifest["result_schema"], "parity report uses a predecessor or unsupported schema")
    require(result.get("status") == "completed" and result.get("infrastructure_errors") == [], "parity did not complete cleanly")
    require_summary(result.get("summary"), len(expected))
    run = result["run"]
    exact_keys(run, {"run_id", "started_at", "finished_at", "manifest", "inputs", "environment", "target", "harness", "command"},
               "parity run")
    require(isinstance(run.get("run_id"), str) and bool(run["run_id"]), "parity run identity is empty")
    require(isinstance(run.get("command"), list) and bool(run["command"])
            and all(isinstance(part, str) for part in run["command"]), "parity command identity is invalid")
    if expected_coverage_profile_dir is not None:
        command = run["command"]
        expected_profile_dir = str(expected_coverage_profile_dir.resolve())
        require(any(command[index:index + 2] == ["--coverage-profile-dir", expected_profile_dir]
                    for index in range(len(command) - 1)),
                "parity result does not use its receipted coverage-profile directory")
    require(run["manifest"] == {"path": "tests/parity/manifest.json", "schema": manifest["schema"],
                                "sha256": sha256(MANIFEST_PATH)}, "parity manifest identity differs from checkout")
    input_schema = source_constant(ROOT / "scripts/run_parity.py", "INPUT_SCHEMA")
    require(run["inputs"] == [{"path": str(path.relative_to(ROOT)), "schema": input_schema, "sha256": sha256(path)}
                               for path in input_paths], "parity input identities differ from checkout")
    target = run["target"]
    exact_keys(target, {"source_sha256", "cargo_lock_sha256", "revision", "dirty", "native_extension"}, "parity target")
    exact_keys(target["native_extension"], {"path", "sha256"}, "parity native")
    require(target.get("source_sha256") == sha256(ROOT / "src/lib.rs"), "parity native source identity differs from checkout")
    require(target.get("cargo_lock_sha256") == sha256(ROOT / "Cargo.lock"), "parity Cargo.lock identity differs")
    require(target.get("revision") == (_current_revision or git_commit()), "parity commit differs from checkout")
    require(type(target.get("dirty")) is bool, "parity has no explicit source-state flag")
    harness = run["harness"]
    exact_keys(harness, {"runner", "runner_sha256", "fixture_app", "fixture_app_sha256", "http3_client"}, "parity harness")
    if harness["http3_client"] is not None:
        exact_keys(harness["http3_client"], {"path", "sha256"}, "HTTP/3 client")
        valid_digest(harness["http3_client"]["sha256"], "HTTP/3 client")
    require(harness.get("runner") == "scripts/run_parity.py" and
            harness.get("runner_sha256") == sha256(ROOT / "scripts/run_parity.py"), "parity runner identity differs")
    require(harness.get("fixture_app") == "tests/parity/app.py" and
            harness.get("fixture_app_sha256") == sha256(ROOT / "tests/parity/app.py"), "parity application identity differs")
    exact_keys(run["environment"], {"python", "platform", "machine", "rustc", "dependencies"}, "parity environment")
    dependencies = run["environment"]["dependencies"]
    require(isinstance(dependencies, dict), "parity dependency identity is invalid")
    for oracle in manifest["oracles"]:
        for distribution, version in [(oracle["id"], oracle["version"]),
                                      *((item["id"], item["version"]) for item in oracle["components"])]:
            require(dependencies.get(distribution) == version, f"parity reference version differs: {distribution}")
    native_sha = valid_digest(target["native_extension"].get("sha256"), "parity native")
    if expected_native_sha256 is not None:
        require(native_sha == expected_native_sha256, "parity did not execute the expected shipping native")
    if not offline:
        imported = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
        require(native_sha == sha256(imported), "parity did not execute the currently imported native")
        recorded = Path(target["native_extension"]["path"])
        require((recorded if recorded.is_absolute() else ROOT / recorded).resolve() == imported,
                "parity native import path differs from current environment")
    rows = result.get("cases")
    require(isinstance(rows, list), "parity has no case rows")
    ids = [row.get("case_id") for row in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected), "parity omitted, added, or duplicated indexed cases")
    for row in rows:
        case = expected[row["case_id"]]
        validate_case_metadata(row, case)
        validate_observations(row, case, manifest)
    return {"status": "passed", "cases": len(expected), "source_sha256": target["source_sha256"],
            "native_sha256": native_sha, "commit": target["revision"], "recorded_dirty": target["dirty"],
            "scope": "retained current evidence; this check does not publish or establish a clean release"}


def llvm_source_name(path: Path) -> str | None:
    """Map only a path inside this checkout to a declared production source."""
    if not path.is_absolute() or ".." in path.parts:
        return None
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None
    return relative if relative in PRODUCTION_SOURCE_SET else None


def llvm_production_regions(
    report: dict[str, Any], source_digest: str,
    *, canonical_functions: dict[tuple[str, int, int], str] | None = None,
    require_normalized_summaries: bool = True,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, int]],
    dict[tuple[str, int, int], str],
]:
    """Reconstruct source-span regions and validate normalized file summaries."""
    data = report.get("data")
    require(isinstance(data, list) and len(data) == 1, "LLVM export must contain one unified measurement")
    files, functions = data[0].get("files"), data[0].get("functions")
    require(isinstance(files, list) and isinstance(functions, list), "LLVM measurement lacks files/functions")
    source_names: dict[str, str | None] = {}

    def source_name(filename: str) -> str | None:
        # Every region refers back to a filename in this immutable export.
        # Resolve each distinct path once, rather than repeating filesystem
        # lookups for every region of every function instantiation.
        if filename not in source_names:
            source_names[filename] = llvm_source_name(Path(filename))
        return source_names[filename]

    selected: dict[str, dict[str, Any]] = {}
    for item in files:
        require(isinstance(item, dict) and isinstance(item.get("filename"), str), "invalid LLVM file row")
        relative = source_name(item["filename"])
        if relative is not None:
            require(relative not in selected, f"LLVM export duplicates {relative}")
            selected[relative] = item
    require(set(EXECUTABLE_SOURCE_SET) <= set(selected), "LLVM export omits an executable production source")

    summaries = {}
    for relative in PRODUCTION_SOURCE_SET:
        item = selected.get(relative)
        if item is None:
            summaries[relative] = {"regions": 0, "lines": 0, "regions_total": 0, "lines_total": 0}
            continue
        summary = item.get("summary")
        require(isinstance(summary, dict), f"LLVM summary missing for {relative}")
        values = {}
        for metric in ("regions", "lines"):
            row = summary.get(metric)
            require(isinstance(row, dict) and type(row.get("covered")) is int
                    and type(row.get("count")) is int and 0 <= row["covered"] <= row["count"],
                    f"invalid LLVM {metric} summary for {relative}")
            values[metric] = row["covered"]
            values[f"{metric}_total"] = row["count"]
        summaries[relative] = values
    for relative in NO_COUNTER_SOURCE_SET:
        require(not any(summaries[relative].values()), f"no-counter file has LLVM counters: {relative}")

    groups: dict[tuple[str, int, int], list[tuple[str, list[list[int]]]]] = {}
    for function in functions:
        require(isinstance(function, dict) and isinstance(function.get("name"), str)
                and isinstance(function.get("filenames"), list) and isinstance(function.get("regions"), list),
                "invalid LLVM function row")
        filenames = function["filenames"]
        require(all(isinstance(filename, str) for filename in filenames), "invalid LLVM function filenames")
        relative_filenames = [source_name(filename) for filename in filenames]
        by_file: dict[str, list[list[int]]] = {}
        for raw in function["regions"]:
            require(isinstance(raw, list) and len(raw) == 8 and all(type(value) is int for value in raw),
                    "invalid raw LLVM region")
            file_index = raw[5]
            require(0 <= file_index < len(filenames), "invalid LLVM region file index")
            relative = relative_filenames[file_index]
            if relative is not None:
                by_file.setdefault(relative, []).append(raw)
        for relative, raw_regions in by_file.items():
            code_regions = [raw for raw in raw_regions if raw[7] == 0]
            if not code_regions:
                continue
            first_region = raw_regions[0]
            group_key = (relative, first_region[0], first_region[1])
            groups.setdefault(group_key, []).append((function["name"], code_regions))

    require(bool(groups), "LLVM export has no executable production function regions")
    if canonical_functions is not None:
        require(set(groups) == set(canonical_functions), "case LLVM function groups differ from aggregate")
    regions: dict[str, dict[str, Any]] = {}
    reconstructed = {relative: {"regions": 0, "regions_total": 0} for relative in selected}
    selected_functions: dict[tuple[str, int, int], str] = {}
    for group_key, instantiations in groups.items():
        relative, group_line, group_column = group_key
        symbols = [symbol for symbol, _ in instantiations]
        require(len(symbols) == len(set(symbols)), f"duplicate LLVM function symbol in group: {group_key}")
        totals = {symbol: len(code_regions) for symbol, code_regions in instantiations}
        covered = {
            symbol: sum(raw[4] > 0 for raw in code_regions)
            for symbol, code_regions in instantiations
        }
        if canonical_functions is None:
            max_total = max(totals.values())
            max_covered = max(covered.values())
            candidates = [
                symbol for symbol in symbols
                if totals[symbol] == max_total and covered[symbol] == max_covered
            ]
            require(bool(candidates), f"LLVM region maxima have no common instantiation: {group_key}")
            symbol = min(candidates)
            reconstructed[relative]["regions"] += max_covered
            reconstructed[relative]["regions_total"] += max_total
        else:
            if group_key not in canonical_functions:
                require(not any(covered.values()),
                        f"case profile hit an LLVM function group absent from aggregate: {group_key}")
                continue
            symbol = canonical_functions[group_key]
            require(symbol in totals,
                    f"case profile is missing aggregate-selected function representative: {group_key}")
        selected_functions[group_key] = symbol
        selected_regions = next(raws for candidate, raws in instantiations if candidate == symbol)
        representative_spans = {
            (raw[0], raw[1], raw[2], raw[3], raw[7]) for raw in selected_regions
        }
        covered_source_spans: set[tuple[int, int, int, int, int]] = set()
        for _, candidate_regions in instantiations:
            candidate_spans = {
                (raw[0], raw[1], raw[2], raw[3], raw[7]) for raw in candidate_regions
            }
            require(candidate_spans <= representative_spans,
                    f"LLVM instantiation has source regions outside its representative: {group_key}")
            covered_source_spans.update(
                (raw[0], raw[1], raw[2], raw[3], raw[7])
                for raw in candidate_regions if raw[4] > 0
            )
        for raw in selected_regions:
            start_line, start_col, end_line, end_col, _, _, _, kind = raw
            source_span = (start_line, start_col, end_line, end_col, kind)
            identity = [source_digest, relative, group_line, group_column, symbol,
                        start_line, start_col, end_line, end_col, kind]
            region_id = digest_json(identity)
            require(region_id not in regions, f"duplicate LLVM function-instantiation region: {region_id}")
            regions[region_id] = {
                "file": relative,
                "function_group": {"line": group_line, "column": group_column},
                "start": {"line": start_line, "column": start_col},
                "end": {"line": end_line, "column": end_col},
                "covered": source_span in covered_source_spans,
                "function_symbols": {symbol},
            }
    for relative in EXECUTABLE_SOURCE_SET:
        file_regions = [region for region in regions.values() if region["file"] == relative]
        source_summary = {
            "regions": sum(region["covered"] for region in file_regions),
            "regions_total": len(file_regions),
        }
        if canonical_functions is None:
            if require_normalized_summaries:
                require(summaries[relative]["regions"] == source_summary["regions"]
                        and summaries[relative]["regions_total"] == source_summary["regions_total"],
                        f"normalized source-span region summary differs for {relative}")
            else:
                # A fresh llvm-cov export carries LLVM's maximum-instantiation
                # file summary. Normalize its region totals to the same
                # source-span union used by the embedded report before the
                # replay comparison. Physical lines are validated from the
                # aggregate LCOV export in the unified runner.
                summaries[relative]["regions"] = source_summary["regions"]
                summaries[relative]["regions_total"] = source_summary["regions_total"]
            require(reconstructed[relative]["regions_total"] == source_summary["regions_total"]
                    and reconstructed[relative]["regions"] <= source_summary["regions"],
                    f"raw LLVM instantiation counters disagree with normalized source spans for {relative}")
    require(bool(regions), "LLVM export has no executable production regions")
    return regions, summaries, selected_functions


def resolve_llvm_tools(expected: dict[str, Any]) -> tuple[Path, Path]:
    try:
        return validate_coverage_tools(expected)
    except ToolchainError as error:
        raise EvidenceError(str(error)) from error


def export_llvm_profile(
    profile_data: Path, *, label: str, llvm_cov: Path, binaries: tuple[Path, Path],
) -> dict[str, Any]:
    command = [
        str(llvm_cov), "export", "--format=text", "--check-binary-ids",
        f"--instr-profile={profile_data}", "--ignore-filename-regex=.*/\\.cargo/registry/.*",
        *(f"--object={binary}" for binary in binaries),
    ]
    exported = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=180, check=False,
    )
    require(exported.returncode == 0 and not exported.stderr.strip(),
            f"cannot export LLVM profile for {label}: {(exported.stderr or exported.stdout)[-3000:]}")
    try:
        llvm_report = json.loads(exported.stdout)
    except json.JSONDecodeError as error:
        raise EvidenceError(f"invalid LLVM export for {label}: {error}") from error
    require(isinstance(llvm_report, dict) and llvm_report.get("type") == "llvm.coverage.json.export",
            f"unsupported LLVM profile export for {label}")
    return llvm_report


def case_profile_regions(
    profile_paths: list[Path], *, label: str, llvm_cov: Path, llvm_profdata: Path,
    binaries: tuple[Path, Path], source_digest: str,
    canonical_functions: dict[tuple[str, int, int], str],
    aggregate_region_ids: set[str],
) -> set[str]:
    """Re-export one retained case profile and independently derive its hit set."""
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-case-coverage-") as directory:
        merged = Path(directory) / "case.profdata"
        merge = subprocess.run(
            [str(llvm_profdata), "merge", "-sparse", "-failure-mode=all", "-o", str(merged),
             *map(str, profile_paths)],
            cwd=ROOT, capture_output=True, text=True, timeout=180, check=False,
        )
        require(merge.returncode == 0 and merged.is_file() and merged.stat().st_size > 0,
                f"cannot merge retained LLVM profiles for {label}: {(merge.stderr or merge.stdout)[-3000:]}")
        llvm_report = export_llvm_profile(merged, label=label, llvm_cov=llvm_cov, binaries=binaries)
        regions, _, _ = llvm_production_regions(
            llvm_report, source_digest, canonical_functions=canonical_functions,
            require_normalized_summaries=False,
        )
        require(set(regions) == aggregate_region_ids,
                f"case LLVM region identity differs from aggregate for {label}")
        return {region_id for region_id, region in regions.items() if region["covered"]}


def expected_source_hashes(coverage_runner: Path, input_paths: list[Path]) -> dict[str, str]:
    require(tuple(source_constant(coverage_runner, "PRODUCTION_SOURCE_SET")) == PRODUCTION_SOURCE_SET
            and tuple(source_constant(coverage_runner, "EXECUTABLE_SOURCE_SET")) == EXECUTABLE_SOURCE_SET
            and tuple(source_constant(coverage_runner, "NO_COUNTER_SOURCE_SET")) == NO_COUNTER_SOURCE_SET
            and tuple(source_constant(coverage_runner, "COVERAGE_SUPPORT_SOURCE_SET")) == COVERAGE_SUPPORT_SOURCE_SET
            and tuple(source_constant(coverage_runner, "PYTHON_SOURCE_SET")) == PYTHON_SOURCE_SET,
            "coverage runner production-source classification differs from validator contract")
    selected: dict[str, str] = {}
    for relative in source_constant(coverage_runner, "SOURCE_PATHS"):
        path = repo_path(relative)
        if path.is_dir():
            selected.update({str(item.relative_to(ROOT)): sha256(item) for item in sorted(path.rglob("*.rs"))})
        else:
            require(path.is_file(), f"missing declared source input: {relative}")
            selected[relative] = sha256(path)
    discovered = {
        str(item.relative_to(ROOT))
        for directory in (ROOT / "src", ROOT / "crates/uvicorn-rs/src", ROOT / "crates/native-app-contract/src")
        for item in directory.rglob("*.rs")
    }
    require(discovered == set(PRODUCTION_SOURCE_SET) | set(COVERAGE_SUPPORT_SOURCE_SET),
            "Rust source inventory is incomplete or unclassified")
    python_sources = {
        str(item.relative_to(ROOT)) for item in (ROOT / "python/uvicorn_rs").rglob("*.py")
    }
    require(python_sources == set(PYTHON_SOURCE_SET), "Python adapter source inventory is incomplete or unclassified")
    selected.update({relative: sha256(repo_path(relative)) for relative in PYTHON_SOURCE_SET})
    for relative in source_constant(coverage_runner, "REPORT_INPUT_PATHS"):
        selected[relative] = sha256(repo_path(relative))
    selected.update({str(path.relative_to(ROOT)): sha256(path) for path in input_paths})
    require(set(PRODUCTION_SOURCE_SET) <= set(selected), "source hash receipt omits production files")
    return selected


def case_slug(case_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_id).strip(".-")
    return f"{safe[:96]}-{hashlib.sha256(case_id.encode()).hexdigest()[:10]}"


def aggregate_source_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        metric: {
            "covered": sum(row["summary"][metric] for row in rows if row["classification"] == "executable"),
            "total": sum(row["summary"][f"{metric}_total"] for row in rows if row["classification"] == "executable"),
            "missing": sum(row["summary"][f"{metric}_total"] - row["summary"][metric]
                           for row in rows if row["classification"] == "executable"),
        }
        for metric in ("regions", "lines")
    }


def source_lines_for_region(region: dict[str, Any]) -> set[int]:
    start = region["start"]
    end = region["end"]
    start_line, start_column = int(start["line"]), int(start["column"])
    end_line, end_column = int(end["line"]), int(end["column"])
    require(start_line >= 1 and end_line >= start_line and start_column >= 1 and end_column >= 1,
            f"invalid executable source span: {region!r}")
    require((start_line != end_line or end_column > start_column),
            f"empty executable source span: {region!r}")
    last_line = end_line if end_column > 1 else end_line - 1
    return set(range(start_line, last_line + 1))


def validate_coverage(
    report: dict[str, Any], report_path: Path, *, allow_pending_mcp: bool = False,
) -> dict[str, Any]:
    manifest, asgi_cases, input_paths = load_contract()
    native_manifest_path = ROOT / "tests/native-core/manifest.json"
    native_manifest = read_json(native_manifest_path)
    native_cases = native_manifest.get("cases")
    require(isinstance(native_cases, list) and bool(native_cases), "native manifest has no cases")
    native_ids = [case.get("id") for case in native_cases if isinstance(case, dict)]
    require(len(native_ids) == len(native_cases) and all(isinstance(item, str) and item.strip() for item in native_ids)
            and len(native_ids) == len(set(native_ids)), "invalid native case index")
    for case in native_cases:
        verification = case.get("verification", "target-contract")
        fault = case.get("fault")
        require(verification in {"target-contract", "fault-contract"},
                f"invalid native verification mode: {case['id']}")
        if verification == "fault-contract":
            require(isinstance(fault, dict) and set(fault) == {"point"}
                    and isinstance(fault.get("point"), str)
                    and fault.get("point") in NATIVE_FAULT_CONTRACTS
                    and case.get("operation") == NATIVE_FAULT_CONTRACTS[fault["point"]]["operation"]
                    and case.get("scenario") == NATIVE_FAULT_CONTRACTS[fault["point"]]["scenario"],
                    f"invalid native fault contract: {case['id']}")
        else:
            require(fault is None, f"native target contract cannot declare a fault: {case['id']}")

    ext = report.get("uvicorn_rs_unified")
    require(report.get("type") == "llvm.coverage.json.export" and isinstance(ext, dict)
            and ext.get("schema") == UNIFIED_SCHEMA, "unsupported unified coverage report")
    exact_keys(ext, {"schema", "status", "run", "matrix", "coverage", "artifacts"}, "unified coverage")
    require(ext["status"] == "complete", "coverage report is incomplete")
    run = ext["run"]
    exact_keys(run, {"run_id", "started_at", "finished_at", "source", "build", "runner", "artifacts_root"},
               "coverage run")
    source = run["source"]
    exact_keys(source, {"revision", "dirty", "file_sha256", "sha256", "manifest_sha256", "manifest_schema",
                        "input_manifest_order", "native_manifest_sha256", "native_manifest_schema",
                        "native_manifest_case_order"}, "coverage source")
    coverage_runner = ROOT / "scripts/run_unified_coverage.py"
    expected_files = expected_source_hashes(coverage_runner, input_paths)
    recorded_files = source.get("file_sha256")
    require(isinstance(recorded_files, dict)
            and source.get("sha256") == digest_json(recorded_files),
            "coverage source identity digest is invalid")
    # This validator runs after measurement and is not an input to the ASGI or
    # native cases. Keep its recorded hash in the immutable receipt, but do not
    # invalidate captured test evidence when the validator itself is repaired.
    validator_path = str(Path(__file__).resolve().relative_to(ROOT))
    recorded_measurement_files = {
        path: digest for path, digest in recorded_files.items() if path != validator_path
    }
    expected_files.pop(validator_path, None)
    require(recorded_measurement_files == expected_files,
            "coverage source/harness/input hashes differ from checkout")
    require(source.get("revision") == git_commit() and type(source.get("dirty")) is bool,
            "coverage revision/source-state differs")
    require(source.get("manifest_sha256") == sha256(MANIFEST_PATH)
            and source.get("manifest_schema") == manifest["schema"]
            and source.get("input_manifest_order") == [str(path.relative_to(ROOT)) for path in input_paths]
            and source.get("native_manifest_sha256") == sha256(native_manifest_path)
            and source.get("native_manifest_schema") == native_manifest["schema_version"]
            and source.get("native_manifest_case_order") == native_ids,
            "coverage manifest identity differs")
    require(run["runner"] == {"path": "scripts/run_unified_coverage.py", "sha256": sha256(coverage_runner)},
            "coverage runner identity differs")

    build = run["build"]
    exact_keys(build, {"native_extension", "native_extension_sha256", "native_runner", "native_runner_sha256",
                       "native_runner_profile", "cargo_lock_sha256", "tools", "machine", "platform", "python"},
               "coverage build")
    native_sha = valid_digest(build.get("native_extension_sha256"), "native extension")
    valid_digest(build.get("native_runner_sha256"), "native runner")
    require(isinstance(build.get("native_extension"), str) and not Path(build["native_extension"]).is_absolute()
            and ".." not in Path(build["native_extension"]).parts, "invalid extension build path")
    require(build.get("native_runner") in {
        "target/asgi-native-coverage/release/examples/native_core_contracts",
        "target/asgi-native-coverage/release/examples/native_core_contracts.exe",
    }, "native runner build path differs")
    require(build.get("native_runner_profile") == "cargo-llvm-cov release profile with workspace crate instrumentation",
            "native runner coverage profile differs")
    tools = build.get("tools")
    cargo_llvm_cov = tools.get("cargo_llvm_cov") if isinstance(tools, dict) else None
    require(build.get("cargo_lock_sha256") == sha256(ROOT / "Cargo.lock")
            and isinstance(cargo_llvm_cov, dict)
            and cargo_llvm_cov.get("version") == "cargo-llvm-cov 0.8.7",
            "coverage build inputs/tool version differ")
    require(all(isinstance(build.get(key), str) and build[key] for key in ("machine", "platform", "python")),
            "coverage environment identity is incomplete")
    llvm_cov, llvm_profdata = resolve_llvm_tools(build.get("tools"))
    extension = repo_path(build["native_extension"])
    native_runner = repo_path(build["native_runner"])
    require(extension.is_file() and sha256(extension) == native_sha
            and native_runner.is_file() and sha256(native_runner) == build["native_runner_sha256"],
            "coverage binaries are missing or differ from the recorded build")
    coverage_binaries = (extension, native_runner)

    matrix = ext["matrix"]
    exact_keys(matrix, {"scope", "manifest_case_count", "asgi_manifest_case_count", "native_manifest_case_count",
                        "selected", "asgi_selected", "native_selected", "executed", "passed", "failed",
                        "infrastructure_failed", "transient_infrastructure_failures", "oracle_parity",
                        "fault_contracts", "verification_runs", "native_verification_runs",
                        "verification_runs_required", "case_attribution_complete", "case_results",
                        "native_case_results"}, "coverage matrix")
    ac, nc = len(asgi_cases), len(native_cases)
    total = ac + nc
    require(matrix.get("scope") == "complete" and matrix.get("manifest_case_count") == total
            and matrix.get("asgi_manifest_case_count") == ac and matrix.get("native_manifest_case_count") == nc
            and matrix.get("selected") == total and matrix.get("asgi_selected") == ac
            and matrix.get("native_selected") == nc and matrix.get("executed") == total
            and matrix.get("passed") == total and matrix.get("failed") == 0
            and matrix.get("infrastructure_failed") == 0 and matrix.get("transient_infrastructure_failures") == 0
            and matrix.get("case_attribution_complete") is True, "coverage matrix is incomplete or contains retries")
    for key, policy in (("oracle_parity", "oracle-parity"), ("fault_contracts", "fault-contract")):
        count = sum(case.get("verification", "oracle-parity") == policy for case in asgi_cases)
        if policy == "fault-contract":
            count += sum(case.get("verification", "target-contract") == policy for case in native_cases)
        require(matrix.get(key) == {"selected": count, "passed": count, "failed": 0},
                f"{key} case denominator differs")

    coverage = ext["coverage"]
    exact_keys(coverage, {"gate", "source_set", "executable_source_set", "coverage_support_source_set",
                         "source_files", "llvm_normalization", "line_validation", "summary", "llvm_summary",
                         "regions", "uncovered_regions", "attribution", "coverage_mcp"}, "coverage")
    require(tuple(coverage.get("source_set", [])) == PRODUCTION_SOURCE_SET
            and tuple(coverage.get("executable_source_set", [])) == EXECUTABLE_SOURCE_SET
            and tuple(coverage.get("coverage_support_source_set", [])) == COVERAGE_SUPPORT_SOURCE_SET,
            "coverage source inventory differs from the declared production sources")
    source_rows = coverage.get("source_files")
    require(isinstance(source_rows, list) and len(source_rows) == len(PRODUCTION_SOURCE_SET),
            "per-file source summaries are incomplete")
    require(coverage.get("llvm_normalization") == {
        "regions": "source-span union across Rust function instantiations",
        "lines": "physical source-line union from LLVM LCOV DA records, validated against executable region spans",
        "function_counters": "raw LLVM instantiation counters retained",
    }, "LLVM source-summary normalization policy differs")
    line_validation = coverage.get("line_validation")
    require(isinstance(line_validation, dict), "physical-line validation evidence is missing")
    exact_keys(line_validation, {"source", "span_coordinates", "physical_line_sets_match",
                                 "covered_line_sets_match", "source_files"}, "line validation")
    require(line_validation.get("source") == "llvm-cov export --format=lcov DA records"
            and line_validation.get("span_coordinates") == "one-based LLVM source columns with an exclusive end coordinate"
            and line_validation.get("physical_line_sets_match") is True
            and line_validation.get("covered_line_sets_match") is True,
            "physical-line validation method or result differs")
    raw_regions, raw_summaries, canonical_functions = llvm_production_regions(report, source["sha256"])
    expected_line_evidence: dict[str, dict[str, int]] = {}
    for path, row in zip(PRODUCTION_SOURCE_SET, source_rows, strict=True):
        exact_keys(row, {"path", "classification", "summary", "llvm_summary"}, f"source summary {path}")
        classification = "no-executable-counters" if path in NO_COUNTER_SOURCE_SET else "executable"
        require(row.get("path") == path and row.get("classification") == classification,
                f"source classification differs: {path}")
        exact_keys(row.get("summary"), {"regions", "lines", "regions_total", "lines_total"}, f"summary {path}")
        require(row["summary"] == raw_summaries[path], f"per-file normalized summary differs: {path}")
        exact_keys(row.get("llvm_summary"), {"regions", "lines", "regions_total", "lines_total"},
                   f"raw LLVM summary {path}")
        if path in NO_COUNTER_SOURCE_SET:
            require(not any(row["llvm_summary"].values()), f"no-counter file has raw LLVM counters: {path}")
            continue
        path_regions = [region for region in raw_regions.values() if region["file"] == path]
        span_lines: set[int] = set()
        hit_lines: set[int] = set()
        for region in path_regions:
            lines = source_lines_for_region(region)
            span_lines.update(lines)
            if region["covered"]:
                hit_lines.update(lines)
        require(row["summary"]["lines_total"] == len(span_lines)
                and row["summary"]["lines"] == len(hit_lines),
                f"normalized physical-line summary differs from unique region spans: {path}")
        expected_line_evidence[path] = {
            "lcov_lines": len(span_lines),
            "region_span_lines": len(span_lines),
            "lcov_covered_lines": len(hit_lines),
            "covered_region_span_lines": len(hit_lines),
        }
    require(line_validation.get("source_files") == expected_line_evidence,
            "physical-line evidence differs from independently reconstructed source spans")
    normalized_source_summary = aggregate_source_summary(source_rows)
    raw_llvm_summary = aggregate_source_summary([
        {**row, "summary": row["llvm_summary"]} for row in source_rows
    ])
    require(coverage.get("llvm_summary") == raw_llvm_summary,
            "raw LLVM summary differs from retained per-file LLVM summaries")
    data = report["data"][0]
    for metric in ("regions", "lines"):
        total_row = data.get("totals", {}).get(metric)
        expected = normalized_source_summary[metric]
        require(isinstance(total_row, dict)
                and total_row.get("count") == expected["total"]
                and total_row.get("covered") == expected["covered"]
                and total_row.get("notcovered") == expected["missing"],
                f"standard LLVM aggregate {metric} totals differ from unified summary")
    source_region_hits = sum(region["covered"] for region in raw_regions.values())
    expected_summary = {
        "regions": {
            "covered": source_region_hits,
            "total": len(raw_regions),
            "missing": len(raw_regions) - source_region_hits,
        },
        "lines": normalized_source_summary["lines"],
    }
    require(coverage.get("summary") == expected_summary,
            "source-span union summary differs from independently reconstructed regions")
    for metric, row in expected_summary.items():
        require(row["total"] > 0 and row["covered"] == row["total"] and row["missing"] == 0,
                f"unified source {metric} coverage is below 100%")
    require(coverage.get("gate") == "passed" and coverage.get("uncovered_regions") == [],
            "coverage gate or uncovered region list differs")

    context = read_json(report_path.with_name(report_path.name + ".context.json"))
    require(context == {
        "report_sha256": sha256(report_path),
        "source_hashes": {path: source["file_sha256"][path] for path in PRODUCTION_SOURCE_SET},
        "build_id": digest_json(build), "scope": "full", "test_status": "passed",
        "recorded_revision": source["revision"],
    }, "context receipt does not hash all production source files")

    producer_report = Path(coverage["coverage_mcp"].get("measurement_path", ""))
    require(not producer_report.is_absolute() and ".." not in producer_report.parts
            and str(report_path.relative_to(ROOT)) == str(producer_report), "invalid Coverage-MCP report path")
    root = Path(run["artifacts_root"])
    require(not root.is_absolute() and ".." not in root.parts and root.is_relative_to(producer_report.parent),
            "invalid run artifact root")
    local_root = (report_path.parent / root.relative_to(producer_report.parent)).resolve()
    require(local_root.is_relative_to(report_path.parent.resolve()), "artifact root escapes report directory")

    def artifact(relative: str, digest: str | None = None, *, inside_run: bool = True) -> Path:
        original = Path(relative)
        require(not original.is_absolute() and ".." not in original.parts, "unsafe artifact path")
        repo_path(relative)  # Validate that the normalized artifact remains within this checkout.
        if inside_run:
            require(original.is_relative_to(root), f"artifact is outside its run: {relative}")
        try:
            suffix = original.relative_to(producer_report.parent)
        except ValueError as error:
            raise EvidenceError("artifact escapes producer report directory") from error
        result = (report_path.parent / suffix).resolve()
        require(result.is_relative_to(report_path.parent.resolve()) and result.is_file(),
                f"missing retained artifact: {relative}")
        if inside_run:
            require(result.is_relative_to(local_root), f"artifact escapes run root: {relative}")
        if digest is not None:
            require(sha256(result) == valid_digest(digest, relative), f"artifact hash differs: {relative}")
        return result

    def exact_run_artifact(relative: Any, expected: Path, label: str) -> Path:
        require(isinstance(relative, str) and Path(relative) == expected,
                f"{label} is outside its exact run directory")
        return artifact(relative)

    artifacts = ext["artifacts"]
    exact_keys(artifacts, {"aggregate_profile_data", "per_case_profiles_root", "native_per_case_profiles_root",
                          "native_input_manifests_root", "matrix_runs_root", "native_matrix_runs_root"}, "artifacts")
    expected_artifact_paths = {
        "aggregate_profile_data": root / "per-case-union.profdata",
        "per_case_profiles_root": root / "profiles",
        "native_per_case_profiles_root": root / "native-profiles",
        "native_input_manifests_root": root / "native-inputs",
        "matrix_runs_root": root / "matrix-runs",
        "native_matrix_runs_root": root / "native-matrix-runs",
    }
    require({key: Path(value) for key, value in artifacts.items()} == expected_artifact_paths,
            "retained artifact roots differ from run layout")

    aggregate_profile = artifact(
        artifacts["aggregate_profile_data"],
        valid_digest(coverage["attribution"].get("aggregate_profile_data_sha256"), "aggregate LLVM profile"),
    )
    require(aggregate_profile.stat().st_size > 0, "aggregate profile union is empty")
    replayed_llvm = export_llvm_profile(
        aggregate_profile, label="aggregate", llvm_cov=llvm_cov, binaries=coverage_binaries,
    )
    replayed_regions, replayed_summaries, replayed_functions = llvm_production_regions(
        replayed_llvm, source["sha256"], require_normalized_summaries=False,
    )
    replayed_region_summaries = {
        path: {key: summary[key] for key in ("regions", "regions_total")}
        for path, summary in replayed_summaries.items()
    }
    embedded_region_summaries = {
        path: {key: summary[key] for key in ("regions", "regions_total")}
        for path, summary in raw_summaries.items()
    }
    require(replayed_regions == raw_regions
            and replayed_region_summaries == embedded_region_summaries
            and replayed_functions == canonical_functions,
            "embedded aggregate LLVM export differs from retained aggregate profile")

    asgi_by_id = {case["case_id"]: case for case in asgi_cases}
    native_by_id = {case["id"]: case for case in native_cases}
    asgi_rows, native_rows = matrix["case_results"], matrix["native_case_results"]
    require(isinstance(asgi_rows, list) and isinstance(native_rows, list)
            and {row.get("case_id") for row in asgi_rows} == set(asgi_by_id)
            and {row.get("case_id") for row in native_rows} == set(native_by_id)
            and len(asgi_rows) == ac and len(native_rows) == nc,
            "case result rows differ from input manifests")
    all_keys = {f"asgi:{item}" for item in asgi_by_id} | {f"native:{item}" for item in native_by_id}
    attribution = coverage["attribution"]
    exact_keys(attribution, {"algorithm", "aggregate_profile_data_sha256", "per_case_profiles",
                             "profile_union_matches_attribution", "case_region_ids_verified",
                             "case_region_lookup", "case_index"}, "coverage attribution")
    case_index = attribution.get("case_index")
    require(attribution.get("per_case_profiles") == total
            and attribution.get("profile_union_matches_attribution") is True
            and attribution.get("case_region_ids_verified") is True
            and isinstance(case_index, list)
            and case_index == sorted(all_keys)
            and len(case_index) == len(set(case_index))
            and attribution.get("algorithm") == (
                "LLVM instantiation groups use a deterministic maximum-summary representative for the denominator; "
                "hits are unioned by exact source span across monomorphizations; region IDs include source hash, "
                "file, group start, representative function symbol, source span, and kind"
            )
            and attribution.get("case_region_lookup") == (
                "coverage.regions[].hit_by -> coverage.attribution.case_index"
            ),
            "coverage attribution receipt is incomplete")

    hit_counts: Counter[str] = Counter()
    case_regions: dict[str, set[str]] = {key: set() for key in all_keys}
    region_ids = set()
    for region in coverage["regions"]:
        exact_keys(region, {"id", "file", "function_group", "start", "end", "kind",
                            "function_symbols", "covered", "hit_by"},
                   "region attribution")
        path = region.get("file")
        require(path in EXECUTABLE_SOURCE_SET and region.get("covered") is True,
                "region is uncovered or outside executable source set")
        exact_keys(region.get("function_group"), {"line", "column"}, "region function group")
        exact_keys(region.get("start"), {"line", "column"}, "region start")
        exact_keys(region.get("end"), {"line", "column"}, "region end")
        symbols = region.get("function_symbols")
        require(isinstance(symbols, list) and len(symbols) == 1 and isinstance(symbols[0], str),
                "region must identify exactly one LLVM representative function")
        identity = [source["sha256"], path, region["function_group"]["line"],
                    region["function_group"]["column"], symbols[0], region["start"]["line"],
                    region["start"]["column"], region["end"]["line"], region["end"]["column"], region["kind"]]
        rid = region.get("id")
        require(rid == digest_json(identity) and rid not in region_ids, "invalid or duplicate region identity")
        region_ids.add(rid)
        raw = raw_regions.get(rid)
        require(raw is not None and raw["file"] == path and raw["covered"]
                and raw["function_group"] == region["function_group"],
                "coverage region is missing or uncovered in LLVM export")
        require(set(symbols) == raw["function_symbols"],
                "region function symbols differ from LLVM")
        hit_indexes = region.get("hit_by")
        require(isinstance(hit_indexes, list) and bool(hit_indexes)
                and all(type(item) is int and 0 <= item < len(case_index) for item in hit_indexes)
                and hit_indexes == sorted(set(hit_indexes)),
                "region attribution is missing or has invalid case indexes")
        hits = [case_index[index] for index in hit_indexes]
        require(set(hits) <= all_keys, "region attribution references an unselected case")
        hit_counts.update(hits)
        for key in hits:
            case_regions[key].add(rid)
    require(region_ids == set(raw_regions), "attribution rows changed the LLVM denominator")

    seen_runs: set[str] = set()
    seen_profiles: set[Path] = set()

    def check_profiles(
        paths: Any, receipts: Any, label: str, *, expected_parent: Path,
    ) -> list[Path]:
        require(isinstance(paths, list) and bool(paths) and isinstance(receipts, list)
                and len(receipts) == len(paths), f"{label} has no complete profile receipts")
        checked: list[Path] = []
        for relative, receipt in zip(paths, receipts, strict=True):
            exact_keys(receipt, {"path", "sha256"}, f"{label} profile receipt")
            require(receipt.get("path") == relative, f"{label} profile path receipt differs")
            path = artifact(relative, valid_digest(receipt.get("sha256"), f"{label} profile"))
            relative_path = Path(relative)
            require(relative_path.parent == expected_parent
                    and path.parent == (ROOT / expected_parent).resolve(),
                    f"{label} profile path is outside its case/attempt directory")
            require(path.suffix == ".profraw" and path.stat().st_size > 0 and path not in seen_profiles,
                    f"{label} contains an empty or reused profile")
            seen_profiles.add(path)
            checked.append(path)
        return checked

    for row in asgi_rows:
        cid = row["case_id"]
        case = asgi_by_id[cid]
        require(row.get("case_key") == f"asgi:{cid}", f"ASGI case key is not namespaced: {cid}")
        validate_case_metadata(row, case)
        require(row.get("error") is None and row.get("transient_infrastructure_failures") == 0
                and row.get("target_extension_sha256") == native_sha
                and type(row.get("covered_regions")) is int
                and row["covered_regions"] == hit_counts[f"asgi:{cid}"] == len(case_regions[f"asgi:{cid}"]) > 0,
                f"ASGI case receipt differs: {cid}")
        attempts = row.get("attempts")
        require(isinstance(attempts, list) and len(attempts) == 1 and attempts[0].get("attempt") == 1
                and attempts[0].get("status") == "passed" and attempts[0].get("runner_exit_code") == 0,
                f"ASGI case retried or failed: {cid}")
        attempt = attempts[0]
        require(all(attempt.get(key) == row.get(key)
                    for key in ("result_artifact", "result_sha256", "profile_data_artifacts",
                                "profile_data_receipts", "stdout_artifact", "stderr_artifact")),
                f"ASGI case artifact receipts differ: {cid}")
        case_result_dir = root / "cases" / case_slug(cid)
        exact_run_artifact(row.get("result_artifact"), case_result_dir / "parity-result.json",
                           f"ASGI case result {cid}")
        exact_run_artifact(row.get("stdout_artifact"), case_result_dir / "stdout.log",
                           f"ASGI case stdout {cid}")
        exact_run_artifact(row.get("stderr_artifact"), case_result_dir / "stderr.log",
                           f"ASGI case stderr {cid}")
        exact_run_artifact(attempt.get("stdout_artifact"), case_result_dir / "stdout.log",
                           f"ASGI case attempt stdout {cid}")
        exact_run_artifact(attempt.get("stderr_artifact"), case_result_dir / "stderr.log",
                           f"ASGI case attempt stderr {cid}")
        retained = read_json(artifact(row["result_artifact"], row["result_sha256"]))
        expected_profile_dir = root / "profiles" / case_slug(cid) / "attempt-1"
        validate_parity(retained, expected_cases=[case], expected_native_sha256=native_sha,
                        _current_revision=source["revision"],
                        expected_coverage_profile_dir=ROOT / expected_profile_dir)
        rid = row.get("run_id")
        require(isinstance(rid, str) and rid == retained["run"]["run_id"] and rid not in seen_runs,
                f"ASGI case run identity differs or repeats: {cid}")
        seen_runs.add(rid)
        observed = retained["cases"][0]
        require(row.get("observations") == {"oracle": observed["oracle_observation"],
                                             "target": observed["target_observation"],
                                             "difference": observed["difference"]},
                f"ASGI observations differ: {cid}")
        profiles = check_profiles(
            row.get("profile_data_artifacts"), row.get("profile_data_receipts"), f"ASGI case {cid}",
            expected_parent=root / "profiles" / case_slug(cid) / "attempt-1" / "target",
        )
        require(artifact(str(Path(row["result_artifact"]).parent / "target.profdata")).stat().st_size > 0,
                f"ASGI merged profile missing: {cid}")
        verified_hits = case_profile_regions(
            profiles, label=f"asgi:{cid}", llvm_cov=llvm_cov, llvm_profdata=llvm_profdata,
            binaries=coverage_binaries, source_digest=source["sha256"],
            canonical_functions=canonical_functions, aggregate_region_ids=region_ids,
        )
        require(verified_hits == case_regions[f"asgi:{cid}"],
                f"ASGI case-to-region attribution differs from retained profile: {cid}")

    input_root = Path(artifacts["native_input_manifests_root"])
    for cid, case in native_by_id.items():
        one_case = read_json(artifact(str(input_root / f"{case_slug(cid)}.json")))
        expected_one = dict(native_manifest)
        expected_one["cases"] = [case]
        require(one_case == expected_one, f"native per-case input differs: {cid}")

    for row in native_rows:
        cid = row["case_id"]
        case = native_by_id[cid]
        key = f"native:{cid}"
        verification = case.get("verification", "target-contract")
        fault = case.get("fault")
        fault_consumed = verification == "fault-contract"
        require(row.get("case_key") == key and row.get("operation") == case.get("operation")
                and row.get("protocol") == case.get("protocol") and row.get("status") == "passed"
                and row.get("verification") == verification and row.get("fault") == fault
                and row.get("fault_consumed") is fault_consumed
                and row.get("error") is None and row.get("runner_exit_code") == 0
                and row.get("expected_pass_ids") == [cid] and row.get("observed_pass_ids") == [cid]
                and row.get("transient_infrastructure_failures") == 0
                and type(row.get("covered_regions")) is int
                and row["covered_regions"] == hit_counts[key] == len(case_regions[key]) > 0,
                f"native case receipt differs: {cid}")
        native_result = read_json(artifact(row["result_artifact"], row["result_sha256"]))
        require(native_result == {
            "schema": "uvicorn-rs-native-case-result/3", "case_id": cid, "case_key": key,
            "verification": verification, "fault": fault, "fault_consumed": fault_consumed,
            "status": "passed", "runner_exit_code": 0, "expected_pass_ids": [cid],
            "observed_pass_ids": [cid], "profile_data_artifacts": row["profile_data_artifacts"],
            "profile_data_receipts": row["profile_data_receipts"],
        }, f"native result artifact differs: {cid}")
        attempts = row.get("attempts")
        require(isinstance(attempts, list) and len(attempts) == 1 and attempts[0] == {
            "attempt": 1, "status": "passed", "verification": verification,
            "fault": fault, "fault_consumed": fault_consumed, "runner_exit_code": 0,
            "result_artifact": row["result_artifact"], "result_sha256": row["result_sha256"],
            "stdout_artifact": row["stdout_artifact"], "stderr_artifact": row["stderr_artifact"],
            "profile_data_artifacts": row["profile_data_artifacts"],
            "profile_data_receipts": row["profile_data_receipts"],
        }, f"native case attempt differs: {cid}")
        native_case_dir = root / "native-cases" / case_slug(cid)
        exact_run_artifact(row.get("result_artifact"), native_case_dir / "native-result.json",
                           f"native case result {cid}")
        exact_run_artifact(row.get("stdout_artifact"), native_case_dir / "stdout.log",
                           f"native case stdout {cid}")
        exact_run_artifact(row.get("stderr_artifact"), native_case_dir / "stderr.log",
                           f"native case stderr {cid}")
        stdout = artifact(row["stdout_artifact"]).read_text(encoding="utf-8")
        artifact(row["stderr_artifact"])
        if verification == "fault-contract":
            require(f"FAULT_CONSUMED {fault['point']}" in stdout.splitlines(),
                    f"native fault point was not observed as consumed: {cid}")
        require([line.removeprefix("PASS ") for line in stdout.splitlines() if line.startswith("PASS ")] == [cid],
                f"native case stdout does not prove its pass: {cid}")
        profiles = check_profiles(
            row.get("profile_data_artifacts"), row.get("profile_data_receipts"), f"native case {cid}",
            expected_parent=root / "native-profiles" / case_slug(cid),
        )
        merged = artifact(row["merged_profile_artifact"])
        require(merged == artifact(str(Path(row["result_artifact"]).parent / "target.profdata"))
                and merged.stat().st_size > 0, f"native merged profile missing: {cid}")
        verified_hits = case_profile_regions(
            profiles, label=key, llvm_cov=llvm_cov, llvm_profdata=llvm_profdata,
            binaries=coverage_binaries, source_digest=source["sha256"],
            canonical_functions=canonical_functions, aggregate_region_ids=region_ids,
        )
        require(verified_hits == case_regions[key],
                f"native case-to-region attribution differs from retained profile: {cid}")

    asgi_repeats, native_repeats = matrix.get("verification_runs"), matrix.get("native_verification_runs")
    require(matrix.get("verification_runs_required") == 3 and isinstance(asgi_repeats, list)
            and len(asgi_repeats) == 3 and isinstance(native_repeats, list) and len(native_repeats) == 3,
            "both ASGI and native matrices require exactly three complete repeats")
    for index, repeat in enumerate(asgi_repeats, 1):
        require(repeat.get("run") == index and repeat.get("status") == "completed"
                and repeat.get("runner_exit_code") == 0 and repeat.get("transient_infrastructure_failures") == 0,
                f"ASGI repeat failed or out of order: {index}")
        require_summary(repeat.get("summary"), ac)
        attempts = repeat.get("attempts")
        require(isinstance(attempts, list) and len(attempts) == 1 and attempts[0].get("attempt") == 1
                and attempts[0].get("runner_exit_code") == 0
                and all(attempts[0].get(key) == repeat.get(key)
                        for key in ("artifact", "sha256", "run_id", "summary", "status",
                                    "profile_data_artifacts", "profile_data_receipts",
                                    "stdout_artifact", "stderr_artifact")),
                f"ASGI repeat attempt differs: {index}")
        repeat_dir = root / "matrix-runs" / f"run-{index}"
        exact_run_artifact(repeat.get("artifact"), repeat_dir / "parity-result.json",
                           f"ASGI repeat result {index}")
        exact_run_artifact(repeat.get("stdout_artifact"), repeat_dir / "stdout.log",
                           f"ASGI repeat stdout {index}")
        exact_run_artifact(repeat.get("stderr_artifact"), repeat_dir / "stderr.log",
                           f"ASGI repeat stderr {index}")
        check_profiles(
            repeat.get("profile_data_artifacts"), repeat.get("profile_data_receipts"),
            f"ASGI repeat {index}", expected_parent=root / "matrix-runs" / f"run-{index}",
        )
        retained = read_json(artifact(repeat["artifact"], repeat["sha256"]))
        validate_parity(retained, expected_cases=asgi_cases, expected_native_sha256=native_sha,
                        _current_revision=source["revision"])
        rid = repeat.get("run_id")
        require(isinstance(rid, str) and rid == retained["run"]["run_id"] and rid not in seen_runs,
                f"ASGI repeat identity differs or repeats: {index}")
        seen_runs.add(rid)

    expected_native_fault_points = [
        case["fault"]["point"] for case in native_cases
        if case.get("verification", "target-contract") == "fault-contract"
    ]
    for index, repeat in enumerate(native_repeats, 1):
        observed_ids = repeat.get("observed_pass_ids")
        observed_fault_points = repeat.get("observed_fault_points")
        require(isinstance(observed_ids, list) and all(isinstance(cid, str) for cid in observed_ids)
                and sorted(observed_ids) == sorted(native_ids),
                f"native repeat case inventory differs: {index}")
        require(isinstance(observed_fault_points, list)
                and all(isinstance(point, str) for point in observed_fault_points)
                and sorted(observed_fault_points) == sorted(expected_native_fault_points),
                f"native repeat fault inventory differs: {index}")
        require(repeat.get("schema") == "uvicorn-rs-native-matrix-result/3" and repeat.get("run") == index
                and repeat.get("status") == "completed" and repeat.get("runner_exit_code") == 0
                and repeat.get("selected") == nc and repeat.get("passed") == nc
                and repeat.get("failed") == 0 and repeat.get("not_run") == 0
                and repeat.get("expected_case_ids") == native_ids
                and repeat.get("expected_fault_points") == expected_native_fault_points
                and repeat.get("transient_infrastructure_failures") == 0,
                f"native repeat failed or expected inventory differs: {index}")
        attempts = repeat.get("attempts")
        require(isinstance(attempts, list) and len(attempts) == 1 and attempts[0].get("attempt") == 1
                and attempts[0].get("status") == "completed" and attempts[0].get("runner_exit_code") == 0
                and attempts[0].get("artifact") == repeat.get("artifact")
                and attempts[0].get("sha256") == repeat.get("sha256")
                and attempts[0].get("stdout_artifact") == repeat.get("stdout_artifact")
                and attempts[0].get("stderr_artifact") == repeat.get("stderr_artifact")
                and attempts[0].get("profile_data_artifacts") == repeat.get("profile_data_artifacts")
                and attempts[0].get("profile_data_receipts") == repeat.get("profile_data_receipts"),
                f"native repeat attempt differs: {index}")
        stored = read_json(artifact(repeat["artifact"], repeat["sha256"]))
        result_fields = ("schema", "run", "status", "runner_exit_code", "selected", "passed", "failed", "not_run",
                         "expected_case_ids", "observed_pass_ids", "expected_fault_points", "observed_fault_points",
                         "stdout_artifact", "stderr_artifact",
                         "profile_data_artifacts", "profile_data_receipts")
        require(stored == {field: repeat[field] for field in result_fields},
                f"native repeat result artifact differs: {index}")
        repeat_dir = root / "native-matrix-runs" / f"run-{index}"
        exact_run_artifact(repeat.get("artifact"), repeat_dir / "native-result.json",
                           f"native repeat result {index}")
        exact_run_artifact(repeat.get("stdout_artifact"), repeat_dir / "stdout.log",
                           f"native repeat stdout {index}")
        exact_run_artifact(repeat.get("stderr_artifact"), repeat_dir / "stderr.log",
                           f"native repeat stderr {index}")
        stdout = artifact(repeat["stdout_artifact"]).read_text(encoding="utf-8")
        artifact(repeat["stderr_artifact"])
        require([line.removeprefix("PASS ") for line in stdout.splitlines() if line.startswith("PASS ")] == observed_ids,
                f"native repeat stdout differs from observed receipt order: {index}")
        require([line.removeprefix("FAULT_CONSUMED ") for line in stdout.splitlines()
                 if line.startswith("FAULT_CONSUMED ")] == observed_fault_points,
                f"native repeat fault consumption differs from observed receipt order: {index}")
        check_profiles(
            repeat.get("profile_data_artifacts"), repeat.get("profile_data_receipts"),
            f"native repeat {index}", expected_parent=root / "native-matrix-runs" / f"run-{index}",
        )

    mcp_receipt = coverage["coverage_mcp"]
    mcp_pending = mcp_receipt.get("status") == "awaiting_query"
    if allow_pending_mcp and mcp_pending:
        exact_keys(mcp_receipt, {"status", "measurement_path", "metric", "required_follow_up"},
                   "pending Coverage-MCP request")
        require(mcp_receipt == pending_coverage_mcp_request(str(report_path.relative_to(ROOT))),
                "pending Coverage-MCP request differs from the producer contract")
    else:
        validate_coverage_mcp(
            mcp_receipt, report_path=report_path, report_relative=str(report_path.relative_to(ROOT)),
            build=build, source=source, summary=expected_summary, artifact=artifact,
        )
    return {
        "status": "passed", "asgi_cases": ac, "native_cases": nc,
        "full_repeats": {"asgi": len(asgi_repeats), "native": len(native_repeats)},
        "coverage": expected_summary, "source_sha256": source["sha256"], "native_sha256": native_sha,
        "recorded_dirty": source["dirty"],
        "scope": "complete unified Rust production-source regions and lines",
        "mcp_status": mcp_receipt["status"],
    }


def validate_coverage_mcp(
    receipt: dict[str, Any], *, report_path: Path, report_relative: str, build: dict[str, Any],
    source: dict[str, Any], summary: dict[str, dict[str, int]], artifact: Any,
) -> None:
    exact_keys(receipt, {"status", "gate", "group_semantics", "measurement_path", "metric", "source", "recorded_revision", "build_id",
                         "tests", "coverage", "line_coverage", "group_count", "groups", "line_group_count",
                         "line_groups", "location_samples_are_bounded", "pages", "line_pages", "receipt_artifact",
                         "receipt_sha256"},
               "Coverage-MCP receipt")
    build_id = digest_json(build)
    require(receipt.get("status") == "measured" and receipt.get("gate") == "passed"
            and receipt.get("group_semantics") == (
                "per-function-instantiation observations; source-span totals are the coverage gate"
            )
            and receipt.get("measurement_path") == report_relative and receipt.get("metric") == "regions"
            and receipt.get("source") == "matches_receipt" and receipt.get("tests") == "passed"
            and receipt.get("recorded_revision") == source["revision"] and receipt.get("build_id") == build_id
            and type(receipt.get("group_count")) is int and receipt["group_count"] >= 0
            and isinstance(receipt.get("groups"), list)
            and len(receipt["groups"]) == receipt["group_count"]
            and type(receipt.get("line_group_count")) is int and receipt["line_group_count"] >= 0
            and isinstance(receipt.get("line_groups"), list)
            and len(receipt["line_groups"]) == receipt["line_group_count"]
            and receipt.get("location_samples_are_bounded") is True,
            "Coverage-MCP does not bind complete source coverage to this test receipt")
    region_total = summary["regions"] | {"metric": "regions"}
    line_total = summary["lines"] | {"metric": "lines"}
    require(receipt.get("coverage") == region_total and receipt.get("line_coverage") == line_total,
            "Coverage-MCP totals differ from unified report")
    require(type(receipt.get("pages")) is int and receipt["pages"] > 0
            and type(receipt.get("line_pages")) is int and receipt["line_pages"] > 0,
            "Coverage-MCP region/line pages are missing")
    receipt_sha = valid_digest(receipt.get("receipt_sha256"), "Coverage-MCP page receipt")
    pages_path = artifact(receipt["receipt_artifact"], receipt_sha, inside_run=False)
    pages = json.loads(pages_path.read_text(encoding="utf-8"))
    require(isinstance(pages, list) and bool(pages), "retained MCP pages are not a non-empty array")
    by_metric: dict[str, list[dict[str, Any]]] = {"regions": [], "lines": []}
    common = None
    for index, page in enumerate(pages):
        require(isinstance(page, dict) and set(page) == {"request", "response"},
                f"invalid MCP page receipt {index}")
        request = page["request"]
        require(isinstance(request, dict) and set(request) == {
            "measurement", "metric", "offset", "limit", "query", "line"
        }, f"invalid MCP request receipt {index}")
        require(request.get("measurement") == report_relative
                and type(request.get("offset")) is int and request["offset"] >= 0
                and type(request.get("limit")) is int and request["limit"] > 0
                and request.get("query") is None and request.get("line") is None,
                f"invalid MCP request scope {index}")
        response = page["response"]
        require(isinstance(response, dict) and isinstance(response.get("data"), dict),
                f"invalid MCP response {index}")
        data = response["data"]
        require(data.get("status") == "measured"
                and type(data.get("group_count")) is int and data["group_count"] >= 0
                and isinstance(data.get("groups"), list),
                f"MCP page {index} is incomplete or has invalid grouped diagnostics")
        measurement = data.get("measurement")
        require(isinstance(measurement, dict) and isinstance(measurement.get("coverage"), dict),
                f"MCP page {index} lacks a measurement")
        metric = measurement["coverage"].get("metric")
        require(metric in by_metric and request.get("metric") == metric,
                f"MCP page {index} has an unsupported metric")
        expected = region_total if metric == "regions" else line_total
        require(measurement["coverage"] == expected and measurement.get("ref") == report_relative
                and measurement.get("source") == "matches_receipt" and measurement.get("tests") == "passed"
                and measurement.get("recorded_revision") == source["revision"]
                and measurement.get("build_id") == build_id,
                f"MCP {metric} page {index} differs from report receipt")
        identity = {key: value for key, value in measurement.items() if key != "coverage"}
        if common is None:
            common = identity
        else:
            require(identity == common, "MCP pages refer to different measurements")
        by_metric[metric].append(page)
    require(len(by_metric["regions"]) == receipt["pages"] and len(by_metric["lines"]) == receipt["line_pages"]
            and by_metric["regions"] and by_metric["lines"], "MCP receipt omits region or line pages")
    for metric, metric_pages in by_metric.items():
        expected_offset = 0
        expected_limit = metric_pages[0]["request"]["limit"]
        observed_group_rows = 0
        total_groups: int | None = None
        for index, page in enumerate(metric_pages):
            request, data = page["request"], page["response"]["data"]
            require(request.get("metric") == metric and request.get("offset") == expected_offset
                    and request.get("limit") == expected_limit,
                    f"MCP {metric} cursor chain or page size is inconsistent at page {index}")
            group_count = data.get("group_count")
            require(type(group_count) is int and group_count >= 0
                    and (total_groups is None or group_count == total_groups),
                    f"MCP {metric} group total differs across pages")
            total_groups = group_count
            groups = data.get("groups")
            require(isinstance(groups, list), f"MCP {metric} page {index} has invalid groups")
            for group in groups:
                require(isinstance(group, dict) and isinstance(group.get("path"), str)
                        and "function" in group
                        and (isinstance(group.get("function"), str)
                             or (metric == "lines" and group.get("function") is None))
                        and type(group.get("count")) is int and group["count"] >= 0
                        and isinstance(group.get("locations"), list),
                        f"MCP {metric} page {index} has an invalid group row")
                observed_group_rows += 1
            next_offset = data.get("next_offset")
            require(next_offset is None or (type(next_offset) is int and next_offset > expected_offset),
                    f"MCP {metric} page {index} has an invalid next offset")
            require((next_offset is None) == (index == len(metric_pages) - 1),
                    f"MCP {metric} page order continues after terminal or stops before next page")
            if next_offset is not None:
                expected_offset = next_offset
        require(total_groups == observed_group_rows,
                f"MCP {metric} page row count differs from its reported group total")
    require(report_path.is_file(), "coverage report disappeared during MCP receipt validation")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("parity", "coverage"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--offline", action="store_true", help="validate retained evidence without importing the installed native")
    parser.add_argument("--require-clean", action="store_true", help="require evidence produced from a clean source checkout")
    parser.add_argument(
        "--allow-pending-mcp",
        action="store_true",
        help=("CI-only mode: validate the complete raw LLVM and matrix evidence while Coverage-MCP is pending; "
              "the default evidence gate still requires an attached zero-gap MCP receipt"),
    )
    args = parser.parse_args()
    if args.kind != "coverage" and args.allow_pending_mcp:
        parser.error("--allow-pending-mcp is valid only for coverage reports")
    path = args.report.resolve()
    result = read_json(path)
    checked = (
        validate_parity(result, offline=args.offline)
        if args.kind == "parity"
        else validate_coverage(result, path, allow_pending_mcp=args.allow_pending_mcp)
    )
    if args.kind == "coverage" and not args.offline:
        imported = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
        require(checked["native_sha256"] == sha256(imported),
                "coverage did not execute the currently imported instrumented native")
    if args.require_clean:
        require(checked["recorded_dirty"] is False, "release evidence was produced from a dirty source checkout")
    print(json.dumps({"kind": args.kind, "report": str(path), **checked}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        print(f"CI evidence rejected: {error}", file=sys.stderr)
        raise SystemExit(1)
