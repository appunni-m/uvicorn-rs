# ADR 0003: Rust-native service contract and crate boundaries

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

- **Status:** The workspace package split is implemented: crates/uvicorn-rs is the Python-free Rust package and the root PyO3 distribution is uvicorn-rs-py. The native service API remains provisional; the Python adapter's default HTTP/1.1 and HTTP/2 TCP/TLS path now uses the native crate through `NativeAsgiService`, while HTTP/3 remains in the extension's Rust server layer. Python ASGI interactions still use the asyncio/PyO3 bridge. The historical 36-case real-socket manifest passed three sequential local macOS ARM64 runs (108/108); see the request-lifetime receipt (`benchmarks/results/2026-10-12/native-request-lifetime-live/report.md`). The new H2 input proves generic service-future termination notification, connection survival, same-connection recovery, and later connection-close notification; it does not prove ASGI http.disconnect or identify the reset cause. The H1 half-close input completes a held response after the client shuts down its write side, with the connection-lifetime handle still open, consistent with the note in RFC 9112 §9.6. The earlier 34-case package-promotion receipt (`benchmarks/results/2026-10-12/native-package-promotion-live/report.md`) is historical. The earlier archived 51/51 receipt used a separate FastAPI-native crate and remains historical. The sole `fastapi-rs` crate now has an initial native service slice; its 17-input H1/H2 composition passed once from clean detached sources at the pinned revisions in [the composition receipt](../native-fastapi-composition.md). Hosted CI, repeated composition, H3 framework composition, Python FastAPI parity, native WebSockets, framework lifecycle integration, and matched performance remain open.
- **Date:** 2026-10-12
- **Scope:** Direct Rust composition of Uvicorn-RS, Starlette-RS, and FastAPI-RS, plus optional Python compatibility clients. The current crate and import layout is transitional; backward compatibility with its package name, import path, or CLI is not a requirement.

## Context

### Source of truth for protocol behavior

The applicable IETF HTTP specifications are authoritative for wire semantics:
RFC 9110 for HTTP semantics, RFC 9112 for HTTP/1.1, RFC 9113 for HTTP/2, and
RFC 9114 for HTTP/3. ASGI specifies the Python application boundary. Uvicorn
and Hypercorn are compatibility references where those specifications leave
observable server behavior open; parity with an implementation does not make
a spec-violating wire input conforming. When a compatibility choice differs
from a protocol requirement, document the difference in the support matrix and
keep the specification behavior.

This precedence also governs benchmark fixtures. For example, RFC 9110
§9.3.1 says GET content has no generally defined semantics and clients SHOULD
NOT generate it without prior agreement. Section 8.6 says a sender SHOULD NOT
send `Content-Length` when a request has no content and its method semantics do
not anticipate it. Ordinary GET workloads therefore have no body and no such
field; workloads whose app consumes content use POST with an explicit body.
HTTP/3 additionally requires a content length to equal the sum of received
DATA-frame payloads when that request is defined as carrying content (RFC 9114
§4.1.2).

The intended native request path has no Python scope dictionaries, ASGI event dictionaries, Python callbacks, or Python values. Uvicorn-RS owns sockets, HTTP protocol state, TLS/QUIC, transport flow control, and connection shutdown. Starlette-RS owns portable web behavior. FastAPI-RS owns its higher-level routing, dependency resolution, validation, serialization, and OpenAPI behavior while composing Starlette-RS.

The current worktrees implement an early slice of that path:

