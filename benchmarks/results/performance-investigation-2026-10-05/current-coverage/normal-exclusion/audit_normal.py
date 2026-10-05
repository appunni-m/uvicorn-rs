#!/usr/bin/env python3
"""Disposable normal-build evidence recipe; never installs the extension."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[3]
AUDIT = Path(__file__).resolve().parent
TARGET = ROOT / "target"
BUILD_RECEIPT = AUDIT / "build-receipt.json"
SOURCE_PATHS = ("src/lib.rs", "Cargo.toml", "Cargo.lock", "pyproject.toml",
                "tools/http3-probe/Cargo.toml")
CASE_ID = "http1.scope-query-header-and-body"
SUPPORT_CASE_IDS = (
    "support.http1.response-header-capacity-error-recovers",
    "support.websocket.accept-header-capacity-error-recovers",
)
CASE_IDS = (CASE_ID, *SUPPORT_CASE_IDS)
ARMED_POINT = "native.runtime.build.error"
EXPECTED_NATIVE_SHA256 = "8f69afda0be9d121d304c674d5638f470da6939fbed58ce809457284df6585b6"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity() -> dict[str, str]:
    return {path: sha256(ROOT / path) for path in SOURCE_PATHS}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clean_environment() -> tuple[dict[str, str], list[str]]:
    environment = os.environ.copy()
    remove = {
        "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER", "LLVM_PROFILE_FILE", "CARGO_BUILD_RUSTFLAGS",
        "UVICORN_RS_COVERAGE_FAULT_FILE",
    }
    remove.update(key for key in environment if "LLVM_COV" in key)
    removed = sorted(key for key in remove if key in environment)
    for key in remove:
        environment.pop(key, None)
    # An absent variable falls back to Cargo's configured wrapper (sccache on
    # this host). Explicit empty overrides disable both configured wrappers.
    environment["RUSTC_WRAPPER"] = ""
    environment["RUSTC_WORKSPACE_WRAPPER"] = ""
    environment["CARGO_TARGET_DIR"] = str(TARGET)
    environment["PYO3_PYTHON"] = sys.executable
    if sys.platform == "darwin":
        environment["RUSTFLAGS"] = "-C link-arg=-undefined -C link-arg=dynamic_lookup"
    return environment, removed


def library_path() -> Path:
    name = ("libuvicorn_rs.dylib" if sys.platform == "darwin" else
            "uvicorn_rs.dll" if sys.platform == "win32" else "libuvicorn_rs.so")
    return TARGET / "release" / name


def build() -> int:
    before = source_identity()
    environment, removed = clean_environment()
    command = ["cargo", "build", "--locked", "--release", "--lib", "--manifest-path", "Cargo.toml"]
    started = datetime.now(timezone.utc).isoformat()
    with (AUDIT / "normal-build.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                stderr=subprocess.STDOUT, check=False)
    after = source_identity()
    library = library_path()
    receipt = {
        "schema": "uvicorn-rs-normal-build/audit-build@1",
        "status": "passed" if result.returncode == 0 and before == after else "failed",
        "command": command, "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": result.returncode, "source_hashes_before": before,
        "source_hashes_after": after, "source_sha256": after["src/lib.rs"],
        "compile_cfg": "default features; coverage wrapper and inherited Rust flags removed",
        "removed_environment_variable_names": removed,
        "build_environment": {key: environment.get(key) for key in
                              ("CARGO_TARGET_DIR", "PYO3_PYTHON", "RUSTFLAGS",
                               "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER")},
        "normal_library": str(library),
        "native_extension_sha256": sha256(library) if result.returncode == 0 and library.exists() else None,
        "workspace_extension_modified": False,
        "audit_recipe_sha256": sha256(Path(__file__)),
    }
    write_json(BUILD_RECEIPT, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(BUILD_RECEIPT)}))
    return 0 if receipt["status"] == "passed" else 1


def registered_fault_points() -> list[str]:
    tree = ast.parse((ROOT / "scripts/run_parity.py").read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "FAULT_POINTS"
            for target in statement.targets
        ):
            return sorted(ast.literal_eval(statement.value))
    raise RuntimeError("Could not read the existing fault point registry")


def audit() -> int:
    build_receipt = json.loads(BUILD_RECEIPT.read_text(encoding="utf-8"))
    if build_receipt["status"] != "passed" or source_identity() != build_receipt["source_hashes_after"]:
        raise RuntimeError("Normal build failed or the measured source changed after its build")
    if sha256(Path(__file__)) != build_receipt["audit_recipe_sha256"]:
        raise RuntimeError("Audit recipe changed after the normal build")
    library = Path(build_receipt["normal_library"])
    normal_sha = sha256(library)
    if normal_sha != build_receipt["native_extension_sha256"]:
        raise RuntimeError("Normal library changed after its build")
    installed = ROOT / "python/uvicorn_rs/_native.abi3.so"
    installed_before = sha256(installed) if installed.exists() else None

    markers = ["UVICORN_RS_COVERAGE_FAULT_FILE", "coverage-only injected MemoryError",
               "coverage-injected ", *registered_fault_points()]
    binary = library.read_bytes()
    byte_counts = {marker: binary.count(marker.encode("utf-8")) for marker in markers}
    strings = subprocess.run(["strings", str(library)], capture_output=True, text=True,
                             errors="replace", check=True, timeout=30)
    (AUDIT / "native-strings.txt").write_text(strings.stdout, encoding="utf-8")
    string_counts = {marker: strings.stdout.count(marker) for marker in markers}
    symbols = subprocess.run(["nm", "-g", str(library)], capture_output=True, text=True,
                             errors="replace", check=True, timeout=30)
    (AUDIT / "native-global-symbols.txt").write_text(symbols.stdout, encoding="utf-8")
    all_symbols = subprocess.run(["nm", "-a", str(library)], capture_output=True, text=True,
                                 errors="replace", check=True, timeout=30)
    (AUDIT / "native-all-symbols.txt").write_text(all_symbols.stdout, encoding="utf-8")
    section_text = ""
    if sys.platform == "darwin":
        sections = subprocess.run(["otool", "-l", str(library)], capture_output=True, text=True,
                                  errors="replace", check=True, timeout=30)
        section_text = sections.stdout
        (AUDIT / "native-macho-load-commands.txt").write_text(section_text, encoding="utf-8")
    llvm_markers = ("__llvm_profile", "__llvm_covmap", "__llvm_covfun", "__llvm_prf")
    llvm_marker_counts = {
        marker: {"raw_binary": binary.count(marker.encode("utf-8")),
                 "strings": strings.stdout.count(marker),
                 "global_symbols": symbols.stdout.count(marker),
                 "all_symbols": all_symbols.stdout.count(marker),
                 "macho_load_commands": section_text.count(marker)}
        for marker in llvm_markers
    }

    # Copy into this disposable artifact directory; keep the installed
    # workspace/site-packages extension intact for its preserved evidence.
    isolated = AUDIT / "normal-python"
    isolated.mkdir(exist_ok=True)
    package = isolated / "uvicorn_rs"
    shutil.copytree(ROOT / "python/uvicorn_rs", package, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.so", "*.dylib", "*.pyd", "__pycache__"))
    suffix = ".pyd" if sys.platform == "win32" else ".so"
    extension = package / ("_native.abi3" + suffix)
    shutil.copy2(library, extension)
    environment, _ = clean_environment()
    environment["PYTHONPATH"] = str(isolated)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    armed = AUDIT / "armed-fault.txt"
    armed.write_text(ARMED_POINT, encoding="utf-8")
    environment["UVICORN_RS_COVERAGE_FAULT_FILE"] = str(armed)

    inspection = subprocess.run(
        [sys.executable, "-c", "import json; import uvicorn_rs._native as n; "
         "print(json.dumps({'path':n.__file__, 'exports':sorted(x for x in dir(n) "
         "if not x.startswith('__')), 'serve_text_signature':getattr(n.serve, '__text_signature__', None)}))"],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=True, timeout=20)
    exports = json.loads(inspection.stdout)
    write_json(AUDIT / "native-exports.json", exports)
    help_result = subprocess.run([sys.executable, "-m", "uvicorn_rs", "--help"],
                                 cwd=ROOT, env=environment, capture_output=True, text=True,
                                 check=True, timeout=20)
    (AUDIT / "cli-help.txt").write_text(help_result.stdout, encoding="utf-8")
    cli_options = sorted(set(re.findall(r"--[a-z][a-z0-9-]*", help_result.stdout)))

    result_path = AUDIT / "parity-result.json"
    command = [sys.executable, str(ROOT / "scripts/run_parity.py"), "--fault-contracts"]
    for case_id in CASE_IDS:
        command.extend(["--case-id", case_id])
    command.extend(["--output", str(result_path)])
    with (AUDIT / "stdout.log").open("w", encoding="utf-8") as stdout, \
         (AUDIT / "stderr.log").open("w", encoding="utf-8") as stderr:
        parity_process = subprocess.run(command, cwd=ROOT, env=environment,
                                        stdout=stdout, stderr=stderr, check=False, timeout=90)
    parity = json.loads(result_path.read_text(encoding="utf-8"))
    measured_native = parity["run"]["target"]["native_extension"]
    summary = parity["summary"]
    cases = {case["case_id"]: case for case in parity["cases"]}
    native_points = set(registered_fault_points())
    expected_support_points = {
        SUPPORT_CASE_IDS[0]: "public.http-response-header-capacity",
        SUPPORT_CASE_IDS[1]: "public.websocket-accept-header-capacity",
    }
    checks = {
        "canonical_native_matches": normal_sha == EXPECTED_NATIVE_SHA256,
        "fault_markers_absent": not any(byte_counts.values()) and not any(string_counts.values()),
        "llvm_coverage_instrumentation_absent": not any(
            count for locations in llvm_marker_counts.values() for count in locations.values()),
        "native_exports_have_no_fault_control": not any(
            "fault" in name.lower() or "coverage" in name.lower() for name in exports["exports"]),
        "cli_has_no_fault_option": not any("fault" in option or "coverage" in option for option in cli_options),
        "armed_fault_file_ignored": armed.read_text(encoding="utf-8") == ARMED_POINT,
        "parity_passed": parity_process.returncode == 0 and summary == {
            "selected": 3, "executed": 3, "passed": 3, "failed": 0,
            "infrastructure_failed": 0, "not_run": 0},
        "exact_case_selection": set(cases) == set(CASE_IDS),
        "primary_case_is_live_oracle_parity": cases.get(CASE_ID, {}).get("verification") == "oracle-parity"
            and cases.get(CASE_ID, {}).get("oracle_observation") is not None,
        "support_cases_are_public_inputs_without_native_injection": all(
            cases.get(case_id, {}).get("verification") == "fault-contract"
            and cases.get(case_id, {}).get("fault", {}).get("point") == point
            and point not in native_points
            and cases.get(case_id, {}).get("oracle_observation") is None
            for case_id, point in expected_support_points.items()),
        "live_parity_used_normal_library": measured_native["sha256"] == normal_sha
            and Path(measured_native["path"]).resolve() == extension.resolve(),
        "inspection_used_normal_library": Path(exports["path"]).resolve() == extension.resolve(),
        "measured_source_unchanged": source_identity() == build_receipt["source_hashes_after"],
        "workspace_extension_unchanged": (
            sha256(installed) if installed.exists() else None) == installed_before,
    }
    lint_names = ("panic", "unwrap_used", "expect_used", "print_stdout", "print_stderr")
    lint_policies = {}
    for path in ("Cargo.toml", "tools/http3-probe/Cargo.toml"):
        cargo = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))
        lint_policies[path] = {name: cargo["lints"]["clippy"].get(name) for name in lint_names}
    checks["authored_panic_error_lints_denied"] = all(
        level == "deny" for policy in lint_policies.values() for level in policy.values())
    receipt = {
        "schema": "uvicorn-rs-normal-build/exclusion-audit@1",
        "status": "passed" if all(checks.values()) else "failed",
        "source_sha256": build_receipt["source_sha256"],
        "source_hashes": build_receipt["source_hashes_after"],
        "normal_library": str(library), "native_extension_sha256": normal_sha,
        "compile_cfg": build_receipt["compile_cfg"], "checks": checks,
        "fault_marker_counts": byte_counts, "strings_fault_marker_counts": string_counts,
        "registered_fault_point_count": len(registered_fault_points()),
        "llvm_instrumentation_marker_counts": llvm_marker_counts,
        "lint_policies": lint_policies, "audit_recipe_sha256": sha256(Path(__file__)),
        "native_exports": exports, "cli_options": cli_options,
        "armed_fault_point": ARMED_POINT, "parity_case_id": CASE_ID,
        "parity_case_ids": list(CASE_IDS),
        "public_support_contract_case_ids": list(SUPPORT_CASE_IDS),
        "verification_groups": {"live_oracle_parity": 1, "public_target_support_contracts": 2,
                                "native_injection_fault_contracts": 0},
        "case_verification_envelopes": {
            case_id: case["verification"] for case_id, case in cases.items()},
        "parity": summary, "parity_exit_code": parity_process.returncode,
        "build_receipt": str(BUILD_RECEIPT),
        "scope": "Authored production panic, unwrap, expect, and stdout/stderr macros are denied by Clippy. "
                 "Recoverable failures follow the repository's Result/PyResult policy. "
                 "The only intentional authored panic helper is cfg(coverage), with one narrow function-local "
                 "allow. The fault runner matches injected source/message/count per process and does not "
                 "allow production panics. This audit demonstrates fault exclusion from this normal binary "
                 "and one live oracle-parity workflow plus two public target support contracts. "
                 "The support contracts do not claim oracle equivalence or use native fault injection. "
                 "It does not prove dependency internals cannot panic, "
                 "including resource/allocation failures, and is not a substitute for the complete matrix.",
    }
    write_json(AUDIT / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(AUDIT / "receipt.json")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "audit"))
    arguments = parser.parse_args()
    raise SystemExit(build() if arguments.action == "build" else audit())
