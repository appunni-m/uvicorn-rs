#!/usr/bin/env python3
"""Build exact Cargo archives as an external consumer and exercise HTTP/3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
CRATES = (
    "native-app-contract",
    "uvicorn-rs-h3",
    "uvicorn-rs-h3-quinn",
    "uvicorn-rs",
)
EXPECTED_CASE = "http3.truncated-data-frame-recovery-after-protocol-error"
FRAME_ERROR = 262


class ConsumerError(RuntimeError):
    """The standalone archive consumer did not satisfy its contract."""


def clean_build_environment() -> dict[str, str]:
    environment = os.environ.copy()
    controls = {
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "CARGO_BUILD_RUSTFLAGS",
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
        "LLVM_PROFILE_FILE",
    }
    controls.update(
        name
        for name in environment
        if name.startswith("CARGO_TARGET_") and name.endswith("_RUSTFLAGS")
    )
    controls.update(
        name
        for name in environment
        if "LLVM_COV" in name or name.startswith("UVICORN_RS_COVERAGE_")
    )
    for name in controls:
        environment[name] = ""
    return environment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=clean_build_environment(),
    )
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip()
        raise ConsumerError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{diagnostic[-4000:]}"
        )
    return result


def extract_crate(archive: Path, package: str, version: str, destination: Path) -> Path:
    root_name = f"{package}-{version}"
    target = destination / root_name
    target.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as crate:
        for member in crate.getmembers():
            name = PurePosixPath(member.name)
            if (
                name.is_absolute()
                or not name.parts
                or name.parts[0] != root_name
                or any(part in {"", ".", ".."} for part in name.parts)
                or not (member.isdir() or member.isfile())
            ):
                raise ConsumerError(f"unsafe or unexpected Cargo archive member: {member.name}")
            output = destination.joinpath(*name.parts)
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            source = crate.extractfile(member)
            if source is None:
                raise ConsumerError(f"Cargo archive member has no content: {member.name}")
            output.parent.mkdir(parents=True, exist_ok=True)
            with source, output.open("wb") as target_file:
                shutil.copyfileobj(source, target_file)
            output.chmod(member.mode & 0o777)
    if not (target / "Cargo.toml").is_file() or not (target / "src").is_dir():
        raise ConsumerError(f"Cargo archive is missing its manifest or source: {archive.name}")
    return target


def ensure_clean_source(commit: str, *, allow_dirty: bool) -> bool:
    head = run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    if head != commit:
        raise ConsumerError(f"source commit mismatch: expected {commit}, got {head}")
    status = run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT
    ).stdout.strip()
    dirty = bool(status)
    if dirty and not allow_dirty:
        raise ConsumerError("standalone archive evidence requires a clean source checkout")
    return dirty


def build_consumer(version: str, extracted: dict[str, Path], scratch: Path) -> Path:
    consumer = ROOT / "tools/standalone-h3-consumer/Cargo.toml"
    manifest = consumer.read_text(encoding="utf-8")
    dependency = re.search(r'(?m)^\s*uvicorn-rs\s*=\s*"([^"]+)"\s*$', manifest)
    if (
        dependency is None
        or dependency.group(1) != version
        or re.search(r"(?m)^\s*\[patch(?:\.|\])", manifest)
        or re.search(r"(?m)^\s*path\s*=", manifest)
    ):
        raise ConsumerError(
            "standalone consumer must use the versioned registry dependency without a manifest patch"
        )
    target = ROOT / "target/standalone-h3-consumer"
    command = [
        "cargo",
        "build",
        "--locked",
        "--manifest-path",
        str(consumer),
        "--target-dir",
        str(target),
    ]
    for package in CRATES:
        command.extend(
            [
                "--config",
                f'patch.crates-io.{package}.path="{extracted[package].as_posix()}"',
            ]
        )
    run(command, cwd=scratch)
    executable = target / "debug" / "uvicorn-rs-standalone-h3-consumer"
    if os.name == "nt":
        executable = executable.with_suffix(".exe")
    if not executable.is_file():
        raise ConsumerError("Cargo completed without producing the standalone consumer")
    return executable


def build_probe(scratch: Path) -> Path:
    target = ROOT / "target/standalone-h3-probe"
    run(
        [
            "cargo",
            "build",
            "--locked",
            "--manifest-path",
            str(ROOT / "tools/http3-probe/Cargo.toml"),
            "--bin",
            "parity-http3",
            "--target-dir",
            str(target),
        ],
        cwd=ROOT,
    )
    executable = target / "debug" / "parity-http3"
    if os.name == "nt":
        executable = executable.with_suffix(".exe")
    if not executable.is_file():
        raise ConsumerError("Cargo completed without producing the HTTP/3 probe")
    return executable


def create_certificate(scratch: Path) -> tuple[Path, Path]:
    key = scratch / "server-key.pem"
    certificate = scratch / "server-cert.pem"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        cwd=scratch,
    )
    return certificate, key


def start_server(executable: Path, certificate: Path, key: Path, scratch: Path) -> tuple[subprocess.Popen[str], str]:
    log_path = scratch / "server.log"
    with (scratch / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(executable), str(certificate), str(key)],
            cwd=scratch,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
        )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise ConsumerError("standalone server has no readiness output pipe")
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout=15):
            process.kill()
            process.wait()
            raise ConsumerError("standalone server did not announce readiness")
        line = process.stdout.readline().strip()
    if not line.startswith("READY "):
        diagnostic = log_path.read_text(encoding="utf-8", errors="replace")
        process.kill()
        process.wait()
        raise ConsumerError(
            f"standalone server returned invalid readiness: {line!r}; "
            f"server log: {diagnostic[-3000:]}"
        )
    return process, line.removeprefix("READY ")


def malformed_frame_probe(probe: Path, address: str, certificate: Path, scratch: Path) -> int:
    ready = scratch / "malformed-ready"
    release = scratch / "malformed-release"
    process = subprocess.Popen(
        [str(probe), address, str(certificate)],
        cwd=scratch,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.stdin is None:
        raise ConsumerError("HTTP/3 probe has no input pipe")
    specification = {
        "method": "POST",
        "path": "/h3-upload-disconnect",
        "headers": [["content-length", "1000"]],
        "body_hex": "",
        "malformed_data_frame_after_headers": True,
        "malformed_result_file": str(ready),
        "malformed_release_file": str(release),
    }
    process.stdin.write(json.dumps(specification))
    process.stdin.close()
    process.stdin = None
    deadline = time.monotonic() + 15
    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    if not ready.exists():
        process.kill()
        stdout, stderr = process.communicate()
        raise ConsumerError(
            "HTTP/3 probe did not send the malformed frame: "
            f"{(stderr or stdout).strip()[-2000:]}"
        )
    release.touch()
    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise ConsumerError("HTTP/3 probe hung waiting for the peer's connection error") from error
    if process.returncode != 0:
        raise ConsumerError(f"malformed-frame probe failed: {(stderr or stdout).strip()[-2000:]}")
    try:
        observation = json.loads(stdout)
        code = observation.get("peer_close_code")
    except json.JSONDecodeError as error:
        raise ConsumerError(f"malformed-frame probe returned invalid JSON: {stdout!r}") from error
    if code != FRAME_ERROR:
        raise ConsumerError(f"expected H3_FRAME_ERROR ({FRAME_ERROR}), observed {code!r}")
    return code


def healthy_fresh_connection_probe(probe: Path, address: str, certificate: Path, scratch: Path) -> int:
    completed = subprocess.run(
        [str(probe), address, str(certificate)],
        cwd=scratch,
        input=json.dumps(
            {"method": "GET", "path": "/state", "headers": [], "body_hex": ""}
        ),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise ConsumerError(
            f"fresh HTTP/3 connection failed: {(completed.stderr or completed.stdout).strip()[-2000:]}"
        )
    try:
        observation = json.loads(completed.stdout)
        status = observation.get("status")
    except json.JSONDecodeError as error:
        raise ConsumerError(f"fresh-connection probe returned invalid JSON: {completed.stdout!r}") from error
    if status != 200 or observation.get("body_hex") != b"healthy".hex():
        raise ConsumerError(
            "fresh HTTP/3 connection expected status 200 and body 'healthy', "
            f"observed status={status!r}, body_hex={observation.get('body_hex')!r}"
        )
    return status


def execute(
    packages: Path,
    version: str,
    commit: str,
    output: Path,
    *,
    allow_dirty: bool,
) -> dict[str, object]:
    source_dirty = ensure_clean_source(commit, allow_dirty=allow_dirty)
    hashes: dict[str, str] = {}
    archives: dict[str, Path] = {}
    for package in CRATES:
        archive = packages / f"{package}-{version}.crate"
        if not archive.is_file() or archive.is_symlink():
            raise ConsumerError(f"missing regular Cargo archive: {archive.name}")
        hashes[archive.name] = sha256(archive)
        archives[package] = archive

    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-standalone-h3-") as temporary:
        scratch = Path(temporary)
        extracted_root = scratch / "archives"
        extracted_root.mkdir()
        extracted = {
            package: extract_crate(archives[package], package, version, extracted_root)
            for package in CRATES
        }
        server = build_consumer(version, extracted, scratch)
        probe = build_probe(scratch)
        certificate, key = create_certificate(scratch)
        process, address = start_server(server, certificate, key, scratch)
        server_log = scratch / "server.log"
        try:
            observed_error = malformed_frame_probe(probe, address, certificate, scratch)
            follow_up_status = healthy_fresh_connection_probe(
                probe, address, certificate, scratch
            )
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process.returncode != 0:
                diagnostic = server_log.read_text(encoding="utf-8", errors="replace")
                raise ConsumerError(
                    f"standalone server exited with status {process.returncode}: {diagnostic[-3000:]}"
                )

    return {
        "schema": "uvicorn-rs-standalone-h3-consumer@1",
        "status": "passed",
        "source_commit": commit,
        "source_dirty": source_dirty,
        "crate_sha256": hashes[f"uvicorn-rs-{version}.crate"],
        "archive_sha256s": hashes,
        "input_case_id": EXPECTED_CASE,
        "registry_dependencies": [
            "native-app-contract",
            "uvicorn-rs-h3",
            "uvicorn-rs-h3-quinn",
        ],
        "dependency_source": "exact-candidate-crate-archives",
        "workspace_h3_patch": False,
        "expected_h3_error_code": FRAME_ERROR,
        "observed_h3_error_code": observed_error,
        "follow_up_connection_reused": False,
        "follow_up_request_status": follow_up_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", type=Path, help="directory containing the four exact .crate archives")
    parser.add_argument("version")
    parser.add_argument("commit")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--allow-dirty-source",
        action="store_true",
        help="run a local diagnostic; the resulting receipt is marked dirty and cannot pass publication",
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ConsumerError(f"refusing to overwrite existing receipt: {args.output}")
        receipt = execute(
            args.packages.resolve(),
            args.version,
            args.commit,
            args.output.resolve(),
            allow_dirty=args.allow_dirty_source,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, sort_keys=True))
    except (ConsumerError, OSError, subprocess.SubprocessError, tarfile.TarError, ValueError) as error:
        parser.exit(1, f"standalone H3 archive consumer failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
