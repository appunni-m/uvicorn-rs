# uvicorn-rs

[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-DB61A2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/appunni-m)

The target product is a Rust-native server crate named `uvicorn-rs`, with an
optional thin Python compatibility client named `uvicorn-rs-py`. Native
FastAPI-RS applications should compose FastAPI-RS → Starlette-RS → Uvicorn-RS
entirely in Rust. Python ASGI applications use `uvicorn-rs-py`; their callables
remain on the Python event loop and cross the Python boundary as ASGI requires.

The Cargo workspace now has distinct package identities: the Python extension
is `uvicorn-rs-py`, and the Python-free Tower server library is `uvicorn-rs`.
This is an intermediate migration step, not completion of the thin-client
architecture: the Python extension still contains its earlier network stack
and is not yet routed through the native server. The next implementation gate
is to converge on one transport and make `uvicorn-rs-py` only the ASGI bridge.
There is no requirement to preserve the old `uvicorn-rs` Python distribution,
import path, Cargo shape, or CLI name.

This remains an experimental prototype, not a demonstrated faster replacement
for Uvicorn. The latest completed full upstream FastAPI comparison is the
2026-10-09 run: it qualified 32 workload/loop comparisons across H1, H2,
WebSockets, and lifecycle. Results vary by workload: ordinary H1 routes, large
responses, H2 small-chunk uploads, and WebSocket echo regress, while H2 large
responses and WebSocket handshakes favor the Rust server. A separate default
1 MiB H1 upload measured 0.458× and 0.563× Uvicorn throughput under asyncio
and uvloop. Later source-bound batches and the 2026-10-12 hosted matrix remain
partial, so they do not establish a complete current-source multi-system
result. See the [complete results](docs/benchmark-results.md),
[benchmark status](docs/benchmark-status.md), and
[feasibility report](docs/feasibility.md).

