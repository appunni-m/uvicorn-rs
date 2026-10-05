# Full-category benchmark run: 2026-10-04

## Result and decision

All 338 rows passed their response, payload, protocol, or lifecycle correctness gates: HTTP/1.1 132, HTTP/2 84, HTTP/3 66, WebSockets 36, and lifespan/shutdown 20. The live HTTP, streaming, WebSocket, cancellation, and lifespan probes also passed; see [`live-probes.log`](live-probes.log).

This is a **correctness-complete, performance-provisional** run. Process snapshots show unrelated input generation, parity validation, compatibility-atlas work, mypy, and Rust compilation during the matrix. One Rust compile reached 787% CPU in the snapshot before WebSocket measurements. These samples cannot establish an uncontended or repeatable performance win. Keep them as a diagnosis snapshot; repeat the matrix with background work stopped before publishing a speedup claim.

The data is workload-specific. HTTP/1.1 fixed responses and several Python-heavy cases trail Uvicorn's `uvloop + httptools`; Rust uses more server CPU there. Rust+uvloop improves throughput on this run's chunked H1 responses, small-chunk uploads, and 64 KiB WebSocket binary echo, but also consumes substantially more CPU. H2/H3 compare against Hypercorn, not Uvicorn. H3 fixed responses have a high Rust RSS peak that needs profiling. Do not describe these results as proof that the server is faster overall.

## Method

- Machine: Apple M3 Pro, macOS 15.7.7, 12 logical CPUs; loopback client and server share the host.
- Runtime: CPython 3.12.13; Rust/Cargo 1.98.1; Uvicorn 0.54.0; uvloop 0.23.0; httptools 0.8.0; Hypercorn 0.18.0; libcurl 8.7.1.
- The locked benchmark environment was checked with `uv lock --check`, then the local release extension was rebuilt using `uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs`.
- H1: 11 available workloads, four server configurations, three repetitions, 2 s samples, 0.25 s warmup, seed 20261004; concurrency 64 except slow-reader (8) and exception-to-500 (1). `starlette-rs-route` was omitted because `starlette-rs` was not installed; the remaining 132 rows are the complete available H1 matrix, not the optional integration matrix.
- H2: seven workloads × four server configurations × three repetitions; concurrency 16 except slow-reader (2). TLS ALPN verified H2 and complete response bytes were checked.
- H3: six workloads; three repetitions; concurrency 4 except slow-reader (2). Hypercorn upload rows are excluded; Rust-only upload rows are not a cross-server comparison. QUIC/TLS, status, and response bytes were checked.
- WebSockets: handshake, 32-byte text echo, and 64 KiB binary echo; three repetitions; echo concurrency 32; handshake capped at 500 fresh connections per repetition. Subprotocol and complete payload equality were checked.
- Lifespan/shutdown: five repetitions across the same four server configurations. Startup state, active request cancellation, and process shutdown were checked.
- Throughput, latency percentiles, server CPU, sampled peak RSS, and client CPU are in the raw JSON files. CPU is process CPU divided by elapsed wall time; 100% is one fully occupied logical core. Table values below are medians across each server/workload's repetitions.

## H1: Rust + uvloop vs Uvicorn uvloop + httptools

Each cell lists median rate; p50/p95/p99 latency; sampled server CPU; peak server RSS. `exception-to-500` is a fixed 200-request, concurrency-one microbenchmark, not a saturation test.

