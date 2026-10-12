# Rust-native FastAPI composition contracts

This directory preserves an input manifest and runner for a Python-free vertical
slice `fastapi-rs-native → Starlette-RS → uvicorn-rs`. The application,
server, protocol clients, and assertions were Rust. The case file is a
target-only contract manifest, not a Python ASGI parity suite. The referenced
`fastapi-rs-native` sibling crate is absent from the currently checked-out
source, so this example is not currently buildable.

The manifest currently covers HTTP/1.1 and HTTP/2 prior knowledge: path/query
routing, bodyless GETs without `Content-Length`, JSON request-body
consumption, request-body progress observed before the upload finishes over
both protocols, a pre-commit application error, response stream progress,
partial-upload disconnect handling over H1, a client-issued H2
`RST_STREAM(CANCEL)` after a partial upload, bounded slow-reader polling,
response-producer cancellation, and graceful drain over H1 and H2. The H2
upload-reset case checks that the app sees one request-body error without
cancelling its handler and that a sibling request succeeds on the same
connection. The H2 streaming-progress case sends a four-byte body prefix,
waits until the composed handler consumes it while the request remains open,
then sends the seven-byte suffix and verifies the 11-byte response. It does not
establish HTTP/3, TLS, WebSocket, lifespan, Python `module:app` compatibility,
or a performance gain.

The example resolves sibling `fastapi-rs` and `starlette-rs` development
checkouts by relative path. The command below is retained to reproduce the
archived result after the missing sibling crate is restored; it currently fails
because the referenced `fastapi-rs-native` manifest is absent:

```sh
cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml --locked -- examples/native-fastapi-contracts/manifest.json
```

The archived 17-input manifest passed three sequential repeats (51/51) on an
earlier dirty, path-linked sibling snapshot. The exact source identities,
three command logs, and normal dependency tree are recorded in the [H2
streaming-progress report](../../benchmarks/results/2026-10-12/native-fastapi-h2-streaming-composition/report.md).

That earlier snapshot used a server-neutral `fastapi-rs-native` crate with an
optional `uvicorn-rs` feature. Restore or recreate the crate, pin the source
checkouts, and rerun the manifest before this can be a release or CI acceptance
gate.
