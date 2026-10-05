"""Capture macOS server stacks under the maintained, body-checked HTTP load.

These are diagnostic runs. Apple ``sample`` changes scheduling, so their raw
client timing fields must never contribute to benchmark medians or speed claims.
The default is ten seconds of load, with six seconds of sampling at one
millisecond after the first second. Run profiles separately from benchmarks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import run_http_category_bench as http_bench
from benchmark_evidence import BenchmarkEvidence, assert_clean_coverage_environment


ROOT = http_bench.ROOT
PROFILE_WORKLOADS = ("fixed", "large-response", "many-response-chunks")
SAMPLE = Path("/usr/bin/sample")
SOURCE_FILES = [
    "scripts/profile_http_workload.py",
    "scripts/run_http_category_bench.py",
    "scripts/bench_http_client.c",
    "scripts/bench_http_matrix.mjs",
    "examples/bench_matrix_asgi.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_receipt(path: Path, receipt: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _stop(process: subprocess.Popen | None, *, graceful: bool = False) -> dict | None:
    """Reap the process and its private process group, retaining escalation."""
    if process is None:
        return None
    stages = []
    if process.poll() is None:
        for signum, timeout in (
            (signal.SIGINT if graceful else signal.SIGTERM, 10 if graceful else 2),
            (signal.SIGTERM, 2),
            (signal.SIGKILL, 2),
        ):
            stages.append(signal.Signals(signum).name)
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=timeout)
                break
            except subprocess.TimeoutExpired:
                continue
    process.wait(timeout=2)
    return {
        "returncode": process.returncode,
        "signals": stages,
        "graceful": graceful and stages == ["SIGINT"] and process.returncode == 0,
    }


def _client_result(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("HTTP client output is not a JSON object")
    if result.get("failures") != 0 or result.get("first_failure") is not None:
        raise RuntimeError(f"HTTP client correctness gate failed: {result.get('first_failure')}")
    if not isinstance(result.get("requests"), int) or result["requests"] < 1:
        raise RuntimeError("HTTP client completed no requests")
    return {
        key: result[key]
        for key in ("requests", "failures", "first_failure", "request_body_bytes", "response_body_bytes")
    }


def _sample_summary(path: Path, pid: int, interval_ms: int) -> dict:
    """Keep sample counts distinct from CPU utilization or elapsed fractions."""
    text = path.read_text(encoding="utf-8", errors="replace")
    header = re.search(r"Analysis of sampling .*?\(pid (\d+)\) every (\d+) milliseconds?", text)
    if header is None or int(header[1]) != pid or int(header[2]) != interval_ms:
        raise RuntimeError("Apple sample target PID or sampling interval differs from the command")
    if "Call graph:" not in text or "Binary Images:" not in text:
        raise RuntimeError("Apple sample did not produce a complete call graph and image inventory")
    thread_roots = [
        {"samples": int(match[1]), "thread": match[2].strip()}
        for match in re.finditer(r"^\s+(\d+) (Thread_.*)$", text, re.MULTILINE)
    ]
    if not thread_roots:
        raise RuntimeError("Apple sample contained no sampled threads")
    collapsed = text.split("Sort by top of stack, same collapsed (when >= 5):", 1)
    top = []
    if len(collapsed) == 2:
        for line in collapsed[1].split("Binary Images:", 1)[0].splitlines():
            match = re.match(r"^\s+(.*?)\s{2,}(\d+)\s*$", line)
            if match:
                top.append({"symbol": match[1], "samples": int(match[2])})
    return {
        "target_pid": pid,
        "interval_ms": interval_ms,
        "thread_roots": thread_roots,
        "top_of_stack_collapsed": top,
        "interpretation": (
            "Counts are sampled wall-time stacks, including idle/waiting threads. "
            "Inclusive and recursive frames overlap; do not add them as CPU shares. "
            "Collapsed entries below five samples are omitted by Apple sample."
        ),
    }


def _runtime_identity(python: Path) -> dict:
    code = """
