# Reproducible performance benchmarks

This guide runs the maintained benchmark matrix: HTTP/1.1, HTTP/2, HTTP/3,
WebSockets, and lifespan/shutdown. The runners check each measured response or
message before recording its metrics. A failed correctness check aborts that
runner; performance numbers from a failed run must not be compared.

The latest local exact-source run is the
[FastAPI five-category report](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/README.md):
520 correctness rows passed across H1, H2, WebSockets, and lifecycle, with 32
qualified workload/loop pairs. H3 at concurrency 64 stopped on Hypercorn
reference timeouts. The run uses one configured Tokio async worker and no
FastAPI-RS or Starlette-RS. See [benchmark status](benchmark-status.md) for the
latest hosted CI and three-system workflow outcomes.

For new comparisons, the wrapper defaults `--h3-concurrency` to 1. Keep it
separate from `--concurrency`: Hypercorn timed out at H3 concurrency 64, so
higher H3 load is a separate capacity experiment and must be reported
separately.

These are loopback application-server benchmarks, not end-to-end production
capacity tests. They measure the combined server, Python ASGI app, event loops,
protocol implementation, client, and host. The maintained cross-category
comparison uses upstream FastAPI on both servers; it does not benchmark
FastAPI-RS or Starlette-RS. Use the same machine, checkout, Python environment,
workloads, and load parameters for comparisons. Do not run
other builds, tests, benchmarks, emulators, or CPU-heavy jobs at the same time.
The automated matrix evaluates each matched candidate/reference pair on one
system; report results per system and never compare absolute rates across machines.
Run one category at a time; each runner serializes samples and shuffles server
configuration order within a repetition using the supplied seed.

## What is compared

| Category | Candidate and baseline | Correctness gate |
|---|---|---|
| HTTP/1.1 | Upstream FastAPI on the Rust server with asyncio and uvloop; Uvicorn with httptools under both loops. The maintained matrix covers 15 FastAPI workloads across routes, request bodies, and response streams. | Every response status and complete body is checked against the workload oracle. |
| HTTP/2 | The same upstream FastAPI app on the Rust server and Hypercorn, each with asyncio and uvloop. | TLS ALPN must select H2; status and full response body are checked. |
| HTTP/3 | The same upstream FastAPI app on the Rust server and Hypercorn, each with asyncio and uvloop. A Hypercorn consumed-request case has failed under load; that attempt must stay visible and cannot yield a ratio. | QUIC/TLS, status, and full response body are checked. |
| WebSockets | The upstream FastAPI `/echo` route on the Rust server and Uvicorn, each with asyncio or uvloop. | Handshake/subprotocol and complete text or binary payload equality are checked. |
| Lifespan/shutdown | A FastAPI app with shared state and a held request on the Rust server and Uvicorn, each with asyncio or uvloop. | Lifespan state, graceful lifespan completion, and cancellation of an active request are required. |

Each comparison matches event loops: asyncio with asyncio and uvloop with
uvloop. Uvicorn uses `httptools` for both H1 pairs so the asyncio comparison
does not also change the HTTP parser. The analyzer reports these pairs
separately and does not combine loop profiles into one rate or latency ratio.

Uvicorn has no H2 or H3 server baseline, so those rows compare with Hypercorn
only. HTTP/3 upload has Rust-only rows because the tested Hypercorn version did
not return a response after consuming the upload. A later FastAPI run also
recorded a Hypercorn/uvloop timeout on the consumed-request workload at
concurrency 64; see the [latest full-category report](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/README.md).
The historical October 4
two-loop matrix passed 66 H3 comparison rows and is archived with all categories in
[`full-2026-10-04T113122Z`](../benchmarks/results/full-2026-10-04T113122Z/).
Its correctness results are valid, but process snapshots show unrelated
CPU-heavy jobs during the measurements, so its performance rows are
provisional. See [the feasibility report](feasibility.md) for the category
results and rerun gate. Do not label candidate-only rows as cross-server wins.

## Machine and environment

The latest local reference environment is Apple M3 Pro / macOS 15.7.7, CPython
3.12.13, Rust 1.98.1, Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0, and
Hypercorn 0.18.0. It is one data point, not a supported-platform claim. The
automated hosted matrix below reports independent Linux x86_64, Linux arm64,
and macOS arm64 runs. CPU
percentages are process CPU divided by wall time: 100% is one fully occupied
logical core. Server and client CPU are reported separately where the runner can
sample both; loopback load clients can themselves become the bottleneck.

### Automated multi-system matrix

The [ASGI performance matrix workflow](../.github/workflows/benchmark-categories.yml)
runs on benchmark-harness changes pushed to `main`, weekly, or by manual
dispatch. Each hosted job builds the same commit with CPython 3.12.13, Rust
1.98.1, the locked Python dependencies, the normal release server wheel, and the
same protocol clients. The runners are Ubuntu 24.04 x86_64, Ubuntu 24.04 arm64,
and macOS 15 arm64. The workflow records the runner image, CPU model and core
counts, total memory, operating system, architecture, and installed system
package versions because hosted images and allocations can change.

Each system runs the public parity gate before timed work, then runs a separate
FastAPI-only HTTP/1.1 comparison followed by all five maintained categories.
The focused run selects only upstream FastAPI route validation/serialization
and Python CPU workloads. The default is five repetitions per server; the
analyzer still requires at least three matching valid repetitions. The
contention monitor and correctness, process-cleanup, and identity gates remain
active. Invalid observations are retained and excluded from ratios. If a host
is noisy, the report shows the missing qualified pairs; rerun the workflow to
collect a fresh sample set rather than relaxing the gate.

