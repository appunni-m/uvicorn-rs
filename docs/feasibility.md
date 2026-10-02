# Feasibility and category benchmark report

## Decision

The full measurement pass does not support a general claim that this server is faster than Uvicorn. On HTTP/1.1, the Rust server beats Uvicorn's `asyncio + h11` setup on the fixed response, but loses to Uvicorn's `uvloop + httptools` setup there and on most other workloads. The largest H1 regression is 256 response chunks of 4 KiB: Rust/uvloop completes 283 requests/s at 228 ms p50, while Uvicorn/uvloop+httptools completes 1,867 requests/s at 33 ms p50. A 1 MiB response also raises Rust's sampled RSS to about 466 MiB versus 33 MiB for Uvicorn in this run.

HTTP/2 and HTTP/3 show substantial throughput and latency improvements over Hypercorn 0.18.0 on several measured cases. Those paths also use more server CPU, and the Rust load client itself reaches high CPU in some H2/H3 cases. Uvicorn does not support H2 or H3, so these results are same-protocol comparisons against Hypercorn and do not repair the HTTP/1.1 replacement gate. HTTP/3 upload has no Hypercorn comparison because its upload case failed the correctness gate.

Keep the implementation as an independent, correctness-tested protocol prototype. Do not position it as a general Uvicorn replacement or as a production-ready server. Keep the Rust network data plane and thin Python ASGI boundary; any additional performance work should start with profiles of the chunked H1 writer and large-response memory path, then rerun the same cases. SIMD is not supported as the current bottleneck diagnosis.

## Measurement setup and gates

All runs used one machine and environment: Apple M3 Pro, macOS 15.7.7, 12 logical CPUs, CPython 3.12.13, Rust 1.98.1, Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0, and Hypercorn 0.18.0. This is evidence for that environment, not a cross-platform performance claim. CPU percentage is normalized per logical core: 100% is approximately one fully occupied core.

| Category | Matrix and baseline | Correctness gate |
|---|---|---|
| HTTP/1.1 | 12 workloads × four configurations × three repetitions; 2 s samples, 0.25 s warmup, concurrency 64 except slow reader at 8 and exception at 1. The four configurations are Rust asyncio/uvloop and Uvicorn asyncio+h11 / uvloop+httptools. | Every response status and complete response body matched the workload oracle. The exception workload used 200 responses per sample. |
| HTTP/2 | Seven workloads × four configurations × three repetitions; 2 s, 0.25 s warmup, concurrency 16 except slow reader at 2. Hypercorn asyncio/uvloop is the same-protocol baseline. | TLS ALPN negotiated H2; every response status and byte was checked. Upload responses included the byte count consumed by the app. |
| HTTP/3 | Six workloads, three repetitions, concurrency 4 except slow reader at 2. Hypercorn asyncio/uvloop is the baseline. Hypercorn upload rows are excluded after the baseline failed to return a response to the upload probe. | QUIC/TLS handshake, response status, and every response byte were checked. Four QUIC connections distribute the load, with streams multiplexed on each. |
| WebSocket | Handshake, 32-byte text echo, and 64 KiB binary echo; three repetitions. Echo cases use 32 persistent connections. Handshake is capped at 500 fresh connections per sample at concurrency 1 to bound client ephemeral-port use. | Each handshake checked subprotocol `bench`; every echo message was compared byte-for-byte. |
| Lifespan/shutdown | Five repetitions for Rust asyncio/uvloop and Uvicorn asyncio+h11 / uvloop+httptools. | Startup state, lifespan shutdown completion, and cancellation of a held ASGI request were required in every row. |

The combined summary has per-workload medians for throughput, p50/p95/p99 latency, server CPU, sampled server RSS, and client CPU where measured. The raw files retain the per-run measurements and correctness fields:

- [All workload medians and row counts](../benchmarks/results/category-summary-2026-10-02.json)
- [HTTP/1.1, 144 rows](../benchmarks/results/http-categories-2026-10-02.json)
- [HTTP/2, 84 rows](../benchmarks/results/http2-categories-2026-10-02.json)
- [HTTP/3, 66 rows](../benchmarks/results/http3-categories-2026-10-02.json)
- [WebSockets, 36 rows](../benchmarks/results/websocket-categories-2026-10-02.json)
- [Lifespan and shutdown, 20 rows](../benchmarks/results/lifecycle-categories-2026-10-02.json)

