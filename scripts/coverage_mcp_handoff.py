#!/usr/bin/env python3
"""Bind reviewed Coverage-MCP pages to one exact CI attempt and artifact."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from coverage_contract import pending_coverage_mcp_request
from project_coverage_mcp import ProjectionError, projection_document


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ".github/workflows/ci.yml"
HANDOFF_WORKFLOW = ".github/workflows/coverage-mcp-handoff.yml"
CI_COVERAGE_JOB = "All parity and fault contracts, 100% native regions and lines"
RAW_ARTIFACT_NAME = "uvicorn-rs-unified-coverage"
REPORT_NAME = "coverage-report.json"
CONTEXT_NAME = f"{REPORT_NAME}.context.json"
CI_IDENTITY_NAME = "ci-run.json"
RECEIPT_NAME = "coverage-mcp-receipt.json"
PROJECTION_NAME = "coverage-mcp-projection.json"
PROJECTION_CONTEXT_NAME = f"{PROJECTION_NAME}.context.json"
REVIEWED_REPORT_NAME = "coverage-report.reviewed.json"
PROJECTION_CONTEXT_SCHEMA = "uvicorn-rs-coverage-mcp-projection@1"
REPORT_SCHEMAS = {"uvicorn-rs-coverage/unified@9", "uvicorn-rs-coverage/unified@10"}
SCHEMA = "uvicorn-rs-coverage-mcp-handoff@1"
CI_IDENTITY_SCHEMA = "uvicorn-rs-ci-artifact-identity@1"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_RECEIPT_BASE64_CHARS = 60_000
MAX_RECEIPT_BYTES = 32 * 1024 * 1024


class HandoffError(RuntimeError):
    """External identities or retained coverage evidence do not match."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HandoffError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HandoffError(f"cannot read JSON file {path}: {error}") from error


