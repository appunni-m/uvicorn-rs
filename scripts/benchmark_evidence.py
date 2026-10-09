"""Identity and resource evidence shared by the maintained benchmark runners.

This supplements the existing category JSON format. Raw invalid samples remain
visible; only samples with stable identities and no measured host contention
can contribute to the category's timing medians. Dirty checkouts are explicitly
local, provisional measurements rather than release performance proof.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import socket
import ssl
import statistics
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psutil

try:
    import resource
except ImportError:
    resource = None


FASTAPI_BENCHMARK_DISTRIBUTIONS = {
    "fastapi": ["fastapi"],
    "starlette": ["starlette"],
    "pydantic": ["pydantic"],
    "pydantic-core": ["pydantic_core"],
    "annotated-doc": ["annotated_doc"],
    "annotated-types": ["annotated_types"],
    "typing-inspection": ["typing_inspection"],
    "typing-extensions": ["typing_extensions"],
    "opentelemetry-api": ["opentelemetry"],
    "anyio": ["anyio"],
    "idna": ["idna"],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def median_valid(rows: list[dict], metric: str):
    values = [
        row[metric]
        for row in rows
        if row.get("timing_valid", True) and row.get(metric) is not None
    ]
    repetitions = {row["repetition"] for row in rows if row.get("timing_valid", True) and row.get(metric) is not None}
    return statistics.median(values) if len(repetitions) >= 3 else None


def assert_clean_coverage_environment() -> None:
    armed = [
        name
        for name in os.environ
        if name.startswith("UVICORN_RS_COVERAGE_")
        or name in {"LLVM_PROFILE_FILE", "CARGO_LLVM_COV", "CARGO_LLVM_COV_TARGET_DIR"}
    ]
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        value = os.environ.get(name, "").lower()
        if "coverage" in value or "llvm-cov" in value or "instrument-coverage" in value:
            armed.append(name)
    if armed:
        raise RuntimeError(
            "benchmark requires an uninstrumented environment; unset "
            + ", ".join(sorted(set(armed)))
        )


def owned_process(argv, **kwargs):
    """Start a benchmark-owned session and retain exact process identities."""
    started = time.monotonic()
    process = subprocess.Popen(argv, start_new_session=os.name == "posix", **kwargs)
    process.benchmark_started = started
    process.benchmark_pid_identities = {}
    _refresh_owned(process)
    return process


def _refresh_owned(process) -> None:
    """Discover descendants only while the original parent identity is live."""
    identities = getattr(process, "benchmark_pid_identities", None)
    if identities is None:
        identities = process.benchmark_pid_identities = {}
    try:
        root = psutil.Process(process.pid)
        created = root.create_time()
        previous = identities.get(root.pid)
        if previous is not None and previous != created:
            return
        if previous is None and process.poll() is not None:
            return
        identities[root.pid] = created
        if root.status() == psutil.STATUS_ZOMBIE:
            return
        for child in root.children(recursive=True):
            try:
                identities[child.pid] = child.create_time()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        return


def _owned_alive(process) -> list[int]:
    alive = []
    for pid, created in process.benchmark_pid_identities.items():
        try:
            current = psutil.Process(pid)
            if current.create_time() == created and current.status() != psutil.STATUS_ZOMBIE:
                alive.append(pid)
        except psutil.NoSuchProcess:
            pass
    return alive


def _signal_owned_pid(process, pid: int, sig) -> None:
    created = process.benchmark_pid_identities[pid]
    try:
        current = psutil.Process(pid)
        if current.create_time() != created or current.status() == psutil.STATUS_ZOMBIE:
            return
        if pid == process.pid:
            if process.poll() is None:
                process.send_signal(sig)
        else:
            current.send_signal(sig)
    except psutil.NoSuchProcess:
        pass


def stop_owned(process, *, graceful: bool = False) -> dict:
    """Verify and signal only captured owned PIDs, with bounded escalation."""
    if process is None:
        return {"returncode": None, "forced": False, "owned_live_pids": []}
    _refresh_owned(process)
    stages = [(signal.SIGINT, 5.0), (signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)] if graceful else [
        (signal.SIGTERM, 3.0), (signal.SIGKILL, 3.0)
    ]
    forced = False
    for index, (sig, seconds) in enumerate(stages):
        alive = _owned_alive(process)
        if not alive:
            break
        forced |= index > 0
        if graceful and index == 0:
            # The supervisor propagates its own shutdown event to workers.
            # Direct worker SIGINT bypasses Hypercorn's graceful protocol.
            if process.pid in alive:
                _signal_owned_pid(process, process.pid, sig)
        else:
            for pid in sorted(alive, key=lambda pid: pid == process.pid):
                _signal_owned_pid(process, pid, sig)
        deadline = time.monotonic() + seconds
        while _owned_alive(process) and time.monotonic() < deadline:
            _refresh_owned(process)
            process.poll()
            time.sleep(0.05)
    live = _owned_alive(process)
    if live:
        raise RuntimeError(f"benchmark-owned process identities {live} survived bounded cleanup")
    process.wait(timeout=1)
    return {
        "returncode": process.returncode, "forced": forced, "owned_live_pids": [],
        "owned_process_identities": [
            {"pid": pid, "create_time": created}
            for pid, created in sorted(process.benchmark_pid_identities.items())
        ],
        "cleanup_verification": "original root reaped; tracked original descendant identities exited or are zombies; recycled PIDs ignored",
    }


def stop_client(process) -> None:
    """Reap the entire client group after monitoring or report decoding fails."""
    stop_owned(process)


def check_server_alive(server) -> None:
    _refresh_owned(server)
    if server.poll() is not None:
        raise RuntimeError(f"server exited during benchmark (returncode={server.returncode})")


def wait_tls_ready(server, port: int, log, certfile: Path, *, seconds: float) -> None:
    """Verify TLS/H1 readiness with the exact shared FastAPI fixed response."""
    context = ssl.create_default_context(cafile=str(certfile))
    context.set_alpn_protocols(["http/1.1"])
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        check_server_alive(server)
        try:
            raw = socket.create_connection(("127.0.0.1", port), timeout=min(2.0, deadline - time.monotonic()))
        except ConnectionRefusedError:
            time.sleep(0.05)
            continue
        with raw:
            with context.wrap_socket(raw, server_hostname="localhost") as tls:
                if tls.selected_alpn_protocol() != "http/1.1":
                    raise RuntimeError("TLS readiness did not negotiate HTTP/1.1")
                tls.sendall(b"GET /fixed HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                response = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("TLS readiness exceeded its absolute wall deadline")
                    tls.settimeout(min(2.0, remaining))
                    chunk = tls.recv(4096)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if len(response) > 65536:
                        raise RuntimeError("TLS readiness response exceeded the bounded header limit")
                if not response.startswith(b"HTTP/1.1 200 ") or not response.endswith(b"\r\n\r\nHello World!"):
                    raise RuntimeError("TLS readiness GET did not return the exact FastAPI fixed response")
                check_server_alive(server)
                return
    log.flush()
    raise TimeoutError(f"server did not complete TLS readiness within {seconds:g}s; log={log.name}")


def run_bounded_client(argv, seconds: float, server, *, cwd: Path):
    """Run a warmup with a wall deadline independent of the client's protocol."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("client duration must be finite and positive")
    check_server_alive(server)
    process = owned_process(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = process.benchmark_started + seconds + 30
    try:
        while True:
            check_server_alive(server)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"warmup client exceeded its {seconds + 30:g}s absolute wall limit")
            try:
                stdout, stderr = process.communicate(timeout=min(0.25, remaining))
                check_server_alive(server)
                return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    finally:
        stop_client(process)


