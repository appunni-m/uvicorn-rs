# Rust-native FastAPI composition contracts

This directory preserves an input manifest and runner for a Python-free Rust
vertical slice `fastapi-rs → Starlette-RS → uvicorn-rs`. The native API lives
in the sole `fastapi-rs` crate; there is no separate `fastapi-rs-native`
behavior crate. The application, server, protocol clients, and assertions are
Rust. The case file is a target-only contract manifest, not Python ASGI parity
or full FastAPI compatibility evidence.

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

The example resolves sibling `fastapi-rs` and `starlette-rs` checkouts by
relative path. Build from a workspace containing the matching FastAPI-RS
native API and the Starlette-RS revision pinned by FastAPI-RS `metadata.yaml`.
The 17/17 local run used clean detached checkouts at the exact revisions and
manifest hashes recorded in the [composition evidence](../../docs/native-fastapi-composition.md):

```sh
cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml --locked -- examples/native-fastapi-contracts/manifest.json
```

To execute one manifest input while retaining the full manifest for shared
application configuration, append `--case-id <id>`. For example:

```sh
cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml --locked -- examples/native-fastapi-contracts/manifest.json --case-id http1.request-stream-progress-before-upload-complete
```

The runner rejects unknown or duplicate case IDs before opening a listener.

## Current mainline source check

FastAPI-RS main at `e5a6e91cb02b3229f9fbdfce1b00171c6913ccfe` now exports
`fastapi_rs::native` from the sole core crate. Its default features exclude
PyO3; the `python` feature enables it optionally. It pins Starlette-RS at
`4139a72449bf5751e8902fb1c7175ee7f191d338`.

On Uvicorn-RS `40b296ecd48cda884bd5b76a020c017c76ac8189` with clean detached
worktrees at those exact sibling revisions, the H1 request-stream-progress
input passed once and the locked normal/build dependency graph contained no
PyO3. This is a focused source check, not the full 17-input hosted matrix or
full FastAPI semantic compatibility. See the [source-bound evidence](../../docs/native-fastapi-composition.md).

The earlier 17-input result (51/51 across three repeats) used a now-removed
`fastapi-rs-native` crate and remains historical. The 17-input hosted result
uses the preserved FastAPI-RS feature-branch snapshot; it is not current-main
evidence. The mainline result above is one local source-bound repetition, not
hosted CI or a release gate. The native API covers a small Rust handler slice;
it does not claim Python FastAPI/Pydantic equivalence.