| Repository | Current source state | Native-path gap |
|---|---|---|
| Uvicorn-RS, base `3dcaeaa0` plus the current package promotion | The root Cargo/Python distribution is now `uvicorn-rs-py` and builds a PyO3 `cdylib`; `crates/uvicorn-rs` is the Python-free native server package. The native crate exposes generic Tower services over Hyper HTTP/1.1/HTTP/2, TLS-over-TCP with ALPN metadata, and HTTP/3 over a caller-configured Quinn endpoint. The historical 36-case input-only socket manifest passed three sequential runs (108/108); see the request-lifetime receipt (`benchmarks/results/2026-10-12/native-request-lifetime-live/report.md`). The H2 reset case observes generic service-future drop and connection survival, not ASGI disconnect semantics. The H1 half-close case completes the held response after client write-side shutdown while the connection lifetime remains open. A local Starlette example uses the native crate over real cleartext H1/H2 sockets. An archived receipt describes a FastAPI-native composition on an earlier dirty sibling snapshot. | The Python adapter's default HTTP/1.1 and HTTP/2 TCP/TLS path now uses the native crate through a Rust Tower service. HTTP/3 remains in the extension's Rust server layer. Python loading, asyncio/PyO3 scheduling, ASGI scope/events, and app callbacks remain on the Python boundary. H3 has isolated native-contract evidence; it is not composed through Starlette-RS/FastAPI-RS and does not establish full RFC 9114 conformance. The older archived FastAPI example points to a removed sibling crate; the sole-core branch passed 17/17 once from clean detached checkouts at the pinned revisions in [the composition receipt](../native-fastapi-composition.md); hosted CI and repeated composition remain open. The separate Starlette example still uses an unpinned sibling checkout. WebSocket transport, ASGI lifespan semantics, framework use of native lifecycle hooks, and matched performance evidence remain open. TLS/QUIC configuration is caller-supplied and TLS is not exercised by composed examples. |
| Starlette-RS, pinned `b4c8a65` for this composition | The core remains free of PyO3 and Uvicorn-RS dependencies. FastAPI-RS's native route service uses the pinned Starlette-RS `RouteTable` through `FastApiOperationRouter`; it does not use a newer sibling service API or move the compatibility pin. The separate Starlette `NativeApplication` API remains available on a later source revision. | The current 17-input composition passed once from clean detached checkouts, including this pinned b4c8 source; the exact revisions and lock/manifest hashes are recorded in [the composition receipt](../native-fastapi-composition.md). Hosted CI and repeated evidence remain open, along with full-stack input parity, complete middleware coverage, WebSocket, and lifespan. |
| FastAPI-RS, native branch `f438a7c` | The native branch adds `fastapi_rs::native` to the sole `fastapi-rs` crate. Its default feature graph excludes PyO3; the `python` feature is enabled by `fastapi-rs-py`. The service registers Rust endpoints, delegates matching to Starlette-RS's pinned `RouteTable`, and preserves pull-based request and response bodies. The 17-input H1/H2 live manifest passed once on macOS ARM64 from clean detached checkouts. | This is local evidence, not hosted CI or release evidence. Complete FastAPI validation/dependencies/OpenAPI semantics, Python FastAPI parity, repeated clean composition, composed HTTP/3, WebSocket, lifespan, and performance remain open. |

The table distinguishes earlier inspected revisions from current source evidence. The 2026-10-13 composition receipt records a clean detached build at three exact commits; it proves this one H1/H2 manifest only, not full conformance or release readiness.

## Decision

### Crate ownership

