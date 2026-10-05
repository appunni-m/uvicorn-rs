"""Measure experimental HTTP/3 paths against Hypercorn's optional aioquic support."""

from __future__ import annotations

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
from datetime import date
from pathlib import Path

import psutil

from benchmark_evidence import (BenchmarkEvidence, SampleMonitor, assert_clean_coverage_environment, median_valid, stop_client, owned_process, stop_owned, run_bounded_client, collect_bounded_client, finalize_server, wait_tls_ready)


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
MANIFEST = ROOT / "tools" / "http3-probe" / "Cargo.toml"
CLIENT = ROOT / "tools" / "http3-probe" / "target" / "release" / "bench"
WORKLOADS = {
    "protocol-scope": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {"mode": "fixed", "path": "/protocol", "expected_body": "http_version=3"},
    },
    "fixed": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {"mode": "fixed", "path": "/fixed"},
    },
    "large-response": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {"mode": "large", "path": "/large/1048576", "response_bytes": 1_048_576},
    },
    "many-response-chunks": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {"mode": "chunks", "path": "/chunks/256/4096", "response_bytes": 1_048_576},
    },
    "request-upload": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "upload", "path": "/upload/1048576", "upload_bytes": 1_048_576,
        },
        # Hypercorn 0.18.0's aioquic H3 path did not return a response after a
        # complete 64 KiB request body in the black-box probe. Keep the Rust
        # loop comparison, but don't report a cross-server performance result.
        "servers": ("uvicorn-rs-asyncio", "uvicorn-rs-uvloop"),
        "excluded_servers": {
            "hypercorn-asyncio": "H3 upload correctness probe timed out awaiting response headers after a complete 64 KiB body",
            "hypercorn-uvloop": "H3 upload correctness probe timed out awaiting response headers after a complete 64 KiB body",
        },
    },
    "slow-reader-backpressure": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "chunks", "path": "/chunks/256/4096", "response_bytes": 1_048_576,
            "read_rate_bytes_per_second": 4_194_304,
        },
        "concurrency": 2,
    },
}
SERVERS = {
    "uvicorn-rs-asyncio": {"kind": "rust", "loop": "asyncio"},
    "uvicorn-rs-uvloop": {"kind": "rust", "loop": "uvloop"},
    "hypercorn-asyncio": {"kind": "hypercorn", "loop": "asyncio"},
    "hypercorn-uvloop": {"kind": "hypercorn", "loop": "uvloop"},
}


def free_port() -> int:
    # Both listeners use the same numeric port but different transports. A
    # TCP-only check can hand out a port already owned by a UDP socket, which
    # makes QUIC server startup fail nondeterministically.
    for _ in range(128):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                try:
                    tcp.bind(("127.0.0.1", 0))
                    port = tcp.getsockname()[1]
                    udp.bind(("127.0.0.1", port))
                except OSError:
                    continue
                return port
    raise OSError("could not find a port available for both TCP and UDP")


