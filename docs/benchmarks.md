# Reproducible performance benchmarks

This guide runs the complete current benchmark matrix: HTTP/1.1, HTTP/2, HTTP/3,
WebSockets, and lifespan/shutdown. The runners check each measured response or
message before recording its metrics. A failed correctness check aborts that
runner; performance numbers from a failed run must not be compared.

These are loopback application-server benchmarks, not end-to-end production
capacity tests. They measure the combined server, Python ASGI app, event loops,
protocol implementation, client, and host. Use the same machine, checkout,
Python environment, workloads, and load parameters for comparisons. Do not run
other builds, tests, benchmarks, emulators, or CPU-heavy jobs at the same time.
Run one category at a time; each runner serializes samples and shuffles server
configuration order within a repetition using the supplied seed.

## What is compared

| Category | Candidate and baseline | Correctness gate |
|---|---|---|
| HTTP/1.1 | Rust server with asyncio and uvloop; Uvicorn with asyncio + h11 and uvloop + httptools. Uvicorn uvloop + httptools is the strongest measured H1 baseline. | Every response status and complete body is checked against the workload oracle. |
| HTTP/2 | Rust server and Hypercorn, each with asyncio and uvloop. | TLS ALPN must select H2; status and full response body are checked. |
| HTTP/3 | Rust server and Hypercorn, each with asyncio and uvloop. Hypercorn's upload workload is known to fail; other Hypercorn rows must still pass each run's correctness gate before they can be compared. | QUIC/TLS, status, and full response body are checked. |
| WebSockets | Rust server with asyncio and uvloop; Uvicorn with its WebSocket implementation and asyncio or uvloop. | Handshake/subprotocol and complete text or binary payload equality are checked. |
| Lifespan/shutdown | Rust server and Uvicorn with both loop choices. | Lifespan state, graceful lifespan completion, and cancellation of an active request are required. |

Uvicorn has no H2 or H3 server baseline, so those rows compare with Hypercorn
only. HTTP/3 upload has Rust-only rows because the tested Hypercorn version did
not return a response after consuming the upload. An earlier archived run
passed the 66-row comparison for its represented H3 workloads. The latest
attempt aborted when Hypercorn asyncio timed out on four fixed-response
requests in repetition 3; the failure log and separate 36-row Rust-only matrix
are in the [latest run record](../benchmarks/results/full-rerun-2026-10-02T161854Z/).
See [the feasibility report](feasibility.md) for the complete status. Do not
label candidate-only rows as cross-server wins.

## Machine and environment

The recorded reference environment is Apple M3 Pro / macOS 15.7.7, CPython
3.12.13, Rust 1.98.1, Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0, and
Hypercorn 0.18.0. It is one data point, not a supported-platform claim. CPU
percentages are process CPU divided by wall time: 100% is one fully occupied
logical core. Server and client CPU are reported separately where the runner can
sample both; loopback load clients can themselves become the bottleneck.

Required tools are `uv`, Python 3.12, Rust/Cargo, a C compiler and `curl-config`
for the native H1 load client, Node.js for the slow-reader fallback, and
OpenSSL for test certificates. H2, H3, and WebSocket benchmark clients are
built in release mode by their runners.

Start from a clean checkout, or record every local code change because runner
source digests do not fingerprint the entire Git worktree. Keep the lockfile
fixed and reinstall the local server extension so the benchmark uses the code
in this checkout:

```sh
uv lock --check
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
uv run python -c 'import uvicorn_rs; print(uvicorn_rs.__file__)'
```

The `benchmark` dependency group contains comparison servers and measurement
tools. None is a runtime dependency of `uvicorn-rs`.

The optional `starlette-rs-route` HTTP workload needs the separate framework
installed in this benchmark environment. That integration is deliberately
optional and does not add it to this server's dependencies. If the framework
checkout is adjacent to this repository:

```sh
uv pip install --python .venv/bin/python --editable ../starlette-rs
git -C ../starlette-rs rev-parse HEAD
```

