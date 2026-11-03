#!/usr/bin/env python3
"""Retain bounded, single-case subprocess evidence for native startup teardown."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "python-api.concurrent-startup-failure-waiter"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("normal", "instrumented"), required=True)
    parser.add_argument("--attempts", type=int, default=500)
    parser.add_argument("--python-source", type=Path)
    parser.add_argument("--core-directory", type=Path)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 1000:
        parser.error("--attempts must be between 1 and 1000")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Resolving a venv interpreter symlink would select the base environment.
    python = args.python.absolute()
    fixture = ROOT / "tests/parity/inputs/python-api.json"
    manifest = ROOT / "tests/parity/manifest.json"
    probe = ROOT / "tests/parity/python_api_probe.py"
    case = next(row for row in json.loads(fixture.read_text())["cases"]
                if row["case_id"] == CASE_ID)
    contract = next(row for row in json.loads(manifest.read_text())["operations"]
                    if row["id"] == case["operation"])
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment.update({
        "PYTHONFAULTHANDLER": "1", "RUST_BACKTRACE": "full",
        "PYTHONNOUSERSITE": "1", "ASGI_PARITY_SERVER_ID": "uvicorn-rs",
        "ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN": "1",
        "ASGI_PARITY_COVERAGE_RUNTIME_MARKER_DIR": str(output / "runtime-probe"),
        "LLVM_PROFILE_FILE": str(output / "profiles/%p-%m.profraw"),
        "PYTHONPATH": os.pathsep.join(str(path) for path in (
            ROOT / "tests/parity/coverage_site", args.python_source,
        ) if path is not None),
    })
    (output / "profiles").mkdir()
    identity_code = (
        "import hashlib,json,platform,sys,uvicorn_rs,uvicorn_rs._native as n;"
        "from pathlib import Path;"
        "print(json.dumps({'python':sys.version,'platform':platform.platform(),"
        "'package':uvicorn_rs.__file__,'native':n.__file__,"
        "'native_sha256':hashlib.sha256(Path(n.__file__).read_bytes()).hexdigest()}))"
    )
    identity = subprocess.run([str(python), "-c", identity_code], env=environment,
                              capture_output=True, text=True, timeout=15, check=True)
    report = {
        "schema": "uvicorn-rs-startup-teardown-diagnostic@1",
        "scope": "diagnostic only; not parity, coverage or performance acceptance",
        "case_id": CASE_ID, "variant": args.variant,
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain",
                                                "--untracked-files=all"], cwd=ROOT)),
        "identity": json.loads(identity.stdout),
        "fixture_sha256": sha256(fixture), "manifest_sha256": sha256(manifest),
        "probe_sha256": sha256(probe), "requested_attempts": args.attempts,
        "profile_retention": "failed attempt only; no coverage acceptance",
        "attempts": [],
    }
    required = {**contract["required_observations"], **contract["target_requirements"]}
    result_path = output / "diagnostic.json"
    for attempt in range(1, args.attempts + 1):
        timed_out = False
        try:
            completed = subprocess.run(
                [str(python), str(probe), json.dumps(case["api"])], cwd=ROOT,
                env=environment, capture_output=True, timeout=12, check=False,
            )
            stdout, stderr, exit_code = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, exit_code = error.stdout or b"", error.stderr or b"", None
            timed_out = True
        stdout_path = output / f"attempt-{attempt:04d}.stdout"
        stderr_path = output / f"attempt-{attempt:04d}.stderr"
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        try:
            observed = json.loads(stdout)["server_startup_failure_waiter"]
        except (ValueError, KeyError, TypeError):
            observed = {}
        if not isinstance(observed, dict):
            observed = {}
        observed["exit_code"] = exit_code
        differences = {key: {"expected": expected, "actual": observed.get(key)}
                       for key, expected in required.items()
                       if type(observed.get(key)) is not type(expected)
                       or observed.get(key) != expected}
        failed = timed_out or bool(differences)
        report["attempts"].append({
            "attempt": attempt, "exit_code": exit_code, "timed_out": timed_out,
            "differences": differences, "stdout": stdout_path.name,
            "stderr": stderr_path.name, "stdout_sha256": sha256(stdout_path),
            "stderr_sha256": sha256(stderr_path),
        })
        report["status"] = "failure-observed" if failed else "not-reproduced"
        result_path.write_text(json.dumps(report, indent=2) + "\n")
        if failed or attempt % 50 == 0 or attempt == args.attempts:
            print(f"{args.variant}: attempt {attempt}/{args.attempts}, "
                  f"exit={exit_code}, status={report['status']}", flush=True)
        if failed:
            print(stderr.decode(errors="replace")[-12000:], flush=True)
            if args.core_directory is not None:
                for core in args.core_directory.glob("core.*"):
                    try:
                        trace = subprocess.run(
                            ["gdb", "--batch", "-ex", "set pagination off", "-ex",
                             "thread apply all bt 32", str(python), str(core)],
                            capture_output=True, timeout=45, check=False,
                        )
                        (output / f"{core.name}.backtrace").write_bytes(trace.stdout + trace.stderr)
                    finally:
                        # Keep stack frames, not a process-memory dump containing
                        # the runner environment, in the uploaded evidence.
                        core.unlink()
            return 1
        for profile in (output / "profiles").glob("*.profraw"):
            profile.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
