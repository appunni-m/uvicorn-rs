#!/usr/bin/env python3
"""Record and revalidate exact-run raw unified coverage for release candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "uvicorn-rs-coverage-evidence@2"
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
RAW_ARTIFACT_NAME = "uvicorn-rs-unified-coverage"
CI_IDENTITY_NAME = "ci-run.json"
REPORT_NAME = "coverage-report.json"
HANDOFF_WORKFLOW = ".github/workflows/coverage-mcp-handoff.yml"
REPORT_SCHEMAS = {"uvicorn_rs_coverage/unified@9", "uvicorn_rs_coverage/unified@10",
                  "uvicorn-rs-coverage/unified@9", "uvicorn-rs-coverage/unified@10"}


class EvidenceError(RuntimeError):
    """Raw coverage does not meet the release evidence contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read JSON file {path}: {error}") from error


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise EvidenceError(f"cannot read evidence file {path}: {error}") from error


def digest_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_inventory(root: Path) -> dict[str, dict[str, Any]]:
    root = root.resolve()
    require(root.is_dir(), f"raw coverage directory does not exist: {root}")
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"symlink is not allowed in raw coverage: {path}")
        if path.is_dir():
            continue
        require(path.is_file(), f"non-regular raw coverage entry: {path}")
        inventory[path.relative_to(root).as_posix()] = {"sha256": file_hash(path), "size": path.stat().st_size}
    require(bool(inventory), f"raw coverage directory is empty: {root}")
    return inventory


def validate_ci_identity(root: Path, *, source: str, run_id: int, attempt: int) -> dict[str, Any]:
    identity = read_json(root / CI_IDENTITY_NAME)
    expected = {
        "schema": "uvicorn-rs-ci-artifact-identity@1",
        "workflow_path": ".github/workflows/ci.yml",
        "run_id": run_id,
        "run_attempt": attempt,
        "head_sha": source,
    }
    require(isinstance(identity, dict) and all(identity.get(key) == value for key, value in expected.items()),
            "CI artifact identity file does not match the selected workflow run and attempt")
    return identity


def validate_raw_report(report_path: Path, *, source: str) -> dict[str, Any]:
    report = read_json(report_path)
    extension = report.get("uvicorn_rs_unified") if isinstance(report, dict) else None
    require(isinstance(extension, dict) and extension.get("schema") in REPORT_SCHEMAS,
            "raw report is not a supported unified-coverage report")
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
    source_files = run_source.get("file_sha256")
    source_set = coverage.get("source_set")
    require(isinstance(source_files, dict) and isinstance(source_set, list) and bool(source_set),
            "coverage report has no source hash inventory")
    context_path = report_path.with_name(report_path.name + ".context.json")
    context = read_json(context_path)
    require(isinstance(context, dict)
            and context.get("report_sha256") == file_hash(report_path)
            and context.get("source_hashes") == {
                path: source_files.get(path) for path in coverage.get("source_set", [])
            }
            and context.get("build_id") == digest_json(build)
            and context.get("scope") == "full"
            and context.get("test_status") == "passed"
            and context.get("recorded_revision") == source,
            "raw coverage context does not bind the report, source, build, and passing full matrix")
    return {"report": report, "extension": extension, "context": context, "build_id": digest_json(build)}


