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

from benchmark_evidence import (
    FASTAPI_BENCHMARK_DISTRIBUTIONS,
    BenchmarkEvidence,
    SampleMonitor,
    assert_clean_coverage_environment,
    host_cpu_model,
    median_valid,
    stop_client,
    owned_process,
    stop_owned,
    run_bounded_client,
    collect_bounded_client,
    finalize_server,
    workspace_rust_source_paths,
)
from uvicorn_oracle import inspect_uvicorn_oracle, python_version


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
CLIENT = ROOT / "target" / "release" / "websocket"
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


def server_command(server: dict, port: int, python: Path, uvicorn_python: Path) -> list[str]:
    server_python = python if server["kind"] == "rust" else uvicorn_python
    if server["kind"] == "rust":
        return [
            str(server_python), "-m", "uvicorn_rs", "examples.bench_fastapi:app", "--host", "127.0.0.1",
            "--port", str(port), "--loop", server["loop"], "--interface", "asgi3",
            "--lifespan", "auto", "--no-access-log", "--log-level", "error",
            "--no-server-header", "--date-header",
        ]
    return [
        str(server_python), "-m", "uvicorn", "examples.bench_fastapi:app", "--host", "127.0.0.1",
        "--port", str(port), "--loop", server["loop"], "--http", "httptools",
        "--ws", "websockets", "--interface", "asgi3", "--lifespan", "auto", "--no-access-log",
        "--log-level", "error", "--no-use-colors", "--no-server-header", "--date-header",
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


def run_client(port: int, seconds: float, concurrency: int, workload: dict, server) -> dict:
    command = [
        str(CLIENT), f"127.0.0.1:{port}", str(seconds), str(concurrency),
        workload["mode"], workload["path"], str(workload["payload_bytes"]),
        str(workload.get("max_requests", 0)),
    ]
    result = run_bounded_client(
        command, seconds, server, cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"WebSocket client failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def source_digest() -> str:
    paths = set((
        "scripts/run_websocket_category_bench.py",
        "scripts/uvicorn_oracle.py",
        "tools/http3-probe/src/bin/websocket.rs",
        "scripts/benchmark_evidence.py",
        "src/lib.rs",
        "python/uvicorn_rs/server.py",
        "examples/bench_fastapi.py",
        "pyproject.toml",
        "uv.lock",
    ))
    paths.update(workspace_rust_source_paths(ROOT))
    digest = hashlib.sha256()
    for name in sorted(paths):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((ROOT / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def sample(
    server: dict,
    workload_name: str,
    seconds: float,
    warmup: float,
    concurrency: int,
    python: Path,
    uvicorn_python: Path,
    evidence: BenchmarkEvidence,
) -> dict:
    identity_before = evidence.before_sample()
    port = free_port()
    log = evidence.open_server_log()
    process = owned_process(
        server_command(server, port, python, uvicorn_python), cwd=ROOT, stdout=log, stderr=log, text=True,
    )
    client_process = None
    try:
        wait_ready(process, port, log)
        workload = WORKLOADS[workload_name]
        if warmup > 0 and workload["mode"] != "handshake":
            result = run_client(port, warmup, concurrency, workload, process)
            if result["failures"]:
                raise RuntimeError(f"WebSocket warm-up correctness gate failed: {result}")
        server_process = psutil.Process(process.pid)
        client_process = owned_process(
            [
                str(CLIENT), f"127.0.0.1:{port}", str(seconds), str(concurrency),
                workload["mode"], workload["path"], str(workload["payload_bytes"]),
                str(workload.get("max_requests", 0)),
            ],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        monitor = SampleMonitor(server_process, psutil.Process(client_process.pid))
        stdout, stderr = collect_bounded_client(client_process, seconds, process, monitor, interval=0.025 if workload["mode"] == "handshake" else 0.25)
        if client_process.returncode != 0:
            raise RuntimeError(f"WebSocket client failed:\n{stdout}\n{stderr}")
        metrics = json.loads(stdout)
        if metrics["failures"]:
            raise RuntimeError(f"WebSocket correctness gate failed: {metrics}")
        metrics.update(monitor.finish(metrics))
        metrics.update(finalize_server(process, log))
        identity = evidence.after_sample(identity_before)
        metrics["timing_valid"] = metrics["timing_valid"] and identity["timing_valid"]
        metrics["timing_invalid_reasons"].extend(identity["timing_invalid_reasons"])
        metrics["measurement_identity"] = identity["measurement_identity"]
        return metrics
    finally:
        stop_client(client_process)
        stop_owned(process, graceful=True)
        log.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", nargs="+", choices=sorted(WORKLOADS), default=list(WORKLOADS))
    parser.add_argument("--servers", nargs="+", choices=sorted(SERVERS), default=list(SERVERS))
    parser.add_argument("--duration", type=float, default=3)
    parser.add_argument("--warmup", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--python", type=Path, default=PYTHON,
                        help="candidate Python interpreter used by uvicorn-rs")
    parser.add_argument("--uvicorn-python", type=Path,
                        default=ROOT / "target" / "uvicorn-oracle" / "bin" / "python",
                        help="isolated Python interpreter containing stock Uvicorn 0.54.0")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "websocket-categories-2026-10-02.json")
    args = parser.parse_args()
    assert_clean_coverage_environment()
    python = args.python.absolute()
    if not python.is_file():
        raise SystemExit(f"candidate Python interpreter does not exist: {python}")
    uvicorn_python = args.uvicorn_python.absolute()
    selected_servers = {name: SERVERS[name] for name in args.servers}
    uvicorn_identity = None
    if any(server["kind"] == "uvicorn" for server in selected_servers.values()):
        required_packages = {"websockets"}
        if any(
            server["kind"] == "uvicorn" and server["loop"] == "uvloop"
            for server in selected_servers.values()
        ):
            required_packages.add("uvloop")
        uvicorn_identity = inspect_uvicorn_oracle(
            uvicorn_python,
            expected_python_version=python_version(python),
            required_packages=tuple(sorted(required_packages)),
        )
    if not CLIENT.exists():
        raise SystemExit(f"prebuild the WebSocket benchmark client before identity capture: {CLIENT}")
    evidence = BenchmarkEvidence(
        ROOT, python,
        ["scripts/run_websocket_category_bench.py", "tools/http3-probe/src/bin/websocket.rs",
         "tools/http3-probe/Cargo.toml", "tools/http3-probe/Cargo.lock", "examples/bench_fastapi.py"],
        [CLIENT],
        artifacts_dir=args.output.with_suffix(".artifacts"),
        extra_dependencies=FASTAPI_BENCHMARK_DISTRIBUTIONS,
    )
    checkpoint_path = args.output.with_suffix(".jsonl")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_path.open("x")
    evidence.checkpoint_provenance(checkpoint_path)
    rng = random.Random(args.seed)
    rows = []
    for workload in args.workloads:
        for repetition in range(1, args.repetitions + 1):
            names = list(selected_servers)
            rng.shuffle(names)
            for name in names:
                evidence.label_sample(workload, name, repetition)
                metrics = sample(
                    SERVERS[name], workload, args.duration, args.warmup,
                    WORKLOADS[workload].get("concurrency", args.concurrency),
                    python, uvicorn_python, evidence,
                )
                row = {"workload": workload, "server": name, "repetition": repetition, **metrics}
                rows.append(row)
                print(json.dumps(row), flush=True)
                checkpoint_file.write(json.dumps(row) + "\n")
                checkpoint_file.flush()

    evidence_metadata = evidence.finish(rows)
    summaries = {}
    for workload in args.workloads:
        summaries[workload] = {}
        for name in selected_servers:
            subset = [row for row in rows if row["workload"] == workload and row["server"] == name]
            summaries[workload][name] = {
                metric: median_valid(subset, metric)
                for metric in (
                    "messages_per_second", "payload_bytes_per_second", "p50_ms", "p95_ms", "p99_ms",
                    "server_cpu_percent_mean", "server_rss_peak_mib", "client_cpu_percent_mean",
                    "server_cpu_percent_elapsed", "server_cpu_microseconds_per_request",
                    "client_cpu_percent_elapsed", "client_cpu_microseconds_per_request", "client_rss_peak_mib",
                )
            }
    cpu_model = host_cpu_model()
    report = {
        "metadata": {
            "date": date.today().isoformat(), "platform": platform.platform(), "machine": platform.machine(),
            "logical_cpus": psutil.cpu_count(logical=True), "cpu_model": cpu_model,
            "python": platform.python_version(),
            "uvicorn_oracle": uvicorn_identity,
            "rustc": evidence.rustc_version,
            "source_sha256": source_digest(),
            **evidence_metadata,
            "response_header_policy": {"date": "enabled on both servers", "server": "disabled on both servers"},
            "reference_logging_policy": {"level": "ERROR on both servers", "colors": False, "access_log": "disabled on both servers", "unexpected_errors": "public app exception tracebacks remain visible to the post-shutdown diagnostic gate"},
            "lifespan_policy": {"reference": "auto via Uvicorn's public --lifespan auto", "rust": "automatic startup/support detection and shutdown", "timing_boundary": "startup precedes readiness/warmup/load; the lifespan task and state remain present during load and graceful shutdown"},
            "servers": selected_servers, "workloads": args.workloads, "concurrency": args.concurrency,
            "workload_concurrency": {
                workload: WORKLOADS[workload].get("concurrency", args.concurrency)
                for workload in args.workloads
            },
            "duration_seconds": args.duration, "warmup_seconds": args.warmup,
            "repetitions": args.repetitions, "seed": args.seed,
            "client": "Rust tokio-tungstenite; persistent WebSocket connections for echo cases",
            "cpu_per_request_unit": "one completed handshake or echoed message (client requests count)",
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
    checkpoint_file.close()
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
