#!/usr/bin/env python3
"""Create a compact, source-bound projection for independent Coverage-MCP review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from coverage_contract import pending_coverage_mcp_request


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMAS = {"uvicorn-rs-coverage/unified@9", "uvicorn-rs-coverage/unified@10"}
CONTEXT_SCHEMA = "uvicorn-rs-coverage-mcp-projection@1"
CI_IDENTITY_SCHEMA = "uvicorn-rs-ci-artifact-identity@1"


class ProjectionError(RuntimeError):
    """The canonical report cannot safely produce an MCP review projection."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProjectionError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectionError(f"cannot read JSON file {path}: {error}") from error


def repository_path(path: Path) -> str:
    resolved = path.resolve()
    require(resolved.is_relative_to(ROOT), "projection and canonical report must be inside the repository")
    return resolved.relative_to(ROOT).as_posix()


def validate_full_matrix(matrix: Any) -> None:
    require(isinstance(matrix, dict) and matrix.get("scope") == "complete",
            "canonical report does not contain a complete unified matrix")
    selected = matrix.get("selected")
    require(type(selected) is int and selected > 0
            and matrix.get("passed") == selected and matrix.get("executed") == selected
            and matrix.get("failed") == 0 and matrix.get("infrastructure_failed") == 0
            and matrix.get("transient_infrastructure_failures") == 0,
            "canonical matrix is not a complete passing test run")
    require(matrix.get("verification_runs_required") == 3,
            "canonical matrix does not require three verification repeats")
    asgi = matrix.get("verification_runs")
    native = matrix.get("native_verification_runs")
    require(isinstance(asgi, list) and len(asgi) == 3 and isinstance(native, list) and len(native) == 3,
            "canonical matrix does not retain all three ASGI and native verification repeats")
    for index, run in enumerate(asgi):
        summary = run.get("summary") if isinstance(run, dict) else None
        require(isinstance(run, dict) and run.get("status") in {"complete", "completed"}
                and run.get("runner_exit_code") == 0
                and isinstance(summary, dict)
                and summary.get("selected") == matrix.get("asgi_selected")
                and summary.get("passed") == matrix.get("asgi_selected")
                and summary.get("failed") == 0 and summary.get("infrastructure_failed") == 0
                and summary.get("not_run") == 0 and run.get("transient_infrastructure_failures") == 0
                and isinstance(run.get("attempts"), list) and len(run["attempts"]) == 1,
                f"ASGI verification repeat {index + 1} is incomplete or retried")
    for index, run in enumerate(native):
        require(isinstance(run, dict) and run.get("status") == "completed"
                and run.get("runner_exit_code") == 0
                and run.get("selected") == matrix.get("native_selected")
                and run.get("passed") == matrix.get("native_selected")
                and run.get("failed") == 0 and run.get("not_run") == 0
                and run.get("transient_infrastructure_failures") == 0
                and isinstance(run.get("attempts"), list) and len(run["attempts"]) == 1,
                f"native verification repeat {index + 1} is incomplete or retried")


def uncovered_llvm_functions(data: Any, uncovered_regions: Any) -> list[dict[str, Any]]:
    """Keep LLVM symbols referenced by normalized gaps and preserve every file record."""
    require(isinstance(data, list), "canonical report lacks an LLVM coverage data array")
    require(isinstance(uncovered_regions, list), "canonical report lacks normalized uncovered regions")
    uncovered_symbols: set[str] = set()
    for region in uncovered_regions:
        require(isinstance(region, dict), "canonical uncovered region is malformed")
        symbols = region.get("function_symbols")
        # Older report schemas may omit symbol attribution for a gap. Retain
        # the entire LLVM function inventory in that case instead of risking
        # an incomplete location projection.
        if not isinstance(symbols, list) or not symbols:
            return data
        require(all(isinstance(symbol, str) and symbol for symbol in symbols),
                "canonical uncovered region has malformed function symbols")
        uncovered_symbols.update(symbols)

    projected: list[dict[str, Any]] = []
    found_symbols: set[str] = set()
    for index, unit in enumerate(data):
        require(isinstance(unit, dict) and isinstance(unit.get("functions"), list),
                f"LLVM coverage data entry {index} lacks function records")
        functions = []
        for function in unit["functions"]:
            require(isinstance(function, dict) and isinstance(function.get("name"), str),
                    f"LLVM coverage data entry {index} has a malformed function record")
            if function["name"] in uncovered_symbols:
                functions.append(function)
                found_symbols.add(function["name"])
        projected.append({**unit, "functions": functions})
    require(uncovered_symbols <= found_symbols,
            "LLVM function inventory is missing symbols referenced by uncovered source spans")
    return projected


