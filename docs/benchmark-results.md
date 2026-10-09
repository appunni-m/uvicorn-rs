# FastAPI benchmark results

This page reports only upstream FastAPI on its normal Starlette and Pydantic
dependencies. No FastAPI-RS or Starlette-RS app or runtime was used. Results
are local, source-bound evidence from one Apple M3 Pro; they are not a
cross-platform release claim.

## Latest five-category run

The [full report](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/README.md)
measured the same FastAPI 0.142.4 app on CPython 3.12.13, macOS 15.7.7 arm64,
with Rust 1.98.1 and one configured Tokio async worker. Uvicorn 0.54.0 with
httptools 0.8.0 is the H1, WebSocket, and lifespan reference. Hypercorn 0.18.0
is the H2 and H3 reference. Both asyncio and uvloop owned the Python ASGI app
loop. The run used five repetitions, five seconds per sample, one second of
warmup, and concurrency 64. Source and normal extension hashes stayed stable.

| Category | Reference | Correct rows | Qualified pairs | Result |
|---|---|---:|---:|---|
| HTTP/1.1 | Uvicorn | 300/300 | 12 | Mixed; common routes and large responses regress, Python CPU route is near parity |
| HTTP/2 | Hypercorn | 140/140 | 14 | Fixed and large responses are faster; small-chunk uploads regress |
| HTTP/3 | Hypercorn | 2/130 planned | 0 | The concurrency-64 reference timed out; no pair qualifies |
| WebSockets | Uvicorn | 60/60 | 5 | Handshakes are faster; text echo is slower |
| Lifespan/shutdown | Uvicorn | 20/20 | 1 | One workload/loop pair; insufficient for a category conclusion |

The four completed categories passed 520 correctness rows. The H3 failure was
64 response-header timeouts in the Hypercorn/uvloop reference during
`protocol-scope-consumed-request`; the two Rust rows are not a comparison.
An earlier run of the same Rust source and native extension measured H3 at
concurrency 1 against Hypercorn and qualified 10 workload/loop pairs. Its
[per-workload analysis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/http3-concurrency1/analysis.md)
is separate evidence and does not establish high-concurrency H3 performance.

Representative matched results follow. Throughput is Rust/reference; latency
is the median of per-run p50 values; CPU is server process-tree microseconds
per operation. The [complete analysis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/analysis.md)
contains every qualified workload's p50/p95/p99, server/client CPU, sampled
RSS, invalid rows, and comparison exclusions.

| Workload and loop | Throughput ratio | p50 reference → Rust | Server CPU reference → Rust |
|---|---:|---:|---:|
| H1 validated FastAPI route / asyncio | 0.908× | 4.381 → 4.928 ms | 68.5 → 83.2 µs/op |
| H1 large response / asyncio | 0.874× | 6.411 → 7.920 ms | 100.6 → 130.4 µs/op |
| H1 1 MiB upload, 1 KiB client writes / asyncio | 1.084× | 197.8 → 187.5 ms | 990.7 → 1,705.2 µs/op |
| H1 Python CPU route / asyncio | 1.043× | 59.708 → 60.416 ms | 955.9 → 934.8 µs/op |
| H2 fixed response / asyncio | 3.720× | 9.135 → 2.606 ms | 147.5 → 48.2 µs/op |
| H2 large response / asyncio | 8.077× | 264.3 → 32.572 ms | 4,122.3 → 574.1 µs/op |
| H2 small-chunk upload / asyncio | 0.548× | 53.090 → 100.8 ms | 860.6 → 2,613.3 µs/op |
| WebSocket handshake / asyncio | 2.151× | 0.420 → 0.189 ms | 281.1 → 152.3 µs/op |
| WebSocket text echo / asyncio | 0.591× | 1.108 → 1.863 ms | 17.3 → 48.1 µs/op |

These ratios are per workload and reference. Do not combine H1, H2, H3, or
WebSocket results into one overall speed number. The deliberate 1 KiB-write
upload above differs from the default 1 MiB upload workload: a separate
qualified same-source run measured that default case at 0.458× Uvicorn
throughput, with 2.33× p50 latency and 3.4× server CPU per operation. The
[same-source diagnosis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md)
explains the upload workload difference and keeps its raw rows.

## Where the additional time appears

The normal matrix shows higher server CPU per request on several H1 workloads
and WebSocket echo. A Python CPU-bound route stays near parity in throughput
and server CPU, so the broad H1 overhead is not explained by Rust executing
FastAPI route code more slowly.

The exact-source instrumented probe checked 48 runs of fixed route, validated
route, 1 MiB upload, and 256-chunk response workloads across Uvicorn and
uvicorn-rs with asyncio and uvloop. All responses were checked, but diagnostic
timings are excluded from performance ratios. Its counters locate two strong
cost signals:

1. **Request-body delivery crosses into Python repeatedly.** Rust produced
   about 18 `http.request` messages and 17.8 receive-bridge futures for a
   1 MiB request; Uvicorn produced five messages. Rust copied approximately
   one payload's worth into Python `bytes`, split across those messages. The
   extra cost is per-message PyO3 future completion, Python attachment, GIL
   acquisition, and event-loop scheduling—not 18 full-body copies.
2. **Chunked responses wait in the bounded Rust body queue.** At 256 chunks,
   the queue filled about 15.8 times per response and accumulated roughly
   40–48 ms of queue-send wait. TCP write-pending wait was negligible for a
   fast reader, so that observed wait is before socket writes. The deliberately
   slow-reader case exercises both queue and TCP backpressure.

The focused [diagnostic receipt](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md)
contains the workload receipts and raw Rust counters. The diagnostics used
instrumentation and are location evidence, not CPU-time attribution. The
available Apple `sample` profiles include waiting threads; exact on-CPU
function shares and comparable total allocation counts remain unmeasured.
No SIMD hotspot has been identified. The one Tokio async worker is not a
one-thread process: Python owns a separate event loop, and the PyO3 completion
path can use Tokio's blocking pool.

H2 small-chunk uploads and WebSocket echo also show elevated Rust server CPU,
but they do not yet have matched stage counters that isolate the cause. They
remain optimization targets to investigate, not proven instances of the H1
receive-bridge mechanism.

## Evidence and limits

- The [machine-readable category rows](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/)
  preserve matched repetitions and exclusions; the [methodology](benchmarks.md)
  describes the validity gates and resource accounting.
- The normal extension passed 239/239 public cases before the full-category
  run. The same extension hash subsequently passed the expanded 240/240
  normal-wheel parity matrix in the [coverage evidence archive](../benchmarks/results/2026-10-09/asgi-unified-coverage-494/).
- The checkout was dirty, host-contended rows were retained and excluded, and
  H3 did not finish at concurrency 64. The automated three-system benchmark
  also failed before producing a validated aggregate; see
  [latest run status](benchmark-status.md).
- Three valid matched repetitions are a descriptive gate, not a statistical
  significance test. The closed-loop, same-host load does not correct for
  coordinated omission. RSS is sampled process-tree RSS, not PSS or allocator
  peak.

The project has no broad performance-replacement claim. Continue performance
work only against a measured workload-specific bottleneck and require normal
parity plus repeatable end-to-end improvement before accepting an optimization.