Record that framework commit with the run. If the optional framework is not
installed, omit `starlette-rs-route` from the H1 `--workloads` argument and
record that omission; do not count the reduced matrix as all 12 H1 workloads.

## Correctness probes

Run the live probes after the extension rebuild and before performance samples:

```sh
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
uv run python scripts/probe_starlette_rs.py  # only after separate installation
```

These are targeted black-box cases, not the complete official ASGI conformance
suite. Save their stdout/stderr as `live-probes.log` in the run's result
directory. The support matrix lists the exact behaviors covered and known gaps.

## Run the full matrix

The settings below match the original category run: a fixed seed, three
repetitions, 2-second samples, and a 0.25-second warmup. New results go into a
unique directory so an earlier raw artifact cannot be overwritten. Save the
environment record before starting the matrix. On another OS, adjust the CPU
model command but keep the other version and revision information.

Before running, inspect `ps -Ao pid,stat,%cpu,comm,args` and defer if unrelated
builds, tests, emulators, or other CPU-heavy jobs are active. Recheck between
categories and save process snapshots: work can start after a clear launch
snapshot. The latest attempt's H1 start snapshot contained two unrelated Rust
compiler processes at 72.8% and 71.3% CPU and a Python workload at 68.2%; its
H3 candidate-only retry overlapped another Rust compiler at 139.6%. An Android
emulator remained resident throughout. All measurements from that run are
provisional; see its [run notes](../benchmarks/results/full-rerun-2026-10-02T161854Z/run-notes.md)
and process snapshots. An earlier archive captured a separate Rust test
process at 687.4% CPU plus concurrent Rust compiler and documentation jobs.
The loopback client also shares CPU with the server; move large-transfer
clients to a separate host when client CPU approaches saturation.

```sh
RUN_ID=$(date -u +%Y-%m-%dT%H%M%SZ)
RESULTS="benchmarks/results/full-${RUN_ID}"
mkdir -p "$RESULTS"
set -o pipefail
{
  git rev-parse HEAD
  git status --short
  uv run python --version
  rustc --version
  cargo --version
  uv --version
  uv run python -c 'import importlib.metadata as m; print("uvicorn", m.version("uvicorn")); print("uvloop", m.version("uvloop")); print("httptools", m.version("httptools")); print("hypercorn", m.version("hypercorn"))'
  uname -a
  sysctl -n machdep.cpu.brand_string 2>/dev/null || true
  ps -Ao pid,stat,%cpu,comm,args
} > "$RESULTS/environment.txt" 2>&1

uv run python scripts/run_http_category_bench.py \
  --workloads fixed large-response many-response-chunks small-response-chunks \
    request-upload request-upload-small-chunks slow-reader-backpressure \
    scope-32-headers contextvars sync-callable-awaitable exception-to-500 \
    starlette-rs-route \
  --duration 2 --warmup 0.25 --concurrency 64 --repetitions 3 --seed 20261002 \
  --output "$RESULTS/http1.json" 2>&1 | tee "$RESULTS/http1.log"

uv run python scripts/run_h2_category_bench.py \
  --duration 2 --warmup 0.25 --concurrency 16 --repetitions 3 --seed 20261002 \
  --output "$RESULTS/http2.json" 2>&1 | tee "$RESULTS/http2.log"

uv run python scripts/run_h3_category_bench.py \
  --duration 2 --warmup 0.25 --concurrency 4 --repetitions 3 --seed 20261002 \
  --output "$RESULTS/http3.json" 2>&1 | tee "$RESULTS/http3.log"

uv run python scripts/run_websocket_category_bench.py \
  --duration 2 --warmup 0.25 --concurrency 32 --repetitions 3 --seed 20261002 \
  --output "$RESULTS/websocket.json" 2>&1 | tee "$RESULTS/websocket.log"

uv run python scripts/run_lifecycle_bench.py \
  --repetitions 5 --seed 20261002 --output "$RESULTS/lifecycle.json" \
  2>&1 | tee "$RESULTS/lifecycle.log"
```

