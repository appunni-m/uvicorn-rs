#!/usr/bin/env python3
"""Verify clean installation, Uvicorn replacement, and rollback for one wheel."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def _python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(arguments: list[str], *, cwd: Path, timeout: int = 300) -> None:
    subprocess.run(arguments, cwd=cwd, check=True, timeout=timeout)


def _probe(python: Path, mode: str, upstream_version: str, cwd: Path) -> None:
    source = r"""
import importlib.metadata
import pathlib
import subprocess
import sys
import uvicorn
import uvicorn.main

mode, upstream_version, probe_cwd = sys.argv[1:]
if mode == "upstream":
    assert importlib.metadata.version("uvicorn") == upstream_version
    assert uvicorn.__version__ == upstream_version
    try:
        importlib.metadata.version("uvicorn-rs-py")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError("replacement distribution remains after rollback")
else:
    distribution = importlib.metadata.distribution("uvicorn-rs-py")
    assert distribution.metadata["Name"] == "uvicorn-rs-py"
    assert uvicorn.__version__ == upstream_version
    try:
        importlib.metadata.version("uvicorn")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError("upstream uvicorn metadata remains after replacement")
    assert callable(uvicorn.main.main)
    commands = (
        ([sys.executable, "-m", "uvicorn", "--help"], "Usage: python -m uvicorn [OPTIONS] APP"),
    )
    for command, expected_usage in commands:
        result = subprocess.run(command, cwd=probe_cwd, capture_output=True, text=True, check=True, timeout=20)
        assert result.stdout.splitlines()[0] == expected_usage
"""
    _run([str(python), "-c", source, mode, upstream_version, str(cwd)], cwd=cwd, timeout=30)
    if mode == "replacement":
        script = python.parent / ("uvicorn.exe" if os.name == "nt" else "uvicorn")
        result = subprocess.run(
            [str(script), "--help"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        assert result.stdout.splitlines()[0] == "Usage: uvicorn [OPTIONS] APP"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--upstream-version", default="0.54.0")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        parser.error(f"wheel does not exist: {wheel}")
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-replacement-install-") as temporary:
        root = Path(temporary)
        clean = root / "clean"
        replacement = root / "replacement"
        venv.EnvBuilder(with_pip=True).create(clean)
        venv.EnvBuilder(with_pip=True).create(replacement)
        clean_python = _python(clean)
        replacement_python = _python(replacement)
        _run([str(clean_python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", str(wheel)], cwd=root)
        _probe(clean_python, "replacement", args.upstream_version, root)

        _run([str(replacement_python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
              f"uvicorn=={args.upstream_version}"], cwd=root)
        _probe(replacement_python, "upstream", args.upstream_version, root)
        _run([str(replacement_python), "-m", "pip", "uninstall", "--disable-pip-version-check", "--yes", "uvicorn"], cwd=root)
        _run([str(replacement_python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", str(wheel)], cwd=root)
        _probe(replacement_python, "replacement", args.upstream_version, root)
        _run([str(replacement_python), "-m", "pip", "uninstall", "--disable-pip-version-check", "--yes", "uvicorn-rs-py"], cwd=root)
        _run([str(replacement_python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
              f"uvicorn=={args.upstream_version}"], cwd=root)
        _probe(replacement_python, "upstream", args.upstream_version, root)
    print("clean install, Uvicorn replacement, and rollback passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