A focused normal-build FastAPI comparison on 2026-10-17 confirmed the
validated-route regression on Linux x86-64: Rust/Uvicorn throughput was
0.652× with asyncio and 0.726× with uvloop, while server CPU per request was
1.96× and 1.75× higher. This one-workload result is not a whole-server score.
The documented scope keeps Python ASGI as a compatibility path and targets
performance claims at Python-free Rust-native application composition. See
the [performance decision](docs/performance-acceptance.json) and the
[retained run record](docs/benchmark-status.md#focused-normal-build-fastapi-matched-result-2026-10-17).

The previous local ASGI-adapter evidence snapshot is dated 2026-10-12: 511 cases,
comprising 243 live oracle comparisons and 268 target-only contracts, passed
attribution and three complete repeats. The dirty source snapshot measured
5,561/5,561 Rust regions and 3,997/3,997 lines; Coverage-MCP found zero missing
groups with matching source/build and test receipts. This is local evidence,
not a clean hosted release result, and covers `src/lib.rs` only. The Python
ASGI path now uses the Python-free `uvicorn-rs` crate for HTTP/1.1 and HTTP/2
over TCP/TLS; HTTP/3 remains in the extension's Rust server layer. Python app
invocation, ASGI events, and event-loop ownership still cross the PyO3 bridge.
See the [support matrix](docs/support-matrix.md) and
[coverage report](docs/coverage.md). A narrower `uvicorn-rs-py` candidate-wheel
smoke passed; see its [receipt](benchmarks/results/2026-10-12/uvicorn-rs-py-wheel-consumer/report.md).
The Python-free `uvicorn-rs` crate has body-aware Tower service entry points for
HTTP/1.1, HTTP/2, TLS over TCP, and HTTP/3 over a caller-configured Quinn
endpoint. The current 36-case live contract passed three sequential runs
(108/108) on macOS ARM64; see the [request-lifetime receipt](benchmarks/results/2026-10-12/native-request-lifetime-live/report.md).
It includes HTTP/3 request/response trailers, streaming, finite slow-reader
backpressure, graceful drain, provisional native startup/shutdown hooks, an
HTTP/2 request-lifetime signal case, and an HTTP/1 client half-close case.
The earlier [package-promotion receipt](benchmarks/results/2026-10-12/native-package-promotion-live/report.md)
retains the 34-case package-move result.
These are target-only native-server contracts, not full protocol conformance or
performance results. An archived 17-input FastAPI-native → Starlette-RS →
earlier Uvicorn-RS core receipt records
three repeats (51/51) on an earlier dirty, path-linked sibling snapshot,
including request-body progress before upload completion over cleartext H1 and
H2. That receipt used a separate `fastapi-rs-native` prototype and remains
historical. The sole `fastapi-rs` crate now has an initial native service
slice on the `codex/native-fastapi-core` branch. Its 17-input H1/H2 socket
manifest passed once from clean detached checkouts of Uvicorn-RS, FastAPI-RS,
and the pinned Starlette-RS source. See the [composition evidence](docs/native-fastapi-composition.md)
and [native composition example](examples/native-fastapi-contracts/README.md).
This is local prototype evidence, not hosted CI, full FastAPI or Python parity,
or a speed result. The native server product is the `uvicorn-rs` Cargo
package, and the Python extension is distributed as `uvicorn-rs-py`. The
Python ASGI path now uses the native crate for HTTP/1.1 and HTTP/2 over
TCP/TLS. HTTP/3 remains in the Rust server layer in the PyO3 extension. Python
ASGI calls still cross into the Python-owned asyncio loop for scope,
`receive`/`send`, context, and exceptions, so this is not a Python-free ASGI
path. Focused current-source cases pass, while exact-source hosted coverage
and performance evidence remain open. See the
[promoted-package live contract receipt](benchmarks/results/2026-10-12/native-package-promotion-live/report.md),
[historical pre-promotion receipt](benchmarks/results/2026-10-12/native-core-http3-live/report.json),
[native composition receipt](benchmarks/results/2026-10-12/native-fastapi-h2-streaming-composition/report.md),
[coverage report](docs/coverage.md#latest-local-evidence-2026-10-12), and
[support matrix](docs/support-matrix.md).
Hosted CI run [38087300590](https://github.com/appunni-m/uvicorn-rs/actions/runs/38087300590)
passed all eight gates on clean commit `16ed349`, before the current dirty core
prototype. The complete official ASGI conformance suite and production
security review have not been run.

`uvicorn-rs` is the project name used by the supplied GitHub repository and is
not affiliated with the Uvicorn project. The native server will remain
independent of Starlette-RS. Rust applications compose the two through the
server-neutral service contract; optional `uvicorn-rs-py`, `starlette-rs-py`,
and `fastapi-rs-py` clients own Python compatibility and version-specific
adaptation. Each client will publish its own tested version combinations:
`uvicorn-rs-py` for Python/runtime and ASGI support, `starlette-rs-py` for
Starlette integration, and `fastapi-rs-py` for FastAPI/Starlette integration.
Uvicorn CLI/API compatibility is separate from accepting standard ASGI apps;
oracle versions do not imply a drop-in API guarantee, and the matrices will
list tested combinations rather than every possible version pairing.

## Try it locally

The local development environment was verified with CPython 3.12.13 and Rust
1.98.1. Locked default and all-feature library builds also pass on Rust 1.85.0,
the declared minimum. An actual macOS wheel also passes an installed-package
HTTP/loop/context/lifespan/cancellation check on CPython 3.9.25. Hosted platform
checks are still pending. From a checkout:

```sh
uv sync --python 3.12
uv run uvicorn-rs-py examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl http://127.0.0.1:8000/
```

This command exercises the current Python ASGI adapter. It loads an importable
`module:attribute` and serves one ASGI application. Its transport has not yet
been consolidated with the native `uvicorn-rs` server crate.
HTTPS and HTTP/3 are enabled together when both `--certfile` and `--keyfile` are
provided. For all supported arguments, defaults, API behavior, and signal
handling, see [configuration](docs/configuration.md). See
[deployment and framework integration](docs/deployment.md) for service-manager
guidance and isolated Starlette compatibility probes.

## What is implemented

- HTTP/1.1, HTTP/2, and experimental HTTP/3 over TCP/TLS and QUIC.
- A Python-free service prototype, now packaged as `uvicorn-rs`, for HTTP/1.1,
  HTTP/2, TCP/TLS, and HTTP/3 over a caller-configured Quinn endpoint. It has
  a local Rust-native Starlette/FastAPI example over H1/H2, including request
  body progress before upload completion on both protocols. It is not
  integrated with the Python ASGI CLI; sibling-source examples are not pinned
  release artifacts. The optional native lifecycle hook is a provisional Rust
  contract, not ASGI lifespan. See the [composition receipt](benchmarks/results/2026-10-12/native-fastapi-h2-streaming-composition/report.md)
  and [lifecycle receipt](benchmarks/results/2026-10-12/native-core-lifecycle-live/report.md).
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
- The CLI starts one server process with one Tokio core worker. The Python app
  remains on its owning asyncio or uvloop event loop; Tokio's blocking pool can
  create additional threads for bridge work.
- HTTP/2 WebSockets and HTTP/3 WebSockets are unsupported. HTTP/3 remains
  experimental.
- No wheel or source distribution has been published.
- `starlette-rs` stays an independent framework and is not a runtime dependency
  of this server.

## Support, security, and licensing

There is no published support window; see [support expectations](SUPPORT.md).
Do not post vulnerability details in a public issue; use the private route in
[the security policy](SECURITY.md). The project is available under
[BSD-3-Clause or MIT](LICENSE), at your option. Copyright © 2026 Appunni M;
the license texts retain the original Uvicorn and Hypercorn notices.

## Documentation map

- [Architecture decision record](docs/adr/0001-runtime-and-asyncio-bridge.md)
- [Rust-native service contract ADR](docs/adr/0003-rust-native-service-contract.md)
- [Architecture and memory ownership](docs/architecture.md)
- [CLI and Python API reference](docs/configuration.md)
- [Deployment and framework integration](docs/deployment.md)
- [ASGI support matrix](docs/support-matrix.md)
- [Input-only server parity suite](docs/parity.md)
- [Reproducible full benchmark setup and commands](docs/benchmarks.md)
- [Latest benchmark run status](docs/benchmark-status.md)
- [Latest multi-system benchmark results](docs/benchmark-results.md)
- [Release candidate workflow and artifact checks](docs/releases.md)
- [Performance feasibility and raw results](docs/feasibility.md)
- [October 5 performance investigation](docs/performance-investigation-2026-10-05.md)
- [Known implementation issues](docs/implementation-review.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Support](SUPPORT.md)
