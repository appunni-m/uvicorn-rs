# Exact-source FastAPI benchmark: full-category retry

**Status:** Local, dirty-checkout evidence. HTTP/3 did not complete, so this is
not a complete cross-protocol result or a release performance claim.

## Identity and method

- Commit: `f260d78c71e9266c2b3301ab3915f74de5511fc2` (dirty worktree).
- Rust source SHA-256: `56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`.
- Normal native extension SHA-256: `94c677f0e37a52bd80d81571997443a60d69379c16bb2acdcf9831bddb0499b0`.
- Apple M3 Pro, macOS 15.7.7 arm64, 12 logical CPUs; Rust 1.98.1;
  CPython 3.12.13; FastAPI 0.142.4, Starlette 1.7.0, Pydantic 2.13.5,
  Uvicorn 0.54.0, Hypercorn 0.18.0, uvloop 0.23.0, httptools 0.8.0.
- The workloads use upstream FastAPI and its stock Starlette/Pydantic
  dependencies. `fastapi-rs` and `starlette-rs` were not used.
- Rust used one configured Tokio async worker. Each category used five
  repetitions, five seconds per sample, one second of warmup, and concurrency
  64. The categories ran sequentially. Uvicorn is the reference for HTTP/1.1,
  WebSockets, and lifecycle; Hypercorn is the reference for HTTP/2 and HTTP/3.
- The exact normal extension passed the 239-case public parity gate before
  timing. Source and native-extension identities stayed stable during the
  completed categories.

## Category results

The completed categories passed all 520 response, message, or lifecycle
correctness rows. A qualified pair is one workload/event-loop comparison with
at least three matching timing-valid repetitions. Counts from different
protocols are not combined into a single speed ratio.

| Category | Reference | Rows completed | Timing-valid rows | Qualified workload/loop pairs | Result |
|---|---|---:|---:|---:|---|
| HTTP/1.1 | Uvicorn | 300/300 | 165 | 12 | Complete locally |
| HTTP/2 | Hypercorn | 140/140 | 135 | 14 | Complete locally |
| HTTP/3 | Hypercorn | 2/130 planned | — | 0 | Stopped on reference timeout |
| WebSockets | Uvicorn | 60/60 | 51 | 5 | Complete locally |
| Lifespan/shutdown | Uvicorn | 20/20 | 13 | 1 | Complete locally |

HTTP/3 stopped during `protocol-scope-consumed-request` at concurrency 64:
the Hypercorn/uvloop reference reported 64 response-header timeouts among
3,840 requests. The category produced only two Rust-side rows before stopping;
they do not form a comparison. The earlier concurrency-1 HTTP/3 results are
separate evidence in the
[exact-source diagnosis](../../fastapi-exact-f260-one-tokio/README.md).

## Representative matched results

Throughput ratios are Rust divided by the named reference. Latency is median
per-run p50; CPU is server process-tree microseconds per operation.

| Category / workload / loop | Rust/reference throughput | p50 reference → Rust | Server CPU reference → Rust |
|---|---:|---:|---:|
| HTTP/1.1 FastAPI validated route / asyncio | 0.908× | 4.381 → 4.928 ms | 68.5 → 83.2 µs/op |
| HTTP/1.1 FastAPI large response / asyncio | 0.874× | 6.411 → 7.920 ms | 100.6 → 130.4 µs/op |
| HTTP/1.1 FastAPI many response chunks / asyncio | 0.955× | 43.517 → 47.029 ms | 682.9 → 1,081.5 µs/op |
| HTTP/1.1 FastAPI many response chunks / uvloop | 1.265× | 46.970 → 37.797 ms | 742.1 → 868.3 µs/op |
| HTTP/1.1 FastAPI 1 MiB upload in 1 KiB writes / asyncio | 1.084× | 197.8 → 187.5 ms | 990.7 → 1,705.2 µs/op |
| HTTP/1.1 FastAPI Python CPU route / asyncio | 1.043× | 59.708 → 60.416 ms | 955.9 → 934.8 µs/op |
| HTTP/2 FastAPI fixed response / asyncio | 3.720× | 9.135 → 2.606 ms | 147.5 → 48.2 µs/op |
| HTTP/2 FastAPI large response / asyncio | 8.077× | 264.3 → 32.572 ms | 4,122.3 → 574.1 µs/op |
| HTTP/2 FastAPI small-chunk upload / asyncio | 0.548× | 53.090 → 100.8 ms | 860.6 → 2,613.3 µs/op |
| WebSocket handshake / asyncio | 2.151× | 0.420 → 0.189 ms | 281.1 → 152.3 µs/op |
| WebSocket text echo / asyncio | 0.591× | 1.108 → 1.863 ms | 17.3 → 48.1 µs/op |

