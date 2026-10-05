#!/usr/bin/env python3
"""Check that Rust, Python, and lockfile versions agree with a release tag."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


def main() -> int:
    if len(sys.argv) not in {1, 2}:
        print("usage: check_release_version.py [MAJOR.MINOR.PATCH]", file=sys.stderr)
        return 2

    expected = sys.argv[1] if len(sys.argv) == 2 else None
    if expected is not None and re.fullmatch(r"\d+\.\d+\.\d+", expected) is None:
        print("expected version must use MAJOR.MINOR.PATCH", file=sys.stderr)
        return 2
    cargo_manifest = tomllib.loads(Path("Cargo.toml").read_text())
    python_manifest = tomllib.loads(Path("pyproject.toml").read_text())
    cargo_lock = tomllib.loads(Path("Cargo.lock").read_text())
    uv_lock = tomllib.loads(Path("uv.lock").read_text())

    versions = {
        "Cargo.toml": cargo_manifest["package"]["version"],
        "pyproject.toml": python_manifest["project"]["version"],
    }
    for filename, data in (("Cargo.lock", cargo_lock), ("uv.lock", uv_lock)):
        matches = [
            package["version"]
            for package in data["package"]
            if package["name"] in {"uvicorn-rs", "uvicorn_rs"}
            and (
                filename != "uv.lock"
                or package.get("source", {}).get("editable") == "."
            )
        ]
        if len(matches) != 1:
            print(
                f"{filename}: expected one locked uvicorn-rs entry, "
                f"found {len(matches)}",
                file=sys.stderr,
            )
            return 1
        versions[filename] = matches[0]

    expected = expected or versions["Cargo.toml"]
    mismatches = {
        name: version for name, version in versions.items() if version != expected
    }
    if mismatches:
        details = ", ".join(f"{name}={version}" for name, version in versions.items())
        print(
            f"release version {expected} does not match project metadata: {details}",
            file=sys.stderr,
        )
        return 1

    print(
        f"release version {expected} matches Cargo.toml, pyproject.toml, "
        "Cargo.lock, and uv.lock"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
