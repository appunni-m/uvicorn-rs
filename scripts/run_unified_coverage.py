#!/usr/bin/env python3
"""Run live adapter and native-contract cases with one LLVM attribution report."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any
import uuid

from coverage_contract import pending_coverage_mcp_request
from coverage_toolchain import ToolchainError, capture_coverage_tools

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SOURCE = ROOT / "python"
PYTHON_SOURCE_TEXT = str(PYTHON_SOURCE)
_existing_pythonpath = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = os.pathsep.join(
    path for path in (PYTHON_SOURCE_TEXT, _existing_pythonpath) if path
)
if PYTHON_SOURCE_TEXT in sys.path:
    sys.path.remove(PYTHON_SOURCE_TEXT)
sys.path.insert(0, PYTHON_SOURCE_TEXT)

run_parity = importlib.import_module("run_parity")


RUNNER = ROOT / "scripts" / "run_parity.py"
BUILD_SCRIPT = ROOT / "scripts" / "build_coverage_extension.py"
RESULT_SCHEMA = "uvicorn-rs-coverage/unified@8"
LLVM_EXTENSION_KEY = "uvicorn_rs_unified"
SOURCE_PATHS = (
    "src",
    "crates/uvicorn-rs/src",
    "crates/native-app-contract/src",
    "Cargo.toml",
    "Cargo.lock",
    "crates/uvicorn-rs/Cargo.toml",
    "crates/native-app-contract/Cargo.toml",
)
PRODUCTION_SOURCE_SET = (
    "src/lib.rs",
    "crates/uvicorn-rs/src/lib.rs",
    "crates/uvicorn-rs/src/http3.rs",
    "crates/uvicorn-rs/src/http3/transport.rs",
    "crates/uvicorn-rs/src/websocket.rs",
    "crates/uvicorn-rs/src/peer_read.rs",
    "crates/native-app-contract/src/lib.rs",
)
# Sources compiled only to drive coverage contracts, not production code.
COVERAGE_SUPPORT_SOURCE_SET = (
    "crates/uvicorn-rs/src/coverage.rs",
    "crates/uvicorn-rs/src/http3/coverage.rs",
)
EXECUTABLE_SOURCE_SET = PRODUCTION_SOURCE_SET[:-1]
NO_COUNTER_SOURCE_SET = ("crates/native-app-contract/src/lib.rs",)
PYTHON_SOURCE_SET = (
    "python/uvicorn_rs/__init__.py",
    "python/uvicorn_rs/__main__.py",
    "python/uvicorn_rs/_bridge.py",
    "python/uvicorn_rs/cli.py",
    "python/uvicorn_rs/server.py",
)
NATIVE_MANIFEST = ROOT / "tests" / "native-core" / "manifest.json"
NATIVE_RUNNER = ROOT / "target" / "asgi-native-coverage" / "release" / "examples" / "native_core_contracts"
NATIVE_FAULT_CONTRACTS = {
    "native.request-lifetime.body-missing-guard": {
        "operation": "native-request-lifetime-body-missing-guard",
        "scenario": "guard-missing",
    },
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
    "http3.peer-stop-observer.unavailable": {
        "operation": "http3-peer-stop-observer-unavailable",
        "scenario": "observer-unavailable",
    },
    "http3.request-body.trailers-pending-once": {
        "operation": "http3-request-trailers",
        "scenario": "trailers-pending",
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
REPORT_INPUT_PATHS = (
    "tests/parity/manifest.json",
    "tests/parity/app.py",
    "tests/parity/startup_probe.py",
    "tests/parity/server_api_probe.py",
    "tests/native-core/manifest.json",
    "crates/uvicorn-rs/examples/native_core_contracts.rs",
    "tests/native-core/tls/localhost-cert.pem",
    "tests/native-core/tls/localhost-key.pem",
    "tools/http3-probe/Cargo.toml",
    "tools/http3-probe/Cargo.lock",
    "tools/http3-probe/src/bin/parity-http3.rs",
    "scripts/run_parity.py",
    "scripts/build_coverage_extension.py",
    "scripts/coverage_toolchain.py",
    "scripts/check_ci_evidence.py",
    "scripts/attach_coverage_mcp.py",
    "scripts/coverage_contract.py",
    "scripts/run_unified_coverage.py",
    "pyproject.toml",
    "uv.lock",
)


class CoverageError(RuntimeError):
    """Coverage evidence is missing, inconsistent, or incompatible."""


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def restore_native_runner(native_runner: Path, snapshot: Path, expected_sha256: str) -> None:
    """Restore the instrumented LLVM object if its Cargo target was cleaned."""
    if native_runner.is_file() and digest_file(native_runner) == expected_sha256:
        return
    native_runner.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot, native_runner)
    if digest_file(native_runner) != expected_sha256:
        raise CoverageError("restored native coverage runner differs from the recorded build")


def profile_receipts(paths: list[Path]) -> list[dict[str, str]]:
    """Bind each retained raw LLVM profile to its report row."""
    return [
        {"path": str(path.relative_to(ROOT)), "sha256": digest_file(path)}
        for path in paths
    ]


def digest_json(value: Any) -> str:
    return digest_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run_checked(command: list[str], *, timeout: int = 300, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout)[-6000:]
        raise CoverageError(f"command failed ({result.returncode}): {command!r}\n{detail}")
    return result.stdout


def load_native_contract() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = json.loads(NATIVE_MANIFEST.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise CoverageError("unsupported native-core manifest version")
    protocols = document.get("protocols")
    cases = document.get("cases")
    if not isinstance(protocols, list) or not isinstance(cases, list) or not cases:
        raise CoverageError("native-core manifest requires protocols and cases")
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or any(not isinstance(case_id, str) for case_id in case_ids):
        raise CoverageError("native-core manifest has an invalid case ID")
    if len(case_ids) != len(set(case_ids)):
        raise CoverageError("native-core manifest contains duplicate case IDs")
    for case in cases:
        covers = case.get("covers")
        if covers is not None and (
            not isinstance(covers, list)
            or not covers
            or any(not isinstance(requirement, str) or not requirement for requirement in covers)
            or len(covers) != len(set(covers))
        ):
            raise CoverageError(f"native-core case {case['id']} has invalid requirement coverage")
        verification = case.get("verification", "target-contract")
        fault = case.get("fault")
        if verification not in {"target-contract", "fault-contract"}:
            raise CoverageError(f"native-core case {case['id']} has invalid verification mode")
        if verification == "fault-contract":
            if (
                not isinstance(fault, dict)
                or set(fault) != {"point"}
                or not isinstance(fault.get("point"), str)
                or fault.get("point") not in NATIVE_FAULT_CONTRACTS
                or case.get("operation") != NATIVE_FAULT_CONTRACTS[fault["point"]]["operation"]
                or case.get("scenario") != NATIVE_FAULT_CONTRACTS[fault["point"]]["scenario"]
            ):
                raise CoverageError(f"native-core case {case['id']} has an invalid fault contract")
        elif fault is not None:
            raise CoverageError(f"native-core target contract {case['id']} cannot declare a fault point")
    return document, cases


def source_identity(
    manifest: dict[str, Any], input_paths: list[Path], native_manifest: dict[str, Any]
) -> dict[str, Any]:
    discovered_sources = {
        str(source.relative_to(ROOT))
        for directory in (ROOT / "src", ROOT / "crates" / "uvicorn-rs" / "src", ROOT / "crates" / "native-app-contract" / "src")
        for source in directory.rglob("*.rs")
    }
    expected_rust_sources = set(PRODUCTION_SOURCE_SET) | set(COVERAGE_SUPPORT_SOURCE_SET)
    if discovered_sources != expected_rust_sources:
        raise CoverageError(
            "Rust source inventory changed: "
            f"expected={sorted(expected_rust_sources)}, discovered={sorted(discovered_sources)}"
        )
    discovered_python_sources = {
        str(source.relative_to(ROOT)) for source in (ROOT / "python" / "uvicorn_rs").rglob("*.py")
    }
    if discovered_python_sources != set(PYTHON_SOURCE_SET):
        raise CoverageError(
            "Python adapter source inventory changed: "
            f"expected={sorted(PYTHON_SOURCE_SET)}, discovered={sorted(discovered_python_sources)}"
        )
    selected: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        if path.is_dir():
            for source in sorted(path.rglob("*.rs")):
                selected[str(source.relative_to(ROOT))] = digest_file(source)
        elif path.is_file():
            selected[relative] = digest_file(path)
    for relative in PYTHON_SOURCE_SET:
        selected[relative] = digest_file(ROOT / relative)
    for relative in REPORT_INPUT_PATHS:
        path = ROOT / relative
        selected[relative] = digest_file(path)
    for path in input_paths:
        selected[str(path.relative_to(ROOT))] = digest_file(path)
    return {
        "revision": run_checked(["git", "rev-parse", "HEAD"]).strip(),
        "dirty": bool(run_checked(["git", "status", "--porcelain"]).strip()),
        "file_sha256": selected,
        "sha256": digest_json(selected),
        "manifest_sha256": digest_file(run_parity.MANIFEST_PATH),
        "manifest_schema": manifest["schema"],
        "input_manifest_order": [str(path.relative_to(ROOT)) for path in input_paths],
        "native_manifest_sha256": digest_file(NATIVE_MANIFEST),
        "native_manifest_schema": native_manifest["schema_version"],
        "native_manifest_case_order": [case["id"] for case in native_manifest["cases"]],
    }


def llvm_tools() -> tuple[Path, Path, dict[str, dict[str, str]]]:
    try:
        receipts, paths = capture_coverage_tools()
    except ToolchainError as error:
        raise CoverageError(str(error)) from error
    return paths["llvm_cov"], paths["llvm_profdata"], receipts


def case_slug(case_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_id).strip(".-")
    return f"{safe[:96]}-{hashlib.sha256(case_id.encode()).hexdigest()[:10]}"


def case_key(family: str, case_id: str) -> str:
    return f"{family}:{case_id}"


def native_pass_ids(output: str) -> list[str]:
    return [line.removeprefix("PASS ") for line in output.splitlines() if line.startswith("PASS ")]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def llvm_export(
    llvm_cov: Path,
    binaries: list[Path],
    profile_data: Path,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    ignored_dependencies = r".*/\.cargo/registry/.*"
    command = [
        str(llvm_cov),
        "export",
        "--format=text",
        "--check-binary-ids",
        f"--instr-profile={profile_data}",
        f"--ignore-filename-regex={ignored_dependencies}",
    ]
    for binary in binaries:
        command.append(f"--object={binary}")
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout)[-6000:]
        raise CoverageError(f"command failed ({result.returncode}): {command!r}\n{detail}")
    if result.stderr.strip():
        raise CoverageError(f"llvm-cov export emitted diagnostics:\n{result.stderr[-6000:]}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CoverageError(f"llvm-cov export returned invalid JSON: {error}") from error
    if report.get("type") != "llvm.coverage.json.export" or not report.get("data"):
        raise CoverageError("llvm-cov export returned an unsupported report")
    return report


def llvm_export_lcov(
    llvm_cov: Path,
    binaries: list[Path],
    profile_data: Path,
    allowed_sources: set[str],
    *,
    timeout: int = 120,
) -> dict[str, dict[int, int]]:
    """Return LLVM's per-physical-line counts for the declared source files."""
    ignored_dependencies = r".*/\.cargo/registry/.*"
    command = [
        str(llvm_cov),
        "export",
        "--format=lcov",
        "--check-binary-ids",
        f"--instr-profile={profile_data}",
        f"--ignore-filename-regex={ignored_dependencies}",
    ]
    for binary in binaries:
        command.append(f"--object={binary}")
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout)[-6000:]
        raise CoverageError(f"command failed ({result.returncode}): {command!r}\n{detail}")
    if result.stderr.strip():
        raise CoverageError(f"llvm-cov LCOV export emitted diagnostics:\n{result.stderr[-6000:]}")

    source_lines: dict[str, dict[int, int]] = {}
    current_path: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("SF:"):
            filename = str(Path(line[3:]).resolve())
            absolute_path = Path(filename)
            if not absolute_path.is_relative_to(ROOT.resolve()):
                current_path = None
                continue
            relative_path = str(absolute_path.relative_to(ROOT.resolve()))
            current_path = relative_path if relative_path in allowed_sources else None
            if current_path is not None:
                if current_path in source_lines:
                    raise CoverageError(f"LCOV export duplicates production file row: {current_path}")
                source_lines[current_path] = {}
            continue
        if current_path is None or not line.startswith("DA:"):
            continue
        fields = line[3:].split(",")
        if len(fields) < 2:
            raise CoverageError(f"LCOV export has an invalid line record: {line!r}")
        try:
            line_number, count = int(fields[0]), int(fields[1])
        except ValueError as error:
            raise CoverageError(f"LCOV export has an invalid line record: {line!r}") from error
        if line_number < 1 or count < 0:
            raise CoverageError(f"LCOV export has an out-of-range line record: {line!r}")
        if line_number in source_lines[current_path]:
            raise CoverageError(
                f"LCOV export repeats line {line_number} in production file {current_path}"
            )
        source_lines[current_path][line_number] = count

    return source_lines


