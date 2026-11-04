#!/usr/bin/env python3
"""Verify a reviewed performance decision against exact hosted benchmark bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tomllib

from aggregate_benchmark_matrix import (
    EXPECTED_SYSTEMS,
    assert_common_identity,
    load_system,
    render_markdown,
)
from run_benchmark_categories import source_paths, workload_names


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "uvicorn-rs-performance-review@1"
SYSTEMS = tuple(EXPECTED_SYSTEMS)
LOOPS = ("asyncio", "uvloop")
MINIMUM_MATCHED_REPETITIONS = 3
REQUIRED_METRICS = (
    "operations_per_second",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "server_cpu_microseconds_per_operation",
    "server_rss_sampled_peak_mib",
)
GAIN_METRICS = frozenset(("operations_per_second", "p50_ms", "p95_ms", "p99_ms"))


class AcceptanceError(ValueError):
    """Raised when hosted performance evidence is incomplete or inconsistent."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceError(f"cannot read JSON evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise AcceptanceError(f"expected a JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def safe_relative_file(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    require(not path.is_absolute() and ".." not in path.parts and bool(path.parts),
            f"unsafe artifact path: {relative!r}")
    result = root.joinpath(*path.parts)
    require(result.is_file(), f"required artifact file is missing: {relative}")
    return result


def verify_file_manifest(artifact: Path) -> dict[str, str]:
    manifest = safe_relative_file(artifact, "SHA256SUMS")
    listed: dict[str, str] = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        require(match is not None, "benchmark SHA256SUMS has a malformed row")
        digest, relative = match.groups()
        require(relative not in listed, f"benchmark SHA256SUMS repeats {relative}")
        path = safe_relative_file(artifact, relative)
        require(sha256_file(path) == digest, f"benchmark artifact digest mismatch: {relative}")
        listed[relative] = digest
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file() and path != manifest
    }
    require(set(listed) == actual, "benchmark SHA256SUMS does not cover the exact artifact file set")
    expected = {"matrix.json", "report.md"} | {
        f"evidence/{system}-evidence.tar.gz" for system in SYSTEMS
    }
    require(set(listed) == expected, "benchmark artifact contains missing or unexpected files")
    return listed


