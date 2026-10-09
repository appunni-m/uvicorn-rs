# Feasibility and performance scope

## Decision

The measured goal of a general speed advantage over Uvicorn is not achieved. The project should be described as an independent Rust-first ASGI server with a documented support subset, not as a faster Uvicorn replacement. Keep performance claims workload-specific. The current evidence supports continuing compatibility and release-candidate work; it does not justify another broad optimization campaign.

This scope revision follows the benchmark objective: stop after the prototype when matched measurements show no meaningful overall gain. The bounded body-coalescing experiment did not reduce the receive/future counts and was removed. Future performance work should require a specific measured bottleneck, parity on unchanged ASGI behavior, and a repeatable end-to-end improvement.

## Current correctness evidence

On the dirty local checkout based on `f260d78`:

- The unified black-box matrix passed 494/494 cases: 240 oracle-parity cases and 254 target-only fault contracts.
- All three complete repeats passed 494/494.
- Coverage-MCP verified 5,298/5,298 Rust regions and 3,753/3,753 lines, with zero region or line gap groups.
- The normal non-instrumented wheel passed all 240 public parity cases.

The compact evidence package is [asgi-unified-coverage-494](../benchmarks/results/2026-10-09/asgi-unified-coverage-494/). This is local macOS arm64 evidence for the declared default-feature Rust source. It is not hosted exact-commit verification or full ASGI conformance.

## Matched FastAPI benchmark

The benchmark used stock FastAPI 0.142.4, Starlette 1.7.0 and Pydantic 2.13.5 on CPython 3.12.13, macOS 15.7.7 arm64 and an Apple M3 Pro. Uvicorn 0.54.0 with httptools 0.8.0 was the H1, WebSocket and lifespan reference. Hypercorn 0.18.0 was the H2/H3 reference. No FastAPI-RS or Starlette-RS implementation was used. The Rust runtime had one configured Tokio async worker; both asyncio and uvloop were measured as the Python-owned ASGI loop.

The latest sequential category attempt passed 520 correctness rows and produced 32 qualified local workload/loop pairs. Each qualified comparison has at least three timing-valid paired repetitions. Host-contended rows were retained and excluded. These dirty-checkout, single-host results are not a cross-platform performance claim.

| Category | Reference | Correct rows | Qualified pairs | Finding |
|---|---|---:|---:|---|
| HTTP/1.1 | Uvicorn | 300/300 | 12 | Mixed; ordinary routes and large responses regress, Python CPU is near parity |
| HTTP/2 | Hypercorn | 140/140 | 14 | Fixed and large responses are faster; small-chunk upload is slower |
| HTTP/3 | Hypercorn | 2/130 at concurrency 64 | 0 in that run | Stopped after reference response-header timeouts; no high-concurrency comparison |
| WebSockets | Uvicorn | 60/60 | 5 | Handshake is faster; text echo is slower |
| Lifespan/shutdown | Uvicorn | 20/20 | 1 | Too few pairs for a performance conclusion |

Representative asyncio results:

| Workload | Throughput, Rust/reference | p50, reference → Rust | Server CPU, reference → Rust |
|---|---:|---:|---:|
| H1 validated FastAPI route | 0.908× | 4.381 → 4.928 ms | 68.5 → 83.2 µs/op |
| H1 large response | 0.874× | 6.411 → 7.920 ms | 100.6 → 130.4 µs/op |
| H1 default 1 MiB upload, separate qualified run | 0.458× | 19.248 → 44.933 ms | 319.5 → 1,088.6 µs/op |
| H1 Python CPU route | 1.043× | 59.708 → 60.416 ms | 955.9 → 934.8 µs/op |
| H2 fixed response | 3.720× | 9.135 → 2.606 ms | 147.5 → 48.2 µs/op |
| H2 large response | 8.077× | 264.3 → 32.572 ms | 4,122.3 → 574.1 µs/op |
| H2 small-chunk upload | 0.548× | 53.090 → 100.8 ms | 860.6 → 2,613.3 µs/op |
| WebSocket handshake | 2.151× | 0.420 → 0.189 ms | 281.1 → 152.3 µs/op |
| WebSocket text echo | 0.591× | 1.108 → 1.863 ms | 17.3 → 48.1 µs/op |

The [complete latest analysis](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/analysis.md) preserves p50/p95/p99, client and server CPU, sampled RSS, exclusions and per-workload qualification. The default upload row comes from an earlier qualified run with the same source and normal-extension hashes; it is not the 1 KiB-write workload in the latest retry. Ratios are never combined across protocols or references.

## Where the measured overhead is

For a 1 MiB H1 upload, Rust delivered about 18 ASGI request-body messages and scheduled about 17.8 receive-bridge futures per request; Uvicorn delivered five messages. The Rust path copied approximately one payload’s worth of data into Python bytes, not 18 full copies. Repeated PyO3 future completion, GIL attachment and Python event-loop scheduling are the stronger measured cost signal. `uvloop` improved the default upload comparison but did not close the gap. The source-matched [diagnosis and raw runtime counters](../benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md) document this evidence and its instrumentation limits.

For a 1 MiB response in 256 chunks, Rust’s bounded body queue filled about 15.8 times per response and accumulated roughly 40–50 ms of send wait. In the fast-reader diagnostic, TCP write-pending time was negligible. This locates that wait before socket writes. The instrumented timings locate work; they are not normal-build speed comparisons.

The Python CPU route is near parity because both servers execute the same Python application and remain subject to Python’s GIL. The one Tokio async worker is not a cap on process OS threads: PyO3 completion uses Tokio’s blocking pool, and diagnostic samples observed multiple Tokio-named thread identities under concurrency.

These measurements do not identify a SIMD hotspot. Exact function-level on-CPU shares and comparable total allocation counts remain unmeasured; sampled wall stacks include waiting threads.

## Benchmark artifacts and reproduction

See [benchmark results](benchmark-results.md) for the current result index and [the benchmark guide](benchmarks.md) for commands, identities, workload definitions, validity gates and measurement limits. The machine-readable category rows and analyzer output are retained beside the full analysis.

A future performance claim requires a clean source identity, the normal-wheel parity gate, at least three matching valid repetitions for each claimed workload, and separate results for each platform and protocol reference. A failed reference workload remains visible and cannot be silently patched or counted as a comparison.