1. **`uvicorn-rs` is the Rust-native server crate/library.** This package identity is now assigned to `crates/uvicorn-rs`; it owns the public Rust service API and network/protocol runtime, with no PyO3, Python runtime, or framework dependency. A Rust application normally builds its own executable and supplies a compiled Rust service to this library; a generic `module:app` loader belongs to the Python client. A standalone launcher, if offered, needs an explicit native app-registration model. The service contract remains provisional.
2. **`uvicorn-rs-py` is the optional Python ASGI client.** The root extension and console-script distribution have been renamed. The current default HTTP/1.1 and HTTP/2 TCP/TLS path uses the native `uvicorn-rs` crate; the extension still owns the HTTP/3 serving path. Python loading, asyncio/PyO3 bridging, ASGI adaptation, and app execution remain Python-facing work. Preserve Python event-loop ownership, callable behavior, context, cancellation, disconnect, streaming, and exception behavior at that boundary. Python code continues to require the GIL.
3. **`starlette-rs-py` and `fastapi-rs-py` are thin Python compatibility clients.** They own compatibility with their corresponding Python framework APIs and the declared Python versions. Rust-native Starlette-RS and FastAPI-RS remain usable without these clients and contain no PyO3 dependency. The clients must not be required by the native server or native framework graph.
4. **The all-Rust request path is the default native integration:** FastAPI-RS composes Starlette-RS, then passes a Rust service to Uvicorn-RS. No Python scope dictionaries, callbacks, or ASGI messages appear on this path. A FastAPI-RS Cargo feature may optionally enable a Uvicorn-RS convenience integration; Starlette-RS remains server-neutral and has no Uvicorn-RS dependency.
5. **There is no migration requirement to preserve the current `uvicorn-rs` Python import path, Cargo crate shape, or CLI name.** The supported Python server command belongs to `uvicorn-rs-py`; it implements the documented ASGI contract rather than inheriting every Uvicorn CLI flag or private framework API. Keep separate compatibility matrices: `uvicorn-rs-py` declares Python/runtime and ASGI support; `starlette-rs-py` declares Starlette/Python combinations; and `fastapi-rs-py` declares FastAPI/Starlette/Python combinations. Uvicorn CLI/API compatibility is a separate contract and is not implied by accepting ASGI `module:app` applications. Publish tested combinations rather than promising their full Cartesian product. The current package layout is transitional and is not a compatibility target.

The root `src/lib.rs` in package `uvicorn-rs-py` still owns Python loading,
asyncio bridging, ASGI conversion, and HTTP/3 serving. Its default TCP/TLS
HTTP/1.1 and HTTP/2 path now calls the native crate, which owns the connection
protocol runtime for those transports. Continue consolidating protocol
ownership without moving Python app execution or ASGI semantics into Rust.
The initial native runtime configuration remains one Tokio worker per process,
as selected for the current performance investigation. Runtime ownership and
caller-supplied runtime support must be explicit in the stable library API.

### HTTP request and response seam

Use the ecosystem's existing HTTP types and Tower service trait:

```rust,ignore
tower_service::Service<http::Request<IncomingBody>>
    -> http::Response<OutgoingBody>
```

The pseudocode describes the shape only; it is not a public type declaration. The actual proposal is:

- Request and response heads use `http::Request` and `http::Response` from `http` 1.x.
- `IncomingBody` and `OutgoingBody` are shorthand for bodies implementing `http_body::Body<Data = bytes::Bytes> + Send + 'static`. The framework service must not depend on Hyper's `Incoming` or the `h3` crate's body type. The server may pass each transport's concrete body type to a generic service implementation.
- Preserve `http_body::Frame<Bytes>` boundaries, including trailers. Do not collect a request body or streamed response into one `Vec` merely to cross the service boundary.
- Use `tower_service::Service` for request readiness, dispatch, response, and typed service errors. The server must honor `poll_ready` before `call`; service cloning and multiplexed concurrency semantics remain a prototype gate.
- Make pre-commit error handling explicit through
  `ServerConfig::service_error_policy`. The default
  `ServiceErrorPolicy::RespondInternalServerError` returns an empty 500.
  `ServiceErrorPolicy::Propagate` preserves the original readiness or service
  error for the protocol driver: HTTP/1 ends its connection, while HTTP/2
  and HTTP/3 reset the failed stream. The observer retains the typed cause
  and phase. This is a prerequisite for the ASGI adapter's invalid HTTP/1
  response-start behavior; the adapter still decides how Python application
  errors map to responses. Response-body errors after commitment retain
  their existing termination behavior.