The run measures the load client on the same host as the server. If the client's
CPU approaches or exceeds one core on a workload, especially large transfers,
use a separate client host for server-efficiency measurements and record the
network/client configuration. Keep loopback results as end-to-end local
measurements, not isolated server capacity.

The runners save per-sample rows and per-workload medians in each JSON file;
the logs retain incremental stdout if a runner stops before writing JSON. The
HTTP/1.1 runner also checkpoints completed rows in `http1.jsonl`. H3
slow-reader concurrency is fixed at 2 by the workload; WebSocket handshake
concurrency is fixed at 1. Record an optional `starlette-rs` commit in
`environment.txt` when that workload is included.

The H3 comparison runner can abort if Hypercorn fails a response check; this
is a correctness failure, not a performance result. Keep the full log and
partial stdout, then collect candidate-only H3 data in a separate file if that
is useful for tracking the Rust server itself:

```sh
uv run python scripts/run_h3_category_bench.py \
  --servers uvicorn-rs-asyncio uvicorn-rs-uvloop \
  --duration 2 --warmup 0.25 --concurrency 4 --repetitions 3 --seed 20261002 \
  --output "$RESULTS/http3-candidate-only.json" \
  2>&1 | tee "$RESULTS/http3-candidate-only.log"
```

That file is useful as a correctness-gated candidate record, but it must not be
used to calculate a Hypercorn speedup. Candidate-only rows do not make the
cross-server H3 benchmark complete.

## Validate before interpreting

All these conditions must hold before using the numbers:

```sh
uv run python - "$RESULTS" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expected_rows = {
    "http1.json": 144,
    "http2.json": 84,
    "websocket.json": 36,
    "lifecycle.json": 20,
}
for filename, expected in expected_rows.items():
    report = json.loads((root / filename).read_text())
    rows = report["rows"]
    assert len(rows) == expected, f"{filename}: expected {expected} rows, found {len(rows)}"
    if filename == "lifecycle.json":
        keys = [(row["server"], row["repetition"]) for row in rows]
    else:
        keys = [(row["workload"], row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == expected, f"{filename}: duplicate or missing case keys"
    for row in rows:
        assert row.get("failures", 0) == 0, f"{filename}: failed gate: {row}"
    if filename == "lifecycle.json":
        assert all(row["active_asgi_task_cancelled"] for row in rows)
    print(f"PASS {filename}: {len(rows)} correctness-gated rows; source={report['metadata'].get('source_sha256')}")

if (root / "http3.json").exists():
    report = json.loads((root / "http3.json").read_text())
    rows = report["rows"]
    assert len(rows) == 66, f"http3.json: expected 66 rows, found {len(rows)}"
    keys = [(row["workload"], row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == 66, "http3.json: duplicate or missing case keys"
    assert all(row.get("failures", 0) == 0 for row in rows), "H3 correctness failure"
    print(f"PASS http3.json: {len(rows)} comparison rows; source={report['metadata'].get('source_sha256')}")
elif (root / "http3-candidate-only.json").exists():
    report = json.loads((root / "http3-candidate-only.json").read_text())
    rows = report["rows"]
    assert len(rows) == 36, f"candidate-only H3: expected 36 rows, found {len(rows)}"
    keys = [(row["workload"], row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == 36, "candidate-only H3: duplicate or missing case keys"
    assert all(row.get("failures", 0) == 0 for row in rows), "H3 candidate correctness failure"
    print("PASS H3 Rust-only matrix; no Hypercorn comparison is available")
else:
    raise AssertionError("No complete or candidate-only H3 result was saved")
PY
```

