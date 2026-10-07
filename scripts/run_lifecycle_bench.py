"""Measure cold start, idle shutdown, and cancellation during graceful shutdown."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import os
import platform
import random
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import psutil

from benchmark_evidence import (
    BenchmarkEvidence, SampleMonitor, _owned_alive, _signal_owned_pid,
    assert_clean_coverage_environment, check_server_alive, median_valid,
    owned_process, resource, stop_owned,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
SERVERS = {
    "uvicorn-rs-asyncio": {"kind": "rust", "loop": "asyncio"},
    "uvicorn-rs-uvloop": {"kind": "rust", "loop": "uvloop"},
    "uvicorn-asyncio-httptools": {"kind": "uvicorn", "loop": "asyncio", "http": "httptools"},
    "uvicorn-uvloop-httptools": {"kind": "uvicorn", "loop": "uvloop", "http": "httptools"},
}


class LifecyclePhaseError(RuntimeError):
    """Keep the completed portion of a failed lifecycle observation."""

    def __init__(self, measurement: dict):
        self.measurement = measurement
        super().__init__(measurement["error"]["message"])


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
        "--no-server-header", "--log-level", "error", "--no-use-colors",
    ]


class DeadlineReader(io.RawIOBase):
    """Check one absolute deadline before every HTTP parser socket read."""

    def __init__(self, connection, deadline: float, byte_limit: int):
        super().__init__()
        self.connection = connection
        self.deadline = deadline
        self.bytes_remaining = byte_limit

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("lifecycle readiness exceeded its absolute response deadline")
        if self.bytes_remaining <= 0:
            raise RuntimeError("lifecycle response exceeded the bounded wire capture")
        self.connection.settimeout(remaining)
        length = self.connection.recv_into(memoryview(buffer)[:self.bytes_remaining])
        self.bytes_remaining -= length
        return length


class DeadlineResponseSocket:
    """Provide HTTPResponse's reader while retaining the owned socket."""

    def __init__(self, connection, deadline: float, byte_limit: int):
        self.connection = connection
        self.deadline = deadline
        self.byte_limit = byte_limit

    def makefile(self, mode):
        if mode != "rb":
            raise ValueError("lifecycle HTTP response parser requires a binary reader")
        return io.BufferedReader(DeadlineReader(self.connection, self.deadline, self.byte_limit))


def request(port: int, path: str, expected_bytes: int, deadline: float) -> tuple[int, bytes]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("lifecycle readiness absolute deadline elapsed")
    with socket.create_connection(("127.0.0.1", port), timeout=remaining) as connection:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("lifecycle readiness absolute deadline elapsed during connect")
        connection.settimeout(remaining)
        connection.sendall(f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode("ascii"))
        response = http.client.HTTPResponse(DeadlineResponseSocket(connection, deadline, 16_384 + expected_bytes + 1))
        try:
            response.begin()
            body = response.read(expected_bytes + 1)
            if time.monotonic() >= deadline:
                raise TimeoutError("lifecycle readiness absolute deadline elapsed during response")
            return response.status, body
        finally:
            response.close()


def wait_response(process: subprocess.Popen, port: int, path: str, expected: bytes, monitor) -> float:
    deadline = time.monotonic() + 15
    last_error = None
    while time.monotonic() < deadline:
        check_server_alive(process)
        monitor.sample()
        try:
            status, body = request(port, path, len(expected), deadline)
            if status != 200 or body != expected:
                raise AssertionError(f"expected 200 {expected!r}, got {status} {body!r}")
            return time.monotonic()
        except OSError as error:
            last_error = error
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    raise TimeoutError(f"server did not serve {path}: {last_error}")


