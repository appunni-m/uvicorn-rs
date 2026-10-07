"""Inspect actual packages and record commit-bound native build evidence.

Receipts are trusted CI integrity records, not signatures or independent proof
of an executed build command. Dirty local records cannot pass assembly.
"""

from __future__ import annotations

import argparse
import ast
import base64
import configparser
import csv
import hashlib
import io
import json
import os
import re
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

import tomllib
from check_release_version import project_versions

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {
    "linux-x86_64": "x86_64-unknown-linux-gnu",
    "macos-arm64": "aarch64-apple-darwin",
    "windows-x86_64": "x86_64-pc-windows-msvc",
}
LICENSES = ("LICENSE", "LICENSE-BSD-3-Clause", "LICENSE-MIT")
LICENSE_EXPRESSION = "BSD-3-Clause OR MIT"
REQUIRED = ("Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock", "README.md", "src/lib.rs", *LICENSES)
FORBIDDEN_DIRS = {
    "benchmarks", "build", "target", "tools", "tests", "scripts", "examples", "coverage",
    ".coverage-mcp", ".github", ".git", ".venv", "venv", "__pycache__", ".agents", ".codex",
}
FORBIDDEN_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".profraw", ".profdata", ".pyc", ".env")
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def _json_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON field: {name}")
        result[name] = value
    return result


def load_json(path: Path) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON number: {value}")

    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_json_pairs,
                        parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise TypeError(f"expected a JSON object: {path.name}")
    return result


def source_hashes() -> dict[str, str]:
    paths = {ROOT / name for name in REQUIRED}
    paths.update((ROOT / "src").rglob("*.rs"))
    paths.update((ROOT / "python" / "uvicorn_rs").glob("*.py"))
    for optional in ("build.rs", ".gitignore"):
        if (ROOT / optional).exists():
            paths.add(ROOT / optional)
    paths.update(ROOT.glob("*.md"))
    paths.update((ROOT / "docs").rglob("*.md"))
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("package source inputs must be regular files")
    return {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sorted(paths)}


def license_contract() -> None:
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))["package"]
    python = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if cargo.get("license") != LICENSE_EXPRESSION or python.get("license") != LICENSE_EXPRESSION:
        raise ValueError("Cargo and Python license expressions must be BSD-3-Clause OR MIT")
    if set(python.get("license-files", [])) != set(LICENSES):
        raise ValueError("Python metadata must declare all three project license files")
    for name in LICENSES:
        if not (ROOT / name).read_bytes().strip():
            raise ValueError(f"empty license file: {name}")


def safe_member(name: str) -> str:
    normalized = name.rstrip("/")
    path = PurePosixPath(normalized)
    if (not normalized or "\\" in name or "\x00" in name or path.is_absolute()
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
            or ":" in path.parts[0] or path.as_posix() != normalized):
        raise ValueError(f"unsafe archive path: {name!r}")
    if (any(part.lower() in FORBIDDEN_DIRS or part.lower().startswith(".env") for part in path.parts)
            or normalized.lower().endswith(FORBIDDEN_SUFFIXES)
            or path.name.lower() in {"credentials", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}):
        raise ValueError(f"repository/developer/secret file in package: {name}")
    return normalized