def file_hash(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as error:
        raise HandoffError(f"cannot read file {path}: {error}") from error


def decode_receipt(encoded: str) -> list[Any]:
    require(isinstance(encoded, str) and 0 < len(encoded) <= MAX_RECEIPT_BASE64_CHARS,
            f"compressed receipt must contain 1 to {MAX_RECEIPT_BASE64_CHARS} base64 characters")
    try:
        compressed = base64.b64decode(encoded, validate=True)
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        payload = decompressor.decompress(compressed, MAX_RECEIPT_BYTES + 1)
    except (binascii.Error, ValueError, zlib.error) as error:
        raise HandoffError(f"receipt_gzip_base64 is not valid base64-encoded gzip: {error}") from error
    require(len(payload) <= MAX_RECEIPT_BYTES and decompressor.eof
            and not decompressor.unconsumed_tail and not decompressor.unused_data,
            "compressed receipt is truncated, has trailing data, or exceeds the 32 MiB limit")
    try:
        pages = json.loads(payload)
    except json.JSONDecodeError as error:
        raise HandoffError(f"decompressed MCP receipt is not valid JSON: {error}") from error
    require(isinstance(pages, list) and bool(pages), "decompressed MCP receipt must be a non-empty page array")
    return pages


def file_inventory(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    require(root.is_dir(), f"evidence directory does not exist: {root}")
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"symlink is not allowed in evidence: {path}")
        if path.is_dir():
            continue
        require(path.is_file(), f"non-regular evidence entry: {path}")
        relative = path.relative_to(root).as_posix()
        inventory[relative] = {"sha256": file_hash(path), "size": path.stat().st_size}
    require(bool(inventory), f"evidence directory is empty: {root}")
    return inventory


def report_relative(report_path: Path) -> str:
    resolved = report_path.resolve()
    require(resolved.is_relative_to(ROOT), "coverage report is outside the repository")
    return resolved.relative_to(ROOT).as_posix()


def validate_ci_identity(root: Path, *, source: str, run_id: int, attempt: int) -> dict[str, Any]:
    identity = read_json(root / CI_IDENTITY_NAME)
    expected = {
        "schema": CI_IDENTITY_SCHEMA,
        "workflow_path": CI_WORKFLOW,
        "run_id": run_id,
        "run_attempt": attempt,
        "head_sha": source,
    }
    require(isinstance(identity, dict) and all(identity.get(key) == value for key, value in expected.items()),
            "CI artifact identity file does not match the selected workflow run and attempt")
    return identity


def validate_pending_report(report_path: Path, *, source: str, expected_path: str) -> dict[str, Any]:
    report = read_json(report_path)
    extension = report.get("uvicorn_rs_unified") if isinstance(report, dict) else None
    require(isinstance(extension, dict) and extension.get("schema") in REPORT_SCHEMAS,
            "raw report is not the supported unified-coverage schema")
    run = extension.get("run")
    run_source = run.get("source") if isinstance(run, dict) else None
    build = run.get("build") if isinstance(run, dict) else None
    require(isinstance(run_source, dict) and run_source.get("revision") == source
            and run_source.get("dirty") is False and isinstance(build, dict),
            "coverage report is not from the selected clean source commit")
    coverage = extension.get("coverage")
    summary = coverage.get("summary") if isinstance(coverage, dict) else None
    require(isinstance(summary, dict), "coverage report has no normalized coverage totals")
    for metric in ("regions", "lines"):
        row = summary.get(metric)
        require(isinstance(row, dict) and type(row.get("total")) is int and row["total"] > 0
                and row.get("covered") == row["total"] and row.get("missing") == 0,
                f"raw unified report does not pass its {metric} coverage gate")
    require(isinstance(coverage, dict)
            and coverage.get("coverage_mcp") == pending_coverage_mcp_request(expected_path),
            "raw report is not awaiting Coverage-MCP for this exact repository path")
    context = read_json(report_path.with_name(report_path.name + ".context.json"))
    require(isinstance(context, dict)
            and context.get("report_sha256") == file_hash(report_path)
            and context.get("source_hashes") == {
                path: run_source.get("file_sha256", {}).get(path)
                for path in coverage.get("source_set", [])
            }
            and context.get("build_id") == digest_json(build)
            and context.get("scope") == "full"
            and context.get("test_status") == "passed"
            and context.get("recorded_revision") == source,
            "raw coverage context does not bind the report, source, build, and passing full matrix")
    return {"report": report, "extension": extension, "context": context, "build_id": digest_json(build)}


def validate_reviewed_report(
    review_root: Path, *, source: str, expected_path: str,
    report_name: str = REVIEWED_REPORT_NAME,
) -> dict[str, Any]:
    report_path = review_root / report_name
    context_path = review_root / f"{report_name}.context.json"
    receipt_path = review_root / RECEIPT_NAME
    report = read_json(report_path)
    extension = report.get("uvicorn_rs_unified") if isinstance(report, dict) else None
    require(isinstance(extension, dict) and extension.get("schema") in REPORT_SCHEMAS,
            "reviewed report is not the supported unified-coverage schema")
    run = extension.get("run")
    run_source = run.get("source") if isinstance(run, dict) else None
    build = run.get("build") if isinstance(run, dict) else None
    coverage = extension.get("coverage")
    summary = coverage.get("summary") if isinstance(coverage, dict) else None
    mcp = coverage.get("coverage_mcp") if isinstance(coverage, dict) else None
    require(isinstance(run_source, dict) and run_source.get("revision") == source
            and run_source.get("dirty") is False and isinstance(build, dict),
            "reviewed report is not from the selected clean source commit")
    require(isinstance(summary, dict) and isinstance(mcp, dict)
            and mcp.get("status") == "measured" and mcp.get("gate") == "passed"
            and mcp.get("measurement_path") == expected_path
            and mcp.get("source") == "matches_receipt" and mcp.get("tests") == "passed"
            and mcp.get("recorded_revision") == source and mcp.get("build_id") == digest_json(build),
            "reviewed report does not contain a passing source-matched Coverage-MCP receipt")
    for metric, key in (("regions", "coverage"), ("lines", "line_coverage")):
        total = summary.get(metric)
        receipt = mcp.get(key)
        require(isinstance(total, dict) and total.get("missing") == 0
                and isinstance(receipt, dict)
                and receipt == {**total, "metric": metric},
                f"Coverage-MCP {metric} totals differ from the full report or have gaps")
    receipt_sha = file_hash(receipt_path)
    require(mcp.get("receipt_sha256") == receipt_sha
            and mcp.get("receipt_artifact") == report_relative(receipt_path),
            "Coverage-MCP request/response page receipt hash or path is invalid")
    context = read_json(context_path)
    require(isinstance(context, dict) and context.get("report_sha256") == file_hash(report_path)
            and context.get("source_hashes") == {
                path: run_source.get("file_sha256", {}).get(path)
                for path in coverage.get("source_set", [])
            }
            and context.get("build_id") == digest_json(build)
            and context.get("scope") == "full" and context.get("test_status") == "passed"
            and context.get("recorded_revision") == source,
            "reviewed context receipt does not bind the report, source, build, and passing matrix")
    pages = read_json(receipt_path)
    require(isinstance(pages, list) and pages, "Coverage-MCP page receipt must be a non-empty array")
    return {"report": report, "extension": extension, "context": context,
            "receipt_sha256": receipt_sha, "build_id": digest_json(build)}


def validate_digest(value: Any, label: str) -> str:
    require(isinstance(value, str) and SHA256.fullmatch(value) is not None,
            f"{label} must be a sha256:<64 lowercase hex> digest")
    return value


def github_json(repository: str, path: str, token: str) -> tuple[Any, str | None]:
    request = Request(
        f"https://api.github.com/repos/{repository}/{path.lstrip('/')}",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "uvicorn-rs-coverage-handoff"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
            links = response.headers.get("Link", "")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HandoffError(f"GitHub API request failed for {path}: {error}") from error
    next_url = None
    for link in links.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="next"', link)
        if match:
            next_url = match.group(1)
            break
    return payload, next_url


def github_pages(repository: str, path: str, token: str) -> list[Any]:
    payload, next_url = github_json(repository, path, token)
    key = "workflow_runs" if "workflow_runs" in payload else "artifacts" if "artifacts" in payload else "jobs"
    rows = list(payload.get(key, []))
    page_count = 1
    while next_url:
        page_count += 1
        require(page_count <= 20, "GitHub API pagination exceeds 20 pages")
        request = Request(next_url, headers={
            "Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "uvicorn-rs-coverage-handoff",
        })
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
                links = response.headers.get("Link", "")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise HandoffError(f"GitHub API pagination failed: {error}") from error
        rows.extend(payload.get(key, []))
        next_url = None
        for link in links.split(","):
            match = re.match(r'\s*<([^>]+)>;\s*rel="next"', link)
            if match:
                next_url = match.group(1)
                break
    return rows


def validate_run_identity(
    repository: str, token: str, *, run_id: int, attempt: int, source: str,
    expected_workflow: str, expected_event: str,
) -> dict[str, Any]:
    run, _ = github_json(repository, f"actions/runs/{run_id}/attempts/{attempt}", token)
    expected = {"id": run_id, "run_attempt": attempt, "head_sha": source, "head_branch": "main",
                "event": expected_event, "status": "completed", "conclusion": "success"}
    require(all(run.get(key) == value for key, value in expected.items()),
            f"workflow run {run_id}/{attempt} is not successful on exact main source {source}")
    require(run.get("path") == expected_workflow,
            f"workflow run {run_id} did not use {expected_workflow}")
    return run


def validated_ci_artifact(repository: str, token: str, *, run_id: int, attempt: int,
                          source: str) -> dict[str, Any]:
    run = validate_run_identity(repository, token, run_id=run_id, attempt=attempt, source=source,
                                expected_workflow=CI_WORKFLOW, expected_event="push")
    jobs = github_pages(repository, f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100", token)
    require(any(job.get("name") == CI_COVERAGE_JOB and job.get("status") == "completed"
                and job.get("conclusion") == "success" for job in jobs),
            "selected CI attempt has no successful unified-coverage job")
    artifacts = github_pages(repository, f"actions/runs/{run_id}/artifacts?per_page=100", token)
    matches = [artifact for artifact in artifacts if artifact.get("name") == RAW_ARTIFACT_NAME
               and artifact.get("expired") is False]
    require(len(matches) == 1, "selected CI run has a missing, expired, or duplicate coverage artifact")
    artifact = matches[0]
    require(type(artifact.get("id")) is int and artifact["id"] > 0
            and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] > 0,
            "coverage artifact metadata omits id or size")
    digest = validate_digest(artifact.get("digest"), "raw coverage artifact digest")
    associated_run = artifact.get("workflow_run")
    require(isinstance(associated_run, dict) and associated_run.get("id") == run_id
            and associated_run.get("head_sha") == source,
            "coverage artifact is not associated with the selected CI run and source")
    return {"run": run, "artifact": artifact, "digest": digest}


def output_values(values: dict[str, Any], output_path: str | None) -> None:
    print(json.dumps(values, sort_keys=True, separators=(",", ":")))
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            for key, value in values.items():
                require("\n" not in str(value) and "\r" not in str(value), "GitHub output contains a newline")
                output.write(f"{key}={value}\n")


def command_validate_ci(args: argparse.Namespace) -> None:
    result = validated_ci_artifact(args.repository, args.token, run_id=args.ci_run_id,
                                   attempt=args.ci_attempt, source=args.source)
    artifact = result["artifact"]
    values = {
        "ci-run-id": args.ci_run_id,
        "ci-attempt": args.ci_attempt,
        "raw-artifact-id": artifact["id"],
        "raw-artifact-name": artifact["name"],
        "raw-artifact-size": artifact["size_in_bytes"],
        "raw-artifact-digest": result["digest"],
    }
    output_values(values, args.github_output)


def command_select_ci(args: argparse.Namespace) -> None:
    runs = github_pages(args.repository,
                        f"actions/workflows/ci.yml/runs?head_sha={args.source}&per_page=100", args.token)
    candidates = sorted(
        (run for run in runs if run.get("head_sha") == args.source and run.get("head_branch") == "main"
         and run.get("event") == "push" and run.get("status") == "completed"
         and run.get("conclusion") == "success" and type(run.get("run_attempt")) is int),
        key=lambda row: row.get("updated_at", ""), reverse=True,
    )
    errors: list[str] = []
    selected = None
    for run in candidates:
        try:
            selected = validated_ci_artifact(args.repository, args.token, run_id=run["id"],
                                             attempt=run["run_attempt"], source=args.source)
            break
        except HandoffError as error:
            errors.append(f"{run.get('id')}/{run.get('run_attempt')}: {error}")
    require(selected is not None, "no successful exact-source CI attempt has complete unified coverage: "
            + ("; ".join(errors[:5]) if errors else "no successful main push run was found"))
    artifact = selected["artifact"]
    values = {
        "run-id": selected["run"]["id"],
        "run-attempt": selected["run"]["run_attempt"],
        "artifact-id": artifact["id"],
        "artifact-name": artifact["name"],
        "artifact-size": artifact["size_in_bytes"],
        "artifact-digest": selected["digest"],
    }
    output_values(values, args.github_output)


def command_select_handoff(args: argparse.Namespace) -> None:
    runs = github_pages(args.repository,
                        f"actions/workflows/coverage-mcp-handoff.yml/runs?head_sha={args.source}&per_page=100",
                        args.token)
    matches: list[dict[str, Any]] = []
    expected_prefix = f"uvicorn-rs-coverage-mcp-{args.ci_run_id}-{args.ci_attempt}-"
    for run in runs:
        if (run.get("head_sha") != args.source or run.get("head_branch") != "main"
                or run.get("event") != "workflow_dispatch" or run.get("status") != "completed"
                or run.get("conclusion") != "success" or type(run.get("run_attempt")) is not int
                or type(run.get("id")) is not int):
            continue
        try:
            validate_run_identity(args.repository, args.token, run_id=run["id"],
                                  attempt=run["run_attempt"], source=args.source,
                                  expected_workflow=HANDOFF_WORKFLOW,
                                  expected_event="workflow_dispatch")
        except HandoffError:
            continue
        artifacts = github_pages(args.repository, f"actions/runs/{run['id']}/artifacts?per_page=100", args.token)
        expected_name = f"{expected_prefix}{run['id']}-{run['run_attempt']}"
        for artifact in artifacts:
            if artifact.get("name") != expected_name or artifact.get("expired") is not False:
                continue
            associated_run = artifact.get("workflow_run")
            require(isinstance(associated_run, dict) and associated_run.get("id") == run["id"]
                    and associated_run.get("head_sha") == args.source,
                    "reviewed handoff artifact is associated with another workflow run or source")
            require(type(artifact.get("id")) is int and artifact["id"] > 0
                    and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] > 0,
                    "reviewed handoff artifact metadata omits id or size")
            digest = validate_digest(artifact.get("digest"), "reviewed handoff artifact digest")
            matches.append({"run": run, "artifact": artifact, "digest": digest})
    require(len(matches) == 1,
            f"expected exactly one successful reviewed handoff for CI {args.ci_run_id}/{args.ci_attempt}; "
            f"found {len(matches)}")
    selected = matches[0]
    values = {
        "run-id": selected["run"]["id"],
        "run-attempt": selected["run"]["run_attempt"],
        "artifact-id": selected["artifact"]["id"],
        "artifact-name": selected["artifact"]["name"],
        "artifact-size": selected["artifact"]["size_in_bytes"],
        "artifact-digest": selected["digest"],
    }
    output_values(values, args.github_output)


def command_validate_handoff(args: argparse.Namespace) -> None:
    run = validate_run_identity(args.repository, args.token, run_id=args.handoff_run_id,
                                attempt=args.handoff_attempt, source=args.source,
                                expected_workflow=HANDOFF_WORKFLOW,
                                expected_event="workflow_dispatch")
    expected_name = (
        f"uvicorn-rs-coverage-mcp-{args.ci_run_id}-{args.ci_attempt}-"
        f"{args.handoff_run_id}-{args.handoff_attempt}"
    )
    require(args.artifact_name == expected_name,
            "selected handoff artifact name does not bind the selected CI and handoff attempts")
    artifacts = github_pages(args.repository,
                             f"actions/runs/{args.handoff_run_id}/artifacts?per_page=100", args.token)
    matches = [artifact for artifact in artifacts if artifact.get("id") == args.artifact_id]
    require(len(matches) == 1, "selected Coverage-MCP artifact is missing or duplicated")
    artifact = matches[0]
    expected = {"name": expected_name, "size_in_bytes": args.artifact_size,
                "digest": args.artifact_digest, "expired": False}
    require(all(artifact.get(key) == value for key, value in expected.items()),
            "selected Coverage-MCP artifact metadata changed during candidate assembly")
    associated_run = artifact.get("workflow_run")
    require(isinstance(associated_run, dict) and associated_run.get("id") == run["id"]
            and associated_run.get("head_sha") == args.source,
            "selected Coverage-MCP artifact is no longer bound to its successful source run")
    print(json.dumps({"status": "verified", "run_id": args.handoff_run_id,
                      "run_attempt": args.handoff_attempt, "artifact_id": args.artifact_id,
                      "artifact_digest": args.artifact_digest}, sort_keys=True))


def command_snapshot(args: argparse.Namespace) -> None:
    require(type(args.ci_run_id) is int and args.ci_run_id > 0
            and type(args.ci_attempt) is int and args.ci_attempt > 0,
            "CI run id and attempt must be positive integers")
    require(type(args.raw_artifact_id) is int and args.raw_artifact_id > 0
            and type(args.raw_artifact_size) is int and args.raw_artifact_size > 0,
            "raw coverage artifact id and size must be positive integers")
    validate_digest(args.raw_artifact_digest, "raw coverage artifact digest")
    require(args.raw_artifact_name == RAW_ARTIFACT_NAME, "unexpected raw coverage artifact name")
    root = args.report.parent.resolve()
    validate_ci_identity(root, source=args.source, run_id=args.ci_run_id, attempt=args.ci_attempt)
    validated = validate_pending_report(args.report, source=args.source,
                                        expected_path=report_relative(args.report))
    inventory = file_inventory(root)
    for required_name in (REPORT_NAME, CONTEXT_NAME, CI_IDENTITY_NAME, "run.log"):
        require(required_name in inventory, f"raw coverage artifact is missing {required_name}")
    snapshot = {
        "schema": "uvicorn-rs-coverage-raw-inventory@1",
        "source_commit": args.source,
        "ci_run": {"id": args.ci_run_id, "attempt": args.ci_attempt, "branch": "main", "event": "push"},
        "artifact": {"id": args.raw_artifact_id, "name": args.raw_artifact_name,
                     "size_in_bytes": args.raw_artifact_size, "digest": args.raw_artifact_digest},
        "measurement_path": report_relative(args.report),
        "report_sha256": file_hash(args.report),
        "context_sha256": file_hash(args.report.with_name(args.report.name + ".context.json")),
        "build_id": validated["build_id"],
        "files": inventory,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot": str(args.output), "files": len(inventory),
                      "report_sha256": snapshot["report_sha256"]}, sort_keys=True))


