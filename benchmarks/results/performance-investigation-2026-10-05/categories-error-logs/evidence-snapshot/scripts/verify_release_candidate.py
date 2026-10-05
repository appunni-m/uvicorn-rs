#!/usr/bin/env python3
"""Validate the candidate files collected from the exact successful main CI run."""

from __future__ import annotations

import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path


def fail(message: str) -> int:
    print(f"release candidate: {message}", file=sys.stderr)
    return 1


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: verify_release_candidate.py DIRECTORY VERSION COMMIT",
            file=sys.stderr,
        )
        return 2

    root = Path(sys.argv[1])
    version = sys.argv[2]
    commit = sys.argv[3]
    if not root.is_dir():
        return fail(f"artifact directory does not exist: {root}")

    files = sorted(path for path in root.iterdir() if path.is_file())
    wheels = [path for path in files if path.suffix == ".whl"]
    sdists = [path for path in files if path.name.endswith(".tar.gz")]
    if len(wheels) != 3 or len(sdists) != 1 or len(files) != 4:
        return fail(
            "expected three platform wheels and one source archive; "
            f"found {len(wheels)} wheels and {len(sdists)} sdists"
        )

    platforms: set[str] = set()
    for wheel in wheels:
        parts = wheel.name[:-4].rsplit("-", maxsplit=3)
        if len(parts) != 4:
            return fail(f"invalid wheel filename: {wheel.name}")
        distribution_version, python_tag, abi_tag, platform_tag = parts
        if distribution_version != f"uvicorn_rs-{version}":
            return fail(f"wheel has unexpected name/version: {wheel.name}")
        if python_tag != "cp39" or abi_tag != "abi3":
            return fail(
                "wheel does not expose the declared CPython abi3 floor: "
                f"{wheel.name}"
            )

        if "manylinux" in platform_tag and "x86_64" in platform_tag:
            platform = "linux-x86_64"
        elif "linux" in platform_tag and "x86_64" in platform_tag:
            platform = "linux-x86_64"
        elif "macosx" in platform_tag and "arm64" in platform_tag:
            platform = "macos-arm64"
        elif "win_amd64" in platform_tag:
            platform = "windows-x86_64"
        else:
            return fail(f"unexpected wheel platform tag: {wheel.name}")
        if platform in platforms:
            return fail(f"duplicate wheel platform: {platform}")
        platforms.add(platform)

        try:
            with zipfile.ZipFile(wheel) as archive:
                metadata_names = [
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/METADATA")
                ]
                wheel_metadata_names = [
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/WHEEL")
                ]
                if len(metadata_names) != 1:
                    return fail(f"expected one wheel METADATA file: {wheel.name}")
                if len(wheel_metadata_names) != 1:
                    return fail(f"expected one wheel WHEEL file: {wheel.name}")
                metadata = archive.read(metadata_names[0]).decode("utf-8")
                wheel_metadata = archive.read(wheel_metadata_names[0]).decode("utf-8")
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
            return fail(f"cannot inspect {wheel.name}: {exc}")
        if (
            "Name: uvicorn-rs\n" not in metadata
            or f"Version: {version}\n" not in metadata
        ):
            return fail(
                f"wheel metadata does not match version {version}: {wheel.name}"
            )
        expected_wheel_tag = f"Tag: {python_tag}-{abi_tag}-{platform_tag}\n"
        if expected_wheel_tag not in wheel_metadata:
            return fail(f"wheel metadata tag does not match its filename: {wheel.name}")

    if platforms != {"linux-x86_64", "macos-arm64", "windows-x86_64"}:
        return fail(f"platform matrix mismatch: {sorted(platforms)}")

    expected_sdist = f"uvicorn_rs-{version}.tar.gz"
    if sdists[0].name != expected_sdist:
        return fail(f"unexpected source archive name: {sdists[0].name}")
    try:
        with tarfile.open(sdists[0], mode="r:gz") as archive:
            members = {Path(member.name).as_posix() for member in archive.getmembers()}
    except (OSError, tarfile.TarError) as exc:
        return fail(f"cannot inspect {sdists[0].name}: {exc}")
    required_suffixes = {
        "/Cargo.toml",
        "/pyproject.toml",
        "/README.md",
        "/src/lib.rs",
        "/python/uvicorn_rs/cli.py",
    }
    missing = [
        suffix
        for suffix in sorted(required_suffixes)
        if not any(name.endswith(suffix) for name in members)
    ]
    if missing:
        return fail(
            "source archive is missing required project files: "
            f"{', '.join(missing)}"
        )

    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in files
    )
    (root / "SHA256SUMS").write_text(checksums)
    (root / "candidate.txt").write_text(f"version={version}\ncommit={commit}\n")
    print(
        f"verified {len(wheels)} wheels and one source archive "
        f"for {version} at {commit}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