If `starlette-rs-route` is omitted, its 12 H1 rows are absent and the expected
H1 count is 132. H3 has 66 rows rather than 72 because its known-failing
Hypercorn upload comparison is omitted. A failed/partial run should be retained
with its failure output and rerun to a new result directory after fixing the
cause; do not silently drop failed rows. If the Hypercorn H3 correctness gate
fails again, preserve its failed log and validate a Rust-only 36-row output as
candidate evidence; do not substitute it for the 66-row comparison matrix.

Each category's `summaries_median` contains throughput, p50/p95/p99 latency,
server CPU, sampled RSS, and client CPU where available. Compare only matching
workloads and protocols. Keep raw JSON, JSONL, environment record, runner
source digests, and correctness output together. See [the feasibility report](feasibility.md)
for interpretation of the existing measurements and [the implementation
review](implementation-review.md) for the unresolved CPU and latency questions.

## Diagnostic counters and profiling

An opt-in Rust feature counts ASGI task schedules, immediate/bridged HTTP
receives, HTTP response messages, full response-body channel sends and their
elapsed full-send wait, plus WebSocket bridge/queue activity. A full-send wait
starts when the body channel reports `Full` and ends when the async send gets
channel capacity; it includes bridge scheduling as well as queue delay, so do
not interpret it as pure time resident in the queue. The feature is disabled by
default and compiled out of normal builds.

Use this only to attribute behavior, not to compare throughput. Build the
instrumented extension, collect fixed and chunk-heavy H1 rows, then restore the
default extension build:

```sh
uv run --with 'maturin>=1.14,<2' maturin develop --release --features runtime-diagnostics
RUN_ID=$(date -u +%Y-%m-%dT%H%M%SZ)
uv run python scripts/run_http_category_bench.py \
  --workloads fixed many-response-chunks \
  --duration 2 --warmup 0.25 --concurrency 64 --repetitions 3 --seed 20261002 \
  --require-runtime-diagnostics \
  --output "benchmarks/results/bridge-diagnostics-${RUN_ID}.json"
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
```

The H1 runner stores a `runtime_diagnostics` object on each Rust row and fails
if the feature did not emit counters. Its throughput and latency values come
from the instrumented build and must not be compared with the ordinary run.
The server also compiles the counters into HTTP/2, HTTP/3, and WebSocket call
paths; their corresponding runners do not currently add counter objects to
their result rows.

## Profiling high CPU and latency

An end-to-end benchmark identifies which cases are slow; it does not attribute
CPU to a Rust function, Python callback, copy, scheduler wakeup, or kernel call.
Collect profiles only after measuring a correctness-passing workload on an
otherwise idle machine. Profile at least fixed H1, 1 MiB H1 response, and
multi-chunk H1 response separately. On macOS, Apple's `sample` can capture a
native process profile; `xctrace` Time Profiler can provide richer call-tree
inspection. On Linux use a Rust-symbol-aware profiler such as `perf` or
`samply`, and separately inspect Python stacks if needed. Record the exact
profile command, release binary, OS, and source revision. Profiling perturbs
latency, so keep profiled numbers separate from benchmark results.

Investigate CPU in this order: ASGI event count and PyO3 calls; task creation,
cross-runtime notifications, and channel sends/receives; Hyper body polling;
HTTP framing/TLS; allocation and buffer lifetime; and socket write/syscall
behavior. For latency, examine queue wait and backpressure first, then Python
loop scheduling and cross-runtime wakeups. Use flame graphs and allocation
profiles to decide whether byte scans or copies are actually hot. SIMD can
help only a measured vectorizable loop; it cannot remove Python ASGI messages,
the GIL, scheduler handoffs, or per-chunk backpressure.

One captured M3 Pro profile is consistent with that order: the candidate's
call graphs include the PyO3 `AsgiIo.send` trampoline, Tokio channel sends,
Hyper body polling/socket writes, and Python `call_soon_threadsafe` activity.
This identifies work on the path, not a trustworthy percentage of CPU
attributed to each function. See the raw profiles linked in [the feasibility
report](feasibility.md); their throughput and latency samples were collected
under profiling and must not be used as normal performance results.
