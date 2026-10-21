# ADR 0004: Rust-native WebSocket and application lifecycle contract

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

- **Status:** Partially implemented; native HTTP/1.1 WebSocket transport is provisional, while the shared framework contract and lifecycle integration remain proposed
- **Date:** 2026-10-12
- **Related work:** Kata `wb4y`, `sw8s`, Starlette-RS `wkz8`, FastAPI-RS `s08y`

## Context

The HTTP-native path uses `http::Request`, `http::Response`, streaming
`http_body::Body` values, and Tower `Service`. That contract carries
request/response streams, but it does not define a bidirectional WebSocket
session or application startup and shutdown.

The current `uvicorn-rs` crate serves HTTP/1.1, HTTP/2, and HTTP/3 Tower
services and provides a provisional HTTP/1.1 WebSocket handshake/session API.
The selected WebSocket report below predates the current 214-case native
manifest: it selected 13 focused cleartext HTTP/1.1 WebSocket cases from the
then 101-case manifest. All 13 selected cases passed with complete per-case
attribution and zero case failures, infrastructure failures, transient
infrastructure failures, or retries.
The selected report,
`target/asgi-coverage/2026-10-13-native-websocket-rfc-contract-final/coverage-report.json`,
records 868/7,384 regions and 699/5,420 lines across its executable source set.
Those selected-scope totals are not aggregate coverage or an RFC 6455
conformance result. Coverage-MCP follow-up matched the source receipt and
reported `tests: passed`, with 32 missing region groups and 17 missing line
groups in `crates/uvicorn-rs/src/websocket.rs`. This selected report does not
establish the current full-matrix coverage gate; see the
[unified coverage status](../coverage.md#current-unified-coverage-status-2026-10-17)
for the latest source-bound evidence. The cases exercise text/binary echo,
Ping/Pong, close exchange,
shutdown close, selected handshake rejection, and subprotocol/header rules.
They do not complete the full handshake inventory. TLS, HTTP/2, and HTTP/3
WebSockets, ASGI mapping, and framework-native integration remain open. The API depends on the server's
HTTP/1.1 upgrade capability and is not a framework-neutral shared contract. A new
`native-app-contract` crate prototypes runtime-neutral application
startup/shutdown hooks, consumed optionally by the core's TCP/TLS and HTTP/3
entry points.
Starlette-RS has WebSocket and lifespan state machines for its Python ASGI
implementation, while its current `NativeApplication` is HTTP-only. An archived
receipt records HTTP composition through Starlette-RS and the Uvicorn core on a
prior dirty sibling snapshot. The current FastAPI-native example references a
missing sibling crate and is not presently reproducible; in any case, that
receipt does not establish native WebSocket or lifecycle support. These are
separate gaps from the existing Python ASGI path.

ADR 0003 selects the package direction: native transport and framework contracts
belong to `uvicorn-rs`, Starlette-RS, and FastAPI-RS. The optional
`uvicorn-rs-py`, `starlette-rs-py`, and `fastapi-rs-py` clients own Python
object conversion and upstream Python-package compatibility. The intended
Python mode will map the native transport/session contract to ASGI WebSocket
and lifespan events on the application's Python event loop. `uvicorn-rs-py`
now delegates HTTP protocol handling to the native Rust transport, while Python
still builds ASGI scopes and events and invokes the application. The generic
native `ConnectionUpgrade` lifecycle has not been mapped to ASGI WebSocket
events. Those Python calls remain a language boundary; they are not present in
the native Rust path.

WebSocket transport depends on the HTTP version. HTTP/1.1 uses the RFC 6455
Upgrade handshake. HTTP/2 uses Extended CONNECT under RFC 8441; HTTP/3 uses
the corresponding mechanism in RFC 9220. HTTP/2 and HTTP/3 do not use the
HTTP/1.1 `101 Switching Protocols` handshake. The transport adapter must own
those differences.

## Decision proposal

### Keep ordinary HTTP on Tower

Keep the HTTP-only service contract in ADR 0003. Do not replace streaming
`http::Request` / `http::Response` with ASGI message dictionaries or expose
Hyper, Quinn, or protocol-specific stream types in Starlette-RS or
FastAPI-RS.

### Add only the missing shared contract

Keep the server-neutral contract crate small. Its current prototype contains
only lifecycle hooks and has no dependencies. The crate must not depend on
Tokio, Hyper, Quinn, Uvicorn-RS, Starlette-RS, FastAPI-RS, PyO3, or a Python
runtime. Add a WebSocket contract only after its API has been reviewed. The
crate name and current lifecycle method signatures remain provisional until
the same contract compiles in all three repositories.

The framework-facing shape should provide:

- A typed WebSocket upgrade capability for a matched native route.
- An accept result containing the selected subprotocol and permitted
  handshake headers, or an HTTP denial response before the handshake is
  committed.
- A protocol-neutral session with text, binary, and close messages. The
  transport owns framing, masking, Ping/Pong handling, and HTTP-version
  handshake translation. A session send waits for downstream capacity;
  implementations must not require an unbounded message queue.
- A receive result that distinguishes a peer close from a transport failure,
  and a close value that preserves the code and reason where the peer sent
  them.
- Cancellation by dropping the session future or by an explicit cancellation
  value supplied by the server. A reset or disconnect cancels only the
  affected stream/session; it must not cancel sibling HTTP/2 or HTTP/3
  streams.

The contract must coexist with the HTTP request/response service contract. It must not
encode a WebSocket session as an `http_body::Body` or require a framework to
depend on a server-owned upgrade type. The implementation spike must prove a
route can choose between an ordinary HTTP response, an HTTP denial, and an
accepted session without the application constructing a protocol-specific
status line.

### Make lifecycle ownership explicit

The server invokes the application startup hook before it accepts requests.
A startup error prevents the listener from entering the serving state and is
returned through a typed error path. Application state remains owned by the
framework application; the server does not store Python-like untyped values.

On shutdown, the server stops accepting first, gives active HTTP requests and
WebSocket sessions the configured drain interval, then cancels and joins work
that remains at the deadline. The application shutdown hook runs after
request/session work has drained or been cancelled. The current server
prototype gives the hook its own timeout after the server's drain interval;
those are separate limits, so total shutdown time can include both. Hook
failure is returned as a typed `ServeError` with its original source, without
changing an HTTP response whose body was already committed. A timed-out hook
future is dropped. The runtime contract must not own a Tokio runtime or choose
a framework's state representation.

The current lifecycle spike is `native_app_contract::ApplicationLifecycle`,
re-exported by `uvicorn_rs` and optionally configured in `ServerConfig`.
It is not the ASGI lifespan event protocol. Seven target-only live inputs now
exercise startup state before request dispatch, H1/H2/H3 drain order, startup
failure and timeout, shutdown failure and timeout, timeout cancellation, and
typed source preservation. A historical 36-input manifest snapshot passed
three local macOS ARM64 repeats (108/108); it predates the current 101-case
manifest. The H2 reset case observes request-future
termination, connection survival, same-connection recovery, and later
connection closure. It does not establish ASGI `http.disconnect` or identify the reset cause. The H1 half-close case completes a held response after client write-side shutdown while the connection lifetime remains open, consistent with RFC 9112 §9.6. See the
request-lifetime receipt (`benchmarks/results/2026-10-12/native-request-lifetime-live/report.md`).
The earlier 34-input package-move result remains in the
package-promotion receipt (`benchmarks/results/2026-10-12/native-package-promotion-live/report.md`).
The [`native-app-contract` 0.1.0 crate](https://crates.io/crates/native-app-contract/0.1.0)
is now published and exposes lifecycle hooks only. Starlette-RS/FastAPI-RS do
not yet consume it on their current main branches.

### Preserve dependency direction

The proposed Rust-native graph is:

```text
FastAPI-RS native app -> Starlette-RS native app -> shared app contract
uvicorn-rs native server --------------------------> shared app contract
uvicorn-rs-py -> Python ASGI callable (compatibility path)
fastapi-rs-py / starlette-rs-py -> Python framework APIs (compatibility paths)
```

Starlette-RS remains independent of Uvicorn-RS. FastAPI-RS uses Starlette-RS
by default and does not acquire a Uvicorn-RS dependency in its default graph.
An optional FastAPI-RS Cargo feature may link native `uvicorn-rs`; a Rust
application may also depend on both directly. Python extras install the
`*_py` clients and do not select a Python-free process.

## Protocol support and acceptance matrix

The shared application contract is protocol-neutral; each transport adapter
must pass its own live cases before that combination is listed as supported.

The following table describes implementation status, not a full support
claim. Each protocol row must pass its live cases and applicable RFC
requirements before that combination is listed as generally supported.

| Transport | Current prototype | Required live cases before general support is claimed |
|---|---|---|
| HTTP/1.1, cleartext and TLS | Provisional native `WebSocketUpgrade` and `WebSocketSession` API; 13 selected cleartext cases pass 13/13 with complete per-case attribution. This selected result is not aggregate coverage; aggregate acceptance remains incomplete. TLS is not yet measured for the native API. | accept/denial, full invalid-handshake inventory, subprotocol/header selection, text/binary exchange, close code/reason, abrupt disconnect, bounded slow consumer, shutdown, TLS |
| HTTP/2, TLS | Not implemented | RFC 8441 negotiation, accept/denial, stream reset, sibling-stream health, frame exchange, bounded send, shutdown |
| HTTP/3, QUIC/TLS | Not implemented | RFC 9220 negotiation, accept/denial, request-stream reset, sibling-stream health, frame exchange, bounded send, graceful drain |

Lifecycle inputs must cover startup ordering, startup failure, state visibility
to a request, shutdown after a drained request/session, cancellation at the
deadline, and hook errors. The core currently covers these hook properties
with its shared live manifest. A future framework integration must additionally
prove the framework's state is visible at request time and that framework
cleanup runs after sessions drain. Inputs should exercise public constructors
and real transport sessions through the existing manifest-driven live
harness; do not create a parallel unit-test framework.

The compatibility table must report each protocol combination separately.
Passing HTTP cases or Starlette's ASGI state-machine cases do not establish
native WebSocket support, framework lifecycle integration, or ASGI lifespan
2.0 support. The seven core hook cases establish only the prototype's native
startup/shutdown contract.

## Current transport API gates (2026-10-13)

The current native API provides distinct request- and connection-scoped
lifetime handles, but it does not yet provide the complete ASGI disconnect
contract above:

- The H2 live case observes RequestEndReason::ServiceFutureDropped after a
  stream reset, confirms that the connection remains open, serves a recovery
  request on that same connection, and then observes connection closure. The
  terminal reason describes what the service boundary observed; it does not
  identify whether a peer reset, connection error, or server cancellation
  dropped the service future. This case does not prove delivery of ASGI
  http.disconnect or the required Python task behavior.
- The current H3 adapter uses the maintained `uvicorn-rs-h3` package, based on
  upstream h3 0.0.8, and `uvicorn-rs-h3-quinn`, based on h3-quinn 0.0.10. It observes a
  request-stream reset when the request body or response writer is polled, but
  it has no independent request-close future for an application waiting on an
  unrelated await. The locked Quinn 0.11.12 provides a passive
  `SendStream::stopped()` future, but the H3 wrappers hide that sender. Kata
  `6sf0` audited these exact sources; implementation is tracked by `a2wf`.
  The preferred seam is an optional QUIC stopped-stream capability forwarded
  through the H3 wrappers to a request-scoped future. Only a peer stop code
  proves `STOP_SENDING`; normal finish acknowledgement and connection errors
  have different meanings. An application held before headers must be
  cancelled before any release, while a sibling request on the same
  connection still completes. Timer polling, probe response bytes, a second
  stream accept loop, and ordinary request-body EOF do not satisfy that gate.
- Hyper-util 0.1.21 hands off HTTP/1 upgrades by completing the connection
  future. The native core now uses `serve_connection_with_upgrades` and exposes
  `ConnectionUpgrade` on HTTP/1.1 requests. Applications register their
  `OnUpgrade` task through that handle; the connection task joins registered
  sessions, signals them at graceful shutdown, and cancels stragglers at the
  existing server deadline. Four focused real-socket inputs pass 4/4 for a
  successful `101` handoff/drain, session-handler error reporting, registration
  without an available upgrade, and registration after connection close. This
  generic upgrade lifecycle evidence is not WebSocket handshake, framing,
  protocol conformance, or aggregate coverage evidence. A provisional
  HTTP/1.1 `WebSocketUpgrade`/`WebSocketSession` API has since been added and
  its 13 selected cleartext handshake/session inputs pass with complete
  per-case attribution. Coverage-MCP follow-up matched the report's source
  receipt and passed tests, but found 32 missing region groups and 17 missing
  line groups in `crates/uvicorn-rs/src/websocket.rs`; aggregate acceptance
  remains incomplete. See the [support matrix](../support-matrix.md)
  for the report path, measured totals, and remaining gaps.

The generic H2 request/connection lifetime signal and its sibling-isolation
case are implemented. The native core now has a transport-specific HTTP/1.1
WebSocket API, but no shared framework contract or ASGI mapping.
ASGI task semantics and independent H3 idle-reset notification remain
feasibility gates, not support claims. Do not route Python ASGI traffic through
the native transport until pending-receive disconnect, response-after-EOF,
ASGI WebSocket, and upgraded-session shutdown cases pass the live matrix.

## Alternatives considered

- **Encode WebSockets as HTTP body frames:** rejected because WebSockets are
  bidirectional sessions with a handshake, close semantics, and independent
  send/receive demand; an HTTP response body cannot represent them correctly.
- **Put shared WebSocket/lifecycle contract types in Uvicorn-RS core:**
  rejected because Starlette-RS would then need a server dependency, reversing
  the agreed dependency direction. The core may depend on the neutral contract
  crate to implement server-side behavior.
- **Make Uvicorn-RS depend on Starlette-RS:** rejected because the server
  must host framework-neutral services and remain independently usable.
- **Keep ASGI dictionaries in the native path:** rejected because this would
  restore the Python-style message boundary that the native integration is
  intended to remove.

## Risks and open questions

- A shared contract crate adds one more independently versioned package. Keep
  it small and runtime-neutral; do not move HTTP request/response types into it
  if standard HTTP and Tower types already suffice.
- The lifecycle spike accepts `Send` futures and applies independent 30-second
  default startup and shutdown hook timeouts. The shutdown hook timeout begins
  after connection draining, so total server stop duration can exceed the
  graceful-drain limit. Revisit the total-deadline policy before stabilizing
  the interface.
- The session API must preserve flow control without forcing `Sync` on
  framework handlers or boxing every frame. Measure allocations and copies
  after a working implementation exists.
- The H2/H3 implementation must confirm that its protocol libraries expose
  the required Extended CONNECT and per-request reset lifecycle before the
  public contract is finalized. Current locked APIs do not yet prove those
  hooks.
- Shutdown policy for an accepted WebSocket session needs a documented close
  behavior and a deterministic deadline case before support is claimed.
- The exact lifecycle method signatures and state construction model remain
  implementation-spike decisions. Do not stabilize names before the same
  example compiles in Uvicorn-RS core, Starlette-RS, and FastAPI-RS.

## References

- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [RFC 8441: Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441.html)
- [RFC 9220: Bootstrapping WebSockets with HTTP/3](https://www.rfc-editor.org/rfc/rfc9220.html)
- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html)
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html)
- [ADR 0003: Rust-native service contract](0003-rust-native-service-contract.md)
- [Rust-native integration architecture](../rust-native-integration-architecture.html)