def command_project(args: argparse.Namespace) -> None:
    report_path = args.report.resolve()
    output_path = args.output.resolve()
    identity_path = (args.ci_identity or report_path.parent / CI_IDENTITY_NAME).resolve()
    require(report_path != output_path, "projection output must not replace the canonical report")
    report_bytes, context_bytes = projection_document(report_path, output_path, identity_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(report_bytes)
    output_path.with_name(output_path.name + ".context.json").write_bytes(context_bytes)
    binding = json.loads(context_bytes)["projection_binding"]
    print(json.dumps({"projection": str(output_path), "bytes": len(report_bytes),
                      "projection_sha256": binding["projection_report_sha256"],
                      "canonical_report_sha256": binding["canonical_report_sha256"],
                      "ci_run": binding["ci_run"]}, sort_keys=True))


def command_write_receipt(args: argparse.Namespace) -> None:
    pages = decode_receipt(args.receipt_gzip_base64)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pages, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    print(json.dumps({"receipt": str(args.output), "pages": len(pages),
                      "bytes": args.output.stat().st_size}, sort_keys=True))


def validate_projection_binding(review_root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    projection_path = review_root / PROJECTION_NAME
    context_path = review_root / PROJECTION_CONTEXT_NAME
    report = read_json(projection_path)
    context = read_json(context_path)
    binding = context.get("projection_binding") if isinstance(context, dict) else None
    require(isinstance(binding, dict) and binding.get("schema") == PROJECTION_CONTEXT_SCHEMA,
            "review projection has no supported canonical binding")
    require(binding.get("canonical_report_path") == snapshot.get("measurement_path")
            and binding.get("canonical_report_sha256") == snapshot.get("report_sha256")
            and binding.get("canonical_context_sha256") == snapshot.get("context_sha256")
            and binding.get("canonical_ci_identity_sha256")
            == snapshot.get("files", {}).get(CI_IDENTITY_NAME, {}).get("sha256")
            and binding.get("source_commit") == snapshot.get("source_commit")
            and binding.get("ci_run") == {
                "id": snapshot.get("ci_run", {}).get("id"),
                "attempt": snapshot.get("ci_run", {}).get("attempt"),
                "workflow_path": CI_WORKFLOW,
            }
            and binding.get("build_id") == snapshot.get("build_id")
            and binding.get("scope") == "full" and binding.get("test_status") == "passed"
            and binding.get("recorded_revision") == snapshot.get("source_commit"),
            "review projection is not bound to the selected raw report, CI attempt, source, build, and passing matrix")
    require(binding.get("projection_report_sha256") == file_hash(projection_path)
            and context.get("report_sha256") == file_hash(projection_path)
            and context.get("source_hashes") == binding.get("source_hashes")
            and context.get("build_id") == binding.get("build_id")
            and context.get("scope") == binding.get("scope")
            and context.get("test_status") == binding.get("test_status")
            and context.get("recorded_revision") == binding.get("recorded_revision"),
            "review projection or its source/build context digest changed")
    extension = report.get("uvicorn_rs_unified") if isinstance(report, dict) else None
    run = extension.get("run") if isinstance(extension, dict) else None
    coverage = extension.get("coverage") if isinstance(extension, dict) else None
    require(isinstance(run, dict) and isinstance(coverage, dict)
            and run.get("source", {}).get("revision") == snapshot.get("source_commit")
            and digest_json(run.get("build")) == snapshot.get("build_id")
            and coverage.get("coverage_mcp") == pending_coverage_mcp_request(report_relative(projection_path)),
            "review projection report identity or MCP measurement path differs")
    return {"report": report, "context": context, "binding": binding}


def verify_reviewed_projection(review_root: Path, *, reviewed_report_path: Path) -> None:
    projection_path = review_root / PROJECTION_NAME
    receipt_path = review_root / RECEIPT_NAME
    (ROOT / "target").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coverage-mcp-reverify-", dir=ROOT / "target") as temp:
        generated_report = Path(temp) / REVIEWED_REPORT_NAME
        command = [sys.executable, str(ROOT / "scripts" / "attach_coverage_mcp.py"),
                   "--report", str(projection_path), "--output", str(generated_report),
                   "--receipt", str(receipt_path)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        require(result.returncode == 0,
                "offline Coverage-MCP page validation failed: " + (result.stderr.strip() or result.stdout.strip()))
        require(generated_report.read_bytes() == reviewed_report_path.read_bytes()
                and generated_report.with_name(generated_report.name + ".context.json").read_bytes()
                == reviewed_report_path.with_name(reviewed_report_path.name + ".context.json").read_bytes(),
                "reviewed report differs from deterministic attachment of its projection and complete page receipt")


def command_create(args: argparse.Namespace) -> None:
    snapshot = read_json(args.snapshot)
    require(isinstance(snapshot, dict) and snapshot.get("schema") == "uvicorn-rs-coverage-raw-inventory@1",
            "raw coverage inventory has an unsupported schema")
    require(type(args.handoff_run_id) is int and args.handoff_run_id > 0
            and type(args.handoff_attempt) is int and args.handoff_attempt > 0,
            "handoff run id and attempt must be positive integers")
    source = snapshot.get("source_commit")
    ci = snapshot.get("ci_run", {})
    artifact = snapshot.get("artifact", {})
    require(isinstance(source, str) and COMMIT_SHA.fullmatch(source) is not None,
            "raw inventory source commit is invalid")
    require(isinstance(ci, dict) and type(ci.get("id")) is int and type(ci.get("attempt")) is int
            and isinstance(artifact, dict), "raw inventory lacks exact CI identity")
    require(ci == {"id": ci["id"], "attempt": ci["attempt"], "branch": "main", "event": "push"}
            and artifact == {"id": artifact.get("id"), "name": RAW_ARTIFACT_NAME,
                             "size_in_bytes": artifact.get("size_in_bytes"),
                             "digest": artifact.get("digest")}
            and type(artifact.get("id")) is int and artifact["id"] > 0
            and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] > 0,
            "raw inventory CI/artifact metadata is invalid")
    validate_digest(artifact.get("digest"), "raw inventory artifact digest")
    projection = validate_projection_binding(args.review_root, snapshot)
    projection_path = args.review_root / PROJECTION_NAME
    reviewed_report_path = args.review_root / REVIEWED_REPORT_NAME
    projection_reference = report_relative(projection_path)
    review = validate_reviewed_report(args.review_root, source=source,
                                      expected_path=projection_reference)
    reviewed_context = review["context"]
    require(reviewed_context.get("projection_binding") == projection["binding"],
            "reviewed report context is not bound to the retained MCP projection")
    verify_reviewed_projection(args.review_root, reviewed_report_path=reviewed_report_path)
    reviewed_files = file_inventory(args.review_root)
    expected_reviewed_files = {
        PROJECTION_NAME, PROJECTION_CONTEXT_NAME, REVIEWED_REPORT_NAME,
        f"{REVIEWED_REPORT_NAME}.context.json", RECEIPT_NAME,
    }
    require(set(reviewed_files) == expected_reviewed_files,
            "reviewed artifact contains missing or unexpected projection/receipt files")
    expected_artifact_name = (
        f"uvicorn-rs-coverage-mcp-{ci['id']}-{ci['attempt']}-"
        f"{args.handoff_run_id}-{args.handoff_attempt}"
    )
    manifest = {
        "schema": SCHEMA,
        "source_commit": source,
        "ci_run": ci,
        "raw_coverage_artifact": artifact,
        "measurement": {"path": snapshot["measurement_path"],
                        "raw_report_sha256": snapshot["report_sha256"],
                        "raw_context_sha256": snapshot["context_sha256"],
                        "build_id": snapshot["build_id"],
                        "projection_path": projection_reference,
                        "projection_report_sha256": projection["binding"]["projection_report_sha256"],
                        "projection_context_sha256": file_hash(args.review_root / PROJECTION_CONTEXT_NAME),
                        "raw_inventory_sha256": file_hash(args.snapshot),
                        "raw_files": snapshot["files"]},
        "reviewed": {"report_sha256": file_hash(reviewed_report_path),
                     "context_sha256": file_hash(args.review_root / f"{REVIEWED_REPORT_NAME}.context.json"),
                     "projection_report_sha256": projection["binding"]["projection_report_sha256"],
                     "projection_context_sha256": file_hash(args.review_root / PROJECTION_CONTEXT_NAME),
                     "receipt_sha256": review["receipt_sha256"],
                     "files": reviewed_files},
        "handoff_run": {"id": args.handoff_run_id, "attempt": args.handoff_attempt,
                        "workflow_path": HANDOFF_WORKFLOW, "event": "workflow_dispatch",
                        "branch": "main", "artifact_name": expected_artifact_name},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(args.output), "artifact_name": expected_artifact_name,
                      "reviewed_files": len(reviewed_files),
                      "report_sha256": manifest["reviewed"]["report_sha256"]}, sort_keys=True))


