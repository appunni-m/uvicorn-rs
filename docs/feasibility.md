# Feasibility and category benchmark report

## Current correctness evidence (2026-10-07)

The current 490-case behavior inventory passes 490/490 instrumented
attribution cases and three complete 490-case repeats with zero failures,
infrastructure errors, retries or cases not run. Its matrix has 238 public
comparisons and 252 target-only contracts across 70 input files and 71
operations. Coverage is 5,108/5,108 native regions and 3,608/3,608 lines
(100%), with zero unfiltered source-matched MCP gaps and tests passed. The
normal non-instrumented local build passes all 238 public comparisons. The
coverage and parity reports are preserved in [current evidence](coverage.md#current-full-verification-490-cases).

The October 5 category measurements below predate the latest H3 close-code
source and were not rerun for it. They remain evidence for their recorded
binaries only. The current correctness result does not add a performance
claim.

The historical shared-write full gate passed
213/213 live oracle comparisons, all 448 attribution cases and three full
repeats with zero failures, infrastructure errors, retries or cases not run.
That named build measured 4,763/4,763 LLVM regions and 3,360/3,360 lines, with
zero unfiltered MCP gaps, and passed every normal exclusion check and three
selected cases. See [historical coverage evidence](coverage.md#current-full-verification-448-cases)
for exact source/native/report hashes and its lossless archive. Its results do
not attest the changed checkout.

This is default-feature `src/lib.rs` with `cfg(coverage)` on macOS ARM64 in a
dirty checkout. It does not certify Python/dependency coverage, other platforms
or features, full official ASGI conformance, security or performance.

## Current performance position

The [October 5 investigation](performance-investigation-2026-10-05.md) finds
a concrete plaintext H1 copy caused by hidden vectored-write capability and
cross-runtime GIL/scheduler handoffs. The current source retains vectored
forwarding with one borrowed scalar/vectored write handler and the defended
typed H3 clean-close correction. Fixed-key/value caching and a one-worker Tokio
runtime remain unaccepted; common-method caching was drafted only. No accepted
end-to-end optimization speedup is claimed.

The five-category comparison retained 139 completed rows but no qualifying
workload pair; the stock Hypercorn H3 reference crashed. A separate 30-row H1
retry also produced no qualifying pair. Both used matching automatic lifespan
policies and visible reference ERROR logs. The target-only HTTP/3 task-reaping
diagnostic observed median sampled peak RSS of 614.328 MiB before and 33.016 MiB
after across five correct runs per build; its zero valid matched timing pairs
cannot establish a speed improvement. See the [investigation](performance-investigation-2026-10-05.md)
for raw identities, rejected timings, memory limits and reference failure logs.
Earlier 120-sample A/B experiments used Uvicorn lifespan off and CRITICAL
logging; they cannot certify the repaired policies. Measurements below retain
their historical source/build scope.

<a id="correctness-update-2026-10-05"></a>

## Historical correctness update (447 cases; 2026-10-05)

That historical regression, native coverage and normal-build exclusion
verification completed. The 447-case source passed every attribution case and
three complete repeats with zero failures, infrastructure errors, retries, or
cases not run. It records 4,734/4,734 native LLVM regions and 3,333/3,333 lines
(100%); unfiltered Coverage-MCP verifies the same source/build and zero gap
groups. The inventory has 212 oracle-parity cases and 235 target-only
contracts, including two public header-capacity support contracts. This is
default-feature `src/lib.rs` with `cfg(coverage)` on macOS ARM64. The preceding
normal-build audit failed because two inactive service-error diagnostic literals
remained. The corrected source's audit passes every exclusion check and three
selected live cases. Its complete instrumented gate also passed independently.
The extension was restored to that audited normal build at the time. See
[coverage evidence](coverage.md).

The server now completes the HTTP transport after the final ASGI body without
waiting for the application to return. The earlier implementation coupled
response completion to post-response application work. HTTP/1.1 and HTTP/2
live parity cases exposed that delay and passed after the fix while finite
background work still completed under server ownership. The before-fix evidence is
`build/asgi-coverage/final-response-before-app-return-before-fix.json`.

The historical 445-case snapshot recorded 4,719/4,719 regions and 3,329/3,329
lines with zero Coverage-MCP gaps and passed all attribution cases. Two full
repeats passed 445/445; the third had 436 passes, one graceful-drain adapter
infrastructure failure, and eight cases not run. It rejected a global
`Cancelled` connection diagnostic after the active response completed. The
gate remains incomplete. Existing plaintext/TLS cases now retain an idle
partial-preface connection through shutdown; its closure and the narrow
protocol-detection cancellation correction subsequently passed the preceding
full verification.
That changed native passed both cases in a seven-case targeted run, with the
same before/after inputs and harness. This addresses the scoped cancellation
regression; it supplies no throughput, latency, CPU, or memory comparison. This
is now historical evidence: its follow-up full run stopped after 219 attribution
passes when valid large ASGI header collections were found to reach implicit
capacity panics in HTTP response and WebSocket handshake construction. Fallible
header assembly and public target-capacity contracts require another source
measurement; profiles from the interrupted run cannot be merged into it.
The fallible header correction passed nine targeted attribution cases,
including both public capacity support contracts, with no failures or retries.
Same-input before-fix receipts recorded two public contract failures and two
unexpected dependency panic hooks; the before/after audit verifies unchanged
harness, inputs, environment, and Cargo lock. The fresh 447-case full gate
subsequently passed. This correction has not been benchmarked.

The preceding 444-case snapshot recorded 4,717/4,717 regions and 3,328/3,328
lines with zero Coverage-MCP gaps, but its complete gate was incomplete:
attribution had 443 passes and one live Uvicorn TLS WebSocket handshake timeout.
All three full repeats passed 444/444 with zero behavioral or infrastructure
failures. The subsequent listener ownership fix and strengthened plaintext/TLS
shutdown cases required a new gate. The preceding 447-case report independently
supplies that evidence without merging profiles from older sources.

Those stronger shutdown cases exposed a public mismatch before the listener
fix: Rust retained admission while a held response drained; Uvicorn closed its
listener before response release. Both cases otherwise matched full response
bytes, lifecycle events, established-connection close, and process termination.
The defending receipt is
`build/asgi-coverage/listener-admission-before-fix-2026-10-05/parity-result.json`.
The corrected listener ownership passed the strengthened pair in a seven-case
targeted run with zero failures; this subset does not replace the full gate.

The historical 423-case matrix passed three full repeats and reached 100%
default native Rust region and line coverage, verified by Coverage-MCP for its
source/build. Production panic removal, inline-callback handling, and the
application ownership refactor changed that source afterward. The preceding
447-case source/build also passes full regression and coverage verification;
its normal-build audit then failed, requiring the exclusion correction
and its separate passing instrumented measurement. See [coverage results](coverage.md) for each
snapshot's configuration and receipts.

The benchmark rows below predate the response-completion fix and these later
ownership, listener, and panic-policy changes. Their throughput, latency, CPU,
and memory effects require a fresh benchmark on a quiet host after the
completed correctness gate. Correctness coverage does not establish a performance
gain.

<a id="decision"></a>

## Historical decision (October 4 matrix)

The historical October 4 full category matrix is
[`benchmarks/results/full-2026-10-04T113122Z`](../benchmarks/results/full-2026-10-04T113122Z/).
All 338 measured rows passed their correctness gates: H1 132, H2 84, H3 66,
WebSockets 36, and lifespan/shutdown 20. The optional `starlette-rs` H1 route
was omitted because that package was not installed in this benchmark
environment. Focused HTTP, streaming, WebSocket, cancellation, and lifespan
probes passed too.

This is correctness evidence and performance diagnosis, not performance
acceptance evidence. Process snapshots show unrelated parity generation and
validation, compatibility-atlas work, mypy, and Rust compilation during the
matrix; one Rust compilation used about 787% CPU before WebSocket measurements.
Therefore these rows cannot establish a repeatable or uncontended performance
gain. H1 was mixed: Rust+uvloop measured 0.59× Uvicorn's `uvloop + httptools`
rate on fixed responses, but 1.27× on 256 response chunks and 1.40× on small
response chunks. The chunk-heavy candidate used about 2× the server CPU, and
several Python-heavy H1 cases remained slower. H2/H3 compare only with
Hypercorn; they do not establish a Uvicorn comparison. H3 Rust fixed-response
RSS peaked above 250 MiB in this run and needs allocation/lifetime profiling.
See the [run notes](../benchmarks/results/full-2026-10-04T113122Z/run-notes.md)
for every category's medians, latency percentiles, CPU, memory, and raw-file
links.

Keep the project positioned as an independent Rust protocol server with a thin
Python ASGI boundary until a quiet-host rerun and the documented conformance
work are complete. Python owns ASGI application execution, event-loop state,
context, and exceptions; Rust owns protocol and socket work. Immutable
outgoing Python `bytes` use owner-backed PyO3 extraction, and known exact
built-in ASGI event names avoid Rust `String` allocations. The available runs
do not isolate a causal performance gain from those changes. Investigate
bridge/scheduler CPU and large-response memory on an idle host before pursuing
SIMD. The October 5 profiles now identify a concrete native copy and GIL
handoffs; they still do not establish a dominant SIMD-amenable scan.

## Measurement setup and gates

All runs used one machine and environment: Apple M3 Pro, macOS 15.7.7, 12 logical CPUs, CPython 3.12.13, Rust 1.98.1, Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0, and Hypercorn 0.18.0. This is evidence for that environment, not a cross-platform performance claim. CPU percentage is normalized per logical core: 100% is approximately one fully occupied core.

| Category | Matrix and baseline | Correctness gate |
|---|---|---|
| HTTP/1.1 | 12 workloads are configured; the October 4 run measured 11 because the optional `starlette-rs` route was not installed. Four configurations × three repetitions; 2 s samples, 0.25 s warmup, concurrency 64 except slow reader at 8 and exception at 1. The configurations are Rust asyncio/uvloop and Uvicorn asyncio+h11 / uvloop+httptools. | Every measured response status and complete response body matched the workload oracle. The exception workload used 200 responses per sample. |
| HTTP/2 | Seven workloads × four configurations × three repetitions; 2 s, 0.25 s warmup, concurrency 16 except slow reader at 2. Hypercorn asyncio/uvloop is the same-protocol baseline. | TLS ALPN negotiated H2; every response status and byte was checked. Upload responses included the byte count consumed by the app. |
| HTTP/3 | Six workloads, three repetitions, concurrency 4 except slow reader at 2. Hypercorn asyncio/uvloop is the baseline. Hypercorn upload rows are excluded after the baseline failed to return a response to the upload probe. | QUIC/TLS handshake, response status, and every response byte were checked. Four QUIC connections distribute the load, with streams multiplexed on each. |
| WebSocket | Handshake, 32-byte text echo, and 64 KiB binary echo; three repetitions. Echo cases use 32 persistent connections. Handshake is capped at 500 fresh connections per sample at concurrency 1 to bound client ephemeral-port use. | Each handshake checked subprotocol `bench`; every echo message was compared byte-for-byte. |
| Lifespan/shutdown | Five repetitions for Rust asyncio/uvloop and Uvicorn asyncio+h11 / uvloop+httptools. | Startup state, lifespan shutdown completion, and cancellation of a held ASGI request were required in every row. |

The original pre-copy category bundle has per-workload medians for throughput,
p50/p95/p99 latency, server CPU, sampled server RSS, and client CPU where
measured. These links are historical; the fresh rerun is documented below and
its raw rows live in a separate run directory:

- [All workload medians and row counts](../benchmarks/results/category-summary-2026-10-02.json)
- [HTTP/1.1, 144 rows](../benchmarks/results/http-categories-2026-10-02.json)
- [HTTP/2, 84 rows](../benchmarks/results/http2-categories-2026-10-02.json)
- [HTTP/3, 66 rows](../benchmarks/results/http3-categories-2026-10-02.json)
- [WebSockets, 36 rows](../benchmarks/results/websocket-categories-2026-10-02.json)
- [Lifespan and shutdown, 20 rows](../benchmarks/results/lifecycle-categories-2026-10-02.json)

The October 4 rebuilt extension passed the seven focused live-probe groups
recorded in that historical run. A 19-case input-only parity workflow passed in an
earlier run. These cases cover HTTP/1.1, HTTP/2, HTTP/3, streaming, WebSockets,
cancellation/disconnect, lifespan, and represented oracle behavior; the
optional `starlette-rs` route was not installed for this run. They are focused
black-box cases, not a complete official ASGI conformance suite.

<a id="latest-full-rerun-2026-10-04-correctness-passed-performance-provisional"></a>

## Historical full rerun: 2026-10-04 correctness passed, performance provisional

All rows were collected on Apple M3 Pro / macOS 15.7.7 with CPython 3.12.13,
Rust 1.98.1, and the versions listed in the run notes. The release extension
was rebuilt from the worktree recorded for that run and all category correctness gates
passed. The host was not quiet, so report the performance values only as
exploratory observations.

| Category | Rows | Correctness result | Performance comparison |
|---|---:|---|---|
| HTTP/1.1 | 132 | 11 available workloads × four configurations × three repetitions passed; optional `starlette-rs` route omitted. | Uvicorn H1 baseline; mixed workload results, higher candidate CPU in many cases. |
| HTTP/2 | 84 | Seven workloads × four configurations × three repetitions passed; TLS ALPN and response bytes checked. | Hypercorn only; not comparable to Uvicorn. |
| HTTP/3 | 66 | Six represented workloads × four configurations × three repetitions passed; QUIC/TLS and response bytes checked. | Hypercorn only; upload baseline remains excluded. |
| WebSockets | 36 | Handshake/subprotocol and complete text/binary payload checks passed. | Uvicorn baseline; mixed handshake/text/binary results and candidate CPU is higher on echo. |
| Lifespan/shutdown | 20 | Startup state, shutdown, and active ASGI cancellation passed in every row. | Timing observations only; not throughput. |

Representative H1 observations (medians; CPU is normalized per logical core)
show the tradeoff. Rust+uvloop fixed response measured 39,894 req/s,
1.58/2.41/2.85 ms p50/p95/p99, and 139% server CPU; Uvicorn measured 67,882
req/s, 0.81/1.58/1.90 ms, and 94% CPU. On 256 response chunks, Rust measured
2,226 req/s and 29.96/43.60/50.37 ms at 179% CPU; Uvicorn measured 1,748 req/s
and 32.75/37.48/231.77 ms at 88% CPU. These are three-repetition medians
collected amid unrelated CPU work, not accepted speedup claims. The raw rows
and source digests are in [H1](../benchmarks/results/full-2026-10-04T113122Z/http1.json),
[H2](../benchmarks/results/full-2026-10-04T113122Z/http2.json),
[H3](../benchmarks/results/full-2026-10-04T113122Z/http3.json),
[WebSocket](../benchmarks/results/full-2026-10-04T113122Z/websocket.json),
and [lifespan](../benchmarks/results/full-2026-10-04T113122Z/lifecycle.json).
Process snapshots and the full interpretation are linked in the
[run notes](../benchmarks/results/full-2026-10-04T113122Z/run-notes.md).

CPU-normalized throughput further qualifies the raw chunk-rate wins: median
per-sample requests per server core were about 1.22k vs 2.00k for 256 response
chunks and 2.65k vs 3.78k for small response chunks (Rust vs Uvicorn). The
candidate used about twice the server CPU in both cases. The [run notes](../benchmarks/results/full-2026-10-04T113122Z/run-notes.md)
show the calculation and additional workloads; host contention makes these
ratios exploratory too.

The full matrix must be repeated after unrelated CPU-heavy jobs stop. The
run's measured outcomes do not meet the benchmark procedure's idle-host gate.

## Previous full rerun: 2026-10-02; H3 comparison aborted

The run used the documented workload set, fixed seed, category order, and
sample settings. Its release extension was rebuilt from the local checkout;
the lockfile check passed and the optional `starlette-rs` fixture was installed
separately. All per-category raw repetitions and source digests are retained in
the run directory.

| Category | Rows | Gate outcome | Performance status |
|---|---:|---|---|
| HTTP/1.1 | 144 | All 12 workloads, four configurations, and response bodies passed. | Provisional: Rust compilation and Python work overlapped H1 start; large-transfer clients used several cores. |
| HTTP/2 | 84 | TLS ALPN and complete response bodies passed across seven workloads. | Provisional: same-protocol Hypercorn comparison; not a Uvicorn comparison. |
| HTTP/3 comparison | Partial log; no complete JSON | Hypercorn asyncio timed out on four fixed-response requests in repetition 3; the runner aborted by design. | No valid cross-server result. |
| HTTP/3 Rust-only | 36 | Six workloads passed status/body checks under asyncio and uvloop. | Provisional candidate tracking only; Rust compilation overlapped the retry. |
| WebSockets | 36 | Handshake/subprotocol and full text/binary echoes passed. | Provisional: desktop/Python background work was visible at category start. |
| Lifespan/shutdown | 20 | Startup/shutdown passed; every held ASGI task was cancelled. | Provisional: no correctness failures; use the raw five-repetition timings as exploratory evidence. |

The top snapshots before H1 measured two unrelated `rustc` processes at
72.8% and 71.3% CPU and a Python process at 68.2%, with 57.4% total CPU idle.
Before the H3 candidate-only retry, `rustc` used 139.6% CPU and system idle was
41.0%. The emulator showed roughly 6 GiB resident memory and 8.8–18.1% process
CPU across category snapshots. The load client reached 588.8% CPU on the Rust
1 MiB response row and 502.2% on Uvicorn. The results therefore do not meet the
quiet-host gate in [the benchmark procedure](benchmarks.md).

Selected medians from that October 2 run make the performance pattern concrete.
CPU is normalized per core; RSS is the maximum process sample during a row.

| Category and workload | Rust candidate | Reference | Rate ratio |
|---|---|---|---:|
| H1 fixed response | 31,028 req/s; p50/p95/p99 1.954/3.745/4.730 ms; CPU 124.4%; RSS 34.7 MiB | Uvicorn uvloop+httptools: 56,694 req/s; 0.845/2.567/4.020 ms; CPU 90.4%; RSS 33.1 MiB | 0.55× |
| H1 256 × 4 KiB response chunks | 892 req/s; 74.187/94.991/103.323 ms; CPU 208.3%; RSS 33.8 MiB | Uvicorn uvloop+httptools: 1,824 req/s; 33.417/36.066/191.256 ms; CPU 98.3%; RSS 37.0 MiB | 0.49× |
| H1 1 MiB response | 8,629 req/s; 7.310/11.454/13.785 ms; CPU 170.0%; RSS 148.1 MiB | Uvicorn uvloop+httptools: 8,266 req/s; 6.931/13.443/21.486 ms; CPU 84.8%; RSS 33.0 MiB | 1.04× |
| H2 fixed response | 47,036 req/s; 0.330/0.521/0.621 ms; CPU 165.5%; RSS 26.5 MiB | Hypercorn uvloop: 7,229 req/s; 2.197/2.340/2.471 ms; CPU 95.2%; RSS 76.1 MiB | 6.51× |
| H3 fixed response, candidate-only | 18,978 req/s; 0.163/0.455/0.727 ms; CPU 134.2%; RSS 177.2 MiB | No valid baseline | — |
| WebSocket 32-byte text echo | 59,522 msg/s; 0.540/0.798/0.932 ms; CPU 247.0%; RSS 33.5 MiB | Uvicorn uvloop: 71,580 msg/s; 0.445/0.461/0.482 ms; CPU 94.6%; RSS 31.8 MiB | 0.83× |
| WebSocket 64 KiB binary echo | 46,156 msg/s; 0.687/0.969/1.118 ms; CPU 238.4%; RSS 53.9 MiB | Uvicorn uvloop: 31,129 msg/s; 1.009/1.185/1.275 ms; CPU 94.9%; RSS 65.7 MiB | 1.48× |

Rust uvloop's lifespan medians were 62.14 ms to the first lifespan-backed
request, 10.57 ms idle SIGTERM exit, 2.05 ms active-request exit, and 23.5 MiB
RSS. Uvicorn uvloop+httptools measured 77.54 ms, 258.52 ms, 2.19 ms, and 30.2
MiB. The complete per-workload throughput, percentiles, client/server CPU,
RSS, and repetitions are in the [raw H1](../benchmarks/results/full-rerun-2026-10-02T161854Z/http1.json),
[H2](../benchmarks/results/full-rerun-2026-10-02T161854Z/http2.json),
[H3 candidate-only](../benchmarks/results/full-rerun-2026-10-02T161854Z/http3-candidate-only.json),
[WebSocket](../benchmarks/results/full-rerun-2026-10-02T161854Z/websocket.json),
and [lifespan](../benchmarks/results/full-rerun-2026-10-02T161854Z/lifecycle.json)
reports.

### Why H1 is slower in this implementation

This does not show that Rust is slower than Python as a language: both servers
run the same Python ASGI app. Uvicorn's fastest H1 path combines `uvloop` with
the compiled `httptools` parser and keeps network and app scheduling on the
same Python loop. This server puts sockets and protocol work on Tokio/Hyper but
preserves the caller-owned Python event loop for the app. Creating an ASGI task
uses `call_soon_threadsafe`; each application `send()` or `receive()` crosses a
PyO3 method boundary, and Tokio channels carry request/response events between
the runtimes. When the bounded response queue fills, `send()` also awaits a
bridge future. Those operations add work that a small fixed response cannot
hide and that repeats for every streamed chunk.

The current runtime starts two Tokio worker threads in addition to the
Python-owned application loop in the [native module initializer](../src/lib.rs#L4084).
Existing measurements do not isolate whether two workers improve throughput
enough to offset their scheduling and wakeup cost. Compare one and two Tokio
workers on the same fixed-response and chunk-stream workloads before changing
the default.

The chunk-heavy CPU and latency pattern is consistent with this extra
coordination, and earlier queue counters recorded frequent full-channel waits.
The profiles and counters identify work on the path, not exact CPU shares. The
October 4 run does not justify a SIMD optimization: outgoing Python `bytes` are
already owner-backed on extraction into Rust, while SIMD cannot remove Python
ASGI object creation, the GIL, scheduling, Tokio wakeups, or per-send
backpressure. Incoming request bytes still must be materialized as Python
`bytes` to satisfy ASGI. The next step is a genuinely quiet, release-mode
fixed/chunk H1 profile plus allocation/lifetime profiling for the 1 MiB
response, followed by measured changes and another correctness-gated A/B run.

## Previous full matrix attempt: correctness passed with a failed H3 baseline gate

The run at
[`benchmarks/results/full-provisional-20261002T151807Z`](../benchmarks/results/full-provisional-20261002T151807Z/)
reused the documented 2-second samples, 0.25-second warmup, fixed seed, and
category-specific concurrency. It rebuilt the benchmark-only environment with
the adjacent `starlette-rs` checkout installed separately, then passed all
seven targeted live probe scripts (17 `PASS` lines).

| Category | Rows saved and checked | Gate outcome | Performance use |
|---|---:|---|---|
| HTTP/1.1 | 144 | All statuses and response bodies passed across 12 workloads and four configurations. | Provisional only: a Pillow benchmark overlapped the category; the start time is unknown. |
| HTTP/2 | 84 | TLS ALPN and full response bodies passed across seven workloads. | Provisional only: FastAPI-RS validation/indexing overlapped samples. |
| HTTP/3 comparison | Partial log; no complete JSON | Hypercorn uvloop failed four warm-up responses with empty bodies where the app expected 14 bytes. The runner aborted as designed. | No cross-server result. |
| HTTP/3 Rust-only | 36 | All six candidate workloads passed status/body checks. | Candidate tracking only; Pillow parity and Rust compilation overlapped. |
| WebSockets | 36 | Handshakes, subprotocol, text echo, and binary echo passed. | Provisional only: Pillow migration parity and input generation overlapped. |
| Lifespan/shutdown | 20 | Startup/shutdown passed, and every active request task was cancelled. | Provisional only: unrelated parity work overlapped. |

The per-category source digests, raw rows, runner logs, process snapshots, and
the detailed explanation are in the run directory's
[`run-notes.md`](../benchmarks/results/full-provisional-20261002T151807Z/run-notes.md).
The H3 comparison failure is preserved in
[`http3.log`](../benchmarks/results/full-provisional-20261002T151807Z/http3.log);
the Rust-only report is separate in
[`http3-candidate-only.json`](../benchmarks/results/full-provisional-20261002T151807Z/http3-candidate-only.json).

The following representative medians come from this attempt. Performance rows
use three 2-second repetitions; lifespan uses five. Percent CPU is server
process CPU, where 100% is one logical core. The host was shared throughout the
matrix, so these figures describe exploratory samples, not a server win.

| Category and workload | Rust candidate: rate; p50/p95/p99; CPU; RSS | Reference: rate; p50/p95/p99; CPU; RSS | Reference |
|---|---|---|---|
| H1 fixed response | 45,208 req/s; 1.386/2.185/2.743 ms; 139.1%; 31.2 MiB | 72,751 req/s; 0.840/1.405/1.704 ms; 97.8%; 31.9 MiB | Uvicorn uvloop + httptools |
| H1 256 × 4 KiB response chunks | 793 req/s; 83.684/103.967/112.581 ms; 179.6%; 34.1 MiB | 1,754 req/s; 33.503/38.397/225.556 ms; 87.5%; 35.9 MiB | Uvicorn uvloop + httptools |
| H2 fixed response | 46,000 req/s; 0.337/0.538/0.663 ms; 163.0%; 26.7 MiB | 7,320 req/s; 2.173/2.362/2.519 ms; 95.0%; 76.4 MiB | Hypercorn uvloop |
| H3 protocol-scope | 11,311 req/s; 0.317/0.597/0.923 ms; 122.8%; 120.4 MiB | No complete baseline in this attempt | Rust-only H3 matrix |
| WebSocket handshake | 6,899/s; 0.127/0.223/0.288 ms; 58.6%; 27.1 MiB | 3,804/s; 0.247/0.363/0.451 ms; 70.5%; 32.6 MiB | Uvicorn uvloop + websockets |
| WebSocket 32-byte text echo | 59,607/s; 0.540/0.799/0.927 ms; 249.2%; 32.0 MiB | 72,802/s; 0.439/0.458/0.490 ms; 95.2%; 31.8 MiB | Uvicorn uvloop + websockets |
| WebSocket 64 KiB binary echo | 38,191/s; 0.793/1.367/1.817 ms; 222.0%; 58.9 MiB | 29,677/s; 1.050/1.246/1.410 ms; 94.6%; 73.4 MiB | Uvicorn uvloop + websockets |
| Lifespan/shutdown timings | 47.36 ms startup; 10.55 ms idle exit; 2.05 ms active exit; 23.6 MiB | 73.32 ms startup; 208.63 ms idle exit; 2.18 ms active exit; 30.5 MiB | Uvicorn uvloop + httptools |

The H1 direction matches prior runs: fixed and context-heavy requests are
slower under Rust, response chunk streams lag by roughly 2×, and the Rust
process uses more CPU. The client CPU, full percentiles, and every workload
median are in the raw category reports, including
[`http1.json`](../benchmarks/results/full-provisional-20261002T151807Z/http1.json),
[`http2.json`](../benchmarks/results/full-provisional-20261002T151807Z/http2.json),
[`http3-candidate-only.json`](../benchmarks/results/full-provisional-20261002T151807Z/http3-candidate-only.json),
[`websocket.json`](../benchmarks/results/full-provisional-20261002T151807Z/websocket.json),
and [`lifecycle.json`](../benchmarks/results/full-provisional-20261002T151807Z/lifecycle.json).

No “Rust is faster than Python” conclusion follows from these results. The
measured comparison is between two servers executing the same Python app:
Uvicorn uses `uvloop + httptools` on one Python loop, while this prototype
combines Tokio/Hyper networking with the app's Python loop. The outgoing
Python `bytes` to Rust `Bytes` conversion is already owner-backed and
zero-copy. The measured code still schedules each ASGI task through
`call_soon_threadsafe`; full response-body channels turn sends into awaited
PyO3/Tokio futures. Prior diagnostic runs found frequent full-channel sends in
the 256-chunk workload, but they used a different source digest and are not
quantitative attribution for this run. SIMD would not remove those task,
cross-runtime, or backpressure handoffs. The incoming ASGI request body and
some scope/WebSocket fields still require Python `bytes` construction.

The next performance acceptance run needs a quiet host for the entire matrix.
Do not infer an improvement from H2/H3 versus Hypercorn or candidate-only H3,
and do not publish these provisional samples as a repeatable gain.

## Earlier full rerun: event-type fast path, contaminated host

The full five-category matrix is saved in
[`benchmarks/results/full-event-type-fastpath-2026-10-02T142406Z`](../benchmarks/results/full-event-type-fastpath-2026-10-02T142406Z/).
All files have the expected row counts, unique workload/configuration/repetition
keys, and zero correctness failures: H1 144, H2 84, H3 66, WebSockets 36, and
lifecycle 20. The H3 baseline now passes its represented workloads on both
asyncio and uvloop; the known failing Hypercorn H3 upload cases are excluded.
The five benchmark files include per-workload medians and raw rows, alongside
the logs and environment snapshot. The seven targeted live probes passed before
the matrix. Afterward, the HTTP bridge probe was extended to cover standard
event names carried by a `str` subclass, and it passed against the corrected
fallback. The follow-up Rust change only restores dispatch for known standard
names wrapped in a `str` subclass; the exact built-in event-name path used by
the benchmark workloads is unchanged. All seven live probes were rerun on that
then-measured source afterward; their output is saved in the
[probe log](../benchmarks/results/full-event-type-fastpath-2026-10-02T142406Z/live-probes-after-subclass-fallback.log).

The environment record captured a separate `image-slash-star` test process at
687.4% CPU and concurrent Rust compilation/doc jobs. Several load clients also
used multiple cores. This is a complete correctness run but an invalid basis
for stable throughput/latency claims. The medians below are useful for locating
workloads to profile; do not interpret them as causal changes from the event
type optimization.

| H1 workload | Uvicorn uvloop + httptools: req/s; p50/p95 ms; CPU; RSS | Rust uvloop: req/s; p50/p95 ms; CPU; RSS |
|---|---:|---:|
| Fixed 12-byte response | 50,214; 0.96/2.81; 87.2%; 32.5 MiB | 41,699; 1.51/2.30; 134.7%; 32.4 MiB |
| 1 MiB response | 9,913; 4.65/11.86; 87.8%; 32.8 MiB | 8,837; 7.14/11.39; 172.0%; 124.2 MiB |
| 256 × 4 KiB response chunks | 1,843; 33.23/34.94; 98.6%; 35.4 MiB | 871; 76.06/93.60; 204.1%; 34.3 MiB |
| 128 × 512 B response chunks | 3,670; 16.97/20.98; 96.2%; 32.6 MiB | 1,646; 39.10/52.94; 185.6%; 30.4 MiB |

The same run's H2 fixed response measured 47,154 requests/s and 0.33 ms p50
for Rust uvloop, versus 7,153 requests/s and 2.21 ms for Hypercorn uvloop;
Rust server CPU was 166% versus 95%. This is a same-protocol Hypercorn
comparison, not Uvicorn parity, and it was collected under the same host load.
H3, WebSocket, and lifecycle results are available in their full per-row JSON
files; the load-contaminated H3 comparison must likewise not be treated as a
stable speed claim.

### Why HTTP/1.1 is slower in the available measurements

This is not a controlled comparison of Rust against Python as languages. The
fast Uvicorn baseline is `uvloop + httptools`: a libuv-based event loop and a
compiled HTTP parser, with ASGI execution on one Python asyncio loop. This
server uses Tokio and Hyper for networking, then crosses into the app's Python
loop for each ASGI invocation and for every request/response event. A fixed
12-byte response has almost no payload work to accelerate; scope and message
creation, Python task scheduling, GIL access, cross-runtime wakeups, channel
synchronization, Hyper framing, and socket I/O dominate its cost. The Rust
server does not replace Python application work: the app remains Python and
runs under the same interpreter constraints.

The 256-chunk response makes that boundary visible. Each of the 256 ASGI
`send()` calls must keep its order and apply backpressure. The queue diagnostic
measured 224 full-channel waits per response at capacity one and 61 at capacity
four; each wait includes bridge scheduling as well as queue delay. Capacity
four changes the measured mechanism, but the latest response-streaming H1
median still trails Uvicorn under a contaminated host. SIMD parsing cannot
remove those app-visible sends or their scheduler/channel coordination.

Copy reduction has a narrower impact than first expected. PyO3 can retain the
owner of immutable outgoing Python `bytes`, so no payload copy occurs at that
extraction boundary. The common built-in ASGI event-name path also avoids a
small Rust `String` allocation. Neither change removes Python `bytes`
construction for incoming ASGI request bodies, scope allocation, message/task
creation, or `send()`/`receive()` wakeups. A known-name comparison and a
payload-copy optimization should not be assumed to improve a request-bound
benchmark unless profiling finds them on its dominant path.

Evidence still cannot assign exact CPU shares. Earlier sampling shows
`AsgiIo.send`, `call_soon_threadsafe`, Tokio channels, Hyper polling, and socket
writes on the path, but the sample is not a statistical flame-graph
attribution. That October 2 full matrix ran while an unrelated test process
used 6.9 cores; the 1 MiB loopback load client also reached 555% CPU for Rust
and 367% for Uvicorn. A proper maximum-performance pass needs an idle host,
interleaved repetitions, and preferably a separate load-generator host for
large transfers. Then collect a release CPU profile, per-request
allocation/lifetime data, and writer/backpressure timing before changing
runtime worker count, parser, or transport batching. The large-response RSS
gap is real in the process samples, but the measurements do not identify which
allocations remain live.

## Previous full rerun: four-item response queue

The earlier four-item-queue run is archived at
[`benchmarks/results/full-queue4-2026-10-02T135820Z`](../benchmarks/results/full-queue4-2026-10-02T135820Z/).
HTTP/1.1 (144 rows), H2 (84), WebSockets (36), and lifecycle (20) each have
unique workload/configuration/repetition keys and zero correctness failures.
H3's cross-server attempt stopped at Hypercorn's warmup gate after four request
timeouts; the log is preserved in
[`http3.log`](../benchmarks/results/full-queue4-2026-10-02T135820Z/http3.log).
The separate 36-row Rust-only H3 matrix passed, but provides no Hypercorn
comparison. All seven focused live probes passed on the same queue-four
extension build immediately before this run.

This was a correctness-complete run, not an idle-host performance run. Its
environment snapshot records an Android emulator at 8.9% CPU and an unrelated
Rust compilation process at capture time. Use the numbers as diagnostics; a
clean, interleaved rerun is still needed for a repeatable performance claim.
The candidate and baseline used the same app, Python version, load clients,
machine, concurrency, and correctness gates. Each category randomized server
order by the fixed seed.

| H1 workload | Uvicorn uvloop + httptools: req/s; p50/p95 ms; CPU; RSS | Rust uvloop: req/s; p50/p95 ms; CPU; RSS | Rust rate ratio |
|---|---:|---:|---:|
| Fixed 12-byte response | 60,516; 0.856/1.957; 91.6%; 32.9 MiB | 31,994; 1.894/3.179; 131.6%; 32.5 MiB | 0.53× |
| 1 MiB response | 9,348; 5.931/12.230; 89.3%; 33.5 MiB | 7,946; 7.992/12.336; 187.3%; 135.4 MiB | 0.85× |
| 256 × 4 KiB response chunks | 1,760; 33.251/39.097; 88.4%; 36.7 MiB | 804; 81.083/100.316; 200.8%; 34.1 MiB | 0.46× |
| 128 × 512 B response chunks | 3,691; 16.997/18.135; 98.1%; 32.6 MiB | 1,692; 39.143/54.003; 193.1%; 29.8 MiB | 0.46× |
| 64 KiB upload in 1 KiB pieces | 3,381; 15.523/43.572; 40.4%; 101.0 MiB | 4,862; 12.744/19.356; 107.9%; 86.2 MiB | 1.44× |

The four-item queue continues to reduce the full-channel rate seen in the
instrumented run, but the full matrix shows H1 fixed, large, and chunked
responses remain slower and use more Rust server CPU. The small-chunk upload
is a workload-specific throughput/latency win at higher Rust CPU; it does not
change the overall H1 result. Large-response client CPU was high for both
servers (427% Rust and 566% Uvicorn), so that transfer comparison is partly
client-limited. The Rust RSS gap on 1 MiB responses remains open.

H2 is compared with Hypercorn because Uvicorn does not serve H2. Representative
uvloop medians were:

| H2 workload | Hypercorn: req/s; p50 ms; CPU; RSS | Rust: req/s; p50 ms; CPU; RSS |
|---|---:|---:|---:|
| Fixed response | 7,022; 2.205; 94.8%; 78.0 MiB | 48,747; 0.317; 168.5%; 26.7 MiB |
| 1 MiB response | 362; 44.311; 95.8%; 179.3 MiB | 2,160; 6.599; 150.1%; 27.5 MiB |
| 256 × 4 KiB chunks | 298; 53.445; 97.4%; 85.3 MiB | 571; 27.818; 253.3%; 26.6 MiB |

These rates are end-to-end loopback results, not isolated server efficiency;
the Rust client used about 116% CPU on fixed H2 and 295% on the 1 MiB H2
response. H2 correctness passed across all 84 rows.

WebSocket handshakes measured 6,157/s for Rust vs 4,398/s for Uvicorn
(p50 0.143 vs 0.213 ms, CPU 76.9% vs 73.8%). Text echo measured 55,910 vs
71,628 messages/s (p50 0.562 vs 0.432 ms, CPU 241% vs 94.4%). The 64 KiB
binary echo measured 24,234 vs 28,544 messages/s (p50 0.952 vs 1.095 ms,
CPU 148.9% vs 94.8%). These 36 message/handshake rows all passed payload and
subprotocol checks. They show workload-specific tradeoffs, not a general
WebSocket win.

All 20 lifecycle rows passed, including active-task cancellation. Rust uvloop
medians were 46.5 ms startup-to-first-response, 10.5 ms idle SIGTERM exit,
2.03 ms active SIGTERM exit, and 23.6 MiB sampled RSS. Uvicorn uvloop+httptools
measured 73.1 ms, 242.3 ms, 2.16 ms, and 30.5 MiB respectively.

## Previous full rerun and its limits (one-item response queue)

The fresh run is archived under
[`benchmarks/results/full-2026-10-02T124926Z`](../benchmarks/results/full-2026-10-02T124926Z/).
It used the M3 Pro / CPython 3.12.13 environment above, a fixed seed, three
repetitions per performance workload, and correctness checks on every response
or message. The run saved 320 valid rows: HTTP/1.1 144, HTTP/2 84, HTTP/3
candidate-only 36, WebSockets 36, and lifecycle 20. All seven focused live
probes also passed. The files include raw rows, per-workload medians, logs,
source digests, and process snapshots.

This was not an idle-host performance run. Process snapshots at category start
show unrelated CPU-heavy local jobs (including a parity/build task and an
emulator). This makes the run useful for correctness and diagnosis, but not a
clean claim of repeatable throughput. Re-run on an otherwise idle host before
making a release or deployment decision. The H3 comparison runner correctly
aborted on Hypercorn response timeouts/empty response bodies under both loop
choices; see the [partial-run log](../benchmarks/results/full-2026-10-02T124926Z/http3-attempt-1-failure.txt),
[asyncio reproduction](../benchmarks/results/full-2026-10-02T124926Z/h3-hypercorn-asyncio-isolated.log),
and [uvloop reproduction](../benchmarks/results/full-2026-10-02T124926Z/h3-hypercorn-uvloop-isolated.log).
The H3 port allocator was corrected to check TCP and UDP before selecting its
shared port, but baseline failures continued after that correction. The
[36-row Rust-only H3 report](../benchmarks/results/full-2026-10-02T124926Z/http3-candidate-only.json)
is candidate evidence only, not a Hypercorn comparison.

### HTTP/1.1 against Uvicorn

Each cell shows median requests/s; p50/p95/p99 latency in milliseconds;
server CPU percent; and sampled RSS. Uvicorn uses `uvloop + httptools`; Rust
uses uvloop. 100% CPU is roughly one logical core. The client CPU samples are
in the linked raw report; bulk-transfer samples are especially client-CPU
constrained.

| Workload | Uvicorn rate; p50/p95/p99; CPU; RSS | Rust rate; p50/p95/p99; CPU; RSS | Rust throughput ratio |
|---|---:|---:|---:|
| Fixed 12-byte response | 64,217; 0.870/1.721/2.479 ms; 94.3%; 32.3 MiB | 36,049; 1.674/2.903/4.009 ms; 132.7%; 31.7 MiB | 0.56× |
| 1 MiB response | 11,712; 4.834/9.161/12.331 ms; 96.5%; 33.0 MiB | 9,396; 6.762/10.707/12.976 ms; 192.3%; 128.6 MiB | 0.80× |
| 256 × 4 KiB response chunks | 1,711; 34.587/38.359/250.017 ms; 88.2%; 37.2 MiB | 228; 278.041/359.656/378.564 ms; 210.5%; 31.0 MiB | 0.13× |
| 128 × 512 B response chunks | 3,568; 17.812/18.259/20.353 ms; 98.6%; 32.4 MiB | 494; 131.944/161.779/173.437 ms; 203.3%; 29.5 MiB | 0.14× |

The [full H1 report](../benchmarks/results/full-2026-10-02T124926Z/http1.json)
has all 12 workloads, four server configurations, and three repetitions. The
direct `Bytes` extraction change reduced copying and improved the earlier
large-response RSS substantially, but latest sampled RSS was still 128.6 MiB
for Rust vs 33.0 MiB for Uvicorn on the 1 MiB response workload. Here the load
client used about 506% CPU for Rust and 313% for Uvicorn, so that throughput
comparison is not server-isolated. The [environment and process snapshot](../benchmarks/results/full-2026-10-02T124926Z/environment.txt)
document host activity.

### HTTP/2 and HTTP/3

Uvicorn is not an H2/H3 baseline. H2's latest correctness-gated comparison is
with Hypercorn; the table shows median rate, p50 latency, and server CPU:

| H2 workload | Hypercorn uvloop: rate; p50/p95/p99; CPU; RSS | Rust uvloop: rate; p50/p95/p99; CPU; RSS |
|---|---:|---:|
| Fixed response | 7,124 req/s; 2.226/2.395/2.539 ms; 95.9%; 76.4 MiB | 48,628 req/s; 0.319/0.510/0.613 ms; 170.3%; 26.9 MiB |
| 1 MiB response | 348 req/s; 45.738/49.607/51.847 ms; 97.5%; 177.3 MiB | 2,296 req/s; 6.608/8.836/10.265 ms; 157.2%; 27.6 MiB |
| 256 × 4 KiB response chunks | 293 req/s; 54.591/58.332/61.190 ms; 97.8%; 87.3 MiB | 331 req/s; 47.983/54.778/61.800 ms; 246.9%; 27.0 MiB |

See all 84 rows in the [H2 raw report](../benchmarks/results/full-2026-10-02T124926Z/http2.json).
The Rust client used 115% CPU on the fixed case and 295% on the large response;
these are whole-host loopback results and need a client-capacity-controlled
rerun before interpreting the large response as server-only gain.

H3's candidate-only uvloop medians (rate; p50/p95/p99; CPU; RSS) were 23,434
req/s; 0.161/0.262/0.339 ms; 147.3%; 215.5 MiB fixed, 314 req/s;
12.544/18.680/21.145 ms; 136.1%; 58.5 MiB for 1 MiB, and 169 req/s;
21.523/39.965/46.680 ms; 143.0%; 29.3 MiB for 256 response chunks. They passed
body equality, but without a passing Hypercorn baseline they show no relative
performance result. H3 candidate data is in
[`http3-candidate-only.json`](../benchmarks/results/full-2026-10-02T124926Z/http3-candidate-only.json).

### WebSockets and lifecycle

WebSocket results compare with Uvicorn's uvloop/websockets configuration:

| WebSocket workload | Uvicorn rate; p50/p95/p99; CPU; RSS | Rust rate; p50/p95/p99; CPU; RSS |
|---|---:|---:|
| Fresh handshake | 3,912/s; 0.229/0.405/0.553 ms; 66.0%; 33.1 MiB | 6,633/s; 0.130/0.221/0.347 ms; 79.5%; 27.5 MiB |
| 32-byte text echo | 63,214/s; 0.462/0.754/1.090 ms; 92.6%; 33.4 MiB | 42,067/s; 0.709/1.310/1.647 ms; 213.5%; 33.7 MiB |
| 64 KiB binary echo | 21,528/s; 1.404/2.190/2.774 ms; 92.4%; 73.6 MiB | 25,616/s; 1.217/1.993/2.370 ms; 207.6%; 56.3 MiB |

All 36 WebSocket rows passed payload checks; see the [raw report](../benchmarks/results/full-2026-10-02T124926Z/websocket.json).
The throughput wins are workload-specific and cost more server CPU.

All 20 lifecycle rows passed, including active-request cancellation. The Rust
uvloop medians were 49.89 ms cold start to first lifespan-backed response,
8.85 ms idle SIGTERM exit, 2.03 ms active SIGTERM exit, and 24.2 MiB sampled
RSS. Uvicorn uvloop+httptools measured 78.05 ms, 233.12 ms, 2.18 ms, and 31.6
MiB respectively. See the [lifecycle report](../benchmarks/results/full-2026-10-02T124926Z/lifecycle.json).

### Why the Rust H1 path is slower

This is not an isolated Rust-vs-Python language test. Both servers execute the
same Python ASGI app. Uvicorn's strongest H1 path combines Python with uvloop
and the compiled `httptools` parser in one Python event-loop architecture. This
server's socket and HTTP work run on Tokio/Hyper, while the ASGI app must still
run on its owning asyncio/uvloop loop under the GIL. Every request therefore
needs the Python scope/app/task boundary plus coordination between two
runtimes.

The sampled candidate profiles include `AsgiIo.send`'s PyO3 trampoline,
Tokio channel operations, `pyo3_async_runtimes::future_into_py`, Python
`call_soon_threadsafe`, Hyper's body dispatcher, and TCP writes. The profile
shows those frames in the path; it does not quantify their aggregate CPU
share. See the [fixed-response profile](../benchmarks/results/full-2026-10-02T124926Z/profile-fixed-uvicorn-rs-uvloop.sample.txt)
and [chunk-heavy profile](../benchmarks/results/full-2026-10-02T124926Z/profile-many-response-chunks-uvicorn-rs-uvloop.sample.txt).
Profiled throughput is deliberately kept separate from the unprofiled tables.

To quantify the channel behavior, I also built the compile-time opt-in
`runtime-diagnostics` feature and ran three repetitions of fixed and 256-chunk
H1 workloads. The [24-row diagnostic run](../benchmarks/results/bridge-diagnostics-2026-10-02-final.json)
passed every body check. It includes warmup requests in its counters, and its
instrumented throughput is not a normal performance result.

| Rust uvloop workload | Response queue capacity | Body messages per response | Full sends per response | Full sends | Accumulated full-send wait per response | Measured p50 |
|---|---:|---:|---:|---:|---:|---:|
| Fixed response, capacity-1 run | 1 | 1 | 0 | 0% | 0 ms | 2.223 ms |
| 256 × 4 KiB chunks, capacity-1 run | 1 | 256 | 224 | 87.3% | ~206 ms | 244.8 ms |
| 256 × 4 KiB chunks, capacity-4 run | 4 | 256 | 61 | 23.8% | ~68.8 ms | 79.6 ms |

For a full channel, one `future_into_py` send future is created. Its measured
elapsed time starts after `try_send` reports `Full` and ends once channel
capacity is available. That includes bridge scheduling as well as queue delay;
it is not a measurement of pure queue residence. Fixed responses had one
`call_soon_threadsafe` ASGI task schedule per request, an immediate request
receive, and no response-body full events. Thus streaming has repeated
backpressure-bridge waits, while the fixed-request regression remains even
without those waits.

For a fixed response, the 12-byte payload is too small for byte-copy or SIMD
work to dominate. Per-request scope construction, task setup, GIL-mediated
Python execution, synchronization, and event-loop handoffs are a larger share
of the work. For a 256-chunk response, every chunk is a separate ASGI
`http.response.body` send. Rust extracts immutable Python `bytes` without a
payload copy, but it still must preserve each send's order and backpressure.
The original one-item diagnostic run found about 87% of body sends hit the
channel's full case and await a Rust future exposed through the Python async
bridge. The aggregate measured full-send wait was about 206 ms per response.
This points to per-chunk flow-control coordination as a contributor to
streaming latency, although the timing includes async bridge scheduling.

As a focused optimization, the response-body channel was raised from one to
four pending chunks; the request-body channel remains at one. The ordinary
follow-up is archived at
[`benchmarks/results/response-queue4-2026-10-02/http1.json`](../benchmarks/results/response-queue4-2026-10-02/http1.json)
and includes 36 H1 rows across four server configurations, with three
repetitions per workload and all response correctness gates passing. On the
256-chunk case Rust uvloop measured 731 requests/s and 88.1/119.0 ms p50/p95;
Uvicorn uvloop+httptools measured 1,646 requests/s and 33.3/40.6 ms. Rust is
still about 2.25× behind on throughput and 2.65× slower at p50. The queue-one
and queue-four ordinary runs were not interleaved A/B samples, so the apparent
~3.2× throughput and ~3.2× p50 improvement is directional. In the separate
instrumented queue-four follow-up, queue-full events fell from 87.3% to 23.8%
and accumulated wait from ~206 ms to ~68.8 ms per response. This confirms the
mechanism changed as intended; it does not establish that queue depth alone
caused the ordinary performance delta.

The queue-four ordinary run also measured fixed responses at 41,009 vs 68,196
requests/s, p50 1.46 vs 0.84 ms, and server CPU 137% vs 96% (Rust vs Uvicorn).
For 1 MiB responses it measured 8,468 vs 10,125 requests/s, p50 7.53 vs
5.62 ms, CPU 190% vs 96%, and RSS 125.6 vs 34.0 MiB. The loopback client used
464% CPU on Rust's large-response rows and 287% on Uvicorn's, limiting how much
of that throughput comparison can be attributed to server CPU alone. These are
focused results, not evidence of a general speedup.

The known event-name copy has now been removed from the common path: exact
built-in Python strings are compared with cached interned ASGI names. Unknown
names and `str` subclasses still extract to a Rust `String`, then use the same
Rust event dispatch, preserving the old conversion behavior. A probe covers
known HTTP event names on a `str` subclass with an overridden `__eq__`. This
small metadata optimization does not remove the ASGI dictionary lookup, Python
call, event-loop wakeup, or channel work. Its targeted and full measurements
ran under external CPU load and do not show a causal performance gain. An
earlier PyO3 `to_cow()` attempt was reverted because `abi3-py39` still encodes
and copies for Python 3.9.

The next optimization should target one measured boundary cost while preserving
app-loop ownership, context, exception behavior, and bounded backpressure.
Existing counters show that four response queue slots reduce chunk-stream full
sends from 224 to 61 per 256-chunk response, but do not explain the full
latency. Add boundary-focused CPU and allocation/lifetime profiles, then run a
clean interleaved A/B matrix with client CPU below saturation. More SIMD or
lower-level socket tuning is premature until profiles show dominant
vectorizable byte processing or syscalls. The large-response RSS gap remains
unexplained: owner-backed extraction avoids an outgoing payload copy, while
the current run measured 124.2 MiB Rust RSS versus 32.8 MiB Uvicorn RSS under
host/client contention. RSS alone does not identify retained allocations.

## HTTP/1.1 categories

These older category results are the pre-PyO3-extraction baseline. Each cell reports median requests/s; p50/p95/p99 milliseconds; server CPU; sampled peak server RSS. They are retained for historical context; the October 4 run above is a later historical category rerun. The JSON report includes both asyncio configurations.

| Workload | Uvicorn uvloop + httptools | uvicorn-rs uvloop |
|---|---:|---:|
| Fixed 12-byte response | 75,641; 0.80/1.41/1.63; 96.5%; 31.4 MiB | 45,482; 1.40/2.11/2.49; 136.5%; 30.3 MiB |
| 1 MiB response | 13,869; 4.14/8.15/11.33; 93.5%; 32.8 MiB | 8,050; 7.78/12.36/15.57; 190.3%; 466.3 MiB |
| 256 × 4 KiB response chunks | 1,867; 32.82/34.16/186.20; 98.7%; 35.2 MiB | 283; 228.18/277.97/289.74; 229.1%; 31.3 MiB |
| 128 × 512 B response chunks | 3,883; 16.17/16.47/32.45; 97.2%; 31.4 MiB | 555; 117.86/144.65/162.52; 221.1%; 30.2 MiB |
| 1 MiB request upload | 4,231; 14.85/18.61/20.77; 98.0%; 227.5 MiB | 2,737; 23.21/26.73/33.13; 198.8%; 87.5 MiB |
| 64 KiB upload in 1 KiB pieces | 4,740; 11.78/34.50/65.56; 58.9%; 84.9 MiB | 5,987; 10.31/16.16/19.43; 120.0%; 83.7 MiB |
| Slow reader, 1 MiB response | 25.86; 307.63/314.23/315.92; 1.9%; 32.3 MiB | 25.89; 307.77/312.66/312.84; 12.7%; 26.3 MiB |
| 32 request headers | 39,179; 1.59/1.69/3.21; 97.8%; 33.5 MiB | 30,376; 2.09/3.16/3.75; 130.2%; 30.3 MiB |
| ContextVar | 70,069; 0.88/1.44/1.78; 98.2%; 32.9 MiB | 39,240; 1.53/2.82/3.97; 136.3%; 31.2 MiB |
| Synchronous callable returning awaitable | 60,419; 0.81/2.13/3.98; 91.2%; 34.0 MiB | 32,935; 1.80/3.40/4.50; 122.1%; 34.6 MiB |
| Exception to HTTP 500 | 5,817; 0.14/0.22/0.32; 4.5%; 31.8 MiB | 2,980; 0.31/0.38/0.46; 15.1%; 24.4 MiB |
| One `starlette-rs` route | 12,168; 5.20/8.76/11.11; 81.9%; 35.7 MiB | 18,778; 3.33/5.38/6.40; 118.5%; 34.5 MiB |

The small-upload and single `starlette-rs` route are workload-specific wins in this run, at higher server CPU. The fixed path still loses to Uvicorn's optimized configuration, and the response-streaming results are large, repeatable regressions. The exception case is a low-concurrency fixed-count microbenchmark, not a saturated throughput comparison.

## HTTP/2 and HTTP/3 categories

The table below is from the original historical category bundle. The latest
rerun is shown above; its H2 output belongs to that source, while its H3 output is
candidate-only because the Hypercorn baseline failed correctness.

Each cell reports median requests/s; p50/p95/p99 milliseconds; server CPU; sampled peak server RSS. These comparisons use Hypercorn's matching protocol implementations; they are not comparisons against Uvicorn.

| Protocol workload | Hypercorn uvloop | uvicorn-rs uvloop |
|---|---:|---:|
| H2 protocol scope | 7,359; 2.16/2.28/2.39; 95.3%; 75.8 MiB | 51,394; 0.31/0.47/0.54; 170.1%; 26.5 MiB |
| H2 fixed response | 7,259; 2.18/2.34/2.52; 95.7%; 76.3 MiB | 50,052; 0.31/0.49/0.57; 172.7%; 26.5 MiB |
| H2 1 MiB response | 353; 45.19/48.63/50.37; 96.6%; 186.4 MiB | 2,560; 6.13/7.45/8.61; 170.6%; 99.9 MiB |
| H2 256 × 4 KiB chunks | 306; 52.05/56.82/66.76; 96.4%; 89.0 MiB | 354; 45.13/58.79/65.10; 242.3%; 27.8 MiB |
| H2 1 MiB upload | 394; 39.96/46.11/60.92; 96.8%; 86.3 MiB | 1,277; 12.50/14.49/15.83; 240.4%; 43.2 MiB |
| H2 64 KiB upload in 1 KiB pieces | 1,297; 7.81/45.13/53.64; 95.0%; 85.1 MiB | 1,481; 10.62/12.34/13.97; 232.3%; 31.8 MiB |
| H2 slow reader at 4 MiB/s | 7.96; 252.39/252.92/252.92; 5.4%; 92.5 MiB | 7.96; 250.97/251.92/251.92; 6.8%; 26.0 MiB |
| H3 protocol scope | 2,573; 1.45/1.77/2.00; 75.9%; 88.8 MiB | 26,015; 0.14/0.24/0.30; 155.0%; 234.8 MiB |
| H3 fixed response | 2,625; 1.42/1.65/1.87; 76.7%; 88.5 MiB | 30,127; 0.13/0.18/0.21; 164.2%; 269.5 MiB |
| H3 1 MiB response | 53; 56.76/116.53/151.96; 78.2%; 126.8 MiB | 410; 9.89/13.16/15.00; 144.3%; 60.9 MiB |
| H3 256 × 4 KiB chunks | 35; 92.90/267.35/484.01; 68.2%; 101.7 MiB | 230; 17.28/18.93/21.27; 199.0%; 28.9 MiB |
| H3 1 MiB upload | Excluded: baseline correctness failure | 128; 30.31/36.73/45.01; 185.5%; 49.8 MiB |
| H3 slow reader at 4 MiB/s | 7.96; 251.23/252.46/252.46; 15.4%; 98.7 MiB | 7.96; 251.17/252.79/252.79; 7.3%; 26.4 MiB |

The H2/H3 Rust client also consumed substantially more CPU on many high-throughput runs than the Hypercorn client. For example, the H2 fixed-case client used about 100–118% CPU versus about 31–34% for Hypercorn; the H3 fixed-case client used about 113–140% versus about 17–20%. These are whole-system loopback measurements, so client CPU limits how much of the transport delta can be attributed to the server alone. The H3 large-response client reached roughly 200–220% CPU for Rust versus 38–42% for Hypercorn. Treat the throughput result as end-to-end on this harness, not an isolated server CPU benchmark.

The H2/H3 slow-reader workloads deliver nearly the same configured byte rate and p50 latency as Hypercorn. H1 slow-reader results are separately paced by 1 ms per client read event and should not be compared numerically across protocols.

An additional H3 multiplexing gate ran the fixed response at 16 workers across four QUIC connections (four concurrent request streams per connection target). Rust passed three repetitions: uvloop median 31,498 requests/s, p50/p95/p99 0.49/0.79/0.93 ms, server CPU 175.6%, and RSS 282.1 MiB. Hypercorn uvloop failed the same gate with 16 timed-out streams, so this is candidate-only evidence and no 16-worker performance comparison is made. See the [candidate rows](../benchmarks/results/http3-fixed-multiplexed-concurrency16-2026-10-02.json) and [baseline failure log](../benchmarks/results/http3-hypercorn-fixed-concurrency16-gate-2026-10-02.log).

## WebSocket and lifecycle categories

The following table is from the earlier category bundle. Use the latest
WebSocket and lifecycle results above for their recorded historical sources.

WebSocket cells report median messages/s; p50/p95/p99 milliseconds; server CPU; sampled server RSS. The baseline is Uvicorn uvloop with its `websockets` implementation.

| Workload | Uvicorn uvloop + websockets | uvicorn-rs uvloop |
|---|---:|---:|
| Fresh handshake, 500 per sample at concurrency 1 | 4,357; 0.21/0.31/0.42; 72.0%; 31.4 MiB | 6,181; 0.14/0.24/0.32; 67.4%; 26.4 MiB |
| 32-byte text echo, 32 persistent connections | 73,134; 0.44/0.46/0.48; 94.8%; 31.7 MiB | 62,451; 0.52/0.76/0.87; 253.9%; 33.6 MiB |
| 64 KiB binary echo, 32 persistent connections | 29,953; 1.04/1.24/1.32; 94.5%; 66.2 MiB | 36,282; 0.86/1.31/1.60; 222.3%; 60.6 MiB |

The candidate wins this fixed-count handshake sample and the 64 KiB echo throughput, but it loses the text echo and uses over twice the server CPU on both persistent echo cases. These results are not a general WebSocket performance win.

| Configuration | First lifespan-backed response (ms) | Idle SIGTERM exit (ms) | Active SIGTERM exit (ms) | Sampled RSS (MiB) |
|---|---:|---:|---:|---:|
| Uvicorn asyncio + h11 | 72.75 | 208.58 | 2.18 | 28.48 |
| uvicorn-rs asyncio | 40.44 | 10.54 | 2.04 | 22.00 |
| Uvicorn uvloop + httptools | 65.74 | 208.64 | 2.16 | 30.05 |
| uvicorn-rs uvloop | 44.19 | 10.55 | 2.04 | 23.59 |

All 20 lifecycle rows passed, including cancellation of the held ASGI task and completed lifespan shutdown. Uvicorn restores its original signal handler and exits by re-raising SIGTERM after cleanup, which is included in the process-exit measurement.

## PyO3 buffer-ownership optimization

The Rust boundary previously extracted Python response bodies, WebSocket binary
data, and header bytes through `Vec<u8>`, then wrapped those vectors in
`bytes::Bytes`. The current path extracts `Bytes` directly using PyO3's safe
`bytes` feature. Immutable Python `bytes` can therefore stay owner-backed while
Rust writes them. Mutable `bytearray` values are still copied into a stable
owned buffer. Rust-to-Python body data still copies into ASGI `bytes`; see the
[ownership ledger](architecture.md#buffer-ownership-and-copies).

The source-matched October 2 follow-up covered five H1 workloads and 64 KiB
WebSocket binary echo, with four server configurations and three repetitions
per workload. Every measured request and message passed its workload
body/payload checks (0 correctness failures). The H1 run overlapped another
CPU-heavy local workload; its per-run variability makes it exploratory, not a
release-grade speed comparison. The pre-change results in the category tables
were collected separately, so the before/after table below is directional, not
an interleaved A/B proof.

| Workload / metric | Rust before extraction | Rust direct `Bytes`, October 2 snapshot | Uvicorn uvloop, same October 2 run |
|---|---:|---:|---:|
| Fixed 12-byte response, requests/s | 45,482 | 32,677 | 53,111 |
| Fixed response, p50 ms | 1.396 | 1.738 | 0.880 |
| 1 MiB response, requests/s | 8,050 | 7,713 | 7,534 |
| 1 MiB response, p50 ms | 7.776 | 7.957 | 7.439 |
| 1 MiB response, sampled peak RSS | 466.3 MiB | 120.8 MiB | 33.8 MiB |
| 256 × 4 KiB chunks, requests/s | 283 | 264 | 1,327 |
| 256 × 4 KiB chunks, p50 ms | 228.18 | 244.74 | 34.20 |
| 128 × 512 B chunks, requests/s | 555 | 578 | 3,657 |
| 32 headers, requests/s | 30,376 | 32,433 | 42,575 |
| 64 KiB WebSocket binary echo, messages/s | 36,282 | 39,591 | 17,010 |
| 64 KiB WebSocket binary echo, p50 ms | 0.855 | 0.794 | 1.318 |

Across the two recorded Rust runs, 1 MiB response sampled RSS fell from about
466 MiB to about 121–123 MiB after direct PyO3 `Bytes` extraction. This is a
large memory reduction, but still above Uvicorn's roughly 34 MiB. H1 fixed and
chunked performance does not establish a Uvicorn replacement: the recorded
256-chunk sample is about 5× lower throughput, and uses 222% server CPU. The
binary WebSocket echo wins throughput in this run, while using about 228% CPU.
RSS is a process sample, not an allocation profile, and the noisy H1 run does
not show that the copy change alone caused its throughput differences.

A 1 KiB threshold experiment copied small immutable Python `bytes` into fresh
Python objects while retaining direct extraction above the threshold. It was
not kept: fixed and chunked H1 throughput regressed relative to direct
extraction, and large-response sampled RSS was higher. That run overlapped
another CPU-heavy local Rust build, so treat it only as a rejected exploratory
candidate. See [threshold rows](../benchmarks/results/http-zero-copy-threshold-2026-10-02.json).

The October 2 raw artifacts for that source snapshot are [HTTP, 60 rows; contended](../benchmarks/results/http-zero-copy-current-source-contended-2026-10-02.json) and [WebSocket, 12 rows](../benchmarks/results/websocket-zero-copy-current-source-2026-10-02.json). Their benchmark source digests are `235bfa555f9f459700692fe4abbc819150d64021cbb2bb2b444b0cd2eb0b56e4` (HTTP) and `2bbb982fecb9cc9b9b59e354c13d7e09aadcc33520a6a9f1b1f6c7720b78d850` (WebSocket); the Rust source file SHA-256 is `7e6afa7f1c803a2d68735874d06c65ec0113efe0af4480388f35b39007c67c73`. Two earlier raw runs are retained as [HTTP candidate data](../benchmarks/results/http-zero-copy-final-2026-10-02.json) and [WebSocket candidate data](../benchmarks/results/websocket-zero-copy-final-2026-10-02.json); those use the same Rust source but predate non-runtime Python docstring and package README metadata edits. The pre-change category baselines are [HTTP](../benchmarks/results/http-categories-2026-10-02.json) and [WebSocket](../benchmarks/results/websocket-categories-2026-10-02.json). The threshold experiment is [available here](../benchmarks/results/http-zero-copy-threshold-2026-10-02.json).

## Why SIMD is not the current explanation

The fixed response is only 12 bytes. Its hot path consists mainly of HTTP state, task scheduling, Python object and scope construction, synchronization, channel operations, and loopback socket I/O. There is no large byte-processing loop for SIMD to accelerate. The optimized H1 receive fast path helps by returning an already-available terminal request event directly instead of constructing an asynchronous Rust-to-Python bridge future, but each application still runs on its Python event loop under the GIL.

The multi-chunk case sends 256 ASGI body events per response. Moving this work into a SIMD parser would not remove those app-visible event boundaries or their sends, wakeups, and backpressure. The October 5 investigation identified and removed an extra native writer-copy path in a profiled candidate; further allocation/lifetime and bridge profiles are needed on the current build, followed by valid paired benchmarks. The RSS results show a memory issue to explain; they do not identify its cause. SIMD should be considered only if such a profile finds a dominant byte-scanning or copying loop.

Rust owns the listener, protocol parsing, connection state, flow control, and network writes. Python still owns the ASGI callable, event-loop execution, task/context propagation, and exception behavior. Each request crosses that boundary; streamed request events and response body sends cross it repeatedly. Rust removes some protocol and runtime overhead, but it does not make Python ASGI work parallel or erase the bridge cost. `uvloop` improves some candidate cases, but Uvicorn also uses uvloop and adds the C `httptools` parser in the fastest H1 configuration.

The prior fixed-response investigation found that bypassing one unnecessary receive bridge await raised the candidate's throughput and lowered latency. The synchronized receive optimization remains useful, but the category results show that it does not solve per-chunk response overhead or establish a broad performance lead. For CPU, latency, and memory attribution beyond these end-to-end observations, profiling is still required.

## Scope and conformance status

The complete ASGI conformance suite has not been run. The live probes cover callable behavior, caller context, exception-to-500, HTTP version/scope, streaming, disconnect, send-after-disconnect, WebSocket behavior, lifespan state, cancellation, and `starlette-rs` independence. ASGI defines these behaviors across the base, HTTP/WebSocket, and lifespan specifications; this project's probes remain selected cases, not exhaustive coverage ([ASGI specification index](https://asgi.readthedocs.io/en/latest/specs/index.html), [HTTP and WebSocket spec](https://asgi.readthedocs.io/en/latest/specs/www.html), [lifespan spec](https://asgi.readthedocs.io/en/latest/specs/lifespan.html)).

Uvicorn documents HTTP/1.1 and WebSockets, not H2/H3, so Hypercorn is used only for same-protocol comparisons on those transports ([Uvicorn settings](https://www.uvicorn.org/settings/)). H3 upload, broader interoperability, packaging across operating systems, and a complete ASGI conformance run remain open. The [support matrix](support-matrix.md) lists current guarantees and limits. [ADR 0001](adr/0001-runtime-and-asyncio-bridge.md) records the supplied project name and runtime decisions.

For a complete non-overwriting rerun of the HTTP/1.1, HTTP/2, HTTP/3,
WebSocket, and lifespan matrices, use the [benchmark setup guide](benchmarks.md).
The shorter HTTP/1.1 command below reproduces the original artifact in place
and is retained only to identify the original matrix parameters; do not rerun it
with that output path because it will replace the recorded raw file.

Original HTTP/1.1 matrix command:

```sh
uv sync --python 3.12 --group benchmark --reinstall-package uvicorn-rs
uv run python scripts/run_http_category_bench.py \
  --workloads fixed large-response many-response-chunks small-response-chunks \
    request-upload request-upload-small-chunks slow-reader-backpressure \
    scope-32-headers contextvars sync-callable-awaitable exception-to-500 starlette-rs-route \
  --duration 2 --warmup 0.25 --concurrency 64 --repetitions 3 --seed 20261002 \
  --output benchmarks/results/http-categories-2026-10-02.json
```

The original H2/H3/WebSocket/lifecycle runs and corrected merged summary are
described in the category sections above. `scripts/assemble_category_results.py`
rebuilds that historical bundle from fixed, date-specific files; it is not the
fresh-run workflow. Each fresh category runner writes its own medians and raw
rows to the unique directory documented in [benchmarks.md](benchmarks.md).
