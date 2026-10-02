"""Measure cold start, idle shutdown, and cancellation during graceful shutdown."""

from __future__ import annotations

import argparse
import hashlib
import http.client
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
SERVERS = {
    "uvicorn-rs-asyncio": {"kind": "rust", "loop": "asyncio"},
    "uvicorn-rs-uvloop": {"kind": "rust", "loop": "uvloop"},
    "uvicorn-asyncio-h11": {"kind": "uvicorn", "loop": "asyncio", "http": "h11"},
    "uvicorn-uvloop-httptools": {"kind": "uvicorn", "loop": "uvloop", "http": "httptools"},
}


def source_digest() -> str:
    paths = (
        "scripts/run_lifecycle_bench.py",
        "src/lib.rs",
        "python/uvicorn_rs/cli.py",
        "python/uvicorn_rs/server.py",
        "examples/lifespan_asgi.py",
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


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def command(server: dict, app: str, port: int) -> list[str]:
    if server["kind"] == "rust":
        return [
            str(PYTHON), "-m", "uvicorn_rs", app, "--host", "127.0.0.1", "--port", str(port),
            "--loop", server["loop"], "--graceful-timeout", "2",
        ]
    return [
        str(PYTHON), "-m", "uvicorn", app, "--host", "127.0.0.1", "--port", str(port),
        "--loop", server["loop"], "--http", server["http"], "--interface", "asgi3",
        "--lifespan", "on", "--timeout-graceful-shutdown", "2", "--no-access-log",
        "--log-level", "critical",
    ]


def request(port: int, path: str, timeout: float = 2.0) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def wait_response(process: subprocess.Popen, port: int, path: str, expected: bytes) -> float:
    deadline = time.monotonic() + 15
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early with status {process.returncode}")
        try:
            status, body = request(port, path)
            if status != 200 or body != expected:
                raise AssertionError(f"expected 200 {expected!r}, got {status} {body!r}")
            return time.monotonic()
        except OSError as error:
            last_error = error
            time.sleep(0.01)
    raise TimeoutError(f"server did not serve {path}: {last_error}")


def start(server: dict, app: str, log):
    port = free_port()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command(server, app, port), cwd=ROOT, env=env, stdout=log, stderr=log, text=True,
    )
    return port, process


def stop_idle(process: subprocess.Popen, log) -> float:
    started = time.monotonic()
    process.send_signal(signal.SIGTERM)
    process.wait(timeout=5)
    elapsed = time.monotonic() - started
    log.seek(0)
    output = log.read()
    # Uvicorn completes graceful shutdown, then re-raises the captured signal
    # after restoring Python's original handler. That produces -SIGTERM even
    # though shutdown and lifespan completed correctly.
    if process.returncode not in (0, -signal.SIGTERM):
        raise RuntimeError(f"idle shutdown exited {process.returncode}:\n{output}")
    if "LIFESPAN_SHUTDOWN_COMPLETE" not in output:
        raise AssertionError(f"idle shutdown did not complete ASGI lifespan:\n{output}")
    return elapsed


def measure_start_and_idle_shutdown(server: dict) -> tuple[float, float, float]:
    with tempfile.TemporaryFile(mode="w+t") as log:
        started = time.monotonic()
        port, process = start(server, "examples.lifespan_asgi:app", log)
        startup_observed_at = wait_response(process, port, "/state", b"startup-token:0")
        startup_ms = (startup_observed_at - started) * 1000
        try:
            rss = psutil.Process(process.pid).memory_info().rss / (1024 * 1024)
        except psutil.Error:
            rss = 0.0
        shutdown_ms = stop_idle(process, log) * 1000
        return startup_ms, shutdown_ms, rss


def measure_active_shutdown(server: dict) -> tuple[float, bool]:
    with tempfile.TemporaryFile(mode="w+t") as log:
        port, process = start(server, "examples.lifespan_asgi:app", log)
        wait_response(process, port, "/state", b"startup-token:0")
        pending = socket.create_connection(("127.0.0.1", port), timeout=2)
        pending.sendall(b"GET /hold HTTP/1.1\r\nHost: localhost\r\n\r\n")
        time.sleep(0.05)
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=5)
        elapsed = time.monotonic() - started
        pending.close()
        log.seek(0)
        output = log.read()
        # See stop_idle: Uvicorn intentionally re-raises SIGTERM after cleanup.
        if process.returncode not in (0, -signal.SIGTERM):
            raise RuntimeError(f"active shutdown exited {process.returncode}:\n{output}")
        cancelled = "APP_CANCELLED_BY_SHUTDOWN" in output
        if "LIFESPAN_SHUTDOWN_COMPLETE" not in output:
            raise AssertionError(f"active shutdown omitted ASGI lifespan completion:\n{output}")
        return elapsed, cancelled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "lifecycle-categories-2026-10-02.json")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    rows = []
    for repetition in range(1, args.repetitions + 1):
        names = list(SERVERS)
        rng.shuffle(names)
        for name in names:
            startup_ms, idle_ms, rss_mib = measure_start_and_idle_shutdown(SERVERS[name])
            active_ms, cancelled = measure_active_shutdown(SERVERS[name])
            row = {
                "server": name, "repetition": repetition,
                "cold_start_to_first_lifespan_request_ms": startup_ms,
                "idle_sigterm_to_process_exit_ms": idle_ms,
                "active_sigterm_to_process_exit_ms": active_ms,
                "active_asgi_task_cancelled": cancelled,
                "sampled_server_rss_mib": rss_mib,
            }
            if not cancelled:
                raise AssertionError(f"active request was not cancelled: {row}")
            rows.append(row)
            print(json.dumps(row), flush=True)

    summary = {}
    for name in SERVERS:
        subset = [row for row in rows if row["server"] == name]
        summary[name] = {
            key: statistics.median(row[key] for row in subset)
            for key in (
                "cold_start_to_first_lifespan_request_ms", "idle_sigterm_to_process_exit_ms",
                "active_sigterm_to_process_exit_ms", "sampled_server_rss_mib",
            )
        }
    try:
        cpu_model = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        cpu_model = platform.processor()
    report = {
        "metadata": {
            "date": date.today().isoformat(), "platform": platform.platform(),
            "machine": platform.machine(), "logical_cpus": psutil.cpu_count(logical=True),
            "cpu_model": cpu_model, "python": platform.python_version(),
            "uvicorn": subprocess.check_output([str(PYTHON), "-c", "import importlib.metadata as m; print(m.version('uvicorn'))"], text=True).strip(),
            "uvloop": subprocess.check_output([str(PYTHON), "-c", "import importlib.metadata as m; print(m.version('uvloop'))"], text=True).strip(),
            "source_sha256": source_digest(),
            "servers": SERVERS, "repetitions": args.repetitions, "seed": args.seed,
            "correctness_gate": "lifespan state response, lifespan shutdown complete, and held ASGI request cancellation validated",
            "definitions": {
                "cold_start_to_first_lifespan_request_ms": "process spawn through a valid response using state set by lifespan.startup",
                "idle_sigterm_to_process_exit_ms": "SIGTERM to process exit after one completed request",
                "active_sigterm_to_process_exit_ms": "SIGTERM to process exit while an ASGI request is blocked; cancellation marker required",
            },
        },
        "summaries_median": summary,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