| Workload | Rust + uvloop | Reference | Rate ratio |
|---|---|---|---:|
| `fixed` | 39,894/s; 1.58/2.41/2.85 ms; 139% CPU; 31.1 MiB | 67,882/s; 0.81/1.58/1.90 ms; 94% CPU; 32.9 MiB | 0.59× |
| `large-response` | 8,781/s; 7.09/11.78/14.20 ms; 177% CPU; 127.0 MiB | 9,475/s; 5.84/12.40/18.76 ms; 90% CPU; 33.9 MiB | 0.93× |
| `many-response-chunks` | 2,226/s; 29.96/43.60/50.37 ms; 179% CPU; 38.0 MiB | 1,748/s; 32.75/37.48/231.77 ms; 88% CPU; 35.7 MiB | 1.27× |
| `small-response-chunks` | 5,208/s; 12.20/14.56/16.70 ms; 196% CPU; 30.6 MiB | 3,724/s; 16.99/17.71/19.21 ms; 99% CPU; 32.8 MiB | 1.40× |
| `request-upload` | 2,703/s; 23.50/27.08/30.73 ms; 221% CPU; 88.2 MiB | 4,090/s; 15.32/19.81/24.27 ms; 98% CPU; 219.4 MiB | 0.66× |
| `request-upload-small-chunks` | 5,787/s; 10.65/16.34/19.75 ms; 125% CPU; 82.8 MiB | 4,819/s; 12.28/32.06/65.55 ms; 53% CPU; 85.3 MiB | 1.20× |
| `slow-reader-backpressure` | 26/s; 311.44/314.52/314.96 ms; 2% CPU; 26.7 MiB | 26/s; 309.99/314.95/315.46 ms; 2% CPU; 32.7 MiB | 1.00× |
| `scope-32-headers` | 27,385/s; 2.31/3.50/4.06 ms; 131% CPU; 31.2 MiB | 36,959/s; 1.44/3.10/3.97 ms; 94% CPU; 32.0 MiB | 0.74× |
| `contextvars` | 30,665/s; 1.94/3.61/4.96 ms; 126% CPU; 34.7 MiB | 59,746/s; 0.89/1.86/2.84 ms; 94% CPU; 33.2 MiB | 0.51× |
| `sync-callable-awaitable` | 39,842/s; 1.59/2.47/3.10 ms; 138% CPU; 31.3 MiB | 72,914/s; 0.79/1.52/1.74 ms; 96% CPU; 33.1 MiB | 0.55× |
| `exception-to-500` | 2,768/s; 0.34/0.41/0.48 ms; 16% CPU; 24.6 MiB | 6,420/s; 0.12/0.21/0.24 ms; 4% CPU; 31.2 MiB | 0.43× |

The candidate's H1 small-upload baseline client consumed a median 923% CPU, so its measured throughput is client-limited. The 1 MiB response client also used multiple cores on both servers; its server RSS difference deserves allocation/lifetime profiling and is not a stable memory requirement.

To separate raw rate from server CPU efficiency, each sample's request rate was divided by its server CPU fraction (`server_cpu_percent_mean / 100`), then the three per-sample values were summarized by median. Rust+uvloop versus Uvicorn uvloop+httptools measured approximately 28.8k vs 72.0k requests/s per server core for `fixed` (0.40×), 1.22k vs 2.00k for `many-response-chunks` (0.61×), 2.65k vs 3.78k for `small-response-chunks` (0.70×), and 25.0k vs 63.8k for `contextvars` (0.39×). Thus the chunked workloads' higher raw request rate in this run did not reflect better CPU efficiency. These ratios inherit the matrix's host contention and remain exploratory.

## H2: Rust + uvloop vs Hypercorn uvloop

Uvicorn has no HTTP/2 server baseline. The table is a same-protocol Hypercorn comparison.

