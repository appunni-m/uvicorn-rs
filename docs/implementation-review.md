# Implementation review: known gaps

This page separates measured failures from risks that still need targeted
evidence. The latest full benchmark passed the H1, H2, WebSocket, lifespan,
and Rust-only H3 correctness gates; its Hypercorn H3 comparison failed, and
unrelated CPU-heavy jobs contaminated performance samples. It is not a
security audit or evidence that the server is ready for public deployment.

## Measured performance gaps

| Finding | Evidence | Current action |
|---|---|---|
| H1 remains slower than Uvicorn's fastest measured configuration. | Latest provisional medians were 31,028 vs 56,694 requests/s fixed and 892 vs 1,824 on 256 × 4 KiB chunks. Fixed p50 was 1.954 vs 0.845 ms; chunked p50 was 74.187 vs 33.417 ms. Rust server CPU was 124.4% vs 90.4% fixed and 208.3% vs 98.3% chunked. H1 started with two unrelated Rust compiler jobs and a Python workload each using about 70% CPU. | Keep performance claims provisional. Rerun after host contention ends and move large-transfer clients to a separate host when measuring server efficiency. |
| Per-message bridge/backpressure work is a measured chunk-heavy cost. | The diagnostic queue-one run showed about 224 full sends and 206 ms accumulated full-send wait per 256-chunk response; queue-four reduced this to about 61 waits and 68.8 ms. The timer includes bridge scheduling, not only queue residence. | Preserve app-loop ownership and backpressure while profiling the writer/bridge path; avoid batching across observable ASGI send boundaries. |
| Large-response memory remains above the Uvicorn baseline after owner-backed extraction. | The latest provisional 1 MiB H1 response row measured 148.1 MiB Rust peak RSS vs 33.0 MiB Uvicorn. The loopback client used 588.8% and 502.2% CPU respectively. | Keep owner-backed extraction. Collect allocation/lifetime profiles on an idle host and move the load client off-host; RSS and client-contended throughput cannot identify retained allocations. |
| Rust server CPU is high in several benchmark cases. | In the latest provisional H1 run, median server CPU was 124.4% vs 90.4% fixed and 208.3% vs 98.3% for 256 chunks (Rust vs Uvicorn). Rust also measured 247.0% vs 94.6% on WebSocket text echo. | Profiles show bridge, channel, runtime, and transport frames but do not attribute their total CPU share. No evidence points to missing SIMD as the cause. |
| H3 candidate RSS is unexpectedly high. | The latest Rust-only H3 fixed-response rows peaked between about 177 and 202 MiB at concurrency 4. The comparison failed its Hypercorn correctness gate, and the retry overlapped a Rust compiler. | Re-run H3 under an idle host and profile connection/stream lifetimes before treating this as a leak or a stable memory requirement. |

The newest run, its environment/process snapshots, raw rows, and the rejected
1 KiB copy threshold experiment are in [the feasibility
report](feasibility.md). A recorded before/after difference is evidence for an
optimization candidate, not a statistical proof that a single change caused
that difference.

## Correctness and protocol coverage

- Focused black-box probes cover HTTP, streaming, HTTP/2, HTTP/3, WebSockets,
  lifespan, cancellation, disconnect, and one optional `starlette-rs` route.
  The complete ASGI 3 / HTTP-WebSocket 2.5 / lifespan 2.0 conformance corpus has
  not been run.
- HTTP/1.0, malformed framing, request-smuggling cases, exhaustive duplicate
  header and raw-target cases, HTTP/2 extended CONNECT, WebSocket fragmentation
  and extensions, and broad HTTP/3 loss/recovery interop remain unverified or
  unsupported. See the [support matrix](support-matrix.md) for per-feature
  status.
- The HTTP/3 implementation depends on experimental `h3` APIs. An earlier
  correctness-gated run has a 66-row Hypercorn comparison for its represented
  workload set. The latest comparison aborted on four Hypercorn asyncio
  timeouts; the separate 36-row Rust-only matrix passed. Broader
  interoperability remains unverified.

## Code and operations

- The Rust data plane is concentrated in a 2,300-line `src/lib.rs`. Keeping one
  module has not yet been shown to cost runtime performance, but it makes
  protocol review and change isolation harder. A module split should preserve
  behavior and be measured independently.
- The Rust/Python boundary necessarily creates Python scope and ASGI message
  objects. Incoming body data and scope bytes currently copy into Python
  `bytes`; immutable outgoing Python `bytes` remain owner-backed in Rust.
  Exact built-in ASGI event names compare against interned Python strings and
  avoid a Rust `String` allocation; unknown names and string subclasses retain
  the owned-string fallback.
  See the [copy ledger](architecture.md#buffer-ownership-and-copies).
- HTTP body queues are bounded by item count, not by bytes per item, and there
  is no configurable body-size limit. Deployments must account for application
  behavior and transport defaults until resource limits are designed and
  verified.
- Error reporting uses `eprintln!` in some Rust paths; structured logging and
  configurable access logs are not implemented.
- The manifest declares Python `>=3.9`, but live validation currently covers
  only CPython 3.12.13 on macOS ARM64. Linux, Windows, alternate Python
  interpreters, and free-threaded CPython have not been validated.
- No package has been published. The repository license is not selected yet;
  no license grant should be inferred until a license is added.

## Next performance work

1. Repeat the full correctness-gated matrix on an otherwise idle host; the
   latest snapshots showed two unrelated Rust compilers and a Python workload
   at H1 start, a Rust compiler at H3 candidate-only start, and a resident
   Android emulator.
2. Use the opt-in bridge counters to profile fixed and chunk-heavy H1 behavior;
   the four-item queue reduces full-channel waits, but fixed sends do not block
   and still lose to Uvicorn. Add allocation/lifetime profiling for the 1 MiB
   response; RSS samples cannot explain retained memory.
3. Attribute the remaining fixed-response cost and change one
   behavior-preserving mechanism at a time, retaining the black-box
   correctness gates, and repeat interleaved A/B samples against Uvicorn's
   `uvloop + httptools` configuration with both server and client CPU recorded.

The next benchmark must include the existing category workload names and use
the same app, client, runtime, concurrency, duration, and machine for both
servers. SIMD is a candidate only if profiles show a dominant vectorizable
byte-processing loop; it cannot remove Python-visible ASGI events.
