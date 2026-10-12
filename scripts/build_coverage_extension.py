"""Build the local extension with LLVM coverage instrumentation enabled."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from coverage_toolchain import capture_coverage_tools


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_TARGET = ROOT / "target" / "asgi-coverage"
NATIVE_COVERAGE_TARGET = ROOT / "target" / "asgi-native-coverage"


def main() -> int:
    try:
        _, tools = capture_coverage_tools()
    except RuntimeError as error:
        print(f"coverage toolchain resolution failed: {error}", file=sys.stderr)
        return 1
    cargo = str(tools["cargo"])
    rustc = str(tools["rustc"])
    coverage_wrapper = str(tools["cargo_llvm_cov"])
    separator = chr(31)
    environment = os.environ.copy()
    # Cargo gives encoded flags precedence even when their value is empty.
    # Remove them so the macOS extension's dynamic-lookup flags take effect.
    environment.pop("CARGO_ENCODED_RUSTFLAGS", None)
    environment.pop("CARGO_BUILD_RUSTFLAGS", None)
    environment["RUSTFLAGS"] = ""
    environment.update(
        {
            "CARGO_TARGET_DIR": str(COVERAGE_TARGET),
            "CARGO_LLVM_COV_TARGET_DIR": str(COVERAGE_TARGET),
            "CARGO_LLVM_COV_BUILD_DIR": str(COVERAGE_TARGET),
            "LLVM_PROFILE_FILE": str(COVERAGE_TARGET / "%p-%m.profraw"),
            "RUSTC": rustc,
            "RUSTC_WRAPPER": coverage_wrapper,
            "LLVM_COV": str(tools["llvm_cov"]),
            "LLVM_PROFDATA": str(tools["llvm_profdata"]),
            "RUSTC_WORKSPACE_WRAPPER": "",
            "CARGO_LLVM_COV": "1",
            "CARGO_LLVM_COV_SHOW_ENV": "1",
            "__CARGO_LLVM_COV_RUSTC_WRAPPER": "1",
            "__CARGO_LLVM_COV_RUSTC_WRAPPER_RUSTFLAGS": (
                f"-C{separator}instrument-coverage{separator}--cfg=coverage"
            ),
            "__CARGO_LLVM_COV_RUSTC_WRAPPER_CRATE_NAMES": "uvicorn_rs",
        }
    )
    if sys.platform == "darwin":
        environment["RUSTFLAGS"] = "-C link-arg=-undefined -C link-arg=dynamic_lookup"

    subprocess.run(
        [cargo, "build", "--manifest-path", "Cargo.toml", "--release", "--lib", "--locked"],
        cwd=ROOT,
        env=environment,
        check=True,
    )

    native_environment = os.environ.copy()
    native_environment["CARGO_TARGET_DIR"] = str(NATIVE_COVERAGE_TARGET)
    native_environment["RUSTC"] = rustc
    native_environment["LLVM_COV"] = str(tools["llvm_cov"])
    native_environment["LLVM_PROFDATA"] = str(tools["llvm_profdata"])
    coverage_environment = subprocess.run(
        [coverage_wrapper, "llvm-cov", "show-env", "--sh"],
        cwd=ROOT,
        env=native_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in coverage_environment.stdout.splitlines():
        if not line.startswith("export "):
            continue
        assignments = shlex.split(line.removeprefix("export "))
        if len(assignments) != 1 or "=" not in assignments[0]:
            raise RuntimeError(f"unexpected cargo-llvm-cov environment line: {line!r}")
        name, value = assignments[0].split("=", 1)
        native_environment[name] = value
    native_environment["RUSTC"] = rustc
    subprocess.run(
        [
            cargo,
            "build",
            "--manifest-path",
            "Cargo.toml",
            "--package",
            "uvicorn-rs",
            "--example",
            "native_core_contracts",
            "--release",
            "--locked",
        ],
        cwd=ROOT,
        env=native_environment,
        check=True,
    )

    if sys.platform == "darwin":
        library = COVERAGE_TARGET / "release" / "libuvicorn_rs.dylib"
        extension_name = "_native.abi3.so"
    elif sys.platform == "win32":
        library = COVERAGE_TARGET / "release" / "uvicorn_rs.dll"
        extension_name = "_native.abi3.pyd"
    else:
        library = COVERAGE_TARGET / "release" / "libuvicorn_rs.so"
        extension_name = "_native.abi3.so"

    extension = ROOT / "python" / "uvicorn_rs" / extension_name
    extension.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(library, extension)
    print(f"instrumented extension: {extension}")

    native_runner = NATIVE_COVERAGE_TARGET / "release" / "examples" / "native_core_contracts"
    if sys.platform == "win32":
        native_runner = native_runner.with_suffix(".exe")
    if not native_runner.is_file():
        print(f"instrumented native contract runner was not built: {native_runner}", file=sys.stderr)
        return 1
    print(f"instrumented native contract runner: {native_runner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