- Keep the response body concrete where the application can do so. A framework may erase body types inside its route table when heterogeneous handlers require it, but the server boundary should not require a boxed body unless measurement or protocol adaptation proves that necessary.
- Carry HTTP version in the standard request head. Put peer, TLS/ALPN, request identity, and other agreed transport context in typed request extensions. Do not expose Tokio-specific types in Starlette-RS's portable API.
- The cleartext/TLS TCP and HTTP/3 QUIC entry points in `uvicorn-rs` insert `uvicorn_rs::ConnectionInfo` into every request's `http::Extensions`. It exposes the peer `SocketAddr`, a typed `TransportKind` (`Tcp` or `Quic`), and optional negotiated TLS/ALPN metadata; the request head supplies the HTTP version. Request identifiers are not yet represented. Starlette-RS passes extensions through without importing Uvicorn-RS, so an application can read this optional server metadata without adding a server dependency to the framework.
- Keep the service error and body error distinct and typed. A service error before response commitment can produce the documented server error response. A body error after commitment terminates the response stream using the protocol's error behavior; it cannot start a second response. The optional `ServerErrorObserver` exposes the original error and source chain synchronously with a phase and peer address; it is disabled by default and does not replace protocol response behavior.

This design lets Hyper and H3 provide different incoming body implementations while the same framework service consumes the `http_body::Body` contract. Moving `Bytes` frames transfers ownership; it does not promise zero-copy parsing, TLS, compression, or application behavior. Copies must be measured and documented at each conversion.

### Peer closure and request lifetime

`ConnectionLifetime` signals connection-driver termination; `RequestLifetime`
reports service or response-body completion/drop. Neither identifies a peer
TCP FIN. The native server now inserts a separate `PeerReadHalfClosed` handle
for TCP requests, including TLS. It records successful raw EOF reads below TLS;
reader destruction without EOF returns `PeerReadHalfClosedUnavailable`.
HTTP/2 stream reset does not set it, and HTTP/3 has no TCP handle.

