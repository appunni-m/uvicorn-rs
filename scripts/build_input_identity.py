"""Hash the source files that can affect a uvicorn-rs wheel build.

This module stays compatible with Python 3.9 because the release consumer
probe also runs on the project's minimum supported interpreter.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def build_input_hashes(root: Path) -> dict[str, str]:
    """Return sorted SHA-256 hashes for manifests, native code and Python code."""
    root = Path(root).resolve()
    paths = {
        root / name
        for name in (
            "Cargo.toml",
            "Cargo.lock",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "LICENSE",
            "LICENSE-BSD-3-Clause",
            "LICENSE-MIT",
            "build.rs",
        )
    }
    for directory in (root / "src", root / "crates"):
        if directory.exists():
            paths.update(path for path in directory.rglob("*") if path.is_file())
    for directory in (root / "python" / "uvicorn_rs", root / "python" / "uvicorn"):
        if directory.exists():
            paths.update(
                path
                for path in directory.rglob("*")
                if path.is_file() and (path.suffix == ".py" or path.name == "py.typed")
            )
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("wheel build inputs must be regular files")
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }
