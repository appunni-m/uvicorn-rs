# ADR 0001: Rust network runtime and Python asyncio bridge

- **Status:** Accepted for the protocol prototype. The synchronized receive fast path has correctness-gated evidence of a baseline improvement. The latest full matrix passed its represented correctness cases but ran under severe host contention; prior and current measurements still show H1 losses against Uvicorn's fastest configuration. This is not approved as a general performance replacement or production server.
- **Date:** 2026-10-02
- **Project name:** `uvicorn-rs`, taken from the GitHub repository URL supplied by the owner. The CLI name is `uvicorn-rs` and the Python import name is `uvicorn_rs`. This project is independent and is not affiliated with Uvicorn.

## Context

The project should host ordinary ASGI 3 applications, including applications built with `starlette-rs`, while keeping `starlette-rs` independent of this server. Keep Python as a thin integration boundary: it resolves `module:app`, owns the app event loop and task creation, and preserves callable, context, and exception behavior at the ASGI boundary. Rust owns the listener, socket handling, protocol implementation, connection and stream state, flow control, and shutdown. The requested HTTP target now includes HTTP/1.1, HTTP/2, and HTTP/3. ASGI requires each HTTP/2 and HTTP/3 request to receive its own scope and its response to stay on the corresponding multiplexed stream; the ASGI `http_version` values are `"1.1"`, `"2"`, and `"3"` respectively ([ASGI HTTP spec](https://asgi.readthedocs.io/en/latest/specs/www.html)). The performance target remains an evidenced improvement over Uvicorn where protocol baselines are comparable, not a claim based on language choice.

ASGI lifespan requires startup and request handling to use the same Python event loop. HTTP and WebSocket bodies are message streams, and server `send()` calls must apply backpressure by flushing data into the transport's send buffer before returning. Disconnects must be visible to the app; sends on closed connections should raise an `OSError` subclass. The lifespan protocol also defines shallow-copied per-request state.

Uvicorn already offers both asyncio and uvloop loop choices, plus multiple HTTP implementations. `uvloop` is an asyncio-compatible event loop built on libuv. In this design, Rust owns network I/O, so uvloop would only accelerate Python-side scheduling and any I/O performed by the app itself. Its value must be measured with this boundary in place.

## Decisions

### 1. Rust owns the network data plane

Use a two-worker Tokio multi-thread runtime for accepting sockets and running the Rust protocol data plane. Hyper's auto server connection handles HTTP/1.1 and HTTP/2 parsing, keep-alive, framing, and stream multiplexing. Cleartext HTTP/2 prior knowledge is accepted; TLS TCP advertises `h2` and `http/1.1` via ALPN. HTTPS and QUIC share the configured address, with Quinn and `h3` handling HTTP/3 over TLS 1.3 and ALPN `h3`. The Rust `h3` crate is experimental, so HTTP/3 stays a preview feature until broader interoperability and stress coverage exist. Request streams map to separate ASGI invocations. Hyper and `h3` own protocol flow control, with bounded Rust-to-Python channels preventing whole-body accumulation. WebSockets use Hyper's HTTP/1.1 Upgrade and `tokio-tungstenite`; WebSocket over HTTP/2 or HTTP/3 is unsupported.

Rust owns connection state, framing, socket reads and writes, bounded buffers, shutdown deadlines, and protocol errors. It does not execute ASGI app code on Tokio worker threads.

### 2. Python owns ASGI execution

The Python-facing CLI is intentionally a thin loader and loop adapter: it imports `module:app`, selects the Python loop, and starts the Rust server from that live loop. Python does not implement socket, HTTP, WebSocket, streaming, or connection-management logic. The default loop is standard asyncio. An opt-in uvloop mode is supported only when uvloop is installed; it is a benchmark candidate, not an assumed default.

Each ASGI invocation runs inside an asyncio `Task` on the loop captured by `Server.serve()`. The Rust bridge uses `call_soon_threadsafe` with the captured event loop and `contextvars.Context`, then calls `asyncio.ensure_future` on that loop. Dropping an in-flight Rust task schedules `Task.cancel()` back onto the same loop; the completion callback returns the original Python exception for traceback reporting. Tokio does not run Python application code on its workers, and no replacement Python loop is created.

The bridge must preserve the original Python exception object and traceback when reporting app failures. When a request is cancelled or its connection is lost, the corresponding Python task must receive cancellation and be joined or otherwise observed; a dropped Rust future alone is not accepted as proof of cancellation. These behaviors are prototype gates before protocol expansion.

### 3. Backpressure and streaming are end-to-end

Request bodies are exposed as incremental `http.request` events, not accumulated before the app starts. The HTTP request channel holds at most one pending body item and the HTTP response channel holds at most four; WebSocket channels hold at most eight messages. Awaiting ASGI `send()` waits for capacity in that bounded writer path. A slow peer therefore applies backpressure to the Python producer instead of growing an unbounded queue. The response capacity was increased from one to four after diagnostics showed frequent per-chunk bridge waits; this reduced those waits, but did not establish a performance win over Uvicorn.

HTTP response framing, content length, chunked transfer encoding, and connection reuse belong to the Rust HTTP implementation. The server ignores an app-provided `Transfer-Encoding` header and chooses valid framing itself. It preserves duplicate header fields and their order.

### 4. Lifespan and shutdown stay on the app loop

Run lifespan startup on the Python app loop before accepting requests. In automatic mode, an app that raises or returns before `lifespan.startup.complete` is logged and treated as not supporting lifespan; an explicit `lifespan.startup.failed` is an error. Reuse that loop for HTTP and WebSocket tasks. On shutdown, stop accepting, start a configured grace deadline, drain active work, cancel remaining Python tasks at expiry, and then deliver lifespan shutdown. Copy the lifespan state dictionary shallowly into each HTTP/WebSocket scope.

### 5. Independent packaging and scope

Build a Rust extension/library with a thin Python CLI and loader. The server may test against `starlette-rs`, but neither its runtime nor its package metadata may depend on, import, or bundle `starlette-rs`. No package is published as part of this work.

The requested contract is ASGI 3, HTTP/WebSocket 2.5 and lifespan 2.0, over HTTP/1.1, HTTP/2, and experimental HTTP/3. The support matrix separates implemented behavior from live evidence. This does not imply Uvicorn CLI, worker, reload, or deployment-option parity. Uvicorn's documented HTTP choices are `h11` and `httptools`, so HTTP/2 and HTTP/3 cannot be compared directly against Uvicorn; those protocols need a separately named server that supports the same protocol ([Uvicorn settings](https://www.uvicorn.org/settings/)).

### 6. Retain immutable Python output buffers with PyO3 `Bytes`

For HTTP response bodies, WebSocket binary payloads, and header byte pairs,
extract PyO3's `bytes::Bytes` directly instead of first allocating Rust
`Vec<u8>` values. With PyO3's `bytes` feature, immutable Python `bytes` can be
retained through an owner-backed `Bytes`, so Rust can write the original payload
without copying it at extraction. Mutable `bytearray` input still has to be
snapshotted to keep the buffer stable for asynchronous transport writes.

Do not use unsafe allocator/layout tricks to transfer a Rust allocation into
Python `bytes`. The Rust-to-Python request/event path currently constructs
Python `bytes` objects and copies payloads. This design keeps
`unsafe_code = "forbid"` and does not claim end-to-end zero-copy I/O. A 1 KiB
copy threshold was rejected after its fixed and chunked H1 cases regressed in
the recorded focused run; the selected path always uses direct extraction for
immutable `bytes`. See the [buffer ownership ledger](../architecture.md#buffer-ownership-and-copies)
and [optimization results](../feasibility.md#pyo3-buffer-ownership-optimization).

For event dispatch, exact built-in Python `str` values are compared with
cached interned ASGI event names, avoiding a temporary Rust `String` for common
HTTP, WebSocket, and lifespan events. Unknown names and `str` subclasses use a
Rust-owned fallback; known standard event names on subclasses are still mapped
to the normal Rust event. The live HTTP probe checks that subclass `__eq__`
overrides are not invoked and dispatch still succeeds. This only avoids a
small event-name allocation: it does not remove ASGI message construction,
Python calls, GIL access, or scheduler handoffs. The event-name optimization
was not isolated in a clean performance run, so no speed gain is claimed.

## Alternatives considered

### Use Python asyncio or uvloop for the sockets

This preserves a single event-loop runtime but leaves socket readiness, HTTP parsing, and protocol handling in Python or C extensions. It does not answer whether moving the network data plane to Rust helps. Retained as the baseline and as the loop that executes the ASGI app.

### Run Python app coroutines on Tokio worker threads

Rejected. Python awaitables are tied to an asyncio event loop, and many apps retain loop-bound resources across lifespan and requests. Acquiring the GIL does not make a thread the owner of the app's event loop.

### Use uvloop as the Rust networking runtime

Not applicable: uvloop implements Python's asyncio loop and cannot replace Tokio's Rust runtime. It remains an optional Python app loop so deployments can benefit when app-side asyncio I/O is significant.

### Write a custom HTTP/1.1 parser and state machine immediately

Rejected for the MVP. A mature HTTP implementation reduces protocol and request-smuggling risk while keeping Rust in charge of network I/O. A custom parser would need separate interoperability and security evidence before it could replace Hyper.

## Consequences and open gates

- Every request crosses a Rust/Python boundary and runs Python app code under the interpreter's scheduling and GIL constraints. Rust can reduce network overhead, but cannot make arbitrary Python application logic execute in parallel in a conventional GIL-enabled CPython build.
- Tokio and Python asyncio are separate schedulers. The bridge adds wakeups and conversions; benchmark measurements must include their cost.
- Owner-backed extraction removes a Python-to-Rust payload copy for immutable outgoing `bytes`, but it does not remove ASGI event construction, Python-to-Rust calls, or Rust-to-Python copies. The focused benchmark showed lower large-response sampled RSS but did not improve every H1 workload.
- Hyper, Tokio, PyO3, and the async bridge versions must be pinned in the lockfile and checked against the supported Python versions before packaging.
- The benchmark currently covers one CPython 3.12 environment; it does not establish a supported Python version range.
- Representative cancellation, exception, lifecycle, streaming, WebSocket, and HTTP protocol probes now pass. These targeted cases do not replace a full ASGI conformance suite.
- If correctness-gated repeated benchmarks do not show a meaningful gain on representative workloads, do not claim this server is a performance replacement; revise the scope using the measured result.

### Feasibility outcome

The latest full matrix contains 144 H1, 84 H2, 66 H3, 36 WebSocket, and 20 lifecycle rows with all represented correctness checks passing. Its saved process snapshot shows an unrelated test process using 687.4% CPU plus concurrent Rust build/doc jobs; treat its performance values as diagnostic. Uvicorn does not provide H2/H3 baselines, so those protocols compare only to Hypercorn. H3's represented Hypercorn cases now pass; its upload cases remain excluded after prior correctness failures. The correct scope is therefore a protocol/interoperability prototype; further performance work should be driven by clean profiles and correctness-preserving hypotheses. See [the full category report](../feasibility.md) and the [latest raw run](../../benchmarks/results/full-event-type-fastpath-2026-10-02T142406Z/). Historical category data and earlier single-workload measurements remain linked in the feasibility report.

## References

- [ASGI HTTP and WebSocket specification source (asgiref)](https://github.com/django/asgiref/blob/main/specs/www.rst)
- [ASGI lifespan specification](https://asgi.readthedocs.io/en/latest/specs/lifespan.html)
- [Python asyncio event-loop documentation](https://docs.python.org/3/library/asyncio-eventloop.html)
- [Uvicorn implementation settings](https://www.uvicorn.org/settings/)
- [uvloop documentation](https://uvloop.readthedocs.io/)
- [PyO3 async-runtime guide](https://github.com/PyO3/pyo3-async-runtimes)
- [PyO3 async bridge and task-local API](https://docs.rs/pyo3-async-runtimes/latest/pyo3_async_runtimes/)
- [Hyper HTTP/2 server connection API](https://docs.rs/hyper/latest/hyper/server/conn/http2/index.html)
- [Rust `h3` server API](https://docs.rs/h3/latest/h3/server/index.html)