def source_lines_for_region(region: dict[str, Any]) -> set[int]:
    """Return physical source lines intersected by one executable LLVM region."""
    start = region["start"]
    end = region["end"]
    start_line = int(start["line"])
    start_column = int(start["column"])
    end_line = int(end["line"])
    end_column = int(end["column"])
    if start_line < 1 or end_line < start_line or start_column < 1 or end_column < 1:
        raise CoverageError(f"LLVM region has invalid source coordinates: {region!r}")
    if start_line == end_line and end_column <= start_column:
        raise CoverageError(f"executable LLVM region has an empty source span: {region!r}")
    # LLVM source columns are one-based and the end coordinate is exclusive.
    # A region ending at column 1 on a later line does not contain code there.
    last_line = end_line if end_column > 1 else end_line - 1
    return set(range(start_line, last_line + 1))


def physical_line_summaries(
    lcov_lines: dict[str, dict[int, int]],
    regions: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """Validate LCOV line records against the union of executable source spans."""
    summaries = {path: {"lines": 0, "lines_total": 0} for path in PRODUCTION_SOURCE_SET}
    evidence: dict[str, dict[str, int]] = {}
    for path in EXECUTABLE_SOURCE_SET:
        records = lcov_lines.get(path)
        if records is None:
            raise CoverageError(f"LLVM LCOV export omitted executable production source {path}")
        region_lines: set[int] = set()
        covered_region_lines: set[int] = set()
        for region in regions.values():
            if region["file"] != path:
                continue
            span_lines = source_lines_for_region(region)
            region_lines.update(span_lines)
            if region["covered"]:
                covered_region_lines.update(span_lines)
        lcov_line_numbers = set(records)
        if region_lines != lcov_line_numbers:
            missing_spans = sorted(lcov_line_numbers - region_lines)
            missing_lcov = sorted(region_lines - lcov_line_numbers)
            raise CoverageError(
                f"LLVM LCOV physical lines differ from executable region spans for {path}: "
                f"unattributed_lcov={missing_spans[:12]}, unrecorded_spans={missing_lcov[:12]}"
            )
        lcov_covered_lines = {line for line, count in records.items() if count > 0}
        if covered_region_lines != lcov_covered_lines:
            missing_hits = sorted(lcov_covered_lines - covered_region_lines)
            missing_records = sorted(covered_region_lines - lcov_covered_lines)
            raise CoverageError(
                f"LLVM LCOV hit lines differ from covered executable region spans for {path}: "
                f"unattributed_hits={missing_hits[:12]}, span_without_hit={missing_records[:12]}"
            )
        summaries[path] = {
            "lines": len(lcov_covered_lines),
            "lines_total": len(lcov_line_numbers),
        }
        evidence[path] = {
            "lcov_lines": len(lcov_line_numbers),
            "region_span_lines": len(region_lines),
            "lcov_covered_lines": len(lcov_covered_lines),
            "covered_region_span_lines": len(covered_region_lines),
        }

    for path in NO_COUNTER_SOURCE_SET:
        if lcov_lines.get(path):
            raise CoverageError(f"source classified as no-counter has LCOV line records: {path}")
        if any(region["file"] == path for region in regions.values()):
            raise CoverageError(f"source classified as no-counter has executable regions: {path}")
    return summaries, evidence


def source_region_map(
    llvm_report: dict[str, Any],
    source_digest: str,
    allowed_sources: set[str],
    *,
    canonical_functions: dict[tuple[str, int, int], str] | None = None,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, int]],
    dict[tuple[str, int, int], str],
]:
    """Map LLVM function-instantiation groups to source-span regions.

    LLVM's file summary counts regions per instantiation group and merges each
    group's instantiations by taking the maximum covered and total counts. Use
    that same deterministic representative to preserve LLVM's denominator and
    raw summary, but attribute a source region as hit when any monomorphization
    executes the exact source span. Generic instantiations share the source
    region even when their branch outcomes differ. Reuse the aggregate-selected
    representative's source spans when attributing isolated case profiles.
    """
    data = llvm_report["data"][0]
    root = ROOT.resolve()
    resolved_filenames: dict[str, str] = {}

    def resolve_filename(filename: str) -> str:
        # Filenames repeat across thousands of regions in one fixed export.
        # Resolve each path once without caching across measurements.
        if filename not in resolved_filenames:
            resolved_filenames[filename] = str(Path(filename).resolve())
        return resolved_filenames[filename]

    files: dict[str, dict[str, Any]] = {}
    relative_paths: dict[str, str] = {}
    for item in data["files"]:
        normalized = resolve_filename(item["filename"])
        absolute_path = Path(normalized)
        if not absolute_path.is_relative_to(root):
            continue
        relative_path = str(absolute_path.relative_to(root))
        if relative_path in allowed_sources:
            if normalized in files:
                raise CoverageError(f"LLVM export duplicates production file row: {relative_path}")
            files[normalized] = item
            relative_paths[normalized] = relative_path
    if not files:
        raise CoverageError("LLVM export contains no files beneath the repository")

    regions: dict[str, dict[str, Any]] = {}
    file_summaries: dict[str, dict[str, int]] = {}
    function_groups: dict[tuple[str, int, int], list[tuple[str, list[list[int]]]]] = {}
    for absolute_path, file_data in files.items():
        relative_path = relative_paths[absolute_path]
        summary = file_data["summary"]
        file_summaries[relative_path] = {
            metric: int(summary[metric]["covered"])
            for metric in ("regions", "lines")
        } | {
            f"{metric}_total": int(summary[metric]["count"])
            for metric in ("regions", "lines")
        }

    for function in data["functions"]:
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            raise CoverageError("LLVM export contains an invalid function row")
        filenames = function.get("filenames")
        raw_regions = function.get("regions")
        if not isinstance(filenames, list) or not all(isinstance(path, str) for path in filenames):
            raise CoverageError(f"LLVM function has invalid filenames: {function['name']}")
        if not isinstance(raw_regions, list):
            raise CoverageError(f"LLVM function has invalid regions: {function['name']}")
        function_paths = [resolve_filename(filename) for filename in filenames]
        by_file: dict[str, list[list[int]]] = {}
        for raw_region in raw_regions:
            if not isinstance(raw_region, list) or len(raw_region) != 8 or not all(
                type(value) is int for value in raw_region
            ):
                raise CoverageError(f"LLVM function has an invalid region: {function['name']}")
            start_line, start_column, end_line, end_column, count, file_index, _, kind = raw_region
            if file_index < 0 or file_index >= len(filenames):
                raise CoverageError(f"LLVM region has an invalid file index: {function['name']}")
            absolute_path = function_paths[file_index]
            if absolute_path not in files:
                continue
            relative_path = relative_paths[absolute_path]
            by_file.setdefault(relative_path, []).append(raw_region)

        for relative_path, file_regions in by_file.items():
            code_regions = [region for region in file_regions if region[7] == 0]
            if not code_regions:
                continue
            first_region = file_regions[0]
            group_key = (relative_path, first_region[0], first_region[1])
            function_groups.setdefault(group_key, []).append((function["name"], code_regions))

    if not function_groups:
        raise CoverageError("LLVM export has no executable production function regions")
    if canonical_functions is not None and set(function_groups) != set(canonical_functions):
        raise CoverageError("case LLVM function groups differ from aggregate function groups")

    selected_functions: dict[tuple[str, int, int], str] = {}
    summary_reconstructed: dict[str, dict[str, int]] = {
        path: {"regions": 0, "regions_total": 0}
        for path in file_summaries
    }
    for group_key, instantiations in function_groups.items():
        relative_path, group_line, group_column = group_key
        symbols = [symbol for symbol, _ in instantiations]
        if len(symbols) != len(set(symbols)):
            raise CoverageError(f"LLVM function symbol repeats within group {group_key}")
        totals = {symbol: len(code_regions) for symbol, code_regions in instantiations}
        covered = {
            symbol: sum(region[4] > 0 for region in code_regions)
            for symbol, code_regions in instantiations
        }
        if canonical_functions is None:
            max_total = max(totals.values())
            max_covered = max(covered.values())
            representatives = [
                symbol for symbol in symbols
                if totals[symbol] == max_total and covered[symbol] == max_covered
            ]
            if not representatives:
                raise CoverageError(
                    f"LLVM region total and covered maxima have no common instantiation: {group_key}"
                )
            symbol = min(representatives)
            summary_reconstructed[relative_path]["regions"] += max_covered
            summary_reconstructed[relative_path]["regions_total"] += max_total
        else:
            symbol = canonical_functions[group_key]
            if symbol not in totals:
                raise CoverageError(f"aggregate LLVM representative is missing for {group_key}")
        selected_functions[group_key] = symbol
        selected_regions = next(
            code_regions for candidate, code_regions in instantiations if candidate == symbol
        )
        representative_spans = {
            (region[0], region[1], region[2], region[3], region[7])
            for region in selected_regions
        }
        covered_source_spans: set[tuple[int, int, int, int, int]] = set()
        for candidate, code_regions in instantiations:
            candidate_spans = {
                (region[0], region[1], region[2], region[3], region[7])
                for region in code_regions
            }
            if not candidate_spans <= representative_spans:
                raise CoverageError(
                    f"LLVM instantiation has source regions outside its representative: {group_key}"
                )
            covered_source_spans.update(
                (region[0], region[1], region[2], region[3], region[7])
                for region in code_regions
                if region[4] > 0
            )

        for raw_region in selected_regions:
            start_line, start_column, end_line, end_column, _, _, _, kind = raw_region
            source_span = (start_line, start_column, end_line, end_column, kind)
            identity = [
                source_digest,
                relative_path,
                group_line,
                group_column,
                symbol,
                start_line,
                start_column,
                end_line,
                end_column,
                kind,
            ]
            region_id = digest_json(identity)
            if region_id in regions:
                raise CoverageError(f"LLVM function-instantiation region repeats: {region_id}")
            regions[region_id] = {
                "id": region_id,
                "file": relative_path,
                "function_group": {"line": group_line, "column": group_column},
                "start": {"line": start_line, "column": start_column},
                "end": {"line": end_line, "column": end_column},
                "kind": kind,
                "function_symbols": [symbol],
                "covered": source_span in covered_source_spans,
            }

    if canonical_functions is None:
        for relative_path, summary in file_summaries.items():
            reconstructed = summary_reconstructed.get(relative_path, {"regions": 0, "regions_total": 0})
            if (reconstructed["regions"], reconstructed["regions_total"]) != (
                summary["regions"], summary["regions_total"]
            ):
                raise CoverageError(
                    f"LLVM instantiation summaries differ for {relative_path}: "
                    f"{reconstructed['regions']}/{reconstructed['regions_total']} != "
                    f"{summary['regions']}/{summary['regions_total']}"
                )

    for relative_path, summary in file_summaries.items():
        expected_regions = summary["regions_total"]
        actual_regions = sum(region["file"] == relative_path for region in regions.values())
        if actual_regions != expected_regions:
            raise CoverageError(
                f"LLVM region identities for {relative_path} differ from its summary: "
                f"{actual_regions} != {expected_regions}"
            )
    for relative_path in EXECUTABLE_SOURCE_SET:
        if relative_path not in file_summaries:
            raise CoverageError(f"LLVM export omitted executable production source {relative_path}")
    for relative_path in NO_COUNTER_SOURCE_SET:
        summary = file_summaries.get(relative_path)
        if summary is not None and any(summary.values()):
            raise CoverageError(
                f"source classified as no-counter has executable coverage counters: {relative_path}"
            )
        file_summaries.setdefault(
            relative_path,
            {"regions": 0, "lines": 0, "regions_total": 0, "lines_total": 0},
        )
    return regions, file_summaries, selected_functions


