#!/usr/bin/env python3
"""Run ASGI parity cases with per-case LLVM attribution and one union report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any
import uuid

import run_parity


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_parity.py"
BUILD_SCRIPT = ROOT / "scripts" / "build_coverage_extension.py"
RESULT_SCHEMA = "uvicorn-rs-coverage/unified@1"
LLVM_EXTENSION_KEY = "uvicorn_rs_unified"
SOURCE_PATHS = ("src", "Cargo.toml", "Cargo.lock")
REPORT_INPUT_PATHS = (
    "tests/parity/manifest.json",
    "tests/parity/app.py",
    "tests/parity/startup_probe.py",
    "tests/parity/server_api_probe.py",
    "tools/http3-probe/Cargo.toml",
    "tools/http3-probe/Cargo.lock",
    "tools/http3-probe/src/bin/parity-http3.rs",
    "scripts/run_parity.py",
    "scripts/build_coverage_extension.py",
    "scripts/run_unified_coverage.py",
)


class CoverageError(RuntimeError):
    """Coverage evidence is missing, inconsistent, or incompatible."""


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


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


def source_identity(manifest: dict[str, Any], input_paths: list[Path]) -> dict[str, Any]:
    selected: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        if path.is_dir():
            for source in sorted(path.rglob("*.rs")):
                selected[str(source.relative_to(ROOT))] = digest_file(source)
        elif path.is_file():
            selected[relative] = digest_file(path)
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
    }


def tool_path(environment_name: str, name: str, sysroot: Path, host: str) -> Path:
    configured = os.environ.get(environment_name)
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            return path
        raise CoverageError(f"{environment_name} does not name a file: {path}")
    suffix = ".exe" if os.name == "nt" else ""
    candidates = [
        sysroot / "lib" / "rustlib" / host / "bin" / f"{name}{suffix}",
        sysroot / "bin" / f"{name}{suffix}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise CoverageError(f"could not locate {name} for rustc host {host}; set {environment_name}")


def llvm_tools() -> tuple[Path, Path, dict[str, str]]:
    version = run_checked(["rustc", "-vV"])
    host = next((line.split(": ", 1)[1] for line in version.splitlines() if line.startswith("host: ")), None)
    if host is None:
        raise CoverageError("rustc -vV did not report its host triple")
    sysroot = Path(run_checked(["rustc", "--print", "sysroot"]).strip())
    llvm_cov = tool_path("LLVM_COV", "llvm-cov", sysroot, host)
    llvm_profdata = tool_path("LLVM_PROFDATA", "llvm-profdata", sysroot, host)
    versions = {
        "rustc": version.splitlines()[0],
        "llvm_cov": run_checked([str(llvm_cov), "--version"]).splitlines()[0],
        "llvm_profdata": run_checked([str(llvm_profdata), "--version"]).splitlines()[0],
        "cargo_llvm_cov": run_checked(["cargo", "llvm-cov", "--version"]).strip(),
    }
    return llvm_cov, llvm_profdata, versions


def case_slug(case_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_id).strip(".-")
    return f"{safe[:96]}-{hashlib.sha256(case_id.encode()).hexdigest()[:10]}"


def llvm_export(
    llvm_cov: Path,
    binary: Path,
    profile_data: Path,
    *,
    timeout: int = 120,
) -> dict[str, Any]:
    ignored_dependencies = r".*/\.cargo/registry/.*"
    output = run_checked(
        [
            str(llvm_cov),
            "export",
            "--format=text",
            f"--instr-profile={profile_data}",
            f"--ignore-filename-regex={ignored_dependencies}",
            str(binary),
        ],
        timeout=timeout,
    )
    try:
        report = json.loads(output)
    except json.JSONDecodeError as error:
        raise CoverageError(f"llvm-cov export returned invalid JSON: {error}") from error
    if report.get("type") != "llvm.coverage.json.export" or not report.get("data"):
        raise CoverageError("llvm-cov export returned an unsupported report")
    return report


def source_region_map(
    llvm_report: dict[str, Any],
    source_digest: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, int]]]:
    data = llvm_report["data"][0]
    files = {
        str(Path(item["filename"]).resolve()): item
        for item in data["files"]
        if Path(item["filename"]).resolve().is_relative_to(ROOT.resolve())
    }
    if not files:
        raise CoverageError("LLVM export contains no files beneath the repository")

    regions: dict[str, dict[str, Any]] = {}
    file_summaries: dict[str, dict[str, int]] = {}
    for absolute_path, file_data in files.items():
        relative_path = str(Path(absolute_path).relative_to(ROOT.resolve()))
        summary = file_data["summary"]
        file_summaries[relative_path] = {
            metric: int(summary[metric]["covered"])
            for metric in ("regions", "lines")
        } | {
            f"{metric}_total": int(summary[metric]["count"])
            for metric in ("regions", "lines")
        }

    for function in data["functions"]:
        for raw_region in function["regions"]:
            start_line, start_column, end_line, end_column, count, file_index, _, kind = raw_region
            absolute_path = str(Path(function["filenames"][file_index]).resolve())
            if absolute_path not in files:
                continue
            relative_path = str(Path(absolute_path).relative_to(ROOT.resolve()))
            identity = [
                source_digest,
                relative_path,
                int(start_line),
                int(start_column),
                int(end_line),
                int(end_column),
                int(kind),
            ]
            region_id = digest_json(identity)
            item = regions.setdefault(
                region_id,
                {
                    "id": region_id,
                    "file": relative_path,
                    "start": {"line": int(start_line), "column": int(start_column)},
                    "end": {"line": int(end_line), "column": int(end_column)},
                    "kind": int(kind),
                    "function_symbols": [],
                    "covered": False,
                },
            )
            symbol = function["name"]
            if symbol not in item["function_symbols"]:
                item["function_symbols"].append(symbol)
            if int(count) > 0:
                item["covered"] = True

    for relative_path, summary in file_summaries.items():
        expected_regions = summary["regions_total"]
        actual_regions = sum(region["file"] == relative_path for region in regions.values())
        if actual_regions != expected_regions:
            raise CoverageError(
                f"LLVM region identities for {relative_path} differ from its summary: "
                f"{actual_regions} != {expected_regions}"
            )
    return regions, file_summaries


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
    parser.add_argument("--case-id", action="append", help="attribute only the named case; repeat to select a subset")
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
    if args.matrix_repeats < 0:
        parser.error("--matrix-repeats cannot be negative")
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
    case_results_root.mkdir(parents=True, exist_ok=False)
    profile_root.mkdir(parents=True, exist_ok=False)
    repeat_root.mkdir(parents=True, exist_ok=False)

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
    if args.case_id:
        requested = set(args.case_id)
        known = {case["case_id"] for case in all_cases}
        unknown = sorted(requested - known)
        if unknown:
            parser.error(f"unknown case ID(s): {', '.join(unknown)}")
        cases = [case for case in all_cases if case["case_id"] in requested]
    else:
        cases = all_cases
    if not cases:
        parser.error("at least one case must be selected")
    if args.case_id and args.matrix_repeats:
        parser.error("--matrix-repeats requires the complete input matrix; set it to 0 for a selected subset")

    source = source_identity(manifest, input_paths)
    llvm_cov, llvm_profdata, tool_versions = llvm_tools()
    identity_profile_dir = artifacts_root / "identity-profile"
    identity_profile_dir.mkdir(parents=True, exist_ok=False)
    os.environ["LLVM_PROFILE_FILE"] = str(identity_profile_dir / "%p-%m.profraw")
    extension = Path(run_parity.runtime_identity(manifest)[1]["native_extension"]["path"])
    if not extension.is_absolute():
        extension = ROOT / extension
    if not extension.is_file():
        raise CoverageError(f"instrumented extension does not exist: {extension}")
    build_identity = {
        "native_extension": str(extension.relative_to(ROOT)),
        "native_extension_sha256": digest_file(extension),
        "cargo_lock_sha256": digest_file(ROOT / "Cargo.lock"),
        "tools": tool_versions,
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }

    case_receipts: list[dict[str, Any]] = []
    all_case_regions: dict[str, dict[str, Any]] | None = None
    all_case_summaries: dict[str, dict[str, int]] | None = None
    all_case_profiles: list[Path] = []
    immutable_identity: tuple[str, str, str] | None = None
    for index, case in enumerate(cases, 1):
        slug = case_slug(case["case_id"])
        case_dir = case_results_root / slug
        profile_dir = profile_root / slug
        case_dir.mkdir(parents=True, exist_ok=False)
        attempts: list[dict[str, Any]] = []
        all_raw_profiles: list[Path] = []
        process: subprocess.CompletedProcess[str] | None = None
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
                "--case-id",
                case["case_id"],
                "--coverage-profile-dir",
                str(attempt_profile_dir),
                "--output",
                str(result_path),
            ]
            if case.get("verification") == "fault-contract":
                command.append("--fault-contracts")
            process = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=args.case_timeout,
                check=False,
            )
            (attempt_dir / "stdout.log").write_text(process.stdout, encoding="utf-8")
            (attempt_dir / "stderr.log").write_text(process.stderr, encoding="utf-8")
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
                or process.returncode not in (0, 1)
                or (attempt_result is not None and attempt_result.get("infrastructure_errors"))
            ):
                attempt_status = "infrastructure_failed"
            attempts.append({
                "attempt": attempt_index + 1,
                "status": attempt_status,
                "runner_exit_code": process.returncode,
                "result_artifact": (
                    str(result_path.relative_to(ROOT)) if result_path.is_file() else None
                ),
                "result_sha256": digest_file(result_path) if result_path.is_file() else None,
                "profile_data_artifacts": [
                    str(path.relative_to(ROOT)) for path in attempt_profiles
                ],
            })
            result = attempt_result
            case_result = attempt_case_result
            status = attempt_status
            error = (
                attempt_case_result.get("error", {}).get("message")
                if attempt_case_result is not None
                else f"parity runner returned {process.returncode} without a result for the selected case"
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

        if result_path is None or process is None:
            case_receipts.append({
                "case_id": case["case_id"],
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
                "profile": case["profile"],
                "operation": case["operation"],
                "verification": case.get("verification", "oracle-parity"),
                "fault": case.get("fault"),
                "status": "infrastructure_failed",
                "error": "instrumented target process produced no LLVM profile",
                "result_artifact": str(result_path.relative_to(ROOT)),
                "hit_region_ids": [],
                "attempts": attempts,
            })
            print(f"[{index}/{len(cases)}] ERROR {case['case_id']}: no target profile", flush=True)
            continue

        case_profdata = case_dir / "target.profdata"
        run_checked([
            str(llvm_profdata), "merge", "-sparse", "-failure-mode=all", "-o",
            str(case_profdata), *map(str, all_raw_profiles),
        ], timeout=120)
        llvm_case = llvm_export(llvm_cov, extension, case_profdata)
        region_map, summaries = source_region_map(llvm_case, source["sha256"])
        if all_case_regions is None:
            all_case_regions = region_map
            all_case_summaries = summaries
        elif set(region_map) != set(all_case_regions):
            raise CoverageError(f"LLVM region identities changed while measuring case {case['case_id']}")
        elif {
            path: (summary["regions_total"], summary["lines_total"])
            for path, summary in summaries.items()
        } != {
            path: (summary["regions_total"], summary["lines_total"])
            for path, summary in all_case_summaries.items()
        }:
            raise CoverageError(f"LLVM source denominators changed while measuring case {case['case_id']}")

        hit_region_ids = sorted(region_id for region_id, item in region_map.items() if item["covered"])
        for region_id in hit_region_ids:
            all_case_regions[region_id]["hit_by"] = sorted(set(all_case_regions[region_id].get("hit_by", [])) | {case["case_id"]})
            all_case_regions[region_id]["covered"] = True
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
            "profile": case["profile"],
            "operation": case["operation"],
            "requirements": case["covers"],
            "verification": case.get("verification", "oracle-parity"),
            "fault": case.get("fault"),
            "status": status if process.returncode in (0, 1) else "infrastructure_failed",
            "error": error or (None if process.returncode in (0, 1) else f"runner exit status {process.returncode}"),
            "observations": {
                "oracle": case_result.get("oracle_observation") if case_result else None,
                "target": case_result.get("target_observation") if case_result else None,
                "difference": case_result.get("difference") if case_result else None,
            },
            "result_artifact": str(result_path.relative_to(ROOT)),
            "result_sha256": digest_file(result_path),
            "run_id": run_meta.get("run_id"),
            "target_extension_sha256": run_identity[0],
            "profile_data_artifacts": [str(path.relative_to(ROOT)) for path in all_raw_profiles],
            "hit_region_ids": hit_region_ids,
            "covered_regions": len(hit_region_ids),
            "attempts": attempts,
            "transient_infrastructure_failures": sum(
                attempt["status"] == "infrastructure_failed" for attempt in attempts[:-1]
            ),
        })
        print(f"[{index}/{len(cases)}] {status.upper()} {case['case_id']} ({len(hit_region_ids)} regions)", flush=True)

    if all_case_regions is None or all_case_summaries is None or not all_case_profiles:
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
            command = [sys.executable, str(RUNNER), "--fault-contracts", "--output", str(result_path)]
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
            }
            result = None
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                attempt.update({
                    "status": result.get("status"),
                    "summary": result.get("summary"),
                    "run_id": result.get("run", {}).get("run_id"),
                    "sha256": digest_file(result_path),
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
            "status": "completed" if final_passed else final_status,
            "summary": final_summary,
            "run_id": final_result.get("run", {}).get("run_id") if final_result is not None else None,
            "artifact": str(final_result_path.relative_to(ROOT)) if final_result_path is not None else None,
            "sha256": digest_file(final_result_path) if final_result_path is not None and final_result_path.is_file() else None,
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

    combined_profdata = artifacts_root / "per-case-union.profdata"
    run_checked([
        str(llvm_profdata), "merge", "-sparse", "-failure-mode=all", "-o",
        str(combined_profdata), *map(str, all_case_profiles),
    ], timeout=180)
    aggregate_llvm = llvm_export(llvm_cov, extension, combined_profdata, timeout=180)
    aggregate_regions, aggregate_summaries = source_region_map(aggregate_llvm, source["sha256"])
    if set(aggregate_regions) != set(all_case_regions):
        raise CoverageError("aggregate LLVM region identities differ from per-case region identities")

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

    for path, summary in aggregate_summaries.items():
        if path == "src/lib.rs":
            source_region_summary = summary
            break
    else:
        raise CoverageError("aggregate LLVM report does not contain src/lib.rs")

    complete_case_matrix = len(case_receipts) == len(cases) and all(
        item["status"] == "passed" for item in case_receipts
    )
    oracle_case_receipts = [item for item in case_receipts if item["verification"] == "oracle-parity"]
    fault_case_receipts = [item for item in case_receipts if item["verification"] == "fault-contract"]
    complete_repeats = (
        args.matrix_repeats >= 3
        and len(matrix_runs) == args.matrix_repeats
        and all(
            item.get("status") == "completed"
            and item.get("runner_exit_code") == 0
            and item.get("summary", {}).get("passed") == item.get("summary", {}).get("selected")
            for item in matrix_runs
        )
    )
    full_case_set = len(cases) == len(all_cases)
    all_regions_hit = len(aggregate_hits) == len(aggregate_regions)
    all_lines_hit = (
        source_region_summary["lines"] == source_region_summary["lines_total"]
    )
    coverage_gate_passed = (
        full_case_set
        and complete_case_matrix
        and args.matrix_repeats >= 3
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
            "hit_by": sorted(all_case_regions[region_id].get("hit_by", [])),
        })

    status = "complete" if complete_case_matrix and complete_repeats else "incomplete"
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
            "manifest_case_count": len(all_cases),
            "selected": len(cases),
            "executed": sum(item["status"] != "not_run" for item in case_receipts),
            "passed": sum(item["status"] == "passed" for item in case_receipts),
            "failed": sum(item["status"] == "failed" for item in case_receipts),
            "infrastructure_failed": sum(item["status"] == "infrastructure_failed" for item in case_receipts),
            "transient_infrastructure_failures": sum(
                item.get("transient_infrastructure_failures", 0) for item in case_receipts
            ) + sum(item.get("transient_infrastructure_failures", 0) for item in matrix_runs),
            "oracle_parity": {
                "selected": len(oracle_case_receipts),
                "passed": sum(item["status"] == "passed" for item in oracle_case_receipts),
                "failed": sum(item["status"] == "failed" for item in oracle_case_receipts),
            },
            "fault_contracts": {
                "selected": len(fault_case_receipts),
                "passed": sum(item["status"] == "passed" for item in fault_case_receipts),
                "failed": sum(item["status"] == "failed" for item in fault_case_receipts),
            },
            "verification_runs": matrix_runs,
            "verification_runs_required": 3,
            "case_attribution_complete": len(case_receipts) == len(cases),
            # Region rows retain the complete hit_by relation. Repeating the
            # inverse SHA256 lists in every case makes a full report exceed
            # Coverage-MCP's size limit without adding evidence.
            "case_results": [
                {key: value for key, value in item.items() if key != "hit_region_ids"}
                for item in case_receipts
            ],
        },
        "coverage": {
            "gate": "passed" if coverage_gate_passed else "incomplete",
            "source_set": ["src/lib.rs"],
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
            "regions": region_rows,
            "uncovered_regions": uncovered,
            "attribution": {
                "algorithm": "LLVM function regions keyed by source hash, file, source span, and region kind",
                "per_case_profiles": len(case_receipts),
                "profile_union_matches_attribution": attribution_matches_union,
                "case_region_ids_verified": True,
                "case_region_lookup": "coverage.regions[].hit_by",
            },
            "coverage_mcp": {
                "status": "awaiting_query",
                "measurement_path": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
                "metric": "regions",
                "required_follow_up": "Run coverage_gaps against this exact report, then record its receipt here.",
            },
        },
        "artifacts": {
            "aggregate_profile_data": str(combined_profdata.relative_to(ROOT)),
            "per_case_profiles_root": str(profile_root.relative_to(ROOT)),
            "matrix_runs_root": str(repeat_root.relative_to(ROOT)),
        },
    }
    if source_identity(manifest, input_paths)["sha256"] != source["sha256"]:
        raise CoverageError("source or parity inputs changed while the coverage run was in progress")
    aggregate_llvm[LLVM_EXTENSION_KEY] = coverage_extension
    output.parent.mkdir(parents=True, exist_ok=True)
    report_bytes = (json.dumps(aggregate_llvm, indent=2, sort_keys=True) + "\n").encode()
    output.write_bytes(report_bytes)
    source_hashes = {
        path: digest
        for path, digest in source["file_sha256"].items()
        if path == "src/lib.rs"
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
    selected_batch_passed = complete_case_matrix and (not full_case_set or complete_repeats)
    return 0 if selected_batch_passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CoverageError, run_parity.ParityError, subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        print(f"unified coverage failure: {error}", file=sys.stderr)
        raise SystemExit(2)
