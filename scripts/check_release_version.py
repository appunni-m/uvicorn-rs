#!/usr/bin/env python3
"""Check Rust, Python, native-contract and lockfile versions for a candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def project_versions(root: Path = ROOT, expected: str | None = None) -> dict[str, str]:
    """Return synchronized versions for the Python adapter and native crate."""
    documents = {
        name: tomllib.loads((root / name).read_text(encoding="utf-8"))
        for name in (
            "Cargo.toml",
            "crates/uvicorn-rs/Cargo.toml",
            "crates/native-app-contract/Cargo.toml",
            "pyproject.toml",
            "Cargo.lock",
            "uv.lock",
        )
    }
    cargo = documents["Cargo.toml"]["package"]
    native = documents["crates/uvicorn-rs/Cargo.toml"]["package"]
    lifecycle = documents["crates/native-app-contract/Cargo.toml"]["package"]
    python = documents["pyproject.toml"]["project"]
    if cargo["name"] != "uvicorn-rs-py" or python["name"] != "uvicorn-rs-py":
        raise ValueError("root Cargo and Python distributions must both be uvicorn-rs-py")
    if native["name"] != "uvicorn-rs":
        raise ValueError("crates/uvicorn-rs must define the Python-free uvicorn-rs package")
    if lifecycle["name"] != "native-app-contract":
        raise ValueError("crates/native-app-contract must define the shared native lifecycle package")

    def locked_package(lock_name: str, package_name: str, *, editable: bool = False) -> dict:
        rows = [
            package
            for package in documents[lock_name]["package"]
            if package["name"] == package_name
            and (
                not editable
                or package.get("source", {}).get("editable") == "."
            )
        ]
        if len(rows) != 1:
            raise ValueError(
                f"{lock_name}: expected one locked {package_name} entry, found {len(rows)}"
            )
        return rows[0]

    versions = {
        "Cargo.toml": cargo["version"],
        "crates/uvicorn-rs/Cargo.toml": native["version"],
        "crates/native-app-contract/Cargo.toml": lifecycle["version"],
        "pyproject.toml": python["version"],
        "Cargo.lock:uvicorn-rs-py": locked_package("Cargo.lock", "uvicorn-rs-py")["version"],
        "Cargo.lock:uvicorn-rs": locked_package("Cargo.lock", "uvicorn-rs")["version"],
        "Cargo.lock:native-app-contract": locked_package("Cargo.lock", "native-app-contract")["version"],
        "uv.lock": locked_package("uv.lock", "uvicorn-rs-py", editable=True)["version"],
    }
    expected = expected if expected is not None else versions["Cargo.toml"]
    if not isinstance(expected, str) or VERSION.fullmatch(expected) is None:
        raise ValueError("version must use canonical MAJOR.MINOR.PATCH")
    if any(version != expected for version in versions.values()):
        details = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise ValueError(f"release version {expected} does not match project metadata: {details}")
    return versions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        versions = project_versions(args.root, args.version)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"release version: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"version": versions["Cargo.toml"], "sources": versions}, sort_keys=True))
    else:
        print(
            f"release version {versions['Cargo.toml']} matches the uvicorn-rs-py "
            "Python adapter, uvicorn-rs native crate, shared lifecycle crate, and locks"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
