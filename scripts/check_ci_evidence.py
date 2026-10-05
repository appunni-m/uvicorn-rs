#!/usr/bin/env python3
"""Validate current parity and complete native coverage evidence without rerunning it.

Offline validation reads only repository files and retained evidence. It does
not import the server, protocol clients, reference packages, or coverage tools.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from functools import lru_cache
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests/parity/manifest.json"


class EvidenceError(RuntimeError):
    """A retained report does not establish the required current gate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    def unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        fields = {}
        for name, item in pairs:
            require(name not in fields, f"duplicate JSON field in {path}: {name}")
            fields[name] = item
        return fields

    def reject_constant(value: str) -> None:
        raise EvidenceError(f"nonfinite JSON number in {path}: {value}")

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields,
                       parse_constant=reject_constant)
    require(isinstance(value, dict), f"expected a JSON object: {path}")
    return value


@lru_cache(maxsize=128)
def _literal_constants(path: str, modified: int, size: int) -> dict[str, Any]:
    del modified, size  # File state is part of the cache key.
    constants = {}
    for statement in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign):
            try:
                value = ast.literal_eval(statement.value)
            except (ValueError, TypeError):
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value
    return constants


def source_constant(path: Path, name: str) -> Any:
    """Read literal contract constants without importing an executable runner."""
    state = path.stat()
    constants = _literal_constants(str(path), state.st_mtime_ns, state.st_size)
    require(name in constants, f"missing literal {name} in {path.relative_to(ROOT)}")
    return constants[name]


def exact_keys(value: Any, keys: set[str], label: str) -> None:
    require(isinstance(value, dict) and set(value) == keys, f"invalid {label} envelope")


def repo_path(relative: str) -> Path:
    require(isinstance(relative, str), "repository path must be a string")
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, f"unsafe repository path: {relative!r}")
    resolved = (ROOT / path).resolve()
    require(resolved.is_relative_to(ROOT), f"repository path escapes checkout: {relative!r}")
    return resolved


def git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=True, timeout=20,
    ).stdout.strip()


def valid_digest(value: Any, label: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            f"invalid SHA-256 identity: {label}")
    return value


def load_contract() -> tuple[dict[str, Any], list[dict[str, Any]], list[Path]]:
    manifest = read_json(MANIFEST_PATH)
    runner = ROOT / "scripts/run_parity.py"
    require(manifest.get("schema") == source_constant(runner, "MANIFEST_SCHEMA"), "unsupported manifest schema")
    require(manifest.get("result_schema") == source_constant(runner, "RESULT_SCHEMA"), "unsupported result schema")
    index = manifest.get("inputs")
    require(isinstance(index, list) and bool(index), "manifest has no indexed inputs")
    require(all(isinstance(item, str) for item in index) and len(index) == len(set(index)), "invalid input index")
    paths = []
    for item in index:
        require(item.startswith("inputs/"), f"input is outside the input directory: {item}")
        paths.append(repo_path("tests/parity/" + item))
    require(set(paths) == set((ROOT / "tests/parity/inputs").rglob("*.json")), "input index is incomplete or stale")
    cases = []
    input_schema = source_constant(runner, "INPUT_SCHEMA")
    operations = {operation["id"] for operation in manifest["operations"]}
    profiles = {profile["id"] for profile in manifest["profiles"]}
    for path in paths:
        document = read_json(path)
        require(document.get("schema") == input_schema, f"unsupported input schema: {path}")
        require(isinstance(document.get("cases"), list), f"input has no cases: {path}")
        for case in document["cases"]:
            require(isinstance(case, dict) and isinstance(case.get("case_id"), str), f"invalid case in {path}")
            require(case.get("profile") in profiles and case.get("operation") in operations,
                    f"unindexed case profile or operation: {case['case_id']}")
            require(case.get("verification", "oracle-parity") in {"oracle-parity", "fault-contract"},
                    f"invalid verification policy: {case['case_id']}")
            cases.append(case)
    ids = [case["case_id"] for case in cases]
    require(bool(ids) and len(ids) == len(set(ids)), "case index is empty or duplicated")
    return manifest, cases, paths


