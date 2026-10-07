#!/usr/bin/env python3
"""Expose concise unified-coverage failures in GitHub's public check summary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAX_CASE_DIAGNOSTICS = 20
MAX_LOG_CHARS = 5000


def command_value(value: str) -> str:
    """Escape text for a GitHub Actions workflow command property or message."""
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def plain(value: Any, limit: int = 500) -> str:
    """Keep report data on one bounded, Markdown-safe line."""
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")[:limit]


def emit(level: str, title: str, message: str, *, file: str | None = None,
         line: int | None = None) -> None:
    properties = []
    if file:
        properties.append(f"file={command_value(file)}")
    if line is not None and line > 0:
        properties.append(f"line={line}")
    properties.append(f"title={command_value(title)}")
    encoded_properties = ",".join(properties)
    print(f"::{level} {encoded_properties}::{command_value(message)}")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def load_repeat_result(artifact: Any) -> dict[str, Any] | None:
    if not isinstance(artifact, str):
        return None
    path = (ROOT / artifact).resolve()
    allowed_root = (ROOT / "target/asgi-coverage").resolve()
    if not path.is_relative_to(allowed_root) or not path.is_file():
        return None
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def failing_cases(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("cases", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("status") != "passed"]


def summary_passed(summary: Any) -> bool:
    return (
        isinstance(summary, dict)
        and summary.get("selected", 0) == summary.get("executed") == summary.get("passed")
        and summary.get("failed", 0) == 0
        and summary.get("infrastructure_failed", 0) == 0
        and summary.get("not_run", 0) == 0
    )


def case_message(row: dict[str, Any]) -> str:
    fields = [
        f"status={plain(row.get('status', 'unknown'))}",
        f"case={plain(row.get('case_id', 'unknown'))}",
    ]
    error = row.get("error")
    if isinstance(error, dict):
        error_class = error.get("class") or error.get("type") or "error"
        error_message = error.get("message") or error.get("detail") or ""
        fields.append(
            f"error={plain(error_class)}: {plain(error_message, MAX_LOG_CHARS)}"
        )
    elif error:
        fields.append(f"error={plain(error)}")
    difference = row.get("difference")
    if difference:
        fields.append(f"difference={plain(difference)}")
    return "; ".join(fields)


def log_tail(log_path: Path) -> str:
    if not log_path.is_file():
        return "No unified coverage report or run log was written."
    try:
        contents = log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as error:
        return f"Could not read the unified coverage run log: {plain(error)}"
    return contents[-MAX_LOG_CHARS:] or "The unified coverage run log is empty."


def markdown_summary(report: dict[str, Any]) -> tuple[str, list[tuple[str, str, str, int | None]]]:
    extension = report.get("uvicorn_rs_unified")
    if not isinstance(extension, dict):
        raise ValueError("report does not contain uvicorn_rs_unified")
    matrix = extension.get("matrix")
    coverage = extension.get("coverage")
    run = extension.get("run")
    if not isinstance(matrix, dict) or not isinstance(coverage, dict) or not isinstance(run, dict):
        raise ValueError("unified report is missing matrix, coverage, or run identity")

    coverage_summary = coverage.get("summary", {})
    regions = coverage_summary.get("regions", {})
    lines = coverage_summary.get("lines", {})
    matrix_status = (
        f"{matrix.get('passed', 0)}/{matrix.get('selected', 0)} cases; "
        f"failed={matrix.get('failed', 0)}, "
        f"infrastructure_failed={matrix.get('infrastructure_failed', 0)}, "
        f"not_run={matrix.get('selected', 0) - matrix.get('executed', 0)}"
    )
    coverage_status = (
        f"regions {regions.get('covered', 0)}/{regions.get('total', 0)} "
        f"(missing {regions.get('missing', 0)}); "
        f"lines {lines.get('covered', 0)}/{lines.get('total', 0)} "
        f"(missing {lines.get('missing', 0)})"
    )
    repeat_rows = matrix.get("verification_runs", [])
    if not isinstance(repeat_rows, list):
        repeat_rows = []
    repeat_status = ", ".join(
        f"{item.get('run', '?')}: {item.get('status', 'unknown')} "
        f"({item.get('summary', {}).get('passed', 0)}/"
        f"{item.get('summary', {}).get('selected', 0)})"
        for item in repeat_rows if isinstance(item, dict)
    ) or "no repeat results recorded"
    source = run.get("source", {})
    build = run.get("build", {})
    tools = build.get("tools", {})
    rustc = tools.get("rustc", build.get("rustc", "unknown"))
    summary = [
        "## Unified ASGI coverage diagnostics",
        "",
        f"- Gate: **{plain(extension.get('status', 'unknown'))}**; coverage: **{plain(coverage.get('gate', 'unknown'))}**",
        f"- Matrix: {plain(matrix_status)}",
        f"- Repeats: {plain(repeat_status)}",
        f"- Native coverage: {plain(coverage_status)}",
        f"- Revision: `{plain(source.get('revision', 'unknown'))}`; source SHA-256: `{plain(source.get('sha256', 'unknown'))}`",
        f"- Environment: {plain(build.get('platform', 'unknown'))} / {plain(build.get('machine', 'unknown'))}; Python {plain(build.get('python', 'unknown'))}; {plain(rustc)}",
        "",
    ]
    diagnostics: list[tuple[str, str, str, int | None]] = []

    attribution_failures = [
        row for row in matrix.get("case_results", [])
        if isinstance(row, dict) and row.get("status") != "passed"
    ]
    uncovered = coverage.get("uncovered_regions", [])
    if not isinstance(uncovered, list):
        uncovered = []
    repeat_failures = [
        item for item in repeat_rows
        if isinstance(item, dict) and item.get("status") != "completed"
    ]

    if attribution_failures:
        summary.extend(["### Attribution failures", ""])
        for row in attribution_failures[:MAX_CASE_DIAGNOSTICS]:
            message = case_message(row)
            summary.append(
                f"- `{plain(row.get('case_id', 'unknown'))}`: "
                f"{plain(message, MAX_LOG_CHARS)}"
            )
            diagnostics.append(("error", "Coverage attribution failure", message, None))
        if len(attribution_failures) > MAX_CASE_DIAGNOSTICS:
            summary.append(f"- … and {len(attribution_failures) - MAX_CASE_DIAGNOSTICS} more cases")

    if repeat_failures:
        summary.extend(["### Failed full-matrix repeats", ""])
        for item in repeat_failures:
            message = (
                f"repeat={item.get('run', 'unknown')}; status={item.get('status', 'unknown')}; "
                f"summary={item.get('summary', {})}"
            )
            summary.append(f"- {plain(message)}")
            diagnostics.append(("error", "Coverage repeat failure", message, None))
            attempt_rows = item.get("attempts", [])
            for attempt in attempt_rows if isinstance(attempt_rows, list) else []:
                result = load_repeat_result(attempt.get("artifact") if isinstance(attempt, dict) else None)
                if result is None:
                    continue
                for row in failing_cases(result)[:MAX_CASE_DIAGNOSTICS]:
                    detail = case_message(row)
                    summary.append(
                        f"  - `{plain(row.get('case_id', 'unknown'))}`: "
                        f"{plain(detail, MAX_LOG_CHARS)}"
                    )
                    diagnostics.append(("error", "Coverage repeat case failure", detail, None))

    if uncovered:
        summary.extend(["### Uncovered native regions", ""])
        for region in uncovered[:MAX_CASE_DIAGNOSTICS]:
            start = region.get("start", {}) if isinstance(region, dict) else {}
            end = region.get("end", {}) if isinstance(region, dict) else {}
            filename = region.get("file", "src/lib.rs") if isinstance(region, dict) else "src/lib.rs"
            line = start.get("line") if isinstance(start, dict) else None
            message = (
                f"region={region.get('id', 'unknown')}; kind={region.get('kind', 'unknown')}; "
                f"span={line}:{start.get('column', '?')}-"
                f"{end.get('line', '?')}:{end.get('column', '?')}"
            )
            summary.append(f"- `{plain(filename)}:{plain(line)}` — {plain(message)}")
            diagnostics.append(("error", "Uncovered LLVM region", message, line if isinstance(line, int) else None))
        if len(uncovered) > MAX_CASE_DIAGNOSTICS:
            summary.append(f"- … and {len(uncovered) - MAX_CASE_DIAGNOSTICS} more regions")

    if not attribution_failures and not repeat_failures and not uncovered:
        summary.extend(["No failed cases, failed repeats, or uncovered LLVM regions are recorded.", ""])

    return "\n".join(summary), diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    arguments = parser.parse_args()

    report_path = arguments.report
    if not report_path.is_file():
        message = log_tail(arguments.log)
        emit("error", "Unified coverage report unavailable", message)
        summary = "## Unified ASGI coverage diagnostics\n\nNo structured coverage report was written.\n\n```text\n" + plain(message, MAX_LOG_CHARS) + "\n```\n"
        extension = None
    else:
        try:
            report = read_json(report_path)
            summary, diagnostics = markdown_summary(report)
            extension = report.get("uvicorn_rs_unified")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            message = f"Could not summarize unified coverage report: {plain(error)}; {plain(log_tail(arguments.log), 1000)}"
            emit("error", "Unified coverage summary unavailable", message)
            summary = "## Unified ASGI coverage diagnostics\n\n" + plain(message, MAX_LOG_CHARS) + "\n"
            extension = None
            diagnostics = []

        if extension is not None:
            matrix = extension.get("matrix", {})
            coverage = extension.get("coverage", {})
            regions = coverage.get("summary", {}).get("regions", {})
            lines = coverage.get("summary", {}).get("lines", {})
            verification_runs = matrix.get("verification_runs", [])
            matrix_passed = (
                matrix.get("scope") == "complete"
                and matrix.get("case_attribution_complete") is True
                and matrix.get("executed") == matrix.get("selected")
                and matrix.get("passed") == matrix.get("selected")
                and matrix.get("failed") == 0
                and matrix.get("infrastructure_failed") == 0
                and matrix.get("transient_infrastructure_failures") == 0
            )
            repeats_passed = (
                isinstance(verification_runs, list)
                and len(verification_runs) >= matrix.get("verification_runs_required", 3)
                and all(
                    isinstance(item, dict)
                    and item.get("status") == "completed"
                    and item.get("transient_infrastructure_failures", 0) == 0
                    and summary_passed(item.get("summary"))
                    for item in verification_runs
                )
            )
            gate_passed = (
                extension.get("status") == "complete"
                and coverage.get("gate") == "passed"
                and matrix_passed
                and repeats_passed
                and regions.get("missing", 1) == 0
                and lines.get("missing", 1) == 0
            )
            emit(
                "notice" if gate_passed else "error",
                "Unified ASGI coverage",
                f"status={extension.get('status')}; "
                f"cases={matrix.get('passed', 0)}/{matrix.get('selected', 0)}; "
                f"coverage={coverage.get('gate', 'unknown')}; "
                f"regions={regions.get('covered', 0)}/{regions.get('total', 0)}; "
                f"lines={lines.get('covered', 0)}/{lines.get('total', 0)}",
            )
            for level, title, message, line in diagnostics:
                emit(level, title, message, file="src/lib.rs" if title == "Uncovered LLVM region" else None,
                     line=line)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with Path(summary_path).open("a", encoding="utf-8") as summary_file:
                summary_file.write(summary)
        except OSError as error:
            emit("warning", "Unified coverage step summary", f"Could not write step summary: {plain(error)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