def filter_llvm_export_sources(
    llvm_report: dict[str, Any], allowed_sources: set[str]
) -> dict[str, Any]:
    """Restrict the saved LLVM document to the declared production sources."""
    data_rows = llvm_report.get("data")
    if not isinstance(data_rows, list) or len(data_rows) != 1:
        raise CoverageError("cannot source-filter an unsupported LLVM export")
    data = data_rows[0]

    def source_path(filename: str) -> str | None:
        path = Path(filename).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            return None
        relative = str(path.relative_to(ROOT.resolve()))
        return relative if relative in allowed_sources else None

    retained_files = [
        item for item in data.get("files", []) if source_path(item.get("filename", "")) is not None
    ]
    retained_names = {item["filename"] for item in retained_files}
    for required in EXECUTABLE_SOURCE_SET:
        if not any(source_path(name) == required for name in retained_names):
            raise CoverageError(f"filtered LLVM export omitted production source {required}")

    retained_functions = []
    for function in data.get("functions", []):
        old_filenames = function.get("filenames", [])
        index_map: dict[int, int] = {}
        filenames: list[str] = []
        for old_index, filename in enumerate(old_filenames):
            if source_path(filename) is not None:
                index_map[old_index] = len(filenames)
                filenames.append(filename)
        regions = []
        for raw_region in function.get("regions", []):
            if not isinstance(raw_region, list) or len(raw_region) != 8:
                raise CoverageError("LLVM export contains an unsupported function region")
            old_index = raw_region[5]
            if old_index not in index_map:
                continue
            filtered_region = list(raw_region)
            filtered_region[5] = index_map[old_index]
            regions.append(filtered_region)
        if not regions:
            continue
        if function.get("branches") or function.get("mcdc_records"):
            raise CoverageError("source filtering does not support branch or MC/DC records")
        retained_functions.append(function | {"filenames": filenames, "regions": regions})

    data["files"] = retained_files
    data["functions"] = retained_functions
    metrics = ("branches", "functions", "instantiations", "lines", "mcdc", "regions")
    totals: dict[str, dict[str, int | float]] = {}
    for metric in metrics:
        count = sum(int(item["summary"][metric]["count"]) for item in retained_files)
        covered = sum(int(item["summary"][metric]["covered"]) for item in retained_files)
        total: dict[str, int | float] = {
            "count": count,
            "covered": covered,
            "percent": (covered / count * 100) if count else 0,
        }
        if any("notcovered" in item["summary"][metric] for item in retained_files):
            total["notcovered"] = count - covered
        totals[metric] = total
    data["totals"] = totals
    return llvm_report


def normalize_llvm_source_summaries(
    llvm_report: dict[str, Any], source_summaries: dict[str, dict[str, int]]
) -> None:
    """Make LLVM file and aggregate summaries use the unified source inventory.

    LLVM retains separate function rows for Rust monomorphizations and its
    default file summary takes one maximum-covered instantiation per group.
    The unified report instead attributes each canonical source span as hit
    when any instantiation executes it. Keep those raw function counters, but
    publish file and aggregate summaries on the same source-span basis used by
    ``uvicorn_rs_unified.coverage.regions`` and Coverage-MCP.
    """
    data_rows = llvm_report.get("data")
    if not isinstance(data_rows, list) or len(data_rows) != 1:
        raise CoverageError("cannot normalize an unsupported LLVM export")
    data = data_rows[0]
    files = data.get("files")
    if not isinstance(files, list):
        raise CoverageError("cannot normalize LLVM export without file rows")

    seen: set[str] = set()
    for item in files:
        filename = item.get("filename")
        if not isinstance(filename, str):
            raise CoverageError("cannot normalize LLVM export with an invalid filename")
        absolute_path = Path(filename).resolve()
        if not absolute_path.is_relative_to(ROOT.resolve()):
            continue
        relative_path = str(absolute_path.relative_to(ROOT.resolve()))
        expected = source_summaries.get(relative_path)
        if expected is None:
            continue
        seen.add(relative_path)
        summary = item.get("summary")
        if not isinstance(summary, dict):
            raise CoverageError(f"LLVM summary missing for {relative_path}")
        for metric in ("regions", "lines"):
            values = expected
            covered = values[metric]
            count = values[f"{metric}_total"]
            row = summary.get(metric)
            if not isinstance(row, dict):
                raise CoverageError(f"LLVM {metric} summary missing for {relative_path}")
            row["covered"] = covered
            row["count"] = count
            row["notcovered"] = count - covered
            row["percent"] = covered / count * 100 if count else 0

    missing = set(EXECUTABLE_SOURCE_SET) - seen
    if missing:
        raise CoverageError(f"normalized LLVM export omitted executable sources: {sorted(missing)}")

    metrics = ("branches", "functions", "instantiations", "lines", "mcdc", "regions")
    totals: dict[str, dict[str, int | float]] = {}
    for metric in metrics:
        count = sum(int(item["summary"][metric]["count"]) for item in files)
        covered = sum(int(item["summary"][metric]["covered"]) for item in files)
        totals[metric] = {
            "count": count,
            "covered": covered,
            "notcovered": count - covered,
            "percent": covered / count * 100 if count else 0,
        }
    data["totals"] = totals


