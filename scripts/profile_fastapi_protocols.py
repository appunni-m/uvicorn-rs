"""Collect diagnostic ASGI stage timings for FastAPI over HTTP/2, HTTP/3, or WebSockets.

The public benchmark runners provide the workload clients, lifecycle checks,
resource sampling, and source identity capture. This adapter selects the same
FastAPI app wrapped by ``examples.profile_fastapi`` on both implementations
and retains stage timing separately from normal performance measurements.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h2_category_bench as h2_bench
import run_h3_category_bench as h3_bench
import run_websocket_category_bench as websocket_bench

PROFILE_APP = "examples.profile_fastapi:app"
DIAGNOSTIC_FEATURE_MARKER = "uvicorn-rs-runtime-diagnostics "


def parse_runtime_diagnostics(metrics: dict) -> dict[str, int] | None:
    """Read the optional Rust runtime counters from the retained server log."""
    log_path = metrics.get("server_log", {}).get("path")
    if not log_path:
        return None
    prefix = DIAGNOSTIC_FEATURE_MARKER
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return {
                key: int(value)
                for key, value in (
                    part.split("=", 1) for part in line[len(prefix) :].split()
                )
            }
    return None


def configure_protocol(protocol: str) -> tuple[object, list[str], list[str], list[str]]:
    """Return runner, default workloads, server pairs, and source inputs."""
    if protocol == "http2":
        return (
            h2_bench,
            ["fixed", "request-upload-small-chunks", "many-response-chunks"],
            ["uvicorn-rs-asyncio", "hypercorn-asyncio"],
            [
                "scripts/run_h2_category_bench.py",
                "tools/http3-probe/src/bin/http2.rs",
                "tools/http3-probe/Cargo.toml",
                "tools/http3-probe/Cargo.lock",
            ],
        )
    if protocol == "http3":
        return (
            h3_bench,
            ["fixed", "large-response", "many-response-chunks", "slow-reader-backpressure"],
            ["uvicorn-rs-asyncio", "hypercorn-asyncio"],
            [
                "scripts/run_h3_category_bench.py",
                "tools/http3-probe/src/bin/bench.rs",
                "tools/http3-probe/Cargo.toml",
                "tools/http3-probe/Cargo.lock",
            ],
        )
    return (
        websocket_bench,
        ["connection-handshake", "text-echo", "binary-64k-echo"],
        ["uvicorn-rs-asyncio", "uvicorn-asyncio-websockets"],
        [
            "scripts/run_websocket_category_bench.py",
            "tools/http3-probe/src/bin/websocket.rs",
            "tools/http3-probe/Cargo.toml",
            "tools/http3-probe/Cargo.lock",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, choices=("http2", "http3", "websocket"))
    parser.add_argument("--workloads", nargs="+")
    parser.add_argument("--servers", nargs="+")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--warmup", type=float, default=0.0)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner, defaults, default_servers, source_inputs = configure_protocol(args.protocol)
    workloads = args.workloads or defaults
    servers = args.servers or default_servers
    for workload in workloads:
        if workload not in runner.WORKLOADS:
            parser.error(f"unknown {args.protocol} workload: {workload}")
    for server in servers:
        if server not in runner.SERVERS:
            parser.error(f"unknown {args.protocol} server: {server}")
    if args.repetitions < 1 or args.duration <= 0 or args.warmup < 0:
        parser.error("repetitions and duration must be positive; warmup cannot be negative")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(output.suffix + ".jsonl").exists():
        parser.error(f"refusing to overwrite existing benchmark output: {output}")
    stages_dir = output.parent / f"{output.stem}-stages"
    stages_dir.mkdir()
    checkpoint = output.with_suffix(output.suffix + ".jsonl")
    checkpoint_file = checkpoint.open("x", encoding="utf-8")

    evidence = runner.BenchmarkEvidence(
        ROOT,
        runner.PYTHON,
        [
            *source_inputs,
            "scripts/profile_fastapi_protocols.py",
            "examples/bench_fastapi.py",
            "examples/profile_fastapi.py",
        ],
        [runner.CLIENT],
        allow_runtime_diagnostics=True,
        artifacts_dir=output.with_suffix(output.suffix + ".artifacts"),
    )
    runner.assert_clean_coverage_environment()
    evidence.checkpoint_provenance(checkpoint)

    if args.protocol in {"http2", "http3"}:
        for workload in workloads:
            runner.WORKLOADS[workload]["app"] = PROFILE_APP
    else:
        original_server_command = runner.server_command

        def profiled_server_command(server: dict, port: int) -> list[str]:
            return [
                PROFILE_APP if part == "examples.bench_fastapi:app" else part
                for part in original_server_command(server, port)
            ]

        runner.server_command = profiled_server_command

    if args.concurrency is not None:
        concurrency = args.concurrency
    elif args.protocol == "http2":
        concurrency = 64
    elif args.protocol == "http3":
        concurrency = 1
    else:
        concurrency = 32
    rng = random.Random(args.seed)
    rows: list[dict] = []
    prior_timing_path = os.environ.get("UVICORN_RS_ASGI_TIMINGS")

    def run_one(workload: str, server_name: str, repetition: int) -> dict:
        stage_path = stages_dir / f"{workload}-{server_name}-repeat-{repetition}.json"
        os.environ["UVICORN_RS_ASGI_TIMINGS"] = str(stage_path)
        evidence.label_sample(workload, server_name, repetition)
        server = runner.SERVERS[server_name]
        if args.protocol in {"http2", "http3"}:
            raise RuntimeError(f"{args.protocol.upper()} sample requires temporary certificate setup")
        metrics = runner.sample(
            server,
            workload,
            args.duration,
            args.warmup,
            runner.WORKLOADS[workload].get("concurrency", concurrency),
            evidence,
        )
        return attach_diagnostics(workload, server_name, repetition, metrics, stage_path)

    def attach_diagnostics(
        workload: str,
        server_name: str,
        repetition: int,
        metrics: dict,
        stage_path: Path,
    ) -> dict:
        if not stage_path.is_file():
            raise RuntimeError(f"ASGI stage timings were not written: {stage_path}")
        metrics["asgi_stage_diagnostics"] = json.loads(stage_path.read_text(encoding="utf-8"))
        metrics["asgi_stage_path"] = str(stage_path)
        if server_name.startswith("uvicorn-rs-"):
            metrics["runtime_diagnostics"] = parse_runtime_diagnostics(metrics)
            if metrics["runtime_diagnostics"] is None:
                raise RuntimeError("Rust server did not emit runtime-diagnostics counters")
        metrics["timing_valid"] = False
        metrics.setdefault("timing_invalid_reasons", []).append("instrumented_asgi_stage_diagnostics")
        metrics["performance_evidence_status"] = "diagnostic_only"
        row = {
            "workload": workload,
            "server": server_name,
            "repetition": repetition,
            **metrics,
        }
        rows.append(row)
        checkpoint_file.write(json.dumps(row, separators=(",", ":")) + "\n")
        checkpoint_file.flush()
        print(json.dumps({
            "workload": workload,
            "server": server_name,
            "repetition": repetition,
            "requests": metrics.get("requests"),
            "messages_per_second": metrics.get("messages_per_second"),
            "requests_per_second": metrics.get("requests_per_second"),
            "stage_path": str(stage_path),
        }), flush=True)
        return row

    try:
        if args.protocol in {"http2", "http3"}:
            import tempfile

            prefix = "uvicorn-rs-stage-h3-" if args.protocol == "http3" else "uvicorn-rs-stage-h2-"
            with tempfile.TemporaryDirectory(prefix=prefix) as directory:
                ca_certificate, cert, key = runner.generate_server_certificate(Path(directory))
                config = Path(directory) / "hypercorn.toml"
                include_date = "false" if args.protocol == "http3" else "true"
                config.write_text(
                    "keep_alive_max_requests = 100000000\n"
                    "include_server_header = false\n"
                    f"include_date_header = {include_date}\n",
                    encoding="utf-8",
                )
                for workload in workloads:
                    for repetition in range(1, args.repetitions + 1):
                        order = list(servers)
                        rng.shuffle(order)
                        for server_name in order:
                            stage_path = stages_dir / f"{workload}-{server_name}-repeat-{repetition}.json"
                            os.environ["UVICORN_RS_ASGI_TIMINGS"] = str(stage_path)
                            evidence.label_sample(workload, server_name, repetition)
                            metrics = runner.sample(
                                runner.SERVERS[server_name], workload, args.duration,
                                args.warmup, concurrency, cert, key, ca_certificate, config, evidence,
                            )
                            attach_diagnostics(workload, server_name, repetition, metrics, stage_path)
        else:
            for workload in workloads:
                for repetition in range(1, args.repetitions + 1):
                    order = list(servers)
                    rng.shuffle(order)
                    for server_name in order:
                        run_one(workload, server_name, repetition)
    finally:
        if prior_timing_path is None:
            os.environ.pop("UVICORN_RS_ASGI_TIMINGS", None)
        else:
            os.environ["UVICORN_RS_ASGI_TIMINGS"] = prior_timing_path
        checkpoint_file.close()

    evidence_metadata = evidence.finish(rows)
    report = {
        "schema": "uvicorn-rs-fastapi-stage-diagnostics@1",
        "protocol": args.protocol,
        "application": "upstream FastAPI app wrapped by examples.profile_fastapi; ASGI messages are forwarded unchanged",
        "performance_evidence_status": "diagnostic_only",
        "diagnostic_interpretation": (
            "ASGI stage timings and server counters locate work; wrapper instrumentation perturbs timing, "
            "so throughput, latency, and CPU values in these rows are not normal-build comparisons."
        ),
        "websocket_timing_unit": "one WebSocket connection/session, with send/receive totals spanning the session",
        "workloads": workloads,
        "servers": servers,
        "concurrency": concurrency,
        "duration_seconds": args.duration,
        "warmup_seconds": args.warmup,
        "repetitions": args.repetitions,
        "seed": args.seed,
        **evidence_metadata,
        "rows": rows,
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