def require_summary(summary: dict[str, Any], count: int) -> None:
    expected = {"selected": count, "executed": count, "passed": count,
                "failed": 0, "infrastructure_failed": 0, "not_run": 0}
    require(isinstance(summary, dict) and all(type(value) is int for value in summary.values())
            and summary == expected, f"incomplete or failing result summary: {summary}")


def validate_case_metadata(row: dict[str, Any], case: dict[str, Any]) -> None:
    for field, source_field in (("profile", "profile"), ("operation", "operation"),
                                ("requirements", "covers"), ("fault", "fault")):
        require(row.get(field) == case.get(source_field), f"case contract differs: {case['case_id']} ({field})")
    require(row.get("verification") == case.get("verification", "oracle-parity"),
            f"case verification policy differs: {case['case_id']}")
    require(row.get("status") == "passed", f"case did not pass: {case['case_id']}")


def validate_observations(row: dict[str, Any], case: dict[str, Any], manifest: dict[str, Any]) -> None:
    exact_keys(row, {"case_id", "profile", "operation", "requirements", "verification", "fault", "status",
                     "oracle_observation", "target_observation", "server_exit_codes", "difference"},
               f"case {case['case_id']}")
    exact_keys(row["server_exit_codes"], {"oracle", "target"}, f"case {case['case_id']} server exits")
    operation = next(item for item in manifest["operations"] if item["id"] == case["operation"])
    target = row.get("target_observation")
    oracle = row.get("oracle_observation")
    require(isinstance(target, dict) and set(target) == set(operation["observe"]),
            f"target observation envelope differs: {case['case_id']}")
    require(row.get("difference") is None, f"passing case carries a difference: {case['case_id']}")
    if case.get("verification", "oracle-parity") == "oracle-parity":
        require(isinstance(oracle, dict) and target == oracle, f"live observations differ: {case['case_id']}")
        for field, expected in operation.get("required_observations", {}).items():
            require(target.get(field) == expected, f"required observation differs: {case['case_id']} ({field})")
    else:
        require(oracle is None, f"target-only contract contains oracle observations: {case['case_id']}")


