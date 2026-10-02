# Full benchmark rerun notes

**Status:** all recorded rows passed their own request/message correctness gates,
except the Hypercorn HTTP/3 comparison, which failed and was rejected. The
Rust-only HTTP/3 matrix passed. Performance figures are exploratory, not a clean
acceptance run.

## Environment and procedure

- Checkout revision: `e015fa62a9e635ed7febc881f766bc4da230e91c`, with local
  modifications recorded in `environment.txt`; the extension was rebuilt in
  release mode from this checkout.
- Apple M3 Pro, macOS 15.7.7, CPython 3.12.13, Rust 1.98.1, Uvicorn 0.54.0,
  uvloop 0.23.0, httptools 0.8.0, and Hypercorn 0.18.0.
- `uv lock --check` passed. The optional `starlette-rs-py` benchmark fixture was
  installed separately from the adjacent checkout at commit
  `dbc1e236b45b9183a6bcf7718ba6b685b90791d1`; it is not a server dependency.
- Seven live probe scripts passed. The version-pinned input-only parity suite
  also passed 19/19 cases; see `live-probes.log`, `asgi-parity.log`, and
  `asgi-parity.json`.
- The documented fixed seed, 2-second samples, 0.25-second warmup, and three
  repetitions were used (five for lifespan). H1, H2, WebSocket, and lifespan
  runners completed their full correctness-gated row sets.

## Category gates

| Category | Rows | Result |
|---|---:|---|
| HTTP/1.1 | 144 | Pass: all 12 workloads across four server configurations |
| HTTP/2 | 84 | Pass: ALPN and complete response bodies across seven workloads |
| HTTP/3 comparison | Partial log; no complete comparison JSON | Fail: Hypercorn asyncio timed out on four fixed-response requests in repetition 3; runner aborted the cross-server comparison |
| HTTP/3 Rust-only | 36 | Pass: six candidate workloads across asyncio and uvloop |
| WebSockets | 36 | Pass: handshake/subprotocol and complete echo payload checks |
| Lifespan/shutdown | 20 | Pass: startup state, graceful exit, and active-request cancellation |

The H3 comparison failure is preserved in `http3.log`. The candidate-only
result is in `http3-candidate-only.json`; it must not be compared as a
Hypercorn speedup.

## Host interference and client limits

The host was not isolated for the whole matrix. The saved category snapshots
show:

- Before H1, two unrelated `rustc` jobs used 72.8% and 71.3% CPU and a Python
  job used 68.2%; the two-sample system snapshot reported 57.4% CPU idle.
- Before the H3 candidate-only retry, an unrelated `rustc` job used 139.6%
  CPU; the system snapshot reported 41.0% idle. This makes the H3 candidate
  measurements especially provisional.
- An Android emulator remained resident throughout. Its process showed about
  8.8–18.1% CPU in the category snapshots and roughly 6 GiB resident memory.
  The WebSocket start snapshot also showed other active desktop/Python work.
- Several large-transfer loopback client samples used 3–6 CPU cores. For
  example, H1's 1 MiB response Rust client reached a 588.8% mean, while the
  Uvicorn client reached 502.2%. Those rows are client-limited or mixed and
  need a separate load-generator host for server-efficiency conclusions.

Process lists and two-sample CPU snapshots before and after every category are
saved next to the category logs. Given these overlaps, do not treat this run as
repeatable performance acceptance evidence, even where repetitions agree.

## Representative medians

CPU is process CPU normalized per logical core (`100%` is one fully occupied
core). Each tuple reports throughput; p50/p95/p99 latency; server CPU; and peak
sampled server RSS. These are medians of the three recorded samples, not
isolated performance claims.

