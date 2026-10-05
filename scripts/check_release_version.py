#!/usr/bin/env python3
"""Check Rust, Python and both lockfiles against one candidate version."""

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
    """Return synchronized versions, or reject missing/ambiguous metadata."""
    documents = {
        name: tomllib.loads((root / name).read_text(encoding="utf-8"))
        for name in ("Cargo.toml", "pyproject.toml", "Cargo.lock", "uv.lock")
    }
    cargo = documents["Cargo.toml"]["package"]
    python = documents["pyproject.toml"]["project"]
    if cargo["name"] != "uvicorn-rs" or python["name"] != "uvicorn-rs":
        raise ValueError("Cargo and Python package names must both be uvicorn-rs")
    versions = {"Cargo.toml": cargo["version"], "pyproject.toml": python["version"]}
    for name in ("Cargo.lock", "uv.lock"):
        rows = [
            package for package in documents[name]["package"]
            if package["name"] in {"uvicorn-rs", "uvicorn_rs"}
            and (name != "uv.lock" or package.get("source", {}).get("editable") == ".")
        ]
        if len(rows) != 1:
            raise ValueError(f"{name}: expected one locked project entry, found {len(rows)}")
        versions[name] = rows[0]["version"]
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
        print(f"release version {versions['Cargo.toml']} matches Cargo.toml, pyproject.toml, Cargo.lock, and uv.lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