def wait_hold_started(process, log, monitor) -> float:
    """Require the application's actual pending-operation entry before SIGTERM."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        check_server_alive(process)
        monitor.sample()
        log.flush()
        # The child's inherited log descriptor shares its file offset with
        # the parent. Poll through a distinct reader to preserve every write.
        lines = Path(log.name).read_text().splitlines()
        count = lines.count("APP_HOLD_STARTED")
        if count == 1:
            if "APP_CANCELLED_BY_SHUTDOWN" in lines or "LIFESPAN_SHUTDOWN_COMPLETE" in lines:
                raise RuntimeError("held application completed before the measured shutdown signal")
            check_server_alive(process)
            return time.monotonic()
        if count > 1:
            raise RuntimeError("more than one held application entered during lifecycle phase")
        time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    raise TimeoutError("held ASGI app did not emit APP_HOLD_STARTED within fifteen seconds")


def start(server: dict, app: str, log):
    port = free_port()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    process = owned_process(
        command(server, app, port), cwd=ROOT, env=env, stdout=log, stderr=log, text=True,
    )
    return port, process


def stop_sigterm(process: subprocess.Popen, monitor) -> tuple[float, float]:
    """Measure the official SIGTERM path without cleanup escalation."""
    check_server_alive(process)
    started = time.monotonic()
    _signal_owned_pid(process, process.pid, signal.SIGTERM)
    deadline = started + 5
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("server did not exit within five seconds after SIGTERM")
        try:
            process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            monitor.sample()
    exited_at = time.monotonic()
    if _owned_alive(process):
        raise RuntimeError("owned descendants remained alive after official server shutdown")
    return exited_at - started, exited_at


def child_cpu_seconds() -> float | None:
    if resource is None:
        return None
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def lifecycle_sampling_policy() -> dict:
    return {
        **SampleMonitor.contention_policy,
        "sampling_interval_seconds": None,
        "minimum_observed_interval_seconds": 0.05,
        "sampling_cadence": "variable: readiness/hold-entry polls10ms, exit waits50ms, plus request and process-scan duration; monitor skips intervals below50ms",
        "minimum_two_interval_duration_seconds": 0.1,
        "consecutive_threshold_interpretation": "two busy observed intervals span at least approximately100ms plus scan/request delay, rather than the sustained-load runner's nominal500ms",
    }


def uvicorn_cancellation_block(lines: list[str], server: dict, evidence) -> tuple[set[int], dict]:
    """Recognize one specific logged timeout and its exact held-task traceback."""
    timeout_line = "ERROR:    Cancel 1 running task(s), timeout graceful shutdown exceeded"
    header = "ERROR:    Exception in ASGI application"
    terminal = "asyncio.exceptions.CancelledError: Task cancelled, timeout graceful shutdown exceeded"
    if lines.count(timeout_line) != 1 or lines.count(header) != 1 or lines.count(terminal) != 1:
        raise RuntimeError("Uvicorn held shutdown did not report its single expected timeout/cancellation block")
    timeout_index, start_index, end_index = lines.index(timeout_line), lines.index(header), lines.index(terminal)
    if not lines.index("APP_HOLD_STARTED") < timeout_index < lines.index("APP_CANCELLED_BY_SHUTDOWN") < start_index < end_index:
        raise RuntimeError("Uvicorn cancellation diagnostics did not follow the held task entry/timeout/cancellation")
    cursor = start_index + 1
    if lines[cursor] == "":
        cursor += 1
    if lines[cursor] != "Traceback (most recent call last):":
        raise RuntimeError("Uvicorn cancellation diagnostic has no exact traceback header")
    cursor += 1
    package = Path(evidence.dependencies_before["uvicorn"]["modules"]["uvicorn"]["package_roots"][0])
    version = ".".join(evidence.runtime["version"].split()[0].split(".")[:2])
    standard_library = Path(evidence.runtime["python"]).resolve().parent.parent / "lib" / f"python{version}"
    frames = (
        (package / "protocols/http" / f"{server['http']}_impl.py", "run_asgi", "result = await app(  # type: ignore[func-returns-value]"),
        (package / "middleware/proxy_headers.py", "__call__", "return await self.app(scope, receive, send)"),
        (ROOT / "examples/lifespan_asgi.py", "app", "await asyncio.Event().wait()"),
        (standard_library / "asyncio/locks.py", "wait", "await fut"),
    )
    observed_frames = []
    for expected_path, function, statement in frames:
        if cursor >= end_index:
            raise RuntimeError("Uvicorn cancellation traceback ended before its expected frame chain")
        match = re.fullmatch(r'  File "([^"\n]+)", line ([0-9]+), in ([A-Za-z0-9_]+)', lines[cursor])
        if match is None or Path(match[1]).resolve() != expected_path.resolve() or match[3] != function:
            raise RuntimeError("Uvicorn cancellation traceback contains an unexpected frame")
        number = int(match[2])
        source = expected_path.read_text().splitlines()
        if not 1 <= number <= len(source) or source[number - 1].strip() != statement:
            raise RuntimeError("Uvicorn cancellation traceback does not match the exact live held-task source line")
        if cursor + 1 >= end_index or lines[cursor + 1] != "    " + statement:
            raise RuntimeError("Uvicorn cancellation traceback has unexpected source text")
        observed_frames.append({"path": str(expected_path), "line": number, "function": function, "source": statement})
        cursor += 2
        # CPython may show one position indicator under the source line. Only
        # whitespace/caret/tilde display is normalized; no other text is accepted.
        if cursor < end_index and re.fullmatch(r"    [ ~^]*[~^][ ~^]*", lines[cursor]):
            cursor += 1
    if cursor != end_index:
        raise RuntimeError("Uvicorn cancellation traceback contains an extra frame, exception chain, or diagnostic")
    block = "\n".join(lines[start_index:end_index + 1])
    return {timeout_index, *range(start_index, end_index + 1)}, {
        "kind": "single deliberately held Uvicorn task timeout and cancellation",
        "timeout_line": timeout_line, "terminal_exception": terminal,
        "frames": observed_frames, "traceback_sha256": hashlib.sha256(block.encode()).hexdigest(),
        "raw_line_numbers": [timeout_index + 1, *range(start_index + 1, end_index + 2)],
    }


def diagnostic_gate(output: str, server: dict, phase: str, returncode: int, evidence) -> dict:
    lines = output.splitlines()
    lifespan_complete = lines.count("LIFESPAN_SHUTDOWN_COMPLETE")
    cancelled = lines.count("APP_CANCELLED_BY_SHUTDOWN")
    held = lines.count("APP_HOLD_STARTED")
    # Uvicorn restores the original signal handler after ASGI cleanup and then
    # re-raises SIGTERM. Rust's CLI consumes its cancellation and exits zero.
    allowed_exit = (0, -signal.SIGTERM) if server["kind"] == "uvicorn" else (0,)
    if returncode not in allowed_exit:
        raise RuntimeError(f"{phase} shutdown exited unexpectedly: {returncode}")
    if lifespan_complete != 1 or cancelled != (1 if phase == "active" else 0) or held != (1 if phase == "active" else 0):
        raise RuntimeError(f"incomplete lifecycle markers: lifespan={lifespan_complete}, hold={held}, cancellation={cancelled}")
    if phase == "active" and not lines.index("APP_HOLD_STARTED") < lines.index("APP_CANCELLED_BY_SHUTDOWN") < lines.index("LIFESPAN_SHUTDOWN_COMPLETE"):
        raise RuntimeError("held request entry/cancellation/lifespan completion were out of order")
    if re.search(r"(?m)^thread [^\n]*panicked at|^fatal runtime error:", output):
        raise RuntimeError("unexpected Rust panic diagnostic during lifecycle phase")
    normalized_indices = set()
    normalization_receipt = []
    if phase == "active" and server["kind"] == "uvicorn":
        normalized_indices, receipt = uvicorn_cancellation_block(lines, server, evidence)
        normalization_receipt.append(receipt)
    # The single deliberately held request re-raises asyncio.CancelledError.
    # Accept only PyErr's exact empty-message display for that request, with
    # its one optional trailing space; no traceback or other error is waived.
    cancellation_lines = [
        line for line in lines
        if phase == "active" and server["kind"] == "rust" and line in (
            "uvicorn-rs: ASGI request failed: CancelledError:",
            "uvicorn-rs: ASGI request failed: CancelledError: ",
        )
    ]
    native_errors = [
        line for line in lines if line.startswith("uvicorn-rs:")
        and re.search(r"\b(failed|exceeded|aborting)\b|does not support lifespan", line)
        and line not in cancellation_lines
    ]
    if native_errors or len(cancellation_lines) > 1:
        raise RuntimeError(f"unexpected native lifecycle error: {native_errors[:3]}")
    for index, line in enumerate(lines):
        if line in cancellation_lines:
            normalized_indices.add(index)
    if cancellation_lines:
        normalization_receipt.append({"kind": "single deliberately held Rust task cancellation", "exact_line": cancellation_lines[0], "occurrences": 1})
    remaining = [line for index, line in enumerate(lines) if index not in normalized_indices and line and line not in {
        "APP_HOLD_STARTED", "APP_CANCELLED_BY_SHUTDOWN", "LIFESPAN_SHUTDOWN_COMPLETE",
    }]
    if remaining:
        raise RuntimeError(f"unexpected lifecycle diagnostic/error/traceback: {remaining[:3]}")
    return {
        "lifespan_shutdown_complete": True,
        "active_asgi_task_cancelled": cancelled == 1,
        "active_asgi_task_started": held == 1,
        "expected_cancellation_diagnostic_count": len(cancellation_lines),
        "diagnostic_normalization_receipt": normalization_receipt,
        "unexpected_panic_events": 0, "unexpected_native_errors": 0,
        "server_lifecycle_gate": "passed",
    }


def measure_phase(server_name: str, server: dict, phase: str, repetition: int, evidence) -> dict:
    identity_before = evidence.before_sample()
    evidence.label_sample(f"lifecycle-{phase}", server_name, repetition)
    log = evidence.open_server_log()
    process = pending = monitor = None
    result = {"workload": "lifecycle", "server": server_name, "repetition": repetition, "phase": phase}
    error = None
    cpu_before = child_cpu_seconds()
    started = time.monotonic()
    exited_at = None
    try:
        port, process = start(server, "examples.lifespan_asgi:app", log)
        # Lifecycle requests run in this observer process. Shared monitor client
        # CPU fields are intentionally discarded; RUSAGE below belongs to the
        # server, the only child created/reaped during this phase.
        monitor = SampleMonitor(psutil.Process(process.pid), psutil.Process(os.getpid()))
        ready_at = wait_response(process, port, "/state", b"startup-token:0", monitor)
        result["cold_start_to_first_lifespan_request_ms"] = (ready_at - started) * 1000
        ready_rss = sum(p.memory_info().rss for p in SampleMonitor._tree(psutil.Process(process.pid)))
        result["sampled_server_rss_mib"] = ready_rss / (1024 * 1024)
        monitor.rss_samples["server"].append(ready_rss)
        if phase == "active":
            pending = socket.create_connection(("127.0.0.1", port), timeout=2)
            pending.sendall(b"GET /hold HTTP/1.1\r\nHost: localhost\r\n\r\n")
            result["hold_entry_observed_seconds_from_phase_start"] = wait_hold_started(process, log, monitor) - started
        elapsed, exited_at = stop_sigterm(process, monitor)
        result[f"{phase}_sigterm_to_process_exit_ms"] = elapsed * 1000
    except Exception as caught:
        error = caught
    finally:
        if pending is not None:
            try:
                pending.close()
            except OSError as caught:
                error = error or caught
        try:
            result["server_shutdown"] = stop_owned(process)
        except Exception as caught:
            result["cleanup_error"] = {"type": type(caught).__name__, "message": str(caught)}
            error = error or caught
        cpu_after = child_cpu_seconds()
        if monitor is not None:
            try:
                observed = monitor.finish({})
                result["observer_process_tree_rss_peak_mib"] = observed["client_rss_peak_mib"]
                result.update({key: value for key, value in observed.items() if not key.startswith("client_") and key != "server_cpu_microseconds_per_request"})
                if cpu_before is not None and cpu_after is not None:
                    result["server_cpu_seconds"] = max(0.0, cpu_after - cpu_before)
                    result["server_cpu_complete"] = True
                else:
                    result["server_cpu_complete"] = False
                result["sample_monitor_wall_seconds"] = result["resource_wall_seconds"]
                result["resource_wall_seconds"] = (exited_at or time.monotonic()) - started
                result["server_cpu_percent_elapsed"] = result["server_cpu_seconds"] / result["resource_wall_seconds"] * 100
                result["server_cpu_limitations"] = "reaped-child lifetime CPU includes startup/readiness/shutdown; no other child is created or reaped in this phase" if result["server_cpu_complete"] else "sampled process-tree CPU can omit final exited-process interval"
            except Exception as caught:
                error = error or caught
        log.flush()
        log.seek(0)
        output = log.read()
        result["server_log"] = {"path": str(log.name), "sha256": hashlib.sha256(Path(log.name).read_bytes()).hexdigest()}
        if error is None:
            try:
                result.update(diagnostic_gate(output, server, phase, process.returncode, evidence))
                if result["server_shutdown"]["forced"]:
                    raise RuntimeError("lifecycle server required cleanup escalation")
            except Exception as caught:
                error = caught
        try:
            identity = evidence.after_sample(identity_before)
            result["timing_valid"] = result.get("timing_valid", True) and identity["timing_valid"]
            result.setdefault("timing_invalid_reasons", []).extend(identity["timing_invalid_reasons"])
            result["measurement_identity"] = identity["measurement_identity"]
        except Exception as caught:
            error = error or caught
        log.close()
    result["failures"] = 1 if error else 0
    result["correctness_valid"] = error is None
    if error is not None:
        result["timing_valid"] = False
        result.setdefault("timing_invalid_reasons", []).append("lifecycle_correctness_gate_failed")
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        raise LifecyclePhaseError(result) from error
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--servers", nargs="+", choices=sorted(SERVERS), default=list(SERVERS))
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "lifecycle-categories-2026-10-02.json")
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("repetitions must be positive")
    if not PYTHON.exists():
        raise SystemExit("install this project and benchmark dependencies in .venv before measuring lifecycle")
    assert_clean_coverage_environment()
    selected_servers = {name: SERVERS[name] for name in args.servers}
    evidence = BenchmarkEvidence(
        ROOT, PYTHON,
        ["scripts/run_lifecycle_bench.py", "examples/lifespan_asgi.py"], [],
        artifacts_dir=args.output.with_suffix(".artifacts"),
    )
    checkpoint_path = args.output.with_suffix(".jsonl")
    phases_path = args.output.with_suffix(".phases.jsonl")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = checkpoint_path.open("x")
    phases_checkpoint = phases_path.open("x")
    evidence.checkpoint_provenance(checkpoint_path)
    evidence.checkpoint_provenance(phases_path)
    for path in (checkpoint_path, phases_path):
        sidecar = path.with_suffix(path.suffix + ".meta.json")
        provenance = json.loads(sidecar.read_text())
        provenance["host_contention_policy"] = lifecycle_sampling_policy()
        sidecar.write_text(json.dumps(provenance, indent=2) + "\n")
    rng = random.Random(args.seed)
    rows = []
    try:
        for repetition in range(1, args.repetitions + 1):
            names = list(selected_servers)
            rng.shuffle(names)
            for name in names:
                phases = {}
                try:
                    for phase in ("idle", "active"):
                        try:
                            measurement = measure_phase(name, selected_servers[name], phase, repetition, evidence)
                        except LifecyclePhaseError as caught:
                            measurement = caught.measurement
                            phases[phase] = measurement
                            phases_checkpoint.write(json.dumps(measurement) + "\n")
                            phases_checkpoint.flush()
                            raise
                        phases[phase] = measurement
                        phases_checkpoint.write(json.dumps(measurement) + "\n")
                        phases_checkpoint.flush()
                    idle, active = phases["idle"], phases["active"]
                    row = {
                        "workload": "lifecycle", "server": name, "repetition": repetition,
                        "cold_start_to_first_lifespan_request_ms": idle["cold_start_to_first_lifespan_request_ms"],
                        "idle_sigterm_to_process_exit_ms": idle["idle_sigterm_to_process_exit_ms"],
                        "active_sigterm_to_process_exit_ms": active["active_sigterm_to_process_exit_ms"],
                        "active_asgi_task_cancelled": active["active_asgi_task_cancelled"],
                        "active_asgi_task_started": active["active_asgi_task_started"],
                        "sampled_server_rss_mib": idle["sampled_server_rss_mib"],
                        "phase_measurements": phases,
                        "failures": 0, "correctness_valid": True,
                        "server_lifecycle_gate": "passed",
                        "unexpected_panic_events": 0, "unexpected_native_errors": 0,
                        "timing_valid": all(p["timing_valid"] for p in phases.values()),
                        "timing_invalid_reasons": sorted({reason for p in phases.values() for reason in p["timing_invalid_reasons"]}),
                    }
                    for phase, measurement in phases.items():
                        for metric in ("server_cpu_seconds", "server_cpu_percent_elapsed", "server_rss_peak_mib"):
                            row[f"{phase}_phase_{metric}"] = measurement[metric]
                except Exception as caught:
                    row = {
                        "workload": "lifecycle", "server": name, "repetition": repetition,
                        "failures": 1, "correctness_valid": False, "timing_valid": False,
                        "timing_invalid_reasons": ["lifecycle_correctness_gate_failed"],
                        "phase_measurements": phases,
                        "error": {"type": type(caught).__name__, "message": str(caught)},
                    }
                    rows.append(row)
                    checkpoint.write(json.dumps(row) + "\n")
                    checkpoint.flush()
                    failure_report = {"metadata": evidence.finish(rows), "rows": rows}
                    failure_report["metadata"]["completion_state"] = "failed lifecycle category; raw phase and row checkpoints retained"
                    failure_report["metadata"]["performance_evidence_status"] = "not_proven"
                    failure_report["metadata"]["host_contention_policy"] = lifecycle_sampling_policy()
                    args.output.with_suffix(".failure.json").write_text(json.dumps(failure_report, indent=2) + "\n")
                    raise RuntimeError(f"lifecycle case failed: server={name}, repetition={repetition}; logs={evidence.artifacts_dir}") from caught
                rows.append(row)
                checkpoint.write(json.dumps(row) + "\n")
                checkpoint.flush()
                print(json.dumps(row), flush=True)
    finally:
        checkpoint.close()
        phases_checkpoint.close()

    metadata = evidence.finish(rows)
    summary = {}
    for name in selected_servers:
        subset = [row for row in rows if row["server"] == name]
        summary[name] = {
            key: median_valid(subset, key)
            for key in (
                "cold_start_to_first_lifespan_request_ms", "idle_sigterm_to_process_exit_ms",
                "active_sigterm_to_process_exit_ms", "sampled_server_rss_mib",
                "idle_phase_server_cpu_seconds", "active_phase_server_cpu_seconds",
                "idle_phase_server_cpu_percent_elapsed", "active_phase_server_cpu_percent_elapsed",
                "idle_phase_server_rss_peak_mib", "active_phase_server_rss_peak_mib",
            )
        }
    try:
        cpu_model = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        cpu_model = platform.processor()
    report = {
        "metadata": {
            **metadata,
            "date": date.today().isoformat(), "platform": platform.platform(),
            "machine": platform.machine(), "logical_cpus": psutil.cpu_count(logical=True),
            "cpu_model": cpu_model, "python": platform.python_version(),
            "uvicorn": subprocess.check_output([str(PYTHON), "-c", "import importlib.metadata as m; print(m.version('uvicorn'))"], text=True).strip(),
            "uvloop": subprocess.check_output([str(PYTHON), "-c", "import importlib.metadata as m; print(m.version('uvloop'))"], text=True).strip(),
            "source_sha256": evidence.before["source_sha256"],
            "servers": selected_servers, "repetitions": args.repetitions, "seed": args.seed,
            "correctness_gate": "exact lifespan-state response, held request entry before SIGTERM, held cancellation before lifespan shutdown completion, expected exit and strict diagnostics validated",
            "process_isolation": "owned sessions and PID/create_time identities; measured shutdown sends SIGTERM only to the original leader; cleanup verifies all captured original identities exited",
            "client_wall_limit": "one absolute15s deadline through readiness connect/send/headers/body (bodycapture expected length+1, wirecapture16KiB+expected length+1); hold-entry marker15s; official SIGTERM exit5s; failed phase cleanup bounded owned TERM/KILL",
            "host_contention_policy": lifecycle_sampling_policy(),
            "graceful_timeout_seconds": 2,
            "resource_boundary": "two independent server process lifetimes per row: idle and active; startup/readiness/held request/shutdown included, with in-process observer CPU reported separately",
            "observer_memory_limitations": "observer_process_tree_rss_peak_mib includes the in-process requester and its server descendants; server_rss_peak_mib remains the server-only sampled tree",
            "load_model": "one completed lifespan-state request per server process; active phase additionally holds one request until shutdown cancellation",
            "latency_limitations": "lifecycle observations are affected by same-process request handling and observer sampling; no sustained throughput or per-request CPU equivalence is claimed",
            "cancellation_diagnostic_normalization": {
                "phase": "active", "maximum_occurrences": 1,
                "rust_exact_line": "uvicorn-rs: ASGI request failed: CancelledError:",
                "rust_optional_suffix": "one trailing space from PyErr's empty-message display",
                "uvicorn_log_level": "publicERROR without colors; unexpected logger errors remain visible",
                "uvicorn_timeout_line": "ERROR:    Cancel 1 running task(s), timeout graceful shutdown exceeded",
                "uvicorn_terminal_exception": "asyncio.exceptions.CancelledError: Task cancelled, timeout graceful shutdown exceeded",
                "uvicorn_traceback_frames": "exact installed protocol run_asgi, proxy_headers.__call__, lifespan_asgi.app Event.wait, stdlib asyncio.locks.Event.wait; file/function/source text and observed line verified, optional caret display only",
                "requirements": "exact held-entry/cancellation/lifespan markers in order, expected official exit, no other error, traceback, exception chain, task diagnostic, or panic; per-phase normalization receipt and full raw logs retained",
                "uvicorn_exit_normalization": "0 or -SIGTERM only after the same ASGI completion checks; Uvicorn intentionally re-raises the captured SIGTERM",
            },
            "observer_startup_limitations": "shared observer initializes after server spawn and before the first readiness request; its reported CPU and elapsed work can affect cold-start observations",
            "raw_phase_checkpoint": str(phases_path),
            "definitions": {
                "cold_start_to_first_lifespan_request_ms": "phase preparation (free port, environment, process spawn) through observed valid lifespan-state response; polling/observer/request delays make this an upper bound on application readiness, with no sub-poll startup precision claim",
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
