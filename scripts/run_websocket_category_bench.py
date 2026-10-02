"""Benchmark HTTP/1.1 WebSocket handshakes and echoed frames."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import random
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
MANIFEST = ROOT / "tools" / "http3-probe" / "Cargo.toml"
CLIENT = ROOT / "tools" / "http3-probe" / "target" / "release" / "websocket"
WORKLOADS = {
    "connection-handshake": {
        "mode": "handshake", "path": "/echo", "payload_bytes": 0,
        "max_requests": 500, "concurrency": 1,
    },
    "text-echo": {"mode": "text", "path": "/echo", "payload_bytes": 32},
    "binary-64k-echo": {"mode": "binary", "path": "/echo", "payload_bytes": 65_536},
}
SERVERS = {
    "uvicorn-asyncio-websockets": {"kind": "uvicorn", "loop": "asyncio"},
    "uvicorn-uvloop-websockets": {"kind": "uvicorn", "loop": "uvloop"},
    "uvicorn-rs-asyncio": {"kind": "rust", "loop": "asyncio"},
    "uvicorn-rs-uvloop": {"kind": "rust", "loop": "uvloop"},
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def server_command(server: dict, port: int) -> list[str]:
    if server["kind"] == "rust":
        return [
            str(PYTHON), "-m", "uvicorn_rs", "examples.bench_matrix_asgi:app", "--host", "127.0.0.1",
            "--port", str(port), "--loop", server["loop"],
        ]
    return [
        str(PYTHON), "-m", "uvicorn", "examples.bench_matrix_asgi:app", "--host", "127.0.0.1",
        "--port", str(port), "--loop", server["loop"], "--http", "httptools" if server["loop"] == "uvloop" else "h11",
        "--ws", "websockets", "--interface", "asgi3", "--lifespan", "off", "--no-access-log",
        "--log-level", "critical",
    ]


def wait_ready(process: subprocess.Popen, port: int, log) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log.seek(0)
            raise RuntimeError(f"server exited early ({process.returncode}):\n{log.read()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("server did not open its listener within 15 seconds")


def process_tree_sample(root: psutil.Process) -> tuple[float, int]:
    cpu, rss = 0.0, 0
    try:
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        processes = [root]
    for process in processes:
        try:
            cpu += process.cpu_percent(interval=None)
            rss += process.memory_info().rss
        except psutil.Error:
            pass
    return cpu, rss


def run_client(port: int, seconds: float, concurrency: int, workload: dict) -> dict:
    command = [
        str(CLIENT), f"127.0.0.1:{port}", str(seconds), str(concurrency),
        workload["mode"], workload["path"], str(workload["payload_bytes"]),
        str(workload.get("max_requests", 0)),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"WebSocket client failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def source_digest() -> str:
    paths = (
        "scripts/run_websocket_category_bench.py",
        "tools/http3-probe/src/bin/websocket.rs",
        "src/lib.rs",
        "python/uvicorn_rs/server.py",
        "examples/bench_matrix_asgi.py",
        "pyproject.toml",
        "uv.lock",
    )
    digest = hashlib.sha256()
    for name in paths:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((ROOT / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def sample(server: dict, workload_name: str, seconds: float, warmup: float, concurrency: int) -> dict:
    port = free_port()
    log = tempfile.TemporaryFile(mode="w+t")
    process = subprocess.Popen(
        server_command(server, port), cwd=ROOT, stdout=log, stderr=log, text=True,
    )
    try:
        wait_ready(process, port, log)
        workload = WORKLOADS[workload_name]
        if warmup > 0 and workload["mode"] != "handshake":
            result = run_client(port, warmup, concurrency, workload)
            if result["failures"]:
                raise RuntimeError(f"WebSocket warm-up correctness gate failed: {result}")
        server_process = psutil.Process(process.pid)
        process_tree_sample(server_process)
        client_process = subprocess.Popen(
            [
                str(CLIENT), f"127.0.0.1:{port}", str(seconds), str(concurrency),
                workload["mode"], workload["path"], str(workload["payload_bytes"]),
                str(workload.get("max_requests", 0)),
            ],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        client_ps = psutil.Process(client_process.pid)
        client_ps.cpu_percent(interval=None)
        server_cpu, server_rss, client_cpu, client_rss = [], [], [], []
        while client_process.poll() is None:
            time.sleep(0.025 if workload["mode"] == "handshake" else 0.25)
            try:
                cpu, rss = process_tree_sample(server_process)
                server_cpu.append(cpu)
                server_rss.append(rss)
            except psutil.Error:
                pass
            try:
                client_cpu.append(client_ps.cpu_percent(interval=None))
                client_rss.append(client_ps.memory_info().rss)
            except psutil.Error:
                pass
        stdout, stderr = client_process.communicate()
        if client_process.returncode != 0:
            raise RuntimeError(f"WebSocket client failed:\n{stdout}\n{stderr}")
        metrics = json.loads(stdout)
        if metrics["failures"]:
            raise RuntimeError(f"WebSocket correctness gate failed: {metrics}")
        metrics.update(
            {
                "server_cpu_percent_mean": statistics.mean(server_cpu) if server_cpu else None,
                "server_cpu_percent_max": max(server_cpu, default=None),
                "server_rss_peak_mib": max(server_rss, default=0) / (1024 * 1024),
                "client_cpu_percent_mean": statistics.mean(client_cpu) if client_cpu else None,
                "client_rss_peak_mib": max(client_rss, default=0) / (1024 * 1024),
            }
        )
        return metrics
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
        log.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", nargs="+", choices=sorted(WORKLOADS), default=list(WORKLOADS))
    parser.add_argument("--duration", type=float, default=3)
    parser.add_argument("--warmup", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "websocket-categories-2026-10-02.json")
    args = parser.parse_args()
    subprocess.run(["cargo", "build", "--release", "--manifest-path", str(MANIFEST), "--bin", "websocket"], check=True)
    if not CLIENT.exists():
        raise SystemExit(f"WebSocket benchmark client was not built: {CLIENT}")
    rng = random.Random(args.seed)
    rows = []
    for workload in args.workloads:
        for repetition in range(1, args.repetitions + 1):
            names = list(SERVERS)
            rng.shuffle(names)
            for name in names:
                metrics = sample(
                    SERVERS[name], workload, args.duration, args.warmup,
                    WORKLOADS[workload].get("concurrency", args.concurrency),
                )
                row = {"workload": workload, "server": name, "repetition": repetition, **metrics}
                rows.append(row)
                print(json.dumps(row), flush=True)

    summaries = {}
    for workload in args.workloads:
        summaries[workload] = {}
        for name in SERVERS:
            subset = [row for row in rows if row["workload"] == workload and row["server"] == name]
            summaries[workload][name] = {
                metric: (
                    statistics.median(value for value in values if value is not None)
                    if any(value is not None for value in values)
                    else None
                )
                for metric in (
                    "messages_per_second", "payload_bytes_per_second", "p50_ms", "p95_ms", "p99_ms",
                    "server_cpu_percent_mean", "server_rss_peak_mib", "client_cpu_percent_mean",
                )
                for values in ([row[metric] for row in subset],)
            }
    try:
        cpu_model = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        cpu_model = platform.processor()
    report = {
        "metadata": {
            "date": date.today().isoformat(), "platform": platform.platform(), "machine": platform.machine(),
            "logical_cpus": psutil.cpu_count(logical=True), "cpu_model": cpu_model,
            "python": platform.python_version(),
            "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
            "source_sha256": source_digest(),
            "servers": SERVERS, "workloads": args.workloads, "concurrency": args.concurrency,
            "workload_concurrency": {
                workload: WORKLOADS[workload].get("concurrency", args.concurrency)
                for workload in args.workloads
            },
            "duration_seconds": args.duration, "warmup_seconds": args.warmup,
            "repetitions": args.repetitions, "seed": args.seed,
            "client": "Rust tokio-tungstenite; persistent WebSocket connections for echo cases",
            "request_caps": {
                name: workload["max_requests"]
                for name, workload in WORKLOADS.items() if "max_requests" in workload
            },
            "correctness_gate": "subprotocol handshake plus complete text/binary payload equality on every measured echo",
        },
        "summaries_median": summaries,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
