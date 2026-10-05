#!/usr/bin/env python3
"""Verify the exact three-platform package and consumer evidence bundle."""

from __future__ import annotations

import argparse
import configparser
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile

from check_release_version import project_versions
from release_evidence import (
    COMMIT, LICENSE_EXPRESSION, PLATFORMS, ROOT, SHA256, command_output,
    fault_points, file_sha256, inspect_sdist, inspect_wheel, license_contract,
    load_json, normal_fault_markers, source_hashes, validate_consumer, validate_packaged_parity,
    validate_source_consumer,
)


def verify_external_evidence(directory: Path, version: str, commit: str, linux: dict) -> dict:
    from check_ci_evidence import load_contract, validate_parity

    floor_path = directory / "python-floor/consumer-python39.json"
    floor = load_json(floor_path)
    validate_consumer(floor, version, linux["sha256"], linux["native"]["sha256"])
    if re.match(r"3\.9\.[0-9]+(?:\s|$)", str(floor.get("python", ""))) is None:
        raise ValueError("Python-floor consumer must execute on CPython 3.9")
    public_path = directory / "public/asgi-parity/result.json"
    public = load_json(public_path)
    normal_path = directory / "public/normal-audit/receipt.json"
    normal = load_json(normal_path)
    if (normal.get("schema") != "uvicorn-rs-normal-build/exclusion-audit@1"
            or normal.get("status") != "passed" or normal.get("git_commit") != commit
            or normal.get("project_version") != version
            or normal.get("source_sha256") != source_hashes()["src/lib.rs"]):
        raise ValueError("normal audit identity/status does not match candidate source/version/commit")
    checks = normal.get("checks", {})
    required_checks = {"fault_markers_absent", "llvm_coverage_instrumentation_absent",
                       "native_exports_have_no_fault_control", "cli_has_no_fault_option",
                       "armed_fault_file_ignored", "parity_passed", "exact_case_selection"}
    if not required_checks <= set(checks) or any(value is not True for value in checks.values()):
        raise ValueError("normal exclusion audit contains absent or failed gates")
    points = fault_points()
    markers = normal_fault_markers()
    if normal.get("registered_fault_point_count") != len(points):
        raise ValueError("normal audit fault denominator differs from current registry")
    for key in ("fault_marker_counts", "strings_fault_marker_counts"):
        counts = normal.get(key, {})
        if set(counts) != markers or any(type(value) is not int or value != 0 for value in counts.values()):
            raise ValueError(f"normal audit {key} is incomplete or contains a marker")
    llvm = normal.get("llvm_instrumentation_marker_counts", {})
    if not {"__llvm_profile", "__llvm_covmap", "__llvm_covfun", "__llvm_prf"} <= set(llvm):
        raise ValueError("normal audit omitted LLVM instrumentation checks")
    locations = {"raw_binary", "strings", "global_symbols", "all_symbols", "sections"}
    if any(set(values) != locations or any(type(count) is not int or count != 0 for count in values.values()) for values in llvm.values()):
        raise ValueError("normal audit retained LLVM instrumentation")
    if normal.get("armed_fault_point") != "native.runtime.build.error":
        raise ValueError("normal exclusion audit armed a different control point")
    inputs = source_hashes()
    hashes = normal.get("source_hashes", {})
    if not {"src/lib.rs", "Cargo.toml", "Cargo.lock", "pyproject.toml"} <= set(hashes):
        raise ValueError("normal audit omitted reviewed build inputs")
    for name, digest in hashes.items():
        expected = inputs.get(name)
        if expected is None:
            path = ROOT / name
            if path.is_absolute() and ROOT in path.resolve().parents and path.is_file():
                expected = file_sha256(path)
        if digest != expected:
            raise ValueError(f"normal audit source input differs: {name}")
    native_sha = normal.get("native_extension_sha256", "")
    if SHA256.fullmatch(str(native_sha)) is None:
        raise ValueError("normal audit omitted native identity")
    validate_parity(public, expected_native_sha256=native_sha, offline=True)
    if public["run"]["target"]["revision"] != commit or public["run"]["target"].get("dirty") is not False:
        raise ValueError("normal public parity is not from the clean expected commit")
    expected_cases = ["http1.scope-query-header-and-body",
                      "support.http1.response-header-capacity-error-recovers",
                      "support.websocket.accept-header-capacity-error-recovers"]
    if (normal.get("parity_case_ids") != expected_cases
            or normal.get("parity") != {"selected": 3, "executed": 3, "passed": 3, "failed": 0, "infrastructure_failed": 0, "not_run": 0}):
        raise ValueError("normal audit did not pass the exact three exclusion cases")
    selected_path = normal_path.parent / "parity-result.json"
    if normal.get("parity_result_sha256") != file_sha256(selected_path):
        raise ValueError("normal audit selected-case report checksum differs")
    _, cases, _ = load_contract()
    case_index = {case["case_id"]: case for case in cases}
    selected = load_json(selected_path)
    validate_parity(selected, expected_cases=[case_index[name] for name in expected_cases],
                    expected_native_sha256=native_sha, offline=True)
    if selected["run"]["target"].get("dirty") is not False:
        raise ValueError("normal selected-case parity did not execute a clean commit")
    return {path.relative_to(directory).as_posix(): file_sha256(path)
            for path in (floor_path, public_path, normal_path, selected_path)}


