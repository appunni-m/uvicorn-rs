# uvicorn-rs

`uvicorn-rs` is a Python-free Rust library for serving Tower applications over
HTTP. The application owns the Tokio runtime and supplies a `tower_service::Service`;
the library accepts connections, drives HTTP, streams bodies under transport
backpressure, and drains connections during shutdown.

This crate is a library, not a standalone executable. It does not load
`module:app` or run Python ASGI applications. Use the separately distributed
[`uvicorn-rs-py`](https://github.com/appunni-m/uvicorn-rs) client for Python
ASGI applications. That client still crosses the Python ASGI boundary.

## Requirements

- Rust 1.85 or newer
- Edition 2021
- Tokio runtime supplied by the application
- No optional Cargo features are defined in this release

## Install

Version 0.1.0 is published on
[crates.io](https://crates.io/crates/uvicorn-rs/0.1.0). These dependency
requirements are Cargo semver ranges, not exact patch pins. Cargo resolves the
newest compatible versions; commit `Cargo.lock` in applications to keep a
deployment's exact dependency selection reproducible.

HTTP/3 is included in this release and is not behind a Cargo feature. The
published `uvicorn-rs-h3` and `uvicorn-rs-h3-quinn` crates are transitive
implementation dependencies; applications should depend directly on
`uvicorn-rs` only.

```toml
[dependencies]
bytes = "1"
http = "1"
http-body-util = "0.1"
hyper = { version = "1", features = ["server"] }
tokio = { version = "1", features = ["macros", "net", "rt", "signal", "sync"] }
tower-service = "0.3"
uvicorn-rs = "0.1"
```

## Minimal server

The [minimal server example](https://github.com/appunni-m/uvicorn-rs/blob/main/crates/uvicorn-rs/examples/minimal.rs)
implements a Tower service, serves `/health`, and returns 404 for other paths.
It owns the listener and Tokio runtime and asks the server to stop on Ctrl-C.
The example is built with the crate's normal CI targets.

From a repository checkout, run it with:

```sh
cargo run --manifest-path crates/uvicorn-rs/Cargo.toml --example minimal
```

Then request `http://127.0.0.1:8080/health`.

## Protocol and support boundaries

- Cleartext TCP and TLS over TCP support HTTP/1.1 and HTTP/2.
- HTTP/3 is experimental and uses a caller-configured Quinn endpoint.
- The native WebSocket API currently supports HTTP/1.1 only.
- `ApplicationLifecycle` provides native Rust startup and shutdown hooks; it
  is not the ASGI lifespan protocol.
- `PeerReadHalfClosed` observes actual raw TCP EOF, including below TLS.
  `ServerConfig.peer_read_half_close` defaults to `OnRead`, which uses no
  read-ahead queue and can wait until an HTTP/1 service or response finishes.
  Opt-in `Proactive` mode drives one owned raw-reader future in the existing
  connection task and feeds TLS/HTTP through a bounded queue: two queued 16 KiB
  chunks plus one being consumed. It adds one input copy and queue wakeups, so
  measure the workload before enabling it. A full queue can still delay EOF.
  Neither mode discards request bytes, completes an incomplete body, cancels a
  request, or closes response writes. If the reader ends without observing EOF,
  the wait method returns `PeerReadHalfClosedUnavailable`. This connection
  signal is absent on HTTP/3.
- HTTP/3 request tasks observe Quinn `STOP_SENDING` while readiness, the Tower
  service, or response-body writes are pending. A stop drops only that request's
  pending work; a normal send-side completion does not cancel the application.
  HTTP/3 retains its own stream and connection error boundaries.
- `ServiceErrorPolicy::RespondInternalServerError` is the default: Rust service
  and readiness errors before response commitment become an empty 500 response.
  `ServiceErrorPolicy::Propagate` forwards the original error to the protocol
  driver instead. HTTP/1 ends the connection; HTTP/2 and HTTP/3 reset the failed
  stream. The error observer receives the original typed cause and phase.
  Errors after response commitment terminate that response stream under either
  policy.
- HTTP/3 catches unwinding application panics during readiness and service
  invocation before headers, reports the corresponding error phase, and
  returns an empty 500. An HTTP/1 upgrade-handler panic ends its session and
  is logged; a live contract checks that the listener remains usable.
- The Rust library is independent of Starlette-RS and FastAPI-RS. Frameworks
  may implement Tower services and compose with this server.

See the project [support matrix](https://github.com/appunni-m/uvicorn-rs/blob/main/docs/support-matrix.md)
for the live-tested behavior and limitations, and the
[release status](https://github.com/appunni-m/uvicorn-rs/blob/main/docs/releases.md)
for current evidence. These statements do not claim full Uvicorn or complete
HTTP protocol compatibility.

## License

Licensed under either BSD-3-Clause or MIT, at your option. The crate archive
includes both license texts and the required attribution notices.
