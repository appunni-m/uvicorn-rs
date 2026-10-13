# Feasibility and performance scope

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

## Decision

The available matched measurements for the Python ASGI compatibility path do not show a general speed advantage over Uvicorn. The project should be described as an independent Rust-first ASGI server with a documented support subset, not as a faster Uvicorn replacement. Keep performance claims workload-specific. Partial matched measurements exist for later source snapshots, but a complete current-source, multi-category, multi-system comparison has not been qualified. Further optimization should target measured bottlenecks and be validated with fresh matched runs. The [proposed Rust-native FastAPI-RS/Starlette-RS architecture](rust-native-integration-architecture.html) is a separate path and has not been implemented or benchmarked. A release candidate still needs complete multi-system performance evidence.

This scope revision follows the benchmark objective: stop after the prototype when matched measurements show no meaningful overall gain. The 2026-10-10 measured H1 body-pump source coalesced already-arrived request data with a 256 KiB cap and a 1 ms maximum wait. A 1 MiB cap modestly increased throughput but worsened p95/p99 latency and sampled RSS; the 512 KiB run lacked enough clean repetitions. That 256 KiB source setting is a historical benchmark identity, not a fresh qualification of the current source. Future performance work should target a specific measured bottleneck, preserve ASGI behavior, and show a repeatable end-to-end improvement.

## Current-source correctness evidence (2026-10-12)

The dirty macOS ARM64 working tree at revision
`3dcaeaa0caf47aca96412d15451ac6a1123ebb04` passed 511/511 attribution cases
and three complete 511-case repeats: 243 oracle-parity cases and 268
target-only contracts. It measured 5,561/5,561 Rust regions and 3,997/3,997
lines. Coverage-MCP found zero missing region/line groups and reported
`source: matches_receipt`, `tests: passed`. The full report (`benchmarks/results/2026-10-12/unified-coverage-runtime-config-511-corrected/coverage-report.json`)
and MCP receipt (`benchmarks/results/2026-10-12/unified-coverage-runtime-config-511-corrected/coverage-mcp-receipt.json`)
record identities and scope. This verifies the PyO3 adapter's measured
`src/lib.rs`, not a clean hosted build, the separate Python-free native crate,
or the official ASGI suite.

This instrumented coverage run is correctness evidence, not benchmark data.
Its extension must not be used for timing. No normal extension rebuild,
post-rebuild parity run, or new benchmark sample is included. The measured goal
of a general speed advantage over Uvicorn therefore remains unachieved.

### Historical benchmark-source correctness evidence (2026-10-11)

The earlier local macOS ARM64 benchmark-source snapshot at the same revision
had `src/lib.rs` SHA-256
`1f222c06c5ecfa4f1c3b22299259ddb69f5d39822427e50c4a9f8b4eebf8f455`. Its
normal non-instrumented extension passed 243/243 public parity cases (SHA-256
`bf3cb991025074bc416ccd514b836aec31899ca1ce6f0d40bdfa819c9dd07d43`). The
506-case unified matrix passed three complete repeats and measured 5,532/5,532
regions and 3,974/3,974 lines with matching Coverage-MCP evidence. The
historical report (`benchmarks/results/2026-10-11/unified-coverage-kata-continuation-20261011/coverage-report.json`),
receipt (`benchmarks/results/2026-10-11/unified-coverage-kata-continuation-20261011/coverage-mcp-receipt.json`),
and evidence README (`benchmarks/results/2026-10-11/unified-coverage-kata-continuation-20261011/README.md`)
remain source-bound to that benchmark run. The corresponding
FastAPI comparison (`benchmarks/results/2026-10-10/fastapi-current-matched-matrix-20261010/README.md`)
used ordinary FastAPI, Starlette, and Pydantic rather than FastAPI-RS or
Starlette-RS. These local results do not replace hosted exact-commit
verification or establish full Uvicorn compatibility.

The exact-source local category analysis on commit `443c5cc` is preserved in
the evidence report (`benchmarks/results/2026-10-11/fastapi-exact-443c5cc-local-evidence/README.md`).
It qualifies only three H1 workload/loop pairs, including slower 1 MiB uploads;
the remaining rows were rejected for host CPU activity or did not meet the
matched-pair gate. This is separate from the hosted run #16 artifacts and does
not identify their category failure.

## Matched FastAPI benchmark

The benchmark used stock FastAPI 0.142.4, Starlette 1.7.0 and Pydantic 2.13.5 on CPython 3.12.13, macOS 15.7.7 arm64 and an Apple M3 Pro. Uvicorn 0.54.0 with httptools 0.8.0 was the H1, WebSocket and lifespan reference. Hypercorn 0.18.0 was the H2/H3 reference. No FastAPI-RS or Starlette-RS implementation was used. The Rust runtime had one configured Tokio async worker; both asyncio and uvloop were measured as the Python-owned ASGI loop.