The FastAPI Python CPU route is near parity because both servers execute the
same Python application work. HTTP/2 wins are against Hypercorn's Python
implementation; they are not Uvicorn comparisons. WebSocket handshake gains
do not carry over to per-message echo. The HTTP/2 small-chunk upload and
HTTP/1.1 route/response rows show material regressions.

The previous qualified exact-source run measured the default 1 MiB upload at
0.458× Uvicorn throughput under asyncio (3,123.3 → 1,428.7 requests/s), with
p50 rising from 19.248 to 44.933 ms and server CPU from 319.5 to 1,088.6
µs/op. Its uvloop throughput ratio was 0.563×. The current retry did not
qualify the default upload workload, so the earlier pair remains the evidence
for that exact case; see the
[exact-source diagnosis](../../fastapi-exact-f260-one-tokio/README.md).

## Where HTTP/1.1 time goes

The stage diagnostics in the
[exact-source diagnosis](../../fastapi-exact-f260-one-tokio/README.md) show that
the FastAPI handler itself is not the main source of the ordinary-route gap:
the Rust ASGI call p50 was 26.0 µs versus Uvicorn's 32.9 µs, while the normal
fixed-route comparison still had lower Rust throughput and higher server
CPU.

For 1 MiB request bodies, Rust delivered about 18 `http.request` messages and
created about 17.8 receive-bridge futures per request; Uvicorn delivered five
messages. The Rust path copies one payload's worth into Python `bytes`, split
across those messages, rather than copying the full body 18 times. Each
receive crosses the PyO3/asyncio boundary; the installed
`pyo3-async-runtimes` completion path submits Python-future completion through
Tokio's blocking pool. This adds scheduling, attachment, and Python-object
work and explains why Rust's one async worker does not mean one operating
system thread under load.

For 256-chunk responses, the Rust bounded response queue filled about 15.8
times per request and accumulated roughly 40–48 ms of queue-send wait, while
TCP write-pending time remained below about 1.1 µs per request in that probe.
That points to ASGI-to-transport queue backpressure, not SIMD or socket writes,
as the measured wait location. These instrumented values locate work; they
are not normal-build CPU attribution or timing comparisons.

## Artifacts

- [Full analyzed tables, exclusions, and limits](analysis.md)
- [Machine-readable analysis summary](analysis.json)
- [Raw category run and identity gates](run.json)
- [HTTP/1.1 observations](http1.jsonl), [HTTP/2 observations](http2.jsonl),
  [WebSocket observations](websocket.jsonl), and
  [lifecycle observations](lifecycle.jsonl)
- [Lifecycle startup/shutdown phases](lifecycle.phases.jsonl)
- [HTTP/3 partial observations](http3.jsonl) and
  [HTTP/3 failure log](http3.log)
- [Source/build manifest](../../asgi-unified-coverage-494/source-manifest.json) and
  [240-case normal-wheel parity receipt](../../asgi-unified-coverage-494/normal-public-parity-240.json.gz)

This is one dirty-worktree macOS run. It does not prove a multi-system speed
advantage or production readiness. The host-contention guard rejected invalid
rows; the full analyzer lists every exclusion and comparison qualification.
