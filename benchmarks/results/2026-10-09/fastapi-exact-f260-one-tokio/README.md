# Exact-source FastAPI runtime diagnosis

This report isolates overhead in the Rust/Python boundary for upstream
FastAPI. The measured Rust source hash is
`56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; the
normal extension hash is
`94c677f0e37a52bd80d81571997443a60d69379c16bb2acdcf9831bddb0499b0`. The
machine was an Apple M3 Pro running macOS 15.7.7 arm64, CPython 3.12.13, Rust
1.98.1, FastAPI 0.142.4, Starlette 1.7.0, and Pydantic 2.13.5. No
FastAPI-RS or Starlette-RS app or runtime was used. Rust used one configured
Tokio async worker; Uvicorn 0.54.0 used httptools 0.8.0 for both asyncio and
uvloop comparisons.

## Matched normal-build results

The separate
[five-category retry](../fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/README.md)
is the latest broad run. The earlier exact-source runs add two qualified
measurements that were not qualified in that retry: the default H1 upload and
H3 at concurrency 1. Their source and native extension hashes match the later
run.

The default 1 MiB H1 upload measured 3,123.3 requests/s on Uvicorn and 1,428.7
on uvicorn-rs under asyncio, a 0.458× ratio. Median per-run p50/p95/p99 latency
rose from 19.248/25.143/28.162 ms to 44.933/47.000/50.601 ms. Server CPU rose
from 319.5 to 1,088.6 µs/request. Under uvloop the throughput ratio was
0.563×. A different latest-run workload that deliberately writes the same
body in 1 KiB client chunks measured 1.084× throughput but 1.72× server CPU;
the client spent substantially more time sending, so these two upload cases
must not be merged.

The earlier H3 run at concurrency 1 qualified 10 workload/loop pairs against
Hypercorn. For the fixed response under asyncio, throughput was 2,056.1 vs
8,817.3 requests/s (4.275×), p50/p95/p99 was 0.481/0.531/0.583 vs
0.111/0.129/0.140 ms, and server CPU was 353.2 vs 86.1 µs/request. These
results do not establish performance at ordinary high concurrency. The latest
concurrency-64 H3 reference timed out and produced no matched comparison.

Summary tables are in the [H1 analysis](http1-attempt1/analysis.md) and
[H3 concurrency-1 analysis](http3-concurrency1/analysis.md). Raw matched rows
and run identities are retained in the [H1 JSONL](http1-attempt1/http1.jsonl),
[H1 run receipt](http1-attempt1/run.json),
[H3 JSONL](http3-concurrency1/http3.jsonl), and
[H3 run receipt](http3-concurrency1/run.json).

## Instrumented boundary diagnosis

The focused instrumented run contains 48 body-checked rows: four FastAPI
workloads (fixed response, validated route, 1 MiB upload, and 256 response
chunks), four server/loop configurations, and three repetitions. Its
[machine-readable report](diagnostics/stage-attribution.json),
[checkpoint rows](diagnostics/stage-attribution.jsonl), and
[raw server receipts](diagnostics/stage-attribution.artifacts/) retain the
stage observations and runtime counters. Instrumentation changed timings, so
these values locate work but are excluded from performance ratios.

### Request uploads

For the 1 MiB request, Rust materialized about 18 ASGI body messages and
scheduled about 17.8 receive-bridge futures per request; Uvicorn exposed five
ASGI messages. The Rust byte counter records approximately one payload's
worth copied into Python `bytes`, split across those messages, not 18 complete
copies. Each Rust receive goes through `future_into_py`, then Python-future
completion, GIL attachment, and event-loop scheduling. The additional
messages/futures and the longer measured receive-await are the strongest
evidence for the default upload regression.

### Streaming responses

For 256 chunks, Rust's bounded response queue filled about 15.8 times per
response and accumulated roughly 40–48 ms of full-queue send wait. In the
fast-reader diagnostic, TCP write-pending wait was below about 1.1 µs per
response. The wait is therefore at the ASGI-to-Hyper queue before socket
writes. A paced slow reader exercises both queue and TCP backpressure.

### Short requests and CPU attribution

The instrumented FastAPI call itself is not slower on the fixed route: its
Rust p50 was about 26 µs versus Uvicorn's 33 µs, while normal-build throughput
and server CPU still favored Uvicorn. This points to request setup, bridge,
protocol, or response scheduling around the Python handler. A near-parity
Python CPU route confirms that the same Python application work is not where
the broad overhead appears.

The available Apple `sample` captures are wall-time stacks and include waiting
threads. They do not establish per-function on-CPU shares; exact CPU attribution
and comparable total allocation counts remain unmeasured. No vectorizable
byte-processing hotspot has been identified, so this evidence does not support
SIMD as the next optimization.

The complete matched workload table and qualifications are in the
[benchmark results](../../../../docs/benchmark-results.md). The
[full local report](../fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/)
retains all categories, latency percentiles, CPU, RSS, and excluded rows.
