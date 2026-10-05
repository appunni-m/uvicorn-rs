#!/usr/bin/env python3
"""Inspect the imported normal wheel and run three existing public workflows.

This command never builds, copies, installs, or replaces a native extension.
Its native identity is the module imported by the invoking interpreter.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from check_ci_evidence import (
    EvidenceError, ROOT, git_commit, load_contract, read_json, require,
    sha256, source_constant, validate_parity,
)


PRIMARY_CASE = "http1.scope-query-header-and-body"
SUPPORT_CASES = {
    "support.http1.response-header-capacity-error-recovers": "public.http-response-header-capacity",
    "support.websocket.accept-header-capacity-error-recovers": "public.websocket-accept-header-capacity",
}
CASE_IDS = (PRIMARY_CASE, *SUPPORT_CASES)
ARMED_POINT = "native.runtime.build.error"
SOURCE_PATHS = ("src/lib.rs", "Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock",
                "scripts/run_parity.py", "tests/parity/manifest.json", "tests/parity/app.py",
                "tools/http3-probe/Cargo.toml", "tools/http3-probe/Cargo.lock",
                "scripts/audit_normal_build.py", "scripts/check_ci_evidence.py")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source_identity() -> dict[str, str]:
    paths = [*SOURCE_PATHS, *(str(path.relative_to(ROOT)) for path in load_contract()[2])]
    return {relative: sha256(ROOT / relative) for relative in paths}


def normal_environment() -> tuple[dict[str, str], list[str]]:
    environment = os.environ.copy()
    remove = {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "RUSTC_WRAPPER",
              "RUSTC_WORKSPACE_WRAPPER", "LLVM_PROFILE_FILE", "CARGO_BUILD_RUSTFLAGS",
              "UVICORN_RS_COVERAGE_FAULT_FILE"}
    remove.update(key for key in environment if "LLVM_COV" in key)
    removed = sorted(key for key in remove if key in environment)
    for key in remove:
        environment.pop(key, None)
    # The parity runner may build its existing protocol client. Disable any
    # inherited/configured instrumentation wrapper for that separate client.
    environment["RUSTC_WRAPPER"] = ""
    environment["RUSTC_WORKSPACE_WRAPPER"] = ""
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment, removed


def capture(command: list[str], output: Path, environment: dict[str, str], timeout: int = 30) -> str:
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                            text=True, errors="replace", timeout=timeout, check=False)
    output.write_text(result.stdout + result.stderr, encoding="utf-8")
    require(result.returncode == 0, f"inspection command failed ({result.returncode}); see {output}")
    return result.stdout


def audit(output: Path) -> int:
    require(sys.platform in {"linux", "darwin"}, "normal native symbol audit currently requires Linux or macOS")
    output.mkdir(parents=True, exist_ok=False)
    before = source_identity()
    module = importlib.import_module("uvicorn_rs._native")
    library = Path(module.__file__).resolve()
    require(not library.is_relative_to(ROOT / "python"), "audit requires an installed wheel, not the editable checkout")
    native_sha = sha256(library)
    environment, removed = normal_environment()
    runner = ROOT / "scripts/run_parity.py"
    points = sorted(source_constant(runner, "FAULT_POINTS"))
    panic_messages = source_constant(runner, "COVERAGE_PANIC_MESSAGES")
    markers = ["UVICORN_RS_COVERAGE_FAULT_FILE", "coverage-only injected MemoryError",
               "coverage-injected ", "coverage_panic", *points, *panic_messages.values()]
    binary = library.read_bytes()
    byte_counts = {marker: binary.count(marker.encode("utf-8")) for marker in markers}
    strings = capture(["strings", str(library)], output / "native-strings.txt", environment)
    string_counts = {marker: strings.count(marker) for marker in markers}
    symbols = capture(["nm", "-g", str(library)], output / "native-global-symbols.txt", environment)
    all_symbols = capture(["nm", "-a", str(library)], output / "native-all-symbols.txt", environment)
    section_command = ["otool", "-l", str(library)] if sys.platform == "darwin" else ["readelf", "-SW", str(library)]
    sections = capture(section_command, output / "native-sections.txt", environment)
    llvm_markers = ("__llvm_profile", "__llvm_covmap", "__llvm_covfun", "__llvm_prf")
    llvm_counts = {
        marker: {"raw_binary": binary.count(marker.encode()), "strings": strings.count(marker),
                 "global_symbols": symbols.count(marker), "all_symbols": all_symbols.count(marker),
                 "sections": sections.count(marker)} for marker in llvm_markers
    }
    armed = output / "armed-fault.txt"
    armed.write_text(ARMED_POINT, encoding="utf-8")
    environment["UVICORN_RS_COVERAGE_FAULT_FILE"] = str(armed)
    inspection_code = (
        "import json; import uvicorn_rs._native as n; "
        "print(json.dumps({'path':n.__file__, 'exports':sorted(x for x in dir(n) if not x.startswith('__')), "
        "'serve_text_signature':getattr(n.serve, '__text_signature__', None)}))"
    )
    exports = json.loads(capture([sys.executable, "-c", inspection_code], output / "native-exports.json", environment, 20))
    help_text = capture([sys.executable, "-m", "uvicorn_rs", "--help"], output / "cli-help.txt", environment, 20)
    cli_options = sorted(set(re.findall(r"--[a-z][a-z0-9-]*", help_text)))
    _, all_cases, _ = load_contract()
    case_index = {case["case_id"]: case for case in all_cases}
    require(set(CASE_IDS) <= set(case_index), "standard normal-build audit cases are missing from the current index")
    selected = [case_index[case_id] for case_id in CASE_IDS]
    result_path = output / "parity-result.json"
    command = [sys.executable, str(runner), "--fault-contracts"]
    for case_id in CASE_IDS:
        command.extend(["--case-id", case_id])
    command.extend(["--output", str(result_path)])
    started = datetime.now(timezone.utc).isoformat()
    with (output / "stdout.log").open("w", encoding="utf-8") as stdout, \
         (output / "stderr.log").open("w", encoding="utf-8") as stderr:
        parity_process = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout,
                                        stderr=stderr, timeout=300, check=False)
    parity = read_json(result_path)
    checks = {
        "fault_markers_absent": not any(byte_counts.values()) and not any(string_counts.values()),
        "llvm_coverage_instrumentation_absent": not any(count for locations in llvm_counts.values() for count in locations.values()),
        "native_exports_have_no_fault_control": not any("fault" in name.lower() or "coverage" in name.lower()
                                                       for name in exports["exports"]),
        "native_signature_has_no_fault_control": not any(
            marker in (exports["serve_text_signature"] or "").lower() for marker in ("fault", "coverage")),
        "cli_has_no_fault_option": not any("fault" in option or "coverage" in option for option in cli_options),
        "armed_fault_file_ignored": armed.read_text(encoding="utf-8") == ARMED_POINT,
        "parity_passed": parity_process.returncode == 0,
        "exact_case_selection": {case["case_id"] for case in parity["cases"]} == set(CASE_IDS),
        "primary_case_is_live_oracle_parity": case_index[PRIMARY_CASE].get("verification", "oracle-parity") == "oracle-parity",
        "support_cases_are_public_inputs_without_native_injection": all(
            case_index[case_id].get("verification") == "fault-contract"
            and case_index[case_id].get("fault", {}).get("point") == point and point not in points
            for case_id, point in SUPPORT_CASES.items()),
        "live_parity_used_normal_library": parity["run"]["target"]["native_extension"]["sha256"] == native_sha,
        "inspection_used_normal_library": Path(exports["path"]).resolve() == library,
        "measured_source_unchanged": source_identity() == before,
        "installed_native_unchanged": sha256(library) == native_sha,
    }
    evidence_error = None
    try:
        validate_parity(parity, expected_cases=selected, expected_native_sha256=native_sha, offline=False)
    except EvidenceError as error:
        evidence_error = str(error)
    checks["strict_current_case_evidence"] = evidence_error is None
    lint_names = ("panic", "unwrap_used", "expect_used", "print_stdout", "print_stderr")
    lint_policies = {}
    for relative in ("Cargo.toml", "tools/http3-probe/Cargo.toml"):
        cargo = tomllib.loads((ROOT / relative).read_text())
        lint_policies[relative] = {name: cargo["lints"]["clippy"].get(name) for name in lint_names}
    checks["authored_panic_error_lints_denied"] = all(
        level == "deny" for policy in lint_policies.values() for level in policy.values())
    receipt = {
        "schema": "uvicorn-rs-normal-build/exclusion-audit@1",
        "status": "passed" if all(checks.values()) else "failed",
        "git_commit": git_commit(),
        "project_version": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": before["src/lib.rs"], "source_hashes": before,
        "normal_library": str(library), "native_extension_sha256": native_sha,
        "compile_cfg": "imported installed normal wheel; no native build or install performed by audit",
        "checks": checks, "evidence_error": evidence_error,
        "fault_marker_counts": byte_counts, "strings_fault_marker_counts": string_counts,
        "registered_fault_point_count": len(points), "llvm_instrumentation_marker_counts": llvm_counts,
        "lint_policies": lint_policies, "audit_recipe_sha256": sha256(Path(__file__)),
        "native_exports": exports, "cli_options": cli_options,
        "armed_fault_point": ARMED_POINT, "removed_environment_variable_names": removed,
        "parity_case_id": PRIMARY_CASE, "parity_case_ids": list(CASE_IDS),
        "public_support_contract_case_ids": list(SUPPORT_CASES),
        "verification_groups": {"live_oracle_parity": 1, "public_target_support_contracts": 2,
                                "native_injection_fault_contracts": 0},
        "case_verification_envelopes": {case["case_id"]: case["verification"] for case in parity["cases"]},
        "parity": parity["summary"], "parity_exit_code": parity_process.returncode,
        "parity_result_sha256": sha256(result_path), "command": command,
        "scope": "Normal installed binary fault exclusion, one live oracle comparison and two public target support contracts; "
                 "no native fault injection, unit tests, publication, or complete-matrix claim.",
    }
    write_json(output / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(output / "receipt.json"),
                      "native_sha256": native_sha, "cases": len(CASE_IDS)}, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="fresh directory retaining binary and live-case evidence")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    existed = output.exists()
    try:
        return audit(output)
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        if not existed and output.is_dir() and not (output / "receipt.json").exists():
            write_json(output / "receipt.json", {"schema": "uvicorn-rs-normal-build/exclusion-audit@1",
                                                 "status": "failed", "error": str(error)})
        print(f"normal build audit rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