def verify(root: Path, version: str, commit: str, evidence: Path | None) -> dict:
    if COMMIT.fullmatch(commit) is None or command_output(["git", "rev-parse", "HEAD"]) != commit:
        raise ValueError("candidate commit must equal the full checked-out Git commit")
    if command_output(["git", "status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("candidate assembly requires a clean tracked checkout")
    project_versions(expected=version)
    license_contract()
    if not root.is_dir():
        raise ValueError(f"artifact directory does not exist: {root}")
    paths = list(root.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("candidate directory must contain only regular artifact files")
    wheels = [path for path in paths if path.suffix == ".whl"]
    sdists = [path for path in paths if path.name.endswith(".tar.gz")]
    if len(wheels) != 3 or len(sdists) != 1 or len(paths) != 12:
        raise ValueError(f"expected exactly three wheels, one sdist and eight evidence files; found {len(wheels)} wheels, {len(sdists)} sdists, {len(paths)} files")
    expected = {path.name for path in wheels} | {f"uvicorn_rs-{version}.tar.gz", "consumer-sdist.json", "parity-linux-x86_64.json"}
    expected |= {f"build-manifest-{platform}.json" for platform in PLATFORMS}
    expected |= {f"consumer-{platform}.json" for platform in PLATFORMS}
    if {path.name for path in paths} != expected:
        raise ValueError("candidate has unexpected filenames or missing evidence")
    inputs = source_hashes()
    inspected = {}
    for path in wheels:
        wheel = inspect_wheel(path, version)
        if wheel["platform"] in inspected:
            raise ValueError("duplicate candidate wheel platform")
        inspected[wheel["platform"]] = wheel
    if set(inspected) != set(PLATFORMS):
        raise ValueError("candidate platform matrix is incomplete")
    sdist = inspect_sdist(sdists[0], version)
    manifests = {}
    tool_versions = set()
    for platform, target in PLATFORMS.items():
        path = root / f"build-manifest-{platform}.json"
        manifest = load_json(path)
        if (manifest.get("schema") != "uvicorn-rs-platform-build@1"
                or manifest.get("commit") != commit or manifest.get("version") != version
                or manifest.get("platform") != platform or manifest.get("target") != target
                or manifest.get("source_dirty") is not False or manifest.get("state") != "candidate"
                or manifest.get("publication_blockers") != []
                or manifest.get("license_expression") != LICENSE_EXPRESSION
                or manifest.get("source_hashes") != inputs
                or manifest.get("source_sha256") != inputs["src/lib.rs"]):
            raise ValueError(f"build manifest identity/clean-source contract mismatch: {platform}")
        wheel = inspected[platform]
        files = {wheel["filename"], f"consumer-{platform}.json"}
        packages = {wheel["filename"]: wheel}
        if platform == "linux-x86_64":
            files |= {sdist["filename"], "consumer-sdist.json", "parity-linux-x86_64.json"}
            packages[sdist["filename"]] = sdist
        if manifest.get("files") != {name: file_sha256(root / name) for name in sorted(files)}:
            raise ValueError(f"build manifest artifact/evidence checksums differ: {platform}")
        if manifest.get("packages") != packages:
            raise ValueError(f"build manifest inspected package/native/RECORD evidence differs: {platform}")
        toolchain = manifest.get("toolchain", {})
        if set(toolchain) != {"rustc", "cargo", "maturin", "python"} or any(not isinstance(value, str) or not value.strip() for value in toolchain.values()):
            raise ValueError(f"build manifest omitted toolchain identities: {platform}")
        if f"host: {target}" not in toolchain["rustc"].splitlines():
            raise ValueError("recorded compiler host differs from native target")
        release = next((line for line in toolchain["rustc"].splitlines() if line.startswith("release: ")), "")
        tool_versions.add((release, toolchain["cargo"], toolchain["maturin"], toolchain["python"].split()[0]))
        build = manifest.get("build", {})
        required_env = {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"}
        if (build.get("wheel_command") != ["maturin", "build", "--release", "--locked", "--interpreter", "python", "--out", "dist"]
                or build.get("features") != ["pyo3/extension-module"] or build.get("profile") != "release"
                or build.get("locked") is not True or not required_env <= set(build.get("environment", {}))
                or any(value != "" for value in build["environment"].values())):
            raise ValueError("build manifest does not record the normal locked release build")
        validate_consumer(load_json(root / f"consumer-{platform}.json"), version, wheel["sha256"], wheel["native"]["sha256"])
        manifests[platform] = file_sha256(path)
    if len(tool_versions) != 1:
        raise ValueError("platform manifests use different compiler/build frontend/Python versions")
    validate_source_consumer(load_json(root / "consumer-sdist.json"), version, sdist)
    linux = inspected["linux-x86_64"]
    parity_path = root / "parity-linux-x86_64.json"
    validate_packaged_parity(parity_path, linux["native"]["sha256"])
    parity_target = load_json(parity_path)["run"]["target"]
    if parity_target.get("revision") != commit or parity_target.get("dirty") is not False:
        raise ValueError("shipping Linux public parity is not from the clean expected commit")
    external = verify_external_evidence(evidence, version, commit, linux) if evidence is not None else {}
    if source_hashes() != inputs:
        raise ValueError("reviewed package inputs changed during candidate verification")
    return {"schema": "uvicorn-rs-candidate-verification@1", "state": "verified candidate; publication disabled",
            "commit": commit, "version": version, "platform_manifest_sha256": manifests,
            "files": {path.name: file_sha256(path) for path in sorted(paths)},
            "external_evidence": external, "source_sha256": inputs["src/lib.rs"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("version")
    parser.add_argument("commit")
    parser.add_argument("--evidence-directory", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.directory, args.version, args.commit, args.evidence_directory)
        outputs = [args.directory / name for name in ("SHA256SUMS", "candidate.txt", "candidate-verification.json")]
        if any(path.exists() for path in outputs):
            raise ValueError("candidate verification outputs already exist; preserve them and use a fresh directory")
        outputs[0].write_text("".join(f"{digest}  {name}\n" for name, digest in result["files"].items()), encoding="utf-8")
        outputs[1].write_text(f"version={args.version}\ncommit={args.commit}\nstate=verified candidate; publication disabled\n", encoding="utf-8")
        outputs[2].write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, configparser.Error, zipfile.BadZipFile, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"release candidate: {error}", file=sys.stderr)
        return 1
    print(f"verified three wheels, one source archive and their consumer/build evidence for {args.version} at {args.commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