def selected_case_results(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in result.get("cases", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "asgi-coverage" / "unified" / "coverage-report.json",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=ROOT / "build" / "asgi-coverage" / "unified" / "artifacts",
    )
    parser.add_argument(
        "--oracle-python",
        type=Path,
        required=True,
        help="isolated Python environment containing stock Uvicorn 0.54.0",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="attribute a case ID; use native:<id> for native contracts, asgi:<id> for parity cases, or an unprefixed ASGI ID",
    )
    parser.add_argument("--matrix-repeats", type=int, default=3, help="complete matrix repeats; use 0 to skip")
    parser.add_argument(
        "--matrix-infra-retries",
        type=int,
        default=1,
        help="bounded retries for complete-matrix infrastructure failures only",
    )
    parser.add_argument("--skip-build", action="store_true", help="use the currently installed instrumented extension")
    parser.add_argument("--case-timeout", type=int, default=300)
    parser.add_argument(
        "--case-infra-retries",
        type=int,
        default=1,
        help="bounded retries for per-case infrastructure failures only",
    )
    args = parser.parse_args()
    oracle_python = Path(os.path.abspath(args.oracle_python))
    if not oracle_python.is_file() or not os.access(oracle_python, os.X_OK):
        parser.error(f"--oracle-python must be an executable interpreter: {oracle_python}")
    if args.matrix_repeats not in {0, 3}:
        parser.error("--matrix-repeats must be 0 for a selected subset or exactly 3 for full matrices")
    if args.case_timeout < 30:
        parser.error("--case-timeout must be at least 30 seconds")
    if args.case_infra_retries < 0:
        parser.error("--case-infra-retries cannot be negative")
    if args.matrix_infra_retries < 0:
        parser.error("--matrix-infra-retries cannot be negative")

    started_at = utc_now()
    run_id = uuid.uuid4().hex
    output = args.output.resolve()
    artifacts_root = args.artifacts_dir.resolve() / run_id
    case_results_root = artifacts_root / "cases"
    profile_root = artifacts_root / "profiles"
    repeat_root = artifacts_root / "matrix-runs"
    native_case_results_root = artifacts_root / "native-cases"
    native_profile_root = artifacts_root / "native-profiles"
    native_input_root = artifacts_root / "native-inputs"
    native_repeat_root = artifacts_root / "native-matrix-runs"
    for path in (
        case_results_root,
        profile_root,
        repeat_root,
        native_case_results_root,
        native_profile_root,
        native_input_root,
        native_repeat_root,
    ):
        path.mkdir(parents=True, exist_ok=False)

    if not args.skip_build:
        build_log = artifacts_root / "instrumented-build.log"
        build = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        build_log.write_text(build.stdout + build.stderr, encoding="utf-8")
        if build.returncode:
            raise CoverageError(f"instrumented build failed; see {build_log}")

    manifest, input_document, input_paths = run_parity.load_contract()
    all_cases = input_document["cases"]
    native_manifest, all_native_cases = load_native_contract()
    shared_requirements = {
        requirement
        for case in all_cases
        for requirement in case.get("covers", [])
    }
    for case in all_native_cases:
        unknown_requirements = set(case.get("covers", [])) - shared_requirements
        if unknown_requirements:
            raise CoverageError(
                f"native-core case {case['id']} references unknown requirements: "
                f"{sorted(unknown_requirements)}"
            )
    if args.case_id:
        requested_asgi: set[str] = set()
        requested_native: set[str] = set()
        known_asgi = {case["case_id"] for case in all_cases}
        known_native = {case["id"] for case in all_native_cases}
        unknown = []
        for requested_id in args.case_id:
            if requested_id.startswith("native:"):
                case_id = requested_id.removeprefix("native:")
                if case_id in known_native:
                    requested_native.add(case_id)
                else:
                    unknown.append(requested_id)
            elif requested_id.startswith("asgi:"):
                case_id = requested_id.removeprefix("asgi:")
                if case_id in known_asgi:
                    requested_asgi.add(case_id)
                else:
                    unknown.append(requested_id)
            elif requested_id in known_asgi:
                requested_asgi.add(requested_id)
            else:
                unknown.append(requested_id)
        if unknown:
            parser.error(f"unknown case ID(s): {', '.join(unknown)}")
        cases = [case for case in all_cases if case["case_id"] in requested_asgi]
        native_cases = [case for case in all_native_cases if case["id"] in requested_native]
    else:
        cases = all_cases
        native_cases = all_native_cases
    if not cases and not native_cases:
        parser.error("at least one case must be selected")
    if args.case_id and args.matrix_repeats:
        parser.error("--matrix-repeats requires both complete input matrices; set it to 0 for selected cases")

    source = source_identity(manifest, input_paths, native_manifest)
    llvm_cov, llvm_profdata, tool_versions = llvm_tools()
    identity_profile_dir = artifacts_root / "identity-profile"
    identity_profile_dir.mkdir(parents=True, exist_ok=False)
    os.environ["LLVM_PROFILE_FILE"] = str(identity_profile_dir / "%p-%m.profraw")
    extension = Path(run_parity.runtime_identity(manifest)[1]["native_extension"]["path"])
    if not extension.is_absolute():
        extension = ROOT / extension
    if not extension.is_file():
        raise CoverageError(f"instrumented extension does not exist: {extension}")
    if not extension.resolve().is_relative_to((PYTHON_SOURCE / "uvicorn_rs").resolve()):
        raise CoverageError(
            "coverage run imported the native extension outside the source package: "
            f"{extension}; expected an extension under {PYTHON_SOURCE / 'uvicorn_rs'}"
        )
    native_runner = NATIVE_RUNNER
    if sys.platform == "win32":
        native_runner = native_runner.with_suffix(".exe")
    if not native_runner.is_file():
        raise CoverageError(f"instrumented native contract runner does not exist: {native_runner}")
    build_identity = {
        "native_extension": str(extension.relative_to(ROOT)),
        "native_extension_sha256": digest_file(extension),
        "native_runner": str(native_runner.relative_to(ROOT)),
        "native_runner_sha256": digest_file(native_runner),
        "native_runner_profile": "cargo-llvm-cov release profile with workspace crate instrumentation",
        "cargo_lock_sha256": digest_file(ROOT / "Cargo.lock"),
        "tools": tool_versions,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    native_runner_snapshot = artifacts_root / "coverage-objects" / native_runner.name
    native_runner_snapshot.parent.mkdir(parents=True, exist_ok=False)
    shutil.copy2(native_runner, native_runner_snapshot)
    if digest_file(native_runner_snapshot) != build_identity["native_runner_sha256"]:
        raise CoverageError("native coverage runner snapshot differs from the recorded build")

    case_receipts: list[dict[str, Any]] = []
    native_case_receipts: list[dict[str, Any]] = []
    all_case_profiles: list[Path] = []
    immutable_identity: tuple[str, str, str] | None = None
    for index, case in enumerate(cases, 1):
        slug = case_slug(case["case_id"])
        case_dir = case_results_root / slug
        profile_dir = profile_root / slug
        case_dir.mkdir(parents=True, exist_ok=False)
        attempts: list[dict[str, Any]] = []
        all_raw_profiles: list[Path] = []
        final_exit_code: int | None = None
        result: dict[str, Any] | None = None
        case_result: dict[str, Any] | None = None
        result_path: Path | None = None
        status = "infrastructure_failed"
        error: str | None = None
        case_attempt_identity: tuple[str, str, str] | None = None
        for attempt_index in range(args.case_infra_retries + 1):
            attempt_dir = case_dir if attempt_index == 0 else case_dir / f"attempt-{attempt_index + 1}"
            if attempt_index > 0:
                attempt_dir.mkdir(parents=True, exist_ok=False)
            attempt_profile_dir = profile_dir / f"attempt-{attempt_index + 1}"
            attempt_profile_dir.mkdir(parents=True, exist_ok=False)
            result_path = attempt_dir / "parity-result.json"
            command = [
                sys.executable,
                str(RUNNER),
                "--oracle-python",
                str(oracle_python),
                "--case-id",
                case["case_id"],
                "--coverage-profile-dir",
                str(attempt_profile_dir),
                "--output",
                str(result_path),
            ]
            if case.get("verification") == "fault-contract":
                command.append("--fault-contracts")
            try:
                process = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=args.case_timeout,
                    check=False,
                )
                attempt_exit_code: int | None = process.returncode
                stdout, stderr = process.stdout, process.stderr
            except subprocess.TimeoutExpired as timeout_error:
                attempt_exit_code = None
                stdout = (timeout_error.stdout.decode(errors="replace")
                          if isinstance(timeout_error.stdout, bytes) else (timeout_error.stdout or ""))
                stderr = (timeout_error.stderr.decode(errors="replace")
                          if isinstance(timeout_error.stderr, bytes) else (timeout_error.stderr or ""))
                stderr += f"\nparity case exceeded {args.case_timeout} seconds"
            (attempt_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (attempt_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            attempt_result = (
                json.loads(result_path.read_text(encoding="utf-8"))
                if result_path.is_file()
                else None
            )
            if attempt_result is not None:
                attempt_run = attempt_result.get("run", {})
                attempt_identity = (
                    attempt_run.get("target", {}).get("native_extension", {}).get("sha256", ""),
                    attempt_run.get("manifest", {}).get("sha256", ""),
                    attempt_run.get("target", {}).get("cargo_lock_sha256", ""),
                )
                if case_attempt_identity is None:
                    case_attempt_identity = attempt_identity
                elif attempt_identity != case_attempt_identity:
                    raise CoverageError(
                        f"source/build identity changed between attempts for case {case['case_id']}"
                    )
            attempt_case_result = (
                selected_case_results(attempt_result).get(case["case_id"])
                if attempt_result is not None
                else None
            )
            attempt_status = (
                attempt_case_result["status"]
                if attempt_case_result is not None
                else "infrastructure_failed"
            )
            attempt_profiles = sorted((attempt_profile_dir / "target").glob("*.profraw"))
            if (
                not attempt_profiles
                or attempt_exit_code not in (0, 1)
                or (attempt_result is not None and attempt_result.get("infrastructure_errors"))
            ):
                attempt_status = "infrastructure_failed"
            attempts.append({
                "attempt": attempt_index + 1,
                "status": attempt_status,
                "runner_exit_code": attempt_exit_code,
                "stdout_artifact": str((attempt_dir / "stdout.log").relative_to(ROOT)),
                "stderr_artifact": str((attempt_dir / "stderr.log").relative_to(ROOT)),
                "result_artifact": (
                    str(result_path.relative_to(ROOT)) if result_path.is_file() else None
                ),
                "result_sha256": digest_file(result_path) if result_path.is_file() else None,
                "profile_data_artifacts": [
                    str(path.relative_to(ROOT)) for path in attempt_profiles
                ],
                "profile_data_receipts": profile_receipts(attempt_profiles),
            })
            result = attempt_result
            case_result = attempt_case_result
            status = attempt_status
            final_exit_code = attempt_exit_code
            error = (
                attempt_case_result.get("error", {}).get("message")
                if attempt_case_result is not None
                else f"parity runner returned {attempt_exit_code} without a result for the selected case"
            )
            all_raw_profiles.extend(attempt_profiles)
            if status != "infrastructure_failed":
                break
            if attempt_index < args.case_infra_retries:
                print(
                    f"[{index}/{len(cases)}] RETRY {case['case_id']} after infrastructure failure "
                    f"({attempt_index + 1}/{args.case_infra_retries})",
                    flush=True,
                )

        if result_path is None or not attempts:
            case_receipts.append({
                "case_id": case["case_id"],
                "case_key": case_key("asgi", case["case_id"]),
                "profile": case["profile"],
                "operation": case["operation"],
                "verification": case.get("verification", "oracle-parity"),
                "fault": case.get("fault"),
                "status": "infrastructure_failed",
                "error": "no per-case parity attempt was executed",
                "hit_region_ids": [],
                "attempts": attempts,
            })
            continue

        if not all_raw_profiles:
            case_receipts.append({
                "case_id": case["case_id"],
                "case_key": case_key("asgi", case["case_id"]),
                "profile": case["profile"],
                "operation": case["operation"],
                "verification": case.get("verification", "oracle-parity"),
                "fault": case.get("fault"),
                "status": "infrastructure_failed",
                "error": "instrumented target process produced no LLVM profile",
                "result_artifact": str(result_path.relative_to(ROOT)),
                "stdout_artifact": str((result_path.parent / "stdout.log").relative_to(ROOT)),
                "stderr_artifact": str((result_path.parent / "stderr.log").relative_to(ROOT)),
                "hit_region_ids": [],
                "attempts": attempts,
            })
            print(f"[{index}/{len(cases)}] ERROR {case['case_id']}: no target profile", flush=True)
            continue

        if result is None or case_result is None:
            case_receipts.append({
                "case_id": case["case_id"],
                "case_key": case_key("asgi", case["case_id"]),
                "profile": case["profile"],
                "operation": case["operation"],
                "verification": case.get("verification", "oracle-parity"),
                "fault": case.get("fault"),
                "status": "infrastructure_failed",
                "error": error or "parity runner produced no selected-case result",
                "result_artifact": str(result_path.relative_to(ROOT)) if result_path.is_file() else None,
                "result_sha256": digest_file(result_path) if result_path.is_file() else None,
                "stdout_artifact": str((result_path.parent / "stdout.log").relative_to(ROOT)),
                "stderr_artifact": str((result_path.parent / "stderr.log").relative_to(ROOT)),
                "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in all_raw_profiles],
                "profile_data_receipts": profile_receipts(all_raw_profiles),
                "hit_region_ids": [],
                "covered_regions": 0,
                "attempts": attempts,
                "transient_infrastructure_failures": sum(
                    attempt["status"] == "infrastructure_failed" for attempt in attempts[:-1]
                ),
            })
            print(f"[{index}/{len(cases)}] ERROR {case['case_id']}: no selected-case result", flush=True)
            continue

        case_profdata = case_dir / "target.profdata"
        run_checked([
            str(llvm_profdata), "merge", "-sparse", "-failure-mode=all", "-o",
            str(case_profdata), *map(str, all_raw_profiles),
        ], timeout=120)
        all_case_profiles.extend(all_raw_profiles)
        assert result is not None
        run_meta = result.get("run", {})
        run_identity = (
            run_meta.get("target", {}).get("native_extension", {}).get("sha256", ""),
            run_meta.get("manifest", {}).get("sha256", ""),
            run_meta.get("target", {}).get("cargo_lock_sha256", ""),
        )
        if immutable_identity is None:
            immutable_identity = run_identity
        elif run_identity != immutable_identity:
            raise CoverageError(f"source/build identity changed while measuring case {case['case_id']}")

        case_receipts.append({
            "case_id": case["case_id"],
            "case_key": case_key("asgi", case["case_id"]),
            "profile": case["profile"],
            "operation": case["operation"],
            "requirements": case["covers"],
            "verification": case.get("verification", "oracle-parity"),
            "fault": case.get("fault"),
            "status": status if final_exit_code in (0, 1) else "infrastructure_failed",
            "error": error or (None if final_exit_code in (0, 1) else f"runner exit status {final_exit_code}"),
            "observations": {
                "oracle": case_result.get("oracle_observation") if case_result else None,
                "target": case_result.get("target_observation") if case_result else None,
                "difference": case_result.get("difference") if case_result else None,
            },
            "result_artifact": str(result_path.relative_to(ROOT)),
            "result_sha256": digest_file(result_path),
            "stdout_artifact": str((result_path.parent / "stdout.log").relative_to(ROOT)),
            "stderr_artifact": str((result_path.parent / "stderr.log").relative_to(ROOT)),
            "run_id": run_meta.get("run_id"),
            "target_extension_sha256": run_identity[0],
            "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in all_raw_profiles],
            "profile_data_receipts": profile_receipts(all_raw_profiles),
            "hit_region_ids": [],
            "covered_regions": 0,
            "attempts": attempts,
            "transient_infrastructure_failures": sum(
                attempt["status"] == "infrastructure_failed" for attempt in attempts[:-1]
            ),
        })
        print(
            f"[{index}/{len(cases)}] {status.upper()} {case['case_id']} "
            "(region attribution deferred until aggregate LLVM representatives are selected)",
            flush=True,
        )

    for index, case in enumerate(native_cases, 1):
        restore_native_runner(
            native_runner, native_runner_snapshot, build_identity["native_runner_sha256"]
        )
        case_id = case["id"]
        slug = case_slug(case_id)
        case_dir = native_case_results_root / slug
        case_dir.mkdir(parents=True, exist_ok=False)
        profile_dir = native_profile_root / slug
        profile_dir.mkdir(parents=True, exist_ok=False)
        input_path = native_input_root / f"{slug}.json"
        one_case_manifest = dict(native_manifest)
        one_case_manifest["cases"] = [case]
        write_json(input_path, one_case_manifest)
        result_path = case_dir / "native-result.json"
        stdout_path = case_dir / "stdout.log"
        stderr_path = case_dir / "stderr.log"
        profile_pattern = profile_dir / "%p-%m.profraw"
        env = os.environ.copy()
        env["LLVM_PROFILE_FILE"] = str(profile_pattern)
        try:
            process = subprocess.run(
                [str(native_runner), str(input_path)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=args.case_timeout,
                check=False,
            )
            exit_code: int | None = process.returncode
            stdout, stderr = process.stdout, process.stderr
        except subprocess.TimeoutExpired as error:
            exit_code = None
            stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
            stderr += f"\nnative case exceeded {args.case_timeout} seconds"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        profiles = sorted(profile_dir.glob("*.profraw"))
        passed_ids = native_pass_ids(stdout)
        verification = case.get("verification", "target-contract")
        fault = case.get("fault")
        fault_consumed = (
            verification == "fault-contract"
            and f"FAULT_CONSUMED {fault['point']}" in stdout.splitlines()
        )
        fault_contract_passed = verification != "fault-contract" or fault_consumed
        status = "passed" if exit_code == 0 and passed_ids == [case_id] and profiles and fault_contract_passed else "failed"
        if not profiles:
            status = "infrastructure_failed"
        native_result = {
            "schema": "uvicorn-rs-native-case-result/3",
            "case_id": case_id,
            "case_key": case_key("native", case_id),
            "verification": verification,
            "fault": fault,
            "fault_consumed": fault_consumed,
            "status": status,
            "runner_exit_code": exit_code,
            "expected_pass_ids": [case_id],
            "observed_pass_ids": passed_ids,
            "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in profiles],
            "profile_data_receipts": profile_receipts(profiles),
        }
        write_json(result_path, native_result)
        if profiles:
            case_profdata = case_dir / "target.profdata"
            run_checked([
                str(llvm_profdata), "merge", "-sparse", "-failure-mode=all", "-o",
                str(case_profdata), *map(str, profiles),
            ], timeout=120)
            all_case_profiles.extend(profiles)
            merged_profile = case_profdata
        else:
            merged_profile = None
        native_case_receipts.append({
            "case_id": case_id,
            "case_key": case_key("native", case_id),
            "operation": case.get("operation"),
            "protocol": case.get("protocol"),
            "requirements": case.get("covers", []),
            "verification": verification,
            "fault": fault,
            "fault_consumed": fault_consumed,
            "status": status,
            "error": None if status == "passed" else f"native runner exit={exit_code}, pass_ids={passed_ids!r}",
            "runner_exit_code": exit_code,
            "expected_pass_ids": [case_id],
            "observed_pass_ids": passed_ids,
            "result_artifact": str(result_path.relative_to(ROOT)),
            "result_sha256": digest_file(result_path),
            "stdout_artifact": str(stdout_path.relative_to(ROOT)),
            "stderr_artifact": str(stderr_path.relative_to(ROOT)),
            "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in profiles],
            "profile_data_receipts": profile_receipts(profiles),
            "merged_profile_artifact": str(merged_profile.relative_to(ROOT)) if merged_profile else None,
            "hit_region_ids": [],
            "covered_regions": 0,
            "attempts": [{
                "attempt": 1,
                "status": status,
                "verification": verification,
                "fault": fault,
                "fault_consumed": fault_consumed,
                "runner_exit_code": exit_code,
                "result_artifact": str(result_path.relative_to(ROOT)),
                "result_sha256": digest_file(result_path),
                "stdout_artifact": str(stdout_path.relative_to(ROOT)),
                "stderr_artifact": str(stderr_path.relative_to(ROOT)),
                "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in profiles],
                "profile_data_receipts": profile_receipts(profiles),
            }],
            "transient_infrastructure_failures": 0,
        })
        print(
            f"[native {index}/{len(native_cases)}] {status.upper()} {case_id} "
            "(region attribution deferred until aggregate LLVM representatives are selected)",
            flush=True,
        )

    if not all_case_profiles:
        raise CoverageError("no case produced an attributable target profile")

    matrix_runs: list[dict[str, Any]] = []
    for repeat in range(1, args.matrix_repeats + 1):
        repeat_dir = repeat_root / f"run-{repeat}"
        repeat_dir.mkdir(parents=True, exist_ok=False)
        attempts: list[dict[str, Any]] = []
        final_result: dict[str, Any] | None = None
        final_result_path: Path | None = None
        final_exit_code: int | None = None
        for attempt_index in range(args.matrix_infra_retries + 1):
            attempt_dir = repeat_dir if attempt_index == 0 else repeat_dir / f"attempt-{attempt_index + 1}"
            if attempt_index > 0:
                attempt_dir.mkdir(parents=True, exist_ok=False)
            result_path = attempt_dir / "parity-result.json"
            env = os.environ.copy()
            env["LLVM_PROFILE_FILE"] = str(attempt_dir / "%p-%m.profraw")
            command = [
                sys.executable,
                str(RUNNER),
                "--oracle-python",
                str(oracle_python),
                "--fault-contracts",
                "--output",
                str(result_path),
            ]
            try:
                process = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=max(args.case_timeout, 1800),
                    check=False,
                )
                exit_code = process.returncode
                stdout = process.stdout
                stderr = process.stderr
            except subprocess.TimeoutExpired as error:
                exit_code = None
                stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
                stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
                stderr += f"\nparity matrix exceeded {max(args.case_timeout, 1800)} seconds"
            (attempt_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (attempt_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            attempt: dict[str, Any] = {
                "attempt": attempt_index + 1,
                "artifact": str(result_path.relative_to(ROOT)),
                "runner_exit_code": exit_code,
                "stdout_artifact": str((attempt_dir / "stdout.log").relative_to(ROOT)),
                "stderr_artifact": str((attempt_dir / "stderr.log").relative_to(ROOT)),
            }
            result = None
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                attempt_profiles = sorted(attempt_dir.glob("*.profraw"))
                attempt.update({
                    "status": result.get("status"),
                    "summary": result.get("summary"),
                    "run_id": result.get("run", {}).get("run_id"),
                    "sha256": digest_file(result_path),
                    "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in attempt_profiles],
                    "profile_data_receipts": profile_receipts(attempt_profiles),
                })
            else:
                attempt.update({
                    "status": "infrastructure_failed",
                    "error": f"parity runner returned {exit_code} without a result file",
                })
            attempts.append(attempt)
            final_result = result
            final_result_path = result_path
            final_exit_code = exit_code

            if (
                result is not None
                and result.get("status") == "completed"
                and exit_code == 0
                and result.get("summary", {}).get("passed") == result.get("summary", {}).get("selected")
            ):
                break
            summary = result.get("summary", {}) if result is not None else {}
            infrastructure_only = (
                result is None
                or (
                    result.get("status") == "failed"
                    and summary.get("failed", 0) == 0
                    and summary.get("infrastructure_failed", 0) > 0
                )
            )
            if not infrastructure_only or attempt_index >= args.matrix_infra_retries:
                break

        final_summary = final_result.get("summary") if final_result is not None else None
        final_status = final_result.get("status") if final_result is not None else "infrastructure_failed"
        final_passed = (
            final_status == "completed"
            and final_exit_code == 0
            and final_summary is not None
            and final_summary.get("passed") == final_summary.get("selected")
        )
        matrix_runs.append({
            "run": repeat,
            "status": "completed" if final_passed else "failed",
            "summary": final_summary,
            "run_id": final_result.get("run", {}).get("run_id") if final_result is not None else None,
            "artifact": str(final_result_path.relative_to(ROOT)) if final_result_path is not None else None,
            "sha256": digest_file(final_result_path) if final_result_path is not None and final_result_path.is_file() else None,
            "stdout_artifact": attempts[-1]["stdout_artifact"],
            "stderr_artifact": attempts[-1]["stderr_artifact"],
            "profile_data_artifacts": attempts[-1].get("profile_data_artifacts", []),
            "profile_data_receipts": attempts[-1].get("profile_data_receipts", []),
            "runner_exit_code": final_exit_code,
            "attempts": attempts,
            "transient_infrastructure_failures": sum(
                item.get("status") == "infrastructure_failed"
                or (
                    item.get("status") == "failed"
                    and item.get("summary", {}).get("failed", 0) == 0
                    and item.get("summary", {}).get("infrastructure_failed", 0) > 0
                )
                for item in attempts[:-1]
            ),
        })
        print(
            f"[matrix {repeat}/{args.matrix_repeats}] {matrix_runs[-1]['status']} "
            f"{(final_summary or {}).get('passed', 0)}/{(final_summary or {}).get('selected', 0)} "
            f"(transient infrastructure failures: {matrix_runs[-1]['transient_infrastructure_failures']})",
            flush=True,
        )

    native_matrix_runs: list[dict[str, Any]] = []
    for repeat in range(1, args.matrix_repeats + 1):
        repeat_dir = native_repeat_root / f"run-{repeat}"
        repeat_dir.mkdir(parents=True, exist_ok=False)
        stdout_path = repeat_dir / "stdout.log"
        stderr_path = repeat_dir / "stderr.log"
        result_path = repeat_dir / "native-result.json"
        profile_pattern = repeat_dir / "%p-%m.profraw"
        env = os.environ.copy()
        env["LLVM_PROFILE_FILE"] = str(profile_pattern)
        try:
            process = subprocess.run(
                [str(native_runner), str(NATIVE_MANIFEST)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=max(args.case_timeout, 1800),
                check=False,
            )
            exit_code: int | None = process.returncode
            stdout, stderr = process.stdout, process.stderr
        except subprocess.TimeoutExpired as error:
            exit_code = None
            stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
            stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
            stderr += f"\nnative matrix exceeded {max(args.case_timeout, 1800)} seconds"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        expected_ids = [case["id"] for case in all_native_cases]
        observed_ids = native_pass_ids(stdout)
        expected_fault_points = [
            case["fault"]["point"] for case in all_native_cases
            if case.get("verification", "target-contract") == "fault-contract"
        ]
        observed_fault_points = [
            line.removeprefix("FAULT_CONSUMED ") for line in stdout.splitlines()
            if line.startswith("FAULT_CONSUMED ")
        ]
        faults_consumed = sorted(observed_fault_points) == sorted(expected_fault_points)
        profiles = sorted(repeat_dir.glob("*.profraw"))
        observed_set = set(observed_ids)
        passed_ids = observed_set & set(expected_ids)
        if not faults_consumed:
            passed_ids -= {
                case["id"] for case in all_native_cases
                if case.get("verification", "target-contract") == "fault-contract"
            }
        passed_count = len(passed_ids)
        failed_count = len(set(expected_ids) - passed_ids)
        not_run_count = len(set(expected_ids) - observed_set)
        # The runner emits shared-server cases before isolated cases, so its
        # pass lines are not guaranteed to follow manifest order. Check an
        # exact multiset match to reject omissions and duplicates without
        # making ordering part of the contract.
        case_ids_match = sorted(observed_ids) == sorted(expected_ids)
        passed = exit_code == 0 and case_ids_match and profiles and faults_consumed
        repeat_result = {
            "schema": "uvicorn-rs-native-matrix-result/3",
            "run": repeat,
            "status": "completed" if passed else "failed",
            "runner_exit_code": exit_code,
            "selected": len(expected_ids),
            "passed": passed_count,
            "failed": failed_count,
            "not_run": not_run_count,
            "expected_case_ids": expected_ids,
            "observed_pass_ids": observed_ids,
            "expected_fault_points": expected_fault_points,
            "observed_fault_points": observed_fault_points,
            "stdout_artifact": str(stdout_path.relative_to(ROOT)),
            "stderr_artifact": str(stderr_path.relative_to(ROOT)),
            "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in profiles],
            "profile_data_receipts": profile_receipts(profiles),
        }
        write_json(result_path, repeat_result)
        native_matrix_runs.append({
            **repeat_result,
            "artifact": str(result_path.relative_to(ROOT)),
            "sha256": digest_file(result_path),
            "attempts": [{
                "attempt": 1,
                "status": repeat_result["status"],
                "runner_exit_code": exit_code,
                "artifact": str(result_path.relative_to(ROOT)),
                "sha256": digest_file(result_path),
                "stdout_artifact": str(stdout_path.relative_to(ROOT)),
                "stderr_artifact": str(stderr_path.relative_to(ROOT)),
                "profile_data_artifacts": repeat_result["profile_data_artifacts"],
                "profile_data_receipts": repeat_result["profile_data_receipts"],
            }],
            "transient_infrastructure_failures": 0,
        })
        print(
            f"[native matrix {repeat}/{args.matrix_repeats}] "
            f"{native_matrix_runs[-1]['status']} {len(set(observed_ids) & set(expected_ids))}/{len(expected_ids)}",
            flush=True,
        )

    combined_profdata = artifacts_root / "per-case-union.profdata"
    run_checked([
        str(llvm_profdata), "merge", "-sparse", "-failure-mode=all", "-o",
        str(combined_profdata), *map(str, all_case_profiles),
    ], timeout=180)
    aggregate_llvm = llvm_export(
        llvm_cov, [extension, native_runner_snapshot], combined_profdata, timeout=180
    )
    aggregate_regions, aggregate_summaries, canonical_functions = source_region_map(
        aggregate_llvm, source["sha256"], set(PRODUCTION_SOURCE_SET)
    )
    aggregate_lcov_lines = llvm_export_lcov(
        llvm_cov,
        [extension, native_runner_snapshot],
        combined_profdata,
        set(PRODUCTION_SOURCE_SET),
        timeout=180,
    )
    physical_line_summary, physical_line_evidence = physical_line_summaries(
        aggregate_lcov_lines, aggregate_regions
    )

    all_case_regions = {
        region_id: {**region, "hit_by": []}
        for region_id, region in aggregate_regions.items()
    }
    asgi_receipts_by_id = {receipt["case_id"]: receipt for receipt in case_receipts}
    native_receipts_by_id = {receipt["case_id"]: receipt for receipt in native_case_receipts}
    attribution_cases: list[tuple[str, dict[str, Any], Path]] = []
    for case in cases:
        receipt = asgi_receipts_by_id[case["case_id"]]
        if not receipt.get("profile_data_artifacts"):
            continue
        merged = case_results_root / case_slug(case["case_id"]) / "target.profdata"
        if not merged.is_file() or merged.stat().st_size == 0:
            raise CoverageError(f"merged ASGI case profile is missing: {case['case_id']}")
        attribution_cases.append(("asgi", receipt, merged))
    for case in native_cases:
        receipt = native_receipts_by_id[case["id"]]
        if not receipt.get("profile_data_artifacts"):
            continue
        merged_name = receipt.get("merged_profile_artifact")
        if not isinstance(merged_name, str):
            raise CoverageError(f"merged native case profile is missing: {case['id']}")
        merged = ROOT / merged_name
        if not merged.is_file() or merged.stat().st_size == 0:
            raise CoverageError(f"merged native case profile is missing: {case['id']}")
        attribution_cases.append(("native", receipt, merged))

    for attribution_index, (namespace, receipt, profile_data) in enumerate(attribution_cases, 1):
        case_llvm = llvm_export(llvm_cov, [extension, native_runner_snapshot], profile_data)
        case_regions, _, _ = source_region_map(
            case_llvm,
            source["sha256"],
            set(PRODUCTION_SOURCE_SET),
            canonical_functions=canonical_functions,
        )
        if set(case_regions) != set(aggregate_regions):
            raise CoverageError(f"case LLVM region identities differ: {receipt['case_key']}")
        hit_region_ids = sorted(
            region_id for region_id, region in case_regions.items() if region["covered"]
        )
        receipt["hit_region_ids"] = hit_region_ids
        receipt["covered_regions"] = len(hit_region_ids)
        for region_id in hit_region_ids:
            all_case_regions[region_id]["hit_by"].append(receipt["case_key"])
        print(
            f"[attribution {attribution_index}/{len(attribution_cases)}] "
            f"{namespace} {receipt['case_id']} ({len(hit_region_ids)} regions)",
            flush=True,
        )

    attributed_union = {
        region_id for region_id, region in all_case_regions.items() if region.get("hit_by")
    }
    aggregate_hits = {
        region_id for region_id, region in aggregate_regions.items() if region["covered"]
    }
    attribution_matches_union = attributed_union == aggregate_hits
    if not attribution_matches_union:
        missing_attribution = sorted(aggregate_hits - attributed_union)
        unexpected_attribution = sorted(attributed_union - aggregate_hits)
        raise CoverageError(
            "per-case attribution does not equal the profile union: "
            f"unattributed={len(missing_attribution)}, unexpected={len(unexpected_attribution)}"
        )
    for region in all_case_regions.values():
        region["hit_by"] = sorted(set(region["hit_by"]))
        region["covered"] = bool(region["hit_by"])
    case_index = sorted(receipt["case_key"] for _, receipt, _ in attribution_cases)
    case_index_by_key = {case_key: index for index, case_key in enumerate(case_index)}

    source_region_summaries = {
        path: {
            "regions": 0,
            "regions_total": 0,
            **physical_line_summary[path],
        }
        for path in PRODUCTION_SOURCE_SET
    }
    for region in aggregate_regions.values():
        summary = source_region_summaries[region["file"]]
        summary["regions_total"] += 1
        summary["regions"] += int(region["covered"])
    normalized_aggregate_summaries = {
        path: {
            **summary,
            **source_region_summaries[path],
        }
        for path, summary in aggregate_summaries.items()
    }

    llvm_source_summary = {
        metric: sum(aggregate_summaries[path][metric] for path in EXECUTABLE_SOURCE_SET)
        for metric in ("regions", "lines")
    } | {
        f"{metric}_total": sum(
            aggregate_summaries[path][f"{metric}_total"]
            for path in EXECUTABLE_SOURCE_SET
        )
        for metric in ("regions", "lines")
    }
    source_region_summary = {
        "regions": sum(source_region_summaries[path]["regions"] for path in EXECUTABLE_SOURCE_SET),
        "regions_total": sum(
            source_region_summaries[path]["regions_total"] for path in EXECUTABLE_SOURCE_SET
        ),
        "lines": sum(source_region_summaries[path]["lines"] for path in EXECUTABLE_SOURCE_SET),
        "lines_total": sum(
            source_region_summaries[path]["lines_total"] for path in EXECUTABLE_SOURCE_SET
        ),
    }
    if source_region_summary["regions"] != len(aggregate_hits):
        raise CoverageError("per-file source region summaries differ from the attributed union")
    complete_case_matrix = (
        len(case_receipts) == len(cases)
        and len(native_case_receipts) == len(native_cases)
        and all(item["status"] == "passed" for item in case_receipts + native_case_receipts)
        and all(len(item.get("attempts", [])) == 1 for item in case_receipts + native_case_receipts)
        and all(item.get("transient_infrastructure_failures", 0) == 0 for item in case_receipts + native_case_receipts)
    )
    oracle_case_receipts = [item for item in case_receipts if item["verification"] == "oracle-parity"]
    fault_case_receipts = [item for item in case_receipts if item["verification"] == "fault-contract"]
    native_fault_case_receipts = [
        item for item in native_case_receipts if item["verification"] == "fault-contract"
    ]
    complete_asgi_repeats = (
        args.matrix_repeats == 3
        and len(matrix_runs) == args.matrix_repeats
        and all(
            item.get("status") == "completed"
            and item.get("runner_exit_code") == 0
            and item.get("summary", {}).get("passed") == item.get("summary", {}).get("selected")
            and item.get("transient_infrastructure_failures") == 0
            and len(item.get("attempts", [])) == 1
            for item in matrix_runs
        )
    )
    expected_native_ids = {case["id"] for case in all_native_cases}
    complete_native_repeats = (
        args.matrix_repeats == 3
        and len(native_matrix_runs) == args.matrix_repeats
        and all(
            item.get("status") == "completed"
            and item.get("runner_exit_code") == 0
            and item.get("selected") == len(expected_native_ids)
            and item.get("passed") == len(expected_native_ids)
            and item.get("failed") == 0
            and item.get("not_run") == 0
            and set(item.get("observed_pass_ids", [])) == expected_native_ids
            and len(item.get("observed_pass_ids", [])) == len(expected_native_ids)
            for item in native_matrix_runs
        )
    )
    complete_repeats = complete_asgi_repeats and complete_native_repeats
    full_case_set = len(cases) == len(all_cases) and len(native_cases) == len(all_native_cases)
    all_regions_hit = len(aggregate_hits) == len(aggregate_regions)
    all_lines_hit = source_region_summary["lines"] == source_region_summary["lines_total"]
    coverage_gate_passed = (
        full_case_set
        and complete_case_matrix
        and args.matrix_repeats == 3
        and complete_repeats
        and all_regions_hit
        and all_lines_hit
    )
    uncovered = []
    for region_id, region in aggregate_regions.items():
        if region_id in aggregate_hits:
            continue
        uncovered.append({
            "region_id": region_id,
            "file": region["file"],
            "function_symbols": region["function_symbols"],
            "function_group": region["function_group"],
            "start": region["start"],
            "end": region["end"],
            "kind": region["kind"],
            "hit_by": [],
            "status": "uncovered",
            "candidate_case_family": None,
            "next_action": "query Coverage-MCP for this source span and add an input or injected fault contract",
        })
    region_rows = []
    for region_id, region in sorted(aggregate_regions.items()):
        region_rows.append({
            **region,
            "hit_by": all_case_regions[region_id]["hit_by"],
        })

    status = "complete" if complete_case_matrix and complete_repeats else "incomplete"
    all_case_receipts = case_receipts + native_case_receipts
    all_source_paths = list(PRODUCTION_SOURCE_SET)
    source_file_rows = [
        {
            "path": path,
            "classification": "no-executable-counters" if path in NO_COUNTER_SOURCE_SET else "executable",
            "summary": normalized_aggregate_summaries[path],
            "llvm_summary": aggregate_summaries[path],
        }
        for path in all_source_paths
    ]
    coverage_extension = {
        "schema": RESULT_SCHEMA,
        "status": status,
        "run": {
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": utc_now(),
            "source": source,
            "build": build_identity,
            "runner": {
                "path": str(Path(__file__).resolve().relative_to(ROOT)),
                "sha256": digest_file(Path(__file__).resolve()),
            },
            "artifacts_root": str(artifacts_root.relative_to(ROOT)),
        },
        "matrix": {
            "scope": "complete" if full_case_set else "selected-subset",
            "manifest_case_count": len(all_cases) + len(all_native_cases),
            "asgi_manifest_case_count": len(all_cases),
            "native_manifest_case_count": len(all_native_cases),
            "selected": len(cases) + len(native_cases),
            "asgi_selected": len(cases),
            "native_selected": len(native_cases),
            "executed": len(all_case_receipts),
            "passed": sum(item["status"] == "passed" for item in all_case_receipts),
            "failed": sum(item["status"] == "failed" for item in all_case_receipts),
            "infrastructure_failed": sum(item["status"] == "infrastructure_failed" for item in all_case_receipts),
            "transient_infrastructure_failures": sum(
                item.get("transient_infrastructure_failures", 0) for item in all_case_receipts
            ) + sum(item.get("transient_infrastructure_failures", 0) for item in matrix_runs)
            + sum(item.get("transient_infrastructure_failures", 0) for item in native_matrix_runs),
            "oracle_parity": {
                "selected": len(oracle_case_receipts),
                "passed": sum(item["status"] == "passed" for item in oracle_case_receipts),
                "failed": sum(item["status"] == "failed" for item in oracle_case_receipts),
            },
            "fault_contracts": {
                "selected": len(fault_case_receipts) + len(native_fault_case_receipts),
                "passed": sum(item["status"] == "passed" for item in fault_case_receipts)
                + sum(item["status"] == "passed" for item in native_fault_case_receipts),
                "failed": sum(item["status"] == "failed" for item in fault_case_receipts)
                + sum(item["status"] == "failed" for item in native_fault_case_receipts),
            },
            "verification_runs": matrix_runs,
            "native_verification_runs": native_matrix_runs,
            "verification_runs_required": 3,
            "case_attribution_complete": len(attribution_cases) == len(cases) + len(native_cases),
            # Region rows retain the complete hit_by relation. Repeating the
            # inverse SHA256 lists in every case makes a full report exceed
            # Coverage-MCP's size limit without adding evidence.
            "case_results": [
                {key: value for key, value in item.items() if key != "hit_region_ids"}
                for item in case_receipts
            ],
            "native_case_results": [
                {key: value for key, value in item.items() if key != "hit_region_ids"}
                for item in native_case_receipts
            ],
        },
        "coverage": {
            "gate": "passed" if coverage_gate_passed else "incomplete",
            "source_set": all_source_paths,
            "executable_source_set": list(EXECUTABLE_SOURCE_SET),
            "coverage_support_source_set": list(COVERAGE_SUPPORT_SOURCE_SET),
            "source_files": source_file_rows,
            "llvm_normalization": {
                "regions": "source-span union across Rust function instantiations",
                "lines": "physical source-line union from LLVM LCOV DA records, validated against executable region spans",
                "function_counters": "raw LLVM instantiation counters retained",
            },
            "line_validation": {
                "source": "llvm-cov export --format=lcov DA records",
                "span_coordinates": "one-based LLVM source columns with an exclusive end coordinate",
                "physical_line_sets_match": True,
                "covered_line_sets_match": True,
                "source_files": physical_line_evidence,
            },
            "summary": {
                "regions": {
                    "covered": int(source_region_summary["regions"]),
                    "total": int(source_region_summary["regions_total"]),
                    "missing": int(source_region_summary["regions_total"] - source_region_summary["regions"]),
                },
                "lines": {
                    "covered": int(source_region_summary["lines"]),
                    "total": int(source_region_summary["lines_total"]),
                    "missing": int(source_region_summary["lines_total"] - source_region_summary["lines"]),
                },
            },
            "llvm_summary": {
                metric: {
                    "covered": int(llvm_source_summary[metric]),
                    "total": int(llvm_source_summary[f"{metric}_total"]),
                    "missing": int(llvm_source_summary[f"{metric}_total"] - llvm_source_summary[metric]),
                }
                for metric in ("regions", "lines")
            },
            "regions": [
                {
                    **region,
                    "hit_by": [case_index_by_key[case_key] for case_key in region["hit_by"]],
                }
                for region in region_rows
            ],
            "uncovered_regions": uncovered,
            "attribution": {
                "algorithm": (
                    "LLVM instantiation groups use a deterministic maximum-summary representative for the denominator; "
                    "hits are unioned by exact source span across monomorphizations; region IDs include source hash, "
                    "file, group start, representative function symbol, source span, and kind"
                ),
                "aggregate_profile_data_sha256": digest_file(combined_profdata),
                "per_case_profiles": len(attribution_cases),
                "profile_union_matches_attribution": attribution_matches_union,
                "case_region_ids_verified": True,
                "case_region_lookup": "coverage.regions[].hit_by -> coverage.attribution.case_index",
                "case_index": case_index,
            },
            "coverage_mcp": pending_coverage_mcp_request(
                str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output)
            ),
        },
        "artifacts": {
            "aggregate_profile_data": str(combined_profdata.relative_to(ROOT)),
            "per_case_profiles_root": str(profile_root.relative_to(ROOT)),
            "native_per_case_profiles_root": str(native_profile_root.relative_to(ROOT)),
            "native_input_manifests_root": str(native_input_root.relative_to(ROOT)),
            "matrix_runs_root": str(repeat_root.relative_to(ROOT)),
            "native_matrix_runs_root": str(native_repeat_root.relative_to(ROOT)),
        },
    }
    if source_identity(manifest, input_paths, native_manifest)["sha256"] != source["sha256"]:
        raise CoverageError("source or parity inputs changed while the coverage run was in progress")
    restore_native_runner(native_runner, native_runner_snapshot, build_identity["native_runner_sha256"])
    native_runner_snapshot.unlink(missing_ok=True)
    aggregate_llvm = filter_llvm_export_sources(aggregate_llvm, set(PRODUCTION_SOURCE_SET))
    normalize_llvm_source_summaries(
        aggregate_llvm,
        {path: normalized_aggregate_summaries[path] for path in PRODUCTION_SOURCE_SET},
    )
    aggregate_llvm[LLVM_EXTENSION_KEY] = coverage_extension
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the complete per-region `hit_by` relation using case-index integers,
    # then serialize compactly so Coverage-MCP can parse large reports.
    report_bytes = (json.dumps(aggregate_llvm, separators=(",", ":"), sort_keys=True) + "\n").encode()
    output.write_bytes(report_bytes)
    source_hashes = {
        path: source["file_sha256"][path]
        for path in PRODUCTION_SOURCE_SET
    }
    receipt = {
        "report_sha256": digest_bytes(report_bytes),
        "source_hashes": source_hashes,
        "build_id": digest_json(build_identity),
        "scope": "full" if full_case_set else "selected_tests",
        # A selected-case measurement is a successful test batch when every
        # selected case passed. Full-matrix repeat requirements gate complete
        # suite evidence, not the result of an incremental batch.
        "test_status": "passed"
        if complete_case_matrix and (not full_case_set or complete_repeats)
        else "failed",
        "recorded_revision": source["revision"],
    }
    output.with_name(output.name + ".context.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": status,
        "report": str(output),
        "matrix": coverage_extension["matrix"] | {"case_results": f"{len(case_receipts)} case rows"},
        "coverage": coverage_extension["coverage"]["summary"],
        "coverage_gate": coverage_extension["coverage"]["gate"],
        "uncovered_regions": len(uncovered),
        "attribution_matches_union": attribution_matches_union,
        "source_sha256": source["sha256"],
        "native_extension_sha256": build_identity["native_extension_sha256"],
    }, indent=2))
    selected_batch_passed = (
        complete_case_matrix
        and (not full_case_set or complete_repeats)
        and (not full_case_set or coverage_gate_passed)
    )
    return 0 if selected_batch_passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CoverageError, run_parity.ParityError, subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        print(f"unified coverage failure: {error}", file=sys.stderr)
        raise SystemExit(2)