The support-matrix probe scripts also passed for HTTP/1.1, HTTP/2, HTTP/3, streaming, WebSockets, cancellation/disconnect, lifespan, and the separately installed `starlette-rs` route. These are focused black-box cases, not a complete ASGI conformance suite.

## HTTP/1.1 categories

Each cell reports median requests/s; p50/p95/p99 milliseconds; server CPU; sampled peak server RSS. This table compares the candidate's uvloop mode with Uvicorn's fastest measured HTTP/1.1 configuration. The JSON report includes both asyncio configurations as well.

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

## Why SIMD is not the current explanation

The fixed response is only 12 bytes. Its hot path consists mainly of HTTP state, task scheduling, Python object and scope construction, synchronization, channel operations, and loopback socket I/O. There is no large byte-processing loop for SIMD to accelerate. The optimized H1 receive fast path helps by returning an already-available terminal request event directly instead of constructing an asynchronous Rust-to-Python bridge future, but each application still runs on its Python event loop under the GIL.

The multi-chunk case sends 256 ASGI body events per response. Moving this work into a SIMD parser would not remove those app-visible event boundaries or their sends, wakeups, and backpressure. A useful next diagnosis is a CPU/allocation profile of the H1 response writer and bridge around `send()` plus the 1 MiB response path. The RSS results show a memory issue to explain; they do not identify its cause. SIMD should be considered only if such a profile finds a dominant byte-scanning or copying loop.

Rust owns the listener, protocol parsing, connection state, flow control, and network writes. Python still owns the ASGI callable, event-loop execution, task/context propagation, and exception behavior. Each request crosses that boundary; streamed request events and response body sends cross it repeatedly. Rust removes some protocol and runtime overhead, but it does not make Python ASGI work parallel or erase the bridge cost. `uvloop` improves some candidate cases, but Uvicorn also uses uvloop and adds the C `httptools` parser in the fastest H1 configuration.

The prior fixed-response investigation found that bypassing one unnecessary receive bridge await raised the candidate's throughput and lowered latency. The synchronized receive optimization remains useful, but the category results show that it does not solve per-chunk response overhead or establish a broad performance lead. For CPU, latency, and memory attribution beyond these end-to-end observations, profiling is still required.

## Scope and conformance status

The complete ASGI conformance suite has not been run. The live probes cover callable behavior, caller context, exception-to-500, HTTP version/scope, streaming, disconnect, send-after-disconnect, WebSocket behavior, lifespan state, cancellation, and `starlette-rs` independence. ASGI defines these behaviors across the base, HTTP/WebSocket, and lifespan specifications; this project's probes remain selected cases, not exhaustive coverage ([ASGI specification index](https://asgi.readthedocs.io/en/latest/specs/index.html), [HTTP and WebSocket spec](https://asgi.readthedocs.io/en/latest/specs/www.html), [lifespan spec](https://asgi.readthedocs.io/en/latest/specs/lifespan.html)).

Uvicorn documents HTTP/1.1 and WebSockets, not H2/H3, so Hypercorn is used only for same-protocol comparisons on those transports ([Uvicorn settings](https://www.uvicorn.org/settings/)). H3 upload, broader interoperability, packaging across operating systems, and a complete ASGI conformance run remain open. The [support matrix](support-matrix.md) lists current guarantees and limits. The project name remains provisional in [ADR 0001](adr/0001-runtime-and-asyncio-bridge.md).

Reproduce the completed HTTP/1.1 matrix with:

```sh
uv sync --python 3.12 --group benchmark --reinstall-package uvicorn-rs
uv run python scripts/run_http_category_bench.py \
  --workloads fixed large-response many-response-chunks small-response-chunks \
    request-upload request-upload-small-chunks slow-reader-backpressure \
    scope-32-headers contextvars sync-callable-awaitable exception-to-500 starlette-rs-route \
  --duration 2 --warmup 0.25 --concurrency 64 --repetitions 3 --seed 20261002 \
  --output benchmarks/results/http-categories-2026-10-02.json
```

H2, H3, WebSocket, and lifecycle commands are in their runner scripts; rebuild the merged H2 and category summary with `uv run python scripts/assemble_category_results.py`.