import hashlib, importlib, importlib.metadata, json, pathlib, platform, sys
modules = {}
for name in ('uvicorn', 'uvloop.loop', 'httptools.parser.parser', 'uvicorn_rs._native'):
    try:
        module = importlib.import_module(name)
    except ImportError:
        modules[name] = {'available': False}
        continue
    path = pathlib.Path(module.__file__).resolve()
    modules[name] = {'available': True, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
versions = {}
for name in ('uvicorn', 'uvloop', 'httptools', 'hypercorn', 'uvicorn-rs'):
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        versions[name] = None
executable = pathlib.Path(sys.executable).resolve()
print(json.dumps({'python': sys.version, 'implementation': platform.python_implementation(),
    'python_executable': str(executable), 'python_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
    'versions': versions, 'module_origins': modules}))
"""
    return json.loads(subprocess.check_output([str(python), "-c", code], cwd=ROOT, text=True))


def _preserve_identity(evidence: BenchmarkEvidence, directory: Path) -> dict:
    """Preserve the exact code and executables represented by this receipt."""
    snapshots = {}
    for name, expected in evidence.before["source_files"].items():
        destination = directory / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        if _sha256(destination) != expected:
            raise RuntimeError(f"source changed while preserving {name}")
        snapshots[name] = {"path": str(destination), "sha256": expected}
    destination = directory / "normal-native.abi3.so"
    shutil.copyfile(evidence.native, destination)
    expected = evidence.before["native_extension"]["sha256"]
    if _sha256(destination) != expected:
        raise RuntimeError("native extension changed while preserving the normal binary")
    return {"source_files": snapshots, "normal_native": {"path": str(destination), "sha256": expected}}


def _profile(args: argparse.Namespace, output: Path, receipt: dict) -> None:
    assert_clean_coverage_environment()
    if args.native_client is not None:
        native_client = args.native_client.resolve()
        if not native_client.is_file() or not os.access(native_client, os.X_OK):
            raise RuntimeError("--native-client must name an executable maintained HTTP client")
        http_bench.NATIVE_CLIENT = native_client
        receipt["client_build"] = {"method": "provided binary; no compilation in this run"}
    else:
        native_client = http_bench._build_native_client()
        receipt["client_build"] = {"method": "maintained H1 helper, before profiling; cc -O3 libcurl client"}
    if native_client is None:
        raise RuntimeError("the maintained native HTTP client requires cc and curl-config")

    saved_client = output / "httpbench"
    shutil.copy2(native_client, saved_client)
    if _sha256(saved_client) != _sha256(native_client):
        raise RuntimeError("HTTP client changed while preserving its executable")
    http_bench.NATIVE_CLIENT = saved_client
    evidence = BenchmarkEvidence(ROOT, http_bench.PYTHON, SOURCE_FILES, [saved_client])
    receipt["identity_before"] = evidence.before
    receipt["preserved"] = _preserve_identity(evidence, output)
    receipt["runtime_before"] = _runtime_identity(http_bench.PYTHON)
    server_definition = {"kind": "rust" if args.server == "uvicorn-rs" else "uvicorn", "loop": args.loop}
    if args.server == "uvicorn":
        server_definition["http"] = args.http
    server_name = f"{args.server}-{args.loop}" + (f"-{args.http}" if args.server == "uvicorn" else "")
    definition = http_bench.WORKLOADS[args.workload]
    port = http_bench._port()
    server_command = http_bench._command(server_definition, definition["app"], port)
    client_command = http_bench._client_command(port, args.duration, args.concurrency, definition["client"])
    receipt.update(
        {
            "server": server_name,
            "workload": args.workload,
            "workload_definition": definition,
            "concurrency": args.concurrency,
            "load_duration_seconds": args.duration,
            "sample_duration_seconds": args.sample_duration,
            "sample_delay_seconds": args.sample_delay,
            "sample_interval_ms": args.interval_ms,
            "warmup_duration_seconds": args.warmup,
            "commands": {"server": server_command, "client": client_command},
        }
    )
    server = client = sampler = None
    server_log = output / "server.log"
    sample_path = output / "server.sample.txt"
    client_stdout = output / "client.stdout.json"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    with (
        server_log.open("w+", encoding="utf-8") as log,
        client_stdout.open("w", encoding="utf-8") as client_out,
        (output / "client.stderr.log").open("w", encoding="utf-8") as client_err,
        (output / "sample.stdout.log").open("w", encoding="utf-8") as sample_out,
        (output / "sample.stderr.log").open("w", encoding="utf-8") as sample_err,
    ):
        try:
            server = subprocess.Popen(
                server_command, cwd=ROOT, env=env, stdout=log, stderr=log, text=True, start_new_session=True
            )
            receipt["server_pid"] = server.pid
            http_bench._wait_ready(server, port, log)
            if args.warmup:
                command = http_bench._client_command(port, args.warmup, args.concurrency, definition["client"])
                receipt["commands"]["warmup"] = command
                warmup_path = output / "warmup.stdout.json"
                with (
                    warmup_path.open("w", encoding="utf-8") as warmup_out,
                    (output / "warmup.stderr.log").open("w", encoding="utf-8") as warmup_err,
                ):
                    warmup = subprocess.run(
                        command, cwd=ROOT, stdout=warmup_out, stderr=warmup_err,
                        timeout=args.warmup + 20, text=True, check=False,
                    )
                receipt["warmup_returncode"] = warmup.returncode
                if warmup.returncode != 0:
                    raise RuntimeError("HTTP warmup client returned nonzero; see warmup.stderr.log")
                receipt["warmup_correctness"] = _client_result(warmup_path)
            identity = evidence.before_sample()
            receipt["load_started_at"] = _now()
            client = subprocess.Popen(
                client_command, cwd=ROOT, stdout=client_out, stderr=client_err,
                text=True, start_new_session=True,
            )
            time.sleep(args.sample_delay)
            if server.poll() is not None or client.poll() is not None:
                raise RuntimeError("server or load client exited before sampling began")
            sample_command = [
                str(SAMPLE), str(server.pid), str(args.sample_duration), str(args.interval_ms), "-file", str(sample_path)
            ]
            receipt["commands"]["sample"] = sample_command
            receipt["sample_started_at"] = _now()
            sampler = subprocess.Popen(
                sample_command, cwd=ROOT, stdout=sample_out, stderr=sample_err,
                text=True, start_new_session=True,
            )
            deadline = time.monotonic() + args.sample_duration + 15
            while sampler.poll() is None:
                if server.poll() is not None or client.poll() is not None:
                    raise RuntimeError("server or load client exited before Apple sample completed")
                if time.monotonic() > deadline:
                    raise TimeoutError("Apple sample did not finish within its diagnostic deadline")
                time.sleep(0.1)
            receipt["sample_finished_at"] = _now()
            receipt["sample_returncode"] = sampler.returncode
            if sampler.returncode != 0:
                raise RuntimeError("Apple sample returned nonzero; see sample.stderr.log")
            receipt["sample_summary"] = _sample_summary(sample_path, server.pid, args.interval_ms)
            client.wait(timeout=args.duration + 20)
            client_out.flush()
            receipt["load_finished_at"] = _now()
            receipt["client_returncode"] = client.returncode
            if client.returncode != 0:
                raise RuntimeError("HTTP load client returned nonzero; see client.stderr.log")
            receipt["load_correctness"] = _client_result(client_stdout)
            if server.poll() is not None:
                raise RuntimeError("server exited before graceful shutdown was requested")
            identity_check = evidence.after_sample(identity)
            receipt["measurement_identity"] = identity_check["measurement_identity"]
            receipt["identity_invalid_reasons"] = identity_check["timing_invalid_reasons"]
            if not identity_check["timing_valid"]:
                raise RuntimeError("source, native extension, or load client changed during profiling")
        finally:
            cleanup_errors = []
            for name, process in (("sample", sampler), ("client", client), ("server", server)):
                try:
                    receipt.setdefault("cleanup", {})[name] = _stop(process, graceful=name == "server")
                except (OSError, subprocess.SubprocessError) as error:
                    cleanup_errors.append(f"{name}: {type(error).__name__}: {error}")
            if cleanup_errors:
                receipt["cleanup_errors"] = cleanup_errors
            log.flush()
            log.seek(0)
            log_text = log.read()
            receipt["server_error_diagnostic"] = bool(
                re.search(r"(?m)(?:panicked at|^Traceback|^ERROR:|^uvicorn-rs: .*failed)", log_text)
            )
            receipt["runtime_after"] = _runtime_identity(http_bench.PYTHON)
            receipt["identity_after"] = evidence.snapshot()
            receipt["identity_stable"] = receipt["identity_before"] == receipt["identity_after"]
            receipt["runtime_identity_stable"] = receipt["runtime_before"] == receipt["runtime_after"]
            receipt["git"] = {
                "revision": evidence.git_revision,
                "dirty_target": evidence.dirty,
                "tracked_worktree_changes": evidence.git_changes,
                "untracked_measured_sources": evidence.untracked_sources,
            }
            receipt["artifacts"] = {
                str(path.relative_to(output)): {"path": str(path), "sha256": _sha256(path)}
                for path in sorted(output.glob("*"))
                if path.is_file() and path.name != "profile-receipt.json"
            }
    shutdown = receipt.get("cleanup", {}).get("server")
    if shutdown is None or not shutdown["graceful"]:
        raise RuntimeError("server did not exit successfully after its initial SIGINT")
    if receipt.get("cleanup_errors"):
        raise RuntimeError("a profiling subprocess could not be reaped")
    if receipt["server_error_diagnostic"]:
        raise RuntimeError("server emitted an error or panic diagnostic; see server.log")
    if not receipt["identity_stable"] or not receipt["runtime_identity_stable"]:
        raise RuntimeError("source, binary, or Python package identity changed during profiling")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", choices=("uvicorn-rs", "uvicorn"), default="uvicorn-rs")
    parser.add_argument("--loop", choices=("asyncio", "uvloop"), default="uvloop")
    parser.add_argument("--http", choices=("h11", "httptools"), default="httptools", help="Uvicorn HTTP implementation")
    parser.add_argument("--workload", choices=PROFILE_WORKLOADS, default="fixed")
    parser.add_argument("--duration", type=float, default=10.0, help="load duration in seconds")
    parser.add_argument("--sample-duration", type=int, default=6, help="Apple sample duration in seconds")
    parser.add_argument("--sample-delay", type=float, default=1.0, help="delay after load starts, in seconds")
    parser.add_argument("--interval-ms", type=int, default=1, help="Apple sample interval in milliseconds")
    parser.add_argument("--warmup", type=float, default=1.0)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--native-client", type=Path, help="existing maintained HTTP client; skip compilation")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory for receipt and diagnostic artifacts")
    args = parser.parse_args()
    if platform.system() != "Darwin" or not SAMPLE.is_file():
        parser.error("this diagnostic driver requires macOS /usr/bin/sample")
    if not http_bench.PYTHON.is_file():
        parser.error("create .venv and install the benchmark dependency group first")
    if (
        not all(math.isfinite(value) for value in (args.duration, args.sample_delay, args.warmup))
        or args.sample_duration < 1 or args.interval_ms < 1 or args.concurrency < 1
        or args.sample_delay < 0 or args.warmup < 0
        or args.duration < args.sample_delay + args.sample_duration + 2
    ):
        parser.error("use finite nonnegative delays, positive sample/concurrency values, and at least two seconds of load after sampling")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt_path = output / "profile-receipt.json"
    receipt = {
        "schema_version": 1,
        "status": "running",
        "started_at": _now(),
        "profiling_only": True,
        "timing_valid": False,
        "performance_evidence_status": "not_applicable",
        "note": (
            "Apple sample perturbs scheduling. Raw client JSON timing fields are retained "
            "only as diagnostic artifacts and must not enter benchmark summaries or speed claims."
        ),
        "correctness_gate": "every response status and complete payload exactly matches the maintained workload oracle",
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    _write_receipt(receipt_path, receipt)
    returncode = 0
    try:
        _profile(args, output, receipt)
        receipt["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        receipt["status"] = "failed"
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        returncode = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        receipt["finished_at"] = _now()
        _write_receipt(receipt_path, receipt)
    print(json.dumps({"status": receipt["status"], "profiling_only": True, "receipt": str(receipt_path)}), flush=True)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