The 2026-10-09 sequential category run passed 520 correctness rows and produced 32 qualified local workload/loop pairs. Each qualified comparison has at least three timing-valid paired repetitions. Host-contended rows were retained and excluded. The newer 2026-10-10 FastAPI-only report adds focused H1 uploads and WebSockets, low-load H3, and lifecycle follow-ups. These dirty-checkout, single-host results are not a cross-platform performance claim.

| Category | Reference | Correct rows | Qualified pairs | Finding |
|---|---|---:|---:|---|
| HTTP/1.1 | Uvicorn | 300/300 | 12 | Mixed; ordinary routes and large responses regress, Python CPU is near parity |
| HTTP/2 | Hypercorn | 140/140 | 14 | Fixed and large responses are faster; small-chunk upload is slower |
| HTTP/3 | Hypercorn | 2/130 at concurrency 64 | 0 in that run | Stopped after reference response-header timeouts; no high-concurrency comparison |
| WebSockets | Uvicorn | 60/60 | 5 | Handshake is faster; text echo is slower |
| Lifespan/shutdown | Uvicorn | 20/20 | 1 | Too few pairs for a performance conclusion |

Representative asyncio results from the 2026-10-09 run:

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

The complete 2026-10-09 analysis (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/analysis.md`) preserves p50/p95/p99, client and server CPU, sampled RSS, exclusions and per-workload qualification. The 2026-10-10 result table and full protocol evidence are in [benchmark results](benchmark-results.md). Ratios are never combined across protocols or references.

## Where the measured overhead is

On the 2026-10-10 benchmark source snapshot at dirty revision `6b164eb…`, H1
1 MiB uploads delivered 0.62–0.68× Uvicorn's throughput and used about 2× its
server CPU per request. In clean
signal-gated thread profiles, Uvicorn used 275.4 µs/request on its Python loop;
uvicorn-rs used 173.2 µs on that loop and another 374.0 µs on Tokio-named
threads, for 547.3 µs total. Five clean matched profiles per server support
that split. Fixed-route profiles show a smaller version: 34.0 µs total on
Uvicorn versus 45.2 µs on Rust, including 16.8 µs on Tokio-named threads.
These are diagnostic CPU measurements, not throughput rankings. See the
current fixed-route profiles (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/thread-cpu-profiles-retry/profile-summary.json`)
and upload profiles (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/thread-cpu-upload-retry/profile-summary.json`).

Profiling-only ASGI timing captures show where upload latency appears: p50
`receive()` wait is 24.06 ms on Rust versus 14.83 ms on Uvicorn, close to the
8.96 ms p50 difference in the normal end-to-end benchmark. FastAPI's p50 time
outside awaited ASGI I/O is 0.12 ms and 0.064 ms respectively. The sample
records six Rust `receive()` calls and five Uvicorn calls per 1 MiB upload.
These instrumented timings localize wall time to body delivery and receive
completion; they are not normal-build performance values or pure CPU time.

That measured adapter source materialized one Python `bytes` object per ASGI
`http.request` message. Across a 1 MiB request, each payload byte is copied
once into Python `bytes`; it is not recopied as a complete body for every
message. Stack captures include PyO3's
`future_into_py_with_locals`, Tokio `spawn_blocking`/`BlockingTask`,
`uvloop.call_soon_threadsafe`, and memory movement. The Python CPU route remains
near parity: 1.022× throughput and 925.9 versus 921.1 server CPU µs/request
on uvloop. Taken together, the measurements point to the Python/Rust
receive-completion boundary as the H1 upload cost, not slow execution of the
FastAPI handler or an identified SIMD loop. Full function-level CPU shares and
a complete allocation/copy ledger remain unknown.

The broader 360-profile H1 sweep in
fastapi-final-506 (`benchmarks/results/2026-10-10/fastapi-final-506/current-source-diagnostics/all-http1-thread-cpu-20261010-aggregate.md`)
is for the earlier `b5c1140…` source snapshot, not the later dirty `6b164eb…` benchmark snapshot.
It found 16 clean workload/loop pairs with Rust process CPU at 1.15–2.13×
Uvicorn and excess CPU on Tokio-named threads. Keep that wider sweep as
historical context; do not use it as exact-source current evidence. The single
configured Tokio async worker also does not cap process OS threads: the runtime
has a blocking pool and the captured bridge path uses it.

## Benchmark artifacts and reproduction

See [benchmark results](benchmark-results.md) for the current result index and [the benchmark guide](benchmarks.md) for commands, identities, workload definitions, validity gates and measurement limits. The machine-readable category rows and analyzer output are retained beside the full analysis.

A future performance claim requires a clean source identity, the normal-wheel parity gate, at least three matching valid repetitions for each claimed workload, and separate results for each platform and protocol reference. A failed reference workload remains visible and cannot be silently patched or counted as a comparison.