def command_verify(args: argparse.Namespace) -> None:
    manifest = read_json(args.manifest)
    require(isinstance(manifest, dict) and manifest.get("schema") == SCHEMA,
            "coverage handoff manifest has an unsupported schema")
    require(manifest.get("source_commit") == args.source, "coverage handoff source commit differs")
    require(COMMIT_SHA.fullmatch(args.source) is not None, "selected source commit is invalid")
    require(args.ci_run_id > 0 and args.ci_attempt > 0 and args.handoff_run_id > 0
            and args.handoff_attempt > 0, "selected run IDs and attempts must be positive")
    ci = manifest.get("ci_run", {})
    require(ci == {"id": args.ci_run_id, "attempt": args.ci_attempt, "branch": "main", "event": "push"},
            "coverage handoff manifest selects another CI run or attempt")
    handoff = manifest.get("handoff_run", {})
    require(handoff == {"id": args.handoff_run_id, "attempt": args.handoff_attempt,
                        "workflow_path": HANDOFF_WORKFLOW, "event": "workflow_dispatch",
                        "branch": "main", "artifact_name": args.handoff_artifact_name},
            "coverage handoff manifest selects another handoff run, attempt, or artifact")
    expected_handoff_name = (
        f"uvicorn-rs-coverage-mcp-{args.ci_run_id}-{args.ci_attempt}-"
        f"{args.handoff_run_id}-{args.handoff_attempt}"
    )
    require(args.handoff_artifact_name == expected_handoff_name,
            "selected handoff artifact name does not bind the selected source CI and handoff attempts")
    validate_digest(args.handoff_artifact_digest, "selected handoff artifact digest")
    require(args.handoff_artifact_id > 0 and args.handoff_artifact_size > 0,
            "selected handoff artifact id and size must be positive")
    raw_artifact = manifest.get("raw_coverage_artifact", {})
    require(args.raw_artifact_name == RAW_ARTIFACT_NAME,
            "selected raw artifact name is not the unified coverage artifact")
    expected_raw_artifact = {"id": args.raw_artifact_id, "name": args.raw_artifact_name,
                             "size_in_bytes": args.raw_artifact_size, "digest": args.raw_artifact_digest}
    require(raw_artifact == expected_raw_artifact,
            "coverage handoff was made from another raw coverage artifact")
    validate_digest(args.raw_artifact_digest, "selected raw coverage artifact digest")

    measurement = manifest.get("measurement", {})
    require(isinstance(measurement, dict), "coverage handoff manifest has no measurement identity")
    measured_path = measurement.get("path") if isinstance(measurement, dict) else None
    projection_path = args.review_root / PROJECTION_NAME
    projection_reference = report_relative(projection_path)
    require(measurement.get("projection_path") == projection_reference,
            "coverage handoff selects another MCP review projection")
    inventory_path = args.manifest.with_name("raw-inventory.json")
    inventory = read_json(inventory_path)
    require(isinstance(inventory, dict)
            and file_hash(inventory_path) == measurement.get("raw_inventory_sha256")
            and inventory.get("schema") == "uvicorn-rs-coverage-raw-inventory@1"
            and inventory.get("source_commit") == args.source
            and inventory.get("ci_run") == ci
            and inventory.get("artifact") == raw_artifact
            and inventory.get("measurement_path") == measured_path
            and inventory.get("report_sha256") == measurement.get("raw_report_sha256")
            and inventory.get("context_sha256") == measurement.get("raw_context_sha256")
            and inventory.get("build_id") == measurement.get("build_id")
            and inventory.get("files") == measurement.get("raw_files"),
            "raw coverage inventory differs from the reviewed handoff manifest")
    raw_report_path = args.ci_raw_root / REPORT_NAME
    require(isinstance(measured_path, str), "coverage handoff has no canonical measurement path")
    validate_ci_identity(args.ci_raw_root, source=args.source, run_id=args.ci_run_id, attempt=args.ci_attempt)
    raw_report = validate_pending_report(raw_report_path, source=args.source, expected_path=measured_path)
    raw_files = file_inventory(args.ci_raw_root)
    require(raw_files == measurement.get("raw_files"),
            "selected raw CI artifact file tree differs from the pre-review inventory")
    require(measurement.get("raw_report_sha256") == file_hash(raw_report_path)
            and measurement.get("raw_context_sha256") == file_hash(args.ci_raw_root / CONTEXT_NAME)
            and measurement.get("build_id") == raw_report["build_id"],
            "selected raw coverage report, context, or build differs from the handoff")

    expected_projection, expected_projection_context = projection_document(
        raw_report_path, projection_path, args.ci_raw_root / CI_IDENTITY_NAME,
        canonical_report_path=measured_path,
    )
    require(projection_path.read_bytes() == expected_projection
            and (args.review_root / PROJECTION_CONTEXT_NAME).read_bytes() == expected_projection_context,
            "MCP projection is stale or differs from the canonical raw report")
    projection = validate_projection_binding(args.review_root, inventory)
    reviewed_report_path = args.review_root / REVIEWED_REPORT_NAME
    reviewed = validate_reviewed_report(args.review_root, source=args.source,
                                        expected_path=projection_reference)
    require(reviewed["context"].get("projection_binding") == projection["binding"],
            "reviewed report context is not bound to the verified MCP projection")
    verify_reviewed_projection(args.review_root, reviewed_report_path=reviewed_report_path)
    reviewed_files = file_inventory(args.review_root)
    reviewed_identity = manifest.get("reviewed", {})
    require(isinstance(reviewed_identity, dict)
            and reviewed_files == reviewed_identity.get("files")
            and reviewed_identity.get("report_sha256") == file_hash(reviewed_report_path)
            and reviewed_identity.get("context_sha256")
            == file_hash(args.review_root / f"{REVIEWED_REPORT_NAME}.context.json")
            and reviewed_identity.get("projection_report_sha256") == projection["binding"]["projection_report_sha256"]
            and reviewed_identity.get("projection_context_sha256") == file_hash(args.review_root / PROJECTION_CONTEXT_NAME)
            and reviewed_identity.get("receipt_sha256") == reviewed["receipt_sha256"],
            "reviewed artifact files differ from their immutable manifest")

    selection = {
        "schema": "uvicorn-rs-coverage-mcp-selection@1",
        "source_commit": args.source,
        "ci_run": ci,
        "raw_coverage_artifact": raw_artifact,
        "handoff_run": handoff,
        "handoff_artifact": {
            "id": args.handoff_artifact_id,
            "name": args.handoff_artifact_name,
            "size_in_bytes": args.handoff_artifact_size,
            "digest": args.handoff_artifact_digest,
        },
        "handoff_manifest_sha256": file_hash(args.manifest),
        "raw_report_sha256": measurement["raw_report_sha256"],
        "reviewed_report_sha256": reviewed_identity["report_sha256"],
        "reviewed_context_sha256": reviewed_identity["context_sha256"],
        "projection_report_sha256": reviewed_identity["projection_report_sha256"],
        "projection_context_sha256": reviewed_identity["projection_context_sha256"],
        "coverage_mcp_receipt_sha256": reviewed_identity["receipt_sha256"],
        "build_id": reviewed["build_id"],
    }
    args.selection_output.parent.mkdir(parents=True, exist_ok=True)
    args.selection_output.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"status": "verified", "source": args.source,
                      "ci_run": f"{args.ci_run_id}/{args.ci_attempt}",
                      "handoff_run": f"{args.handoff_run_id}/{args.handoff_attempt}",
                      "report_sha256": selection["reviewed_report_sha256"]}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    validate_ci = commands.add_parser("validate-ci", help="validate an exact successful CI artifact via GitHub API")
    validate_ci.add_argument("--repository", required=True)
    validate_ci.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    validate_ci.add_argument("--source", required=True)
    validate_ci.add_argument("--ci-run-id", required=True, type=int)
    validate_ci.add_argument("--ci-attempt", required=True, type=int)
    validate_ci.add_argument("--github-output")
    validate_ci.set_defaults(func=command_validate_ci)

    select_ci = commands.add_parser("select-ci", help="select the latest complete exact-source successful CI run")
    select_ci.add_argument("--repository", required=True)
    select_ci.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    select_ci.add_argument("--source", required=True)
    select_ci.add_argument("--github-output")
    select_ci.set_defaults(func=command_select_ci)

    select_handoff = commands.add_parser("select-handoff", help="select one reviewed handoff for the selected CI attempt")
    select_handoff.add_argument("--repository", required=True)
    select_handoff.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    select_handoff.add_argument("--source", required=True)
    select_handoff.add_argument("--ci-run-id", required=True, type=int)
    select_handoff.add_argument("--ci-attempt", required=True, type=int)
    select_handoff.add_argument("--github-output")
    select_handoff.set_defaults(func=command_select_handoff)

    validate_handoff = commands.add_parser("validate-handoff", help="revalidate the selected handoff run and artifact")
    validate_handoff.add_argument("--repository", required=True)
    validate_handoff.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    validate_handoff.add_argument("--source", required=True)
    validate_handoff.add_argument("--ci-run-id", required=True, type=int)
    validate_handoff.add_argument("--ci-attempt", required=True, type=int)
    validate_handoff.add_argument("--handoff-run-id", required=True, type=int)
    validate_handoff.add_argument("--handoff-attempt", required=True, type=int)
    validate_handoff.add_argument("--artifact-id", required=True, type=int)
    validate_handoff.add_argument("--artifact-name", required=True)
    validate_handoff.add_argument("--artifact-size", required=True, type=int)
    validate_handoff.add_argument("--artifact-digest", required=True)
    validate_handoff.set_defaults(func=command_validate_handoff)

    snapshot = commands.add_parser("snapshot", help="inventory an unmodified raw CI coverage artifact")
    snapshot.add_argument("--report", type=Path, required=True)
    snapshot.add_argument("--source", required=True)
    snapshot.add_argument("--ci-run-id", type=int, required=True)
    snapshot.add_argument("--ci-attempt", type=int, required=True)
    snapshot.add_argument("--raw-artifact-id", type=int, required=True)
    snapshot.add_argument("--raw-artifact-name", required=True)
    snapshot.add_argument("--raw-artifact-size", type=int, required=True)
    snapshot.add_argument("--raw-artifact-digest", required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.set_defaults(func=command_snapshot)

    project = commands.add_parser("project", help="create a deterministic source-bound MCP review projection")
    project.add_argument("--report", type=Path, required=True, help="unchanged canonical CI report")
    project.add_argument("--ci-identity", type=Path, help="defaults to ci-run.json beside --report")
    project.add_argument("--output", type=Path, required=True, help="repository-relative projection path")
    project.set_defaults(func=command_project)

    receipt = commands.add_parser("write-receipt", help="decode bounded gzip/base64 MCP receipt input")
    receipt.add_argument("--receipt-gzip-base64", default=os.environ.get("RECEIPT_GZIP_BASE64", ""))
    receipt.add_argument("--output", type=Path, required=True)
    receipt.set_defaults(func=command_write_receipt)

    create = commands.add_parser("create", help="record hashes after strict MCP attachment succeeds")
    create.add_argument("--snapshot", type=Path, required=True)
    create.add_argument("--review-root", type=Path, required=True)
    create.add_argument("--handoff-run-id", type=int, required=True)
    create.add_argument("--handoff-attempt", type=int, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.set_defaults(func=command_create)

    verify = commands.add_parser("verify", help="verify selected raw and reviewed artifacts for a candidate")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--source", required=True)
    verify.add_argument("--ci-run-id", type=int, required=True)
    verify.add_argument("--ci-attempt", type=int, required=True)
    verify.add_argument("--raw-artifact-id", type=int, required=True)
    verify.add_argument("--raw-artifact-name", required=True)
    verify.add_argument("--raw-artifact-size", type=int, required=True)
    verify.add_argument("--raw-artifact-digest", required=True)
    verify.add_argument("--ci-raw-root", type=Path, required=True)
    verify.add_argument("--review-root", type=Path, required=True)
    verify.add_argument("--handoff-run-id", type=int, required=True)
    verify.add_argument("--handoff-attempt", type=int, required=True)
    verify.add_argument("--handoff-artifact-id", type=int, required=True)
    verify.add_argument("--handoff-artifact-name", required=True)
    verify.add_argument("--handoff-artifact-size", type=int, required=True)
    verify.add_argument("--handoff-artifact-digest", required=True)
    verify.add_argument("--selection-output", type=Path, required=True)
    verify.set_defaults(func=command_verify)
    return root


def main() -> int:
    args = parser().parse_args()
    if hasattr(args, "token"):
        require(bool(args.token), "GH_TOKEN is required for GitHub run selection")
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HandoffError, ProjectionError) as error:
        raise SystemExit(f"coverage MCP handoff error: {error}")
