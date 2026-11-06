#!/usr/bin/env python3
"""Check Cargo, Python, HTTP/3 and lockfile versions for a candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
CONSUMER_LOCKS = (
    "examples/native-fastapi-contracts/Cargo.lock",
    "examples/native-starlette-server/Cargo.lock",
    "tools/standalone-h3-consumer/Cargo.lock",
)
HTTP3_CONSUMER_MANIFEST = "tools/standalone-h3-consumer/Cargo.toml"


def project_versions(root: Path = ROOT, expected: str | None = None) -> dict[str, str]:
    """Return synchronized release versions for the Python and native packages."""
    documents = {
        name: tomllib.loads((root / name).read_text(encoding="utf-8"))
        for name in (
            "Cargo.toml",
            "crates/uvicorn-rs/Cargo.toml",
            "crates/asgi-lifespan-protocol-rs/Cargo.toml",
            "pyproject.toml",
            "Cargo.lock",
            "uv.lock",
            *CONSUMER_LOCKS,
            HTTP3_CONSUMER_MANIFEST,
        )
    }
    cargo = documents["Cargo.toml"]["package"]
    native = documents["crates/uvicorn-rs/Cargo.toml"]["package"]
    lifecycle = documents["crates/asgi-lifespan-protocol-rs/Cargo.toml"]["package"]
    python = documents["pyproject.toml"]["project"]
    if cargo["name"] != "uvicorn-rs-py" or python["name"] != "uvicorn-rs":
        raise ValueError(
            "root Cargo integration package must be uvicorn-rs-py and the Python distribution must be uvicorn-rs"
        )
    if cargo.get("publish", True) is not False:
        raise ValueError("the uvicorn-rs-py Cargo integration package must stay unpublished")
    scripts = python.get("scripts", {})
    if scripts.get("uvicorn") != "uvicorn.main:main":
        raise ValueError("the uvicorn-rs PyPI distribution must provide the uvicorn command")
    if scripts.get("uvicorn-rs-py") != "uvicorn_rs.cli:main":
        raise ValueError("the optional uvicorn-rs-py adapter command is missing or has changed")
    python_packages = documents["pyproject.toml"].get("tool", {}).get("maturin", {}).get(
        "python-packages", []
    )
    if not {"uvicorn_rs", "uvicorn"} <= set(python_packages):
        raise ValueError("the uvicorn-rs wheel must include both the adapter and uvicorn namespaces")
    if native["name"] != "uvicorn-rs":
        raise ValueError("crates/uvicorn-rs must define the Python-free uvicorn-rs package")
    if "http3" not in documents["crates/uvicorn-rs/Cargo.toml"].get("features", {}):
        raise ValueError("the uvicorn-rs crate must expose HTTP/3 behind its http3 feature")
    workspace_members = set(documents["Cargo.toml"].get("workspace", {}).get("members", []))
    legacy_h3_members = {"crates/uvicorn-rs-h3", "crates/uvicorn-rs-h3-quinn"}
    if legacy_h3_members & workspace_members:
        raise ValueError("HTTP/3 and Quinn must not return as separate workspace crates")
    if lifecycle["name"] != "asgi-lifespan-protocol-rs":
        raise ValueError("crates/asgi-lifespan-protocol-rs must define the shared lifecycle package")

    workflow_dir = root / ".github/workflows"
    release_workflow_path = workflow_dir / "release.yml"
    candidate_workflow_path = workflow_dir / "candidate.yml"
    if not release_workflow_path.is_file() or not candidate_workflow_path.is_file():
        raise ValueError("release.yml publisher and candidate.yml workflow must both exist")
    if (workflow_dir / "publish.yml").exists():
        raise ValueError("package publication must use release.yml, not a separate publish.yml")
    release_workflow = release_workflow_path.read_text(encoding="utf-8")
    candidate_workflow = candidate_workflow_path.read_text(encoding="utf-8")
    lines = release_workflow.splitlines()
    try:
        action_start = lines.index("      action:")
        action_end = lines.index("      confirmation:", action_start + 1)
    except ValueError as error:
        raise ValueError("release.yml must expose the staged publication action selector") from error
    action_block = "\n".join(lines[action_start:action_end])
    action_options = re.findall(r"(?m)^          - ([^\s#]+)\s*$", action_block)
    if action_options != ["prepare-only", "pypi"]:
        raise ValueError("release.yml must expose only prepare-only and PyPI publication actions")
    if any(
        marker in release_workflow
        for marker in (
            "  publish-lifecycle:",
            "  publish-uvicorn-rs:",
            "cargo publish",
            "crates-io-auth-action",
        )
    ):
        raise ValueError("release.yml must leave Cargo publication to the authorized local release step")

    try:
        job_start = lines.index("  publish-pypi:")
    except ValueError as error:
        raise ValueError("release.yml is missing its publish-pypi job") from error
    job_end = next(
        (
            index
            for index in range(job_start + 1, len(lines))
            if lines[index].startswith("  ") and not lines[index].startswith("    ")
        ),
        len(lines),
    )
    pypi_job = "\n".join(lines[job_start:job_end])
    if (
        "needs: prepare" not in pypi_job
        or "needs.prepare.outputs.publish-pypi == 'true'" not in pypi_job
    ):
        raise ValueError("release.yml PyPI publication must be gated by its exact-candidate preflight")
    if not re.search(r"(?m)^    environment:\s*['\"]?pypi['\"]?\s*$", pypi_job):
        raise ValueError("release.yml must bind its PyPI publisher to the pypi environment")
    if not re.search(r"(?m)^      id-token:\s*write\s*$", pypi_job):
        raise ValueError("release.yml PyPI publisher must request OIDC only in its publish job")
    if "pypa/gh-action-pypi-publish" in candidate_workflow:
        raise ValueError("candidate.yml must remain candidate-only and must not publish to PyPI")

    registry_step = "      - name: Check immutable registry versions without credentials"
    registry_start = next(
        (index for index, line in enumerate(lines) if line == registry_step),
        None,
    )
    if registry_start is None:
        raise ValueError("release.yml is missing its registry preflight")
    registry_end = next(
        (
            index
            for index in range(registry_start + 1, len(lines))
            if lines[index] == "  publish-pypi:"
        ),
        len(lines),
    )
    registry_script = "\n".join(lines[registry_start:registry_end])
    required_registry_checks = (
        'inspect_all = action == "prepare-only"',
        "def check_crate_exists(name):",
        'f"https://crates.io/api/v1/crates/{name}"',
        "if pypi_selected or inspect_all:",
        "missing_names = [name for name, exists in crate_exists.items() if not exists]",
        'raise SystemExit("create these crates before the PyPI release: "',
        "unpublished = [name for name, absent in crate_absent.items() if absent]",
        'raise SystemExit("publish these exact candidate Cargo versions before PyPI: "',
        "pypi_absent = check_pypi()",
        "expected[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()",
        "if len(expected) != 4:",
        'f"https://pypi.org/pypi/uvicorn-rs/{version}/json"',
        'actual = {item.get("filename"): item.get("digests", {}).get("sha256") for item in files}',
        "if actual != expected:",
        "publish_pypi = pypi_selected and pypi_absent",
        'version_info.get("yanked") is True',
        "actual != digest",
    )
    if any(check not in registry_script for check in required_registry_checks):
        raise ValueError(
            "release.yml must inspect exact Cargo and PyPI registry state in prepare-only mode "
            "and permit PyPI only after exact candidate Cargo versions and PyPI filenames/checksums "
            "are verified"
        )

    verify_start = lines.index("  verify-publication:")
    publication_verification = "\n".join(lines[verify_start:])
    if (
        "def verify_pypi():" not in publication_verification
        or 'check_registry(verify_pypi, f"uvicorn-rs {version}")' not in publication_verification
        or "crates.io/api/v1/crates" in publication_verification
        or "verify_crate" in publication_verification
    ):
        raise ValueError("PyPI publication verification must verify only the exact PyPI distribution")

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
        "crates/asgi-lifespan-protocol-rs/Cargo.toml": lifecycle["version"],
        "pyproject.toml": python["version"],
        "Cargo.lock:uvicorn-rs-py": locked_package("Cargo.lock", "uvicorn-rs-py")["version"],
        "Cargo.lock:uvicorn-rs": locked_package("Cargo.lock", "uvicorn-rs")["version"],
        "Cargo.lock:asgi-lifespan-protocol-rs": locked_package(
            "Cargo.lock", "asgi-lifespan-protocol-rs"
        )["version"],
        "uv.lock": locked_package("uv.lock", "uvicorn-rs", editable=True)["version"],
    }
    for lock_name in CONSUMER_LOCKS:
        for package_name in ("uvicorn-rs", "asgi-lifespan-protocol-rs"):
            versions[f"{lock_name}:{package_name}"] = locked_package(
                lock_name, package_name
            )["version"]
    consumer_dependency = documents[HTTP3_CONSUMER_MANIFEST].get("dependencies", {}).get(
        "uvicorn-rs"
    )
    if (
        not isinstance(consumer_dependency, dict)
        or "path" in consumer_dependency
        or consumer_dependency.get("features") != ["http3"]
    ):
        raise ValueError(
            "the standalone HTTP/3 consumer must use the versioned registry dependency with http3"
        )
    versions[f"{HTTP3_CONSUMER_MANIFEST}:uvicorn-rs"] = consumer_dependency.get("version")
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
            f"release version {versions['Cargo.toml']} matches the uvicorn-rs Python distribution, "
            "Cargo integration package, lifecycle crate, and locks"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
