#!/usr/bin/env python3
"""Attach paginated Coverage-MCP gap evidence to a unified LLVM report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_KEY = "uvicorn_rs_unified"
REPORT_SCHEMA = "uvicorn-rs-coverage/unified@1"


class ReceiptError(RuntimeError):
    """A Coverage-MCP receipt does not match the unified report."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True, help="JSON array of Coverage-MCP structuredContent pages")
    args = parser.parse_args()
    report_path = args.report.resolve()
    receipt_path = args.receipt.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pages = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(pages, list) or not pages:
        raise ReceiptError("receipt must be a non-empty array of Coverage-MCP page objects")
    extension = report.get(EXTENSION_KEY)
    if not isinstance(extension, dict) or extension.get("schema") != REPORT_SCHEMA:
        raise ReceiptError("report does not contain the unified coverage extension")
    expected_reference = str(report_path.relative_to(ROOT))

    page_data: list[dict[str, Any]] = []
    for index, page in enumerate(pages):
        data = page.get("data")
        if not isinstance(data, dict) or data.get("status") != "measured":
            raise ReceiptError(f"Coverage-MCP page {index} is not a measured result")
        measurement = data.get("measurement", {})
        if measurement.get("ref") != expected_reference:
            raise ReceiptError(f"Coverage-MCP page {index} references another report")
        page_data.append(data)

    first_measurement = page_data[0]["measurement"]
    if first_measurement.get("build_id") != digest_json(extension["run"]["build"]):
        raise ReceiptError("Coverage-MCP build identity does not match the unified report")
    coverage_summary = extension["coverage"]["summary"]["regions"]
    if first_measurement.get("coverage") != {
        "covered": coverage_summary["covered"],
        "metric": "regions",
        "missing": coverage_summary["missing"],
        "total": coverage_summary["total"],
    }:
        raise ReceiptError("Coverage-MCP region totals do not match the unified report")
    if any(data["measurement"] != first_measurement for data in page_data[1:]):
        raise ReceiptError("Coverage-MCP pages refer to inconsistent source/build measurements")

    group_count = page_data[0]["group_count"]
    groups = []
    seen: set[tuple[str, str]] = set()
    for data in page_data:
        for group in data.get("groups", []):
            identity = (group["path"], group["function"])
            if identity in seen:
                raise ReceiptError(f"Coverage-MCP returned a duplicate function group: {identity}")
            seen.add(identity)
            groups.append({
                "file": group["path"],
                "function": group["function"],
                "missing_observations": group["count"],
                "sampled_locations": [
                    {"span": location["span"], "arm": location.get("arm")}
                    for location in group.get("locations", [])
                ],
                "locations_omitted": group.get("locations_omitted", 0),
                "unmeasured_reason": group.get("unmeasured_reason"),
            })
    if len(groups) != group_count:
        raise ReceiptError(f"Coverage-MCP pagination returned {len(groups)} of {group_count} groups")

    span_to_regions: dict[tuple[str, int, int, int, int], list[str]] = {}
    for region in extension["coverage"]["regions"]:
        key = (
            region["file"],
            region["start"]["line"],
            region["start"]["column"],
            region["end"]["line"],
            region["end"]["column"],
        )
        span_to_regions.setdefault(key, []).append(region["id"])
    for group in groups:
        sampled_ids = set()
        for location in group["sampled_locations"]:
            line_start, column_start, line_end, column_end = location["span"]
            key = (group["file"], line_start, column_start, line_end, column_end)
            sampled_ids.update(span_to_regions.get(key, []))
        group["sampled_region_ids"] = sorted(sampled_ids)

    extension["coverage"]["coverage_mcp"] = {
        "status": "measured",
        "measurement_path": expected_reference,
        "metric": "regions",
        "source": first_measurement.get("source"),
        "recorded_revision": first_measurement.get("recorded_revision"),
        "build_id": first_measurement.get("build_id"),
        "tests": first_measurement.get("tests"),
        "coverage": first_measurement["coverage"],
        "group_count": group_count,
        "groups": groups,
        "location_samples_are_bounded": True,
        "pages": len(page_data),
        "receipt_artifact": str(receipt_path.relative_to(ROOT)) if receipt_path.is_relative_to(ROOT) else str(receipt_path),
    }
    for region in extension["coverage"]["uncovered_regions"]:
        region["coverage_mcp_groups"] = sorted(
            group["function"]
            for group in groups
            if region["region_id"] in group["sampled_region_ids"]
        )

    output_bytes = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    report_path.write_bytes(output_bytes)
    source_hashes = {
        path: digest
        for path, digest in extension["run"]["source"]["file_sha256"].items()
        if path in {"src/lib.rs"}
    }
    matrix = extension["matrix"]
    verification_runs = matrix["verification_runs"]
    complete_repeats = (
        len(verification_runs) >= max(3, matrix.get("verification_runs_required", 3))
        and all(
            item.get("status") in {"complete", "completed"}
            and item.get("runner_exit_code") == 0
            and item.get("summary", {}).get("passed") == matrix["selected"]
            and item.get("summary", {}).get("failed") == 0
            and item.get("summary", {}).get("infrastructure_failed") == 0
            and item.get("summary", {}).get("not_run") == 0
            for item in verification_runs
        )
    )
    passed = (
        matrix["passed"] == matrix["selected"]
        and matrix["failed"] == 0
        and matrix["infrastructure_failed"] == 0
        and (matrix["scope"] != "complete" or complete_repeats)
    )
    context = {
        "report_sha256": sha256_bytes(output_bytes),
        "source_hashes": source_hashes,
        "build_id": digest_json(extension["run"]["build"]),
        "scope": "full" if matrix["scope"] == "complete" else "selected_tests",
        "test_status": "passed" if passed else "failed",
        "recorded_revision": extension["run"]["source"]["revision"],
    }
    report_path.with_name(report_path.name + ".context.json").write_text(
        json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "report": str(report_path),
        "coverage_mcp": extension["coverage"]["coverage_mcp"],
        "receipt": str(report_path.with_name(report_path.name + ".context.json")),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReceiptError, OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SystemExit(f"coverage-mcp receipt error: {error}")
