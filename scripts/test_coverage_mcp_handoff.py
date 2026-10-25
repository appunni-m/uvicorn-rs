#!/usr/bin/env python3
"""Focused acceptance fixtures for the Coverage-MCP release evidence handoff."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from coverage_contract import pending_coverage_mcp_request
from project_coverage_mcp import uncovered_llvm_functions


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "scripts" / "coverage_mcp_handoff.py"
ATTACH = ROOT / "scripts" / "attach_coverage_mcp.py"
SOURCE = "a" * 40
SOURCE_FILE_HASH = "b" * 64
CI_RUN_ID = 123456
CI_ATTEMPT = 2
RAW_ARTIFACT_ID = 456789
RAW_ARTIFACT_SIZE = 1234
RAW_ARTIFACT_DIGEST = "sha256:" + "c" * 64
HANDOFF_RUN_ID = 678901
HANDOFF_ATTEMPT = 1
HANDOFF_ARTIFACT_ID = 987654
HANDOFF_ARTIFACT_SIZE = 2345
HANDOFF_ARTIFACT_DIGEST = "sha256:" + "d" * 64


def digest_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def page(measurement: str, build_id: str, metric: str, *, next_offset: int | None = None) -> dict[str, Any]:
    return {
        "request": {"measurement": measurement, "metric": metric, "offset": 0, "limit": 15,
                    "query": None, "line": None},
        "response": {"context": {}, "page": None,
                     "data": {"status": "measured", "measurement": {
                         "ref": measurement, "coverage": {"covered": 1, "total": 1, "missing": 0,
                                                              "metric": metric},
                         "source": "matches_receipt", "tests": "passed",
                         "recorded_revision": SOURCE, "build_id": build_id},
                         "group_count": 0, "groups": [], "next_offset": next_offset}},
    }


def make_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    report_root = root / "target" / "coverage-handoff-fixture" / "asgi-coverage"
    report_root.mkdir(parents=True)
    review_root = root / "target" / "coverage-handoff-fixture" / "asgi-coverage-review"
    review_root.mkdir(parents=True)
    report_path = report_root / "coverage-report.json"
    relative_report = report_path.relative_to(ROOT).as_posix()
    build = {"tool": "fixture", "profile": "coverage"}
    extension = {
        "schema": "uvicorn-rs-coverage/unified@9",
        "run": {"build": build,
                "source": {"revision": SOURCE, "dirty": False,
                           "file_sha256": {"src/lib.rs": SOURCE_FILE_HASH}}},
        "coverage": {"source_set": ["src/lib.rs"],
                      "summary": {
                          "regions": {"covered": 1, "total": 1, "missing": 0},
                          "lines": {"covered": 1, "total": 1, "missing": 0},
                      },
                      "regions": [{"file": "src/lib.rs", "start": {"line": 1, "column": 1},
                                   "end": {"line": 1, "column": 2}, "covered": True, "id": "r0"}],
                      "uncovered_regions": [],
                      "coverage_mcp": pending_coverage_mcp_request(relative_report)},
        "matrix": {
            "scope": "complete", "passed": 1, "selected": 1, "executed": 1,
            "failed": 0, "transient_infrastructure_failures": 0,
            "infrastructure_failed": 0, "asgi_selected": 1, "native_selected": 1,
            "verification_runs_required": 3,
            "verification_runs": [{
                "status": "complete", "runner_exit_code": 0,
                "summary": {"selected": 1, "passed": 1, "failed": 0,
                            "infrastructure_failed": 0, "not_run": 0},
                "transient_infrastructure_failures": 0, "attempts": [{}],
            } for _ in range(3)],
            "native_verification_runs": [{
                "status": "completed", "runner_exit_code": 0, "selected": 1, "passed": 1,
                "failed": 0, "not_run": 0, "transient_infrastructure_failures": 0,
                "attempts": [{}],
            } for _ in range(3)],
        },
    }
    llvm_data = [{
        "files": [{"filename": "src/lib.rs", "segments": [[1, 1, 1, True, True, False]]}],
        "functions": [
            {"branches": [], "count": 1, "filenames": ["src/lib.rs"], "mcdc_records": [],
             "name": "covered_function", "regions": [[1, 1, 1, 2, 1, 0, 0, 0]]},
            {"branches": [], "count": 0, "filenames": ["src/lib.rs"], "mcdc_records": [],
             "name": "uncovered_function", "regions": [[2, 1, 2, 2, 0, 0, 0, 0]]},
        ],
        "totals": {"functions": {"count": 2, "covered": 1, "notcovered": 1}},
    }]
    write_json(report_path, {"type": "llvm.coverage.json.export", "version": "2.0.1",
                             "data": llvm_data, "uvicorn_rs_unified": extension})
    context = {
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "source_hashes": {"src/lib.rs": SOURCE_FILE_HASH},
        "build_id": digest_json(build), "scope": "full", "test_status": "passed",
        "recorded_revision": SOURCE,
    }
    write_json(report_path.with_name(report_path.name + ".context.json"), context)
    write_json(report_root / "ci-run.json", {
        "schema": "uvicorn-rs-ci-artifact-identity@1", "workflow_path": ".github/workflows/ci.yml",
        "run_id": CI_RUN_ID, "run_attempt": CI_ATTEMPT, "head_sha": SOURCE,
    })
    (report_root / "run.log").write_text("coverage fixture\n", encoding="utf-8")
    (report_root / "artifacts").mkdir()
    (report_root / "artifacts" / "profile.bin").write_bytes(b"fixture profile")
    receipt_path = review_root / "coverage-mcp-receipt.json"
    return report_path, receipt_path, report_root, review_root


def run(*args: str, expected: int = 0, detail: str = "") -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != expected:
        raise AssertionError(
            f"command returned {result.returncode}, expected {expected}: {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    combined = result.stdout + result.stderr
    if detail and detail not in combined:
        raise AssertionError(f"expected diagnostic {detail!r} was absent:\n{combined}")
    return result


def check_uncovered_function_projection() -> None:
    files = [{"filename": "src/lib.rs", "segments": [[1, 1, 1, True, True, False]]}]
    totals = {"functions": {"count": 2, "covered": 1, "notcovered": 1}}
    functions = [
        {"name": "covered_function", "regions": [[1, 1, 1, 2, 1, 0, 0, 0]]},
        {"name": "uncovered_function", "regions": [[2, 1, 2, 2, 0, 0, 0, 0]]},
    ]
    projected = uncovered_llvm_functions(
        [{"files": files, "functions": functions, "totals": totals}],
        [{"function_symbols": ["uncovered_function"]}],
    )
    if (len(projected) != 1 or projected[0]["files"] != files or projected[0]["totals"] != totals
            or [item["name"] for item in projected[0]["functions"]] != ["uncovered_function"]):
        raise AssertionError("gap projection must preserve file inventory/totals and every uncovered symbol")
    if uncovered_llvm_functions([{"files": files, "functions": functions, "totals": totals}],
                                [{"function_symbols": []}]) != [
                                    {"files": files, "functions": functions, "totals": totals}
                                ]:
        raise AssertionError("unmapped uncovered spans must retain the complete LLVM function inventory")


def main() -> int:
    check_uncovered_function_projection()
    (ROOT / "target").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-coverage-handoff-", dir=ROOT / "target") as temp:
        root = Path(temp)
        report, receipt, raw_root, review_root = make_fixture(root / "valid")
        ci_raw = root / "valid" / "ci-raw"
        shutil.copytree(raw_root, ci_raw)
        snapshot_path = root / "valid" / "raw-inventory.json"
        run(str(HANDOFF), "snapshot", "--report", str(report), "--source", SOURCE,
            "--ci-run-id", str(CI_RUN_ID), "--ci-attempt", str(CI_ATTEMPT),
            "--raw-artifact-id", str(RAW_ARTIFACT_ID), "--raw-artifact-name", "uvicorn-rs-unified-coverage",
            "--raw-artifact-size", str(RAW_ARTIFACT_SIZE), "--raw-artifact-digest", RAW_ARTIFACT_DIGEST,
            "--output", str(snapshot_path))
        projection = review_root / "coverage-mcp-projection.json"
        run(str(HANDOFF), "project", "--report", str(report), "--output", str(projection))
        projection_ref = projection.relative_to(ROOT).as_posix()
        pages = [page(projection_ref, digest_json({"tool": "fixture", "profile": "coverage"}), "regions"),
                 page(projection_ref, digest_json({"tool": "fixture", "profile": "coverage"}), "lines")]
        receipt_bytes = json.dumps(pages, separators=(",", ":")).encode()
        encoded_receipt = base64.b64encode(gzip.compress(receipt_bytes, mtime=0)).decode("ascii")
        decoded_receipt_path = root / "valid" / "decoded-receipt.json"
        run(str(HANDOFF), "write-receipt", "--receipt-gzip-base64", encoded_receipt,
            "--output", str(decoded_receipt_path))
        if json.loads(decoded_receipt_path.read_text(encoding="utf-8")) != pages:
            raise AssertionError("compressed MCP receipt did not round-trip without changing its pages")
        run(str(HANDOFF), "write-receipt", "--receipt-gzip-base64", "not-base64!",
            "--output", str(root / "valid" / "invalid-receipt.json"), expected=1,
            detail="not valid base64-encoded gzip")
        write_json(receipt, pages)
        reviewed_report = review_root / "coverage-report.reviewed.json"
        run(str(ATTACH), "--report", str(projection), "--output", str(reviewed_report),
            "--receipt", str(receipt))
        raw_sha_before = hashlib.sha256(report.read_bytes()).hexdigest()
        manifest_path = root / "valid" / "handoff.json"
        run(str(HANDOFF), "create", "--snapshot", str(snapshot_path), "--review-root", str(review_root),
            "--handoff-run-id", str(HANDOFF_RUN_ID), "--handoff-attempt", str(HANDOFF_ATTEMPT),
            "--output", str(manifest_path))
        selection_path = root / "valid" / "selection.json"
        verify_args = (
            str(HANDOFF), "verify", "--manifest", str(manifest_path), "--source", SOURCE,
            "--ci-run-id", str(CI_RUN_ID), "--ci-attempt", str(CI_ATTEMPT),
            "--raw-artifact-id", str(RAW_ARTIFACT_ID), "--raw-artifact-name", "uvicorn-rs-unified-coverage",
            "--raw-artifact-size", str(RAW_ARTIFACT_SIZE), "--raw-artifact-digest", RAW_ARTIFACT_DIGEST,
            "--ci-raw-root", str(ci_raw), "--review-root", str(review_root),
            "--handoff-run-id", str(HANDOFF_RUN_ID), "--handoff-attempt", str(HANDOFF_ATTEMPT),
            "--handoff-artifact-id", str(HANDOFF_ARTIFACT_ID),
            "--handoff-artifact-name", f"uvicorn-rs-coverage-mcp-{CI_RUN_ID}-{CI_ATTEMPT}-{HANDOFF_RUN_ID}-{HANDOFF_ATTEMPT}",
            "--handoff-artifact-size", str(HANDOFF_ARTIFACT_SIZE),
            "--handoff-artifact-digest", HANDOFF_ARTIFACT_DIGEST,
            "--selection-output", str(selection_path),
        )
        run(*verify_args)
        if hashlib.sha256(report.read_bytes()).hexdigest() != raw_sha_before:
            raise AssertionError("projection attachment changed the canonical raw report")

        # A handoff for another CI attempt cannot be accepted even if its page data matches.
        wrong_attempt = list(verify_args)
        wrong_attempt[wrong_attempt.index("--ci-attempt") + 1] = str(CI_ATTEMPT + 1)
        run(*wrong_attempt, expected=1, detail="another CI run or attempt")
        wrong_source = list(verify_args)
        wrong_source[wrong_source.index("--source") + 1] = "e" * 40
        run(*wrong_source, expected=1, detail="source commit differs")

        # The original CI payload must match the pre-review inventory byte for byte.
        (ci_raw / "run.log").write_text("changed after review\n", encoding="utf-8")
        run(*verify_args, expected=1, detail="file tree differs")

        # An MCP chain that advertises another page but omits it is rejected by the attacher.
        broken_root = root / "broken"
        broken_report, broken_receipt, _, broken_review = make_fixture(broken_root)
        broken_projection = broken_review / "coverage-mcp-projection.json"
        run(str(HANDOFF), "project", "--report", str(broken_report), "--output", str(broken_projection))
        broken_ref = broken_projection.relative_to(ROOT).as_posix()
        incomplete_pages = [page(broken_ref, digest_json({"tool": "fixture", "profile": "coverage"}),
                                 "regions", next_offset=15),
                            page(broken_ref, digest_json({"tool": "fixture", "profile": "coverage"}), "lines")]
        write_json(broken_receipt, incomplete_pages)
        broken_reviewed = broken_review / "coverage-report.reviewed.json"
        run(str(ATTACH), "--report", str(broken_projection), "--output", str(broken_reviewed),
            "--receipt", str(broken_receipt),
            expected=1, detail="receipt omits later pages")
    print("PASS coverage MCP handoff: exact raw artifact, reviewed report, source/run binding, and rejection cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