def collect_bounded_client(process, seconds: float, server, monitor, *, interval: float = 0.25):
    """Monitor a load client until completion or its absolute wall deadline."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("client duration must be finite and positive")
    deadline = process.benchmark_started + seconds + 30
    while process.poll() is None:
        check_server_alive(server)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"load client exceeded its {seconds + 30:g}s absolute wall limit")
        _refresh_owned(process)
        time.sleep(min(interval, remaining))
        monitor.sample()
    check_server_alive(server)
    stdout, stderr = process.communicate(timeout=max(0.001, deadline - time.monotonic()))
    return stdout, stderr


def finalize_server(process, log, *, permit_app_error: bool = False) -> dict:
    """Require a live server, clean graceful exit, and no unexpected panic hook."""
    check_server_alive(process)
    shutdown = stop_owned(process, graceful=True)
    log.flush()
    log.seek(0)
    output = log.read()
    panic = re.search(r"(?m)^thread [^\n]*panicked at|^fatal runtime error:", output)
    unexpected_python_error = not permit_app_error and (
        "Traceback (most recent call last):" in output or "Task exception was never retrieved" in output
    )
    native_error_lines = [
        line for line in output.splitlines()
        if line.startswith("uvicorn-rs:") and re.search(r"\b(failed|exceeded|aborting)\b|does not support lifespan", line)
        and not (permit_app_error and line == "uvicorn-rs: ASGI request failed: RuntimeError: benchmark exception path")
    ]
    if shutdown["forced"] or shutdown["returncode"] != 0 or panic or unexpected_python_error or native_error_lines:
        raise RuntimeError(
            f"server lifecycle/diagnostic gate failed: shutdown={shutdown}, "
            f"unexpected_panic={bool(panic)}, unexpected_python_error={unexpected_python_error}; "
            f"unexpected_native_errors={native_error_lines[:3]}; "
            f"log={log.name}"
        )
    return {
        "server_shutdown": shutdown,
        "server_log": {"path": str(log.name), "sha256": _sha256(Path(log.name))},
        "server_lifecycle_gate": "passed",
        "unexpected_panic_events": 0,
        "unexpected_native_errors": 0,
    }


class BenchmarkEvidence:
    """Bind samples to the files and binaries present before execution."""

    def __init__(
        self,
        root: Path,
        python: Path,
        source_paths: list[str],
        clients: list[Path],
        *,
        allow_runtime_diagnostics: bool = False,
        artifacts_dir: Path | None = None,
        extra_dependencies: dict[str, list[str]] | None = None,
    ) -> None:
        assert_clean_coverage_environment()
        self.root = root
        self.artifacts_dir = artifacts_dir or root / "benchmarks" / "results" / f"benchmark-artifacts-{uuid.uuid4().hex}"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.sample_name = "unlabeled"
        self.extra_dependencies = extra_dependencies or {}
        self.started_at = datetime.now(timezone.utc).isoformat()
        code = (
            "import json,sys,uvicorn_rs._native as n; "
            "print(json.dumps({'native':n.__file__,'python':sys.executable,'version':sys.version}))"
        )
        runtime = json.loads(subprocess.check_output([str(python), "-c", code], cwd=root, text=True))
        self.native = Path(runtime["native"]).resolve()
        self.runtime = runtime
        self.clients = [path.resolve() for path in clients]
        common = [
            "Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock", "src/lib.rs",
            "python/uvicorn_rs/__init__.py", "python/uvicorn_rs/__main__.py",
            "python/uvicorn_rs/_bridge.py", "python/uvicorn_rs/cli.py", "python/uvicorn_rs/server.py",
            "scripts/benchmark_evidence.py",
        ]
        self.source_paths = sorted(set(common + source_paths))
        native_bytes = self.native.read_bytes()
        markers = (b"coverage-injected", b"UVICORN_RS_COVERAGE_", b"__llvm_profile", b"__llvm_covmap")
        if any(marker in native_bytes for marker in markers):
            raise RuntimeError("installed native extension contains coverage/fault-injection markers")
        if not allow_runtime_diagnostics and b"uvicorn-rs-runtime-diagnostics " in native_bytes:
            raise RuntimeError("installed native extension contains runtime diagnostics; rebuild normal release")
        self.allow_runtime_diagnostics = allow_runtime_diagnostics
        self.before = self.snapshot()
        self.dependencies_before = self.dependency_snapshot(python)
        instrumented = [
            path for name in self.extra_dependencies
            for path in self.dependencies_before[name]["native_instrumentation_detected"]
        ]
        if instrumented:
            raise RuntimeError(f"selected optional dependency contains coverage instrumentation: {instrumented}")
        self.python = python
        self.git_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        self.git_changes = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True
        ).splitlines()
        tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0"))
        self.untracked_sources = [name for name in self.source_paths if name not in tracked]
        self.dirty = bool(self.git_changes or self.untracked_sources)

    def label_sample(self, workload: str, server: str, repetition: int) -> None:
        self.sample_name = f"{workload}-{server}-repeat-{repetition}"

    def open_server_log(self):
        path = self.artifacts_dir / f"{self.sample_name}-server.log"
        return path.open("x+t")

    def checkpoint_provenance(self, path: Path) -> None:
        """Label unfinished raw rows explicitly before any sample is executed."""
        path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps({
            "benchmark_evidence_version": 1,
            "performance_evidence_status": "not_proven",
            "completion_state": "raw checkpoint; category completion requires the final JSON report",
            "started_at": self.started_at,
            "identity_before": self.before,
            "installed_dependencies_before": self.dependencies_before,
            "git_revision": self.git_revision,
            "dirty_target": self.dirty,
            "minimum_valid_paired_repetitions": 3,
            "server_logs_directory": str(self.artifacts_dir),
        }, indent=2) + "\n")

    def dependency_snapshot(self, python: Path) -> dict:
        code = '''
import base64,hashlib,importlib.metadata as m,importlib.util,json,subprocess,sys
from pathlib import Path
from urllib.parse import unquote,urlsplit,urlunsplit
result={}
extra=json.loads(sys.argv[1])
modules={name:[name.replace("-","_")] for name in ("uvicorn","hypercorn","h11","h2","hpack","hyperframe","aioquic","uvloop","httptools","websockets","wsproto","cryptography","pylsqpack")}
modules.update(extra)
for name,module_names in modules.items():
 try: distribution=m.distribution(name)
 except m.PackageNotFoundError:
  if name in extra: raise RuntimeError("selected optional workload requires installed distribution "+name)
  continue
 roots=[]; resolutions={}
 for module_name in module_names:
  spec=importlib.util.find_spec(module_name)
  locations=[Path(p).resolve() for p in (spec.submodule_search_locations or [])] if spec is not None else []
  roots.extend(locations)
  resolutions[module_name]={"origin":spec.origin if spec is not None else None,"package_roots":[str(p) for p in locations]}
 roots=sorted(set(roots))
 paths={p.resolve() for root in roots for p in root.rglob("*") if p.is_file() and p.suffix in (".py",".so",".dylib",".pyd") and "__pycache__" not in p.parts}
 record_hashes={Path(distribution.locate_file(p)).resolve():p.hash for p in distribution.files or [] if p.hash is not None}
 files={}; mismatches=[]; unrecorded=[]; instrumented=[]
 for path in sorted(paths):
  content=path.read_bytes(); digest=hashlib.sha256(content).digest(); files[str(path)]=digest.hex()
  if name in extra and path.suffix in (".so",".dylib",".pyd") and any(marker in content for marker in (b"__llvm_profile",b"__llvm_covmap",b"coverage-injected")): instrumented.append(str(path))
  expected=record_hashes.get(path)
  if expected is None: unrecorded.append(str(path))
  elif expected.mode=="sha256" and base64.urlsafe_b64encode(digest).decode().rstrip("=")!=expected.value: mismatches.append(str(path))
 direct_text=distribution.read_text("direct_url.json"); direct=json.loads(direct_text) if direct_text else None
 if direct and "url" in direct:
  u=urlsplit(direct["url"]); direct["url"]=urlunsplit((u.scheme,u.netloc.split("@")[-1],u.path,"",""))
 external=None
 if direct and direct.get("dir_info",{}).get("editable") and urlsplit(direct.get("url","")).scheme=="file":
  checkout=Path(unquote(urlsplit(direct["url"]).path)).resolve()
  try:
   revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=checkout,text=True).strip()
   status=subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=checkout,text=True).splitlines()
   indexed=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","-z"],cwd=checkout).decode().split("\\0")
   relevant={str(Path(p)):hashlib.sha256((checkout/p).read_bytes()).hexdigest() for p in sorted(set(indexed)) if p and (checkout/p).is_file() and Path(p).suffix in (".rs",".py",".pyi",".toml",".lock")}
   tracked=set(subprocess.check_output(["git","ls-files","--cached","-z"],cwd=checkout).decode().split("\\0"))
   untracked_relevant=[p for p in relevant if p not in tracked]
   external={"path":str(checkout),"revision":revision,"dirty":bool(status or untracked_relevant),"tracked_changes":status,"untracked_source_files":untracked_relevant,"source_files":relevant,"source_sha256":hashlib.sha256(json.dumps(relevant,sort_keys=True).encode()).hexdigest(),"compiled_source_binding":"source and installed binary fingerprints; no independent build attestation"}
  except subprocess.CalledProcessError:
   external={"path":str(checkout),"revision":None,"dirty":None,"source_sha256":None,"compiled_source_binding":"editable path has no readable Git identity"}
 record_text=distribution.read_text("RECORD")
 result[name]={"version":distribution.version,"modules":resolutions,"package_roots":[str(p) for p in roots],"files":files,"source_sha256":hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),"record_sha256":hashlib.sha256(record_text.encode()).hexdigest() if record_text else None,"record_content_mismatches":mismatches,"unrecorded_source_files":unrecorded,"direct_url":direct,"direct_url_sha256":hashlib.sha256(direct_text.encode()).hexdigest() if direct_text else None,"external_checkout":external,"native_instrumentation_detected":instrumented}
print(json.dumps(result))
'''
        return json.loads(subprocess.check_output([str(python), "-c", code, json.dumps(self.extra_dependencies)], cwd=self.root, text=True))

    def snapshot(self) -> dict:
        source = {name: _sha256(self.root / name) for name in self.source_paths}
        digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        return {
            "source_sha256": digest,
            "source_files": source,
            "native_extension": {"path": str(self.native), "sha256": _sha256(self.native)},
            "clients": {str(path): _sha256(path) for path in self.clients},
        }

    def before_sample(self) -> dict:
        assert_clean_coverage_environment()
        return self.snapshot()

    def after_sample(self, before: dict) -> dict:
        after = self.snapshot()
        stable = before == after == self.before
        return {
            "timing_valid": stable,
            "timing_invalid_reasons": [] if stable else ["source_or_binary_identity_changed"],
            "measurement_identity": {
                "source_sha256_before": before["source_sha256"],
                "source_sha256_after": after["source_sha256"],
                "native_sha256_before": before["native_extension"]["sha256"],
                "native_sha256_after": after["native_extension"]["sha256"],
                "client_sha256_before": before["clients"],
                "client_sha256_after": after["clients"],
            },
        }

    def finish(self, rows: list[dict]) -> dict:
        after = self.snapshot()
        dependencies_after = self.dependency_snapshot(self.python)
        stable = self.before == after and self.dependencies_before == dependencies_after
        modified_baselines = [
            name for name, identity in self.dependencies_before.items()
            if identity["record_content_mismatches"] or identity["unrecorded_source_files"]
            or (identity["direct_url"] and identity["direct_url"].get("dir_info", {}).get("editable"))
        ]
        if not stable:
            for row in rows:
                row["timing_valid"] = False
                if "suite_identity_changed" not in row["timing_invalid_reasons"]:
                    row["timing_invalid_reasons"].append("suite_identity_changed")
        excluded = [
            {"workload": row.get("workload"), "server": row["server"], "repetition": row["repetition"],
             "reasons": row["timing_invalid_reasons"]}
            for row in rows if not row.get("timing_valid", True)
        ]
        paired = []
        for workload in sorted({row.get("workload") for row in rows if row.get("workload")}):
            servers = {row["server"] for row in rows if row.get("workload") == workload}
            for candidate in sorted(name for name in servers if name.startswith("uvicorn-rs-")):
                for baseline in sorted(name for name in servers if not name.startswith("uvicorn-rs-")):
                    candidate_repetitions = {row["repetition"] for row in rows if row.get("workload") == workload and row["server"] == candidate and row.get("timing_valid", True)}
                    baseline_repetitions = {row["repetition"] for row in rows if row.get("workload") == workload and row["server"] == baseline and row.get("timing_valid", True)}
                    matching = sorted(candidate_repetitions & baseline_repetitions)
                    paired.append({"workload": workload, "candidate": candidate, "baseline": baseline,
                                   "valid_matching_repetitions": matching, "required": 3,
                                   "outcome": "available" if len(matching) >= 3 else "not_proven"})
        return {
            "benchmark_evidence_version": 1,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "identity_before": self.before,
            "identity_after": after,
            "identity_stable": stable,
            "installed_dependencies_before": self.dependencies_before,
            "installed_dependencies_after": dependencies_after,
            "modified_or_unrecorded_dependencies": modified_baselines,
            "python_runtime": self.runtime,
            "git_revision": self.git_revision,
            "dirty_target": self.dirty,
            "tracked_worktree_changes": self.git_changes,
            "untracked_measured_sources": self.untracked_sources,
            "performance_evidence_status": "not_proven" if self.dirty or modified_baselines or not stable or excluded or not paired or any(pair["outcome"] != "available" for pair in paired) else "completed",
            "performance_evidence_scope": "local paired experiment" if self.dirty else "frozen checkout benchmark",
            "timing_valid": stable and not excluded,
            "timing_median_policy": "at least three unique timing_valid repetitions; every excluded/partial raw row is retained",
            "timing_excluded_rows": excluded,
            "paired_timing_repetitions": paired,
            "minimum_valid_paired_repetitions": 3,
            "process_isolation": "owned POSIX sessions; track root/descendant PID and create_time; leader SIGINT triggers official graceful shutdown, then identity-verified TERM/KILL per owned PID if needed; no process-group signal probes",
            "client_wall_limit": "requested duration plus 30 seconds for warmup and measured load independently",
            "runtime_diagnostics": self.allow_runtime_diagnostics,
            "host_contention_policy": SampleMonitor.contention_policy,
            "load_model": "closed loop: each worker sends its next request after the previous complete response",
            "latency_limitations": "no open-loop offered-rate test or coordinated-omission correction; latency includes client work",
            "resource_boundary": "client process lifetime, including setup/drain/report; client active request windows vary by protocol",
            "memory_limitations": "sampled process-tree RSS peak; not allocator peak or proportional/private set size",
        }


class SampleMonitor:
    """Collect process-tree CPU deltas and unrelated-host activity without argv."""

    contention_policy = {
        "sampling_interval_seconds": 0.25,
        "per_process_cpu_percent_threshold": 25.0,
        "consecutive_intervals_required": 2,
        "single_interval_cpu_percent_threshold": 200.0,
        "aggregate_cpu_percent_threshold": 100.0,
        "cpu_percent_basis": "100% equals one logical core",
        "excluded": "runner ancestors and runner/server/client descendant PIDs",
    }

    def __init__(self, server: psutil.Process, client: psutil.Process) -> None:
        self.server, self.client = server, client
        self.started = time.monotonic()
        self.runner_cpu_before = time.process_time()
        self.monitor_cpu_seconds = 0.0
        self.last_sample = self.started
        self.resource_states: dict[str, dict] = {"server": {}, "client": {}}
        self.cpu_intervals: dict[str, list[float]] = {"server": [], "client": []}
        self.rss_samples: dict[str, list[int]] = {"server": [], "client": []}
        self.ambient_states: dict[tuple[int, float], float] = {}
        self.ambient_streaks: dict[tuple[int, float], int] = {}
        self.ambient_samples: list[dict] = []
        self.invalid_reasons: set[str] = set()
        self.child_cpu_before = self._child_cpu()
        self.sample(initial=True)

    @staticmethod
    def _child_cpu() -> float | None:
        if resource is None:
            return None
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return usage.ru_utime + usage.ru_stime

    @staticmethod
    def _tree(root: psutil.Process) -> list[psutil.Process]:
        try:
            return [root, *root.children(recursive=True)]
        except psutil.Error:
            return [root]

    def sample(self, *, initial: bool = False, final: bool = False) -> None:
        started = time.process_time()
        try:
            self._sample(initial=initial, final=final)
        finally:
            self.monitor_cpu_seconds += time.process_time() - started

    def _sample(self, *, initial: bool = False, final: bool = False) -> None:
        now = time.monotonic()
        interval = now - self.last_sample
        if not initial and not final and interval < 0.05:
            return
        excluded = {os.getpid()}
        try:
            excluded.update(process.pid for process in psutil.Process().parents())
            excluded.update(process.pid for process in psutil.Process().children(recursive=True))
        except psutil.Error:
            pass
        for label, root in (("server", self.server), ("client", self.client)):
            delta, rss = 0.0, 0
            for process in self._tree(root):
                excluded.add(process.pid)
                try:
                    key = (process.pid, process.create_time())
                    times = process.cpu_times()
                    cpu = times.user + times.system
                    rss += process.memory_info().rss
                    previous = self.resource_states[label].get(key)
                    if previous is None:
                        self.resource_states[label][key] = [cpu, cpu]
                    else:
                        delta += max(0.0, cpu - previous[1])
                        previous[1] = cpu
                except psutil.Error:
                    pass
            self.rss_samples[label].append(rss)
            if not initial and interval >= 0.05:
                self.cpu_intervals[label].append(delta / interval * 100)
        if not initial and interval < 0.05:
            return
        activity = []
        live_keys = set()
        for process in psutil.process_iter(["pid", "name", "create_time", "cpu_times"], ad_value=None):
            info = process.info
            if info["pid"] in excluded or info["cpu_times"] is None or info["create_time"] is None:
                continue
            key = (info["pid"], info["create_time"])
            live_keys.add(key)
            cpu = info["cpu_times"].user + info["cpu_times"].system
            previous = self.ambient_states.get(key)
            self.ambient_states[key] = cpu
            if initial or previous is None or interval <= 0:
                continue
            percent = max(0.0, cpu - previous) / interval * 100
            streak = self.ambient_streaks.get(key, 0) + 1 if percent > 25 else 0
            self.ambient_streaks[key] = streak
            if percent >= 1:
                activity.append({"pid": info["pid"], "name": info["name"], "cpu_percent": percent})
            if streak >= 2 or percent >= 200:
                self.invalid_reasons.add("unrelated_host_cpu_activity")
        self.ambient_states = {key: value for key, value in self.ambient_states.items() if key in live_keys}
        self.ambient_streaks = {key: value for key, value in self.ambient_streaks.items() if key in live_keys}
        if not initial:
            total = sum(item["cpu_percent"] for item in activity)
            if total > 100:
                self.invalid_reasons.add("unrelated_host_cpu_activity")
            self.ambient_samples.append({
                "elapsed_seconds": now - self.started, "interval_seconds": interval,
                "unrelated_cpu_percent": total, "processes": activity,
                "excluded_pids": sorted(excluded),
            })
        self.last_sample = now

    def finish(self, metrics: dict) -> dict:
        self.sample(final=True)
        elapsed = time.monotonic() - self.started
        requests = metrics.get("requests", 0)
        result = {
            "resource_wall_seconds": elapsed,
            "runner_cpu_seconds": time.process_time() - self.runner_cpu_before,
            "monitor_cpu_seconds": self.monitor_cpu_seconds,
            "observer_limitations": "same-host observer consumes CPU; its measured CPU is reported and excluded from unrelated-process contention",
            "host_cpu_activity": self.ambient_samples,
            "timing_valid": not self.invalid_reasons,
            "timing_invalid_reasons": sorted(self.invalid_reasons),
        }
        for label in ("server", "client"):
            cpu = sum(last - first for first, last in self.resource_states[label].values())
            child_cpu_after = self._child_cpu()
            if label == "client" and self.child_cpu_before is not None and child_cpu_after is not None:
                cpu = max(0.0, child_cpu_after - self.child_cpu_before)
            intervals = self.cpu_intervals[label]
            result.update({
                f"{label}_cpu_seconds": cpu,
                f"{label}_cpu_percent_elapsed": cpu / elapsed * 100 if elapsed else None,
                f"{label}_cpu_microseconds_per_request": cpu / requests * 1_000_000 if requests else None,
                f"{label}_cpu_percent_mean": statistics.mean(intervals) if intervals else None,
                f"{label}_cpu_percent_max": max(intervals, default=None),
                f"{label}_rss_peak_mib": max(self.rss_samples[label], default=0) / (1024 * 1024),
            })
        result["client_cpu_complete"] = self.child_cpu_before is not None
        result["client_cpu_limitations"] = (
            "reaped-child rusage delta includes setup/drain/report; no other runner children are reaped in this boundary"
            if self.child_cpu_before is not None else
            "exited client CPU can omit its final unsampled interval; server CPU is read before shutdown"
        )
        return result