The selected 18-input EOF run verified response delivery after peer write-half
closure and observation after complete, empty, or streamed H1 responses over
TCP/TLS. That run did not establish notification before a held service
returns. Locked Hyper's half-close policy can defer reads during an H1
response, and a service-wide EOF guard would suppress incomplete request-body
errors. The later native implementation uses opt-in
`PeerReadHalfCloseMode::Proactive`: one owned raw TCP reader feeds TLS/HTTP
through a bounded queue while the protocol driver remains the sole consumer.
The current 206-case native manifest includes held-service inputs for
bodyless, complete, and incomplete uploads over cleartext and TLS. All 206
native cases passed in each of three repeats in the source-bound 717-case
unified report, which remains dirty local evidence rather than hosted release
proof. Default `OnRead` behavior can still defer EOF observation, and this
native request extension does not deliver ASGI `http.disconnect`. See the
[current coverage record](../coverage.md#current-unified-coverage-status-2026-10-15).

An isolated copy of Hyper 1.11.1 demonstrates a narrower parser-aware path:
when request parsing has reached `Reading::KeepAlive` with no buffered bytes,
poll for input and close only the read side on EOF. Its six cleartext socket
inputs pass for held empty/fixed/chunked requests, incomplete-body errors and
a peer that stays write-open. Unmodified Hyper fails the three prompt-EOF
assertions while both builds retain response delivery. The observer assertion
requires successful completion and confirmed EOF, so reader destruction
cannot satisfy it. This is feasibility evidence under ignored `target/`, not
a dependency change or production capability. TLS and buffered pipelining
need separate evidence before adopting this parser-aware Hyper change; the
production Proactive mode is a distinct bounded-reader design.

The follow-up 11-input TLS/pipeline comparison failed **2/11 candidate inputs**:
an unclean TLS raw FIN surfaced Rustls `UnexpectedEof` before the held response,
and a TLS raw-FIN pipeline delivered the first response but did not dispatch
the buffered follow-up within the two-second bound. The candidate passed the
TLS `close_notify`-only and peer-open pipeline controls, plus cleartext
pipelining. The unchanged baseline delivered both TLS raw-FIN responses; its
prompt EOF observation varied across runs. This is a transport-driver
incompatibility in the prototype, so the cleartext patch is not ready to apply
unchanged to the production TLS path. The full comparison and hashes are in
the ignored receipt `target/hyper-eof-tls-pipeline-20261014/receipt.md`.

The wire semantics constrain how to interpret these outcomes. RFC 9112
§9.6 explicitly says a client TCP half-close does not delimit an HTTP request
and does not imply that the client cannot receive a response. Preserve response
writes after a cleartext peer FIN, and expose this fact as a read-half-closure
signal rather than treating it as a completed HTTP request or full disconnect.
For HTTPS, RFC 8446 §6.1 requires a TLS `close_notify` before a peer closes its
write side; a transport FIN without that alert leaves the receiver unable to
know whether all TLS data arrived. Keep the `UnexpectedEof` outcome for this
unclean TLS close distinct from orderly TLS `close_notify`. The prototype's
TLS raw-FIN failures are therefore an adoption blocker, not grounds to bypass
Rustls truncation handling. The cleartext candidate still needs parser-aware
pipeline and held-service evidence before any production change.

### Dependency versions

Use these compatible semver requirements in crates that expose the corresponding types publicly:

| Crate | Proposed requirement | Resolved in the inspected lockfiles | Role |
|---|---:|---:|---|
| `http` | `1` | `1.5.0` in the Uvicorn core, Starlette-RS, and FastAPI-native lockfiles | Request/response heads and extensions |
| `bytes` | `1` | `1.12.1` in the Uvicorn core, Starlette-RS, and FastAPI-native lockfiles | Owned body data frames |
| `http-body` | `1` | `1.1.0` in the Uvicorn core, Starlette-RS, and FastAPI-native lockfiles | Streaming data and trailer frames |
| `tower-service` | `0.3` | `0.3.3` in the Uvicorn core, Starlette-RS, and FastAPI-native dependency graph through Starlette-RS | Minimal Tower `Service` trait |
| `tower-layer` | `0.3` | `0.3.3` in the Starlette-RS and FastAPI-native dependency graphs; not a direct Uvicorn-core dependency | Middleware composition |

The Uvicorn-RS core and Starlette-RS workspaces pass locked all-target checks on Rust 1.85. The earlier FastAPI-native receipt records locked all-target Clippy and a default graph without Uvicorn-RS core; those checks apply to the removed separate crate. The new sole-core native branch passes `make clippy`, a default-feature `cargo check`, and a live graph build without PyO3. Its checked-in relative-path example has not yet been validated from a clean sibling workspace. Verify there is only one resolved HTTP/body major version in the final integration binary.

`http-body-util` is an implementation dependency of the Starlette-RS prototype and its `UnsyncBoxBody` type is currently visible through public body aliases. The framework response erases heterogeneous endpoint body types once at the dynamic route boundary while preserving streamed frames. Decide whether to keep that public body type or replace it with a crate-owned erased body before stabilizing the API.

### WebSocket and application lifecycle

`tower_service::Service<Request<B>>` and `http_body::Body` cover HTTP request/response streams. They do not define a bidirectional WebSocket session. A provisional `native-app-contract` crate now defines runtime-neutral startup and shutdown hooks, but neither that interface nor its use by a framework is stable. Do not model WebSocket messages as HTTP body chunks or reintroduce ASGI dictionaries on the native path.

The native HTTP service API remains provisional and can change while the crate boundary is migrated. Keep lifecycle hooks in the small runtime-neutral contract crate, and design the WebSocket session contract there as a separate addition. Preserve dependency direction: Starlette-RS cannot depend on Uvicorn-RS, and Uvicorn-RS cannot depend on Starlette-RS. An optional FastAPI-RS integration is allowed, but it must not enter the default framework graph. The lifecycle method shape remains provisional until Starlette-RS and FastAPI-RS consume the same crate.

The Python ASGI adapter now uses the native server for HTTP/1.1 and HTTP/2 over
TCP/TLS through `NativeAsgiService`. `uvicorn-rs-py` remains a separate
PyO3-backed distribution, while `crates/uvicorn-rs` accepts native Tower
services and contains no PyO3 runtime dependency. HTTP/3 still uses the
extension's Rust server layer. Python application loading, asyncio ownership,
ASGI callbacks, event conversion, context, and exception behavior cross the
bridge to Python; native framework services do not. This split keeps Python
compatibility while allowing Starlette-RS/FastAPI-RS to compose without a
Python boundary. Hosted source-matched correctness evidence and valid paired
performance evidence for the integrated transport remain release gates.

## Consequences

- Starlette-RS can implement or adapt the HTTP service without linking the server or Python. FastAPI-RS can compose that service at Rust level after its Python compatibility implementation is separated.
- Generic incoming body types avoid forcing protocol-specific crates into framework dependencies. The framework response body remains one concrete Rust type per application.
- The isolated core has live HTTP/3 cases for request/response body streaming, request/response trailers, QUIC metadata, finite slow-reader backpressure, cancellation, and graceful drain. This does not establish full RFC 9114 conformance, broad QUIC interoperability, or equivalent behavior through Starlette-RS/FastAPI-RS. Service cloning, larger-scale multiplexing, loss/recovery, and many protocol edge cases remain open.
- This ADR does not establish native WebSocket support, ASGI lifespan 2.0 semantics, framework integration of lifecycle hooks, a clean external multi-repository build, package readiness, or a performance gain.

## Prototype gates

1. **Prototype passed:** build the core without PyO3 or Python runtime dependencies; verify on Rust 1.85 and stable and inspect its dependency tree.
2. **Prototype passed:** serve a body-aware Tower service over a real socket and verify the streamed response with HTTP/1.1 and HTTP/2 prior knowledge. The Starlette-composed example consumes the full request before starting its response, so it does not prove early response, slow-reader backpressure, or cancellation through Starlette.
3. **Partially passed:** thirty-six live inputs passed three sequential local repeats (108/108) on macOS ARM64. The manifest includes cleartext HTTP/1.1, cleartext HTTP/2 prior knowledge, TLS HTTP/1.1 and HTTP/2 ALPN/metadata, seven HTTP/3 inputs, three lifecycle-drain inputs across H1/H2/H3, four lifecycle fault inputs, and the H2 request-lifetime reset input, and the H1 peer write-half-close input. The original 34-input package-promotion receipt remains historical; that historical snapshot's input/source hashes and logs are in benchmarks/results/2026-10-12/native-request-lifetime-live/. The new input observes a generic ServiceFutureDropped reason after an H2 stream reset, verifies that the same connection remains usable for a recovery request, and then observes connection closure. It does not determine whether a peer reset, connection failure, or server cancellation dropped the service future, and it does not establish ASGI http.disconnect. The H1 input is a single HTTP/1 behavior contract, not broad conformance. Existing TCP/H3 inputs cover peer metadata, body streaming/trailers, response streaming, request/response cancellation, typed transport-error observation, bounded slow-reader polling, and graceful drain. These are finite target-only contracts, not a general buffer-size or performance claim; they do not establish full RFC 9114 conformance, broad interoperability, or ASGI lifespan behavior.
4. **Partially passed:** the isolated generic core now serves H3 over a caller-configured Quinn endpoint and carries QUIC peer, transport-kind, negotiated TLS/ALPN, and HTTP-version metadata. The seven H3 live cases cover streaming, trailers, backpressure/cancellation, and graceful drain. This does not yet integrate H3 with the composed Starlette-RS/FastAPI-RS stack or prove full RFC 9114 conformance; broader interoperability, loss/recovery, QUIC connection-close behavior, and service-level H3 parity remain open.
5. **Initial native composition passed:** the sole `fastapi-rs` crate now has a `fastapi_rs::native` service surface. It uses FastAPI-RS operation metadata and the pinned Starlette-RS `RouteTable`, exposes Rust endpoint closures as a Tower service, and keeps request/response bodies pull-based. The current `examples/native-fastapi-contracts/manifest.json` passed 17/17 live H1/H2 inputs once on macOS ARM64 from clean detached checkouts: Uvicorn-RS `8e7e68046082a024a73877ee6476c5c395339839`, FastAPI-RS `f438a7cbb2308e6c1f795aef98e333de23388533`, and pinned Starlette-RS `b4c8a65c85e1b0d251ca05874412811eaa3ac7b8`. The [composition receipt](../native-fastapi-composition.md) records manifest, lockfile, and Cargo manifest hashes. The earlier 51/51 receipt at `benchmarks/results/2026-10-12/native-fastapi-h2-streaming-composition/` used a separate `fastapi-rs-native` crate and remains historical. **Open:** hosted CI and repeated composition, extend native validation/dependency/OpenAPI semantics, establish Python FastAPI parity through `fastapi-rs-py`, and record composed H3, WebSocket, lifecycle integration, and performance evidence. Do not add a separate `fastapi-rs-native` behavior crate.
6. **Partially passed:** the provisional runtime-neutral lifecycle hook contract passes the seven inputs described in gate 3. **Open:** define and implement WebSocket sessions; consume the lifecycle contract from Starlette-RS/FastAPI-RS; test ASGI lifespan separately; and establish cross-repository compatibility before stabilizing the API.

Select the normal H1/H2/TLS/H3 prototype inputs before running the normal
example. Coverage-only fault cases remain in the complete unified runner:

```sh
python3 scripts/select_native_contracts.py
cargo run -p uvicorn-rs --example native_core_contracts --locked --offline -- target/native-contracts/normal-inputs.json
```

The HTTP/3 entry point accepts a caller-configured Quinn endpoint; the caller
owns certificate and QUIC TLS policy. The seven H3 cases are isolated core
contracts and are not the composed FastAPI/Starlette integration. Repeatable
local evidence is recorded in
`native-core-http3-live` (`benchmarks/results/2026-10-12/native-core-http3-live/report.json`).

These target-only native service contracts do not replace the Python ASGI
parity/fault matrix, nor do they establish full HTTP protocol conformance.

The Starlette-RS service smoke currently runs with:

```sh
cargo run -p starlette-rs-native-service-smoke --locked
```

It exercises a streamed two-frame request, typed route parameter, query and
header access, a Tower request-header layer, one-demand-per-response-frame
polling, and the 404 fallback. This is application-level in-process evidence;
it does not close the socket-level, cancellation, or protocol integration
gate above.

The current local Uvicorn-core-to-Starlette socket example runs with:

```sh
cargo run --manifest-path examples/native-starlette-server/Cargo.toml --locked -- 127.0.0.1:8080
```

It passed live HTTP/1.1 and HTTP/2 prior-knowledge POSTs, a service failure
before response commitment, and a response-body failure after a 200 response
and partial body were observed. The example uses a relative path dependency on
the sibling Starlette-RS worktree; it is local integration evidence, not the
pinned clean-source example required for release readiness.

## References

- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html), especially [§8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6) and [§9.3.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.1)
- [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)
- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html)
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html), especially [§4.1.2](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.1.2)
- [Tower Service 0.3.3](https://docs.rs/tower-service/0.3.3/tower_service/trait.Service.html)
- [`http` 1.5.0](https://docs.rs/http/1.5.0/http/)
- [`http-body` 1.1.0 `Body`](https://docs.rs/http-body/1.1.0/http_body/trait.Body.html) and [`Frame`](https://docs.rs/http-body/1.1.0/http_body/struct.Frame.html)
- [`bytes` 1.12.1 `Bytes`](https://docs.rs/bytes/1.12.1/bytes/struct.Bytes.html)
- [Rust-native integration architecture](../rust-native-integration-architecture.html)