The aggregate validates that all three systems used the same source, harness,
Python version, and dependency versions. It never averages or ranks rates across
machines. After every main-branch attempt, a documentation job opens or refreshes
one PR with the [latest run status](benchmark-status.md). A validated aggregate
also updates the [latest complete results](benchmark-results.md), a versioned
matrix JSON, and machine-readable per-system evidence bundles. An incomplete or
failed attempt leaves the previous complete report intact and links to that
run's artifacts. Repository settings must allow the workflow's `GITHUB_TOKEN`
to create pull requests. This keeps benchmark execution out of ordinary docs
builds. Raw workflow artifacts retain detailed logs for 90 days; the committed
bundles retain measurements, analysis, identity, and parity receipts for
long-term review. A successful correctness-gated run can still have zero
qualified performance pairs and then makes no speed claim.

The latest attempt status and latest completed measurements are tracked
separately. Historical local measurements below remain tied to their own source
revisions and must not be read as results for the current commit.

Required tools are `uv`, Python 3.12, Rust/Cargo, a C compiler and `curl-config`
for the native H1 load client, Node.js for the slow-reader fallback, and
OpenSSL for test certificates. Build the H2, H3, and WebSocket Rust clients
with the prebuild command below before freezing identity; category runners use
those exact binaries and do not rebuild them during measurement.

Start from a clean checkout for a release comparison. A dirty checkout can
produce a local experiment, but its report remains `performance_evidence_status:
not_proven`. The runners fingerprint their declared measured files, not every
file in the worktree. Keep the lockfile fixed and reinstall the normal release
extension before collecting samples:

```sh
uv lock --check
uv sync --python 3.12 --locked --group benchmark --group fastapi-benchmark --reinstall-package uvicorn-rs
uv run --no-sync python -c 'import uvicorn_rs; print(uvicorn_rs.__file__)'
```

The `benchmark` dependency group contains comparison servers and measurement
tools. The `fastapi-benchmark` group pins upstream FastAPI 0.142.4 and is
required by the maintained cross-category comparison. FastAPI, its upstream
Starlette dependency, and Pydantic come from the same locked Python environment
for Uvicorn and `uvicorn-rs`. The report identity records these versions. The
full FastAPI comparison has no mode that silently omits FastAPI workloads.

### Focused FastAPI comparison

For a Python-heavy application comparison, select only the two upstream FastAPI
workloads. Both use the same interpreter and installed app stack: one validates
path/query inputs and serializes a Pydantic response model; the other runs a
deterministic pure-Python CPU loop in a synchronous FastAPI route. Each response
status and body must match its oracle before the row is accepted. The four
server configurations pair Uvicorn and `uvicorn-rs` under asyncio, then again
under uvloop. The Rust server's Tokio runtime remains at one worker thread in
both rows; uvloop controls only the Python app event loop.

```sh
uv lock --check
uv sync --python 3.12 --locked --group benchmark --group fastapi-benchmark --reinstall-package uvicorn-rs
cargo build --release --locked --manifest-path tools/http3-probe/Cargo.toml --bins
.venv/bin/python scripts/run_benchmark_categories.py \
  --capture-identity target/fastapi-one-tokio/parity-before.json
.venv/bin/python scripts/run_parity.py \
  --prebuilt-http3-client \
  --output target/fastapi-one-tokio/parity.json
.venv/bin/python scripts/run_benchmark_categories.py \
  --parity-before-identity target/fastapi-one-tokio/parity-before.json \
  --parity-report target/fastapi-one-tokio/parity.json \
  --category http1 \
  --workloads fastapi-validated-route fastapi-python-cpu \
  --duration 5 --warmup 1 --concurrency 64 --repetitions 5 --seed 20261008 \
  --output-dir target/fastapi-one-tokio/results
```

At five repetitions this focused run plans 40 rows (two workloads × four server
configurations × five repetitions). Read each event-loop pair separately. The
closed-loop load client and server share the host; keep the contention gate on,
retain rejected observations, and make no speed claim unless each pair has at
least three matching timing-valid repetitions. The report fingerprints the
FastAPI/Starlette/Pydantic distributions, the app and harness sources, the
normal Rust binary, Python runtime, and load client.

Older October 8 measurements are historical and tied to an earlier source
snapshot. Use the [latest exact-source FastAPI results](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/README.md)
for current workload comparisons.

### Expanded upstream FastAPI workload matrix

The expanded matrix keeps the same upstream FastAPI app, dependency lock,
CPython, HTTP/1.1 client, and four server configurations while separating
framework work from transport work. It covers a constant response, validated
Pydantic route, synchronous Python CPU route, 1 MiB response, large and small
response chunks, 1 MiB upload, 64 KiB upload sent in 1 KiB writes, a rate-limited
slow reader, 32 request headers, and an async dependency using `ContextVar`.
Every status and complete body is checked before a timing row can qualify.
`uvicorn-rs` uses one Tokio worker; asyncio or uvloop is the Python application
loop in both servers. No FastAPI-RS or Starlette-RS package or route is used.

Reproduce the matrix after installing the locked benchmark groups and building
the normal extension as described above:

```sh
.venv/bin/python scripts/run_benchmark_categories.py \
  --capture-identity target/fastapi-all/parity-before.json
.venv/bin/python scripts/run_parity.py \
  --prebuilt-http3-client \
  --output target/fastapi-all/parity.json
.venv/bin/python scripts/run_benchmark_categories.py \
  --parity-before-identity target/fastapi-all/parity-before.json \
  --parity-report target/fastapi-all/parity.json \
  --category http1 \
  --workloads fastapi-fixed fastapi-validated-route fastapi-python-cpu \
    fastapi-large-response fastapi-many-response-chunks \
    fastapi-small-response-chunks fastapi-request-upload \
    fastapi-request-upload-small-chunks fastapi-slow-reader-backpressure \
    fastapi-scope-32-headers fastapi-contextvars \
  --duration 5 --warmup 1 --concurrency 64 --repetitions 5 --seed 20261008 \
  --output-dir target/fastapi-all/results
```