def make_certificate(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "server.pem", directory / "server-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return cert, key


def server_command(
    server: dict, app: str, port: int, cert: Path, key: Path, hypercorn_config: Path
) -> list[str]:
    if server["kind"] == "rust":
        return [
            str(PYTHON), "-m", "uvicorn_rs", app, "--host", "127.0.0.1", "--port", str(port),
            "--loop", server["loop"], "--certfile", str(cert), "--keyfile", str(key),
        ]
    return [
        str(PYTHON), "-m", "hypercorn", app, "--bind", f"127.0.0.1:{port}",
        "--quic-bind", f"127.0.0.1:{port}", "--certfile", str(cert), "--keyfile", str(key),
        "--worker-class", server["loop"], "--log-level", "error",
        "--config", str(hypercorn_config),
    ]


def wait_ready(process: subprocess.Popen, port: int, log, cert: Path) -> None:
    wait_tls_ready(process, port, log, cert, seconds=20)


def process_tree_sample(
    root: psutil.Process, cpu_baselines: dict[int, psutil.Process]
) -> tuple[float, int]:
    cpu, rss = 0.0, 0
    try:
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        processes = [root]
    live_pids = {process.pid for process in processes}
    for process in processes:
        try:
            tracker = cpu_baselines.get(process.pid)
            if tracker is None:
                tracker = process
                cpu_baselines[process.pid] = tracker
                tracker.cpu_percent(interval=None)
            else:
                cpu += tracker.cpu_percent(interval=None)
            rss += process.memory_info().rss
        except psutil.Error:
            pass
    for pid in cpu_baselines.keys() - live_pids:
        del cpu_baselines[pid]
    return cpu, rss


def client_command(port: int, cert: Path, seconds: float, concurrency: int, case: dict) -> list[str]:
    return [
        str(CLIENT), f"127.0.0.1:{port}", str(cert), str(seconds), str(concurrency),
        str(min(4, concurrency)),
        case.get("mode", "fixed"), case.get("path", "/fixed"), str(case.get("response_bytes", 0)),
        str(case.get("upload_bytes", 0)), str(case.get("expected_status", 200)),
        case.get("expected_body", ""), str(case.get("read_rate_bytes_per_second", 0)),
    ]


def sample(
    server: dict,
    workload: str,
    seconds: float,
    warmup: float,
    concurrency: int,
    cert: Path,
    key: Path,
    hypercorn_config: Path,
    evidence: BenchmarkEvidence,
) -> dict:
    identity_before = evidence.before_sample()
    definition = WORKLOADS[workload]
    port = free_port()
    log = evidence.open_server_log()
    process = owned_process(
        server_command(server, definition["app"], port, cert, key, hypercorn_config), cwd=ROOT,
        stdout=log, stderr=log, text=True,
    )
    case = definition["client"]
    load = None
    try:
        wait_ready(process, port, log, cert)
        if warmup > 0:
            warm = run_bounded_client(
                client_command(port, cert, warmup, definition.get("concurrency", concurrency), case),
                warmup, process, cwd=ROOT,
            )
            if warm.returncode != 0:
                log.seek(0)
                server_log = log.read()
                raise RuntimeError(
                    f"HTTP/3 warm-up gate failed:\n{warm.stdout}\n{warm.stderr}"
                    f"\nserver output:\n{server_log[-4000:]}"
                )

        server_process = psutil.Process(process.pid)
        load = owned_process(
            client_command(port, cert, seconds, definition.get("concurrency", concurrency), case),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        monitor = SampleMonitor(server_process, psutil.Process(load.pid))
        stdout, stderr = collect_bounded_client(load, seconds, process, monitor)
        if load.returncode != 0:
            log.seek(0)
            server_log = log.read()
            raise RuntimeError(
                f"HTTP/3 client failed:\n{stdout}\n{stderr}\nserver output:\n{server_log[-4000:]}"
            )
        metrics = json.loads(stdout)
        if metrics["failures"]:
            raise RuntimeError(f"HTTP/3 correctness gate failed: {metrics}")
        metrics.update(monitor.finish(metrics))
        metrics.update(finalize_server(process, log))
        identity = evidence.after_sample(identity_before)
        metrics["timing_valid"] = metrics["timing_valid"] and identity["timing_valid"]
        metrics["timing_invalid_reasons"].extend(identity["timing_invalid_reasons"])
        metrics["measurement_identity"] = identity["measurement_identity"]
        return metrics
    finally:
        stop_client(load)
        stop_owned(process, graceful=True)
        log.close()


def source_digest() -> str:
    files = [
        "scripts/run_h3_category_bench.py", "tools/http3-probe/src/bin/bench.rs",
        "src/lib.rs", "python/uvicorn_rs/server.py", "examples/bench_matrix_asgi.py",
        "examples/protocol_asgi.py", "pyproject.toml", "uv.lock",
    ]
    digest = hashlib.sha256()
    for name in files:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update((ROOT / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", nargs="+", choices=sorted(WORKLOADS), default=list(WORKLOADS))
    parser.add_argument("--servers", nargs="+", choices=sorted(SERVERS), default=list(SERVERS))
    parser.add_argument("--duration", type=float, default=3)
    parser.add_argument("--warmup", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "http3-categories-2026-10-02.json")
    args = parser.parse_args()
    assert_clean_coverage_environment()
    selected_servers = {name: SERVERS[name] for name in args.servers}
    if not PYTHON.exists():
        raise SystemExit("install the benchmark dependency group before running HTTP/3 cases")
    subprocess.run(["cargo", "build", "--release", "--manifest-path", str(MANIFEST), "--bin", "bench"], check=True)
    if not CLIENT.exists():
        raise SystemExit(f"benchmark client was not built: {CLIENT}")

    evidence = BenchmarkEvidence(
        ROOT, PYTHON,
        ["scripts/run_h3_category_bench.py", "tools/http3-probe/src/bin/bench.rs",
         "tools/http3-probe/Cargo.toml", "tools/http3-probe/Cargo.lock", "examples/bench_matrix_asgi.py"],
        [CLIENT],
        artifacts_dir=args.output.with_suffix(".artifacts"),
    )
    checkpoint_path = args.output.with_suffix(".jsonl")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_path.open("x")
    evidence.checkpoint_provenance(checkpoint_path)
    rng = random.Random(args.seed)
    rows = []
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-h3-") as directory:
        cert, key = make_certificate(Path(directory))
        hypercorn_config = Path(directory) / "hypercorn.toml"
        hypercorn_config.write_text("keep_alive_max_requests = 100000000\ninclude_server_header = false\ninclude_date_header = false\n")
        for workload in args.workloads:
            for repetition in range(1, args.repetitions + 1):
                names = [
                    name for name in WORKLOADS[workload].get("servers", SERVERS)
                    if name in selected_servers
                ]
                rng.shuffle(names)
                for name in names:
                    evidence.label_sample(workload, name, repetition)
                    try:
                        metrics = sample(
                            selected_servers[name], workload, args.duration, args.warmup,
                            args.concurrency, cert, key, hypercorn_config, evidence,
                        )
                    except Exception as error:
                        raise RuntimeError(
                            f"HTTP/3 case failed: workload={workload}, server={name}, "
                            f"repetition={repetition}: {error}"
                        ) from error
                    row = {"workload": workload, "server": name, "repetition": repetition, **metrics}
                    rows.append(row)
                    print(json.dumps(row), flush=True)
                    checkpoint_file.write(json.dumps(row) + "\n")
                    checkpoint_file.flush()

    evidence_metadata = evidence.finish(rows)
    summaries = {}
    for workload in args.workloads:
        summaries[workload] = {}
        for name in WORKLOADS[workload].get("servers", SERVERS):
            if name not in selected_servers:
                continue
            subset = [row for row in rows if row["workload"] == workload and row["server"] == name]
            summaries[workload][name] = {
                metric: median_valid(subset, metric)
                for metric in (
                    "requests_per_second", "application_bytes_per_second", "p50_ms", "p95_ms", "p99_ms",
                    "server_cpu_percent_mean", "server_rss_peak_mib", "client_cpu_percent_mean",
                    "server_cpu_percent_elapsed", "server_cpu_microseconds_per_request",
                    "client_cpu_percent_elapsed", "client_cpu_microseconds_per_request", "client_rss_peak_mib",
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
            "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
            "hypercorn": subprocess.check_output([str(PYTHON), "-c", "import importlib.metadata as m; print(m.version('hypercorn'))"], text=True).strip(),
            "readiness": "trusted TLS HTTP/1.1 HEAD /fixed with Connection: close, outside measured H2/H3 workload",
            "hypercorn_config": {"keep_alive_max_requests": 100000000, "include_server_header": False, "include_date_header": False, "accesslog": None},
            "reference_logging_policy": {"level": "ERROR", "access_log": "disabled", "unexpected_errors": "public app exception tracebacks remain visible to the post-shutdown diagnostic gate"},
            "lifespan_policy": {"reference": "auto via Hypercorn's default support detection", "rust": "automatic startup/support detection and shutdown", "timing_boundary": "startup precedes readiness/warmup/load; the lifespan task and state remain present during load and graceful shutdown"},
            **evidence_metadata,
            "slow_reader_rate_bytes_per_second": 4_194_304,
            "remaining_header_difference": "Hypercorn advertises automatic Alt-Svc when QUIC bind is configured; Rust does not. No private baseline monkeypatch removes this behavior.",
            "h3_client": "Rust quinn/h3, up to four QUIC connections with multiplexed request streams distributed round-robin, full response-body equality; non-upload requests carry a 1-byte body for ASGI compatibility",
            "source_sha256": source_digest(), "workloads": args.workloads, "servers": selected_servers,
            "excluded_servers_by_workload": {
                name: WORKLOADS[name].get("excluded_servers", {})
                for name in args.workloads if WORKLOADS[name].get("excluded_servers")
            },
            "concurrency": args.concurrency, "duration_seconds": args.duration,
            "workload_concurrency": {
                workload: WORKLOADS[workload].get("concurrency", args.concurrency)
                for workload in args.workloads
            },
            "warmup_seconds": args.warmup, "repetitions": args.repetitions, "seed": args.seed,
            "correctness_gate": "HTTP/3 QUIC/TLS handshake, expected status, and every response byte validated for each measured request",
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
