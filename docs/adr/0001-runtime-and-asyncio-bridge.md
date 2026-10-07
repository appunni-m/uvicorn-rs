# ADR 0001: Rust network runtime and Python asyncio bridge

- **Status:** Accepted for the protocol prototype. Historical receive-fast-path measurements remain scoped to their recorded builds. The October 4 matrix was contended, and the October 5 optimization comparison has no accepted general speedup. Current 490-case correctness evidence and 238/238 normal-build parity are recorded in the [coverage report](../coverage.md#current-full-verification-490-cases). The source remains experimental and is not approved as a general performance replacement or production server.
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

Request bodies are exposed as incremental `http.request` events, not accumulated before the app starts. The HTTP request channel holds at most one pending body item and the current HTTP response channel holds at most sixteen; WebSocket channels hold at most eight messages. Awaiting ASGI `send()` waits for capacity in that bounded writer path. A slow peer therefore applies backpressure to the Python producer instead of growing an unbounded queue. Diagnostics first motivated increasing the response capacity from one to four, and it has since been raised to sixteen. The latest instrumented run still recorded about 14.9 full sends per 256-chunk response; this measurement includes bridge scheduling and does not establish a performance win over Uvicorn.

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

The canonical source does not cache fixed ASGI scope/message keys, Python
method lookups or common HTTP methods. Key/value and one-Tokio-worker builds
were tested, but every optimization timing was rejected by the host guard;
common-method caching was drafted only. These experiments remain unaccepted.
HTTP path decoding retains its borrowed
`Cow<str>` for the common already-decoded case instead of first allocating an
owned Rust `String`. HTTP methods retain the existing uppercasing path;
percent-encoded paths retain the existing decoding semantics. Event-name
interning and path borrowing do not establish a speedup independently.

### 7. Preserve transport capabilities and typed H3 close handling

The October 5 source forwards `is_write_vectored` and
`poll_write_vectored` through `ConnectionIo`. Hyper can then retain queued
body/header slices on supporting transports instead of flattening them. A
private borrowed scalar/vectored buffer enum uses one fallible write handler;
it preserves original errors and disconnect signaling without payload copies,
allocation, dynamic dispatch or unsafe Rust. TLS retains its encryption and
buffering work. The earlier plaintext H1 profile observed the flattening copy
disappear; wall-stack observations are not speed or CPU-percentage evidence.

The H3 accept loop treats typed `H3_NO_ERROR` (`0x100`) and unknown remote
HTTP/3 application close codes as clean peer closure, as required by
[RFC 9114 section 8](https://www.rfc-editor.org/rfc/rfc9114.html#section-8).
Cases cover unknown code zero, reserved GREASE `0x21`, unknown
`0x111`, and maximum u62. Registered HTTP/3-family application codes `0x33`,
`0x101`, and `0x200` retain the error path. The public wire-input cases check
the response, a fresh connection, scoped diagnostics and graceful exit against
Hypercorn. QUIC transport `CONNECTION_CLOSE` behavior is unverified.

The task-reaping source joins completed H3 request tasks during acceptance and
retains final draining of owned tasks after an acceptance error. The current
matrix declares 490 cases across 70 input files and 71 operations: 238 public
comparisons and 252 target-only contracts. Its held-response accept-error
workflow uses the existing point to require remote `0x102`, actual incomplete
body/stream failure, cancellation diagnostics before the original error,
Python cleanup and a healthy fresh request. A selected instrumented public
pair passed the 128-response sequence with GREASE disabled and the clean-close
case (2/2). The held-response accept-error contract passed its selected
instrumented case (1/1), then the current 490-case attribution run and three
complete repeats passed with zero failures, infrastructure errors, retries or
cases not run. The instrumented build measures 5,108/5,108 regions and
3,608/3,608 lines with zero unfiltered source-matched MCP gaps and tests passed.
Both formerly
missing final-drain spans are covered solely by the held-response case. Its
remote `ApplicationClosed(0x102)`, body-stream error, connection closure and
cleanup establish connection-error termination/cancellation; `stream_reset`
alone follows a client error convention and does not identify a QUIC
`RESET_STREAM` frame. The current normal non-instrumented local build passes
238/238 public comparisons. The installed-wheel result and 16-check exclusion
audit belong to the preceding source snapshot and have not been repeated for
this source. See [current evidence](../coverage.md#current-full-verification-490-cases).

The request-body-pump work closes the detached-task ownership gap separately
from H3 request-task reaping. `ServerContext` owns body pumps in a `JoinSet`;
each pump observes server, connection and request cancellation. H1 drains after
the receiver closes to preserve request framing and keep-alive reuse; H2 stream
cancellation is bridged to `http.disconnect`; H3 body errors and closed
receivers terminate their request pumps. Shutdown joins all registered pumps
within the remaining transport grace period, then aborts and drains them if the
deadline expires. Public and target-only cases exercise partial uploads, early
responses, disconnects, malformed H1 final chunks, sibling/follow-up health,
reaping and both graceful and forced shutdown. The complete evidence archive
binds these cases to the same source/build and normal wheel.

The historical shared-write normal build passes 213 public cases; 448 instrumented cases and
three full repeats pass with 4,763/4,763 regions, 3,360/3,360 lines and zero
source-matched unfiltered MCP gaps. The separate normal exclusion audit passes.
These are historical source-bound local macOS ARM64 native results; they do
not attest the changed checkout. The earlier generic helper
had aggregate 100% coverage but seven MCP function observations; its receipt
is retained without exclusions or profile merging. See
[coverage evidence](../coverage.md#current-full-verification-448-cases) and
[the performance investigation](../performance-investigation-2026-10-05.md).

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

The historical October 4 full matrix contains 132 H1, 84 H2, 66 H3, 36 WebSocket, and 20 lifecycle rows with all represented correctness checks passing; the optional `starlette-rs` H1 route was omitted. Its saved process snapshots show unrelated parity, Python, and Rust build work, including a compiler at about 787% CPU; treat performance values as diagnostic. Uvicorn does not provide H2/H3 baselines, so those protocols compare only to Hypercorn. H3's represented Hypercorn cases passed; its upload cases remain excluded after prior correctness failures. The scope remains a protocol/interoperability prototype; further performance work requires valid paired measurements. See [the historical category report](../feasibility.md), [October 4 raw run](../../benchmarks/results/full-2026-10-04T113122Z/), and [October 5 investigation](../performance-investigation-2026-10-05.md). Earlier measurements retain their own source/build scope.

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
