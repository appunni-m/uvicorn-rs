# ADR 0001: Rust network runtime and Python asyncio bridge

- **Status:** Accepted for the protocol prototype. The synchronized receive fast path is correctness-gated and materially improves the Rust baseline, but the server remains slower than Uvicorn's fastest measured HTTP/1.1 configuration and is not approved as a general performance replacement or production server.
- **Date:** 2026-10-02
- **Working project name:** `uvicorn-rs` (provisional, taken from the workspace directory; owner confirmation is still open). The CLI name is `uvicorn-rs` and the Python import name is `uvicorn_rs`. This project is independent and is not the Uvicorn project.

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

Request bodies are exposed as incremental `http.request` events, not accumulated before the app starts. HTTP request and response channels hold at most one pending body item; WebSocket channels hold at most eight messages. Awaiting ASGI `send()` waits for capacity in that bounded writer path. A slow peer therefore applies backpressure to the Python producer instead of growing an unbounded queue.

HTTP response framing, content length, chunked transfer encoding, and connection reuse belong to the Rust HTTP implementation. The server ignores an app-provided `Transfer-Encoding` header and chooses valid framing itself. It preserves duplicate header fields and their order.

### 4. Lifespan and shutdown stay on the app loop

Run lifespan startup on the Python app loop before accepting requests. In automatic mode, an app that raises or returns before `lifespan.startup.complete` is logged and treated as not supporting lifespan; an explicit `lifespan.startup.failed` is an error. Reuse that loop for HTTP and WebSocket tasks. On shutdown, stop accepting, start a configured grace deadline, drain active work, cancel remaining Python tasks at expiry, and then deliver lifespan shutdown. Copy the lifespan state dictionary shallowly into each HTTP/WebSocket scope.

### 5. Independent packaging and scope

Build a Rust extension/library with a thin Python CLI and loader. The server may test against `starlette-rs`, but neither its runtime nor its package metadata may depend on, import, or bundle `starlette-rs`. No package is published as part of this work.

The requested contract is ASGI 3, HTTP/WebSocket 2.5 and lifespan 2.0, over HTTP/1.1, HTTP/2, and experimental HTTP/3. The support matrix separates implemented behavior from live evidence. This does not imply Uvicorn CLI, worker, reload, or deployment-option parity. Uvicorn's documented HTTP choices are `h11` and `httptools`, so HTTP/2 and HTTP/3 cannot be compared directly against Uvicorn; those protocols need a separately named server that supports the same protocol ([Uvicorn settings](https://www.uvicorn.org/settings/)).

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
- Hyper, Tokio, PyO3, and the async bridge versions must be pinned in the lockfile and checked against the supported Python versions before packaging.
- The benchmark currently covers one CPython 3.12 environment; it does not establish a supported Python version range.
- Representative cancellation, exception, lifecycle, streaming, WebSocket, and HTTP protocol probes now pass. These targeted cases do not replace a full ASGI conformance suite.
- If correctness-gated repeated benchmarks do not show a meaningful gain on representative workloads, do not claim this server is a performance replacement; revise the scope using the measured result.

### Feasibility outcome

The synchronized receive fast path remains in the prototype. The full 12-workload H1 matrix confirms that uvicorn-rs/uvloop beats Uvicorn `asyncio + h11` on the fixed response (45,482 versus 22,016 requests/s) but loses to Uvicorn `uvloop + httptools` (45,482 versus 75,641 requests/s), at higher server CPU. Large and chunked H1 responses also show significant throughput, latency, or memory regressions. Some individual workloads favor Rust, but they do not establish a general Uvicorn performance replacement.

The H2/H3 matrices show faster throughput than Hypercorn on several same-protocol cases, with higher CPU on many of those runs. Uvicorn does not provide H2/H3 baselines, Hypercorn failed the H3 16-worker comparison gate, and the H3 upload baseline failed its correctness gate. The Rust server passed a candidate-only H3 fixed-response multiplexing gate at 16 workers. WebSocket measurements are mixed. The correct scope is therefore a protocol/interoperability prototype; stop performance-server expansion until profiling identifies a specific, correctness-preserving opportunity. See [the full category report](../feasibility.md), the [machine-readable medians](../../benchmarks/results/category-summary-2026-10-02.json), and the raw [H1](../../benchmarks/results/http-categories-2026-10-02.json), [H2](../../benchmarks/results/http2-categories-2026-10-02.json), [H3](../../benchmarks/results/http3-categories-2026-10-02.json), [WebSocket](../../benchmarks/results/websocket-categories-2026-10-02.json), and [lifecycle](../../benchmarks/results/lifecycle-categories-2026-10-02.json) results. The earlier single-workload measurements remain as optimization history in the feasibility report.

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
