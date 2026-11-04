#!/usr/bin/env python3
"""Run the frozen buffer on/off experiment on one quiet hosted runner.

The existing focused workflow installs the normal reuse wheel first. This
driver builds the fresh-allocation control in a separate checkout/target,
verifies affected public parity on both installed wheels, then executes every
adjacent pair exactly once. This is not a stock-server speed comparison.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from benchmark_evidence import assert_clean_coverage_environment
from parity_identity import runtime_source_digest, runtime_source_hashes

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tests/performance/peer-read-comparison.json"
PATCH = ROOT / "tests/performance/peer-read-fresh-allocation.patch"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def run(command: list[str], root: Path, log: Path, **kwargs) -> None:
    with log.open("x") as stream:
        subprocess.run(command, cwd=root, stdout=stream,
                       stderr=subprocess.STDOUT, check=True, **kwargs)


def absolute_python(path: Path) -> Path:
    """Keep a virtualenv interpreter's symlink so Python loads that environment."""
    return path.absolute()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    oracle = absolute_python(args.oracle_python)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = json.loads(PLAN.read_text())
    assert len(plan["pairs"]) == plan["planned_pairs"] == 40
    assert_clean_coverage_environment()
    assert not any(os.environ.get(key) for key in (
        "UVICORN_RS_UPLOAD_TRACE", "UVICORN_RS_DIAGNOSTIC_PEER_READ_MODE"))
    assert not git(ROOT, "status", "--porcelain", "--untracked-files=all")
    hashes = runtime_source_hashes(ROOT)
    assert runtime_source_digest(hashes) == plan["accepted_runtime_sha256"]
    revision = git(ROOT, "rev-parse", "HEAD")
    journal = {"schema": "peer-read-hosted-execution@1",
               "plan_sha256": sha(PLAN), "control_patch_sha256": sha(PATCH),
               "driver_sha256": sha(Path(__file__)), "source_revision": revision,
               "started_at": datetime.now(timezone.utc).isoformat(),
               "variants": {}, "attempts": [], "complete": False,
               "scope": "normal on/off builds on this runner; no stock-server speed claim"}
    def checkpoint():
        write(output / "execution.json", journal)
    checkpoint()
    control = output / "fresh-source"
    run(["git", "clone", "--shared", "--no-checkout", str(ROOT), str(control)],
        ROOT, output / "control-clone.log")
    git(control, "checkout", "-B", "develop", revision)
    git(control, "apply", "--check", str(PATCH))
    git(control, "apply", str(PATCH))
    control_hashes = runtime_source_hashes(control)
    assert control_hashes.keys() == hashes.keys()
    assert [name for name in hashes if hashes[name] != control_hashes[name]] == [
        "crates/uvicorn-rs/src/peer_read.rs"]
    git(control, "add", "crates/uvicorn-rs/src/peer_read.rs")
    git(control, "-c", "user.name=Buffer comparison", "-c",
        "user.email=buffer-comparison@localhost", "commit", "-m",
        "Experimental fresh-allocation control; do not publish")
    assert not git(control, "status", "--porcelain", "--untracked-files=all")
    run(["uv", "sync", "--python", "3.12.13", "--group", "benchmark",
         "--group", "fastapi-benchmark", "--frozen", "--no-install-project"],
        control, output / "control-sync.log")
    python = control / ".venv/bin/python"
    wheels = output / "control-wheels"
    wheels.mkdir()
    target = output / "control-cargo-target"
    assert not target.exists()
    run(["uvx", "--from", "maturin==1.14.1", "maturin", "build", "--release",
         "--locked", "--interpreter", str(python), "--out", str(wheels)],
        control, output / "control-build.log",
        env={**os.environ, "CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0"})
    wheel, = wheels.glob("*.whl")
    run(["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
        control, output / "control-install.log")
    clones = {"fresh": control, "reuse": ROOT}
    for variant, clone in clones.items():
        report = output / (variant + "-parity.json")
        command = [str(clone / ".venv/bin/python"), str(clone / "scripts/run_parity.py"),
                   "--oracle-python", str(oracle), "--installed-candidate",
                   "--output", str(report)]
        for case in plan["case_ids"]:
            command.extend(["--case-id", case])
        run(command, clone, output / (variant + "-parity.log"))
        result = json.loads(report.read_text())
        assert result["summary"] == {"selected": 13, "executed": 13, "passed": 13,
                                      "failed": 0, "not_run": 0, "infrastructure_failed": 0}
        identity = result["run"]["target"]
        assert identity["dirty"] is False
        assert identity["source_files"] == runtime_source_hashes(clone)
        assert identity["revision"] == git(clone, "rev-parse", "HEAD")
        journal["variants"][variant] = {"git_commit": identity["revision"],
            "native_sha256": identity["native_extension"]["sha256"],
            "runtime_sha256": identity["source_sha256"],
            "runtime_files": identity["source_files"],
            "parity_sha256": sha(report), "parity_command": command}
        checkpoint()
    assert journal["variants"]["fresh"]["native_sha256"] != journal["variants"]["reuse"]["native_sha256"]
    write(output / "plan.json", plan)
    run([sys.executable, str(ROOT / "scripts/benchmark_host_preflight.py"),
         "--output", str(output / "host-preflight.json")], ROOT, output / "host-preflight.log")
    for index, pair in enumerate(plan["pairs"], 1):
        for variant in pair["variant_order"]:
            clone = clones[variant]
            stem = f"{index:02d}-{variant}"
            report = output / (stem + ".json")
            command = [str(clone / ".venv/bin/python"), str(clone / "scripts/run_http_category_bench.py"),
                "--python", str(clone / ".venv/bin/python"), "--uvicorn-python", str(oracle),
                "--workloads", pair["workload"], "--servers", "uvicorn-rs-" + pair["loop"],
                "--duration", str(plan["duration_seconds"]), "--warmup", str(plan["warmup_seconds"]),
                "--concurrency", str(pair["concurrency"]), "--repetitions", "1",
                "--seed", str(plan["seed"]), "--output", str(report)]
            attempt = {"pair": index, **pair, "variant": variant, "command": command,
                       "started_at": datetime.now(timezone.utc).isoformat(), "returncode": None}
            journal["attempts"].append(attempt)
            checkpoint()
            with (output / (stem + ".log")).open("x") as log:
                result = subprocess.run(command, cwd=clone, stdout=log, stderr=subprocess.STDOUT)
            attempt.update(returncode=result.returncode,
                report_sha256=sha(report) if report.exists() else None,
                report_file=report.name, finished_at=datetime.now(timezone.utc).isoformat())
            checkpoint()
            print(json.dumps({"pair": index, "variant": variant, "returncode": result.returncode}), flush=True)
    journal["complete"] = len(journal["attempts"]) == plan["planned_pairs"] * 2
    checkpoint()


if __name__ == "__main__":
    main()
