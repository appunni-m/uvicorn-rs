# Benchmark and release-gate status

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

## Focused HTTP/2 candidate diagnostic (2026-10-17)

The Git-push-triggered [run 39025351808](https://github.com/appunni-m/uvicorn-rs/actions/runs/39025351808)
tested commit `a8d84d0a3b4a90d5737617a76a62be5395264110` on Linux x86-64. It ran
`examples.bench_fastapi:app` through `uvicorn-rs-asyncio` with CPython 3.12.13
and Rust 1.98.1. The selected `protocol-scope` workload used verified H2 ALPN,
concurrency 64, four client connections, five repetitions, a 1-second warmup,
and a 5-second measurement per repetition.

All five response and clean-shutdown checks passed. Repetition 1 was excluded
because the host monitor detected unrelated CPU activity, leaving four valid
timing rows. The table reports the median of those four rows; latency values
are medians of the per-row percentiles.

| Metric | `uvicorn-rs-asyncio` |
|---|---:|
| Throughput | 5,196.56 req/s |
| p50 latency | 12.37 ms |
| p95 latency | 19.52 ms |
| p99 latency | 23.07 ms |
| Server CPU | 243.65 µs/request (123.37% of elapsed time) |
| Client CPU | 14.03% of elapsed time |
| Peak server RSS | 48.64 MiB |
| Peak client RSS | 6.02 MiB |

This diagnostic ran only uvicorn-rs and has no matched Hypercorn result. It is
not a performance comparison and establishes no speedup. Source SHA-256 is
`fead54a838f7658419b8f0f621a9ca00bb13579b0322859b3b322e93d4208a08`; the
normal native binary SHA-256 is
`4ec09abc9b547370ea4bafbf1d4d5843551f4719d214d07e1e48c28ae5cba893`. The
[workflow artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39025351808/artifacts/12098656237)
contains raw repetitions, host observations, hashes, and server logs.

## Full three-system matrix result (2026-10-17)

The [matrix run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268578)
measures commit `aa4c93836f5e2147462837bbd8b1bde6c0ebe84e`. Exact-binary public
parity and selected FastAPI-only comparisons passed on all three systems.
Linux x86-64 and macOS ARM64 completed their category runs; Linux ARM64 stopped
at its H3 correctness gate during `many-response-chunks`. The Linux ARM64
artifact retained 90 of 130 H3 rows before stopping. The matrix is terminal but
incomplete as a three-system result.

The first divergence was on repetition 3 of `hypercorn-uvloop`: request 43
returned HTTP 200 with 4,096 response bytes in four data chunks where the
client expected 1,048,576 bytes; there was no Content-Length header. The
retained Hypercorn server log then reports its UDP task failing with
`KeyError(164)` while looking up the H3 stream in `protocol/h3.py` during
teardown. This is the observed sequence, not a proven root cause. It could be
an intermittent Hypercorn H3 stream-lifecycle failure or another interaction
in that reference/client path. The focused same-source
[run 39026041230](https://github.com/appunni-m/uvicorn-rs/actions/runs/39026041230)
passed all five full-response, lifecycle, and clean-shutdown repetitions;
four timing rows passed the host guard, but this reference-only run is not a
comparison. Causality remains unproven. The matrix failure invalidates the
affected H3 comparison and prevents a completed three-system aggregate. Do not
infer a Rust performance win from these partial rows.

The run predates the H3 cancellation case on `93d1217` and does not cover that
new conformance input. Runtime Rust sources, the Python bridge, and dependency
manifests are unchanged between this matrix source and current main
`76379e2d64abc33e01827a9f160223e761858779`. Current-head CI
[39026041176](https://github.com/appunni-m/uvicorn-rs/actions/runs/39026041176)
has not started its jobs yet. Older exact-head CI
[39024130047](https://github.com/appunni-m/uvicorn-rs/actions/runs/39024130047)
has passed unified coverage, native composition, installed-wheel parity, MSRV,
Rust quality, and the Windows package job on `77e1f425`. Its Linux candidate
wheel parity job is running and its macOS package job is queued. Those results
do not substitute for current-head CI.

## Cross-system category and FastAPI-only findings (2026-10-17)

The category ratios below are medians across qualified workload/loop pairs
within each system. They are not request-weighted aggregates or one overall
speed score. H1 and WebSocket use stock Uvicorn references; H2 and H3 use stock
Hypercorn references.

| Category | Linux x86-64 | Linux ARM64 | macOS ARM64 |
|---|---:|---:|---:|
| HTTP/1.1 | 0.663x (6/30 faster) | 0.651x (5/30 faster) | 0.730x (7/28 faster) |
| HTTP/2 | 2.208x (8/14 faster) | 2.495x (10/14 faster) | 2.958x (13/14 faster) |
| HTTP/3 | 2.259x (11/12 faster) | no qualified rows; correctness gate failed | 3.145x (10/12 faster) |
| WebSocket | 0.559x (2/6 faster) | 0.705x (2/6 faster) | 0.777x (2/6 faster) |

These medians hide workload reversals. HTTP/2 `many-response-chunks` measured
0.069x on Linux x86-64 and 0.083x on Linux ARM64, while macOS ARM64 was near
parity at 0.992x. HTTP/1.1 upload workloads reached 0.237x on Linux x86-64 and
0.265x on Linux ARM64. WebSocket text echo ranged from 0.365x to 0.487x across
the systems; handshake-only workloads were faster.

The stock FastAPI-only comparison used the same `examples.bench_fastapi:app`,
Python 3.12.13, FastAPI 0.142.4, Starlette 1.7.0, and Pydantic 2.13.5 for both
servers. Four selected pairs qualified on each Linux system; two of four
qualified on macOS. The small validated route exposes a repeated regression:

| System and loop | Rust/Uvicorn throughput | Server CPU per request, Rust/Uvicorn | p50, Rust/Uvicorn |
|---|---:|---:|---:|
| Linux x86-64, asyncio | 0.654x | 262 / 141 µs | 13.64 / 8.98 ms |
| Linux x86-64, uvloop | 0.705x | 226 / 130 µs | 11.94 / 8.25 ms |
| Linux ARM64, asyncio | 0.759x | 295 / 183 µs | 15.63 / 11.59 ms |
| Linux ARM64, uvloop | 0.870x | 260 / 185 µs | 13.72 / 11.75 ms |

For the Python CPU workload, Rust/Uvicorn throughput was 0.918x and 0.931x on
Linux x86-64, 0.963x and 0.984x on Linux ARM64, and 0.922x and 1.030x on macOS
ARM64 (asyncio/uvloop where available). Near parity on this Python-heavy route
contrasts with the small validated route and suggests fixed server-path work
is a substantial part of the latter gap. This is an inference from aggregate
measurements, not a profiled causal breakdown.

The source confirms several candidate costs: each Python app request is
scheduled onto its owning event loop with `call_soon_threadsafe`, then wrapped
in an asyncio task and completion callback ([`python_task_future`](../src/lib.rs#L2508));
the Python bridge creates per-request async `receive` and `send` wrappers
([`_bridge.py`](../python/uvicorn_rs/_bridge.py#L4)); and `build_scope` creates
Python scope dictionaries, header tuples, bytes, and address values for every
request ([`build_scope`](../src/lib.rs#L7013)). The Rust server also uses
Hyper's HTTP/1 path while the reference uses Uvicorn's `httptools` backend.
The benchmark does not isolate any one of these costs.

Immutable Python `bytes` response bodies use PyO3's `bytes::Bytes` extraction
backed by `PyBackedBytes`, retaining the Python owner instead of copying the
response body into a Rust allocation. The validated GET has no request body, so
request-body materialization is not a likely explanation for that particular
route gap. HTTP upload workloads still materialize Python `bytes` ASGI request
messages from Rust body storage.

The small-route result does not point to SIMD as the first optimization.
First isolate parser/runtime work, Python task scheduling, scope construction,
and ASGI send/receive stages with the existing diagnostic-only flags
`--require-runtime-diagnostics` and `--asgi-stage-diagnostics`. Instrumented
timing must not be treated as performance evidence. A sandboxed host preflight
could not enumerate processes. The read-only preflight with process access then
rejected all eight intervals: unrelated CPU ranged from 472% to 524%, with
multiple sustained processes above the guard. It started no benchmark. Its
ignored local receipt is
`target/benchmark-preflight/kata-continuation-20261017-escalated.json`; retry
the focused diagnostic only after a clean preflight or on a clean hosted
runner.

The matrix does **not** demonstrate a general performance gain over Uvicorn:
HTTP/1.1 and WebSocket category medians regress on all three systems, the small
FastAPI route regresses on every qualified Linux pair, and the full matrix is
incomplete. Keep the performance release gate open.

## Focused FastAPI ASGI-stage diagnosis (2026-10-17)

The hosted [run 39030988829](https://github.com/appunni-m/uvicorn-rs/actions/runs/39030988829)
completed on commit `96fc66a9b44f583478c90b4de9d60fce07714884` using Linux
x86-64, CPython 3.12.13, one Tokio worker, and the stock FastAPI workload
`fastapi-validated-route`. Three repetitions ran for each of four servers.
All twelve rows passed response checks, lifecycle checks, stable identity, and
clean shutdown. Host preflight passed. The [retained artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39030988829/artifacts/12100785359)
has SHA-256 `d953767bc30eb5f33155b822f178b4935e2818cf19e96162d09491a9de6ade32`.
Its measured source SHA-256 is
`bc8c9cc930c99532bb48e0da63fb26e37629144e0e9e2ca86e433350e75c0b11`; the
runtime-diagnostics extension SHA-256 is
`7116057ef6f3c50ef55df0b5432a3cbe8fd175901814c78af61d402342582589`.

Every row is intentionally marked timing-invalid because both Rust runtime
counters and the per-request FastAPI stage wrapper are enabled. The throughput,
latency, and CPU columns below are observations from an instrumented build, not
performance evidence. Stage columns are medians of the three repetition-level
percentiles and use one request as the unit.

| Server / loop | Observed req/s, non-rankable | Observed server CPU, non-rankable | ASGI app wall p50 | ASGI `send` wait p50 | App time outside ASGI I/O p50 |
|---|---:|---:|---:|---:|---:|
| uvicorn-rs / asyncio | 4,704.7 | 268.2 µs/request | 111.5 µs | 5.8 µs | 105.4 µs |
| Uvicorn / asyncio | 8,292.4 | 120.7 µs/request | 89.6 µs | 23.1 µs | 64.6 µs |
| uvicorn-rs / uvloop | 5,448.3 | 228.0 µs/request | 108.5 µs | 5.3 µs | 103.2 µs |
| Uvicorn / uvloop | 8,336.9 | 120.0 µs/request | 91.2 µs | 23.0 µs | 66.6 µs |

The Rust counters recorded one Python attachment and one Python task-starter
schedule per request. Their median accumulated wall time per call was 134.5 µs
and 77.3 µs under asyncio, and 118.2 µs and 34.5 µs under uvloop. They include
thread/task scheduling and callback work; they are not exclusive CPU or pure
GIL-wait measurements. The app-stage wrapper found no `receive()` calls, no
request-body bytes, and no request-body materialization/copy for this GET. The
response was 71 bytes over two ASGI sends, with no bounded response queue
backpressure. Request-body copy removal or SIMD applied only to body copying
cannot explain this workload's observed gap; the result does not assess SIMD
in HTTP parsing or other paths.

The measured Rust `send()` wait is shorter, while the ASGI app wall time and
the app time outside awaited `send()`/`receive()` are longer. That outside-I/O
time includes FastAPI route matching, parameter validation, response-model
serialization, Python execution, and any other awaits; it is not CPU time. The
evidence narrows the next measurement to per-request scheduling/task setup and
the Python ASGI execution path, but does not yet isolate a causal component.
The next focused case uses the normal uninstrumented release wheel and requires
three valid matching repetitions per loop before reporting performance.

## Latest focused macOS HTTP/3 large-response comparison (2026-10-17)

Focused run [39013640218](https://github.com/appunni-m/uvicorn-rs/actions/runs/39013640218)
on commit `f815728ded987419123a786ce5a9c04c669c80cb` completed ten large-response
samples on macOS ARM64: five Hypercorn asyncio and five uvicorn-rs asyncio.
All response checks passed, and all servers shut down cleanly without force.
Only one of ten timing rows was valid; unrelated host CPU activity invalidated
the other nine, so there is no matched timing pair and no performance
conclusion. Artifact 12094156939 retains the samples and host observations.
The four-valid-pair Linux ARM64 result below remains scoped to one workload;
neither result closes the full multi-system benchmark gate.

## Focused matched HTTP/3 large-response comparison (2026-10-17)

The [focused run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39013025705)
on commit `e2a39c55594eb4aab2ac922c2e9128e970ca7f7e` compared Hypercorn and
uvicorn-rs with asyncio on one Linux ARM64 runner. Both served the same standard
FastAPI app (`examples.bench_fastapi:app`) under Python 3.12.13. The workload
was a bodyless HTTP/3 GET returning a cached 1 MiB response; server order was
randomized for each of five repetitions.

This exercises the Rust transport and HTTP/3 implementation with a real Python
FastAPI ASGI app. It does not remove the Python boundary, and it does not
measure a future Rust-native FastAPI/Starlette composition.

All five repetitions on both servers passed complete response validation and
clean, unforced shutdown. Rust repetition 1 was excluded from timing because
the monitor detected unrelated host CPU activity, leaving four valid matched
pairs (repetitions 2–5). The table reports each metric's median over that same
four-pair cohort.

| Metric | Hypercorn asyncio | uvicorn-rs asyncio | Change |
|---|---:|---:|---:|
| Throughput | 19.84 req/s | 483.74 req/s | 24.38× |
| p50 latency | 38.58 ms | 2.00 ms | 94.8% lower |
| p95 latency | 75.60 ms | 2.56 ms | 96.6% lower |
| p99 latency | 77.31 ms | 2.77 ms | 96.4% lower |
| Server CPU | 31,089 µs/request | 1,813 µs/request | 94.2% lower |
| Peak server RSS | 114.94 MiB | 49.06 MiB | 57.3% lower |

The valid per-repetition throughput ratios ranged from 23.91× to 26.48×.
This is a focused, single-workload Linux ARM64 result; it does not establish a
general or multi-system speedup and does not close the full benchmark gate. The
[raw artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39013025705/artifacts/12093617960)
retains all rows, validity reasons, hashes, and server logs.

## Latest multi-system benchmark attempt (2026-10-17)

The [multi-system run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490)
on commit `128aa2721aa78a289a93952539fa584d8412be14` did not produce a complete
three-system result. Linux x86-64 completed; macOS ARM64 and Linux ARM64 failed
the HTTP/3 `large-response` correctness gate when Hypercorn asyncio timed out
waiting for response headers (repetition 2 on macOS and repetition 5 on Linux
ARM64). A later focused Linux ARM64 run, above, passed all five Hypercorn and
all five Rust correctness/shutdown samples, so the timeout is intermittent and
still unexplained. Do not treat the focused pass as resolving the matrix
failure. The [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490/artifacts/12093376239),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490/artifacts/12093050892),
and [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490/artifacts/12093037005)
retain each platform's raw results.

## Focused HTTP/2 close-diagnostic follow-up (2026-10-17)

The focused Linux x86-64 run
[39009246269](https://github.com/appunni-m/uvicorn-rs/actions/runs/39009246269),
commit `93669808`, stopped in repetition 2 after the client completed its
response checks with zero failures and its H2 drivers exited successfully. The
server exited cleanly without forced shutdown, with two exact `BrokenPipe`
connection diagnostics from distinct peer ports; the finalizer then allowed
only one. Repetition 1 completed 25,192 requests, but its timing was excluded
for unrelated runner CPU activity. The [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39009246269/artifacts/12092605687)
retains the raw rows and logs.

The earlier focused run
[39003779460](https://github.com/appunni-m/uvicorn-rs/actions/runs/39003779460)
used four client connections and logged one exact peer-close line in
repetitions 1 and 2, with no such lines in repetitions 3–5. Its five response
and shutdown checks passed; four timings passed the host guard. The pushed
change bounds this exact Rust H2 diagnostic to one per
configured client connection and continues to reject counts above the bound,
other server errors, response failures, driver failures, and unclean shutdown.

A local normal-wheel run of `protocol-scope` passed 5/5 response and shutdown
checks with zero peer-close lines. All five timing rows were excluded for
unrelated host CPU activity. A direct finalizer smoke check accepted 2/4 exact
diagnostics and rejected 5/4. These results validate the gate behavior; they
provide no performance evidence. Focused run
[39010673595](https://github.com/appunni-m/uvicorn-rs/actions/runs/39010673595)
later passed five Linux x86-64 `uvicorn-rs-asyncio` / `protocol-scope`
correctness and shutdown checks; four timings passed the host guard. It was a
target-only diagnostic, not a paired performance comparison. Exact-source CI
run [39011984443](https://github.com/appunni-m/uvicorn-rs/actions/runs/39011984443)
completed successfully on `e22df3a`. The later coverage run
[39020268579](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579)
passed its 749-case matrix and all reported source regions and lines. Current
exact-head CI [39024130047](https://github.com/appunni-m/uvicorn-rs/actions/runs/39024130047)
is in progress; its current state is summarized at the top of this document.

## Earlier full benchmark attempt (2026-10-17)

The [full matrix run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146)
measured commit
[`5dbd981332080e289ef416357606f49c8e2503b4`](https://github.com/appunni-m/uvicorn-rs/commit/5dbd981332080e289ef416357606f49c8e2503b4).
It did not complete across all three systems, so it does not qualify a
multi-system performance result.

| System | Outcome |
|---|---|
| Linux x86-64 | Stopped before timed categories: the installed wheel failed public parity at `http3.scope-preserves-duplicate-headers`. A later installed-wheel run on the current commit passed that case within 248/248 public cases, so no current mismatch is established; this matrix still has no qualified category result. |
| macOS ARM64 | Stopped in HTTP/2 `many-response-chunks` on `hypercorn-uvloop`; the H2 client connection driver did not shut down within its timeout. No complete multi-category result. |
| Linux ARM64 | All selected categories completed with qualified local pairs. In HTTP/2 `many-response-chunks`, uvicorn-rs throughput was 0.092× Hypercorn under asyncio and 0.084× under uvloop. Median throughput was about 6.97 vs 75.66 requests/s (asyncio) and 7.08 vs 84.28 requests/s (uvloop). This is a measured regression for that workload, not a cross-system conclusion. |

The same ARM64 run shows that HTTP/2 is not uniformly slower in Rust. On
`protocol-scope`, each server had five valid repetitions with zero failures;
uvicorn-rs reached 2.342× Hypercorn throughput under asyncio and 2.982× under
uvloop. Median rates were 5,894.7 vs 2,562.2 requests/s and 7,542.4 vs
2,533.0 requests/s. Rust p50/p95/p99 latency was 10.924/16.646/18.936 ms
under asyncio and 8.586/12.745/14.838 ms under uvloop; Hypercorn measured
24.211/35.689/36.679 ms and 24.469/36.517/37.470 ms. Rust server CPU per
request was 199/155 µs versus 390/394 µs; peak RSS was 48/50 MiB versus
95/97 MiB. These matched rows use the same ARM64 host and app. They coexist
with the chunk-streaming regression below and do not establish a category-wide
or multi-system win.

The ARM64 `many-response-chunks` rows also had substantially higher median p50
latency on uvicorn-rs (about 8.88 s under asyncio and 8.70 s under uvloop) than on
Hypercorn (about 0.85 s and 0.77 s). Server CPU per operation was about 27.8
ms and 19.8 ms for uvicorn-rs versus 13.2 ms and 11.85 ms for Hypercorn.
This gap is much larger in wall time than in server CPU: it points away from a
CPU-bound or byte-copy bottleneck as the first explanation and toward time spent
waiting for stream progress, backpressure, or scheduling. That is an inference
from aggregate CPU and latency, not a proven cause.

The same raw rows report a median of about 509 client `RecvStream.data()`
results per 1 MiB Rust response, versus about 70 for Hypercorn under asyncio
and 66 under uvloop. The counter records chunks returned by the H2 client API;
it is not a packet capture and does not establish wire-frame boundaries. It
does justify measuring whether response chunk granularity and transport
backpressure amplify per-send scheduling. The existing instrumented profile
collects ASGI send-await time, body-channel-full events and wait duration, and
final-body availability. A local preflight on 2026-10-17 rejected the host
because four unrelated Python processes each used roughly one core; no
instrumented profile was started.

The [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146/artifacts/12087490643),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146/artifacts/12089425539),
and [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146/artifacts/12088867853)
retain the reports and logs.

A focused macOS ARM64 rerun
[completed](https://github.com/appunni-m/uvicorn-rs/actions/runs/39001707728)
the `hypercorn-uvloop` / `many-response-chunks` case with 5/5 response and
shutdown checks passing. All timing samples were rejected by the host CPU
guard, and the case has no matched Rust-server comparison. It is a correctness
diagnostic only. SHA-256 identities for `src/lib.rs`, the H2 category runner,
and the FastAPI benchmark app match the current checkout; later changes were
workflow selectors, release-evidence metadata, and documentation. This links
the diagnostic to current runtime source without presenting the run as an
exact-commit full matrix.

The [focused Linux x86-64 rerun](https://github.com/appunni-m/uvicorn-rs/actions/runs/39003779460)
on the current commit exercised only `uvicorn-rs-asyncio` / `protocol-scope`;
all five repetitions passed response and shutdown checks with zero unexpected
native errors or panics. Four timing rows passed the host guard; repetition 1
was excluded for unrelated host CPU activity. The four valid rows had median
throughput 5,175 requests/s, p50/p95/p99 latency 12.40/19.36/22.43 ms, server
CPU 244 µs/request, and peak RSS 48.6 MiB. The [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39003779460/artifacts/12090680106)
contains the raw rows. This target-only x86-64 diagnostic has no reference
server and must not be compared with the ARM64 rates above.

## Latest hosted benchmark attempt (2026-10-16)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975)
measured clean commit
[`c2de34a08a0b5083f830cc59c88182378a7d1a81`](https://github.com/appunni-m/uvicorn-rs/commit/c2de34a08a0b5083f830cc59c88182378a7d1a81).
Exact-binary public parity and the stock-FastAPI comparison completed on
Linux x86-64, Linux ARM64, and macOS ARM64. All three category jobs stopped
before the maintained matrix completed; no cross-system performance result is
qualified.

| System | First HTTP/2 failure | Other category failures |
|---|---|---|
| Linux x86-64 | `protocol-scope`, `uvicorn-rs-asyncio`, repetition 1. All client response checks and graceful shutdown passed; the server emitted `HTTP connection failed: connection error`. | H1: `fastapi-request-upload`, Rust/uvloop repetition 5 (concurrency 64), and `fastapi-upload-1m-write-1k`, Rust/asyncio repetition 5 (concurrency 8), each hit a libcurl timeout. H3 `fixed`, `hypercorn-uvloop`, repetition 2: 2,573 responses passed before one response-header timeout; Hypercorn's log was empty. Lifecycle analysis rejected the Rust TCP graceful-timeout diagnostic. |
| Linux ARM64 | `protocol-scope`, `uvicorn-rs-asyncio`, repetition 3, with the same generic connection diagnostic after successful responses and clean shutdown. | H1: `fastapi-upload-1m-write-1k`, Rust/uvloop repetition 4 and Rust/asyncio repetition 5 (both concurrency 8), each hit a libcurl timeout. Lifecycle analysis rejected the Rust TCP graceful-timeout diagnostic. |
| macOS ARM64 | `request-upload`, `uvicorn-rs-asyncio`, repetition 1, with the same generic connection diagnostic after successful responses and clean shutdown. | H1 completed all 300 rows without request failures. Lifecycle analysis rejected the Rust TCP graceful-timeout diagnostic. |

The H1 category processed all 300 planned rows on each system. Both Linux
systems had 298 correctness-eligible rows; macOS had 300. The four failed
Rust rows ran for about 15.4–18.0 seconds before libcurl reported
`Timeout was reached`. The affected Starlette handlers then observed
`ClientDisconnect`, and the Rust bridge logged a client disconnect before
response start. These errors invalidate the affected samples and fail the
Linux category jobs; their partial request rates are not performance data.
On macOS, 30 matched H1 workload/loop pairs qualified. Twenty-seven Rust /
Uvicorn throughput ratios were below 1.0; three were above 1.0. The median
ratio was 0.748× (range 0.452–1.042×). This is evidence against a broad H1
gain on that system, and does not provide the missing Linux measurements.

The retained platform artifacts are
[Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975/artifacts/12017648435),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975/artifacts/12018946775),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975/artifacts/12019086925).

### Focused hosted HTTP/2 diagnostic (latest rerun: 2026-10-17 local)

The [focused Linux x86-64 run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176)
ran only `protocol-scope` against `uvicorn-rs-asyncio` on `h2-debug` commit
`3d31e241cccfac939cb9403786f369d870f812da`. Attempt 7 completed all five
correctness and lifecycle repetitions with zero request failures, empty server
logs, and zero unexpected native errors or panic events. Repetitions 1, 3, 4,
and 5 passed the host timing guard; repetition 2 was excluded for unrelated
host CPU activity. Across the four valid samples, medians were 8,092
requests/s, 7.58/13.09/15.55 ms p50/p95/p99 latency, 155 microseconds of
server CPU per request, and 48.60 MiB peak server RSS. The retained
[attempt-7 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176/artifacts/12078313679)
has SHA-256
`8ccefead8c5144bd5ecf1859f0a663cdaaa7614ae51bc9bc7a2432450c71d58f`.

Two additional focused hosted runs tested Linux ARM64 and the macOS upload
case. Each completed all five correctness and lifecycle repetitions; all five
timing samples on both systems passed the host guard. There were zero request
failures, unexpected native errors, or generic connection diagnostics:

| System and workload | Workflow run and artifact | Timing-valid samples | Median throughput | Median p50/p95/p99 | Server CPU/request | Peak server RSS |
|---|---|---:|---:|---:|---:|---:|
| Linux ARM64, `protocol-scope` | [run 38863847199](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863847199), [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863847199/artifacts/12030229138); commit `4057bc320bf054ece2b3a1b511f5adcc5a72e79a` | 5/5 | 5,855 req/s | 10.98/16.70/19.19 ms | 202 µs | 48.47 MiB |
| macOS ARM64, `request-upload` | [run 38864179333](https://github.com/appunni-m/uvicorn-rs/actions/runs/38864179333), [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38864179333/artifacts/12030394350); commit `31cf827cb732cb19152df9f458accb4770fedb1d` | 5/5 | 370 req/s | 161.59/268.77/321.99 ms | 3,294 µs | 177.13 MiB |

These are target-only diagnostics with no matched Hypercorn reference. Their
timings do not establish a speedup or satisfy comparative performance
acceptance. Across the three focused hosted cases, the generic H2 connection
error did not recur; the original full-matrix failures remain unexplained.
The focused jobs do not cover other H2 workloads or runtime configurations.

The current local source replayed the macOS `request-upload` case once with
the same duration, warmup, concurrency, and server selection. Responses and
shutdown passed with an empty server log; unrelated CPU activity invalidated
the timing. This does not reproduce the hosted failure on Linux or prove a
performance gain. Three additional focused replays on the current local
source passed correctness and clean-shutdown checks:

| Case | Result | Timing |
|---|---|---|
| H3 `fixed`, `hypercorn-uvloop`, repetition 1 | 9,583 responses, zero client failures, empty server log, graceful shutdown | Invalid: unrelated CPU spiked above the host limit, including Codex Renderer activity. |
| H2 `protocol-scope`, `uvicorn-rs-asyncio`, repetition 1 | 38,117 responses, zero client failures, empty server log, graceful shutdown | Invalid: unrelated CPU exceeded the host limit, including `coverage-mcp` and `pillow-perfdb`. |
| H2 `protocol-scope`, `uvicorn-rs-asyncio`, repetitions 1–5 | All five repetitions had zero client failures, clean server exit, empty logs, and no unexpected native errors. | Invalid in all five repetitions: unrelated host CPU activity. |

The five-repetition H2 replay used 5-second duration, 1-second warmup, and
concurrency 64 on the local Apple M3 Pro. Source identity was stable at
`0b407a54c3baa9b0e33c3db3bad7b720ba686d6cbd4cb4c3daabf05093747918`; the
normal native extension identity was stable at
`2a5cbd4a2d4930430a51b65f9e6d8cbbabd894cf8c7dc43763d26ed44dfb0b3c`. The
timing rows are not performance evidence. The raw ignored report is
`target/benchmark-categories/h2-protocol-scope-singlecase-debug-current-20261016.json`.
This local M3 replay did not reproduce the generic HTTP/2 connection
diagnostic, so the hosted failure remains unresolved.

### Focused FastAPI upload failure replay (2026-10-17)

The current local source ran one matched repetition of
`fastapi-upload-1m-write-1k` on Uvicorn/asyncio and uvicorn-rs/asyncio, using
the stock FastAPI workload, 1 MiB requests sent in 1 KiB chunks, and
concurrency 8. Both servers completed all requests and graceful shutdown with
zero client failures. Throughput was 356.7 requests/s for Uvicorn and 351.5
for uvicorn-rs; p50 latency was 21.92 ms and 22.56 ms, respectively. Both
timing samples were rejected because unrelated host CPU activity ranged from
about 256% to 340% of one core. This single macOS replay does not reproduce
the hosted Linux timeout, and its measurements are not performance evidence.
It identifies no root cause and supports no code change by itself. The raw
ignored report is
`target/benchmark-categories/fastapi-upload-1m-write-1k-focused-uvicorn-vs-rs-asyncio-20261017.json`.

### HTTP/2 diagnostic status

The benchmark client shares its H2 senders among workers, drops all sender
handles after the workers finish, and awaits each H2 connection driver before
reporting the sample. The hosted failure therefore is not explained by the
client skipping its driver join. The original hosted server log contains only
Hyper's generic `connection error`; that matrix commit did not log the
concrete error detail. Focused debug-logging replays on Linux x86-64 and
ARM64 passed five repetitions without reproducing it. The focused macOS
upload replay also passed. These results narrow the issue to an intermittent
or environment-specific failure, but do not identify whether it is a
transport bug or expected peer-close condition. Preserve detailed connection
logging and the strict lifecycle gate until a reproducing input provides the
concrete error.

These local runs and the later focused hosted H2 diagnostics do not explain
the hosted H2 transport diagnostic or H3 timeout, and do not establish a
performance gain. Their Git-ignored
receipts are `target/benchmark-categories/h3-fixed-hypercorn-uvloop-retry2-20261016.json`,
`target/benchmark-categories/h2-protocol-scope-rust-asyncio-single-20261016.json`,
`target/benchmark-categories/h2-request-upload-rust-asyncio-exact-20261016.json`,
and `target/benchmark-categories/h2-protocol-scope-singlecase-debug-current-20261016.json`.

Latest clean hosted CI
[run 38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888)
on `27de9f3ac7d259a3a9b612c3247ab2c60eb27306` passed all 712 indexed cases,
Rust quality and MSRV checks, installed-wheel public parity, and pinned native
composition. Its older manifest measured 8,496/8,650 LLVM regions and
6,486/6,592 lines, leaving 154 regions and 106 lines uncovered; package and
Python-floor jobs were skipped. The preceding hosted run
[38828501018](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828501018)
left 155 regions and 107 lines uncovered. A later local dirty-worktree
run executed and passed all 748 current cases (534 ASGI and 214 native), with
three clean full repeats of each matrix, and measured 100% executable
source-span and normalized physical-line coverage. Its aggregate remains
incomplete because one WebSocket TLS attribution attempt had a transient
infrastructure failure before a passing retry; a separate focused rerun then
passed cleanly. It does not replace a clean hosted release-candidate run.
The release candidate remains blocked by the failed category matrix,
`performance-acceptance.json` set to `not_proven`, and the need for clean
exact-source release evidence. See [release status](releases.md)
and the [current coverage record](coverage.md#current-unified-coverage-status-2026-10-17).

The latest local host-only preflight, recorded at
`target/benchmark-preflight/kata-finish-20261017-04.json`, sampled eight
0.25-second intervals on macOS 15.7.7 ARM64 (12 logical CPUs) and rejected
timing before launch. Unrelated aggregate CPU ranged from 300.3% to 316.8%;
three `python3.12` processes each reached 101.9–104.6% of one logical core.
The aggregate and repeated per-process guards rejected the host. No timing
benchmark started and no process was stopped. The receipt records process
names and PIDs only; command lines were not read. Recheck the host before
attempting a local matched pair.

## Previous completed hosted benchmark matrix: run #29 (2026-10-14)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330)
measured commit
[`1bde9cee0bb89618a30c3fc01b04af183f709c7b`](https://github.com/appunni-m/uvicorn-rs/commit/1bde9cee0bb89618a30c3fc01b04af183f709c7b).
Parity completed on all three systems. The category step failed on each
system because HTTP/2 stopped before all 140 planned rows were written.
HTTP/3 also stopped early on Linux x86-64 and Linux ARM64; the retained Linux
output includes a Hypercorn asyncio `protocol-scope` request that timed out
waiting for response headers. macOS completed all 130 HTTP/3 rows. WebSocket
completed 60/60 rows and lifecycle completed 20/20 rows on every system.

| System | FastAPI-only HTTP/1 | HTTP/1 categories | HTTP/2 | HTTP/3 | WebSocket | Lifecycle |
|---|---:|---:|---:|---:|---:|---:|
| Linux x86-64 | 40/40 rows; 39 timing-valid | 300/300; 300 timing-valid | incomplete; 140 planned | incomplete; 130 planned | 60/60 | 20/20 |
| Linux ARM64 | 40/40 rows; 39 timing-valid | 300/300; 300 timing-valid | incomplete; 140 planned | incomplete; 130 planned | 60/60 | 20/20 |
| macOS ARM64 | 40/40 rows; 5 timing-valid | 300/300; 232 timing-valid | incomplete; 140 planned | 130/130; 117 timing-valid | 60/60 | 20/20 |

The completed HTTP/1 rows had zero correctness failures. Timing validity does
not establish a speedup: the standalone FastAPI comparisons are
`not_proven`, and the broader category matrix is incomplete. The latest
complete multi-system FastAPI comparison remains run #27 below; its median
Rust/Uvicorn throughput ratios were below 1.0 on all three systems, so it did
not demonstrate a broad gain.

The workflow used Python 3.12.13, Rust 1.98.1, five repetitions, five seconds
per timed sample, one second of warmup, and concurrency 64 (HTTP/3 concurrency
1). The [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330/artifacts/11884090964),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330/artifacts/11884251396),
and [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330/artifacts/11885435428)
retain category JSONL checkpoints and logs. The HTTP/2 failure's specific
sample-level cause is not present in the job summary; the retained artifacts
are needed to diagnose it. This run does not satisfy performance acceptance.

## Focused local FastAPI HTTP/1 workload (2026-10-16)

A single `fastapi-fixed` workload was run on Apple M3 Pro / macOS 15.7.7 with
the same stock FastAPI app on Uvicorn and `uvicorn-rs-py`, under asyncio and
uvloop. The run used Python 3.12.13, Rust 1.98.1, concurrency 64, a one-second
warmup, five-second samples, and three repetitions per server. All 12 samples
passed response correctness and graceful shutdown, and source identity stayed
stable. The initial host preflight accepted, but unrelated CPU activity rose
during the run. The per-sample guard accepted only 4 of 12 timings: Uvicorn
asyncio 1/3, Rust asyncio 2/3, Uvicorn uvloop 0/3, and Rust uvloop 1/3. No
matched pair has the required three valid repetitions. A follow-up host
preflight rejected before another timing run because unrelated CPU exceeded
the aggregate and process limits. These rows do not establish a ratio or
performance result. The raw report and logs are local-only under
`target/benchmark-categories/2026-10-16/fastapi-fixed-single.json`.

## Previous hosted benchmark matrix: run #27 (2026-10-14)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006)
measured commit
[`ef9680c8e34fb2bf1c959b94d832f61cbf580213`](https://github.com/appunni-m/uvicorn-rs/commit/ef9680c8e34fb2bf1c959b94d832f61cbf580213).
Exact-binary parity and all correctness checks in the separate stock-FastAPI
comparison passed on all three systems. All platform category jobs stopped in
HTTP/2 after successful response checks because the server logged
`connection task failed: connection error`; each server shut down cleanly. The
underlying I/O error remains unknown. The category diagnostic gate remains
strict; a focused local follow-up is recorded below.

| System | HTTP/1 | HTTP/2 | HTTP/3 | WebSocket | Lifecycle | Qualified pairs |
|---|---|---|---|---|---|---:|
| Linux x86-64 | 300/300 rows; 30/30 pairs | 27/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| Linux ARM64 | 300/300 rows; 30/30 pairs | 2/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| macOS ARM64 | 300/300 rows; 24/30 pairs | 53/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 44 |

The HTTP/1 rows compare a stock Python FastAPI app under Uvicorn and
`uvicorn-rs-py`; they do not use FastAPI-RS or Starlette-RS. Each Linux system
qualified all 30 workload/event-loop pairs;
macOS qualified 24. The table reports medians of matched per-pair Rust/Uvicorn
ratios, so architectures are not combined.

| System | Qualified H1 pairs | Rust higher throughput | Throughput ratio, median | p95 latency ratio, median | Server CPU/operation ratio, median | Server RSS ratio, median |
|---|---:|---:|---:|---:|---:|---:|
| Linux x86-64 | 30/30 | 7/30 | 0.765 | 1.497 | 1.549 | 1.010 |
| Linux ARM64 | 30/30 | 5/30 | 0.793 | 1.460 | 1.575 | 1.013 |
| macOS ARM64 | 24/30 | 5/24 | 0.835 | 1.198 | 1.357 | 1.016 |

The current Python ASGI path has no broad speed advantage in this run: median
throughput is below Uvicorn on all three systems, and median server CPU per
operation is higher. The macOS timing exclusions and incomplete HTTP/2
categories also mean the matrix does not qualify the full required workload
inventory. These are measured outcomes, not release performance acceptance.

The workflow used Python 3.12.13 and Rust 1.98.1, five repetitions, five
seconds per timed sample, one second of warmup, concurrency 64 (HTTP/3
concurrency 1), and independent hosted Linux x86-64, Linux ARM64, and macOS
ARM64 runners. See [benchmark methodology](benchmarks.md) and the
[generated multi-system report](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11879148475).
The [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11878788763),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11879906195),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11879698658)
artifacts retain the raw rows and server logs. The evidence aggregates to
`validated_partial_matrix`; it does not satisfy the performance gate.

## Focused HTTP/2 diagnostic probe (2026-10-14)

After changing the local server diagnostic to print Hyper's `Debug` error,
five normal-build repetitions of HTTP/2 `large-response` on
`uvicorn-rs-asyncio` passed all response checks and exited cleanly. All five
server logs were empty, so the hosted connection error did not recur and the
new diagnostic did not capture its underlying cause. The host guard rejected
all five timing samples for unrelated CPU activity; this is not performance
evidence. The probe used working-tree source SHA-256
`a74b6c7d799d1fa5080f0a7064fb8c23b4671b89449dc83e16f3449d4a907dd9` and is
retained only under Git-ignored `target/h2-debug-format-20261014.jsonl` and
`target/h2-debug-format-20261014.artifacts/`. It does not resolve the hosted
failure or replace the complete benchmark matrix.

## Previous hosted benchmark matrix: run #26 (2026-10-14)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313)
passed public parity and the separate stock-FastAPI HTTP/1 comparison on all
three systems. The category jobs and overall matrix are incomplete, so this
run does not establish a three-system performance result or a speedup.

| System | HTTP/1 | HTTP/2 | HTTP/3 | WebSocket | Lifecycle | Qualified pairs |
|---|---|---|---|---|---|---:|
| Linux x86-64 | 300/300 rows; 30/30 pairs | 47/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| Linux ARM64 | 300/300 rows; 30/30 pairs | 48/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| macOS ARM64 | 124/300 rows; incomplete | 140/140 rows; 12/14 pairs | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 32 |

The macOS HTTP/1 category recorded four correctness failures in the 1 MiB
upload workload using 1 KiB client writes at concurrency 64. All four server
profiles failed during warm-up with client send errors; FastAPI observed
`ClientDisconnect`. Linux HTTP/2 stopped in the Rust/asyncio `large-response`
workload after successful client response checks, followed by the generic
`uvicorn-rs: connection task failed: connection error` diagnostic. The
failures occurred at repetition 2 on x86-64 and repetition 3 on ARM64; server
shutdown was clean. Their shared cause is not established.

The separate FastAPI-only comparison produced all 40 planned rows without
correctness failures on each system. It qualified 4/4 workload/loop pairs on
each Linux system and 0/4 on macOS because of timing exclusions. This comparison
uses stock FastAPI and Starlette under Uvicorn and uvicorn-rs; it does not use
FastAPI-RS or Starlette-RS.

The [matrix artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11873134174)
and [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11874197074),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11873189132),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11874001693)
artifacts retain source-bound receipts, raw rows, reports, and logs for 90
days. The artifacts aggregate to `validated_partial_matrix`: 50 qualified
pairs on each Linux system and 32 on macOS. Partial pairs are descriptive
evidence only and do not satisfy performance acceptance.

Focused local follow-ups validated the two failing inputs after harness
changes. The HTTP/1 upload passed once on all four server/loop profiles at
concurrency 8 with response and lifecycle gates passing. The HTTP/2
large-response probe completed 4,071 requests with no client failures and a
clean server exit after the client sent GOAWAY and drained pending frames.
Both runs rejected timing because unrelated local CPU activity exceeded the
guard. These probes do not confirm the fixes on hosted runners or provide
performance evidence. The next complete hosted matrix must validate the
workload changes.

The status/docs job also failed: it tried to stage per-run files under the
Git-ignored `benchmarks/results/` directory. The workflow now keeps generated
reports and logs in 90-day Actions artifacts and proposes documentation-only
changes on its automation branch. Repository Actions permissions cannot
create pull requests, so the workflow provides a compare link for manual
review.

## Local host preflight (2026-10-14)

The latest eight-sample macOS ARM64 preflight rejected benchmark timing before
launch. Unrelated CPU use ranged from 114.9% to 228.1% of one logical core;
`python3.12` remained near one core across the samples, and `rustfmt` briefly
used 97.1%. The decision followed the existing aggregate and sustained-process
guard. No timed benchmark started and no process was stopped. The receipt is
Git-ignored at
`target/benchmark-preflight/kata-finish-20261014-retry1.json` and records HEAD
`796dee690ca83654cddb97131dc1dee37de96bcd`. The FastAPI benchmark remains
unqualified; retry after a clean preflight.

## Previous hosted benchmark matrix: run #25 (2026-10-13)

The matrix
[38418430949](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949)
passed exact-normal-binary public parity on all three systems. All three
platform category jobs are now terminal failures. The multi-system evidence
validation job passed as an aggregation check, but the required categories did
not complete and there is no validated three-system performance result.

The preliminary FastAPI-only HTTP/1 comparison produced 40 planned rows on
each system with no correctness failures. It had 2 timing-valid rows on macOS
and 39 on each Linux system; all three reports say `not_proven`. The full
stock-FastAPI HTTP/1 category completed 300/300 correct, timing-valid rows on
each Linux system. macOS stopped at 124 rows: rows 121–124 failed during the
1 MiB upload workloads, and 75 rows were timing-valid. Its trace ends in
Starlette `ClientDisconnect` while reading the upload body.

The complete Linux HTTP/1 reports qualified all 30 FastAPI workload/event-loop
pairs on each system, with five matched repetitions per pair. The ratios below
are medians of the 30 per-pair Rust/Uvicorn ratios; they summarize the recorded
workloads and do not combine samples from different machines.

| System | Qualified pairs | Rust faster | Throughput ratio, median (range) | p95 latency ratio, median | Server CPU per operation ratio, median | Server RSS ratio, median |
|---|---:|---:|---:|---:|---:|---:|
| Linux x86-64 | 30/30 | 6/30 | 0.713 (0.450–1.402) | 1.565 | 1.764 | 1.008 |
| Linux ARM64 | 30/30 | 6/30 | 0.844 (0.436–1.463) | 1.369 | 1.563 | 1.014 |

These measurements show no broad speed advantage for the current Python ASGI
server path: throughput was lower in 24 of 30 pairs on each Linux machine, and
median server CPU per operation was higher. They do not identify which layer
caused the overhead. The reports compare FastAPI under Uvicorn with FastAPI
under the current `uvicorn-rs-py` implementation; they do not measure the
separate Python-free Rust application composition path. This evidence fails the
project's performance objective and must not be presented as a release gain.

HTTP/2 stopped on all three systems when the server diagnostic gate rejected
`uvicorn-rs: connection task failed: connection error`; shutdown itself was
clean. HTTP/3 also stopped on all three: the Linux Hypercorn reference failed
large-response body-length checks (192,037 or 251,633 bytes received versus
1,048,576 expected), while macOS Hypercorn/uvloop timed out waiting for
protocol-scope response headers. The logs do not establish whether these H3
failures share one cause. WebSocket completed 60/60 correct, timing-valid rows
on every system. Lifecycle completed 20/20 on both Linux systems and 19/20 on
macOS. Those passing categories do not make the whole matrix complete.

The aggregate validator marked the result `validated_partial_matrix`. Its
artifact reports 38 individually qualified workload/reference pairs on each
Linux system and 8 on macOS; the separate FastAPI-only comparison qualified 4
pairs on each Linux system and none on macOS. These counts are partial
descriptive evidence, not a substitute for complete categories or a
cross-system performance claim. The [aggregate evidence artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949/artifacts/11829521030)
contains the generated comparison report and source manifests.

The benchmark docs job failed because GitHub Actions could not create a PR;
commit documentation updates through the normal repository workflow. The
category logs and partial reports are retained in the
[run #25 artifacts](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949).

Run #24
([38354960306](https://github.com/appunni-m/uvicorn-rs/actions/runs/38354960306))
produced no parity or timing rows because the protocol clients were looked up
under `tools/http3-probe/target/release/` instead of repository
`target/release/`. The parity and category scripts now use the workspace output
directory, and run #25 has passed hosted parity with those paths. The #24
benchmark documentation job could not create a PR under the repository's
Actions permissions; documentation updates must be reviewed and committed
through the normal repository workflow.

## Latest local benchmark preparation (2026-10-13)

The exact normal build passed **243/243** parity cases at commit
`957143ab5f810be861183bde0c239d558f78fefb`. The measured source
(`src/lib.rs` SHA-256
`ea149b5821a398f62c5a7762a83774040ae15ae0b268c28d921e4c61f3e54f47`),
normal extension (`8e7a060c5bdd9e1bd5d1c4d5bbcd5136de739208f7eccdbbd80963f235dcc64f`),
benchmark scripts, and lockfiles are unchanged in the current checkout. Since
parity commit `957143ab5f810be861183bde0c239d558f78fefb`, the Python adapter
source, extension, dependencies, benchmark scripts, and parity cases are
unchanged; later commits affect the independent native crate, native contract
example, manifest, docs, and ignore rules. The 243/243 parity receipt therefore
still matches the benchmark input without another parity run.

The post-parity host preflight rejected three windows before timing began.
Unrelated CPU measured 128.7–245.2%, 238.9–268.8%, and 214.7–243.3% across
the three receipts. No timed rows were produced and no processes were stopped.
The receipts are in the local-only
`benchmarks/results/2026-10-13/kata-finish-20261013-1/` directory and are
excluded from Git.

A new eight-sample preflight on clean `main` commit
`a851386cc252fed04c95e3c4fbddc342c630351c` also rejected before timing.
Unrelated aggregate CPU ranged from 35.4% to 156.2%; a Google Chrome Helper
renderer exceeded 25% for four consecutive intervals and peaked at 104.8%,
while a Codex renderer reached 25.5%. The receipt records
`timing_benchmark_started: false`; no process was stopped. Its JSON is
local-only at
`target/benchmark-preflight/wh9k-a851386cc-preflight-1.json` and is excluded
from Git.

The next benchmark work is limited to the underqualified matched pairs once a
host window passes preflight. The full parity suite does not need to be
repeated unless its code or input identity changes. This preparation
establishes no repeatable performance gain.

### Latest FastAPI HTTP/1 measurement attempt (2026-10-13)

After the host preflight accepted on `cc485f3b4`, one normal-build run measured
the 15 selected stock-FastAPI HTTP/1 workloads against Uvicorn `httptools` on
asyncio and uvloop. Each server/workload used three repetitions, five seconds
per sample, one second warmup, and concurrency 64. All **180/180** rows passed
response checks and server lifecycle checks; there were no request failures,
unexpected native errors, or panic events. The per-row CPU guard rejected
**151/180** timing rows for unrelated host CPU activity. The analyzer found
**zero qualified workload/loop pairs** with three matching valid repetitions,
so it emitted no ratios or performance medians. This run provides no evidence
of a speedup or regression. Raw rows, logs, and analysis remain local under
`target/benchmark-categories/wh9k-cc485f3b4/` and are excluded from Git. No
full parity or coverage suite was repeated.

## Previous hosted ASGI matrix: run 38122909359

The hosted matrix ran on clean commit
[`9b2d8aaf`](https://github.com/appunni-m/uvicorn-rs/commit/9b2d8aaf321666eb365b1fa69d39029233d0ece0).
The aggregate job validated a **partial** matrix; each platform job stopped in
the sequential category step, so this run does not establish a complete
three-system performance result. Its FastAPI validated-route throughput was
below Uvicorn on all three systems: 0.676×/0.700× on Linux x86-64,
0.769×/0.936× on Linux ARM64, and 0.671×/0.683× on macOS ARM64 (asyncio /
uvloop). The [matrix report and digest manifest](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696763811)
and the [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11697233690),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696963085),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696818454)
artifacts retain the raw category logs outside Git. They expire on 2027-01-09;
no benchmark logs or raw reports are committed.

The incomplete categories stopped at different boundaries:

| System | Category and failing input | Observed failure |
|---|---|---|
| Linux x86-64 | HTTP/2 `protocol-scope`, Rust/uvloop, repetition 5 | The response check passed, then the server logged only `connection task failed: connection error`. Shutdown exited cleanly; the underlying error is not identified. |
| Linux ARM64 | HTTP/2 `many-response-chunks`, Rust/asyncio, repetition 4 | The response check passed, then the same generic Rust connection error was logged. Shutdown exited cleanly; the underlying error is not identified. |
| Linux ARM64 | HTTP/3 `fixed`, Hypercorn/uvloop, repetition 2 | The client timed out waiting for response headers. Hypercorn logged an unhandled `KeyError(0)` while looking up an H3 stream; the cause of the missing response is not established. |
| macOS ARM64 | HTTP/1 FastAPI upload, 1 MiB body in 1 KiB writes, Rust/uvloop, repetition 1 | libcurl reported 31 send failures across 110 requests. FastAPI observed `ClientDisconnect`, followed by the server's disconnect-before-response-start error. The trigger remains unconfirmed. |

These observations do not establish one shared failure cause or a complete
performance ranking. Only individually qualified matched pairs are reported.

The docs updater pushed commit [`94f68885`](https://github.com/appunni-m/uvicorn-rs/commit/94f68885d3455383a806c606b53781fe7be7b7a2)
to `automation/benchmark-results`, then failed in the final “Propose the
updated results documentation” step (job
[`114433266672`](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/job/114433266672#step:5:76)).
The GitHub Actions job log confirms that the branch push succeeded, but
`gh pr create` was rejected with `GitHub Actions is not permitted to create or
approve pull requests (createPullRequest)`. The workflow requested
`pull-requests: write`; the effective Actions policy still blocked PR creation.
The docs update is on the pushed branch, but no PR was opened. This permission
failure is separate from the aggregate benchmark result.

The separately attached `asgi-category-benchmarks-macos-arm64 (1).zip` has
SHA-256 `92e2cd68d8afb38a367b6e789fc5143e6ff054b7cf7b3ab3298466692ee7091a`,
identical to the [macOS artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696818454)
above. It adds no new benchmark
samples. Its HTTP/1 category stopped after 120/300 rows when a 1 KiB upload
case failed in the libcurl client; FastAPI then observed a client disconnect.
The analyzer withholds all H1 ratios because the category is incomplete. The
other categories produced 14 HTTP/2, 12 HTTP/3, 6 WebSocket, and 2 lifecycle
matched descriptive pairs. The H1 experiment and its interpretation limits
are recorded in [the local retries section](#h1-benchmark-source-retries-interrupted-by-host-load-2026-10-12)
below.

The later attached `asgi-category-benchmarks-macos-arm64.zip` has SHA-256
`e556828c831dbec775a3da4a58445d96e60453f0874711b028717566b38593a3`. It
contains 11 preparation files, including the detailed parity report, but no
timed category results. That report records the exact old first-receive
mismatch: Uvicorn returned `http.disconnect`, while uvicorn-rs returned
`http.request` followed by `http.disconnect`; both follow-up responses were
200 and both connections remained usable. The report ran clean revision
`72dfa51` and had 239/240 parity cases pass.

The old fixture waited a fixed 50 ms after its app checkpoint. The driver
closed the client after observing that checkpoint, then waited 250 ms before
releasing the app; the fixture did not wait for that release. So the first
the fixed delay did not order the first `receive()` after the driver's
post-close settle interval. The fixture now waits for the release marker. The corrected case
passed one focused run plus 10 repeats locally with matching oracle and target
observations. This identifies a test synchronization flaw but does not prove
the old runtime correct or incorrect for an immediate post-disconnect receive,
and it is not a hosted rerun. See the archived-row review and repeat
evidence (`benchmarks/results/2026-10-12/http1-disconnect-before-first-receive-repro/README.md`).

The Tokio blocking-pool experiment passed 243/243 public parity cases with the
default, 1-thread, and 4-thread settings. Its first timing slice has one
qualified descriptive pair: default pool, stock FastAPI, 1 MiB request body,
64 KiB client callback cap, three host-valid repetitions per server. Uvicorn
handled 4,149 requests/s and Rust 3,840 (0.925×); Rust p50/p95/p99 and observed
server CPU were higher. The setting comparison is incomplete: cap 1 had no
qualified pairs, and cap 4 has not been timed. See the full experiment
report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/README.md`).

Twelve earlier consecutive host preflights (receipts 5–16) rejected before
benchmark startup. The latest of those samples found
`mediaanalysisd` at 66.2–100.9% of one core, `qemu-system-aarch64-headless`
reached 28.7% in one interval, and aggregate unrelated CPU ranged from 94.8%
to 140.1%, with consecutive samples over the aggregate threshold. No process
was stopped. Subsequent short windows accepted for the default and cap-1 runs,
but the per-row guard still rejected noisy rows. Ten later cap-4 preflights
rejected; the first (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-4-host-preflight.json`)
and latest (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-4-host-preflight-retry-9.json`)
receipts show the aggregate and sustained-process guards. Three subsequent
focused cap-1 preflights rejected under the same guards; see the latest
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-1-focused-preflight-retry-2.json`).
Eighteen resumed preflights also rejected before timing: `mediaanalysisd` used
29.3–101.5% of one core, `qemu-system-aarch64-headless` reached 78.7%, and
aggregate unrelated CPU ranged from 56.2% to 279.6%. The latest sample found
`mediaanalysisd` at 29.3–96.1% and aggregate unrelated CPU at 56.2–115.2%.
No process was stopped.
See the first (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-1.json`)
and latest (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-18.json`)
receipts.
See the current experiment
status (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/current-run-status.md`).
The latest goal-continuation preflight also rejected before timing: unrelated
aggregate CPU ranged from 115.1% to 178.8%, a `python3.12` process used
94.6–100.6% of one core throughout all eight intervals, and
`qemu-system-aarch64-headless` reached 79.6% in one interval. The receipt
records process names and PIDs only; no benchmark started and no process was
stopped. See the latest receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-goal-continuation-20261012.json`).
The intended comparison isolates stock FastAPI 1 MiB uploads with 64 KiB and
256 KiB client writes against Uvicorn on the same asyncio loop. No performance
claim about pool-cap effects follows from this partial timing evidence.

A fresh standalone host preflight after the profile review rejected as well:
the process named `python3.12` used 85.3–104.3% of one core in all eight
intervals, and unrelated aggregate CPU ranged from 100.4% to 151.4%. The
receipt captures names and PIDs, not the process command. No timed benchmark
started in that rejected window and no process was stopped. Later short windows
accepted for default and cap 1, but the cap comparison remains incomplete. See
the preflight receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-post-doc-audit.json`).

### HTTP/2 benchmark-client shutdown check (2026-10-12)

The two hosted HTTP/2 failures had successful client response checks, clean
server-process exits, and one generic Rust connection-error line. The H2 load
client previously discarded its connection-driver result and returned without
explicitly draining the driver. It now drops all request senders, waits for
each driver to finish its GOAWAY/TLS shutdown, and fails the client correctness
gate if a driver reports an error or does not stop within five seconds.

The local check passed six of six rows across three repetitions each of
`protocol-scope` and `many-response-chunks`: response checks passed, server
lifecycle gates passed, and no unexpected native diagnostics were recorded.
Only two rows passed the host timing guard, below the three-repetition
threshold; this is a teardown correctness check, not a performance result. The
raw report and server logs (`benchmarks/results/2026-10-12/http2-client-shutdown-20261012/README.md`)
record the command, source identity, host, and exclusions. A hosted rerun is
still needed to confirm whether this client lifecycle defect explains the
previous intermittent server diagnostic.

## Local FastAPI results

### Recorded FastAPI-only subset (macOS ARM64, 2026-10-11)

The archived run used stock FastAPI, Starlette, and Pydantic on CPython 3.12.13,
with concurrency 64 and five planned repetitions. Its selected HTTP/1 subset
completed 40/40 response-checked rows; one row was excluded by the host timing
guard. These measurements are from clean commit `9b2d8aa`, not the current
worktree. Uvicorn's `httptools` implementation is the reference for both loop
pairs.

| FastAPI workload / loop | Rust/Uvicorn throughput | p50, Uvicorn → Rust | p95, Uvicorn → Rust | Server CPU µs/request, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: |
| Validated route / asyncio | 0.671× | 7.109 → 11.481 ms | 14.612 → 22.294 ms | 121.2 → 202.0 |
| Validated route / uvloop | 0.683× | 6.213 → 9.793 ms | 12.460 → 19.037 ms | 107.1 → 173.8 |
| Python CPU handler / asyncio | 0.991× | 117.5 → 124.5 ms | 161.2 → 183.8 ms | 1,958.8 → 2,062.9 |
| Python CPU handler / uvloop | 0.938× | 108.0 → 118.3 ms | 146.8 → 183.1 ms | 1,731.7 → 1,881.5 |

The lightweight validated route exposes materially higher Rust request-path
cost in this Python integration. When the Python handler spends much longer
computing, throughput is close to Uvicorn's and the same extra fixed cost is a
smaller share of total time. This localizes the gap to work around the
application path, but does not attribute it to a specific parser, Tokio stage,
or Python bridge function. The containing five-category matrix remains
incomplete because HTTP/1 stopped during a separate upload workload; its other
protocol results cannot turn these rows into an overall speed claim. The
[hosted matrix artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696763811)
records the raw per-system rows and digest manifest; its partial status is
summarized above.

### H1 benchmark-source retries interrupted by host load (2026-10-12)

The attached macOS ZIP was an exact duplicate of the previously analyzed
artifact. Two fresh local attempts used the captured dirty source snapshot and normal
native extension, which passed **243/243 public parity cases** before timing.
Both initial host preflights accepted, but unrelated CPU activity returned
during the 300-row HTTP/1 runs. The first stopped after 41 rows (zero response
failures, 24 timing-valid, 17 host-rejected); the retry stopped after 22 (zero
response failures, 9 timing-valid, 13 host-rejected). Both strict analyses
withheld ratios because category completion and identity gates were incomplete,
and both post-stop preflights rejected. Do not combine the partial attempts or
draw a performance conclusion. See the attempt ledger and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/README.md`).

### H1 benchmark-source route and fixed-response batch (2026-10-12)

A separate complete 40-row selected-subset run passed all response checks; 30
rows passed the timing guard and three workload/loop pairs qualified. The
validated FastAPI route measured 0.900× Uvicorn throughput under asyncio and
0.966× under uvloop. The fixed response measured 0.750× under asyncio; its
uvloop pair had only two valid repetitions. The qualified pairs used 9.0–20.1
µs more aggregate server-process CPU per operation. This does not isolate the
CPU between the Python event loop, PyO3 bridge, and Rust networking. The
source-bound report and raw rows (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-route-fixed/README.md`)
record the exact identity and limits. These results cover two of 15 H1
workloads and do not establish an overall speedup.

### H1 benchmark-source response workloads (2026-10-12)

A separate 60-row batch covered large responses, many response chunks, and
small response chunks. All correctness rows passed; 50 timing rows passed the
host guard and five workload/loop pairs qualified. Throughput versus Uvicorn
was 0.871× and 0.931× for large responses, 0.956× for many chunks under
asyncio and 1.275× under uvloop, and 0.920× for small chunks under asyncio.
Small chunks under uvloop had only two valid repetitions. Rust used more
aggregate server-process CPU in all five qualified pairs; the measurements do
not attribute that CPU to a particular Python or Rust function. The report
and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-response-workloads/README.md`)
record the source identity, latency, CPU, RSS, exclusions, and limits. Across
the two completed H1 subsets, results show regressions on several workloads
and one uvloop streaming win; they do not show a broad speedup.

### H1 benchmark-source request-upload workloads (2026-10-12)

A 120-row batch exercised six upstream FastAPI upload cases: 1 MiB request
bodies with 64 KiB, 1 KiB, 16 KiB, 256 KiB, and 1 MiB client writes, plus a
64 KiB body sent in 1 KiB writes. All correctness rows passed; 60 passed the
host timing guard, and five workload/loop pairs qualified. Throughput versus
Uvicorn was 0.648× / 0.686× for the standard 64 KiB writes, 1.001× / 0.995×
for 1 KiB writes, and 0.649× for 256 KiB writes under asyncio. Rust used more
aggregate server-process CPU in all five qualified pairs. The remaining cases
did not have enough matching valid repetitions. The report and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-workloads/README.md`)
record the exact identities and limitations. The workload-dependent results
point to request-upload handling for deeper profiling; they do not identify a
specific hot function or establish an overall speedup.

The 1 KiB-write near-parity rows are client-limited: the load generator used
about 10.4–10.8 CPU cores at the observed rate on this 12-core machine. In the
better-loaded 64 KiB-write cases, Rust's 8.8–10.3 ms p50 gap exceeds the
0.27–0.33 ms server CPU increase by a wide margin. The current evidence points
toward receive delivery or waiting latency, but does not identify the precise
stage. The client setting is a cap on libcurl read-callback returns, not a
guarantee of socket-write or packet boundaries.

The post-run host preflight rejected another timed batch before it started:
unrelated aggregate CPU peaked at 134.4% of one core, and `mediaanalysisd`
used 72.4–105.2% across all eight intervals. A later preflight still rejected
with that process above 25% in every interval. No result-grade timing was
started during the rejected windows. A separate diagnostic-only upload profile
ran under host load; every timing row was rejected, while thread snapshots and
sampled stacks identified a possible PyO3 `spawn_blocking`/GIL completion cost.
That observation motivates a controlled pool-limit A/B, but does not quantify
the cause. See the profile report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-profile/README.md`),
preflight receipts (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-h1-rest.json`),
and retry (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-profile-next-2.json`).
The latest host check also rejected before timing: `mediaanalysisd` remained at
63.2–87.9% of one core in all eight intervals, with unrelated aggregate CPU
peaking at 115.9%. A retry 30 seconds later also rejected, with aggregate
unrelated CPU peaking at 290.0% and `mediaanalysisd` remaining at 65.5–87.2% in
all intervals. See the first receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-20261012.json`)
and retry (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry1-20261012.json`).
A second retry rejected too: `mediaanalysisd` remained at 56.6–85.9% in all
intervals, and aggregate unrelated CPU peaked at 136.4%. See the second retry
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry2-20261012.json`).
A third retry rejected as well: unrelated aggregate CPU peaked at 214.2%,
`mediaanalysisd` used 55.1–87.8%, and a `python3.12` process used 86.0–100.5%
in all intervals. No benchmark started and no process was stopped. See the
third receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry3-20261012.json`).
A fourth retry rejected 45 seconds later: `mediaanalysisd` remained at
51.6–98.4%, `rustc` at 94.0–103.5%, and aggregate unrelated CPU peaked at
220.1%. No benchmark started. See the fourth receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry4-20261012.json`).
A fifth preflight 60 seconds later rejected as well: `mediaanalysisd` used
70.8–75.5%, `rustc` used 94.3–101.5% in all intervals, and aggregate CPU
peaked at 211.9%. See the fifth receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry5-20261012.json`).
A fresh preflight on continuation also rejected, with aggregate CPU peaking at
200.3%, `mediaanalysisd` at 50.6–80.4% in all intervals, and a `python3.12`
process at 95.8–97.1% in three intervals. No timing began. See the
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-1.json`).
A second continuation preflight rejected too: aggregate CPU peaked at 227.1%,
`mediaanalysisd` used 46.8–73.5% in all intervals, `git` used 27.5–32.0% in
seven, and `rustc` briefly used 101.1%. See the receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-2.json`).

### Recorded dirty-source five-category run (2026-10-11)

The normal extension passed **243/243 public parity cases** before timing.
The frozen run used upstream FastAPI 0.142.4, Starlette 1.7.0, Pydantic 2.13.5,
Uvicorn 0.54.0, Hypercorn 0.18.0, CPython 3.12.13, macOS 15.7.7 ARM64, and
one Tokio worker. No FastAPI-RS or Starlette-RS app or route was used. The
working tree was dirty at revision `3dcaeaa0caf47aca96412d15451ac6a1123ebb04`;
`src/lib.rs` SHA-256 was
`5ecbf23cbd9cb430be9af6c9f69399bc4c835eb4441c8f8794f4e3c881beca7d`, and the
normal native extension SHA-256 was
`5c23a4e33006b6183f3a0bba89b2506c3866be2d293b9cd49ebffb037c47b028`.

The five-category analysis (`benchmarks/results/2026-10-11/fastapi-current-full-category-20261011-retry1/analysis.md`)
and its raw rows keep each category and each host-rejected sample separate.
HTTP/1 completed all 300 planned rows with zero response failures, but only 20
passed the timing guard and **no H1 workload/loop pair qualified**. HTTP/2
stopped after 68/140 rows when uvicorn-rs could not bind its HTTP/3 endpoint
(`Address already in use`); all 68 collected rows had zero response failures.
HTTP/3 completed 130/130 rows (112 timing-valid, 10 qualified pairs), WebSocket
completed 60/60 (57 timing-valid, 6 pairs), and lifecycle completed 20/20 (14
timing-valid, 1 pair).

An isolated HTTP/2 retry (`benchmarks/results/2026-10-11/fastapi-current-full-category-20261011-http2-retry1/analysis.md`)
completed all 140 planned rows with zero response failures; 26 rows passed the
timing guard and two workload/loop pairs qualified. Its only qualifying
workload was protocol-scope, at 3.566× throughput under asyncio and 3.995×
under uvloop versus Hypercorn. This retry is a separate attempt and is not
pooled with the incomplete HTTP/2 category from the five-category run.

| Category and workload | Reference | Asyncio Rust/reference | Uvloop Rust/reference |
| --- | --- | ---: | ---: |
| HTTP/2 protocol-scope | Hypercorn | 3.566× | 3.995× |
| HTTP/3 large response | Hypercorn | 9.514× | 19.904× |
| HTTP/3 many response chunks | Hypercorn | 17.051× | 18.040× |
| HTTP/3 slow-reader backpressure | Hypercorn | 0.997× | 0.996× |
| WebSocket connection handshake | Uvicorn | 2.181× | 1.804× |
| WebSocket text echo | Uvicorn | 0.593× | 0.716× |
| WebSocket binary 64 KiB echo | Uvicorn | 1.029× | 1.060× |

These are workload-specific same-host results. They show large gains on some
HTTP/2 and HTTP/3 transfer cases, slower text WebSocket echo, near parity on
WebSocket binary echo and H3 slow-reader load, and no clean H1 result for the
that benchmark source. The full matrix is marked `incomplete_categories`; it does not
establish an overall server speedup. A passing host preflight did not guarantee
clean timing windows: the per-sample guard rejected 280/300 H1 rows and
114/140 rows in the isolated H2 retry because of unrelated host CPU activity.
Three matching repetitions are a descriptive evidence threshold, not a
statistical-significance claim.

Two fresh preflights before a focused H1 retry rejected the host before
starting timed work. `mediaanalysisd` used 73.1–98.2% and 68.7–94.8% of one
core; unrelated aggregate CPU reached 118.2% and 107.4%. Both receipts confirm
that no benchmark started: first (`benchmarks/results/2026-10-11/fastapi-current-h1-focused-retry-20261011/host-preflight.json`)
and second (`benchmarks/results/2026-10-11/fastapi-current-h1-focused-retry-20261011-2/host-preflight.json`).

The 2026-10-10 exact-source FastAPI category matrix (`benchmarks/results/2026-10-10/fastapi-current-matched-matrix-20261010/README.md`)
uses stock FastAPI on CPython 3.12.13, one Tokio async worker, and source
`1f222c0…` with normal extension `bf3cb99…`. It has 390/390 complete-matrix
correctness rows, 420 focused retry rows, and 192 deeper H1 rows. H1 fixed
requests regress against Uvicorn as concurrency rises; H1 upload diagnostics
locate latency in `receive()` delivery and the Rust/Python future bridge.
HTTP/1 streaming has near-parity rate with higher Rust CPU, while WebSocket
handshake and qualifying HTTP/2/3 workloads favor Rust. The per-workload table
and source-snapshot interpretation are in the report; there is no single
cross-protocol speed ratio.

### HTTP/3 request semantics

The H3 benchmark client now follows [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
for request content: ordinary GETs carry no content and omit `Content-Length`;
the route that consumes a body uses POST with one byte, and upload uses POST
with its configured body. HTTP specifications are the source of truth when a
wire-level compatibility observation conflicts with them.
The corrected-input smoke run (`benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/analysis.md`)
passed 24/24 response checks. Its 0.2-second duration is exploratory; although
the analyzer formed one matched H3 uvloop pair, the fresh host preflight had
rejected and the run is not a performance result. Older rows that sent a
one-byte GET body are a different input identity. See the [HTTP/3 request-shape
details](benchmark-results.md#http3-request-shape-correction-2026-10-11).
Thirteen subsequent preflights rejected timed work for aggregate unrelated CPU
above 100% of one core and a process above the per-process threshold in
consecutive intervals. The latest receipt (`benchmarks/results/2026-10-11/wh9k-after-native-core-20261011-1.json`)
records no benchmark start. In preflight 13, unrelated CPU ranged from
49.4–122.2% of one core and `mediaanalysisd` used 28.1–102.7% across eight
intervals. Preflight 12 recorded 119.0–172.3% aggregate activity, with a Codex
renderer peaking at 39.0% and a Chrome helper at 63.0%. Earlier rejected
receipts remain available beside the benchmark results.

Follow-up diagnostics now cover all 15 HTTP/1 workload variants with thread
CPU counters and add 320 response-checked stage rows for HTTP/2, HTTP/3, and
WebSockets. See the per-thread report (`benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md`)
and protocol-stage report (`benchmarks/results/2026-10-10/fastapi-current-protocol-stages-20261010/README.md`).
The stage timings are diagnostic-only; the ordinary matched matrix remains
the throughput, latency, process CPU, and RSS evidence.

A 32-byte WebSocket text-echo attempt on the recorded benchmark source passed 20/20 payload
checks, but all 20 timing rows failed the host-activity guard. Its
receipt (`benchmarks/results/2026-10-10/fastapi-current-ws-text-echo-20261010/README.md`)
records the attempt without making a small-frame speed claim.

The exact-source per-thread CPU retry covers 15 HTTP/1 workloads, four
server/loop variants, and five repetitions: 300 response checks passed and
193 timing captures passed the host and identity guard. Its paired CPU split
shows the Python loop near or below Uvicorn on most routes, with additional
work on Tokio-named threads for fixed requests, uploads, and chunked output.
The per-workload report (`benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md`)
keeps lower-count pairs and host-rejected captures visible. An earlier 228-row
attempt had no timing captures pass the guard; it remains in the
attempt receipts (`benchmarks/results/2026-10-10/fastapi-causal-profiling-20261010/attempts.md`).

The earlier focused diagnosis on source `6b164eb…` (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/README.md`)
adds per-thread CPU evidence and qualified upload, streaming, WebSocket, HTTP/2,
lifecycle, H3 chunked-response, and slow-reader follow-ups. It narrows the main
measured HTTP/1.1 upload cost to request-body delivery and the Python/Rust
async/bytes boundary; the Python CPU route stays near parity. For that
`6b164eb…` source, four shared clean 1 MiB-upload CPU profile repetitions measured
274.8 µs/request for Uvicorn and 547.5 for uvicorn-rs, including 374.2 µs on
Tokio-named threads. A later diagnostic profile covers all 11 H1 FastAPI
workloads with three clean matched per-thread CPU repetitions each on that
earlier source. These remain separate evidence; the current `1f222c0…` source
now has its own 15-workload CPU profile with varying clean-pair counts, linked
above. Neither report provides function-level CPU shares. The earlier-source
profile confirms that uvicorn-rs uses less Python event-loop CPU but adds CPU
on Tokio-named threads. Separately, the current matrix source `1f222c0…` has a
feature-gated upload diagnostic: p50 `receive()` wait is 21.334 ms for
uvicorn-rs and 12.997 ms for Uvicorn; app time outside awaited ASGI I/O is
0.117 ms versus 0.061 ms; Python-bytes materialization takes 73.0 µs. Those
instrumented timings do not rank throughput or isolate pure `memcpy` CPU
time. On source `1f222c0…`, normal-build H3 large and chunked responses qualify
at concurrency 1; the stage report adds attribution for those paths. No
higher-concurrency H3 capacity claim is available.

The full five-category report (`benchmarks/results/2026-10-10/fastapi-final-506/README.md`)
uses source hash `b5c1140…`. Its seven low-concurrency H3 comparisons and
20-repetition lifecycle results are historical evidence for that source.
The newer focused report above uses dirty working-tree hash `6b164eb…`: H1
uploads and small WebSocket echo remain slower; the Python CPU
route is near parity; H2 transfer cases favor Rust over Hypercorn; and two H3
workloads qualify at concurrency 1. H3 large-response and high-concurrency
results remain incomplete. Both reports are single-host evidence, not a
cross-platform performance claim. The captured dirty-source thread and stack
profiles point to receive-bridge scheduling and per-frame overhead; they do
not provide function-level CPU shares. The expanded per-thread profiles add
all 11 H1 workload categories but still do not resolve individual function CPU
shares. No SIMD hotspot was identified. A feature-instrumented follow-up
measured the full request `bytes` conversion path at about 73 µs per 1 MiB
upload, but it does not separate the allocator from the copy loop. A complete
allocation/copy ledger remains open; see the bridge and copy report (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/copy-time-runtime-diagnostics-retry2-20261010/README.md`).

A same-source request-body batch-threshold experiment compared the current
256 KiB default with a temporary 1 MiB threshold on FastAPI's 1 MiB upload.
The baseline reached three shared clean pairs; host contention left the
candidate below the three-pair gate. Its two isolated clean pairs suggest
small CPU savings alongside higher RSS and worse tail latency, but are not
enough to justify changing the default. The 256 KiB source and matching native
build are restored. See the threshold experiment receipt (`benchmarks/results/2026-10-10/fastapi-upload-threshold-ab-20261010/README.md`).

The dirty `6b164eb…` working tree passed 243/243 normal-build public parity
cases. The unified matrix passed 506/506 cases across three complete runs;
Coverage-MCP measured 5,518/5,518 regions and 3,960/3,960 lines. This does not
replace hosted exact-commit CI: run #50 on `e8148e4` has a WSS oracle timeout,
and the package and Python-floor jobs were skipped.

Two fresh local host preflights were rejected before timing. The latest
eight-interval sample found unrelated `rustc` at 96.9–100.8% and
`mediaanalysisd` at 74.8–95.8% of one core in every interval; aggregate
unrelated CPU was 187.1–214.1%. No benchmark process was started. The
first receipt (`benchmarks/results/2026-10-10/fastapi-current-host-preflight-20261010/README.md`)
and follow-up receipt (`benchmarks/results/2026-10-10/fastapi-current-host-preflight-retry2-20261010/README.md`)
retain the measurements and guard policy.

A third eight-interval sample at 14:35 UTC also rejected timing. Unrelated
aggregate CPU ranged from 116.6% to 251.4% of one core; `mediaanalysisd` was
over 25% in every interval, while `rustc` and the Codex renderer also exceeded
the guard in consecutive intervals. No benchmark process was started. See the
third preflight receipt (`benchmarks/results/2026-10-10/fastapi-current-host-preflight-retry3-20261010/README.md`).

The earlier 2026-10-09 full-category run used stock FastAPI, Starlette, and
Pydantic, with one configured Tokio worker. H1, H2, WebSocket, and lifecycle
completed 520 correctness rows and produced 32 workload/loop pairs with at
least three valid matched repetitions. H3 at concurrency 64 stopped on
Hypercorn reference timeouts and produced no valid pair. The newer low-load H3
follow-up is separate evidence and does not establish high-concurrency H3
performance.

The report fastapi-thread-cpu-attribution (`benchmarks/results/2026-10-09/fastapi-thread-cpu-attribution/README.md`)
adds 48 signal-gated CPU captures across four FastAPI H1 workloads, two event
loops, and both servers. Every response passed; 12/48 captures passed the
host/identity timing guard, so all CPU captures are diagnostic-only. A separate
direct timer measured the synchronous FastAPI CPU handler in 12 captures, all
with the guard passing. It found the Python handler near parity and the
largest extra process CPU on request-body receive paths. Exact native
function-level CPU shares and a complete allocation/copy ledger remain open.

The committed `e8148e4` per-thread CPU run (`benchmarks/results/2026-10-09/fastapi-thread-cpu-mach-current-source-run2/README.md`)
passed all 12 response checks and 11/12 host/identity guards. Its clean
1 MiB-upload rows attribute about 563 µs/request of uvicorn-rs CPU to
Tokio-named threads, with 22–23 runtime-named threads observed despite one
configured async worker. The Rust Python loop itself used slightly less CPU
than Uvicorn's. These measurements are for the committed source before the
later dirty `6b164eb…` capture and must not be merged with its 374 µs/thread
result. They remain diagnostic-only and do not identify hot functions.

The committed `e8148e4` upload write-size sweep (`benchmarks/results/2026-10-09/fastapi-upload-granularity-current/README.md`)
passed response checks and obtained three to five valid pairs per workload.
For 16 KiB–1 MiB client writes, uvicorn-rs delivered about half Uvicorn's
throughput and used about three times its server CPU. Separate receive-stage
counters showed 18 Rust ASGI body messages and 17.9 bridge futures per request
versus five Uvicorn receives, while Python-bytes copy volume stayed at one
payload. This strengthens the receive-bridge diagnosis; function-level CPU
shares remain open.

The latest native stack captures (`benchmarks/results/2026-10-09/fastapi-native-stack-attribution-run2/README.md`)
add 12 correctness-passing profiles of the same FastAPI routes across asyncio
and uvloop. They show upload time concentrated in `receive()` awaits, chunked
response time in bounded Rust `send()` waits, and multiple Tokio-named runtime
threads under load despite one async worker. These are diagnostic wall-time
samples, not CPU shares or rankable benchmark rows.

The local 494-case ASGI evidence archive (`benchmarks/results/2026-10-09/asgi-unified-coverage-494/`)
records 240 live oracle comparisons, 254 target-only fault contracts, three
complete repeats, 5,298/5,298 Rust regions, 3,753/3,753 lines, and 240/240
normal-wheel parity. This archive is dirty local evidence based on `f260d78`;
the current `e8148e4` source has the same `src/lib.rs` hash, but the archive is
not an exact-commit hosted verification.

A fresh normal-wheel rerun on the current `e8148e4` source passed all 240
public parity cases with zero behavioral or infrastructure failures. The
focused TLS-WebSocket case that timed out once in hosted CI passed three
consecutive local oracle comparisons. These runs used the same source and
native-extension hashes recorded above, but the checkout was dirty, so they
do not replace clean hosted evidence. Raw reports are
here (`benchmarks/results/2026-10-09/current-full-parity-recheck-240.json`)
and here (`benchmarks/results/2026-10-09/wss-oracle-exact-e8148e4-retry3/`).

A separate 2026-10-10 follow-up repeated that WSS input eight times on the
current working tree: seven passed and one was classified as an oracle
infrastructure timeout. The failure occurred while a preflight sample showed
unrelated `mediaanalysisd` and `rustc` using about one CPU core each; three
later standard attempts and three debug attempts passed. This supports a
load-sensitive timeout as a possibility, not a proven root cause, and the
follow-up is not an exact source/build or hosted CI gate. See the
WSS follow-up receipt (`benchmarks/results/2026-10-10/ci50-wss-oracle-followup-local-20261010/README.md`).

## Latest hosted correctness and release CI

CI [run 38087300590](https://github.com/appunni-m/uvicorn-rs/actions/runs/38087300590)
completed successfully on commit [`16ed349`](https://github.com/appunni-m/uvicorn-rs/commit/16ed349f0d1528b8e6f42536b3d406ce17799915).
All eight hosted jobs passed: exact installed-wheel public parity, the full
parity and fault-contract matrix with 100% native region and line coverage,
Rust quality and documentation, the Rust minimum, package verification on
Windows/Linux/macOS, and the declared Python-floor wheel. This establishes
those gates for that commit; it does not provide a validated performance
matrix or release-candidate bundle.

CI [run 38079929722](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929722)
also passed on `443c5cc`; see the benchmark matrix section below for the
separate performance workflow that failed after its parity gates.

## Historical hosted correctness and release CI (CI #54)

CI [run #54](https://github.com/appunni-m/uvicorn-rs/actions/runs/38045596633)
completed on `a93cdff`. Rust quality, Rust 1.85, and installed-wheel public
parity passed (240/240). Unified native coverage measured 5,298/5,298 regions
and 3,753/3,753 lines, but its first case-attribution pass completed 492/494:
one oracle failure and one target-adapter infrastructure failure. The oracle
case was `http3.concurrent-stream-load-slow-reader-resource-bound`. The
infrastructure case was
`lifespan.active-response-stream-drains-on-tls-shutdown`; its annotation says
the Rust connection task failed while draining the completed response during
shutdown with `tls handshake eof`. Three later complete matrix runs each
passed 494/494. The aggregate correctly remains incomplete because those
later repeats do not erase the first-pass attribution failures. CI runs the
case-attribution pass with `--case-infra-retries 0`, and its evidence checker
requires zero failed or infrastructure-failed case receipts. A fresh run must
complete attribution and all three repeats cleanly. The two named cases passed
four focused repetitions each on the clean local `a93cdff` worktree; that does
not establish the hosted cause. The hosted annotation does not expose the
HTTP/3 observations needed to establish why its parity check failed. No clean
release candidate is established by this run.

Follow-up inspection found that the TLS-drain case reports this adapter error
after its response-body, stream-finished, and connection-close assertions have
passed. Its listener-closure check used raw TCP probes even for TLS, which can
create an incomplete-handshake EOF if a probe is accepted during shutdown. A
local HTTPS-probe correction passed 10/10 TLS-drain runs on `a93cdff`, 3/3
neighboring HTTP-drain cases, 3/3 neighboring TLS fault cases, and 6/6 runs on
the candidate source used in those local runs. The hosted cause remains unconfirmed; details and
receipts are in the TLS-drain probe follow-up (`benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md`).

## Earlier hosted multi-system benchmark (run #11)

The [ASGI performance matrix run #11](https://github.com/appunni-m/uvicorn-rs/actions/runs/38045596557)
ran on `a93cdff` across Linux x86-64, Linux ARM64, and macOS ARM64. The x86-64
and macOS jobs failed the exact normal-binary parity gate before timing. ARM64
passed parity and ran the categories, but its analysis gate failed. The
aggregate and documentation-update jobs then failed, so there is no validated
three-system report. GitHub lists all three per-system artifacts, but their
contents and job logs require authenticated access in this environment.
The public run annotations alone are insufficient to diagnose the row-level
failures or support performance claims.

## Hosted follow-up validation

Commit [`b2ea48bc`](https://github.com/appunni-m/uvicorn-rs/commit/b2ea48bc25835f37eab41a0f408ea8e4072c4e92)
changes only the parity runner's TLS listener-closure probe. CI #55
([run 38058258362](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258362))
and ASGI performance matrix #12
([run 38058258390](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258390))
were triggered on that commit. At 2026-10-10 14:16 UTC, CI #55 showed Rust
quality and MSRV passing, installed-wheel parity passing 240/240, and unified
coverage still running. The old 494-case excerpt supplied for CI #54 reports
an infrastructure failure in the TLS-drain adapter check, not a response or
ASGI behavior mismatch. The local HTTPS-probe correction and focused receipts
are recorded in the TLS-drain probe follow-up (`benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md`).

At that snapshot, benchmark #12 remained in progress. Its Linux x86-64 job
failed the exact-binary step,
`Gate the exact normal binary on every indexed public parity case`; the FastAPI
control and sequential category steps were skipped, so this system produced no
timing data. GitHub exposes the artifact
`asgi-category-benchmarks-linux-x86_64` (SHA-256
`f0ad1637ad6a494f3f3a94977ffb8cc2a1b5871a56eacd8b83b743ff60a1d4c7`); its
archive download returns 401 without authentication, and the job-log endpoint
returns 403 with `Must have admin rights to Repository`. The public annotation
does not identify which parity case failed. Linux ARM64 and macOS ARM64 jobs
remain in progress; there is no validated aggregate yet.
The hosted runs use committed server source from `a93cdff` plus the runner-only
change in `b2ea48bc`; they do not validate the dirty Rust candidate measured
in the later local reports.

At 2026-10-10 14:53 UTC, CI #55 was terminal after 28m44s. Rust quality, MSRV,
and installed-wheel parity passed (240/240). Unified coverage attributed all
494 indexed cases and measured 5,298/5,298 regions and 3,753/3,753 lines, but
the gate failed in repeat 2: 486 cases passed, the target-only fault contract
`fault.http1.early-response-body-drain-terminal-frame` was classified as
infrastructure-failed (`request-body test fault was not consumed`), and seven
later cases were not run. The previous CI #54 HTTP/3 oracle failure is not the
failure reported by #55; the hosted HTTP/3 observations from #54 remain
unavailable, so its cause is still unconfirmed.

The fault contract passed three focused local repetitions on the same
`a93cdff` Rust source, using a selected-subset coverage invocation. Each run
attributed 2,002 regions and 1,449 lines; the focused report is incomplete by
design and does not satisfy the full coverage gate. See the
reproduction receipt (`benchmarks/results/2026-10-10/ci55-body-pump-fault-repro-a93-20261010/README.md`).

Commit [`72dfa51`](https://github.com/appunni-m/uvicorn-rs/commit/72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f)
adds bounded case-specific annotations to the benchmark parity step and is
now pushed to `main`. CI #56 completed successfully on this exact commit: the
installed-wheel parity, unified coverage, package, Python-floor, Rust quality,
and MSRV gates passed. ASGI performance matrix #13 is still running on the same
commit. Its macOS ARM64 job failed exact parity at
`http1.disconnect-before-first-asgi-receive` before timing; its Linux x86-64 and
Linux ARM64 jobs passed parity and the FastAPI control, then entered sequential
category measurements. No three-system benchmark aggregate is available yet.
The exact-commit local reproduction (`benchmarks/results/2026-10-10/ci13-disconnect-exact72-repro/README.md`)
passed the case 60/60 times with matching oracle and target observations. The
hosted artifact row is now retained: Uvicorn returned `http.disconnect`, while
uvicorn-rs returned `http.request` followed by `http.disconnect`; both
follow-up responses were 200 and both connections remained usable. The fixture
uses a 50 ms delay, which is not an acknowledgment that the Rust side observed
TCP EOF before its first ASGI receive. The cause remains unconfirmed. Benchmark
#13's macOS ARM64 job failed before timing, so it supplies no macOS performance
result; the last observed Linux jobs entered category measurements, but no
validated three-system aggregate is recorded. Benchmark #12 is terminal
without validated timing data: all three system jobs and aggregation failed,
with the Linux x86-64 parity gate stopping before timing.

## Previous hosted benchmark matrix attempt: run #16

ASGI performance matrix [run #16](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730)
ran on clean commit [`443c5cc`](https://github.com/appunni-m/uvicorn-rs/commit/443c5cc64bbb23f79cfc21edb85f11bcab9199be).
GitHub's run and job-step metadata show that all three system jobs passed
environment setup, the release-wheel build, identity freeze, the exact-binary
public-parity gate, and the FastAPI-only comparison. All three then failed in
the sequential full-category step. The multi-system validation/render job
succeeded, while the documentation-update job failed when proposing the
updated results documentation. The available metadata does not identify which
category or check caused the three category-step failures, so this run does not
establish a validated multi-system performance result.

GitHub lists the unexpired [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11681132542),
[Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11681108761),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11680829825),
and [aggregate artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11681333990).
Their hosted category logs and analysis are not present in this checkout.
Inspect the `run.json`, category JSON/logs, and `analysis.json` from those exact
artifacts before attributing the hosted failure.

A separate exact-source local run on commit `443c5cc` completed its public
parity gate (240/240) and all 650 category rows with zero recorded failures.
Its analysis and raw evidence (`benchmarks/results/2026-10-11/fastapi-exact-443c5cc-local-evidence/README.md`)
show 570/650 timing rows rejected for unrelated host CPU activity; only three
matched H1 pairs qualified. The 1 MiB upload measured 0.453× Uvicorn throughput
under asyncio and 0.544× under uvloop, while HTTP/2, HTTP/3, WebSocket, and
lifecycle had no qualified pairs. This local result confirms that host load
can prevent timing qualification but does not diagnose the hosted run #16
failure.

The latest local preflight, run 7, again rejected timing before starting a
benchmark: unrelated host CPU ranged from 101.0% to 156.7% of one core, and
`mediaanalysisd` used 74.4% to 100.5% in all eight intervals. See the
preflight receipt (`benchmarks/results/2026-10-11/kata-continuation-host-preflight-7/host-preflight.json`).

A fresh preflight after the HTTP/3 input correction also rejected timing before
starting a benchmark. Unrelated CPU reached 298.1% of one core; `homed` used
58.7% to 126.4% and `cloudd` used up to 76.4% across the rejected intervals.
The host guard rejected both aggregate and sustained per-process activity. See
the preflight receipt (`benchmarks/results/2026-10-11/h3-corrected-current-host-preflight-20261011-1.json`).

The earlier 78-row full H3 report is not validation of the corrected request
framing: its recorded source hashes for the H3 script and client were
`d3f11375` and `8e798372`, and its client binary hash was
`a6947902`. The current H3 script and client source hashes are `26567768` and
`34d464c5`, and the current binary hash is `c0ae1fce`. Exclude the earlier
report's zero-failure count from evidence for the correction; its raw rows (`benchmarks/results/2026-10-11/fastapi-kata-continuation-http3-20261011/http3.json`)
remain available for its original run identity.

The focused 24-row report matches the current H3 script, client source, and
binary identities. It covers `protocol-scope` and
`protocol-scope-consumed-request`, with zero request failures and 16/24
timing-valid rows. See its raw report (`benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/http3.json`).

The complete corrected H3 matrix subsequently finished with 130/130 planned
rows and zero request failures. Source, native-extension, and probe-binary
identities were stable before and after the run. The host guard accepted 69
timing rows and rejected 61 for unrelated host CPU activity. At least three
matched valid repetitions exist for `protocol-scope` and `fixed` under both
loops, `large-response` under both loops, and `protocol-scope-consumed-request`
under uvloop. The run analysis (`benchmarks/results/2026-10-11/h3-rfc-input-corrected-repeat-20261011-1.artifacts/README.md`)
reports their same-repetition throughput, latency, server CPU, and RSS ratios.
These are one local Mac run against Hypercorn, not a multi-system or repeated
release performance result. The chunked-response and slow-reader workloads
have no qualified pairs; H3 upload has no Hypercorn reference rows and no valid
Rust timing rows. The raw report (`benchmarks/results/2026-10-11/h3-rfc-input-corrected-repeat-20261011-1.json`),
JSONL checkpoints, and runner log retain all results.

Review of run #16's `443c5cc` client source found that it sent a one-byte body
with `Content-Length: 1` on every non-upload GET workload. The current
candidate sends bodyless GETs for ordinary requests and POST with one byte only
for the request-consuming workload, in accordance with RFC 9110's GET
semantics. The corrected full matrix passed its response checks. This input
correction does not by itself establish why run #16 exited nonzero; that still
requires the retained category log.

The first four post-run host preflights rejected timing before starting another
measurement. Unrelated CPU ranged 178.6–200.0%, 78.4–202.4%, 90.6–282.9%,
and 171.9–199.7% of one core across their eight intervals. The first recorded
`rustc` and `mediaanalysisd` above 25% in every interval; the third included
sustained `mediaanalysisd` activity. See preflight 1 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-1.json`),
2 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-2.json`),
3 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-3.json`),
and 4 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-4.json`).
No process was stopped and no benchmark measurement began during these
preflights.

## Release candidate

No release-candidate bundle is ready. CI run `38087300590` passed its eight
hosted gates on clean commit `16ed349`. The newer ASGI benchmark matrix
`38122909359` stopped in the sequential category step on all three systems, so
it produced no validated multi-system performance result. Its docs-update job
pushed the evidence branch, then `gh pr create` failed because GitHub Actions
was not permitted to create or approve pull requests. No PR was opened. No tag,
GitHub Release, crates.io publication, or PyPI package was created. See
[release status](releases.md).

## Reproduction

Use the maintained setup and commands in the [benchmark guide](benchmarks.md).
Freeze the source, native extension, FastAPI app, clients, Python and
dependencies; pass the complete parity gate before timing; retain rejected
attempts; and report each protocol/reference separately. A failed reference
workload is incomplete evidence, not a performance result.
