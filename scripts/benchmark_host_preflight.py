#!/usr/bin/env python3
"""Record ambient CPU activity before starting a local ASGI benchmark."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from benchmark_evidence import SampleMonitor


ROOT = Path(__file__).resolve().parents[1]
POLICY = {
    **SampleMonitor.contention_policy,
    "excluded": "preflight process, its ancestors, and its descendants",
}


def repository_revision() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def excluded_process_ids() -> set[int]:
    process = psutil.Process()
    excluded = {process.pid}
    try:
        excluded.update(parent.pid for parent in process.parents())
        excluded.update(child.pid for child in process.children(recursive=True))
    except psutil.Error:
        pass
    return excluded


def process_snapshot(excluded: set[int]) -> dict[tuple[int, float], dict]:
    snapshot = {}
    for process in psutil.process_iter(
        ["pid", "name", "create_time", "cpu_times"], ad_value=None
    ):
        info = process.info
        pid = info.get("pid")
        created = info.get("create_time")
        cpu_times = info.get("cpu_times")
        if pid is None or pid in excluded or created is None or cpu_times is None:
            continue
        key = (int(pid), float(created))
        snapshot[key] = {
            "pid": int(pid),
            "name": info.get("name") or "unknown",
            "cpu_seconds": float(cpu_times.user + cpu_times.system),
        }
    return snapshot


def ancestor_and_child_ids() -> list[int]:
    return sorted(excluded_process_ids())


def sample_host(intervals: int, interval_seconds: float) -> dict:
    excluded = set(ancestor_and_child_ids())
    previous = process_snapshot(excluded)
    previous_at = time.monotonic()
    streaks: dict[tuple[int, float], int] = {}
    samples = []
    reject_reasons: set[str] = set()

    for _ in range(intervals):
        time.sleep(interval_seconds)
        sampled_at = time.monotonic()
        elapsed = sampled_at - previous_at
        current = process_snapshot(excluded)
        activity = []
        total_cpu_percent = 0.0

        for key, process in current.items():
            prior = previous.get(key)
            if prior is None or elapsed <= 0:
                streaks[key] = 0
                continue
            cpu_percent = max(
                0.0,
                process["cpu_seconds"] - prior["cpu_seconds"],
            ) / elapsed * 100.0
            total_cpu_percent += cpu_percent
            streaks[key] = streaks.get(key, 0) + 1 if cpu_percent > 25.0 else 0
            if cpu_percent >= 1.0:
                activity.append(
                    {
                        "pid": process["pid"],
                        "name": process["name"],
                        "cpu_percent": round(cpu_percent, 1),
                    }
                )
            if streaks[key] >= 2:
                reject_reasons.add("process_over_25_percent_for_two_consecutive_intervals")
            if cpu_percent >= 200.0:
                reject_reasons.add("single_interval_process_cpu_over_200_percent")

        live_keys = set(current)
        streaks = {key: value for key, value in streaks.items() if key in live_keys}
        activity.sort(key=lambda item: item["cpu_percent"], reverse=True)
        if total_cpu_percent > 100.0:
            reject_reasons.add("aggregate_unrelated_cpu_over_100_percent")
        samples.append(
            {
                "interval_seconds": round(elapsed, 3),
                "unrelated_total_cpu_percent": round(total_cpu_percent, 1),
                "over_25_percent": {
                    item["name"]: item["cpu_percent"]
                    for item in activity
                    if item["cpu_percent"] > 25.0
                },
                "top_processes": activity[:8],
                "reject": bool(reject_reasons),
            }
        )
        previous = current
        previous_at = sampled_at

    return {
        "samples": samples,
        "reject_reasons": sorted(reject_reasons),
        "decision": "reject" if reject_reasons else "accept",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sample unrelated host CPU activity without starting a benchmark "
            "or stopping other processes."
        )
    )
    parser.add_argument("--output", type=Path, required=True, help="new JSON receipt path")
    parser.add_argument("--intervals", type=int, default=8, help="sample count (default: 8)")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0.25,
        help="seconds between samples (default: 0.25)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.intervals < 3:
        raise SystemExit("--intervals must be at least 3")
    if args.interval_seconds < 0.05:
        raise SystemExit("--interval-seconds must be at least 0.05")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing preflight receipt: {output}")

    result = sample_host(args.intervals, args.interval_seconds)
    receipt = {
        "schema_version": 1,
        "measurement": "host-preflight-only",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": repository_revision(),
        "host": {
            "os": platform.system(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "logical_cpu_count": psutil.cpu_count(logical=True),
            "physical_cpu_count": psutil.cpu_count(logical=False),
            "python": platform.python_version(),
            "psutil": psutil.__version__,
        },
        "policy": POLICY,
        "intervals": result["samples"],
        "decision": result["decision"],
        "reject_reasons": result["reject_reasons"],
        "timing_benchmark_started": False,
        "process_data_scope": "process names and PIDs only; command-line arguments are not read",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(
        json.dumps(
            {
                "decision": receipt["decision"],
                "output": str(output),
                "reject_reasons": receipt["reject_reasons"],
                "timing_benchmark_started": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["decision"] == "accept" else 2


if __name__ == "__main__":
    raise SystemExit(main())