def extract_evidence(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                member_path = PurePosixPath(member.name)
                require(not member_path.is_absolute() and ".." not in member_path.parts,
                        f"unsafe path in benchmark evidence archive: {member.name!r}")
                require(member.isfile(), f"unsupported member in benchmark evidence archive: {member.name!r}")
                target = destination.joinpath(*member_path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                require(source is not None, f"cannot read benchmark evidence archive member: {member.name}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
    except (OSError, tarfile.TarError) as error:
        raise AcceptanceError(f"cannot read benchmark evidence archive {archive_path}: {error}") from error


def verify_source_identity(identity: dict, expected_commit: str, expected_native: str,
                           system_id: str) -> None:
    require(identity.get("git_revision") == expected_commit,
            "benchmark run commit differs from the release commit")
    require(identity.get("dirty_target") is False and identity.get("tracked_worktree_changes") == [],
            "benchmark run did not use a clean source tree")
    require(identity.get("optional_workloads", {}).get("fastapi", {}).get("selected") is True,
            "benchmark did not select stock FastAPI workloads")
    native_digest = identity.get("native")
    require(isinstance(native_digest, str) and re.fullmatch(r"[0-9a-f]{64}", native_digest),
            f"{system_id}: measured native extension digest is missing or malformed")
    if system_id == "linux-x86_64":
        require(native_digest == expected_native,
                "Linux x86-64 benchmark binary differs from the normal release candidate binary")
    runtime = identity.get("python_runtime")
    runtime_version = runtime.get("version") if isinstance(runtime, dict) else None
    require(isinstance(runtime, dict)
            and isinstance(runtime_version, str) and runtime_version.split()
            and runtime_version.split(maxsplit=1)[0] == "3.12.13",
            f"{system_id}: benchmark Python runtime differs from the maintained 3.12.13 build")

    snapshot = identity.get("snapshot")
    require(isinstance(snapshot, dict), "benchmark source snapshot is missing")
    source_files = snapshot.get("source_files")
    require(isinstance(source_files, dict) and source_files,
            "benchmark source file inventory is missing")
    expected_paths = set(source_paths(ROOT))
    require(set(source_files) == expected_paths,
            "benchmark source inventory differs from the release checkout")
    for relative, recorded in source_files.items():
        path = safe_relative_file(ROOT, relative)
        require(isinstance(recorded, str) and re.fullmatch(r"[0-9a-f]{64}", recorded)
                and sha256_file(path) == recorded,
                f"benchmark source hash differs from the release checkout: {relative}")
    source_digest = sha256_bytes(json.dumps(source_files, sort_keys=True).encode())
    require(snapshot.get("source_sha256") == source_digest,
            "benchmark combined source snapshot digest is invalid")
    require(identity.get("source") == source_files.get("src/lib.rs"),
            "benchmark Rust server source digest is inconsistent")
    extension = snapshot.get("native_extension")
    require(isinstance(extension, dict) and extension.get("sha256") == native_digest
            and identity.get("native") == extension.get("sha256"),
            "benchmark native extension identity is inconsistent")
    harness = {key: value for key, value in source_files.items() if key.startswith("scripts/")}
    examples = {key: value for key, value in source_files.items() if key.startswith("examples/")}
    require(identity.get("harness") == harness and identity.get("examples") == examples,
            "benchmark harness/example source identity is inconsistent")
    require(identity.get("wrapper_sha256") == harness.get("scripts/run_benchmark_categories.py"),
            "benchmark driver hash differs from its source snapshot")

    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked_versions: dict[str, set[str]] = {}
    for package in lock.get("package", []):
        name = str(package.get("name", "")).lower().replace("_", "-")
        version = package.get("version")
        if name and isinstance(version, str):
            locked_versions.setdefault(name, set()).add(version)
    dependencies = identity.get("dependencies")
    require(isinstance(dependencies, dict) and dependencies,
            "benchmark dependency identity is missing")
    required = {"fastapi", "starlette", "uvicorn", "uvicorn-rs", "uvloop", "httptools"}
    require(required <= set(dependencies), "benchmark omitted a required upstream dependency identity")
    forbidden_references = {"fastapi-rs", "starlette-rs"}
    require(not (forbidden_references & {
        name.lower().replace("_", "-") for name in dependencies
    }), "benchmark included FastAPI-RS or Starlette-RS instead of stock Python frameworks")
    for raw_name, package in dependencies.items():
        name = raw_name.lower().replace("_", "-")
        require(isinstance(package, dict), f"malformed dependency identity: {raw_name}")
        version = package.get("version")
        require(isinstance(version, str) and version in locked_versions.get(name, set()),
                f"measured dependency {raw_name} is not pinned to uv.lock")
        require(not package.get("record_content_mismatches") and not package.get("unrecorded_source_files")
                and not package.get("native_instrumentation_detected"),
                f"measured dependency has modified or instrumented files: {raw_name}")
        direct_url = package.get("direct_url")
        require(not (isinstance(direct_url, dict)
                     and direct_url.get("dir_info", {}).get("editable")),
                f"measured dependency is editable: {raw_name}")


def verify_complete_matrix(matrix: dict, arguments: argparse.Namespace,
                           artifact_hashes: dict[str, str], work: Path) -> dict:
    require(matrix.get("schema") == "uvicorn-rs-benchmark-matrix@2",
            "unsupported benchmark matrix schema")
    require(matrix.get("status") == "validated_complete_matrix",
            f"benchmark matrix is not complete: {matrix.get('status')!r}")
    require(matrix.get("repository") == arguments.repository,
            "benchmark matrix repository differs from the release repository")
    require(matrix.get("commit") == arguments.expected_commit,
            "benchmark matrix commit differs from the release commit")
    require(str(matrix.get("run_id")) == str(arguments.run_id)
            and matrix.get("run_attempt") == arguments.run_attempt,
            "benchmark matrix run identity differs from the selected workflow run")
    require(matrix.get("system_ids") == list(SYSTEMS),
            "benchmark matrix system inventory differs from the maintained inventory")
    require(matrix.get("workflow_run_url") ==
            f"https://github.com/{arguments.repository}/actions/runs/{arguments.run_id}",
            "benchmark matrix run URL is inconsistent")
    reported = matrix.get("systems")
    require(isinstance(reported, list) and all(isinstance(item, dict) for item in reported)
            and {item.get("system_id") for item in reported} == set(SYSTEMS),
            "benchmark matrix does not contain exactly the maintained systems")

    recomputed: list[dict] = []
    source_identity: dict | None = None
    native_hashes: dict[str, str] = {}
    for system_id in SYSTEMS:
        archive_path = safe_relative_file(arguments.artifact_dir,
                                          f"evidence/{system_id}-evidence.tar.gz")
        extracted = work / f"{system_id}-evidence"
        extract_evidence(archive_path, extracted)
        run = read_json(extracted / "benchmark-categories/run.json")
        identity = run.get("identity_before")
        require(isinstance(identity, dict) and run.get("identity_after") == identity,
                f"{system_id}: benchmark identity changed during measurement")
        verify_source_identity(identity, arguments.expected_commit,
                               arguments.expected_native_sha256, system_id)
        native_binary = safe_relative_file(extracted, "benchmark-preparation/native-extension.bin")
        native_bytes = native_binary.read_bytes()
        require(sha256_bytes(native_bytes) == identity["native"],
                f"{system_id}: retained benchmark extension differs from the measured extension")
        forbidden_markers = (b"coverage-injected", b"UVICORN_RS_COVERAGE_", b"__llvm_profile",
                             b"__llvm_covmap", b"uvicorn-rs-runtime-diagnostics ")
        require(not any(marker in native_bytes for marker in forbidden_markers),
                f"{system_id}: retained benchmark extension contains instrumentation/diagnostic markers")
        native_hashes[system_id] = identity["native"]
        if source_identity is None:
            source_identity = identity
        else:
            for key in ("source", "harness", "examples", "dependencies", "optional_workloads"):
                require(identity.get(key) == source_identity.get(key),
                        f"benchmark runner identities differ across systems for {key}")
        artifact = work / f"asgi-category-benchmarks-{system_id}"
        artifact.mkdir()
        # load_system consumes the retained bundle with the same input schema as
        # the platform artifact; copy only its top-level evidence directories.
        for name in ("benchmark-preparation", "benchmark-categories", "fastapi-only"):
            shutil.copytree(extracted / name, artifact / name)
        recomputed.append(load_system(artifact, system_id, arguments.expected_commit))

    assert_common_identity(recomputed)
    by_system = {item["system_id"]: item for item in reported}
    for system in recomputed:
        require(by_system[system["system_id"]] == system,
                f"aggregated matrix differs from retained {system['system_id']} source evidence")
        require(system["matrix_status"] == "validated_complete_system",
                f"{system['system_id']}: category matrix is incomplete")
        require(system["benchmark_parameters"].get("repetitions", 0) >= MINIMUM_MATCHED_REPETITIONS,
                f"{system['system_id']}: fewer than three repetitions were requested")

    return {"matrix": matrix, "systems": by_system, "source_identity": source_identity,
            "native_hashes": native_hashes,
            "artifact_hashes": artifact_hashes}


def fastapi_workloads() -> list[str]:
    return [name for name in workload_names(ROOT / "scripts/run_http_category_bench.py")
            if name.startswith("fastapi-")]


def pair_map(system: dict) -> dict[tuple[str, str], dict]:
    pairs = system["categories"]["http1"].get("pairs", [])
    result = {}
    for pair in pairs:
        key = (pair.get("workload"), pair.get("loop"))
        require(key not in result, f"duplicate HTTP/1 workload/loop comparison: {key}")
        result[key] = pair
    return result


def validate_pair(pair: dict, *, system_id: str, workload: str, loop: str) -> list[int]:
    expected_reference = "uvicorn-asyncio-httptools" if loop == "asyncio" else "uvicorn-uvloop-httptools"
    expected_candidate = "uvicorn-rs-asyncio" if loop == "asyncio" else "uvicorn-rs-uvloop"
    require(pair.get("reference") == expected_reference and pair.get("candidate") == expected_candidate,
            f"{system_id}/{workload}/{loop}: comparison is not stock Uvicorn vs the uvicorn-rs PyPI distribution")
    matches = pair.get("matched_repetitions")
    minimum = pair.get("minimum_required")
    require(isinstance(matches, list) and len(matches) >= MINIMUM_MATCHED_REPETITIONS
            and len(matches) == len(set(matches))
            and all(type(value) is int and value > 0 for value in matches),
            f"{system_id}/{workload}/{loop}: fewer than three unique matched repetitions")
    require(pair.get("qualified") is True and type(minimum) is int
            and MINIMUM_MATCHED_REPETITIONS <= minimum <= len(matches),
            f"{system_id}/{workload}/{loop}: workload pair is not qualified")
    require(pair.get("recorded_pair_gate", {}).get("outcome") == "available",
            f"{system_id}/{workload}/{loop}: recorded comparison gate is unavailable")
    for metric_name in REQUIRED_METRICS:
        values = pair.get("metrics", {}).get(metric_name)
        require(isinstance(values, dict)
                and values.get("matched_repetitions") == matches
                and type(values.get("minimum_required")) is int
                and MINIMUM_MATCHED_REPETITIONS <= values["minimum_required"] <= len(matches)
                and all(type(values.get(side)) in (int, float)
                        and math.isfinite(values[side]) and values[side] > 0
                        for side in ("reference", "rust")),
                f"{system_id}/{workload}/{loop}: required metric {metric_name} is absent or invalid")
    return matches


def validate_review(review: dict, pair_indexes: dict[str, dict[tuple[str, str], dict]],
                    workloads: list[str]) -> list[dict]:
    require(review.get("schema") == SCHEMA, "unsupported performance review schema")
    scope = review.get("scope")
    require(isinstance(scope, dict), "performance review scope is missing")
    require(scope.get("comparison") == "stock FastAPI and Starlette under the uvicorn-rs PyPI distribution versus Uvicorn",
            "performance review does not declare the maintained stock-FastAPI comparison")
    require(scope.get("systems") == list(SYSTEMS)
            and scope.get("loops") == list(LOOPS)
            and scope.get("category") == "http1"
            and scope.get("workloads") == workloads
            and scope.get("minimum_matched_repetitions") == MINIMUM_MATCHED_REPETITIONS
            and scope.get("required_metrics") == list(REQUIRED_METRICS),
            "performance review scope differs from the maintained benchmark matrix")
    require(isinstance(review.get("rationale"), str) and review["rationale"].strip(),
            "performance review decision needs a written rationale")

    decision = review.get("decision")
    if decision == "not_proven":
        raise AcceptanceError("performance review decision is not_proven")
    require(decision in {"gain_proven", "scope_revised"},
            f"unsupported performance review decision: {decision!r}")

    verified_claims: list[dict] = []
    if decision == "gain_proven":
        claims = review.get("claims")
        require(isinstance(claims, list) and claims,
                "gain_proven requires at least one measured performance claim")
        seen_ids: set[str] = set()
        for claim in claims:
            require(isinstance(claim, dict), "performance claim must be an object")
            claim_id = claim.get("id")
            require(isinstance(claim_id, str) and claim_id.strip() and claim_id not in seen_ids,
                    "performance claim identifiers must be non-empty and unique")
            seen_ids.add(claim_id)
            require(isinstance(claim.get("statement"), str) and claim["statement"].strip(),
                    f"{claim_id}: a user-facing claim statement is required")
            metric_name = claim.get("metric")
            require(metric_name in GAIN_METRICS,
                    f"{claim_id}: a gain claim must be based on throughput or latency")
            expected_direction = "higher" if metric_name == "operations_per_second" else "lower"
            require(claim.get("direction") == expected_direction,
                    f"{claim_id}: metric direction conflicts with its definition")
            claim_workloads = claim.get("workloads")
            require(isinstance(claim_workloads, list) and claim_workloads
                    and len(claim_workloads) == len(set(claim_workloads))
                    and set(claim_workloads) <= set(workloads),
                    f"{claim_id}: claim workload set is invalid")
            metric_phrases = {
                "operations_per_second": "higher throughput",
                "p50_ms": "lower p50 latency",
                "p95_ms": "lower p95 latency",
                "p99_ms": "lower p99 latency",
            }
            expected_statement = (
                f"The uvicorn-rs PyPI distribution showed {metric_phrases[metric_name]} than stock Uvicorn for "
                f"{', '.join(claim_workloads)} on every maintained system and both asyncio and "
                "uvloop profiles, with at least three matched valid repetitions per comparison."
            )
            require(claim.get("statement") == expected_statement,
                    f"{claim_id}: statement must match the exact evidence scope")
            observations = []
            for system_id in SYSTEMS:
                for workload in claim_workloads:
                    for loop in LOOPS:
                        pair = pair_indexes[system_id].get((workload, loop))
                        require(pair is not None, f"{claim_id}: missing pair {system_id}/{workload}/{loop}")
                        repetitions = validate_pair(pair, system_id=system_id, workload=workload, loop=loop)
                        values = pair["metrics"][metric_name]
                        ratio = values["rust"] / values["reference"]
                        improving = ratio > 1 if expected_direction == "higher" else ratio < 1
                        require(improving,
                                f"{claim_id}: measured {system_id}/{workload}/{loop} does not support the claim")
                        observations.append({"system": system_id, "workload": workload, "loop": loop,
                                            "matched_repetitions": repetitions, "rust_over_reference": ratio})
            verified_claims.append({"id": claim_id, "statement": claim["statement"],
                                    "metric": metric_name, "direction": expected_direction,
                                    "workloads": claim_workloads, "observations": observations})
        require(review.get("scope_revision") in (None, {}),
                "gain_proven cannot also carry a scope revision")
    else:
        revision = review.get("scope_revision")
        require(isinstance(revision, dict), "scope_revised requires a scope_revision record")
        document = revision.get("document")
        require(isinstance(document, str) and document.startswith("docs/")
                and not Path(document).is_absolute() and ".." not in Path(document).parts,
                "scope revision must cite a repository documentation file")
        require((ROOT / document).is_file(), "scope revision document is missing from the release commit")
        require(isinstance(revision.get("statement"), str) and revision["statement"].strip()
                and isinstance(revision.get("rationale"), str) and revision["rationale"].strip(),
                "scope revision needs a statement and rationale")
        evidence = revision.get("measured_pairs")
        require(isinstance(evidence, list) and evidence,
                "scope revision must cite retained measured pairs")
        for row in evidence:
            require(isinstance(row, dict), "scope revision evidence pair must be an object")
            system_id, workload, loop = row.get("system"), row.get("workload"), row.get("loop")
            require(system_id in SYSTEMS and workload in workloads and loop in LOOPS,
                    "scope revision cites a pair outside the maintained benchmark inventory")
            pair = pair_indexes[system_id].get((workload, loop))
            require(pair is not None, f"scope revision cites a missing pair: {row}")
            validate_pair(pair, system_id=system_id, workload=workload, loop=loop)
        verified_claims.append({"scope_revision": revision})
        require(review.get("claims") in (None, []),
                "scope_revised must not carry gain claims")
    return verified_claims


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-size", type=int, required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--expected-native-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    require(re.fullmatch(r"[0-9a-f]{40}", args.expected_commit) is not None,
            "expected commit must be a full lowercase SHA")
    require(args.run_attempt > 0 and args.artifact_id > 0 and args.artifact_size > 0,
            "benchmark run/artifact metadata is invalid")
    expected_artifact_name = f"asgi-benchmark-matrix-{args.run_id}-{args.run_attempt}"
    require(args.artifact_name == expected_artifact_name,
            "selected artifact name does not match the benchmark run and attempt")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", args.artifact_digest) is not None,
            "GitHub benchmark artifact digest is missing or malformed")
    require(re.fullmatch(r"[0-9a-f]{64}", args.expected_native_sha256) is not None,
            "expected normal native extension hash is malformed")

    artifact_hashes = verify_file_manifest(args.artifact_dir)
    matrix_path = safe_relative_file(args.artifact_dir, "matrix.json")
    matrix = read_json(matrix_path)
    work = args.receipt.parent / ".performance-evidence-verify"
    require(not work.exists(), f"verification scratch path already exists: {work}")
    work.mkdir(parents=True)
    try:
        complete = verify_complete_matrix(matrix, args, artifact_hashes, work)
        workloads = fastapi_workloads()
        require(len(workloads) == 15,
                f"maintained stock-FastAPI HTTP/1 workload inventory changed: {len(workloads)}")
        pair_indexes = {system_id: pair_map(system) for system_id, system in complete["systems"].items()}
        expected_pairs = {(workload, loop) for workload in workloads for loop in LOOPS}
        for system_id, pairs in pair_indexes.items():
            require(set(pairs) == expected_pairs,
                    f"{system_id}: HTTP/1 FastAPI comparison inventory differs from the maintained scope")
            http1 = complete["systems"][system_id]["category_integrity"]["http1"]
            require(http1["execution"].get("correctness_failures") == 0
                    and http1["execution"].get("exact_planned_rows_present") is True
                    and http1["execution"].get("category_identity_stable") is True,
                    f"{system_id}: correctness-gated HTTP/1 evidence is incomplete")

        review = read_json(args.review)
        claims = validate_review(review, pair_indexes, workloads)
        report_path = safe_relative_file(args.artifact_dir, "report.md")
        report_text = report_path.read_text()
        require(report_text == render_markdown(matrix),
                "human-readable matrix report does not match the validated matrix")
        evidence_hashes = {
            name: digest for name, digest in artifact_hashes.items() if name.startswith("evidence/")
        }
        artifact_tree = sha256_bytes("".join(f"{name}  {digest}\n" for name, digest in
                                              sorted(artifact_hashes.items())).encode())
        receipt = {
            "schema": "uvicorn-rs-performance-acceptance@1",
            "status": "verified",
            "decision": review["decision"],
            "decision_rationale": review["rationale"],
            "review_sha256": sha256_file(args.review),
            "release_commit": args.expected_commit,
            "repository": args.repository,
            "workflow_run_id": args.run_id,
            "workflow_run_attempt": args.run_attempt,
            "artifact_id": args.artifact_id,
            "artifact_name": args.artifact_name,
            "artifact_size_bytes": args.artifact_size,
            "github_artifact_digest": args.artifact_digest,
            "artifact_tree_sha256": artifact_tree,
            "matrix_sha256": artifact_hashes["matrix.json"],
            "report_sha256": artifact_hashes["report.md"],
            "system_evidence_sha256": evidence_hashes,
            "source_sha256": matrix["systems"][0]["source_sha256"],
            "native_extension_sha256_by_system": complete["native_hashes"],
            "systems": list(SYSTEMS),
            "workloads": workloads,
            "loops": list(LOOPS),
            "minimum_matched_repetitions": MINIMUM_MATCHED_REPETITIONS,
            "required_metrics": list(REQUIRED_METRICS),
            "verified_claims": claims,
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"status": receipt["status"], "decision": receipt["decision"],
                          "run_id": args.run_id, "run_attempt": args.run_attempt,
                          "artifact_id": args.artifact_id, "artifact_tree_sha256": artifact_tree,
                          "claim_count": len(claims), "receipt": str(args.receipt)}))
        return 0
    finally:
        shutil.rmtree(work)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"performance acceptance verification failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
