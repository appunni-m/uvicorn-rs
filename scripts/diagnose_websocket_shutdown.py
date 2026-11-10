#!/usr/bin/env python3
"""Reproduce and capture a Linux ARM64 Uvicorn-RS WebSocket shutdown crash."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import psutil

from benchmark_evidence import assert_clean_coverage_environment
from run_websocket_category_bench import (
    PYTHON,
    ROOT,
    WORKLOADS,
    free_port,
    run_client,
    server_command,
    wait_ready,
)


def wait_for_inferior(debugger: subprocess.Popen, timeout: float = 15.0) -> int:
    """Find the Python server process launched by GDB."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if debugger.poll() is not None:
            raise RuntimeError("GDB exited before the server became ready")
        try:
            children = psutil.Process(debugger.pid).children(recursive=True)
        except psutil.Error:
            children = []
        for child in children:
            try:
                command = child.cmdline()
            except psutil.Error:
                continue
            if "uvicorn_rs" in command and "examples.bench_fastapi:app" in command:
                return child.pid
        time.sleep(0.05)
    raise TimeoutError("could not identify GDB's Python server process")


def terminate_debug_session(debugger: subprocess.Popen) -> None:
    if debugger.poll() is not None:
        return
    try:
        os.killpg(debugger.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        debugger.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(debugger.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        debugger.wait(timeout=3)


def reproduce(args: argparse.Namespace, repetition: int) -> dict:
    port = free_port()
    output_dir = args.output_dir / f"repeat-{repetition}"
    output_dir.mkdir(parents=True, exist_ok=False)
    log_path = output_dir / "gdb.log"
    command = server_command(
        {"kind": "rust", "loop": "asyncio"},
        port,
        args.python,
        args.python,
    )
    debugger_command = [
        shutil.which("gdb") or "gdb",
        "--quiet",
        "--batch",
        "-ex",
        "set pagination off",
        "-ex",
        "set confirm off",
        "-ex",
        "set debuginfod enabled off",
        "-ex",
        "handle SIGINT nostop noprint pass",
        "-ex",
        "run",
        "-ex",
        "thread apply all bt 40",
        "--args",
        *command,
    ]

    with log_path.open("w+", encoding="utf-8") as log:
        debugger = subprocess.Popen(
            debugger_command,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        try:
            wait_ready(debugger, port, log)
            server_pid = wait_for_inferior(debugger)
            workload = WORKLOADS["binary-64k-echo"]
            warmup = run_client(port, args.warmup, args.concurrency, workload, debugger)
            sample = run_client(port, args.duration, args.concurrency, workload, debugger)
            try:
                os.kill(server_pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                debugger.wait(timeout=20)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError("GDB did not finish after graceful server shutdown") from error
        except BaseException:
            terminate_debug_session(debugger)
            raise
        finally:
            terminate_debug_session(debugger)
        log.flush()
        log.seek(0)
        debug_log = log.read()

    crashed = "SIGSEGV" in debug_log or "Segmentation fault" in debug_log
    report = {
        "repetition": repetition,
        "workload": "binary-64k-echo",
        "event_loop": "asyncio",
        "payload_bytes": workload["payload_bytes"],
        "concurrency": args.concurrency,
        "warmup": {"requests": warmup["requests"], "failures": warmup["failures"]},
        "sample": {
            "requests": sample["requests"],
            "failures": sample["failures"],
            "first_failure": sample["first_failure"],
        },
        "shutdown": "sigsegv" if crashed else "no_sigsegv_observed",
        "gdb_log": str(log_path),
    }
    print(json.dumps(report, sort_keys=True), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=PYTHON)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--warmup", type=float, default=1.0)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "target" / "websocket-shutdown-diagnostic"
    )
    args = parser.parse_args()
    assert_clean_coverage_environment()
    args.python = args.python.absolute()
    args.output_dir = args.output_dir.absolute()
    if not args.python.is_file():
        raise SystemExit(f"candidate Python interpreter does not exist: {args.python}")
    if not shutil.which("gdb"):
        raise SystemExit("gdb is required to capture the native crash backtrace")
    if args.repetitions < 1 or args.duration <= 0 or args.warmup <= 0 or args.concurrency < 1:
        raise SystemExit("repetitions, duration, warmup, and concurrency are out of range")
    args.output_dir.mkdir(parents=True, exist_ok=False)

    for repetition in range(1, args.repetitions + 1):
        report = reproduce(args, repetition)
        if report["shutdown"] == "sigsegv":
            return 0
    print(json.dumps({"status": "no_sigsegv_observed", "repetitions": args.repetitions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
