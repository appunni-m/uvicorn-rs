# ASGI behavior and input inventory

This page maps the project's declared ASGI behavior to its live input cases and
records known gaps. It is a focused compatibility inventory, not the official
ASGI conformance suite. The normative references are the [ASGI 3 callable
specification](https://asgi.readthedocs.io/en/latest/specs/main.html), [HTTP and
WebSocket sub-specification 2.5](https://asgi.readthedocs.io/en/latest/specs/www.html),
and [lifespan sub-specification 2.0](https://asgi.readthedocs.io/en/latest/specs/lifespan.html).

The indexed, input-only cases live in [`tests/parity/manifest.json`](../tests/parity/manifest.json)
and [`tests/parity/inputs/`](../tests/parity/inputs/). They start a live
reference and target and compare wire-visible behavior. Cases marked
`verification: fault-contract` are target-only contracts; they are not counted
as oracle parity. The case IDs below name the current public input evidence.

## Declared behavior map

| ASGI area | Input evidence | Status and boundary |
|---|---|---|
| Callable shape and event dispatch | `http1.sync-callable-returns-awaitable`; `http1.asgi-event-type-string-subclass`; `http2.asgi-event-type-string-subclass`; `http3.asgi-event-type-string-subclass`; `websocket.subclass-event-types`; `lifespan-subclass-event-types.complete-events` | Live cases exercise synchronous callables returning awaitables and normal event names carried by `str` subclasses. The server does not implement ASGI 2-style thread-pool callables. |
| HTTP scope and request target | H1: `http1.scope-query-header-and-body`, `http1.scope-encoded-path-and-query`, `http1.scope-duplicate-header-order-and-raw-uri`, `http1.absolute-form-target-preserves-raw-headers`, `http1.scope-reports-http-1-0`, `http1.scope-http-1-0-without-host-header`, `http1-tls.scope-reports-https`. H2/H3: `http2.scope-query-header-and-body`, `http2.scope-preserves-duplicate-headers`, `http2.scope-raw-uri-authority-and-host`, `http2.scope-host-fallback-without-authority`, and matching `http3.*` cases. | The fixture observes scope type, ASGI version, HTTP version, method, scheme, decoded path, raw path, query bytes, root path, headers, client/server, and state. The custom H2/H3 inputs check `:authority`/`Host` mapping and duplicate values. This is a focused request-target inventory. |
| HTTP and WebSocket ASGI spec version | `support.http1.asgi-http-spec-version-2-5`, `support.http2.asgi-http-spec-version-2-5`, `support.http3.asgi-http-spec-version-2-5`, `support.websocket.asgi-http-spec-version-2-5`; WebSocket close/disconnect reason inputs include `websocket.server-initiated-close` and `websocket.client-close-code-and-reason`. | The support contracts verify the advertised `spec_version` and public reason behavior. They do not prove every requirement in the advertised revision. |
| Request body and `http.request` events | H1: `http1.request-upload-stream`, `http1.request-streaming-progress-before-upload-complete`, `http1.post-empty-body`, `http1.request-trailers-after-streamed-upload`, `http1.upload-remains-after-one-asgi-receive`, `http1.request-body-drained-after-early-response`. H2: `http2.request-upload-stream`, `http2.request-streaming-progress-before-upload-complete`, `http2.empty-final-data-frame-is-ignored`, `http2.request-trailers-after-streamed-upload`. H3: `http3.post-first-upload-response`, `http3.post-empty-data-frame-before-body`, `http3.early-response-with-open-upload`. | Cases exercise incremental bodies, empty final chunks, early response while upload continues, drain behavior, and body completion. H1 chunk decoding and H2/H3 DATA framing belong to the protocol adapters. Request-trailer handling is not claimed as an ASGI trailer event. |
| Disconnect and cancellation | H1: `http1.client-disconnect-event`, `http1.disconnect-before-first-asgi-receive`, `http1.disconnect-after-complete-request-while-receive-waits`, `http1.reset-during-incomplete-request-body`, `http1.malformed-chunk-body-becomes-asgi-disconnect`, `http1.disconnect-after-response-start-send-error`. H2: `http2.reset-incomplete-upload-keeps-sibling-stream-healthy`, `http2.reset-after-empty-request-keeps-sibling-stream-healthy`, `http2.reset-after-complete-upload-keeps-sibling-stream-healthy`, `http2.response-stream-reset-cancels-app`. H3: `http3.request-body-client-abort`, `http3.client-cancels-large-response-after-headers`. Zero-grace shutdown: `lifespan.zero-timeout-shutdown-cancels-16-active-streams`. | These are synchronized public-input cases for the listed combinations, not an exhaustive disconnect race or QUIC reset-frame corpus. The zero-grace case holds and cancels 16 HTTP/1.1 responses and verifies completed lifespan shutdown. Target-only pump and cancellation fault contracts are recorded separately in the unified report. |
| HTTP response start/body and streaming | H1: `http1.response-stream-order`, `http1.response-first-chunk-before-app-completion`, `http1.response-burst-backpressure`, `http1.response-burst-backpressure-large-body`, `http1.response-body-fields-default-empty`, `http1.final-response-completes-before-app-return`. H2: `http2.response-stream-order`, `http2.response-first-chunk-before-app-completion`, `http2.response-burst-backpressure`, `http2.final-response-completes-before-app-return`. H3: `http3.response-stream-order`, `http3.response-burst-backpressure`, `http3.response-body-fields-default-empty`. | The cases cover status/body delivery, ordering of body chunks, first-byte progress, queue pressure, and final-body completion. They do not claim support for every optional response extension. |
| Concurrent slow-reader load | H1: `http1.concurrent-connections-slow-readers-resource-bound`; H2: `http2.concurrent-stream-load-slow-reader-resource-bound`; H3: `http3.concurrent-stream-load-slow-reader-resource-bound`; WebSocket: `websocket.concurrent-sessions-slow-reader-resource-bound`. | Inputs drive fixed concurrency, repeated slow reads, response/message fingerprints, task cleanup, follow-up health, and sampled RSS/task stability. They do not establish high-scale capacity, an absolute memory cap, or a performance gain. H1/H2 run 32 clients for four rounds; H3 runs 16 clients for three rounds; WebSocket runs 16 sessions for four rounds. See [the parity workflow](parity.md#concurrent-load-and-zero-grace-shutdown-workflows). |
| Response header values | `http1.response-headers-preserve-duplicate-value-order`, `http2.response-headers-preserve-duplicate-value-order`, `http3.response-headers-preserve-duplicate-value-order`. | Repeated values for each name are compared in input order. H1/H2 results retain ordered wire fields. The H3 client exposes response fields through `http::HeaderMap`; its iteration order is not evidence of wire order. The comparator groups values by name because the current transport representation regroups different names. |
| WebSocket scope, accept, and messages | Scope: `websocket.scope-headers-path-query-and-subprotocols`, `websocket-tls.scope-headers-path-query-and-subprotocols`. Handshake rejection: `websocket.empty-subprotocol-token-handshake-rejected`. Messages: `websocket.text-and-binary-round-trip`, `websocket.empty-text-and-binary-payloads`, `websocket.accept-with-custom-asgi-header`, `websocket.pre-accept-denial`, `websocket.client-close-code-and-reason`, `websocket.send-after-client-disconnect`, `websocket.control-ping-pong`, `websocket.abrupt-client-disconnect`. | The scope fixture observes type, HTTP version, scheme, path/raw path/query, headers, addresses, subprotocols, and state. The malformed-header case verifies that empty comma-list members are rejected during handshake parsing before the ASGI app runs. Other cases cover handshake decisions, text/binary messages, custom acceptance headers, close values, disconnect, and protocol ping/pong. WebSocket transport support is HTTP/1.1 Upgrade only. |
| Lifespan and state | `lifespan.state-shallow-copy-does-not-rehash-keys`, `lifespan.startup-and-shutdown-cancel`, `lifespan.lifespan-startup-complete-then-returns`, `lifespan.shutdown-complete-then-raises`, `lifespan.lifespan-shutdown-unexpected-event`, `lifespan.public-server-api-cancels-and-shuts-down`, `lifespan.zero-timeout-shutdown-cancels-16-active-streams`; startup failure cases are indexed under `tests/parity/inputs/startup-*.json`. | Live cases cover startup/shutdown sequencing, startup and shutdown failures, auto fallback for unsupported lifespan, same-loop state transfer, shallow per-request state copying, and selected shutdown cancellations. The zero-timeout case verifies that 16 active HTTP/1.1 response tasks are cancelled while lifespan shutdown completes inside its own bounded window. H2/H3/WebSocket shutdown under concurrent load remains unverified. |
| Invalid events and application exceptions | H1: `http1.invalid-asgi-missing-event-type`, `http1.invalid-asgi-unknown-event-type`, `http1.invalid-asgi-body-before-start`, `http1.invalid-asgi-response-status-range`, `http1.duplicate-response-start`, `http1.response-start-then-app-error`, `http1.application-error`. H2/H3 include `http2.invalid-asgi-response-start-missing-status`, `http3.invalid-asgi-response-start-missing-status`, and `*.application-error-before-response-start`. WebSocket cases include `websocket.missing-event-type`, `websocket.unsupported-event-type`, `websocket.app-error-before-handshake`, and `websocket.application-error-after-accept`. | These cases observe public error responses, process behavior, and selected logs. Instrumented target-only contracts cover internal errors that ordinary ASGI inputs cannot trigger. |
| Python loop, thread, and context | `scripts/probe_http.py`, `scripts/check_installed_wheel.py`, and the `lifespan.*` public Server API workflows; task-factory cleanup has target-only `server_api_probe.py` cases. | These are focused API/package probes, not all live source/target input comparisons. Other event loops, nested contexts, and every task-factory schedule are unverified. |

The TLS WebSocket scope-close input runs with a fresh reference and target
server lifetime. It sends a server-initiated close; transport teardown from that
connection can race a later independent TLS case when a profile server is
reused. The runner isolates this case boundary and still compares both live
servers against the same input.

## Known gaps and unsupported surface

- The HTTP/WebSocket specification says response header order must be preserved
  in the HTTP response. The interleaved input records a concrete H1/H2 mismatch:
  output groups duplicate values by name after the Rust bridge stores them in
  `http::HeaderMap`. H3 response fields also pass through a `HeaderMap` in the
  client adapter, so the current H3 observation cannot establish raw wire order.
  Cross-name response order is a known H1/H2 ASGI deviation and remains
  unverified over H3.
- `http.response.trailers` and other optional response extensions are not
  implemented or advertised. An unknown `http.response.trailers` event is
  exercised by `http1.invalid-asgi-unknown-event-type`; this is not trailer
  support.
- WebSockets over HTTP/2 or HTTP/3, WSGI callables, reload/watch, worker
  supervision, and full Uvicorn CLI compatibility are outside the support
  claim.
- The official ASGI conformance suite and a complete HTTP security/framing
  corpus have not been run. Passing the indexed inputs is not full ASGI
  conformance.

See the [support matrix](support-matrix.md), [parity contract](parity.md), and
[unified coverage evidence](coverage.md) for current run identities and limits.
