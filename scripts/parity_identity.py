"""Source identity helpers for input-driven parity receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


FIXED_RUNTIME_PATHS = (
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "uv.lock",
    "crates/uvicorn-rs/Cargo.toml",
    "crates/uvicorn-rs/third-party/h2/Cargo.toml",
    "crates/uvicorn-rs/third-party/hyper/Cargo.toml",
    "crates/asgi-lifespan-protocol-rs/Cargo.toml",
)
OPTIONAL_RUNTIME_PATHS = (
    ".cargo/config.toml",
    ".cargo/config",
    ".rust-toolchain",
    "rust-toolchain.toml",
    "build.rs",
    "crates/uvicorn-rs/build.rs",
    "crates/asgi-lifespan-protocol-rs/build.rs",
)
RUST_SOURCE_ROOTS = (
    "src",
    "crates/uvicorn-rs/src",
    "crates/uvicorn-rs/third-party/h2/src",
    "crates/uvicorn-rs/third-party/hyper/src",
    "crates/asgi-lifespan-protocol-rs/src",
)
PYTHON_PACKAGE_ROOTS = (
    "python/uvicorn",
    "python/uvicorn_rs",
)


def runtime_source_hashes(root: Path) -> dict[str, str]:
    """Hash only files that can change the Python server exercised by parity."""
    paths: set[Path] = set()
    for relative in FIXED_RUNTIME_PATHS:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        paths.add(path)
    for relative in OPTIONAL_RUNTIME_PATHS:
        path = root / relative
        if path.exists():
            if not path.is_file():
                raise ValueError(f"runtime source path is not a regular file: {relative}")
            paths.add(path)
    for relative in RUST_SOURCE_ROOTS:
        directory = root / relative
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        paths.update(path for path in directory.rglob("*.rs") if path.is_file())
    for relative in PYTHON_PACKAGE_ROOTS:
        directory = root / relative
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        paths.update(
            path
            for path in directory.rglob("*")
            if path.is_file() and (path.suffix in {".py", ".pyi"} or path.name == "py.typed")
        )
    if any(path.is_symlink() for path in paths):
        raise ValueError("runtime source identity cannot include symlinks")
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def runtime_source_digest(source_hashes: Mapping[str, str]) -> str:
    """Return a stable digest for the path-to-content-hash inventory."""
    encoded = json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
