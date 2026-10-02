# uvicorn-rs

An independent Rust network server for Python ASGI 3 applications. Rust handles
listeners, HTTP/1.1, HTTP/2, experimental HTTP/3, WebSocket transport, flow
control, and shutdown. Python loads the application and keeps ownership of its
asyncio event loop and ASGI tasks.

This is an experimental prototype. Its measured HTTP/1.1 performance does not
match Uvicorn's fastest configuration across representative workloads; streamed
responses are a known regression. See [the measured results](docs/feasibility.md)
before evaluating it for deployment. The current implementation has targeted
black-box coverage, not a complete ASGI conformance run or a production security
review.

`uvicorn-rs` is the project name used by the supplied GitHub repository and is
not affiliated with the Uvicorn project. `starlette-rs` is an optional,
separately installed ASGI application; this server neither depends on nor
bundles it.

## Try it locally

The local development environment was verified with CPython 3.12.13 and Rust
1.98.1. `Cargo.toml` declares Rust 1.83 as the minimum, but that exact toolchain
has not been validated. From a checkout:

```sh
uv sync --python 3.12
uv run uvicorn-rs examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl http://127.0.0.1:8000/
```

The CLI loads an importable `module:attribute` and serves one ASGI application.
HTTPS and HTTP/3 are enabled together when both `--certfile` and `--keyfile` are
provided. For all supported arguments, defaults, API behavior, and signal
handling, see [configuration](docs/configuration.md).

## What is implemented

- HTTP/1.1, HTTP/2, and experimental HTTP/3 over TCP/TLS and QUIC.
- HTTP request and response streaming with bounded message queues.
- HTTP/1.1 WebSocket upgrade and ASGI WebSocket messages.
- ASGI lifespan, request disconnect events, task cancellation, and graceful
  shutdown.
- A Python asyncio boundary, with optional uvloop for the Python application
  loop. Rust Tokio owns the network runtime; uvloop does not replace Tokio.
- PyO3 conversion that retains immutable Python `bytes` owners for outgoing
  HTTP bodies, WebSocket binary payloads, and header fields, avoiding payload
  copies on those Python-to-Rust paths.

The exact live-tested behaviors, missing protocol cases, and platform limits are
listed in the [ASGI support matrix](docs/support-matrix.md). See
[architecture and buffer ownership](docs/architecture.md) for the Rust/Python
boundary and remaining required copies.

## Development and evidence

Use the [contributor guide](CONTRIBUTING.md) for formatting, lint, documentation,
black-box probes, and the [input-only parity matrix](docs/parity.md). The
[implementation review](docs/implementation-review.md) tracks known technical
issues. The [feasibility report](docs/feasibility.md) includes baseline
methodology, per-category performance results, and the PyO3 buffer-ownership
experiment with links to raw JSON.

Run the input-only black-box server parity matrix with
`uv run --group benchmark python scripts/run_parity.py`; see the [parity suite
guide](docs/parity.md) for its oracle choices, support slice, and result format.

## Project boundaries

- This is not a drop-in Uvicorn replacement. Uvicorn CLI parity, reload, worker
  supervision, proxy-header handling, and Unix sockets are outside the current
  scope.
- HTTP/2 WebSockets and HTTP/3 WebSockets are unsupported. HTTP/3 remains
  experimental.
- No wheel or source distribution has been published.
- `starlette-rs` stays an independent framework and is not a runtime dependency
  of this server.

## Support, security, and licensing

There is no published support window; see [support expectations](SUPPORT.md).
Do not post vulnerability details in a public issue; use the private route in
[the security policy](SECURITY.md). The project has not selected a license, so
the public source grants no redistribution or reuse rights.

## Documentation map

- [Architecture decision record](docs/adr/0001-runtime-and-asyncio-bridge.md)
- [Architecture and memory ownership](docs/architecture.md)
- [CLI and Python API reference](docs/configuration.md)
- [ASGI support matrix](docs/support-matrix.md)
- [Input-only server parity suite](docs/parity.md)
- [Reproducible full benchmark setup and commands](docs/benchmarks.md)
- [Release candidate workflow and artifact checks](docs/releases.md)
- [Performance feasibility and raw results](docs/feasibility.md)
- [Known implementation issues](docs/implementation-review.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Support](SUPPORT.md)