def validate_parity(
    result: dict[str, Any], *, expected_cases: list[dict[str, Any]] | None = None,
    expected_native_sha256: str | None = None, offline: bool = True,
    _current_revision: str | None = None,
) -> dict[str, Any]:
    """Check exact indexed cases; callers may bind evidence to a shipping native hash."""
    manifest, all_cases, input_paths = load_contract()
    if expected_cases is None:
        expected_cases = [case for case in all_cases if case.get("verification", "oracle-parity") == "oracle-parity"]
    expected = {case["case_id"]: case for case in expected_cases}
    require(len(expected) == len(expected_cases) and bool(expected), "expected parity case selection is empty or duplicated")
    exact_keys(result, {"schema", "status", "run", "summary", "cases", "infrastructure_errors"}, "parity report")
    require(result.get("schema") == manifest["result_schema"], "parity report uses a predecessor or unsupported schema")
    require(result.get("status") == "completed" and result.get("infrastructure_errors") == [], "parity did not complete cleanly")
    require_summary(result.get("summary"), len(expected))
    run = result["run"]
    exact_keys(run, {"run_id", "started_at", "finished_at", "manifest", "inputs", "environment", "target", "harness", "command"},
               "parity run")
    require(isinstance(run.get("run_id"), str) and bool(run["run_id"]), "parity run identity is empty")
    require(isinstance(run.get("command"), list) and bool(run["command"])
            and all(isinstance(part, str) for part in run["command"]), "parity command identity is invalid")
    require(run["manifest"] == {"path": "tests/parity/manifest.json", "schema": manifest["schema"],
                                "sha256": sha256(MANIFEST_PATH)}, "parity manifest identity differs from checkout")
    input_schema = source_constant(ROOT / "scripts/run_parity.py", "INPUT_SCHEMA")
    require(run["inputs"] == [{"path": str(path.relative_to(ROOT)), "schema": input_schema, "sha256": sha256(path)}
                               for path in input_paths], "parity input identities differ from checkout")
    target = run["target"]
    exact_keys(target, {"source_sha256", "cargo_lock_sha256", "revision", "dirty", "native_extension"}, "parity target")
    exact_keys(target["native_extension"], {"path", "sha256"}, "parity native")
    require(target.get("source_sha256") == sha256(ROOT / "src/lib.rs"), "parity native source identity differs from checkout")
    require(target.get("cargo_lock_sha256") == sha256(ROOT / "Cargo.lock"), "parity Cargo.lock identity differs")
    require(target.get("revision") == (_current_revision or git_commit()), "parity commit differs from checkout")
    require(type(target.get("dirty")) is bool, "parity has no explicit source-state flag")
    harness = run["harness"]
    exact_keys(harness, {"runner", "runner_sha256", "fixture_app", "fixture_app_sha256", "http3_client"}, "parity harness")
    if harness["http3_client"] is not None:
        exact_keys(harness["http3_client"], {"path", "sha256"}, "HTTP/3 client")
        valid_digest(harness["http3_client"]["sha256"], "HTTP/3 client")
    require(harness.get("runner") == "scripts/run_parity.py" and
            harness.get("runner_sha256") == sha256(ROOT / "scripts/run_parity.py"), "parity runner identity differs")
    require(harness.get("fixture_app") == "tests/parity/app.py" and
            harness.get("fixture_app_sha256") == sha256(ROOT / "tests/parity/app.py"), "parity application identity differs")
    exact_keys(run["environment"], {"python", "platform", "machine", "rustc", "dependencies"}, "parity environment")
    dependencies = run["environment"]["dependencies"]
    require(isinstance(dependencies, dict), "parity dependency identity is invalid")
    for oracle in manifest["oracles"]:
        for distribution, version in [(oracle["id"], oracle["version"]),
                                      *((item["id"], item["version"]) for item in oracle["components"])]:
            require(dependencies.get(distribution) == version, f"parity reference version differs: {distribution}")
    native_sha = valid_digest(target["native_extension"].get("sha256"), "parity native")
    if expected_native_sha256 is not None:
        require(native_sha == expected_native_sha256, "parity did not execute the expected shipping native")
    if not offline:
        imported = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
        require(native_sha == sha256(imported), "parity did not execute the currently imported native")
        recorded = Path(target["native_extension"]["path"])
        require((recorded if recorded.is_absolute() else ROOT / recorded).resolve() == imported,
                "parity native import path differs from current environment")
    rows = result.get("cases")
    require(isinstance(rows, list), "parity has no case rows")
    ids = [row.get("case_id") for row in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected), "parity omitted, added, or duplicated indexed cases")
    for row in rows:
        case = expected[row["case_id"]]
        validate_case_metadata(row, case)
        validate_observations(row, case, manifest)
    return {"status": "passed", "cases": len(expected), "source_sha256": target["source_sha256"],
            "native_sha256": native_sha, "commit": target["revision"], "recorded_dirty": target["dirty"],
            "scope": "retained current evidence; this check does not publish or establish a clean release"}


