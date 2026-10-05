"""Build the local extension with LLVM coverage instrumentation enabled."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_TARGET = ROOT / "target" / "asgi-coverage"


def main() -> int:
    separator = chr(31)
    environment = os.environ.copy()
    environment.update(
        {
            "CARGO_TARGET_DIR": str(COVERAGE_TARGET),
            "CARGO_LLVM_COV_TARGET_DIR": str(COVERAGE_TARGET),
            "CARGO_LLVM_COV_BUILD_DIR": str(COVERAGE_TARGET),
            "LLVM_PROFILE_FILE": str(COVERAGE_TARGET / "%p-%m.profraw"),
            "RUSTC_WRAPPER": str(Path.home() / ".cargo" / "bin" / "cargo-llvm-cov"),
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
        ["cargo", "build", "--manifest-path", "Cargo.toml", "--release", "--lib"],
        cwd=ROOT,
        env=environment,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
