"""Repeatable local feasibility comparison against Uvicorn."""

import argparse
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
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
CLIENT = ROOT / "scripts" / "bench_http.mjs"
CASES = {
    "uvicorn-asyncio-h11": [
        "-m", "uvicorn", "examples.bench_asgi:app", "--host", "127.0.0.1",
        "--loop", "asyncio", "--http", "h11", "--lifespan", "off",
        "--no-access-log", "--log-level", "critical",
    ],
    "uvicorn-uvloop-httptools": [
        "-m", "uvicorn", "examples.bench_asgi:app", "--host", "127.0.0.1",
        "--loop", "uvloop", "--http", "httptools", "--lifespan", "off",
        "--no-access-log", "--log-level", "critical",
    ],
    "uvicorn-rs-asyncio": [
        "-m", "uvicorn_rs", "examples.bench_asgi:app", "--host", "127.0.0.1",
        "--loop", "asyncio",
    ],
    "uvicorn-rs-uvloop": [
        "-m", "uvicorn_rs", "examples.bench_asgi:app", "--host", "127.0.0.1",
        "--loop", "uvloop",
    ],
}


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_client(port, seconds, concurrency, path, expected_body):
    result = subprocess.run(
        [
            "node",
            str(CLIENT),
            "127.0.0.1",
            str(port),
            str(seconds),
            str(concurrency),
            path,
            expected_body,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"load client failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def _wait_ready(process, port, log):
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
    raise RuntimeError("server did not open its listener within 15 seconds")


def _sample_load(server, port, duration, concurrency, path, expected_body):
    server_process = psutil.Process(server.pid)
    server_process.cpu_percent(interval=None)
    client = subprocess.Popen(
        [
            "node",
            str(CLIENT),
            "127.0.0.1",
            str(port),
            str(duration),
            str(concurrency),
            path,
            expected_body,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    client_process = psutil.Process(client.pid)
    client_process.cpu_percent(interval=None)
    server_cpu = []
    client_cpu = []
    server_rss = []
    client_rss = []
    while client.poll() is None:
        time.sleep(0.25)
        try:
            server_cpu.append(server_process.cpu_percent(interval=None))
            server_rss.append(server_process.memory_info().rss)
        except psutil.Error:
            pass
        try:
            client_cpu.append(client_process.cpu_percent(interval=None))
            client_rss.append(client_process.memory_info().rss)
        except psutil.Error:
            pass
    stdout, stderr = client.communicate()
    if client.returncode != 0:
        raise RuntimeError(f"load client failed ({client.returncode}):\n{stdout}\n{stderr}")
    metrics = json.loads(stdout)
    if metrics["failures"] != 0:
        raise RuntimeError(f"correctness gate failed: {metrics}")
    metrics.update(
        {
            "server_cpu_percent_mean": statistics.mean(server_cpu) if server_cpu else None,
            "server_cpu_percent_max": max(server_cpu, default=None),
            "server_rss_peak_mib": max(server_rss, default=0) / (1024 * 1024),
            "client_cpu_percent_mean": statistics.mean(client_cpu) if client_cpu else None,
            "client_cpu_percent_max": max(client_cpu, default=None),
            "client_rss_peak_mib": max(client_rss, default=0) / (1024 * 1024),
        }
    )
    return metrics


def _stop(server, log):
    if server.poll() is None:
        server.send_signal(signal.SIGINT)
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)
    log.seek(0)
    return log.read()


def _versions():
    code = (
        "import json, platform, sys, uvicorn, uvloop, httptools; "
        "print(json.dumps({'python': sys.version.split()[0], "
        "'implementation': platform.python_implementation(), 'uvicorn': uvicorn.__version__, "
        "'uvloop': uvloop.__version__, 'httptools': httptools.__version__}))"
    )
    output = subprocess.check_output([str(PYTHON), "-c", code], text=True)
    return json.loads(output)


def _source_digest(workload):
    app = (
        "examples/bench_streaming_asgi.py"
        if workload == "streaming"
        else "examples/bench_asgi.py"
    )
    paths = (
        "Cargo.toml",
        "Cargo.lock",
        "src/lib.rs",
        "python/uvicorn_rs/_bridge.py",
        "python/uvicorn_rs/server.py",
        "python/uvicorn_rs/cli.py",
        "scripts/run_feasibility_bench.py",
        "scripts/bench_http.mjs",
        app,
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / path).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=7)
    parser.add_argument("--warmup", type=float, default=2)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--workload", choices=("fixed", "streaming"), default="fixed")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks" / "results" / "feasibility-2026-10-02.json",
    )
    args = parser.parse_args()
    if not PYTHON.exists():
        raise SystemExit("create .venv and install this project plus the benchmark dependency group first")

    rng = random.Random(args.seed)
    app = (
        "examples.bench_streaming_asgi:app"
        if args.workload == "streaming"
        else "examples.bench_asgi:app"
    )
    path = "/stream" if args.workload == "streaming" else "/"
    expected_body = "Hello World!"
    rows = []
    for repetition in range(1, args.repetitions + 1):
        names = list(CASES)
        rng.shuffle(names)
        for name in names:
            port = _port()
            log = tempfile.TemporaryFile(mode="w+t")
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            server_args = list(CASES[name])
            server_args[server_args.index("examples.bench_asgi:app")] = app
            command = [str(PYTHON), *server_args, "--port", str(port)]
            server = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                text=True,
            )
            try:
                _wait_ready(server, port, log)
                warmup = _run_client(
                    port, args.warmup, args.concurrency, path, expected_body
                )
                if warmup["failures"] != 0:
                    raise RuntimeError(f"warm-up correctness gate failed: {warmup}")
                metrics = _sample_load(
                    server, port, args.duration, args.concurrency, path, expected_body
                )
                row = {"case": name, "repetition": repetition, **metrics}
                rows.append(row)
                print(json.dumps(row), flush=True)
            finally:
                output = _stop(server, log)
                log.close()
                if server.returncode not in (0, -signal.SIGINT, 128 + signal.SIGINT):
                    raise RuntimeError(f"{name} exited {server.returncode}:\n{output}")

    summaries = {}
    for name in CASES:
        case_rows = [row for row in rows if row["case"] == name]
        summaries[name] = {
            metric: statistics.median(row[metric] for row in case_rows)
            for metric in (
                "requests_per_second",
                "p50_ms",
                "p95_ms",
                "p99_ms",
                "server_cpu_percent_mean",
                "server_rss_peak_mib",
                "client_cpu_percent_mean",
            )
        }

    try:
        cpu_model = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        cpu_model = platform.processor()
    report = {
        "metadata": {
            "date": "2026-10-02",
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": psutil.cpu_count(logical=True),
            "cpu_model": cpu_model,
            "python_environment": _versions(),
            "source_sha256": _source_digest(args.workload),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
            "workload": {
                "fixed": "same examples.bench_asgi:app, persistent HTTP/1.1, one fixed 12-byte response",
                "streaming": "same examples.bench_streaming_asgi:app, persistent HTTP/1.1, two streamed body chunks totaling 12 bytes",
            }[args.workload],
            "load_client": "scripts/bench_http.mjs; one outstanding request per connection",
            "correctness_gate": f"every measured response must be HTTP 200 with body {expected_body}",
            "duration_seconds": args.duration,
            "warmup_seconds": args.warmup,
            "concurrency": args.concurrency,
            "repetitions": args.repetitions,
            "seed": args.seed,
        },
        "summaries_median": summaries,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