def command_snapshot(args: argparse.Namespace) -> None:
    require(COMMIT_SHA.fullmatch(args.source) is not None, "source must be a full commit SHA")
    require(type(args.ci_run_id) is int and args.ci_run_id > 0
            and type(args.ci_attempt) is int and args.ci_attempt > 0,
            "CI run ID and attempt must be positive integers")
    require(type(args.raw_artifact_id) is int and args.raw_artifact_id > 0
            and type(args.raw_artifact_size) is int and args.raw_artifact_size > 0,
            "raw coverage artifact ID and size must be positive integers")
    require(args.raw_artifact_name == RAW_ARTIFACT_NAME,
            "unexpected raw coverage artifact name")
    require(isinstance(args.raw_artifact_digest, str)
            and ARTIFACT_SHA.fullmatch(args.raw_artifact_digest) is not None,
            "raw coverage artifact digest is invalid")
    report_path = args.report.resolve()
    require(report_path.name == REPORT_NAME and report_path.is_relative_to(ROOT),
            "coverage report must be the repository's canonical report file")
    report_path_relative = report_path.relative_to(ROOT).as_posix()
    validated = validate_raw_report(report_path, source=args.source)
    root = report_path.parent
    validate_ci_identity(root, source=args.source, run_id=args.ci_run_id, attempt=args.ci_attempt)
    inventory = file_inventory(root)
    for required_name in (REPORT_NAME, f"{REPORT_NAME}.context.json", CI_IDENTITY_NAME, "run.log"):
        require(required_name in inventory, f"raw coverage artifact is missing {required_name}")
    snapshot = {
        "schema": "uvicorn-rs-coverage-raw-inventory@1",
        "source_commit": args.source,
        "ci_run": {"id": args.ci_run_id, "attempt": args.ci_attempt, "branch": "main", "event": "push"},
        "artifact": {"id": args.raw_artifact_id, "name": args.raw_artifact_name,
                     "size_in_bytes": args.raw_artifact_size, "digest": args.raw_artifact_digest},
        "measurement_path": report_path_relative,
        "report_sha256": file_hash(report_path),
        "context_sha256": file_hash(report_path.with_name(report_path.name + ".context.json")),
        "build_id": validated["build_id"],
        "files": inventory,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot": str(args.output), "files": len(inventory),
                      "report_sha256": snapshot["report_sha256"]}, sort_keys=True))


def accepted_review(selection_path: Path, *, source: str, ci_run: dict[str, Any],
                    raw_artifact: dict[str, Any], report_sha256: str,
                    build_id: str) -> dict[str, Any]:
    selection = read_json(selection_path)
    require(isinstance(selection, dict)
            and selection.get("schema") == "uvicorn-rs-coverage-mcp-selection@1"
            and selection.get("source_commit") == source,
            "Coverage-MCP selection does not bind the requested source")
    expected_ci = {key: ci_run[key] for key in ("id", "attempt", "branch", "event")}
    require(selection.get("ci_run") == expected_ci,
            "Coverage-MCP selection does not bind the exact CI run and attempt")
    require(selection.get("raw_coverage_artifact") == raw_artifact,
            "Coverage-MCP selection does not bind the selected raw coverage artifact")
    handoff_inventory_sha256 = selection.get("raw_inventory_sha256")
    require(isinstance(handoff_inventory_sha256, str)
            and SHA256_HEX.fullmatch(handoff_inventory_sha256) is not None,
            "Coverage-MCP selection omits the reviewed raw inventory hash")
    require(selection.get("raw_report_sha256") == report_sha256,
            "Coverage-MCP selection does not bind the raw report")
    require(selection.get("build_id") == build_id,
            "Coverage-MCP selection does not bind the report build")

    handoff = selection.get("handoff_run")
    require(isinstance(handoff, dict)
            and type(handoff.get("id")) is int and handoff["id"] > 0
            and type(handoff.get("attempt")) is int and handoff["attempt"] > 0
            and handoff.get("workflow_path") == HANDOFF_WORKFLOW
            and handoff.get("event") == "workflow_dispatch"
            and handoff.get("branch") == "main",
            "Coverage-MCP selection has an invalid handoff workflow identity")
    expected_handoff_artifact_name = (
        f"uvicorn-rs-coverage-mcp-{ci_run['id']}-{ci_run['attempt']}-"
        f"{handoff['id']}-{handoff['attempt']}"
    )
    handoff_artifact = selection.get("handoff_artifact")
    require(isinstance(handoff_artifact, dict)
            and type(handoff_artifact.get("id")) is int and handoff_artifact["id"] > 0
            and handoff_artifact.get("name") == expected_handoff_artifact_name
            and type(handoff_artifact.get("size_in_bytes")) is int
            and handoff_artifact["size_in_bytes"] > 0
            and isinstance(handoff_artifact.get("digest"), str)
            and ARTIFACT_SHA.fullmatch(handoff_artifact["digest"]) is not None,
            "Coverage-MCP selection has invalid reviewed-artifact identity or digest")

    hashes = {
        "handoff_manifest_sha256": selection.get("handoff_manifest_sha256"),
        "reviewed_report_sha256": selection.get("reviewed_report_sha256"),
        "reviewed_context_sha256": selection.get("reviewed_context_sha256"),
        "projection_report_sha256": selection.get("projection_report_sha256"),
        "projection_context_sha256": selection.get("projection_context_sha256"),
        "coverage_mcp_receipt_sha256": selection.get("coverage_mcp_receipt_sha256"),
    }
    require(all(isinstance(value, str) and SHA256_HEX.fullmatch(value) is not None
                for value in hashes.values()),
            "Coverage-MCP selection omits a valid receipt, review, projection, or handoff hash")
    return {
        "status": "accepted",
        "source_commit": source,
        "ci_run": expected_ci,
        "handoff_raw_inventory_sha256": handoff_inventory_sha256,
        "raw_report_sha256": report_sha256,
        "build_id": build_id,
        "handoff_run": handoff,
        "handoff_artifact": handoff_artifact,
        **hashes,
        "selection_sha256": file_hash(selection_path),
    }


