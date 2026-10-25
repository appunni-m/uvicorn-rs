# ADR 0006: One native server crate with optional HTTP/3

- **Status:** Accepted
- **Date:** 2026-10-22

## Context

The native server was split across `uvicorn-rs`, `uvicorn-rs-h3`, and
`uvicorn-rs-h3-quinn`. The two H3 crates exist only to provide implementation
details to the server. Requiring applications to navigate and publish those
packages creates extra package identities and release steps without giving
framework authors a useful independent contract.

The Python ASGI adapter has a different role. It bridges a Python-owned event
loop and ASGI callables into the Rust server. Rust-native applications should
be able to use the same server crate without importing Python or PyO3.

The lifecycle interface is useful independently of the server: Rust-native
frameworks can implement startup and shutdown hooks without taking a server
dependency.

## Decision

1. `uvicorn-rs` is the single native server crate. HTTP/1.1, HTTP/2, WebSocket
   transport support, and the server API live in this crate.
2. HTTP/3 protocol and Quinn adapter source live under `uvicorn-rs` and are
   compiled only with its optional `http3` Cargo feature. The default Rust
   dependency does not enable HTTP/3. Consumers that need it opt in with
   `features = ["http3"]`.
3. The Python ASGI client targets the not-yet-published PyPI distribution
   `uvicorn-rs`. Its root Cargo integration package and optional extra console
   script remain named `uvicorn-rs-py`. It depends on `uvicorn-rs` with HTTP/3
   enabled and owns Python app loading, event-loop scheduling, and ASGI message
   adaptation. This adapter is not a dependency of `uvicorn-rs`.
4. The runtime-neutral lifecycle package is named
   `asgi-lifespan-protocol-rs`. `uvicorn-rs` re-exports its public lifecycle
   types, while frameworks may depend on the lifecycle contract directly.
5. Do not publish separate `uvicorn-rs-h3` or `uvicorn-rs-h3-quinn` packages.
   Their 0.1.0 uploads remain in the historical bootstrap audit. A crates.io
   API check on 2026-10-25 returned HTTP 404 for those names and the removed
   `uvicorn-rs` 0.1.0 name. Keep the old checksums as history, but verify current
   `uvicorn-rs` name availability before a later server release. They are not
   dependencies of the new server.
6. `starlette-rs` does not depend on or bundle `uvicorn-rs`. A Rust-native
   `fastapi-rs` integration can optionally compose `starlette-rs` and
   `uvicorn-rs` at the Rust service boundary. The Python `*-py` clients remain
   independent adapters for Python ecosystem compatibility.

## Consequences

- Rust applications depend on one server crate and enable HTTP/3 explicitly.
- The `uvicorn-rs` archive contains vendored H3 source, the upstream MIT
  license texts, and attribution notices; Cargo feature selection controls
  whether H3 and Quinn are compiled into an application.
- Cargo release automation publishes `asgi-lifespan-protocol-rs` before
  `uvicorn-rs`, then verifies the server archive with HTTP/3 enabled and
  disabled. There are no project-owned H3 package publication jobs.
- Changing the default HTTP/3 feature and removing the split package graph is a
  release boundary. The next package version is 0.2.0. The 0.1.0 bootstrap
  checksums remain recorded as publication history, although current crates.io
  API lookups for the old names return HTTP 404. The published
  `asgi-lifespan-protocol-rs` 0.2.0 archive records `dirty: true`; its checksum
  and provenance must be handled explicitly before candidate assembly.
- The Python bridge still crosses into Python for ASGI applications. A
  Python-free FastAPI-RS/Starlette-RS composition reaches Rust application
  services directly and does not use `uvicorn-rs-py`.

## Verification

The required Rust build checks compile `uvicorn-rs` with default features and
with `http3` enabled. The Python adapter build confirms it uses the integrated
crate with HTTP/3 enabled. The package workflow inspects both Cargo archives
and builds the server archive as an external consumer. Protocol correctness,
coverage, and benchmark acceptance remain separate release gates.

## Alternatives considered

- **Keep the two project-owned H3 crates:** rejected because they are internal
  pieces of the same server, add publication order, and do not provide a
  separately requested user-facing product.
- **Keep HTTP/3 on by default:** rejected because it pulls Quinn and the H3
  implementation into every Rust application, including applications that
  need only TCP HTTP/1.1 or HTTP/2.
- **Move the lifecycle API into `uvicorn-rs`:** rejected because native
  frameworks should implement the lifecycle contract without depending on a
  particular server.
- **Make `uvicorn-rs` depend on a framework:** rejected because the server
  remains runtime-neutral and frameworks own routing and application
  semantics.
