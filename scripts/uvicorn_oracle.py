"""Inspect the isolated stock-Uvicorn process environment used for comparisons."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


EXPECTED_UVICORN_VERSION = "0.54.0"


def inspect_uvicorn_oracle(
    python: Path,
    *,
    expected_python_version: str,
    required_packages: tuple[str, ...] = (),
) -> dict:
    """Require a genuine, isolated Uvicorn install and return its identity.

    The oracle must not contain uvicorn-rs because both distributions own
    the ``uvicorn`` import namespace. Keep the venv executable path as given:
    resolving it can follow a venv symlink to a base interpreter and lose the
    environment's site-packages.
    """
    executable = python.absolute()
    if not executable.is_file():
        raise RuntimeError(f"Uvicorn oracle Python interpreter does not exist: {executable}")
    probe = r"""
import importlib.metadata as metadata
import importlib.util
import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import uvicorn

try:
    metadata.distribution("uvicorn-rs")
except metadata.PackageNotFoundError:
    pass
else:
    raise SystemExit("oracle environment contains uvicorn-rs")

if importlib.util.find_spec("uvicorn_rs") is not None:
    raise SystemExit("oracle environment can import uvicorn_rs")

distribution = metadata.distribution("uvicorn")
record_text = distribution.read_text("RECORD") or ""
record_digest = hashlib.sha256(record_text.encode("utf-8")).hexdigest()
module_path = Path(uvicorn.__file__).resolve()
prefix = Path(sys.prefix).resolve()
try:
    module_path.relative_to(prefix)
except ValueError:
    raise SystemExit(f"uvicorn module is outside oracle environment: {module_path}")

names = ("uvicorn", "httptools", "uvloop", "websockets", "fastapi", "starlette")
packages = {}
for name in names:
    try:
        packages[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        packages[name] = None

package_paths = {}
for name in ("fastapi", "starlette"):
    spec = importlib.util.find_spec(name)
    if spec is None:
        package_paths[name] = None
    elif spec.submodule_search_locations:
        package_paths[name] = str(Path(next(iter(spec.submodule_search_locations))).resolve())
    elif spec.origin:
        package_paths[name] = str(Path(spec.origin).resolve().parent)
    else:
        package_paths[name] = None

record_content_mismatches = []
source_digest = hashlib.sha256()
for row in csv.reader(record_text.splitlines()):
    if not row:
        continue
    relative_path = row[0]
    recorded_hash = row[1] if len(row) > 1 else ""
    path = Path(distribution.locate_file(relative_path))
    if not path.is_file():
        record_content_mismatches.append(relative_path)
        continue
    content = path.read_bytes()
    if path.suffix == ".py" and "uvicorn/" in relative_path:
        source_digest.update(relative_path.encode("utf-8"))
        source_digest.update(b"\0")
        source_digest.update(content)
        source_digest.update(b"\0")
    if recorded_hash:
        algorithm, separator, expected = recorded_hash.partition("=")
        actual = base64.urlsafe_b64encode(hashlib.new(algorithm, content).digest()).rstrip(b"=").decode("ascii")
        if not separator or actual != expected:
            record_content_mismatches.append(relative_path)
if record_content_mismatches:
    raise SystemExit("Uvicorn files differ from their installed RECORD hashes")
if getattr(uvicorn, "__version__", None) != distribution.version:
    raise SystemExit("uvicorn.__version__ differs from the installed distribution metadata")

print(json.dumps({
    "executable": sys.executable,
    "python_version": platform.python_version(),
    "python_implementation": platform.python_implementation(),
    "environment_prefix": str(prefix),
    "uvicorn_version": distribution.version,
    "uvicorn_module_path": str(module_path),
    "uvicorn_record_sha256": record_digest,
    "uvicorn_source_files_sha256": source_digest.hexdigest(),
    "uvicorn_record_content_mismatches": record_content_mismatches,
    "packages": packages,
    "package_paths": package_paths,
}))
"""
    result = subprocess.run(
        [str(executable), "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"invalid Uvicorn oracle environment: {detail}")
    identity = json.loads(result.stdout)
    if identity["uvicorn_version"] != EXPECTED_UVICORN_VERSION:
        raise RuntimeError(
            "benchmark oracle must be stock Uvicorn "
            f"{EXPECTED_UVICORN_VERSION}, found {identity['uvicorn_version']}"
        )
    if identity["python_version"] != expected_python_version:
        raise RuntimeError(
            "candidate and Uvicorn oracle must use the same Python version; "
            f"candidate={expected_python_version}, oracle={identity['python_version']}"
        )
    missing = [name for name in required_packages if identity["packages"].get(name) is None]
    if missing:
        raise RuntimeError(f"Uvicorn oracle is missing required packages: {', '.join(missing)}")
    identity["executable"] = str(executable)
    identity["required_packages"] = list(required_packages)
    identity["status"] = "verified_stock_uvicorn_oracle"
    return identity


def python_version(python: Path) -> str:
    """Return the Python version reported by a candidate interpreter."""
    result = subprocess.run(
        [str(python.absolute()), "-c", "import platform; print(platform.python_version())"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()
