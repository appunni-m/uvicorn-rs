#!/usr/bin/env python3
"""Rebuild an actual source archive with locked dependencies and consume its wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from release_evidence import validate_sdist_source_contents


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maturin-version", default=os.environ.get("MATURIN_VERSION"),
                        help="pinned maturin version (defaults to MATURIN_VERSION)")
    parser.add_argument("--consumer-python", type=Path,
                        help="Python used for the isolated wheel consumer (defaults to the build interpreter)")
    parser.add_argument("--cargo-target-dir", type=Path,
                        help="Reuse a Cargo target cache; the default builds in a fresh directory under output-dir")
    args = parser.parse_args()
    archive_path = args.sdist.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = output / "source"
    sources.mkdir()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsafe source archive member: {member.name}")
        archive.extractall(sources, filter="data")
    roots = list(sources.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError("source archive must have exactly one package root")
    source = roots[0]
    required = ["Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock", "README.md", "src/lib.rs",
                "python/uvicorn_rs/__init__.py", "python/uvicorn_rs/server.py",
                "python/uvicorn_rs/cli.py", "python/uvicorn_rs/_bridge.py", "python/uvicorn_rs/__main__.py",
                "python/uvicorn/__init__.py", "python/uvicorn/main.py", "python/uvicorn/_types.py",
                "python/uvicorn/importer.py",
                "python/uvicorn/__main__.py", "python/uvicorn/py.typed",
                "LICENSE", "LICENSE-BSD-3-Clause", "LICENSE-MIT"]
    for name in required:
        if not (source / name).is_file():
            raise ValueError(f"source archive lacks required input: {name}")
    archive_files = {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in source.rglob("*") if path.is_file()}
    contents = {path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*") if path.is_file()}
    hashes = validate_sdist_source_contents(contents, ROOT)
    environment = os.environ.copy()
    for key in list(environment):
        if ("LLVM_COV" in key or key.startswith("UVICORN_RS_COVERAGE_")
                or key in {"LLVM_PROFILE_FILE", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS"}):
            environment.pop(key)
    environment.update(RUSTC_WRAPPER="", RUSTC_WORKSPACE_WRAPPER="",
                       CARGO_TARGET_DIR=str(
                           args.cargo_target_dir.resolve()
                           if args.cargo_target_dir is not None
                           else output / "cargo-target"
                       ))
    if not args.maturin_version:
        parser.error("--maturin-version or MATURIN_VERSION is required")
    wheels = output / "wheels"
    command = ["uvx", "--from", f"maturin=={args.maturin_version}", "maturin", "build",
               "--release", "--locked", "--interpreter", sys.executable, "--out", str(wheels)]
    with (output / "build.log").open("w") as log:
        subprocess.run(command, cwd=source, env=environment, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=1800)
    artifacts = list(wheels.glob("*.whl"))
    if len(artifacts) != 1:
        raise ValueError("source rebuild did not produce exactly one wheel")
    consumer = output / "consumer-environment"
    consumer_interpreter = args.consumer_python.resolve() if args.consumer_python else Path(sys.executable)
    if not consumer_interpreter.is_file() or not os.access(consumer_interpreter, os.X_OK):
        raise ValueError(f"consumer Python is not an executable file: {consumer_interpreter}")
    environment["UV_PROJECT_ENVIRONMENT"] = str(consumer)
    subprocess.run(
        ["uv", "sync", "--project", str(source), "--python", str(consumer_interpreter),
         "--locked", "--no-dev", "--no-install-project"],
        cwd=source, env=environment, check=True, timeout=300,
    )
    python = consumer / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), "--no-deps", "--offline",
         str(artifacts[0])],
        env=environment, check=True, timeout=120,
    )
    receipt = output / "consumer.json"
    subprocess.run([str(python), str(ROOT / "scripts/check_installed_wheel.py"),
                    "--wheel", str(artifacts[0]), "--output", str(receipt)],
                   cwd=output, env=environment, check=True, timeout=60)
    if {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()} != set(archive_files):
        raise ValueError("locked source rebuild changed the extracted file inventory")
    for name, digest in archive_files.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"locked source rebuild modified a package input: {name}")
    result = {"schema": "uvicorn-rs-source-consumer@1", "status": "passed",
              "sdist_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
              "source_hashes": hashes, "maturin_version": args.maturin_version,
              "build_command": command,
              "wheel_sha256": hashlib.sha256(artifacts[0].read_bytes()).hexdigest(),
              "consumer": json.loads(receipt.read_text()),
              "scope": "clean extracted source build and real installed-wheel smoke; not full oracle parity"}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "passed", "receipt": str(output / "result.json")}))


if __name__ == "__main__":
    main()
