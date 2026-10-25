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
    if action_options != ["prepare-only", "cargo", "pypi", "cargo-and-pypi"]:
        raise ValueError("release.yml must expose prepare-only, Cargo, PyPI, and combined actions")

    cargo_conditions = {
        "publish-lifecycle": "needs.prepare.outputs.publish-lifecycle == 'true'",
        "publish-uvicorn-rs": "needs.prepare.outputs.publish-uvicorn-rs == 'true'",
    }
    for cargo_job_name in ("publish-lifecycle", "publish-uvicorn-rs"):
        try:
            cargo_job_start = lines.index(f"  {cargo_job_name}:")
        except ValueError as error:
            raise ValueError(f"release.yml is missing {cargo_job_name}") from error
        cargo_job_end = next(
            (
                index
                for index in range(cargo_job_start + 1, len(lines))
                if lines[index].startswith("  ") and not lines[index].startswith("    ")
            ),
            len(lines),
        )
        cargo_job = "\n".join(lines[cargo_job_start:cargo_job_end])
        if cargo_conditions[cargo_job_name] not in cargo_job:
            raise ValueError(
                f"release.yml {cargo_job_name} must be gated by its registry preflight output"
            )

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
        "needs: [prepare, publish-lifecycle, publish-uvicorn-rs]" not in pypi_job
        or "inputs.action != 'cargo-and-pypi'" not in pypi_job
        or "needs.publish-lifecycle.result == 'success'" not in pypi_job
        or "needs.publish-lifecycle.result == 'skipped'" not in pypi_job
        or "needs.publish-uvicorn-rs.result == 'success'" not in pypi_job
        or "needs.publish-uvicorn-rs.result == 'skipped'" not in pypi_job
    ):
        raise ValueError("release.yml combined mode must wait for both Cargo publisher jobs before PyPI")
    if not re.search(r"(?m)^    environment:\s*['\"]?pypi['\"]?\s*$", pypi_job):
        raise ValueError("release.yml must bind its PyPI publisher to the pypi environment")
    if not re.search(r"(?m)^      id-token:\s*write\s*$", pypi_job):
        raise ValueError("release.yml PyPI publisher must request OIDC only in its publish job")
    if "pypa/gh-action-pypi-publish" in candidate_workflow:
        raise ValueError("candidate.yml must remain candidate-only and must not publish to PyPI")

    try:
        server_start = lines.index("  publish-uvicorn-rs:")
    except ValueError as error:
        raise ValueError("release.yml is missing its uvicorn-rs crates.io publisher") from error
    server_end = next(
        (
            index
            for index in range(server_start + 1, len(lines))
            if lines[index].startswith("  ") and not lines[index].startswith("    ")
        ),
        len(lines),
    )
    server_job = "\n".join(lines[server_start:server_end])
    index_step = "      - name: Wait for the exact lifecycle crate in the crates.io index"
    auth_step = "      - uses: rust-lang/crates-io-auth-action@"
    required_index_checks = (
        "needs: [prepare, publish-lifecycle]",
        "always()",
        "needs.publish-lifecycle.result == 'skipped'",
        "https://index.crates.io/{name[:2]}/{name[2:4]}/{name}",
        'row.get("vers") == version',
        'entry.get("yanked") is True',
        'actual_checksum != expected_checksum',
        "time.monotonic() + 300",
    )
    if (
        server_job.count(index_step) != 1
        or auth_step not in server_job
        or server_job.index(index_step) >= server_job.index(auth_step)
        or any(check not in server_job for check in required_index_checks)
    ):
        raise ValueError(
            "release.yml must wait for the exact lifecycle crate checksum in the crates.io index "
            "before authenticating to publish uvicorn-rs"
        )

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
            if lines[index] == "  publish-lifecycle:"
        ),
        len(lines),
    )
    registry_script = "\n".join(lines[registry_start:registry_end])
    required_bootstrap_checks = (
        "def check_crate_exists(name):",
        'f"https://crates.io/api/v1/crates/{name}"',
        "if cargo_selected and not crate_exists[crate_names[0]]:",
        "is a first crates.io publication",
    )
    if any(check not in registry_script for check in required_bootstrap_checks):
        raise ValueError(
            "release.yml must stop before Cargo publication when the lifecycle crate needs its first manual bootstrap"
        )

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