def check_content(name: str, data: bytes) -> None:
    if (re.search(rb"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----", data)
            or re.search(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|pypi-[A-Za-z0-9_-]{40,})", data)):
        raise ValueError(f"credential-like content in package: {name}")


def runner_constant(name: str) -> object:
    tree = ast.parse((ROOT / "scripts/run_parity.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"could not find indexed runner constant: {name}")


def fault_points() -> list[str]:
    source = (ROOT / "src/lib.rs").read_text(encoding="utf-8")
    block = source.split("impl CoverageFaultPoint {", 1)[1].split("fn coverage_fault_is_armed", 1)[0]
    points = sorted(set(re.findall(r'"([a-z][a-z0-9.-]+)"', block)))
    if points != sorted(runner_constant("FAULT_POINTS")):
        raise ValueError("source and parity fault point registries differ")
    return points


def normal_fault_markers() -> set[str]:
    messages = runner_constant("COVERAGE_PANIC_MESSAGES")
    return {*fault_points(), *messages.values(), "coverage_panic", "UVICORN_RS_COVERAGE_FAULT_FILE",
            "coverage-only injected MemoryError", "coverage-injected "}


def inspect_native(data: bytes, platform_name: str | None = None) -> dict:
    if platform_name == "linux-x86_64":
        if (len(data) < 20 or data[:6] != b"\x7fELF\x02\x01"
                or struct.unpack_from("<H", data, 18)[0] != 62):
            raise ValueError("Linux wheel native module must be ELF64 x86-64")
    elif platform_name == "macos-arm64":
        if (len(data) < 8 or data[:4] != b"\xcf\xfa\xed\xfe"
                or struct.unpack_from("<I", data, 4)[0] != 0x0100000C):
            raise ValueError("macOS wheel native module must be Mach-O ARM64")
    elif platform_name == "windows-x86_64":
        if len(data) < 64 or data[:2] != b"MZ":
            raise ValueError("Windows wheel native module must be PE x86-64")
        offset = struct.unpack_from("<I", data, 60)[0]
        if (len(data) < offset + 6 or data[offset:offset + 4] != b"PE\x00\x00"
                or struct.unpack_from("<H", data, offset + 4)[0] != 0x8664):
            raise ValueError("Windows wheel native module must be PE x86-64")
    points = fault_points()
    markers = [*sorted(normal_fault_markers()), "__llvm_profile", "__llvm_cov", "__llvm_prf",
               "__profc_", "__profd_", "__covrec_", ".llvm_prf", "uvicorn-rs-runtime-diagnostics"]
    found = [marker for marker in markers if marker.encode() in data]
    if found:
        raise ValueError(f"native module contains coverage/fault/diagnostic markers: {found}")
    return {"sha256": sha256(data), "size": len(data), "fault_points_checked": len(points),
            "fault_registry_sha256": sha256("\n".join(points).encode()), "normal_markers_absent": True}


def wheel_platform(tag: str) -> str:
    tags = tag.split(".")
    if all(re.fullmatch(r"(?:linux|manylinux(?:1|2010|2014|_[0-9]+_[0-9]+))_x86_64", item) for item in tags):
        return "linux-x86_64"
    if all(re.fullmatch(r"macosx_[0-9]+_[0-9]+_arm64", item) for item in tags):
        return "macos-arm64"
    if tags == ["win_amd64"]:
        return "windows-x86_64"
    raise ValueError(f"unexpected wheel platform tag: {tag}")


def package_metadata(data: bytes, version: str) -> object:
    metadata = BytesParser(policy=policy.default).parsebytes(data)
    for key, expected in (("Name", "uvicorn-rs"), ("Version", version),
                          ("License-Expression", LICENSE_EXPRESSION), ("Requires-Python", ">=3.9")):
        if metadata.get_all(key) != [expected]:
            raise ValueError(f"package metadata {key} must be exactly {expected!r}")
    if sorted(metadata.get_all("License-File", [])) != sorted(LICENSES):
        raise ValueError("package metadata must include exactly three License-File fields")
    if metadata.get_payload(decode=True).decode("utf-8").strip() != (ROOT / "README.md").read_text(encoding="utf-8").strip():
        raise ValueError("packaged README differs from the reviewed checkout")
    return metadata


def inspect_wheel(path: Path, version: str, expected_platform: str | None = None) -> dict:
    match = re.fullmatch(r"uvicorn_rs-([0-9.]+)-cp39-abi3-(.+)\.whl", path.name)
    if match is None or match[1] != version:
        raise ValueError(f"unexpected wheel name/version/ABI floor: {path.name}")
    platform_name = wheel_platform(match[2])
    if expected_platform is not None and platform_name != expected_platform:
        raise ValueError(f"wheel platform differs from requested producer: {path.name}")
    prefix = f"uvicorn_rs-{version}.dist-info"
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [safe_member(entry.filename) for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("duplicate wheel members")
        contents = {}
        for entry, name in zip(entries, names):
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError(f"symlink or encrypted wheel member: {name}")
            if not name.startswith(("uvicorn_rs/", prefix + "/")):
                raise ValueError(f"unexpected wheel member: {name}")
            if not entry.is_dir():
                contents[name] = archive.read(entry)
                check_content(name, contents[name])
    metadata_name, wheel_name, record_name = (f"{prefix}/{name}" for name in ("METADATA", "WHEEL", "RECORD"))
    package_metadata(contents[metadata_name], version)
    wheel_metadata = BytesParser(policy=policy.default).parsebytes(contents[wheel_name])
    expected_tags = sorted(f"cp39-abi3-{tag}" for tag in match[2].split("."))
    if (wheel_metadata.get_all("Tag") is None or sorted(wheel_metadata.get_all("Tag")) != expected_tags
            or wheel_metadata.get_all("Root-Is-Purelib") != ["false"]):
        raise ValueError("wheel metadata tags or native-library declaration differ from filename")
    entry_points = configparser.ConfigParser(interpolation=None)
    entry_points.optionxform = str
    entry_points.read_string(contents[f"{prefix}/entry_points.txt"].decode("utf-8"))
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    if entry_points.sections() != ["console_scripts"] or dict(entry_points["console_scripts"]) != declared:
        raise ValueError("wheel console entry points differ from reviewed project scripts")
    rows = list(csv.reader(io.StringIO(contents[record_name].decode("utf-8"))))
    recorded = set()
    for row in rows:
        if len(row) != 3 or row[0] in recorded or row[0] not in contents:
            raise ValueError("wheel RECORD contains malformed, duplicate or unknown members")
        name, digest, size = row
        recorded.add(name)
        if name == record_name:
            if digest or size:
                raise ValueError("wheel RECORD must leave its own digest and size empty")
        else:
            expected_digest = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(contents[name]).digest()).decode().rstrip("=")
            if digest != expected_digest or size != str(len(contents[name])):
                raise ValueError(f"wheel RECORD hash/size mismatch: {name}")
    if recorded != set(contents):
        raise ValueError("wheel RECORD does not account for every packaged file")
    for name in LICENSES:
        if contents[f"{prefix}/licenses/{name}"] != (ROOT / name).read_bytes():
            raise ValueError(f"packaged license differs: {name}")
    for source in sorted((ROOT / "python/uvicorn_rs").glob("*.py")):
        name = f"uvicorn_rs/{source.name}"
        if contents[name] != source.read_bytes():
            raise ValueError(f"packaged Python source differs: {name}")
    native_names = [name for name in contents if name.startswith("uvicorn_rs/_native.") and name.endswith((".so", ".pyd"))]
    if len(native_names) != 1:
        raise ValueError("wheel must contain exactly one native module")
    if native_names[0].endswith(".pyd") != (platform_name == "windows-x86_64"):
        raise ValueError("native library extension does not match wheel platform")
    allowed = {metadata_name, wheel_name, record_name, f"{prefix}/entry_points.txt", *native_names}
    allowed.update(f"{prefix}/licenses/{name}" for name in LICENSES)
    allowed.update(f"uvicorn_rs/{source.name}" for source in (ROOT / "python/uvicorn_rs").glob("*.py"))
    extras = set(contents) - allowed
    if any(not re.fullmatch(re.escape(prefix) + r"/sboms/[^/]+\.json", name) for name in extras):
        raise ValueError(f"unexpected files in wheel: {sorted(extras)}")
    return {"filename": path.name, "sha256": file_sha256(path), "size": path.stat().st_size,
            "platform": platform_name, "tags": expected_tags, "members": sorted(contents),
            "record_verified": True, "native": {"member": native_names[0], **inspect_native(contents[native_names[0]], platform_name)}}


def inspect_sdist(path: Path, version: str) -> dict:
    if path.name != f"uvicorn_rs-{version}.tar.gz":
        raise ValueError(f"unexpected source archive name: {path.name}")
    prefix = f"uvicorn_rs-{version}/"
    contents = {}
    seen = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = safe_member(member.name)
            if name in seen or not (member.isfile() or member.isdir()):
                raise ValueError(f"duplicate or nonregular source archive member: {name}")
            seen.add(name)
            if not name.startswith(prefix):
                if member.isdir() and name == prefix.rstrip("/"):
                    continue
                raise ValueError("source archive must have exactly the expected package root")
            if member.isfile():
                reader = archive.extractfile(member)
                if reader is None:
                    raise ValueError(f"unreadable source member: {name}")
                relative = name[len(prefix):]
                contents[relative] = reader.read()
                check_content(name, contents[relative])
    package_metadata(contents["PKG-INFO"], version)
    inputs = source_hashes()
    mandatory = {*REQUIRED, *(f"python/uvicorn_rs/{path.name}" for path in (ROOT / "python/uvicorn_rs").glob("*.py"))}
    if not mandatory <= set(contents):
        raise ValueError(f"source archive missing required inputs: {sorted(mandatory - set(contents))}")
    for name, data in contents.items():
        if name != "PKG-INFO" and (name not in inputs or sha256(data) != inputs[name]):
            raise ValueError(f"source archive differs from reviewed input: {name}")
    return {"filename": path.name, "sha256": file_sha256(path), "size": path.stat().st_size,
            "members": sorted(contents), "source_hashes": {name: sha256(data) for name, data in sorted(contents.items()) if name != "PKG-INFO"}}


def validate_consumer(value: dict, version: str, wheel_sha: str, native_sha: str | None = None) -> None:
    if not isinstance(wheel_sha, str) or SHA256.fullmatch(wheel_sha) is None:
        raise ValueError("consumer wheel identity must be a SHA-256 digest")
    if (value.get("schema") != "uvicorn-rs-installed-wheel-consumer@1" or value.get("version") != version
            or value.get("wheel_sha256") != wheel_sha or value.get("cli_help") != "passed"
            or SHA256.fullmatch(str(value.get("native_sha256", ""))) is None
            or SHA256.fullmatch(str(value.get("consumer_probe_sha256", ""))) is None):
        raise ValueError("installed-wheel consumer identity/CLI evidence mismatch")
    if native_sha is not None and value["native_sha256"] != native_sha:
        raise ValueError("consumer imported a different native module")
    deployment = value.get("cli_tls_and_shutdown", {})
    if not isinstance(deployment, dict):
        raise TypeError("installed-wheel CLI/TLS/shutdown evidence must be an object")
    if value.get("platform") == "win32":
        if deployment.get("status") != "not_run":
            raise ValueError("Windows consumer must identify the POSIX-only CLI/TLS/signal probe as not_run")
    elif (
        deployment.get("status") != "passed"
        or deployment.get("command") != "python -m uvicorn_rs module:app --certfile ... --keyfile ..."
        or deployment.get("http_status") != 200
        or deployment.get("http_body") != "startup-token:0"
        or not isinstance(deployment.get("tls_version"), str)
        or not deployment["tls_version"].startswith("TLS")
        or deployment.get("alpn") != "http/1.1"
        or deployment.get("held_request_cancelled") is not True
        or deployment.get("lifespan_shutdown_completed") is not True
        or deployment.get("signal") != "SIGTERM"
        or deployment.get("exit_code") != 0
        or deployment.get("shutdown_bound_seconds") != 5
        or not isinstance(deployment.get("shutdown_elapsed_seconds"), (int, float))
        or deployment["shutdown_elapsed_seconds"] > 5
    ):
        raise ValueError("installed-wheel CLI/TLS/shutdown evidence is incomplete or failed")
    live = value.get("live_asgi", {})
    if (live.get("status") != "passed" or live.get("events") != ["startup", "http.complete", "shutdown"]
            or any(live.get(key) is not True for key in ("caller_loop_thread_context_preserved", "server_cancellation_propagated", "caller_loop_alive"))):
        raise ValueError("installed-wheel live consumer outcomes are incomplete or failed")


def validate_source_consumer(value: dict, version: str, sdist: dict) -> None:
    if value.get("schema") != "uvicorn-rs-source-consumer@1" or value.get("status") != "passed" or value.get("sdist_sha256") != sdist["sha256"]:
        raise ValueError("source consumer does not identify the exact passed source archive")
    hashes = value.get("source_hashes", {})
    if hashes != sdist["source_hashes"]:
        raise ValueError("source consumer must record every packaged checkout input with exact archive hashes")
    command = value.get("build_command", [])
    if not isinstance(command, list) or command[:2] != ["maturin", "build"] or not {"--release", "--locked"} <= set(command):
        raise ValueError("source consumer did not record a locked release rebuild")
    validate_consumer(value.get("consumer", {}), version, value.get("wheel_sha256"))


def validate_packaged_parity(path: Path, native_sha: str) -> None:
    from check_ci_evidence import validate_parity

    validate_parity(load_json(path), expected_native_sha256=native_sha, offline=True)


def command_output(command: list[str]) -> str:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True, timeout=30).stdout.strip()


def record(args: argparse.Namespace) -> None:
    if COMMIT.fullmatch(args.commit) is None or command_output(["git", "rev-parse", "HEAD"]) != args.commit:
        raise ValueError("expected commit must be the full checked-out Git commit")
    directory = args.directory.resolve()
    if not directory.is_dir() or args.output.resolve() != directory / f"build-manifest-{args.platform}.json":
        raise ValueError("manifest output must be build-manifest-PLATFORM.json within the artifact directory")
    if args.output.exists():
        raise ValueError("manifest already exists; preserve it and use a fresh artifact directory")
    version = project_versions()["Cargo.toml"]
    license_contract()
    inputs = source_hashes()
    tracked = set(command_output(["git", "ls-files"]).splitlines())
    dirty = bool(command_output(["git", "status", "--porcelain", "--untracked-files=no"])) or not set(inputs) <= tracked
    if dirty and not args.allow_dirty:
        raise ValueError("source checkout is dirty; --allow-dirty records local preparation only")
    names = {path.name for path in directory.iterdir()}
    wheels = [directory / name for name in names if name.endswith(".whl")]
    if len(wheels) != 1:
        raise ValueError("each platform producer must contain exactly one wheel")
    wheel = inspect_wheel(wheels[0], version, args.platform)
    expected = {wheel["filename"], f"consumer-{args.platform}.json"}
    packages = {wheel["filename"]: wheel}
    if args.platform == "linux-x86_64":
        expected |= {f"uvicorn_rs-{version}.tar.gz", "consumer-sdist.json", "parity-linux-x86_64.json"}
        sdist = inspect_sdist(directory / f"uvicorn_rs-{version}.tar.gz", version)
        packages[sdist["filename"]] = sdist
        validate_source_consumer(load_json(directory / "consumer-sdist.json"), version, sdist)
        validate_packaged_parity(directory / "parity-linux-x86_64.json", wheel["native"]["sha256"])
    if names != expected or any(path.is_symlink() or not path.is_file() for path in directory.iterdir()):
        raise ValueError(f"unexpected platform artifact inventory: expected {sorted(expected)}, found {sorted(names)}")
    validate_consumer(load_json(directory / f"consumer-{args.platform}.json"), version, wheel["sha256"], wheel["native"]["sha256"])
    flag_names = {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"}
    flag_names.update(name for name in os.environ if name.startswith("CARGO_TARGET_") and name.endswith("_RUSTFLAGS"))
    if any(os.environ.get(name) for name in flag_names) or any(os.environ.get(name) for name in os.environ if "LLVM_COV" in name or name.startswith("UVICORN_RS_COVERAGE_") or name == "LLVM_PROFILE_FILE"):
        raise ValueError("normal candidate requires empty Rust flags/wrappers and no coverage controls")
    rustc = command_output(["rustc", "-vV"])
    host = next((line[6:] for line in rustc.splitlines() if line.startswith("host: ")), None)
    if host != PLATFORMS[args.platform]:
        raise ValueError("producer host differs from declared native target")
    value = {"schema": "uvicorn-rs-platform-build@1", "state": "local preparation" if dirty else "candidate",
             "commit": args.commit, "version": version, "platform": args.platform, "target": host,
             "source_dirty": dirty, "source_hashes": inputs, "source_sha256": inputs["src/lib.rs"],
             "recorded_at": datetime.now(timezone.utc).isoformat(), "license_expression": LICENSE_EXPRESSION,
             "publication_blockers": ["dirty source checkout"] if dirty else [],
             "toolchain": {"rustc": rustc, "cargo": command_output(["cargo", "--version"]),
                           "maturin": command_output(["maturin", "--version"]), "python": sys.version},
             "build": {"wheel_command": ["maturin", "build", "--release", "--locked", "--interpreter", "python", "--out", "dist"],
                       "features": ["pyo3/extension-module"], "profile": "release", "locked": True,
                       "environment": {name: "" for name in sorted(flag_names)}},
             "packages": packages, "files": {name: file_sha256(directory / name) for name in sorted(expected)}}
    if source_hashes() != inputs:
        raise ValueError("source inputs changed during artifact inspection")
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "recorded", "state": value["state"], "manifest": str(args.output), "sha256": file_sha256(args.output)}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    producer = commands.add_parser("record")
    producer.add_argument("--directory", type=Path, required=True)
    producer.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    producer.add_argument("--commit", required=True)
    producer.add_argument("--output", type=Path, required=True)
    producer.add_argument("--allow-dirty", action="store_true", help="record blocked local preparation, never an assemblable candidate")
    args = parser.parse_args()
    try:
        record(args)
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, configparser.Error, zipfile.BadZipFile, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"release evidence: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
