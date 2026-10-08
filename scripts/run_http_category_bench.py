"""Measure HTTP/1.1 request, body, context, scope, and framework workloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import shlex
import shutil
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
    median_valid,
    stop_client,
    owned_process,
    stop_owned,
    run_bounded_client,
    collect_bounded_client,
    finalize_server,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = ROOT / ".venv" / "bin" / "python"
CLIENT = ROOT / "scripts" / "bench_http_matrix.mjs"
NATIVE_CLIENT_SOURCE = ROOT / "scripts" / "bench_http_client.c"
NATIVE_CLIENT: Path | None = None
_CLIENT_TEMP: tempfile.TemporaryDirectory | None = None


def _scope_headers() -> list[list[str]]:
    return [[f"x-bench-{index}", "value"] for index in range(32)]


WORKLOADS = {
    "fixed": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {"mode": "fixed", "path": "/fixed"},
    },
    "large-response": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "large",
            "path": "/large/1048576",
            "response_bytes": 1_048_576,
        },
    },
    "many-response-chunks": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "chunks",
            "path": "/chunks/256/4096",
            "response_bytes": 1_048_576,
        },
    },
    "small-response-chunks": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "chunks",
            "path": "/chunks/128/512",
            "response_bytes": 65_536,
        },
    },
    "request-upload": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "upload",
            "path": "/upload/1048576",
            "upload_bytes": 1_048_576,
            "upload_chunk_bytes": 65_536,
        },
    },
    "request-upload-small-chunks": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "upload",
            "path": "/upload/65536",
            "upload_bytes": 65_536,
            "upload_chunk_bytes": 1024,
        },
    },
    "slow-reader-backpressure": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "chunks",
            "path": "/chunks/256/4096",
            "response_bytes": 1_048_576,
            "read_rate_bytes_per_second": 4_194_304,
        },
        "concurrency": 8,
    },
    "scope-32-headers": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "scope",
            "path": "/scope",
            "expected_body": "scope-ok",
            "headers": _scope_headers(),
        },
    },
    "contextvars": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {"mode": "context", "path": "/context"},
    },
    "sync-callable-awaitable": {
        "app": "examples.bench_sync_asgi:app",
        "client": {"mode": "fixed", "path": "/fixed"},
    },
    "exception-to-500": {
        "app": "examples.bench_matrix_asgi:app",
        "client": {
            "mode": "exception",
            "path": "/exception",
            "expected_status": 500,
            "headers": [["connection", "close"]],
            "max_requests": 200,
        },
        "concurrency": 1,
        "duration_seconds": 1.0,
        "warmup_seconds": 0.0,
        "timing_rankable": False,
        "timing_exclusion_reason": "unequal_exception_diagnostic_policy",
    },
    "fastapi-validated-route": {
        "app": "examples.bench_fastapi:app",
        "client": {
            "mode": "fixed",
            "path": "/items/7?repeat=3",
            "expected_body": (
                '{"item_id":21,"name":"item-7","active":true,'
                '"labels":["python","asgi"]}'
            ),
        },
    },
    "fastapi-python-cpu": {
        "app": "examples.bench_fastapi:app",
        "client": {
            "mode": "fixed",
            "path": "/cpu/20000",
            "expected_body": '{"iterations":20000,"checksum":499563}',
        },
    },
}

SERVERS = {
    "uvicorn-asyncio-httptools": {
        "kind": "uvicorn",
        "loop": "asyncio",
        "http": "httptools",
    },
    "uvicorn-uvloop-httptools": {
        "kind": "uvicorn",
        "loop": "uvloop",
        "http": "httptools",
    },
    "uvicorn-rs-asyncio": {"kind": "rust", "loop": "asyncio"},
    "uvicorn-rs-uvloop": {"kind": "rust", "loop": "uvloop"},
}


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _command(server: dict, app: str, port: int, python: Path) -> list[str]:
    if server["kind"] == "rust":
        return [
            str(python),
            "-m",
            "uvicorn_rs",
            app,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--loop",
            server["loop"],
        ]
    return [
        str(python),
        "-m",
        "uvicorn",
        app,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--loop",
        server["loop"],
        "--http",
        server["http"],
        "--lifespan",
        "auto",
        "--interface",
        "asgi3",
        "--no-access-log",
        "--no-server-header",
        "--log-level",
        "error",
        "--no-use-colors",
    ]


def _build_native_client() -> Path | None:
    global NATIVE_CLIENT, _CLIENT_TEMP
    if NATIVE_CLIENT is not None:
        return NATIVE_CLIENT
    if shutil.which("curl-config") is None or shutil.which("cc") is None:
        return None
    flags = shlex.split(subprocess.check_output(["curl-config", "--cflags", "--libs"], text=True))
    _CLIENT_TEMP = tempfile.TemporaryDirectory(prefix="uvicorn-rs-httpbench-")
    binary = Path(_CLIENT_TEMP.name) / "httpbench"
    subprocess.run(
        ["cc", "-O3", "-std=c11", "-pthread", str(NATIVE_CLIENT_SOURCE), "-o", str(binary), *flags],
        check=True,
    )
    NATIVE_CLIENT = binary
    return NATIVE_CLIENT


def _client_command(port: int, seconds: float, concurrency: int, case: dict) -> list[str]:
    if case.get("read_delay_ms", 0) > 0 or case.get("read_rate_bytes_per_second", 0) > 0 or NATIVE_CLIENT is None:
        config = {
            "host": "127.0.0.1",
            "port": port,
            "seconds": seconds,
            "concurrency": concurrency,
            **case,
        }
        return ["node", str(CLIENT), json.dumps(config)]
    args = [
        str(NATIVE_CLIENT),
        "127.0.0.1",
        str(port),
        str(seconds),
        str(concurrency),
        case.get("mode", "fixed"),
        case.get("path", "/fixed"),
        str(case.get("response_bytes", 0)),
        str(case.get("upload_bytes", 0)),
        str(case.get("expected_status", 200)),
        case.get("expected_body", ""),
        str(case.get("upload_chunk_bytes", case.get("upload_bytes", 0))),
        str(case.get("max_requests", 0)),
    ]
    args.extend(f"{name}: {value}" for name, value in case.get("headers", []))
    return args


def _wait_ready(process: subprocess.Popen, port: int, log) -> None:
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


def _stop_server(process: subprocess.Popen) -> None:
    stop_owned(process, graceful=True)


def _runtime_diagnostics(log) -> dict[str, int] | None:
    log.flush()
    log.seek(0)
    prefix = "uvicorn-rs-runtime-diagnostics "
    for line in log:
        if line.startswith(prefix):
            return {
                key: int(value)
                for key, value in (part.split("=", 1) for part in line[len(prefix) :].split())
            }
    return None


def _client(port: int, seconds: float, concurrency: int, case: dict, server) -> dict:
    result = run_bounded_client(
        _client_command(port, seconds, concurrency, case),
        seconds, server, cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"HTTP client failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def _sample(
    server_name: str,
    server: dict,
    workload: str,
    seconds: float,
    warmup: float,
    concurrency: int,
    python: Path,
    require_runtime_diagnostics: bool = False,
    evidence: BenchmarkEvidence | None = None,
) -> dict:
    identity_before = evidence.before_sample() if evidence is not None else None
    definition = WORKLOADS[workload]
    port = _port()
    log = evidence.open_server_log() if evidence is not None else tempfile.NamedTemporaryFile(mode="w+t", suffix="-server.log", delete=False)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = owned_process(
        _command(server, definition["app"], port, python),
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=log,
        text=True,
    )
    client = None
    try:
        _wait_ready(process, port, log)
        case = definition["client"]
        if warmup > 0:
            result = _client(port, warmup, concurrency, case, process)
            if result["failures"]:
                raise RuntimeError(f"warm-up correctness gate failed: {result}")

        server_process = psutil.Process(process.pid)
        client = owned_process(
            _client_command(port, seconds, concurrency, case),
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        monitor = SampleMonitor(server_process, psutil.Process(client.pid))
        stdout, stderr = collect_bounded_client(client, seconds, process, monitor)
        if client.returncode != 0:
            raise RuntimeError(f"HTTP client failed ({client.returncode}):\n{stdout}\n{stderr}")
        metrics = json.loads(stdout)
        if metrics["failures"]:
            raise RuntimeError(f"correctness gate failed: {metrics}")
        metrics.update(monitor.finish(metrics))
        metrics.update(finalize_server(process, log, permit_app_error=workload == "exception-to-500"))
        if not definition.get("timing_rankable", True):
            metrics["timing_valid"] = False
            metrics["timing_invalid_reasons"].append(definition["timing_exclusion_reason"])
            metrics["diagnostic_policy"] = {
                "equal": False,
                "uvicorn": "public ERROR logging writes the full Python app exception traceback",
                "uvicorn_rs": "native app exception diagnostics write the exception line",
                "ranking": "disabled; raw correctness-passing operational sample only",
            }
        if evidence is not None:
            identity = evidence.after_sample(identity_before)
            metrics["timing_valid"] = metrics["timing_valid"] and identity["timing_valid"]
            metrics["timing_invalid_reasons"].extend(identity["timing_invalid_reasons"])
            metrics["measurement_identity"] = identity["measurement_identity"]
        if server_name.startswith("uvicorn-rs-"):
            diagnostics = _runtime_diagnostics(log)
            if diagnostics is not None:
                metrics["runtime_diagnostics"] = diagnostics
            elif require_runtime_diagnostics:
                raise RuntimeError(
                    "Rust server did not emit runtime diagnostics; rebuild with "
                    "the `runtime-diagnostics` Cargo feature"
                )
        return metrics
    except Exception as error:
        log.seek(0)
        server_output = log.read()
        raise RuntimeError(
            f"{server_name} {workload} failed: {error}\n"
            f"server output (last 4000 characters):\n{server_output[-4000:]}"
        ) from error
    finally:
        stop_client(client)
        _stop_server(process)
        log.close()


def _versions(python: Path) -> dict:
    code = (
        "import importlib.metadata as m, json, platform, sys; "
        "print(json.dumps({'python': sys.version.split()[0], 'implementation': "
        "platform.python_implementation(), 'uvicorn': m.version('uvicorn'), "
        "'uvloop': m.version('uvloop'), 'httptools': m.version('httptools'), "
        "'hypercorn': m.version('hypercorn')}))"
    )
    versions = json.loads(subprocess.check_output([str(python), "-c", code], text=True))
    try:
        versions["fastapi"] = subprocess.check_output(
            [
                str(python),
                "-c",
                "import importlib.metadata as m; print(m.version('fastapi'))",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        versions["fastapi"] = None
    return versions


def _median(rows: list[dict], metric: str):
    values = [row[metric] for row in rows if row.get(metric) is not None]
    return statistics.median(values) if values else None


def _source_digest(workloads: list[str]) -> str:
    paths = [
        "pyproject.toml",
        "uv.lock",
        "Cargo.toml",
        "Cargo.lock",
        "src/lib.rs",
        "python/uvicorn_rs/_bridge.py",
        "python/uvicorn_rs/cli.py",
        "python/uvicorn_rs/server.py",
            "scripts/run_http_category_bench.py",
            "scripts/bench_http_matrix.mjs",
            "scripts/bench_http_client.c",
    ]
    paths.extend(
        [
            "examples/bench_matrix_asgi.py",
            "examples/bench_sync_asgi.py",
            "examples/bench_fastapi.py",
        ]
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / path).read_bytes())
        digest.update(b"\0")
    digest.update(json.dumps(workloads, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", nargs="+", choices=sorted(WORKLOADS), default=["fixed"])
    parser.add_argument("--servers", nargs="+", choices=sorted(SERVERS), default=list(SERVERS))
    parser.add_argument("--duration", type=float, default=5)
    parser.add_argument("--warmup", type=float, default=1)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument(
        "--python",
        type=Path,
        default=DEFAULT_PYTHON,
        help="Python interpreter used for all measured servers (default: checkout .venv)",
    )
    parser.add_argument(
        "--require-runtime-diagnostics",
        action="store_true",
        help="require the Rust runtime-diagnostics feature and add its counters to candidate rows",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks" / "results" / "http-categories-2026-10-02.json",
    )
    args = parser.parse_args()
    python = args.python.absolute()
    if not python.exists():
        raise SystemExit(f"Python interpreter does not exist: {python}")
    assert_clean_coverage_environment()
    native_client = _build_native_client()
    selected_servers = {name: SERVERS[name] for name in args.servers}
    evidence = BenchmarkEvidence(
        ROOT, python,
        ["scripts/run_http_category_bench.py", "scripts/bench_http_matrix.mjs", "scripts/bench_http_client.c",
         "examples/bench_matrix_asgi.py", "examples/bench_sync_asgi.py", "examples/bench_fastapi.py"],
        [native_client] if native_client is not None else [],
        allow_runtime_diagnostics=args.require_runtime_diagnostics,
        artifacts_dir=args.output.with_suffix(".artifacts"),
        extra_dependencies=(FASTAPI_BENCHMARK_DISTRIBUTIONS
                            if any(name.startswith("fastapi-") for name in args.workloads) else None),
    )

    rng = random.Random(args.seed)
    rows = []
    checkpoint_path = args.output.with_suffix(".jsonl")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_path.open("x")
    evidence.checkpoint_provenance(checkpoint_path)
    for workload in args.workloads:
        definition = WORKLOADS[workload]
        concurrency = definition.get("concurrency", args.concurrency)
        duration = definition.get("duration_seconds", args.duration)
        warmup = definition.get("warmup_seconds", args.warmup)
        for repetition in range(1, args.repetitions + 1):
            names = list(selected_servers)
            rng.shuffle(names)
            for server_name in names:
                evidence.label_sample(workload, server_name, repetition)
                try:
                    metrics = _sample(
                        server_name,
                        SERVERS[server_name],
                        workload,
                        duration,
                        warmup,
                        concurrency,
                        python,
                        args.require_runtime_diagnostics,
                        evidence,
                    )
                except Exception as error:
                    raise RuntimeError(
                        f"benchmark case failed: workload={workload}, server={server_name}, "
                        f"repetition={repetition}: {error}"
                    ) from error
                row = {
                    "workload": workload,
                    "server": server_name,
                    "repetition": repetition,
                    "concurrency": concurrency,
                    "duration_seconds_target": duration,
                    "warmup_seconds_target": warmup,
                    **metrics,
                }
                rows.append(row)
                print(json.dumps(row), flush=True)
                checkpoint_file.write(json.dumps(row) + "\n")
                checkpoint_file.flush()

    evidence_metadata = evidence.finish(rows)
    summaries = {}
    for workload in args.workloads:
        summaries[workload] = {}
        for server_name in selected_servers:
            case_rows = [
                row for row in rows if row["workload"] == workload and row["server"] == server_name
            ]
            if not case_rows:
                continue
            summaries[workload][server_name] = {
                metric: median_valid(case_rows, metric)
                for metric in (
                    "requests_per_second",
                    "application_bytes_per_second",
                    "p50_ms",
                    "p95_ms",
                    "p99_ms",
                    "server_cpu_percent_mean",
                    "server_rss_peak_mib",
                    "client_cpu_percent_mean",
                    "server_cpu_percent_elapsed",
                    "server_cpu_microseconds_per_request",
                    "client_cpu_percent_elapsed",
                    "client_cpu_microseconds_per_request",
                    "client_rss_peak_mib",
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
            "date": date.today().isoformat(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": psutil.cpu_count(logical=True),
            "cpu_model": cpu_model,
            "python_environment": _versions(python),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
            "source_sha256": _source_digest(args.workloads),
            "workloads": args.workloads,
            "workload_parameters": {
                name: {
                    "concurrency": WORKLOADS[name].get("concurrency", args.concurrency),
                    "duration_seconds": WORKLOADS[name].get("duration_seconds", args.duration),
                    "warmup_seconds": WORKLOADS[name].get("warmup_seconds", args.warmup),
                    "max_requests": WORKLOADS[name]["client"].get("max_requests", 0),
                    "client": WORKLOADS[name]["client"],
                }
                for name in args.workloads
            },
            "servers": selected_servers,
            "response_header_policy": {"date": "enabled on both H1 servers", "server": "disabled on Uvicorn; absent in Rust"},
            "reference_logging_policy": {"level": "ERROR", "colors": False, "access_log": "disabled", "unexpected_errors": "public app exception tracebacks remain visible to the post-shutdown diagnostic gate"},
            "lifespan_policy": {"reference": "auto via Uvicorn's public --lifespan auto", "rust": "automatic startup/support detection and shutdown", "timing_boundary": "startup precedes readiness/warmup/load; the lifespan task and state remain present during load and graceful shutdown"},
            **evidence_metadata,
            "concurrency": args.concurrency,
            "duration_seconds": args.duration,
            "warmup_seconds": args.warmup,
            "repetitions": args.repetitions,
            "seed": args.seed,
            "client": "threaded libcurl C workers with persistent HTTP/1.1 connections and complete response-body checks",
            "correctness_gate": "every measured response status and complete body exactly matches the workload oracle",
            "runtime_diagnostics_required": args.require_runtime_diagnostics,
            "native_client": "libcurl C client compiled from scripts/bench_http_client.c" if native_client is not None else "unavailable; Node.js fallback used",
            "fallback_client": "Node.js HTTP/1.1 with full body checking; used for slow-reader backpressure",
            "libcurl": subprocess.check_output(["curl-config", "--version"], text=True).strip() if native_client is not None else None,
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