If the host gate leaves a workload/loop pair short of three matching valid
repetitions, keep the frozen identity and parity receipts, then rerun only the
missing workload names with the same load parameters, a new seed, and a new
output directory. Analyze each attempt independently; do not pool samples
across attempts. Do not edit tracked files between identity capture and run
completion: the suite identity deliberately rejects a worktree change during
measurement.

Earlier local matrices and retries are historical and tied to their own
source snapshots. They are not pooled into the latest results. The latest
exact-source report gives the completed H1, H2, WebSocket, and lifecycle
categories, the incomplete high-concurrency H3 case, and every retained timing
exclusion.

### Fixed-size upload write-size sweep

The follow-up upload sweep keeps the FastAPI request body at 1 MiB and changes
only the client upload callback chunk target: 1 KiB, 16 KiB, 64 KiB, 256 KiB,
or 1 MiB. It runs with the same Uvicorn/Uvicorn-RS server and loop pairs. This
isolates body size from the client-side fragmentation setting. The configured
chunk size is not a TCP packet-size claim; inspect the ASGI receive counts in
the diagnostic run to see how each server actually presents the body to the
application.

```sh
.venv/bin/python scripts/run_http_category_bench.py \
  --workloads fastapi-upload-1m-write-1k fastapi-upload-1m-write-16k \
    fastapi-request-upload fastapi-upload-1m-write-256k fastapi-upload-1m-write-1m \
  --servers uvicorn-rs-asyncio uvicorn-asyncio-httptools \
    uvicorn-rs-uvloop uvicorn-uvloop-httptools \
  --duration 5 --warmup 1 --concurrency 8 --repetitions 5 --seed 20261009 \
  --output benchmarks/results/fastapi-upload-fragmentation-2026-10-09/performance.json
```

Collect bridge and ASGI receive diagnostics separately, using the instrumented
build instructions below and the same workload list. These rows are diagnostic
only; do not use their latency, throughput, or CPU for performance ranking.
Compare all five write targets in one report, preserving each run's validity
receipt and full-body correctness checks. The result can establish whether
measured ASGI message/future counts and the end-to-end gap move with write-size
target; it cannot infer TCP segment boundaries or total copy bytes by itself.

The latest exact-source report distinguishes the default 1 MiB upload from a
1 KiB client-write workload and reports their separate matched outcomes. Its
[boundary diagnosis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md)
contains the receive/future counts; those counters locate work but are not
normal-build timing evidence.

## Correctness probes

Run the live probes after the extension rebuild and before performance samples:

```sh
uv run --no-sync python scripts/probe_http.py
uv run --no-sync python scripts/probe_http2.py
uv run --no-sync python scripts/probe_streaming.py
uv run --no-sync python scripts/probe_websocket.py
uv run --no-sync python scripts/probe_cancellation.py
uv run --no-sync python scripts/probe_lifespan.py
```

These are targeted black-box cases, not the complete official ASGI conformance
suite. Save their stdout/stderr as `live-probes.log` in the run's result
directory. The support matrix lists the exact behaviors covered and known gaps.

