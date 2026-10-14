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
REPORT_SCHEMA = "uvicorn-rs-coverage/unified@5"


class ReceiptError(RuntimeError):
    """A Coverage-MCP receipt does not match the unified report."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def group_row_identity(group: dict[str, Any]) -> str:
    """Identify an MCP row without collapsing nullable line-function rows."""
    return json.dumps(group, sort_keys=True, separators=(",", ":"))


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

    page_data: dict[str, list[dict[str, Any]]] = {"regions": [], "lines": []}
    common_measurement: dict[str, Any] | None = None
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or set(page) != {"request", "response"}:
            raise ReceiptError(f"Coverage-MCP page {index} lacks its request receipt")
        request = page["request"]
        if not isinstance(request, dict) or set(request) != {
            "measurement", "metric", "offset", "limit", "query", "line"
        }:
            raise ReceiptError(f"Coverage-MCP request {index} has an invalid envelope")
        if request.get("measurement") != expected_reference:
            raise ReceiptError(f"Coverage-MCP request {index} references another report")
        if type(request.get("offset")) is not int or request["offset"] < 0:
            raise ReceiptError(f"Coverage-MCP request {index} has an invalid offset")
        if type(request.get("limit")) is not int or request["limit"] <= 0:
            raise ReceiptError(f"Coverage-MCP request {index} has an invalid limit")
        if request.get("query") is not None or request.get("line") is not None:
            raise ReceiptError("Coverage-MCP acceptance queries must not filter gaps")
        response = page["response"]
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict) or data.get("status") != "measured":
            raise ReceiptError(f"Coverage-MCP page {index} is not a measured result")
        measurement = data.get("measurement", {})
        if (measurement.get("ref") != expected_reference
                or request.get("metric") != measurement.get("coverage", {}).get("metric")):
            raise ReceiptError(f"Coverage-MCP page {index} references another report")
        coverage = measurement.get("coverage", {})
        metric = coverage.get("metric")
        if metric not in page_data:
            raise ReceiptError(f"Coverage-MCP page {index} has unsupported metric {metric!r}")
        identity = {key: value for key, value in measurement.items() if key != "coverage"}
        if common_measurement is None:
            common_measurement = identity
        elif identity != common_measurement:
            raise ReceiptError("Coverage-MCP pages refer to inconsistent source/build measurements")
        page_data[metric].append(page)

    if not page_data["regions"] or not page_data["lines"] or common_measurement is None:
        raise ReceiptError("receipt must include measured region and line pages")
    expected_coverage = extension["coverage"]["summary"]
    first_measurements: dict[str, dict[str, Any]] = {}
    for metric, metric_pages in page_data.items():
        if not metric_pages:
            continue
        first_measurement = metric_pages[0]["response"]["data"]["measurement"]
        if first_measurement.get("coverage") != {
            "covered": expected_coverage[metric]["covered"],
            "metric": metric,
            "missing": expected_coverage[metric]["missing"],
            "total": expected_coverage[metric]["total"],
        }:
            raise ReceiptError(f"Coverage-MCP {metric} totals do not match the unified report")
        if any(data["response"]["data"]["measurement"] != first_measurement for data in metric_pages[1:]):
            raise ReceiptError(f"Coverage-MCP {metric} pages refer to inconsistent measurements")
        first_measurements[metric] = first_measurement

    if common_measurement.get("build_id") != digest_json(extension["run"]["build"]):
        raise ReceiptError("Coverage-MCP build identity does not match the unified report")

    def collect_groups(metric: str) -> tuple[int, list[dict[str, Any]]]:
        metric_pages = page_data[metric]
        if not metric_pages:
            raise ReceiptError(f"Coverage-MCP receipt is missing {metric} pages")
        group_count = metric_pages[0]["response"]["data"].get("group_count")
        if type(group_count) is not int or group_count < 0:
            raise ReceiptError(f"Coverage-MCP {metric} reports an invalid group count")
        expected_offset = 0
        expected_limit = metric_pages[0]["request"]["limit"]
        groups = []
        seen: set[str] = set()
        for page_index, page in enumerate(metric_pages):
            request = page["request"]
            data = page["response"]["data"]
            if data.get("group_count") != group_count:
                raise ReceiptError(f"Coverage-MCP {metric} pages report inconsistent totals")
            if request.get("metric") != metric or request.get("offset") != expected_offset:
                raise ReceiptError(f"Coverage-MCP {metric} cursor chain is broken at page {page_index}")
            if request.get("limit") != expected_limit:
                raise ReceiptError(f"Coverage-MCP {metric} page limits differ")
            page_groups = data.get("groups")
            if not isinstance(page_groups, list):
                raise ReceiptError(f"Coverage-MCP {metric} page {page_index} has invalid groups")
            next_offset = data.get("next_offset")
            if next_offset is not None and (type(next_offset) is not int or next_offset <= expected_offset):
                raise ReceiptError(f"Coverage-MCP {metric} page {page_index} has an invalid next offset")
            if next_offset is None and page_index != len(metric_pages) - 1:
                raise ReceiptError(f"Coverage-MCP {metric} has pages after its terminal page")
            if next_offset is not None and page_index == len(metric_pages) - 1:
                raise ReceiptError(f"Coverage-MCP {metric} receipt omits later pages")
            for group in page_groups:
                if not isinstance(group, dict) or not isinstance(group.get("path"), str):
                    raise ReceiptError(f"Coverage-MCP {metric} returned an invalid group row")
                if "function" not in group or (
                    group["function"] is not None and not isinstance(group["function"], str)
                ):
                    raise ReceiptError(f"Coverage-MCP {metric} returned an invalid function value")
                if type(group.get("count")) is not int or group["count"] < 0:
                    raise ReceiptError(f"Coverage-MCP {metric} returned an invalid group count")
                if not isinstance(group.get("locations"), list):
                    raise ReceiptError(f"Coverage-MCP {metric} returned invalid group locations")
                identity = group_row_identity(group)
                if identity in seen:
                    raise ReceiptError(f"Coverage-MCP returned a duplicate group row: {identity}")
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
            if next_offset is not None:
                expected_offset = next_offset
        if len(groups) != group_count:
            raise ReceiptError(
                f"Coverage-MCP {metric} pagination returned {len(groups)} of {group_count} groups"
            )
        return group_count, groups

    group_count, groups = collect_groups("regions")
    line_group_count, line_groups = collect_groups("lines")
    first_measurement = first_measurements["regions"]
    line_measurement = first_measurements["lines"]
    if first_measurement.get("source") != "matches_receipt" or line_measurement.get("source") != "matches_receipt":
        raise ReceiptError("Coverage-MCP source identity does not match the saved context receipt")
    if first_measurement.get("tests") != "passed" or line_measurement.get("tests") != "passed":
        raise ReceiptError("Coverage-MCP did not observe a passing full input receipt")

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
        "gate": "passed" if group_count == 0 and line_group_count == 0 else "incomplete",
        "measurement_path": expected_reference,
        "metric": "regions",
        "source": first_measurement.get("source"),
        "recorded_revision": first_measurement.get("recorded_revision"),
        "build_id": first_measurement.get("build_id"),
        "tests": first_measurement.get("tests"),
        "coverage": first_measurement["coverage"],
        "line_coverage": (
            first_measurements["lines"]["coverage"] if "lines" in first_measurements else None
        ),
        "group_count": group_count,
        "groups": groups,
        "line_group_count": line_group_count,
        "line_groups": line_groups,
        "location_samples_are_bounded": True,
        "pages": len(page_data["regions"]),
        "line_pages": len(page_data["lines"]),
        "receipt_artifact": str(receipt_path.relative_to(ROOT)) if receipt_path.is_relative_to(ROOT) else str(receipt_path),
        "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
    }
    for region in extension["coverage"]["uncovered_regions"]:
        functions = {
            group["function"]
            for group in groups
            if region["region_id"] in group["sampled_region_ids"]
        }
        region["coverage_mcp_groups"] = sorted(
            functions,
            key=lambda function: "" if function is None else function,
        )

    # Unified per-case region attribution can make the report large. Keep the
    # saved artifact compact so Coverage-MCP can read it under its report-size
    # limit, while preserving the same JSON data and stable key ordering.
    output_bytes = (json.dumps(report, separators=(",", ":"), sort_keys=True) + "\n").encode()
    report_path.write_bytes(output_bytes)
    source_hashes = {
        path: extension["run"]["source"]["file_sha256"][path]
        for path in extension["coverage"]["source_set"]
    }
    matrix = extension["matrix"]
    verification_runs = matrix["verification_runs"]
    native_verification_runs = matrix["native_verification_runs"]
    complete_repeats = (
        matrix.get("verification_runs_required") == 3
        and len(verification_runs) == 3
        and len(native_verification_runs) == 3
        and all(
            item.get("status") in {"complete", "completed"}
            and item.get("runner_exit_code") == 0
            and item.get("summary", {}).get("selected") == matrix["asgi_selected"]
            and item.get("summary", {}).get("passed") == matrix["asgi_selected"]
            and item.get("summary", {}).get("failed") == 0
            and item.get("summary", {}).get("infrastructure_failed") == 0
            and item.get("summary", {}).get("not_run") == 0
            and item.get("transient_infrastructure_failures") == 0
            and len(item.get("attempts", [])) == 1
            for item in verification_runs
        )
        and all(
            item.get("status") == "completed"
            and item.get("runner_exit_code") == 0
            and item.get("selected") == matrix["native_selected"]
            and item.get("passed") == matrix["native_selected"]
            and item.get("failed") == 0
            and item.get("not_run") == 0
            and item.get("transient_infrastructure_failures") == 0
            and len(item.get("attempts", [])) == 1
            for item in native_verification_runs
        )
    )
    passed = (
        matrix["passed"] == matrix["selected"]
        and matrix["failed"] == 0
        and matrix["infrastructure_failed"] == 0
        and (matrix["scope"] != "complete" or complete_repeats)
        and len(page_data["regions"]) > 0
        and len(page_data["lines"]) > 0
        and group_count == 0
        and line_group_count == 0
        and first_measurement.get("source") == "matches_receipt"
        and line_measurement.get("source") == "matches_receipt"
        and first_measurement.get("tests") == "passed"
        and line_measurement.get("tests") == "passed"
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
