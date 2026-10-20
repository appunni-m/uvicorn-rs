"""Measure event-loop, process, and per-thread CPU during FastAPI workloads.

This diagnostic-only runner uses the normal HTTP benchmark client and source
identity gates. It measures the server's Python main/event-loop thread CPU
immediately before the measured load, whole-process CPU, and per-thread CPU
over the same signal window. Linux reads procfs task counters; macOS uses Mach
thread snapshots. The resulting rows are diagnostic-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_http_category_bench as http_bench  # noqa: E402
from benchmark_evidence import BenchmarkEvidence  # noqa: E402


BOOTSTRAP = r'''"""Signal-gated CPU accounting bootstrap for one server process."""
import ctypes
import json
import os
import resource
import signal
import sys
import threading
import time
from pathlib import Path

if os.environ.get("UVICORN_RS_LOOP_CPU_PROFILE") == "1":
    _output = Path(os.environ["UVICORN_RS_LOOP_CPU_PROFILE_OUT"])
    class _ThreadCpuSample(ctypes.Structure):
        _fields_ = [
            ("thread_id", ctypes.c_uint64),
            ("user_time_ns", ctypes.c_uint64),
            ("system_time_ns", ctypes.c_uint64),
            ("name", ctypes.c_char * 64),
        ]

    if sys.platform == "darwin":
        _thread_cpu_backend = "macos-mach-thread-info"
        _thread_cpu_library = ctypes.CDLL(os.environ["UVICORN_RS_THREAD_CPU_LIBRARY"])
        _thread_cpu_snapshot_fn = _thread_cpu_library.uvicorn_rs_thread_cpu_snapshot
        _thread_cpu_snapshot_fn.argtypes = [ctypes.POINTER(_ThreadCpuSample), ctypes.c_int]
        _thread_cpu_snapshot_fn.restype = ctypes.c_int

        def _thread_cpu_snapshot():
            capacity = 4096
            records = (_ThreadCpuSample * capacity)()
            count = _thread_cpu_snapshot_fn(records, capacity)
            if count < 0:
                return None
            return {
                int(records[index].thread_id): {
                    "cpu_time_ns": (
                        int(records[index].user_time_ns)
                        + int(records[index].system_time_ns)
                    ),
                    "user_time_ns": int(records[index].user_time_ns),
                    "system_time_ns": int(records[index].system_time_ns),
                    "runqueue_wait_ns": None,
                    "timeslices": None,
                    "name": bytes(records[index].name).decode("utf-8", errors="replace"),
                }
                for index in range(count)
            }
    elif sys.platform.startswith("linux"):
        _thread_cpu_backend = "linux-procfs-schedstat"
        _clock_ticks_per_second = os.sysconf("SC_CLK_TCK")

        def _thread_cpu_snapshot():
            records = {}
            tasks = Path("/proc/self/task")
            try:
                thread_directories = list(tasks.iterdir())
            except OSError:
                return None
            for directory in thread_directories:
                try:
                    stat = (directory / "stat").read_text(encoding="ascii")
                    comm_end = stat.rfind(")")
                    if comm_end < 0:
                        continue
                    fields = stat[comm_end + 2 :].split()
                    user_ticks = int(fields[11])
                    system_ticks = int(fields[12])
                    schedstat = (directory / "schedstat").read_text(
                        encoding="ascii"
                    ).split()
                    cpu_time_ns = int(schedstat[0])
                    runqueue_wait_ns = int(schedstat[1])
                    timeslices = int(schedstat[2])
                    name = (directory / "comm").read_text(encoding="utf-8").strip()
                    thread_id = int(directory.name)
                except (OSError, UnicodeError, ValueError, IndexError):
                    continue
                records[thread_id] = {
                    "cpu_time_ns": cpu_time_ns,
                    "user_time_ns": (
                        user_ticks * 1_000_000_000 // _clock_ticks_per_second
                    ),
                    "system_time_ns": (
                        system_ticks * 1_000_000_000 // _clock_ticks_per_second
                    ),
                    "runqueue_wait_ns": runqueue_wait_ns,
                    "timeslices": timeslices,
                    "name": name,
                }
            return records or None
    else:
        _thread_cpu_backend = "unsupported"

        def _thread_cpu_snapshot():
            return None

    _started = False
    _thread_cpu_start = 0
    _process_cpu_start = (0.0, 0.0)
    _wall_start = 0
    _thread_cpu_start_snapshot = None
    _event_loop_native_id = None

    def _cpu_times():
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_utime, usage.ru_stime

    def _start_profile(_signum, _frame):
        global _started, _thread_cpu_start, _process_cpu_start, _wall_start
        global _thread_cpu_start_snapshot, _event_loop_native_id
        if _started:
            return
        route_module = sys.modules.get("examples.profile_fastapi_cpu")
        if route_module is not None:
            route_module._start_measurement()
        _thread_cpu_start_snapshot = _thread_cpu_snapshot()
        _event_loop_native_id = threading.get_native_id()
        _thread_cpu_start = time.thread_time_ns()
        _process_cpu_start = _cpu_times()
        _wall_start = time.monotonic_ns()
        _started = True

    def _stop_profile(_signum, _frame):
        global _started
        if not _started:
            return
        route_module = sys.modules.get("examples.profile_fastapi_cpu")
        if route_module is not None:
            route_module._stop_measurement()
        thread_cpu_end = _thread_cpu_snapshot()
        python_threads = {
            thread.native_id: thread.name
            for thread in threading.enumerate()
            if thread.native_id is not None
        }
        thread_cpu_ns = max(0, time.thread_time_ns() - _thread_cpu_start)
        process_cpu_end = _cpu_times()
        wall_ns = max(0, time.monotonic_ns() - _wall_start)
        _started = False

        thread_cpu_seconds = thread_cpu_ns / 1_000_000_000
        process_cpu_seconds = (
            process_cpu_end[0] - _process_cpu_start[0]
            + process_cpu_end[1] - _process_cpu_start[1]
        )
        per_thread_cpu = []
        if _thread_cpu_start_snapshot is not None and thread_cpu_end is not None:
            for thread_id, ending in thread_cpu_end.items():
                beginning = _thread_cpu_start_snapshot.get(thread_id, {})
                cpu_ns = max(
                    0,
                    ending["cpu_time_ns"] - beginning.get("cpu_time_ns", 0),
                )
                user_ns = max(
                    0, ending["user_time_ns"] - beginning.get("user_time_ns", 0)
                )
                system_ns = max(
                    0,
                    ending["system_time_ns"] - beginning.get("system_time_ns", 0),
                )
                wait_start = beginning.get("runqueue_wait_ns")
                wait_end = ending["runqueue_wait_ns"]
                runqueue_wait_ns = (
                    max(0, wait_end - wait_start)
                    if wait_start is not None and wait_end is not None
                    else None
                )
                slices_start = beginning.get("timeslices")
                slices_end = ending["timeslices"]
                timeslices = (
                    max(0, slices_end - slices_start)
                    if slices_start is not None and slices_end is not None
                    else None
                )
                name = (
                    ending["name"]
                    or beginning.get("name")
                    or python_threads.get(thread_id, "")
                )
                if thread_id == _event_loop_native_id:
                    role = "python-event-loop-thread"
                elif name.startswith("tokio"):
                    role = "tokio-named-thread"
                elif thread_id in python_threads:
                    role = "python-thread"
                else:
                    role = "native-unclassified-thread"
                per_thread_cpu.append({
                    "thread_id": thread_id,
                    "thread_name": name,
                    "role": role,
                    "total_cpu_ns": cpu_ns,
                    "user_cpu_ns": user_ns,
                    "system_cpu_ns": system_ns,
                    "runqueue_wait_ns": runqueue_wait_ns,
                    "timeslices": timeslices,
                })
            per_thread_cpu.sort(key=lambda item: item["total_cpu_ns"], reverse=True)
        report = {
            "schema": "uvicorn-rs-python-loop-cpu-profile@3",
            "profiled": True,
            "timer": "time.thread_time_ns; CPU on the Python event-loop thread",
            "thread_snapshot_backend": _thread_cpu_backend,
            "interval_seconds": wall_ns / 1_000_000_000,
            "event_loop_thread_cpu_seconds": thread_cpu_seconds,
            "process_cpu_seconds": process_cpu_seconds,
            "other_process_thread_cpu_seconds": max(
                0.0, process_cpu_seconds - thread_cpu_seconds
            ),
            "event_loop_native_thread_id": _event_loop_native_id,
            "thread_snapshot_start_count": (
                len(_thread_cpu_start_snapshot) if _thread_cpu_start_snapshot is not None else None
            ),
            "thread_snapshot_end_count": (
                len(thread_cpu_end) if thread_cpu_end is not None else None
            ),
            "thread_snapshot_error": (
                _thread_cpu_start_snapshot is None or thread_cpu_end is None
            ),
            "thread_cpu": per_thread_cpu,
            "thread_cpu_sum_seconds": sum(
                item["total_cpu_ns"] for item in per_thread_cpu
            ) / 1_000_000_000,
            "interpretation": (
                "The main-thread timer measures Python event-loop thread CPU, including any "
                "native calls made on that thread. Process CPU includes every server thread. "
                "OS thread snapshots add CPU time by thread ID and name; they are not a "
                "function-level Rust profile, and threads that exit before the final snapshot "
                "are not included in the per-thread list. Linux schedstat provides CPU runtime "
                "and runqueue wait in nanosecond units; its user/system split from task stat is "
                "quantized to scheduler ticks. Runqueue wait is time queued for CPU, not I/O wait."
            ),
        }
        _output.parent.mkdir(parents=True, exist_ok=True)
        temporary = _output.with_suffix(_output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(_output)

    signal.signal(signal.SIGUSR1, _start_profile)
    signal.signal(signal.SIGUSR2, _stop_profile)
'''


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workloads",
        nargs="+",
        choices=sorted(http_bench.WORKLOADS),
        default=[
            "fastapi-validated-route",
            "fastapi-request-upload",
            "fastapi-python-cpu",
            "fastapi-many-response-chunks",
        ],
    )
    parser.add_argument(
        "--servers",
        nargs="+",
        choices=sorted(http_bench.SERVERS),
        default=["uvicorn-asyncio-httptools", "uvicorn-rs-asyncio"],
    )
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--warmup", type=float, default=1.0)
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument(
        "--require-runtime-diagnostics",
        action="store_true",
        help=(
            "require runtime-diagnostics counters in the Rust extension; "
            "the resulting profile remains diagnostic-only"
        ),
    )
    parser.add_argument(
        "--native-stack-sampling",
        action="store_true",
        help="collect macOS sample(1) thread stacks during each measured server load",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if not (sys.platform == "darwin" or sys.platform.startswith("linux")):
        parser.error("per-thread CPU snapshots require Linux procfs or macOS Mach thread_info")
    if not all(name.startswith("fastapi-") for name in args.workloads):
        parser.error("only the ordinary FastAPI workloads are supported")
    if not any(name.startswith("uvicorn-rs-") for name in args.servers) or not any(
        name.startswith("uvicorn-") for name in args.servers
    ):
        parser.error("select at least one Uvicorn and one uvicorn-rs server")
    if args.duration <= 0 or args.warmup < 0 or args.concurrency < 1 or args.repetitions < 1:
        parser.error("duration, concurrency, and repetitions must be positive; warmup cannot be negative")
    native_sample_command = shutil.which("sample") if args.native_stack_sampling else None
    if args.native_stack_sampling and native_sample_command is None:
        parser.error("--native-stack-sampling requires the macOS sample utility")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    profiles_dir = output_dir / "profiles"
    profiles_dir.mkdir()
    sources_dir = output_dir / "sources"
    sources_dir.mkdir()
    bootstrap_dir = output_dir / "bootstrap"
    bootstrap_dir.mkdir()
    thread_cpu_library = None
    thread_cpu_source = None
    if sys.platform == "darwin":
        thread_cpu_library = bootstrap_dir / "libuvicorn_rs_thread_cpu.dylib"
        thread_cpu_source = ROOT / "scripts" / "macos_thread_cpu.c"
    profile_script_source = Path(__file__).resolve()
    preserved_sources = {}
    sources_to_preserve = [profile_script_source]
    if thread_cpu_source is not None:
        sources_to_preserve.append(thread_cpu_source)
    for source in sources_to_preserve:
        destination = sources_dir / source.name
        shutil.copyfile(source, destination)
        expected_hash = _sha256(source)
        if _sha256(destination) != expected_hash:
            raise RuntimeError(f"diagnostic source changed while preserving {source.name}")
        preserved_sources[source.name] = {
            "path": str(destination.relative_to(output_dir)),
            "sha256": expected_hash,
        }
    if thread_cpu_library is not None and thread_cpu_source is not None:
        subprocess.run(
            ["cc", "-O2", "-dynamiclib", "-o", str(thread_cpu_library), str(thread_cpu_source)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    bootstrap_path = bootstrap_dir / "sitecustomize.py"
    bootstrap_path.write_text(BOOTSTRAP, encoding="utf-8")

    existing_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(bootstrap_dir) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    if thread_cpu_library is not None:
        os.environ["UVICORN_RS_THREAD_CPU_LIBRARY"] = str(thread_cpu_library)

    current_sample: dict[str, str | int] = {}
    label_sample = BenchmarkEvidence.label_sample
    owned_process = http_bench.owned_process
    collect_bounded_client = http_bench.collect_bounded_client

    def label_current_sample(
        evidence: BenchmarkEvidence, workload: str, server: str, repetition: int
    ) -> None:
        current_sample.update(
            workload=workload,
            server=server,
            repetition=repetition,
        )
        label_sample(evidence, workload, server, repetition)

    def start_profiled_server(argv, **kwargs):
        if len(argv) >= 3 and argv[1:3] in (["-m", "uvicorn"], ["-m", "uvicorn_rs"]):
            if not current_sample:
                raise RuntimeError("benchmark server started before its sample identity was recorded")
            name = (
                f"{current_sample['workload']}-{current_sample['server']}-"
                f"repeat-{current_sample['repetition']}"
            )
            profile_path = profiles_dir / f"{name}.json"
            if profile_path.exists():
                raise RuntimeError(f"refusing to overwrite Python profile: {profile_path}")
            server_env = dict(kwargs.get("env") or os.environ)
            server_env["UVICORN_RS_LOOP_CPU_PROFILE"] = "1"
            server_env["UVICORN_RS_LOOP_CPU_PROFILE_OUT"] = str(profile_path)
            if current_sample["workload"] == "fastapi-python-cpu":
                server_env["UVICORN_RS_CPU_ROUTE_PROFILE_OUT"] = str(
                    profiles_dir / f"{name}.route.json"
                )
            kwargs["env"] = server_env
        return owned_process(argv, **kwargs)

    def collect_with_profile(client, seconds, server, monitor, *positional, **keywords):
        profile_path = None
        stack_sample_path = None
        stack_sample_log_path = None
        stack_sample_process = None
        stack_sample_log = None
        if current_sample:
            name = (
                f"{current_sample['workload']}-{current_sample['server']}-"
                f"repeat-{current_sample['repetition']}"
            )
            profile_path = profiles_dir / f"{name}.json"
            server.send_signal(signal.SIGUSR1)
            if native_sample_command is not None:
                stack_sample_path = profiles_dir / f"{name}.sample.txt"
                stack_sample_log_path = profiles_dir / f"{name}.sample.log"
                if stack_sample_path.exists() or stack_sample_log_path.exists():
                    raise RuntimeError(
                        f"refusing to overwrite native stack profile for {name}"
                    )
                stack_sample_log = stack_sample_log_path.open("x", encoding="utf-8")
        try:
            if stack_sample_log is not None:
                stack_sample_process = subprocess.Popen(
                    [
                        native_sample_command,
                        str(server.pid),
                        str(seconds),
                        "1",
                        "-mayDie",
                        "-fullPaths",
                        "-file",
                        str(stack_sample_path),
                    ],
                    stdout=stack_sample_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            return collect_bounded_client(
                client, seconds, server, monitor, *positional, **keywords
            )
        finally:
            stack_sample_error = None
            if stack_sample_process is not None:
                try:
                    stack_sample_process.wait(timeout=seconds + 10.0)
                except subprocess.TimeoutExpired:
                    stack_sample_process.terminate()
                    try:
                        stack_sample_process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        stack_sample_process.kill()
                        stack_sample_process.wait()
                    stack_sample_error = (
                        f"macOS sample exceeded its bounded wait: {stack_sample_log_path}"
                    )
                if stack_sample_process.returncode != 0 and stack_sample_error is None:
                    stack_sample_error = (
                        f"macOS sample exited {stack_sample_process.returncode}; "
                        f"see {stack_sample_log_path}"
                    )
            if stack_sample_log is not None:
                stack_sample_log.close()
            if profile_path is not None:
                if server.poll() is None:
                    server.send_signal(signal.SIGUSR2)
                deadline = time.monotonic() + 3.0
                while not profile_path.is_file() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not profile_path.is_file():
                    raise RuntimeError(
                        f"server did not write its signal-gated Python profile: {profile_path}"
                    )
                if stack_sample_path is not None and not stack_sample_path.is_file():
                    stack_sample_error = (
                        f"macOS sample did not write its stack profile: {stack_sample_path}"
                    )
            if stack_sample_error is not None:
                raise RuntimeError(stack_sample_error)

    BenchmarkEvidence.label_sample = label_current_sample
    http_bench.owned_process = start_profiled_server
    http_bench.collect_bounded_client = collect_with_profile
    if "fastapi-python-cpu" in args.workloads:
        http_bench.WORKLOADS["fastapi-python-cpu"] = {
            **http_bench.WORKLOADS["fastapi-python-cpu"],
            "app": "examples.profile_fastapi_cpu:app",
        }
    report_path = output_dir / "http1-benchmark.json"
    sys.argv = [
        str(ROOT / "scripts" / "run_http_category_bench.py"),
        "--workloads",
        *args.workloads,
        "--servers",
        *args.servers,
        "--duration",
        str(args.duration),
        "--warmup",
        str(args.warmup),
        "--concurrency",
        str(args.concurrency),
        "--repetitions",
        str(args.repetitions),
        "--output",
        str(report_path),
    ]
    if args.require_runtime_diagnostics:
        sys.argv.append("--require-runtime-diagnostics")
    try:
        http_bench.main()
    finally:
        BenchmarkEvidence.label_sample = label_sample
        http_bench.owned_process = owned_process
        http_bench.collect_bounded_client = collect_bounded_client

    benchmark = json.loads(report_path.read_text(encoding="utf-8"))
    profiles = []
    for row in benchmark["rows"]:
        name = f"{row['workload']}-{row['server']}-repeat-{row['repetition']}"
        profile_path = profiles_dir / f"{name}.json"
        if not profile_path.is_file():
            raise RuntimeError(f"missing server profile for completed row: {profile_path}")
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if profile.get("thread_snapshot_error"):
            raise RuntimeError(f"per-thread CPU snapshots failed: {profile_path}")
        route_profile = None
        if row["workload"] == "fastapi-python-cpu":
            route_path = profiles_dir / f"{name}.route.json"
            if not route_path.is_file():
                raise RuntimeError(f"missing synchronous-route CPU receipt: {route_path}")
            route_profile = json.loads(route_path.read_text(encoding="utf-8"))
        profiles.append(
            {
                "workload": row["workload"],
                "server": row["server"],
                "repetition": row["repetition"],
                "completed_requests": row["requests"],
                "correctness_failures": row["failures"],
                "host_and_identity_guard_passed_before_diagnostic_label": row[
                    "timing_valid"
                ],
                "profile_path": str(profile_path.relative_to(output_dir)),
                "profile_sha256": _sha256(profile_path),
                "event_loop_thread_cpu_seconds": profile[
                    "event_loop_thread_cpu_seconds"
                ],
                "process_cpu_seconds": profile["process_cpu_seconds"],
                "other_process_thread_cpu_seconds": profile[
                    "other_process_thread_cpu_seconds"
                ],
                "thread_snapshot_backend": profile["thread_snapshot_backend"],
                "thread_cpu": profile["thread_cpu"],
                "thread_cpu_sum_seconds": profile["thread_cpu_sum_seconds"],
                "thread_snapshot_error": profile["thread_snapshot_error"],
                "sync_route_cpu": route_profile,
                "native_stack_profile_path": (
                    str((profiles_dir / f"{name}.sample.txt").relative_to(output_dir))
                    if native_sample_command is not None
                    else None
                ),
                "native_stack_profile_sha256": (
                    _sha256(profiles_dir / f"{name}.sample.txt")
                    if native_sample_command is not None
                    else None
                ),
                "native_stack_profile_log_path": (
                    str((profiles_dir / f"{name}.sample.log").relative_to(output_dir))
                    if native_sample_command is not None
                    else None
                ),
            }
        )

    benchmark["observed_unrankable_summaries_median"] = benchmark.pop(
        "summaries_median", {}
    )
    benchmark["summaries_median"] = {}
    for row in benchmark["rows"]:
        row["timing_valid"] = False
        row.setdefault("timing_invalid_reasons", []).append(
            "signal_gated_thread_cpu_diagnostic"
        )
        row["performance_evidence_status"] = "diagnostic_only"
    benchmark["performance_evidence_status"] = "diagnostic_only"
    benchmark["timing_valid"] = False
    checkpoint_path = report_path.with_suffix(".jsonl")
    checkpoint_path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in benchmark["rows"]),
        encoding="utf-8",
    )
    report_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    metadata_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".meta.json")
    if metadata_path.is_file():
        checkpoint_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        checkpoint_metadata["performance_evidence_status"] = "diagnostic_only"
        checkpoint_metadata["completion_state"] = (
            "completed diagnostic-only benchmark; timing rows are not rankable"
        )
        metadata_path.write_text(
            json.dumps(checkpoint_metadata, indent=2) + "\n", encoding="utf-8"
        )

    manifest = {
        "schema": "uvicorn-rs-fastapi-loop-cpu-profiles@3",
        "application": "upstream FastAPI with its ordinary Starlette/Pydantic dependencies",
        "alternate_frameworks_used": False,
        "diagnostic_only": True,
        "runtime_diagnostics_required": args.require_runtime_diagnostics,
        "diagnostic_method": (
            "time.thread_time_ns and RUSAGE_SELF are signal-gated around the measured client load. "
            "RUSAGE_SELF captures process CPU. Linux schedstat supplies per-thread CPU runtime, "
            "runqueue wait and timeslices; task stat adds tick-quantized user/system times. "
            "macOS Mach supplies per-thread user/system CPU times and pthread names. "
            "The client checks each response body. Timing rows are diagnostic-only."
            + (
                " macOS sample(1) also records sampled call stacks for the server process during "
                "the load; the profile is for call-site context and is not rankable timing evidence."
                if native_sample_command is not None
                else ""
            )
        ),
        "native_stack_sampler": (
            {
                "command": native_sample_command,
                "sampling_interval_ms": 1,
                "profile_format": "macOS sample(1) text call tree",
                "interpretation": (
                    "wall-time thread stack samples include active and waiting stacks; "
                    "they do not quantify per-function CPU; symbol availability depends "
                    "on the native build"
                ),
            }
            if native_sample_command is not None
            else None
        ),
        "profile_bootstrap_sha256": _sha256(bootstrap_path),
        "profile_sources": preserved_sources,
        "thread_snapshot_backend": (
            "linux-procfs-schedstat"
            if sys.platform.startswith("linux")
            else "macos-mach-thread-info"
        ),
        "thread_cpu_helper_source": (
            str(thread_cpu_source.relative_to(ROOT)) if thread_cpu_source is not None else None
        ),
        "thread_cpu_helper_source_sha256": (
            _sha256(thread_cpu_source) if thread_cpu_source is not None else None
        ),
        "thread_cpu_helper_binary_sha256": (
            _sha256(thread_cpu_library) if thread_cpu_library is not None else None
        ),
        "diagnostic_fastapi_wrapper": (
            "examples/profile_fastapi_cpu.py"
            if "fastapi-python-cpu" in args.workloads
            else None
        ),
        "diagnostic_fastapi_wrapper_sha256": (
            _sha256(ROOT / "examples" / "profile_fastapi_cpu.py")
            if "fastapi-python-cpu" in args.workloads
            else None
        ),
        "benchmark_report": str(report_path.relative_to(output_dir)),
        "workloads": args.workloads,
        "servers": args.servers,
        "duration_seconds": args.duration,
        "warmup_seconds": args.warmup,
        "concurrency": args.concurrency,
        "repetitions": args.repetitions,
        "profiles": profiles,
        "limitations": [
            "Event-loop-thread CPU includes Python and native calls on that thread.",
            (
                "Per-thread CPU time does not identify functions; pair it with permitted "
                "on-CPU profiles for call-site context."
            ),
            (
                "macOS sample(1) captures active and waiting thread stacks; stack counts "
                "are not per-function CPU shares, and missing symbols limit call-site attribution."
            ),
            "Threads that exit before the ending snapshot are absent from the per-thread delta list.",
            (
                "Linux schedstat CPU runtime and runqueue wait use nanosecond units; task stat "
                "user/system components are quantized to scheduler ticks."
            ),
            (
                "Linux thread names come from /proc task comm and may be truncated; runqueue "
                "wait is CPU scheduling delay, not I/O wait."
            ),
            "Other-thread CPU can include synchronous FastAPI worker threads and Rust runtime threads; only the CPU route has a separate function timer.",
            "The synchronous route receipt measures endpoint CPU, not response validation or transport.",
            "Use the separate normal-build matrix for throughput, latency, and CPU-per-request comparisons.",
        ],
    }
    (output_dir / "profile-summary.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output_dir / 'profile-summary.json'}")


if __name__ == "__main__":
    main()