The timed FastAPI rows use only upstream FastAPI and its locked dependencies.
Separate framework interoperability evidence is documented in
[deployment and framework integration](deployment.md#test-starlette-integrations);
that integration is not part of the performance matrix.

## Evidence required for a comparison

The HTTP, WebSocket and lifecycle runners share
[`benchmark_evidence.py`](../scripts/benchmark_evidence.py). Their reports separate
correct public output from usable timing evidence. Lifecycle has a distinct
phase measurement boundary, described below.

| Gate | What the runner records or rejects |
|---|---|
| Normal build | Reject armed coverage environment variables, coverage/fault markers in the installed server binary, and runtime counters unless explicitly requested for diagnostics. Selected optional framework native files are also checked for instrumentation markers. |
| Measured identity | Fingerprint declared Rust/Python/app/harness sources, manifests/lockfiles, loaded native extension and client executables before/after every sample and the suite. Identity changes invalidate timing. |
| Dependency identity | Record installed package versions, origins, Python/native file hashes, `RECORD` and direct-install metadata before/after the suite. Changes invalidate the suite; editable, modified or unrecorded dependency files keep release evidence `not_proven`. |
| Public output | Require protocol negotiation where applicable, expected status, and every expected payload byte or WebSocket message. A correctness failure aborts the category. |
| Resource isolation | Record unrelated-process CPU intervals, server and available client process-tree CPU/RSS, and observer CPU. Contended rows remain visible with `timing_valid: false`. |
| Server lifecycle | Require a live server through the load, graceful successful exit without escalation, and no unexpected panic, Python task error or native failure diagnostic. Preserve each sample's log path and digest. |
| Repetition pairing | Require at least three valid matching repetition IDs per candidate/reference/workload. Missing or excluded rows do not become speed evidence. |

Most sustained-load cases sample the contention guard about every 0.25
seconds. WebSocket handshakes poll more frequently; the monitor skips observed
intervals shorter than 50 ms. Lifecycle uses variable sampling, described below.
A row is invalidated when an unrelated process uses more than 25% of one core for two consecutive
intervals, reaches 200% in one interval, or recorded unrelated activity exceeds
100% in aggregate. Runner ancestors and runner/server/client descendants are
excluded from this guard. These thresholds detect observed contention; they do
not establish an idle machine or rule out unobserved short jobs.

Sustained server CPU is observed live process-tree `cpu_times` deltas over the
load/monitor boundary, read before shutdown. It is not complete reaped-server
lifetime accounting. The observer also consumes CPU on the same host;
`runner_cpu_seconds` and `monitor_cpu_seconds` expose that cost. Client CPU,
including setup/drain/report, is reported separately. Reaped-child resource accounting supplies its complete
CPU delta where available; otherwise a final unsampled client interval can be
missed. Prefer `server_cpu_percent_elapsed` / `client_cpu_percent_elapsed` and
`server_cpu_microseconds_per_request` / `client_cpu_microseconds_per_request`
for CPU comparisons; the sampled `*_cpu_percent_mean` values describe observed
intervals and can miss exit time. The resource window and protocol request
window differ. Peak RSS is a sampled sum across the process tree, not allocator
peak or private memory.

The sustained-load clients use a closed-loop load: each worker waits for a
complete response before issuing its next request. Latency includes client
work and has no open-loop offered-rate or coordinated-omission correction. A multi-core
loopback client can limit throughput while competing with the server. Use a
separate client host for isolated server-capacity work and record that changed
network/load setup; it is a separate experiment.

Cleanup for H1/H2/H3 and WebSockets tracks owned PID/create-time identities,
sends the server leader SIGINT first, and permits its supervisor to shut down
workers. It uses bounded TERM/KILL escalation only for captured identities and
rejects a sample that needed escalation. Warmup and load clients each have an absolute wall
limit of their requested duration plus 30 seconds. No unrelated process is
terminated to make a benchmark appear quiet.

### Workload and logging fairness

Keep identical application code, request headers, payloads, concurrency,
connection reuse and client drain policy for each compared server. The H1
Uvicorn command disables access logs and its server header. Uvicorn reference
profiles use public ERROR logging without colors; Hypercorn uses ERROR logging,
so background/post-response errors remain visible to the strict log gate.
Reports record `reference_logging_policy`. The scope workload sends the same 32 explicit request headers through the native and fallback
clients. Payload gates do not compare every response header; use the live
parity matrix for the supported header/protocol contract.

All comparison servers use automatic lifespan behavior: Uvicorn explicitly uses
`--lifespan auto`, Hypercorn uses its default automatic support detection, and
Rust uses its automatic bridge. Reports record `lifespan_policy`. Startup
precedes readiness/warmup/load; the lifespan task and state remain present
during load and shutdown. The synchronous-callable fixture implements lifespan
while retaining its callable-returning-awaitable shape and identical HTTP
behavior. The historical 120-sample A/B used reference lifespan off and CRITICAL
logs; its response checks do not certify the final matched automatic-lifespan
and visible-error policies. Raw historical artifacts remain unchanged.

The `exception-to-500` case is a capped correctness case: concurrency 1, at most
200 requests, 1-second duration and no warmup. Its exception diagnostic policies
differ between servers, so it is always excluded from timing rankings with
`unequal_exception_diagnostic_policy`, even when every 500 response is correct.
A full H1 report containing this case therefore remains `not_proven` at suite
level. Check matching valid repetitions for each rankable workload; collect a
separate frozen timing suite without the exception case if a fully rankable
suite is required, retaining its correctness evidence alongside it.

Slow-reader workloads use cumulative byte pacing at 4,194,304 bytes/s per
connection, rather than sleeping once per transport callback. The final bytes
are included in the paced completion boundary. This keeps drain policy stable
when TCP segmentation changes. H1 uses eight slow-reader connections; H2/H3
use two. Report slow-reader results as backpressure behavior at that imposed
rate, not unrestricted transport capacity.

`performance_evidence_status: completed` means the frozen comparison passed
these evidence gates; it does not mean Rust was faster. Dirty local experiments,
modified dependencies or missing valid pairs remain `not_proven`. Preserve raw
invalid rows and improve the run conditions before making a speed claim.

### Lifecycle measurement boundary

The lifecycle runner uses the same normal-build, identity, dependency,
contention and minimum-three-paired-repetition gates. Each row starts two
independent server processes: an idle shutdown phase and an active phase with
one held ASGI request. The original cold-start, shutdown and ready-RSS metrics
remain; `phase_measurements.idle` and `phase_measurements.active` retain logs,
digests, resource samples and shutdown receipts. `lifecycle.jsonl` checkpoints
whole rows, `lifecycle.phases.jsonl` checkpoints each completed or failed phase,
and `lifecycle.failure.json` records an aborted category as `not_proven`.

Measured shutdown sends SIGTERM to the owned leader. Rust must exit 0;
Uvicorn may exit 0 or re-raise SIGTERM only after the exact lifespan completion
marker. The active phase must first observe `APP_HOLD_STARTED` while the server
is alive, then cancellation before lifespan completion. Its strict log gate
normalizes at most one exact Rust `CancelledError` line, or Uvicorn's single
intentional held-task timeout plus its exact four-frame `CancelledError`
traceback verified against the installed sources. Required markers and official
exit must pass first. Raw logs and `diagnostic_normalization_receipt` retain the
accepted block; every other error, traceback, chain, unhandled task or panic
fails. The exact policy is in `metadata.cancellation_diagnostic_normalization`.

`idle_phase_server_cpu_seconds` / `active_phase_server_cpu_seconds`, their
`*_server_cpu_percent_elapsed` values and `*_server_rss_peak_mib` describe each
complete phase, including startup/readiness/shutdown. Reaped-child accounting
supplies complete server CPU where available; otherwise the receipt states its
sampling limit. Requests run in the observer process, so there is no separate
client CPU or per-request CPU denominator. Observer CPU is reported separately;
`observer_process_tree_rss_peak_mib` includes its server descendants, while
server RSS is server-only. Observer initialization occurs after spawn and before
the first readiness request and can affect the reported cold-start time.
Cold-start includes free-port/environment/spawn preparation through the observed
valid response; it is an upper bound with polling/observer delays, not a claim
of precision finer than the poll interval. Readiness has one absolute 15-second
connect/send/header/body deadline and bounded capture (expected body length + 1;
wire capture 16 KiB + expected length + 1). Held entry has 15 seconds and the
measured SIGTERM exit has five seconds.

Lifecycle sampling is variable: readiness/entry retries are 10 ms, exit waits
are 50 ms, and scans/requests add work. The monitor skips intervals below 50 ms;
two busy observed intervals span at least about 100 ms, rather than the nominal
500 ms of ordinary load samples. Reports retain this category-specific policy.
These values are lifecycle observations, not sustained request throughput.

## Run the standalone protocol probe matrix

This older per-category command sequence includes synthetic ASGI HTTP/1.1
workloads. It is useful for isolating server transport and preserving
historical probe behavior; it is not the maintained FastAPI-only comparison.
For user-facing FastAPI performance evidence across all categories, use
[the complete comparison command](#run-the-complete-comparison-with-one-command-interface)
below.

Use at least three repetitions, 5-second samples and a 1-second warmup for a
new comparison. The October 4 archive used shorter 2-second samples and a
0.25-second warmup; its contended timing remains provisional. Create a fresh
UTC-dated directory for every attempt and retain earlier raw artifacts. Save
the environment record before starting; adjust only the CPU model command on
another OS. Workload-specific duration/concurrency overrides are recorded in
each report, including the unranked exception case.

Before running, inspect `ps -Ao pid,stat,%cpu,comm` and defer if unrelated
builds, tests, emulators, or other CPU-heavy jobs are active. Recheck between
categories and save process snapshots: work can start after a clear launch
snapshot. The October 4 matrix overlapped unrelated parity generation and
validation, mypy, compatibility-atlas work, and Rust compilation; one Rust
compile reached 787% CPU before WebSocket measurements. Its performance rows
are provisional. See its
[`run-notes.md`](../benchmarks/results/full-2026-10-04T113122Z/run-notes.md)
and process snapshots for details. Earlier archives also contain overlapping
Rust builds, tests, and documentation jobs. The loopback client shares CPU
with the server; move large-transfer clients to a separate host when client
CPU approaches saturation.

```sh
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)-$(uuidgen)"
RESULTS="benchmarks/results/full-${RUN_ID}"
mkdir "$RESULTS"
set -o pipefail
{
  git rev-parse HEAD
  git status --short
  uv run --no-sync python --version
  rustc --version
  cargo --version
  uv --version
  uv run --no-sync python -c 'import importlib.metadata as m; print("uvicorn", m.version("uvicorn")); print("uvloop", m.version("uvloop")); print("httptools", m.version("httptools")); print("hypercorn", m.version("hypercorn"))'
  uv run --no-sync python -c 'from pathlib import Path; import hashlib, uvicorn_rs._native as n; p=Path(n.__file__); print("native_extension", p); print("native_extension_sha256", hashlib.sha256(p.read_bytes()).hexdigest())'
  uname -a
  sysctl -n machdep.cpu.brand_string 2>/dev/null || true
  ps -Ao pid,stat,%cpu,comm
} > "$RESULTS/environment.txt" 2>&1

uv run --no-sync python scripts/run_http_category_bench.py \
  --workloads fixed large-response many-response-chunks small-response-chunks \
    request-upload request-upload-small-chunks slow-reader-backpressure \
    scope-32-headers contextvars sync-callable-awaitable exception-to-500 \
  --duration 5 --warmup 1 --concurrency 64 --repetitions 3 --seed 20261005 \
  --output "$RESULTS/http1.json" 2>&1 | tee "$RESULTS/http1.log"

uv run --no-sync python scripts/run_h2_category_bench.py \
  --duration 5 --warmup 1 --concurrency 16 --repetitions 3 --seed 20261005 \
  --output "$RESULTS/http2.json" 2>&1 | tee "$RESULTS/http2.log"

uv run --no-sync python scripts/run_h3_category_bench.py \
  --duration 5 --warmup 1 --concurrency 4 --repetitions 3 --seed 20261005 \
  --output "$RESULTS/http3.json" 2>&1 | tee "$RESULTS/http3.log"

uv run --no-sync python scripts/run_websocket_category_bench.py \
  --duration 5 --warmup 1 --concurrency 32 --repetitions 3 --seed 20261005 \
  --output "$RESULTS/websocket.json" 2>&1 | tee "$RESULTS/websocket.log"

uv run --no-sync python scripts/run_lifecycle_bench.py \
  --repetitions 5 --seed 20261005 --output "$RESULTS/lifecycle.json" \
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
concurrency is fixed at 1.

The H3 comparison runner can abort if Hypercorn fails a response check; this
is a correctness failure, not a performance result. Keep the full log and
partial stdout, then collect candidate-only H3 data in a separate file if that
is useful for tracking the Rust server itself:

```sh
uv run --no-sync python scripts/run_h3_category_bench.py \
  --servers uvicorn-rs-asyncio uvicorn-rs-uvloop \
  --duration 5 --warmup 1 --concurrency 4 --repetitions 3 --seed 20261005 \
  --output "$RESULTS/http3-candidate-only.json" \
  2>&1 | tee "$RESULTS/http3-candidate-only.log"
```

That file is useful as a correctness-gated candidate record, but it must not be
used to calculate a Hypercorn speedup. Candidate-only rows do not make the
cross-server H3 benchmark complete.

## Validate before interpreting

All these conditions must hold before using the numbers:

```sh
uv run --no-sync python - "$RESULTS" <<'PY'
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
    assert len(rows) == 78, f"http3.json: expected 78 rows, found {len(rows)}"
    keys = [(row["workload"], row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == 78, "http3.json: duplicate or missing case keys"
    assert all(row.get("failures", 0) == 0 for row in rows), "H3 correctness failure"
    print(f"PASS http3.json: {len(rows)} comparison rows; source={report['metadata'].get('source_sha256')}")
elif (root / "http3-candidate-only.json").exists():
    report = json.loads((root / "http3-candidate-only.json").read_text())
    rows = report["rows"]
    assert len(rows) == 42, f"candidate-only H3: expected 42 rows, found {len(rows)}"
    keys = [(row["workload"], row["server"], row["repetition"]) for row in rows]
    assert len(set(keys)) == 42, "candidate-only H3: duplicate or missing case keys"
    assert all(row.get("failures", 0) == 0 for row in rows), "H3 candidate correctness failure"
    print("PASS H3 Rust-only matrix; no Hypercorn comparison is available")
else:
    raise AssertionError("No complete or candidate-only H3 result was saved")
PY
```

This standalone command plans 144 H1 rows for the 12 listed workloads at three
repetitions. H3 has 78 rows rather than 84 because its known-failing
Hypercorn upload comparison is omitted. A failed/partial run should be retained
with its failure output and rerun to a new result directory after fixing the
cause; do not silently drop failed rows. If the Hypercorn H3 correctness gate
fails again, preserve its failed log and validate a Rust-only 42-row output as
candidate evidence; do not substitute it for the 78-row comparison matrix.

Row counts and response equality are correctness checks only. For every category,
also inspect `metadata.identity_stable`, `timing_excluded_rows`,
`paired_timing_repetitions` and `performance_evidence_status`. A single valid
row or median is insufficient: each candidate/reference pair needs at least
three matching valid repetition IDs. `summaries_median` stores `null` for a
metric when its server/workload has fewer than three distinct valid repetitions;
it is not itself proof that the pair meets the matching-repetition gate.

Keep raw JSON, checkpoints, environment records, dependency identities and
per-sample server logs together. Excluded timing rows retain their metrics and
reasons; failed or interrupted attempts retain their available logs/checkpoints
and require a new output directory for a rerun. Lifecycle uses the same evidence
gates while preserving its separate phase metrics and resource boundary.
See [the feasibility report](feasibility.md) for historical interpretation and
[the implementation review](implementation-review.md) for remaining questions.

## Run the complete comparison with one command interface

[`run_benchmark_categories.py`](../scripts/run_benchmark_categories.py) runs the
maintained HTTP/1.1, HTTP/2, HTTP/3, WebSocket and lifecycle categories sequentially.
It derives workloads and public parity cases from the maintained matrix, rejects
coverage/fault/diagnostic binaries, and requires a passing complete public matrix
on the exact measured normal binary. Prepare the normal release server and
coherent release protocol clients using the setup above. The maintained
cross-category comparison uses upstream FastAPI applications throughout; it
does not install or benchmark FastAPI-RS or Starlette-RS.

```sh
export RUSTC_WRAPPER= RUSTC_WORKSPACE_WRAPPER=
cargo build --release --locked --manifest-path tools/http3-probe/Cargo.toml --bins
.venv/bin/python scripts/run_benchmark_categories.py \
  --capture-identity target/benchmark-preparation/parity-before.json
.venv/bin/python scripts/run_parity.py \
  --prebuilt-http3-client \
  --output target/benchmark-preparation/parity.json
.venv/bin/python scripts/run_benchmark_categories.py \
  --parity-before-identity target/benchmark-preparation/parity-before.json \
  --parity-report target/benchmark-preparation/parity.json \
  --duration 5 --warmup 1 --concurrency 64 --repetitions 3 --seed 20261005
```

Every capture file and output directory must be new. Omitting `--output-dir`
creates a timestamp/UUID directory under `target/benchmark-categories/`. The
At three repetitions, the full FastAPI-only matrix plans 390 rows: 180 HTTP/1.1,
84 HTTP/2, 78 HTTP/3, 36 WebSocket, and 12 lifespan/shutdown rows. The hosted
workflow's five-repeat default plans 650 rows. H3 can abort on a reference
correctness failure; a partial run remains incomplete, and completed categories
do not make it a complete matrix. The separate focused FastAPI-only H1 report
contains 40 rows at five repetitions. Each category includes the available
loop-matched reference/candidate pairs.
`run.json`, event/checkpoint JSONL, source/binary/dependency hashes, server logs,
cleanup receipts and raw failures are retained. The wrapper stops on identity
drift and preserves independent category attempts after an isolated failure.
It never stops unrelated processes or retries invalid timings into the same run.
Keep the same build-wrapper settings for prebuild, identity capture, parity and
benchmarks. A configured coverage wrapper can otherwise rebuild a client after
capture; that invalidates the gate even when every response passes.

The pure JSON analyzer automatically writes `analysis.json` and `analysis.md`.
To analyze existing artifacts without running load:

```sh
.venv/bin/python scripts/analyze_benchmark_categories.py \
  --input-dir target/benchmark-categories/RUN_DIRECTORY
```

For local diagnosis, select one or more categories with repeated `--category`
flags, for example `--category http1 --category websocket`. The wrapper still
requires the complete public parity gate on the frozen binary, then measures
only the selected categories. Its report lists omitted categories and marks a
selected run `partial_category_subset`; this is useful for isolating a failed
category but does not replace the complete five-category matrix or qualify as
the full release benchmark.

Each comparison requires three matching valid repetitions. Incomplete categories,
host contention, modified dependencies, deliberate exception costs and missing
reference upload results remain excluded. Successful correctness execution can
still produce zero qualified performance comparisons.

The [current normal-build run](../benchmarks/results/performance-investigation-2026-10-05/final-normal-c7-categories/analysis.md)
qualifies three matched WebSocket connection-handshake repetitions, with a
median same-repetition Rust/Uvicorn rate ratio of 1.590. Other workloads lack
enough clean matches, and HTTP/3 is incomplete after a reference correctness
failure. See the [investigation](performance-investigation-2026-10-05.md) for
throughput, latency, CPU, memory and the scope of that local result.
When a driver receipt is present, the analyzer also requires its complete public
parity gate, stable before/after identity, exact category plan and report hash,
successful category exit, and clean owned-process cleanup. A failed category
does not qualify through a complete JSON report; other independently completed
categories retain their own gates.

HTTP/3 includes a separate `protocol-scope-consumed-request` workload. Its
identical app on both servers reads through the final `more_body=false` event
and returns the protocol version and received byte count. The existing legal
early-response workload is unchanged. If that workload crashes stock Hypercorn,
retain the failure; measure the consumed-request workload in a separate run
with its own fixture identity rather than replacing the failed workload.

The consumed-request workload explicitly disables optional H3 GREASE on the
same client for both servers. Pinned aioquic 1.3.0 can lose the request-end event
when an unknown trailing frame and FIN share incoming data. Existing workloads
retain GREASE enabled, and their failed attempts remain visible. The selected
setting is present in the workload definition, client output and report metadata.
At concurrency 64 with four QUIC connections, this fully consumed workload also
failed under stock Hypercorn: 13,291 correct responses followed by 16 header
timeouts, with an empty server log. The Rust sample passed, but no ratio is
qualified. This is separate from the earlier GREASE-dependent first-request
failure and captured early-response `KeyError`; neither is established as its
cause. Preserve the failed attempt when diagnosing lower declared loads.
Run that declared comparison separately:

```sh
.venv/bin/python scripts/run_h3_category_bench.py \
  --servers hypercorn-uvloop uvicorn-rs-uvloop \
  --workloads protocol-scope-consumed-request \
  --duration 5 --warmup 1 --concurrency 64 --repetitions 5 --seed 20261005 \
  --output target/h3-consumed-NEW_RUN.json
```

Keep a new output path for every attempt. This narrower workload cannot establish
coverage of the complete H3 benchmark category or remove the earlier failure.

### Hosted benchmark CI

[ASGI performance matrix](../.github/workflows/benchmark-categories.yml)
runs manually, weekly, and when benchmark-related files change on `main`. It
uses Linux x86_64, Linux arm64, and macOS arm64 with Python 3.12.13 and Rust
1.98.1. Each system installs the locked references, builds a normal release
server and protocol clients, and gates the exact binary on every current public
parity case before timing. It uploads preparation, parity, and category
artifacts even on failure. Hosted image and system package versions are
recorded, not fully pinned.

After all systems pass their correctness and identity gates, the aggregate job
checks the source, Python, harness, and dependency identities and keeps platform
results separate. The documentation job opens or refreshes one PR with the
generated summary and a versioned evidence archive. Category artifacts retain
detailed logs for 90 days; the committed evidence bundles retain raw measurement
rows, analysis, identity, and parity receipts. Hosted VMs do not establish
dedicated physical hardware or an absence of noisy neighbors; compare servers
within each system and retain host contention and client CPU limits.

To request a run, select **Actions → ASGI performance matrix → Run workflow**
from `main`. The [status page](benchmark-status.md) records the latest attempt;
the [results page](benchmark-results.md) links the latest completed report to
its exact workflow run and archived evidence after the docs update PR is merged.

## Diagnostic counters and profiling

An opt-in Rust feature counts ASGI task schedules, immediate/bridged HTTP
receives, HTTP response messages, full response-body channel sends and their
elapsed full-send wait, plus WebSocket bridge/queue activity. A full-send wait
starts when the body channel reports `Full` and ends when the async send gets
channel capacity; it includes bridge scheduling as well as queue delay, so do
not interpret it as pure time resident in the queue. The feature is disabled by
default and compiled out of normal builds.

For FastAPI diagnosis, the same feature also totals the time from request
dispatch to acquisition of the Python interpreter for the request callback,
request dispatch to `http.response.start`, and request dispatch to availability
of the final ASGI body message. The last boundary is before the response is
fully written to the client. A task-starter timer runs from before the PyO3
starter object is created until its Python event-loop callback begins; it
includes starter construction, context setup, cross-thread scheduling, and
callback delay, so it is not a queue-only measurement. These are aggregate
elapsed-time sums and call counts, not histograms. Interpret them alongside
client latency and Python profiles; the instrumented build must never supply
performance claims.

Use this only to attribute behavior, not to compare throughput. Build the
instrumented extension, collect fixed and chunk-heavy H1 rows, then restore the
default extension build:

```sh
uv run --with 'maturin>=1.14,<2' maturin develop --release --features runtime-diagnostics
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)-$(uuidgen)"
uv run --no-sync python scripts/run_http_category_bench.py \
  --workloads fastapi-validated-route fastapi-python-cpu \
  --servers uvicorn-rs-asyncio \
  --duration 3 --warmup 1 --concurrency 32 --repetitions 3 --seed 20261008 \
  --require-runtime-diagnostics \
  --output "benchmarks/results/bridge-diagnostics-${RUN_ID}.json"
uv sync --python 3.12 --locked --group benchmark --group fastapi-benchmark --reinstall-package uvicorn-rs
```

The H1 runner stores a `runtime_diagnostics` object on each Rust row and fails
if the feature did not emit counters. Its throughput and latency values come
from the instrumented build and must not be compared with the ordinary run.
The server also compiles the counters into HTTP/2, HTTP/3, and WebSocket call
paths; their corresponding runners do not currently add counter objects to
their result rows.

For matched per-request ASGI-boundary timings, add
`--asgi-stage-diagnostics`. The runner substitutes
`examples.profile_fastapi:app`, which forwards the same messages and records
FastAPI-call wall time, awaited `receive`/`send` time, ASGI event counts, and
body bytes for both servers. Rust-only counters add interpreter-attach,
Python-loop callback scheduling, response-start/final-body, and full response
queue waits. Every row is marked `timing_valid: false` and
`performance_evidence_status: diagnostic_only`; the added timers perturb the
workload. These values are wall time, not CPU time. `send()` wait is also not
directly comparable across implementations: Uvicorn may wait for transport
drain, while Rust usually queues the message for Hyper and waits only on its
bounded body channel.

Run all 11 FastAPI workloads under both loops and all four server settings:

```sh
uv run --with 'maturin>=1.14,<2' maturin develop --release --features runtime-diagnostics
RUN_ID="$(date -u +%Y-%m-%dT%H%M%SZ)-$(uuidgen)"
uv run --no-sync python scripts/run_http_category_bench.py \
  --workloads fastapi-fixed fastapi-validated-route fastapi-python-cpu \
    fastapi-large-response fastapi-many-response-chunks fastapi-small-response-chunks \
    fastapi-request-upload fastapi-request-upload-small-chunks \
    fastapi-slow-reader-backpressure fastapi-scope-32-headers fastapi-contextvars \
  --servers uvicorn-rs-asyncio uvicorn-asyncio-httptools \
    uvicorn-rs-uvloop uvicorn-uvloop-httptools \
  --duration 2 --warmup 0 --concurrency 64 --repetitions 3 --seed 20261008 \
  --require-runtime-diagnostics --asgi-stage-diagnostics \
  --output "benchmarks/results/bridge-stage-attribution-${RUN_ID}.json"
uv sync --python 3.12 --locked --group benchmark --group fastapi-benchmark --reinstall-package uvicorn-rs
```

The [exact-source boundary diagnosis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md)
shows how to interpret current runtime counters. It records receive/future
counts and response-channel waits for this Rust source. App-boundary timers
and Rust-only internal counters have different meanings; neither should be
treated as a CPU-time decomposition.

## Capture a diagnostic profile on macOS

[`profile_http_workload.py`](../scripts/profile_http_workload.py) runs the
maintained body-checking H1 client with fixed, transfer, streaming, or the same
FastAPI validation and Python-CPU workloads used by the benchmark matrix, then
captures Apple `sample` stacks. Run this separately from normal benchmarks,
using the normal server binary. For example:

```sh
PROFILE_ID="$(date -u +%Y-%m-%dT%H%M%SZ)-$(uuidgen)"
uv run --no-sync python scripts/profile_http_workload.py \
  --server uvicorn-rs --loop uvloop --workload large-response \
  --duration 10 --warmup 1 --concurrency 32 \
  --sample-duration 6 --sample-delay 1 --interval-ms 1 \
  --output-dir "benchmarks/results/profile-${PROFILE_ID}"
```

Repeat into a new directory with `--server uvicorn --http httptools` for the
reference, or change `--workload` to isolate another fixed or streaming path.
The profile accepts all 11 workload names from the upstream FastAPI
matrix: `fastapi-fixed`, `fastapi-validated-route`, `fastapi-python-cpu`,
`fastapi-large-response`, `fastapi-many-response-chunks`,
`fastapi-small-response-chunks`, `fastapi-request-upload`,
`fastapi-request-upload-small-chunks`, `fastapi-slow-reader-backpressure`,
`fastapi-scope-32-headers`, and `fastapi-contextvars`. Run each with
`--server uvicorn-rs --loop asyncio`, then repeat with
`--server uvicorn --http httptools --loop asyncio` to compare the same upstream
FastAPI app, loop, and parser workload. Repeat under `uvloop` as a separate
matched pair. The [exact-source FastAPI diagnosis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md)
summarizes the completed local profiles and separates wall-time stack samples
from on-CPU attribution.
The profiler also accepts `fastapi-upload-1m-write-1k`,
`fastapi-upload-1m-write-16k`, `fastapi-upload-1m-write-256k`, and
`fastapi-upload-1m-write-1m` for the fixed-size upload write-target follow-up.
The runtime identity records FastAPI, Starlette, and Pydantic versions. The
FastAPI profile uses a wrapper that records the duration of the inner ASGI call,
including awaited `send` and `receive` calls, and verifies the unchanged response
body through the normal client gate. This is a profiling-only metric; it helps
separate application-plus-bridge time from end-to-end client latency, but is not
an additive decomposition because the percentile populations and scheduling
overlap. The wrapper's source and output are retained in the profile receipt.
The helper builds its maintained C client before profiling; `--native-client PATH`
reuses an existing executable and records its digest. The output directory must
not already exist. Load duration must include the sample delay, sample duration
and at least two seconds after sampling.

The receipt preserves source snapshots, normal native/client executables,
Python executable/module origins and hashes, exact commands, full client
correctness results, sample PID/interval, stacks and logs. It checks before/after
identity, successful graceful server exit and absence of error diagnostics.
Every receipt is explicitly `profiling_only: true`, `timing_valid: false` and
`performance_evidence_status: not_applicable`: raw client timing is retained for
diagnosis and never enters benchmark medians or rankings.

Sample counts include idle and blocked threads; inclusive/recursive stacks
overlap and cannot be added as CPU percentages. A standalone profile that
locates a copy or GIL wait motivates a candidate. It does not prove that removing
that operation improves speed: require ordinary paired end-to-end benchmarks
and affected parity cases for the exact rebuilt candidate. An optional framework
route also needs its coherent full wheel and live integration gate; profiling a
bare ASGI response does not validate that framework path.

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