def verified_record(report_path: Path, inventory_path: Path, source: str,
                    handoff_selection_path: Path) -> dict[str, Any]:
    require(COMMIT_SHA.fullmatch(source) is not None, "expected source must be a full commit SHA")
    report_path = report_path.resolve()
    inventory_path = inventory_path.resolve()
    root = report_path.parent
    inventory = read_json(inventory_path)
    require(isinstance(inventory, dict)
            and inventory.get("schema") == "uvicorn-rs-coverage-raw-inventory@1"
            and inventory.get("source_commit") == source,
            "raw inventory does not bind the requested source")
    ci_run = inventory.get("ci_run")
    require(isinstance(ci_run, dict)
            and set(ci_run) == {"id", "attempt", "branch", "event"}
            and type(ci_run.get("id")) is int and ci_run["id"] > 0
            and type(ci_run.get("attempt")) is int and ci_run["attempt"] > 0
            and ci_run.get("branch") == "main" and ci_run.get("event") == "push",
            "raw inventory has an invalid exact main CI identity")
    report_path_relative = inventory.get("measurement_path")
    pure_report_path = PurePosixPath(report_path_relative) if isinstance(report_path_relative, str) else None
    actual_report_path = report_path.relative_to(ROOT).as_posix() if report_path.is_relative_to(ROOT) else None
    require(pure_report_path is not None and not pure_report_path.is_absolute()
            and all(part not in {"", ".", ".."} for part in pure_report_path.parts)
            and report_path.name == "coverage-report.json"
            and actual_report_path == report_path_relative,
            "raw inventory selects a different or unexpected coverage report path")
    identity = validate_ci_identity(root, source=source, run_id=ci_run["id"], attempt=ci_run["attempt"])
    artifact = inventory.get("artifact")
    require(isinstance(artifact, dict)
            and type(artifact.get("id")) is int and artifact["id"] > 0
            and artifact.get("name") == RAW_ARTIFACT_NAME
            and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] > 0
            and isinstance(artifact.get("digest"), str)
            and ARTIFACT_SHA.fullmatch(artifact["digest"]) is not None,
            "raw inventory has invalid GitHub artifact identity or digest")
    require(inventory.get("files") == file_inventory(root),
            "raw coverage artifact files differ from the immutable inventory")
    validated = validate_raw_report(report_path, source=source)
    extension = validated["extension"]
    coverage = extension["coverage"]
    matrix = extension["matrix"]
    summary = coverage["summary"]
    expected_matrix = (
        matrix.get("scope") == "complete"
        and type(matrix.get("manifest_case_count")) is int and matrix["manifest_case_count"] > 0
        and matrix.get("selected") == matrix["manifest_case_count"]
        and matrix.get("executed") == matrix["manifest_case_count"]
        and matrix.get("passed") == matrix["manifest_case_count"]
        and matrix.get("failed") == 0
        and matrix.get("infrastructure_failed") == 0
        and matrix.get("transient_infrastructure_failures") == 0
        and matrix.get("case_attribution_complete") is True
        and matrix.get("verification_runs_required") == 3
        and isinstance(matrix.get("verification_runs"), list)
        and len(matrix["verification_runs"]) == 3
        and isinstance(matrix.get("native_verification_runs"), list)
        and len(matrix["native_verification_runs"]) == 3
    )
    require(expected_matrix, "raw coverage report does not record the complete passing three-repeat matrix")
    totals: dict[str, dict[str, int]] = {}
    for metric in ("regions", "lines"):
        row = summary.get(metric)
        require(isinstance(row, dict)
                and type(row.get("covered")) is int and type(row.get("total")) is int
                and type(row.get("missing")) is int and row["total"] > 0
                and row["covered"] == row["total"] and row["missing"] == 0,
                f"raw report does not have 100% unified {metric} coverage")
        totals[metric] = {key: row[key] for key in ("covered", "total", "missing")}
    require(inventory.get("report_sha256") == file_hash(report_path)
            and inventory.get("context_sha256") == file_hash(report_path.with_name(report_path.name + ".context.json"))
            and inventory.get("build_id") == validated["build_id"],
            "raw coverage inventory hashes or build identity differ from the report")
    independent_review = accepted_review(
        handoff_selection_path, source=source, ci_run=ci_run, raw_artifact=artifact,
        report_sha256=inventory["report_sha256"], build_id=inventory["build_id"],
    )
    return {
        "schema": SCHEMA,
        "status": "passed",
        "acceptance": "exact-source raw unified coverage at 100% for regions and lines",
        "independent_review": independent_review,
        "source_commit": source,
        "ci_run": ci_run,
        "artifact": artifact,
        "report": {
            "path": report_path_relative,
            "sha256": inventory["report_sha256"],
            "context_sha256": inventory["context_sha256"],
            "build_id": inventory["build_id"],
        },
        "coverage": totals,
        "matrix": {
            "scope": "complete",
            "manifest_case_count": matrix["manifest_case_count"],
            "selected": matrix["selected"],
            "executed": matrix["executed"],
            "passed": matrix["passed"],
            "failed": matrix["failed"],
            "infrastructure_failed": matrix["infrastructure_failed"],
            "transient_infrastructure_failures": matrix["transient_infrastructure_failures"],
            "verification_runs_required": matrix["verification_runs_required"],
            "asgi_repeats": len(matrix["verification_runs"]),
            "native_repeats": len(matrix["native_verification_runs"]),
        },
        "raw_inventory_sha256": file_hash(inventory_path),
        "ci_identity_sha256": file_hash(root / "ci-run.json"),
        "ci_workflow_path": identity["workflow_path"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot", help="inventory a raw exact-run coverage artifact")
    snapshot.add_argument("--report", type=Path, required=True)
    snapshot.add_argument("--source", required=True)
    snapshot.add_argument("--ci-run-id", type=int, required=True)
    snapshot.add_argument("--ci-attempt", type=int, required=True)
    snapshot.add_argument("--raw-artifact-id", type=int, required=True)
    snapshot.add_argument("--raw-artifact-name", required=True)
    snapshot.add_argument("--raw-artifact-size", type=int, required=True)
    snapshot.add_argument("--raw-artifact-digest", required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    for command in ("record", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--report", type=Path, required=True)
        subparser.add_argument("--raw-inventory", type=Path, required=True)
        subparser.add_argument("--handoff-selection", type=Path, required=True)
        subparser.add_argument("--source", required=True)
        subparser.add_argument("--output", type=Path, help="required for record; evidence file for verify")
        subparser.set_defaults(func=command)
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            command_snapshot(args)
            return 0
        expected = verified_record(args.report, args.raw_inventory, args.source, args.handoff_selection)
        if args.command == "record":
            if args.output is None:
                raise EvidenceError("record requires --output")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps({"status": expected["status"], "source": args.source,
                              "ci_run": expected["ci_run"], "regions": expected["coverage"]["regions"],
                              "lines": expected["coverage"]["lines"],
                              "evidence_sha256": file_hash(args.output)}, sort_keys=True))
        else:
            if args.output is not None:
                raise EvidenceError("verify does not accept --output")
            actual = read_json(args.raw_inventory.parent / "coverage-evidence.json")
            require(actual == expected, "recorded coverage evidence differs from the raw report and inventory")
            print(json.dumps({"status": "verified", "source": args.source,
                              "ci_run": expected["ci_run"], "regions": expected["coverage"]["regions"],
                              "lines": expected["coverage"]["lines"]}, sort_keys=True))
    except (OSError, KeyError, TypeError, ValueError, EvidenceError) as error:
        print(f"coverage evidence: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
