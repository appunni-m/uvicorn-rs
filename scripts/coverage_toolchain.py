"""Resolve and receipt the exact Rust/LLVM executables used for coverage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any


class ToolchainError(RuntimeError):
    """A required coverage tool cannot be identified reproducibly."""


def _resolve_executable(name: str, environment_name: str | None = None) -> Path:
    configured = os.environ.get(environment_name) if environment_name else None
    if configured:
        words = shlex.split(configured)
        if len(words) != 1:
            raise ToolchainError(f"{environment_name} must name one executable path")
        candidate = Path(words[0]).expanduser()
        if candidate.is_absolute() or candidate.parent != Path("."):
            found = candidate if candidate.is_absolute() else Path.cwd() / candidate
        else:
            located = shutil.which(words[0])
            found = Path(located) if located else candidate
    else:
        located = shutil.which(name)
        if located is None:
            raise ToolchainError(f"{name} is not available on PATH")
        found = Path(located)
    absolute = Path(os.path.abspath(found))
    if not absolute.is_file():
        raise ToolchainError(f"{environment_name or name} does not resolve to a file: {absolute}")
    return absolute


def _capture(path: Path, arguments: tuple[str, ...]) -> dict[str, str]:
    try:
        result = subprocess.run(
            [str(path), *arguments], capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ToolchainError(f"cannot identify {path}: {error}") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise ToolchainError(f"cannot identify {path}: {(result.stderr or result.stdout)[-2000:]}")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "version": result.stdout.strip(),
    }


def capture_coverage_tools() -> tuple[dict[str, dict[str, str]], dict[str, Path]]:
    """Return exact executable receipts and paths for the active coverage toolchain."""
    rustc_entrypoint = _resolve_executable("rustc", "RUSTC")
    cargo = _resolve_executable("cargo")
    cargo_llvm_cov = _resolve_executable("cargo-llvm-cov")
    entrypoint_version = _capture(rustc_entrypoint, ("-vV",))
    host = next((line.split(": ", 1)[1] for line in entrypoint_version["version"].splitlines()
                 if line.startswith("host: ")), None)
    if host is None:
        raise ToolchainError("rustc -vV did not report its host triple")
    try:
        sysroot_result = subprocess.run(
            [str(rustc_entrypoint), "--print", "sysroot"], capture_output=True, text=True,
            timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ToolchainError(f"cannot query rustc sysroot: {error}") from error
    if sysroot_result.returncode != 0 or not sysroot_result.stdout.strip():
        raise ToolchainError("rustc did not report its sysroot")
    sysroot = Path(sysroot_result.stdout.strip()).resolve()
    rustc = sysroot / "bin" / f"rustc{'.exe' if os.name == 'nt' else ''}"
    if not rustc.is_file():
        raise ToolchainError(f"sysroot does not contain the active rustc compiler: {rustc}")
    rustc_receipt = _capture(rustc, ("-vV",))
    if rustc_receipt["version"] != entrypoint_version["version"]:
        raise ToolchainError("rustc entrypoint and active sysroot compiler differ")
    rustc = Path(os.path.abspath(rustc))
    suffix = ".exe" if os.name == "nt" else ""

    def llvm_path(environment_name: str, name: str) -> Path:
        configured = os.environ.get(environment_name)
        if configured:
            return _resolve_executable(name, environment_name)
        for candidate in (
            sysroot / "lib" / "rustlib" / host / "bin" / f"{name}{suffix}",
            sysroot / "bin" / f"{name}{suffix}",
        ):
            if candidate.is_file():
                return Path(os.path.abspath(candidate))
        raise ToolchainError(f"cannot locate {name} in Rust sysroot {sysroot}")

    llvm_cov = llvm_path("LLVM_COV", "llvm-cov")
    llvm_profdata = llvm_path("LLVM_PROFDATA", "llvm-profdata")
    paths = {
        "rustc": rustc,
        "cargo": cargo,
        "cargo_llvm_cov": cargo_llvm_cov,
        "llvm_cov": llvm_cov,
        "llvm_profdata": llvm_profdata,
    }
    receipts: dict[str, dict[str, str]] = {
        "rustc": rustc_receipt,
        "cargo": _capture(cargo, ("-Vv",)),
        "cargo_llvm_cov": _capture(cargo_llvm_cov, ("llvm-cov", "--version")),
        "llvm_cov": _capture(llvm_cov, ("--version",)),
        "llvm_profdata": _capture(llvm_profdata, ("--version",)),
    }
    return receipts, paths


def validate_coverage_tools(expected: Any) -> tuple[Path, Path]:
    """Compare current executables byte-for-byte and return the LLVM tools."""
    if not isinstance(expected, dict) or set(expected) != {
        "rustc", "cargo", "cargo_llvm_cov", "llvm_cov", "llvm_profdata",
    }:
        raise ToolchainError("coverage toolchain receipt is incomplete")
    actual, paths = capture_coverage_tools()
    if actual != expected:
        raise ToolchainError("current coverage tool executable paths, hashes, or versions differ from receipt")
    return paths["llvm_cov"], paths["llvm_profdata"]