| Workload | Rust + uvloop | Reference | Rate ratio |
|---|---|---|---:|
| `protocol-scope` | 44,467/s; 0.35/0.56/0.68 ms; 165% CPU; 27.5 MiB | 6,947/s; 2.23/2.86/3.05 ms; 96% CPU; 78.2 MiB | 6.40× |
| `fixed` | 45,689/s; 0.34/0.54/0.68 ms; 166% CPU; 26.7 MiB | 7,215/s; 2.20/2.40/2.56 ms; 96% CPU; 77.4 MiB | 6.33× |
| `large-response` | 1,394/s; 11.48/13.35/14.31 ms; 137% CPU; 28.2 MiB | 368/s; 43.16/47.12/48.99 ms; 98% CPU; 177.4 MiB | 3.78× |
| `many-response-chunks` | 566/s; 27.70/36.76/42.22 ms; 222% CPU; 27.7 MiB | 313/s; 50.98/54.29/56.46 ms; 98% CPU; 88.6 MiB | 1.81× |
| `request-upload` | 1,013/s; 15.32/20.06/22.33 ms; 226% CPU; 47.2 MiB | 393/s; 39.19/53.04/58.65 ms; 97% CPU; 88.9 MiB | 2.58× |
| `request-upload-small-chunks` | 1,577/s; 10.10/11.25/12.25 ms; 233% CPU; 31.4 MiB | 1,276/s; 7.94/46.25/52.43 ms; 97% CPU; 82.6 MiB | 1.24× |
| `slow-reader-backpressure` | 8/s; 250.88/251.72/251.72 ms; 7% CPU; 26.2 MiB | 8/s; 251.87/252.62/252.62 ms; 5% CPU; 93.9 MiB | 1.00× |

## H3: Rust + uvloop vs Hypercorn uvloop

Uvicorn has no HTTP/3 server baseline. Hypercorn's chunk-heavy rows vary substantially by repetition; candidate-only upload rows cannot be used to calculate a ratio. The median of per-repetition sampled peak RSS for Rust fixed responses was 203.9 MiB for asyncio and 252.3 MiB for uvloop at concurrency 4; this remains an open allocation/lifetime question.

| Workload | Rust + uvloop | Reference | Rate ratio |
|---|---|---|---:|
| `protocol-scope` | 8,924/s; 0.42/0.64/1.17 ms; 113% CPU; 110.0 MiB | 2,435/s; 1.53/2.04/4.18 ms; 77% CPU; 92.1 MiB | 3.66× |
| `fixed` | 28,244/s; 0.14/0.19/0.22 ms; 166% CPU; 252.3 MiB | 2,576/s; 1.53/1.77/1.91 ms; 78% CPU; 89.7 MiB | 10.96× |
| `large-response` | 398/s; 9.93/14.01/15.95 ms; 143% CPU; 57.0 MiB | 54/s; 57.00/120.54/179.84 ms; 79% CPU; 124.7 MiB | 7.44× |
| `many-response-chunks` | 374/s; 10.56/13.91/16.76 ms; 156% CPU; 36.9 MiB | 35/s; 94.23/229.60/952.92 ms; 76% CPU; 103.0 MiB | 10.66× |
| `request-upload` | 154/s; 25.31/30.11/36.60 ms; 201% CPU; 46.8 MiB | No comparable reference row | — |
| `slow-reader-backpressure` | 8/s; 251.35/253.02/253.02 ms; 6% CPU; 30.5 MiB | 8/s; 251.19/251.83/251.83 ms; 16% CPU; 100.2 MiB | 1.00× |

## WebSockets: Rust + uvloop vs Uvicorn uvloop

| Workload | Rust + uvloop | Reference | Rate ratio |
|---|---|---|---:|
| `connection-handshake` | 6,028/s; 0.15/0.22/0.28 ms; 61% CPU; 26.6 MiB | 3,684/s; 0.26/0.38/0.53 ms; 76% CPU; 33.3 MiB | 1.64× |
| `text-echo` | 60,525/s; 0.52/0.84/1.05 ms; 244% CPU; 34.3 MiB | 73,207/s; 0.43/0.50/0.67 ms; 94% CPU; 33.2 MiB | 0.83× |
| `binary-64k-echo` | 33,608/s; 0.90/1.57/2.09 ms; 216% CPU; 58.8 MiB | 22,399/s; 1.42/2.04/2.45 ms; 91% CPU; 72.8 MiB | 1.50× |

