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
    if (
        "  workflow_run:" not in release_workflow
        or "    workflows: [Release candidate]" not in release_workflow
        or "    types: [completed]" not in release_workflow
    ):
        raise ValueError("release.yml must start automatically after Release candidate completes")
    if any(marker in release_workflow for marker in ("prepare-only", "PUBLISH v", "confirmation:")):
        raise ValueError("release.yml must not retain the retired manual publication selector")
    if (
        'tags: ["v*"]' not in candidate_workflow
        or "uvicorn-rs-candidate-${{ github.ref_name }}-${{ github.run_attempt }}" not in candidate_workflow
        or 'artifact_name = f"uvicorn-rs-candidate-{tag}-{attempt}"' not in release_workflow
    ):
        raise ValueError("tag candidate artifact selection must bind the exact run attempt")

    def workflow_job(name: str) -> str:
        try:
            start = lines.index(f"  {name}:")
        except ValueError as error:
            raise ValueError(f"release.yml is missing its {name} job") from error
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if lines[index].startswith("  ") and not lines[index].startswith("    ")
            ),
            len(lines),
        )
        return "\n".join(lines[start:end])

    prepare_job = workflow_job("prepare")
    crates_job = workflow_job("publish-crates")
    pypi_job = workflow_job("publish-pypi")
    verify_job = workflow_job("verify-publication")
    github_release_job = workflow_job("github-release")

    local_bootstrap_gates = (
        "first publication must create these crates locally before tagging",
        'manual_cargo_version = "0.3.0"',
        "must be published locally and match the candidate before tagging",
        "must be made locally before this automated release",
    )
    if (
        "publish_crates = any(crate_absent.values())" not in prepare_job
        or '"pending_first_publish"' not in prepare_job
        or "publish_pypi = pypi_absent" not in prepare_job
        or any(marker in release_workflow for marker in local_bootstrap_gates)
    ):
        raise ValueError(
            "release preflight must publish missing and first Cargo versions through the "
            "GitHub Trusted Publisher workflow"
        )
    required_crate_publish = (
        "environment: crates-io",
        "id-token: write",
        "rust-lang/crates-io-auth-action",
        "cargo publish --locked --no-verify -p asgi-lifespan-protocol-rs",
        "cargo publish --locked --no-verify -p uvicorn-rs",
        "Verify lifecycle crate registry bytes before publishing the server",
        "Publish the lifecycle crate",
        "Publish uvicorn-rs",
    )
    if any(check not in crates_job for check in required_crate_publish):
        raise ValueError("Cargo publication must use OIDC, preserve dependency order, and match candidate archives")
    if not (
        crates_job.index("Publish the lifecycle crate")
        < crates_job.index("Verify lifecycle crate registry bytes before publishing the server")
        < crates_job.index("Publish uvicorn-rs")
    ):
        raise ValueError("the lifecycle crate must be published and checksum-verified before uvicorn-rs")
    if (
        "needs: [prepare, publish-crates]" not in pypi_job
        or "needs.prepare.outputs.publish-pypi == 'true'" not in pypi_job
        or not re.search(r"(?m)^    environment:\s*['\"]?pypi['\"]?\s*$", pypi_job)
        or not re.search(r"(?m)^      id-token:\s*write\s*$", pypi_job)
        or "pypa/gh-action-pypi-publish" not in pypi_job
    ):
        raise ValueError("PyPI publication must follow Cargo verification and use its isolated OIDC environment")
    if "pypa/gh-action-pypi-publish" in candidate_workflow:
        raise ValueError("candidate.yml must remain candidate-only and must not publish to PyPI")
    if (
        "needs.verify-publication.result == 'success'" not in github_release_job
        or "contents: write" not in github_release_job
        or "actions/attest" not in github_release_job
        or '"gh", "release", "create"' not in github_release_job
    ):
        raise ValueError("GitHub Release creation and provenance must follow publication verification")
    if ("verify_crate(name)" not in verify_job
            or "for crate in (\"asgi-lifespan-protocol-rs\", \"uvicorn-rs\")" not in verify_job
            or "check_registry(verify_pypi" not in verify_job):
        raise ValueError("publication verification must compare both crate and PyPI bytes with the candidate")

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