def llvm_native_regions(report: dict[str, Any], source_digest: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Reconstruct the source region denominator from the retained LLVM export.

    Producer paths can belong to a different CI checkout. Bind the one native
    source file by its suffix, then use that exact producer path throughout.
    """
    data = report.get("data")
    require(isinstance(data, list) and len(data) == 1, "LLVM export must contain one native measurement")
    files = data[0]["files"]
    native_files = [item for item in files if Path(item["filename"]).parts[-2:] == ("src", "lib.rs")]
    require(len(native_files) == 1, "LLVM export must contain exactly one src/lib.rs")
    native_file = native_files[0]
    producer_path = Path(native_file["filename"])
    require(producer_path.is_absolute() and ".." not in producer_path.parts, "invalid LLVM producer source path")
    producer_root = producer_path.parent.parent
    require([item["filename"] for item in files if Path(item["filename"]).is_relative_to(producer_root)]
            == [native_file["filename"]], "LLVM source scope contains additional repository files")
    regions: dict[str, dict[str, Any]] = {}
    for function in data[0]["functions"]:
        for raw in function["regions"]:
            require(isinstance(raw, list) and len(raw) == 8 and all(type(item) is int for item in raw),
                    "invalid raw LLVM region")
            start_line, start_column, end_line, end_column, count, file_index, _, kind = raw
            require(0 <= file_index < len(function["filenames"]), "invalid LLVM region file index")
            if Path(function["filenames"][file_index]) != producer_path:
                continue
            identity = [source_digest, "src/lib.rs", start_line, start_column, end_line, end_column, kind]
            region_id = digest_json(identity)
            region = regions.setdefault(region_id, {"covered": False, "function_symbols": set()})
            region["covered"] |= count > 0
            region["function_symbols"].add(function["name"])
    require(bool(regions), "LLVM export contains no native function regions")
    return regions, native_file["summary"]


def validate_coverage(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    manifest, cases, input_paths = load_contract()
    extension = report.get("uvicorn_rs_unified", {})
    require(report.get("type") == "llvm.coverage.json.export" and
            extension.get("schema") == "uvicorn-rs-coverage/unified@1", "unsupported unified coverage report")
    require(extension.get("status") == "complete", "coverage report is incomplete")
    source = extension["run"]["source"]
    coverage_runner = ROOT / "scripts/run_unified_coverage.py"
    expected_files = {}
    for relative in source_constant(coverage_runner, "SOURCE_PATHS"):
        path = repo_path(relative)
        if path.is_dir():
            expected_files.update({str(item.relative_to(ROOT)): sha256(item) for item in sorted(path.rglob("*.rs"))})
        else:
            expected_files[relative] = sha256(path)
    for relative in source_constant(coverage_runner, "REPORT_INPUT_PATHS"):
        expected_files[relative] = sha256(repo_path(relative))
    expected_files.update({str(path.relative_to(ROOT)): sha256(path) for path in input_paths})
    require(source.get("file_sha256") == expected_files and source.get("sha256") == digest_json(expected_files),
            "coverage source, harness, or input identity differs from checkout")
    require(source.get("revision") == git_commit() and type(source.get("dirty")) is bool, "coverage commit or source-state flag differs")
    require(source.get("manifest_sha256") == sha256(MANIFEST_PATH) and source.get("manifest_schema") == manifest["schema"]
            and source.get("input_manifest_order") == [str(path.relative_to(ROOT)) for path in input_paths],
            "coverage manifest/input index identity differs")
    require(extension["run"]["runner"] == {"path": "scripts/run_unified_coverage.py", "sha256": sha256(coverage_runner)},
            "coverage runner identity differs")
    build = extension["run"]["build"]
    native_sha = valid_digest(build.get("native_extension_sha256"), "coverage native")
    require(build.get("cargo_lock_sha256") == sha256(ROOT / "Cargo.lock"), "coverage build lockfile identity differs")
    require(build.get("tools", {}).get("cargo_llvm_cov") == "cargo-llvm-cov 0.8.7", "coverage tool version differs from pinned CI")
    matrix = extension["matrix"]
    count = len(cases)
    require(matrix.get("scope") == "complete" and matrix.get("manifest_case_count") == count
            and matrix.get("selected") == count and matrix.get("executed") == count and matrix.get("passed") == count,
            "coverage omitted indexed cases")
    require(all(matrix.get(field) == 0 for field in ("failed", "infrastructure_failed", "transient_infrastructure_failures"))
            and matrix.get("case_attribution_complete") is True, "coverage contains failed, retried, or unattributed cases")
    for label, verification in (("oracle_parity", "oracle-parity"), ("fault_contracts", "fault-contract")):
        denominator = sum(case.get("verification", "oracle-parity") == verification for case in cases)
        require(matrix.get(label) == {"selected": denominator, "passed": denominator, "failed": 0},
                f"coverage {label} denominator differs")
    expected = {case["case_id"]: case for case in cases}
    rows = matrix["case_results"]
    ids = [row.get("case_id") for row in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected), "coverage case rows differ from the full index")
    coverage = extension["coverage"]
    require(coverage.get("gate") == "passed" and coverage.get("source_set") == ["src/lib.rs"]
            and coverage.get("uncovered_regions") == [], "native coverage gate or source scope differs")
    attribution = coverage["attribution"]
    require(attribution.get("per_case_profiles") == count and attribution.get("profile_union_matches_attribution") is True
            and attribution.get("case_region_ids_verified") is True and attribution.get("case_region_lookup") == "coverage.regions[].hit_by",
            "coverage profile union/attribution proof is incomplete")
    hit_counts: Counter[str] = Counter()
    case_region_ids: dict[str, set[str]] = {case_id: set() for case_id in expected}
    region_ids = set()
    raw_regions, raw_summary = llvm_native_regions(report, source["sha256"])
    for region in coverage["regions"]:
        require(region.get("file") == "src/lib.rs" and region.get("covered") is True, "uncovered or excluded native region")
        identity = [source["sha256"], region["file"], region["start"]["line"], region["start"]["column"],
                    region["end"]["line"], region["end"]["column"], region["kind"]]
        require(region.get("id") == digest_json(identity) and region["id"] not in region_ids, "invalid or duplicated LLVM region identity")
        region_ids.add(region["id"])
        require(region["id"] in raw_regions and raw_regions[region["id"]]["covered"] is True,
                "attribution region is absent or uncovered in the LLVM union")
        require(isinstance(region.get("function_symbols"), list)
                and len(region["function_symbols"]) == len(set(region["function_symbols"]))
                and set(region["function_symbols"]) == raw_regions[region["id"]]["function_symbols"],
                "attribution region function symbols differ from LLVM")
        hits = region.get("hit_by")
        require(isinstance(hits, list) and bool(hits) and len(hits) == len(set(hits)) and set(hits) <= set(expected),
                "region lacks exact indexed case attribution")
        hit_counts.update(hits)
        for case_id in hits:
            case_region_ids[case_id].add(region["id"])
    for metric in ("regions", "lines"):
        summary = coverage["summary"][metric]
        require(type(summary.get("total")) is int and summary["total"] > 0 and summary.get("missing") == 0
                and summary.get("covered") == summary["total"], f"native {metric} coverage is below 100%")
        require(raw_summary[metric]["count"] == summary["total"] and raw_summary[metric]["covered"] == summary["covered"],
                f"native {metric} summary differs from raw LLVM denominator")
    require(region_ids == set(raw_regions) and len(region_ids) == coverage["summary"]["regions"]["total"],
            "region rows reduced the raw LLVM denominator")
    context = read_json(report_path.with_name(report_path.name + ".context.json"))
    require(context == {"report_sha256": sha256(report_path), "source_hashes": {"src/lib.rs": expected_files["src/lib.rs"]},
                        "build_id": digest_json(build), "scope": "full", "test_status": "passed",
                        "recorded_revision": source["revision"]}, "coverage context receipt differs")
    producer_report = Path(coverage["coverage_mcp"]["measurement_path"])
    require(not producer_report.is_absolute() and ".." not in producer_report.parts, "invalid producer coverage path")

    def artifact(relative: str, digest: str | None = None) -> Path:
        original = Path(relative)
        require(not original.is_absolute() and ".." not in original.parts, "unsafe retained artifact path")
        try:
            remapped = report_path.parent / original.relative_to(producer_report.parent)
        except ValueError as error:
            raise EvidenceError("artifact escapes the retained coverage directory") from error
        path = remapped.resolve()
        require(path.is_relative_to(report_path.parent.resolve()) and path.is_file(), f"missing retained artifact: {relative}")
        if digest is not None:
            require(sha256(path) == valid_digest(digest, relative), f"retained artifact hash differs: {relative}")
        return path

    run_ids = set()
    retained_profiles = set()
    for row in rows:
        case = expected[row["case_id"]]
        validate_case_metadata(row, case)
        require(row.get("error") is None and row.get("transient_infrastructure_failures") == 0
                and row.get("target_extension_sha256") == native_sha, f"invalid attribution result: {case['case_id']}")
        require(row.get("covered_regions") == hit_counts[case["case_id"]] > 0, f"case hit mapping differs: {case['case_id']}")
        # The compact report stores the relation once, on each region's hit_by
        # field. The producer verifies the inverse before omitting its lists.
        require("hit_region_ids" not in row and len(case_region_ids[case["case_id"]]) == row["covered_regions"],
                f"compact case-to-region attribution differs: {case['case_id']}")
        attempts = row.get("attempts")
        require(isinstance(attempts, list) and len(attempts) == 1 and attempts[0].get("attempt") == 1
                and attempts[0].get("runner_exit_code") == 0 and attempts[0].get("status") == "passed",
                f"case contains retries or a failed attempt: {case['case_id']}")
        require(all(attempts[0].get(field) == row.get(field)
                    for field in ("result_artifact", "result_sha256", "profile_data_artifacts")),
                "case attempt artifacts differ from attribution receipt")
        retained = read_json(artifact(row["result_artifact"], row["result_sha256"]))
        validate_parity(retained, expected_cases=[case], expected_native_sha256=native_sha, _current_revision=source["revision"])
        require(row.get("run_id") == retained["run"]["run_id"] and row["run_id"] not in run_ids,
                "attribution run identity differs or is reused")
        run_ids.add(row["run_id"])
        observed = retained["cases"][0]
        require(row.get("observations") == {"oracle": observed["oracle_observation"],
                                             "target": observed["target_observation"], "difference": observed["difference"]},
                f"attribution observations differ: {case['case_id']}")
        require(bool(row.get("profile_data_artifacts")), f"case has no retained target profiles: {case['case_id']}")
        for relative in row["profile_data_artifacts"]:
            profile = artifact(relative)
            require(profile.suffix == ".profraw" and profile.stat().st_size > 0 and profile not in retained_profiles,
                    "empty, reused, or invalid target profile")
            retained_profiles.add(profile)
        require(artifact(str(Path(row["result_artifact"]).parent / "target.profdata")).stat().st_size > 0,
                "case has no retained merged target profile")
    repeats = matrix.get("verification_runs")
    require(matrix.get("verification_runs_required") == 3 and isinstance(repeats, list) and len(repeats) >= 3,
            "coverage requires at least three complete matrix repeats")
    for index, repeat in enumerate(repeats, 1):
        require(repeat.get("run") == index and repeat.get("status") == "completed" and repeat.get("runner_exit_code") == 0
                and repeat.get("transient_infrastructure_failures") == 0, "repeat failed, retried, or is out of order")
        require_summary(repeat["summary"], count)
        require(len(repeat.get("attempts", [])) == 1 and repeat["attempts"][0].get("attempt") == 1
                and repeat["attempts"][0].get("runner_exit_code") == 0, "repeat contains retries or a failed attempt")
        require(all(repeat["attempts"][0].get(field) == repeat.get(field)
                    for field in ("artifact", "sha256", "run_id", "summary", "status")),
                "repeat attempt identity differs from final receipt")
        retained = read_json(artifact(repeat["artifact"], repeat["sha256"]))
        validate_parity(retained, expected_cases=cases, expected_native_sha256=native_sha, _current_revision=source["revision"])
        require(repeat.get("run_id") == retained["run"]["run_id"] and repeat["run_id"] not in run_ids, "repeat run identities differ or repeat")
        run_ids.add(repeat["run_id"])
    require(artifact(extension["artifacts"]["aggregate_profile_data"]).stat().st_size > 0, "empty aggregate profile union")
    require(source.get("revision") == git_commit(), "checkout commit changed while validating coverage")
    return {"status": "passed", "cases": count, "full_repeats": len(repeats), "coverage": coverage["summary"],
            "source_sha256": source["sha256"], "native_sha256": native_sha, "recorded_dirty": source["dirty"],
            "mcp_status": coverage["coverage_mcp"].get("status"),
            "scope": "complete current src/lib.rs native regions/lines; MCP verification is separately recorded"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("parity", "coverage"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--offline", action="store_true", help="validate retained evidence without importing the installed native")
    parser.add_argument("--require-clean", action="store_true", help="require evidence produced from a clean source checkout")
    args = parser.parse_args()
    path = args.report.resolve()
    result = read_json(path)
    checked = validate_parity(result, offline=args.offline) if args.kind == "parity" else validate_coverage(result, path)
    if args.kind == "coverage" and not args.offline:
        imported = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
        require(checked["native_sha256"] == sha256(imported),
                "coverage did not execute the currently imported instrumented native")
    if args.require_clean:
        require(checked["recorded_dirty"] is False, "release evidence was produced from a dirty source checkout")
    print(json.dumps({"kind": args.kind, "report": str(path), **checked}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, ImportError, subprocess.SubprocessError) as error:
        print(f"CI evidence rejected: {error}", file=sys.stderr)
        raise SystemExit(1)