| Category/workload | Rust candidate | Reference | Rate ratio |
|---|---|---|---:|
| H1 fixed response | 31,028 req/s; 1.954/3.745/4.730 ms; 124.4%; 34.7 MiB | Uvicorn uvloop+httptools: 56,694 req/s; 0.845/2.567/4.020 ms; 90.4%; 33.1 MiB | 0.55× |
| H1 256 × 4 KiB response chunks | 892 req/s; 74.187/94.991/103.323 ms; 208.3%; 33.8 MiB | Uvicorn uvloop+httptools: 1,824 req/s; 33.417/36.066/191.256 ms; 98.3%; 37.0 MiB | 0.49× |
| H1 128 × 512 B response chunks | 1,841 req/s; 35.612/55.172/57.701 ms; 208.3%; 29.3 MiB | Uvicorn uvloop+httptools: 3,814 req/s; 16.306/17.266/32.828 ms; 97.1%; 31.3 MiB | 0.48× |
| H1 1 MiB response | 8,629 req/s; 7.310/11.454/13.785 ms; 170.0%; 148.1 MiB | Uvicorn uvloop+httptools: 8,266 req/s; 6.931/13.443/21.486 ms; 84.8%; 33.0 MiB | 1.04× |
| H1 1 MiB upload | 2,893 req/s; 22.089/24.388/26.615 ms; 202.1%; 83.8 MiB | Uvicorn uvloop+httptools: 4,666 req/s; 13.753/16.625/19.373 ms; 96.9%; 220.3 MiB | 0.62× |
| H1 64 KiB upload in 1 KiB chunks | 5,511 req/s; 11.299/16.724/22.152 ms; 111.8%; 84.7 MiB | Uvicorn uvloop+httptools: 3,863 req/s; 13.946/34.217/49.486 ms; 40.0%; 102.7 MiB | 1.43× |
| H1 contextvars | 43,149 req/s; 1.462/2.223/2.634 ms; 136.8%; 30.3 MiB | Uvicorn uvloop+httptools: 69,798 req/s; 0.880/0.990/1.778 ms; 96.7%; 31.3 MiB | 0.62× |
| H2 fixed response | 47,036 req/s; 0.330/0.521/0.621 ms; 165.5%; 26.5 MiB | Hypercorn uvloop: 7,229 req/s; 2.197/2.340/2.471 ms; 95.2%; 76.1 MiB | 6.51× |
| H2 256 × 4 KiB response chunks | 577 req/s; 27.647/32.688/34.700 ms; 251.3%; 26.6 MiB | Hypercorn uvloop: 304 req/s; 52.577/55.605/57.708 ms; 97.1%; 85.1 MiB | 1.90× |
| H3 fixed response, candidate-only | 18,978 req/s; 0.163/0.455/0.727 ms; 134.2%; 177.2 MiB | No valid cross-server result | — |
| WebSocket fresh handshake | 7,113/s; 0.116/0.207/0.251 ms; 54.9%; 26.1 MiB | Uvicorn uvloop: 4,504/s; 0.193/0.308/0.442 ms; 66.0%; 31.5 MiB | 1.58× |
| WebSocket 32-byte text echo | 59,522 msg/s; 0.540/0.798/0.932 ms; 247.0%; 33.5 MiB | Uvicorn uvloop: 71,580 msg/s; 0.445/0.461/0.482 ms; 94.6%; 31.8 MiB | 0.83× |
| WebSocket 64 KiB binary echo | 46,156 msg/s; 0.687/0.969/1.118 ms; 238.4%; 53.9 MiB | Uvicorn uvloop: 31,129 msg/s; 1.009/1.185/1.275 ms; 94.9%; 65.7 MiB | 1.48× |

For lifespan, Rust uvloop medians were 62.14 ms cold-start-to-first-request,
10.57 ms idle SIGTERM exit, 2.05 ms active-request SIGTERM exit, and 23.5 MiB
RSS. Uvicorn uvloop+httptools measured 77.54 ms, 258.52 ms, 2.19 ms, and
30.2 MiB respectively. All 20 rows confirmed active ASGI-task cancellation.

Every workload's p50/p95/p99, server/client CPU, RSS, and raw repetitions live
in `http1.json`, `http2.json`, `http3-candidate-only.json`, `websocket.json`,
and `lifecycle.json`.

## What these measurements say about the overhead

This is not a benchmark of Rust language performance against Python. Both
servers execute the same Python ASGI application. Uvicorn's strongest H1 path
uses `uvloop` and the compiled `httptools` parser on the Python application's
event loop. This server uses Tokio/Hyper for sockets and protocol work while
preserving the caller-owned Python event loop for application tasks.

On a small fixed H1 response, Rust uvloop measured 0.55× the Uvicorn rate,
2.31× its p50 latency, and 1.38× its server CPU. With 256 app-visible body
chunks, it measured 0.49× the rate, 2.22× p50 latency, and 2.12× server CPU.
This pattern is consistent with the added coordination at the ASGI boundary:
the Python task is scheduled with `call_soon_threadsafe`, each `receive()` or
`send()` enters a PyO3 method, Tokio channels carry messages between runtimes,
and a full bounded response queue turns `send()` into an awaited bridge future.
Uvicorn does not cross between two event loops for each request/response path.

That mechanism is supported by the current source and earlier bridge counters,
but the CPU percentages above are not a flame-graph attribution. They do not
tell us the exact share spent in PyO3, scheduling, channels, Hyper framing,
allocation, or kernel calls. The outgoing immutable Python `bytes` path is
already owner-backed and does not copy the payload into Rust. SIMD would not
remove Python message creation, the GIL, task scheduling, channel wakeups, or
per-send backpressure. The next useful optimization step is a quiet-host,
release-mode profile of fixed and chunked H1, followed by one change at a time
and the same correctness gates.

## Artifacts

- [Environment and revision](environment.txt)
- [Live probes](live-probes.log)
- [Input-only ASGI parity result](asgi-parity.json) and [log](asgi-parity.log)
- [HTTP/1.1 results](http1.json), [log](http1.log)
- [HTTP/2 results](http2.json), [log](http2.log)
- [HTTP/3 comparison failure](http3.log)
- [Rust-only HTTP/3 results](http3-candidate-only.json), [log](http3-candidate-only.log)
- [WebSocket results](websocket.json), [log](websocket.log)
- [Lifespan results](lifecycle.json), [log](lifecycle.log)
- [Category exit codes](category-exits.tsv) and [correctness validation](validation.log)
