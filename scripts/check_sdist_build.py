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
import venv


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
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
                "LICENSE", "LICENSE-BSD-3-Clause", "LICENSE-MIT"]
    for name in required:
        if not (source / name).is_file():
            raise ValueError(f"source archive lacks required input: {name}")
    archive_files = {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in source.rglob("*") if path.is_file()}
    hashes = {}
    for packaged in sorted(source.rglob("*")):
        if not packaged.is_file():
            continue
        name = packaged.relative_to(source).as_posix()
        if name == "PKG-INFO":
            continue  # Generated distribution metadata is inspected by the package verifier.
        data = packaged.read_bytes()
        checkout = ROOT / name
        if not checkout.is_file() or data != checkout.read_bytes():
            raise ValueError(f"source archive differs from reviewed checkout: {name}")
        hashes[name] = hashlib.sha256(data).hexdigest()
    environment = os.environ.copy()
    for key in list(environment):
        if ("LLVM_COV" in key or key.startswith("UVICORN_RS_COVERAGE_")
                or key in {"LLVM_PROFILE_FILE", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTFLAGS"}):
            environment.pop(key)
    environment.update(RUSTC_WRAPPER="", RUSTC_WORKSPACE_WRAPPER="",
                       CARGO_TARGET_DIR=str(output / "cargo-target"))
    wheels = output / "wheels"
    command = ["maturin", "build", "--release", "--locked", "--interpreter", sys.executable,
               "--out", str(wheels)]
    with (output / "build.log").open("w") as log:
        subprocess.run(command, cwd=source, env=environment, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=1800)
    artifacts = list(wheels.glob("*.whl"))
    if len(artifacts) != 1:
        raise ValueError("source rebuild did not produce exactly one wheel")
    consumer = output / "consumer-environment"
    venv.EnvBuilder(with_pip=True).create(consumer)
    python = consumer / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-index",
                    str(artifacts[0])], env=environment, check=True, timeout=120)
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
              "source_hashes": hashes, "build_command": command,
              "wheel_sha256": hashlib.sha256(artifacts[0].read_bytes()).hexdigest(),
              "consumer": json.loads(receipt.read_text()),
              "scope": "clean extracted source build and real installed-wheel smoke; not full oracle parity"}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "passed", "receipt": str(output / "result.json")}))


if __name__ == "__main__":
    main()