Handshake rate uses a fixed 500-connection sample; its measured duration varied sharply, so treat that comparison cautiously.

## Lifespan and shutdown

| Server | First lifespan request, ms | Idle SIGTERM exit, ms | Active SIGTERM exit, ms | Peak RSS, MiB |
|---|---:|---:|---:|---:|
| `uvicorn-rs-uvloop` | 43.35 | 9.79 | 2.02 | 24.0 |
| `uvicorn-uvloop-httptools` | 73.37 | 249.29 | 2.16 | 31.5 |
| `uvicorn-rs-asyncio` | 41.86 | 10.54 | 2.05 | 22.7 |
| `uvicorn-asyncio-h11` | 73.80 | 249.19 | 2.16 | 29.2 |

The active SIGTERM test confirmed ASGI task cancellation in all 20 rows. The server's idle SIGTERM exit was much shorter than Uvicorn's default shutdown wait in this harness; that is an operational difference, not a throughput result.

## Bridge counters and performance interpretation

A separate `runtime-diagnostics` build was run only for H1 `fixed` and `many-response-chunks`. Its throughput is instrumented and must not be compared with the normal matrix. The normal extension was restored afterwards and `probe_http.py` passed.

The fixed workload recorded about one scheduled Python ASGI task and one response-body message per request, with no queue-full sends. The 1 MiB, 256-chunk workload recorded exactly 256 response-body messages per request and about 14.9 queue-full sends per request at response queue capacity 16. Accumulated send-wait time was roughly 24–31 ms per request in the Rust+uvloop repetitions. The timer starts when Tokio's channel is full and ends after capacity becomes available; it includes async bridge scheduling and is not pure channel residence time.

These counters show where streaming work crosses the boundary: the Python app calls the PyO3 `send()` method once per ASGI body event, and a full Tokio queue converts some sends into awaitable waits. Fixed-response H1 remains slower even when its response queue never fills, so queue capacity is not the whole explanation. Existing sampled profiles show Python loop wakeups/GIL acquisition, PyO3 ASGI methods, Tokio channels, Hyper body polling, and socket writes on the path; they do not quantify each component's CPU share. The current evidence does not identify a missing SIMD hot loop.

## Raw artifacts and rerun gate

- [`environment.txt`](environment.txt) records revision, environment, and package versions.
- Host snapshots: [`before probes`](processes-before-probes.txt), [`before H1`](processes-before-http1.txt), [`before H2`](processes-before-http2.txt), [`before H3`](processes-before-http3.txt), [`before WebSockets`](processes-before-websocket.txt), [`before lifespan`](processes-before-lifecycle.txt), and [`before bridge diagnostics`](processes-before-bridge-diagnostics.txt). Several contain active unrelated CPU work.
- [`http1.json`](http1.json), [`http2.json`](http2.json), [`http3.json`](http3.json), [`websocket.json`](websocket.json), and [`lifecycle.json`](lifecycle.json) retain every measured row and source digest; matching logs retain runner output.
- [`bridge-diagnostics.json`](bridge-diagnostics.json) and [`bridge-diagnostics.log`](bridge-diagnostics.log) contain opt-in counter data, not ordinary performance measurements.
- `git rev-parse HEAD` was `cf9bf062133721b094e914f49ed8f54c613eb30f`. The worktree was dirty; inspect the recorded status and per-report source digests before attempting an exact reproduction.

For an acceptance benchmark, repeat the documented commands on the same hardware and locked environment with the concurrent build/parity jobs stopped. Save a fresh process snapshot before each category and defer the run if an unrelated compiler, test, emulator, or workload is active. Large transfer cases should be repeated with a separate client host when client CPU approaches saturation. Require repeated, interleaved candidate/reference results with equivalent workload and protocol before accepting a win. If H1 remains slower or less CPU-efficient after an uncontended rerun, revise the project's performance positioning rather than claiming a general Uvicorn replacement.