def projection_document(
    report_path: Path, output_path: Path, ci_identity_path: Path, *, canonical_report_path: str | None = None,
) -> tuple[bytes, bytes]:
    raw_bytes = report_path.read_bytes()
    report = read_json(report_path)
    extension = report.get("uvicorn_rs_unified") if isinstance(report, dict) else None
    require(isinstance(extension, dict) and extension.get("schema") in REPORT_SCHEMAS,
            "canonical report does not use the supported unified-coverage schema")
    run = extension.get("run")
    source = run.get("source") if isinstance(run, dict) else None
    build = run.get("build") if isinstance(run, dict) else None
    coverage = extension.get("coverage")
    summary = coverage.get("summary") if isinstance(coverage, dict) else None
    require(isinstance(source, dict) and isinstance(build, dict)
            and isinstance(source.get("revision"), str) and source.get("dirty") is False
            and isinstance(source.get("file_sha256"), dict),
            "canonical report lacks a clean source and build identity")
    require(isinstance(summary, dict)
            and all(isinstance(summary.get(metric), dict) for metric in ("regions", "lines")),
            "canonical report lacks normalized region and line totals")
    require(isinstance(coverage.get("regions"), list)
            and isinstance(coverage.get("uncovered_regions"), list),
            "canonical report lacks complete source-span inventories")
    matrix = extension.get("matrix")
    validate_full_matrix(matrix)

    context_path = report_path.with_name(report_path.name + ".context.json")
    context = read_json(context_path)
    source_hashes = {path: source["file_sha256"].get(path) for path in coverage.get("source_set", [])}
    build_id = digest_json(build)
    require(isinstance(context, dict)
            and context.get("report_sha256") == sha256_bytes(raw_bytes)
            and context.get("source_hashes") == source_hashes
            and context.get("build_id") == build_id
            and context.get("scope") == "full" and context.get("test_status") == "passed"
            and context.get("recorded_revision") == source["revision"],
            "canonical report context does not bind its source, build, and passing full matrix")

    ci_identity = read_json(ci_identity_path)
    require(isinstance(ci_identity, dict)
            and ci_identity.get("schema") == CI_IDENTITY_SCHEMA
            and ci_identity.get("head_sha") == source["revision"]
            and type(ci_identity.get("run_id")) is int and ci_identity["run_id"] > 0
            and type(ci_identity.get("run_attempt")) is int and ci_identity["run_attempt"] > 0
            and ci_identity.get("workflow_path") == ".github/workflows/ci.yml",
            "CI identity does not match the canonical report source")

    measurement_path = repository_path(output_path)
    projected_coverage = {
        key: coverage[key]
        for key in (
            "coverage_support_source_set", "executable_source_set", "gate", "line_validation",
            "llvm_normalization", "llvm_summary", "source_files", "source_set", "summary",
        )
        if key in coverage
    }
    # Per-case hit lists and function symbols dominate the canonical report's
    # size. The projection retains every source span and all uncovered rows,
    # while reducing covered rows to their stable coordinates and identity.
    projected_coverage["regions"] = [
        {key: region[key] for key in ("covered", "end", "file", "id", "start")}
        for region in coverage["regions"]
    ]
    projected_coverage["uncovered_regions"] = coverage["uncovered_regions"]
    projected_coverage["coverage_mcp"] = pending_coverage_mcp_request(measurement_path)

    compact_matrix = {
        key: matrix[key]
        for key in (
            "asgi_manifest_case_count", "asgi_selected", "case_attribution_complete", "executed",
            "failed", "fault_contracts", "infrastructure_failed", "manifest_case_count",
            "native_manifest_case_count", "native_selected", "oracle_parity", "passed", "scope",
            "selected", "transient_infrastructure_failures", "verification_runs_required",
        )
        if key in matrix
    }
    projected_extension = {
        "schema": extension["schema"],
        "status": extension.get("status"),
        "run": run,
        "matrix": compact_matrix,
        "coverage": projected_coverage,
    }
    projection = {
        "type": report.get("type"),
        "version": report.get("version"),
        # Coverage-MCP gets every file/span plus all LLVM function records that
        # contain uncovered regions. Fully covered function records add size
        # without adding any gap locations; aggregate totals remain unchanged.
        "data": uncovered_llvm_functions(report.get("data", []), coverage["uncovered_regions"]),
        "uvicorn_rs_unified": projected_extension,
    }
    output_bytes = (json.dumps(projection, separators=(",", ":"), sort_keys=True) + "\n").encode()
    canonical_reference = canonical_report_path or repository_path(report_path)
    require(not Path(canonical_reference).is_absolute() and ".." not in Path(canonical_reference).parts,
            "canonical report path must be a safe repository-relative path")
    binding = {
        "schema": CONTEXT_SCHEMA,
        "canonical_report_path": canonical_reference,
        "canonical_report_sha256": sha256_bytes(raw_bytes),
        "canonical_context_sha256": sha256_bytes(context_path.read_bytes()),
        "canonical_ci_identity_sha256": sha256_bytes(ci_identity_path.read_bytes()),
        "ci_run": {"id": ci_identity["run_id"], "attempt": ci_identity["run_attempt"],
                   "workflow_path": ci_identity["workflow_path"]},
        "projection_report_sha256": sha256_bytes(output_bytes),
        "source_commit": source["revision"],
        "source_hashes": source_hashes,
        "build_id": build_id,
        "scope": "full",
        "test_status": "passed",
        "recorded_revision": source["revision"],
        "summary": summary,
    }
    projection_context = {
        "report_sha256": sha256_bytes(output_bytes),
        "source_hashes": source_hashes,
        "build_id": build_id,
        "scope": "full",
        "test_status": "passed",
        "recorded_revision": source["revision"],
        "projection_binding": binding,
    }
    context_bytes = (json.dumps(projection_context, indent=2, sort_keys=True) + "\n").encode()
    return output_bytes, context_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="unchanged canonical CI report")
    parser.add_argument("--ci-identity", type=Path, help="defaults to ci-run.json beside --report")
    parser.add_argument("--output", type=Path, required=True, help="repository-relative MCP projection path")
    args = parser.parse_args()
    report_path = args.report.resolve()
    output_path = args.output.resolve()
    identity_path = (args.ci_identity or report_path.parent / "ci-run.json").resolve()
    require(report_path != output_path, "projection output must not replace the canonical report")
    output_bytes, context_bytes = projection_document(report_path, output_path, identity_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)
    output_path.with_name(output_path.name + ".context.json").write_bytes(context_bytes)
    binding = json.loads(context_bytes)["projection_binding"]
    print(json.dumps({"projection": str(output_path), "bytes": len(output_bytes),
                      "projection_sha256": binding["projection_report_sha256"],
                      "canonical_report_sha256": binding["canonical_report_sha256"],
                      "ci_run": binding["ci_run"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProjectionError, OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"coverage MCP projection error: {error}")
