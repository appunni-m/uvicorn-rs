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

The public FastAPI-RS `main` resolved to
`0afccce9f35447f38ebb5e94d0e67fd338ea7ea4` on 2026-10-25. It exports
`fastapi_rs::native` from the sole core crate, excludes PyO3 from its default
features, and pins Starlette-RS at
`4139a72449bf5751e8902fb1c7175ee7f191d338`.

The current local composition evidence uses clean detached checkouts at those
exact FastAPI-RS and Starlette-RS revisions and runs 17 distinct H1/H2 inputs
once each against the dirty Uvicorn-RS draft. The locked normal/build dependency
graph contains no PyO3. Receipt paths, hashes, and limits are recorded in the
[source-bound composition evidence](../../docs/native-fastapi-composition.md).
This is local evidence, not hosted acceptance, repeated acceptance, or full
FastAPI semantic compatibility.

### Earlier selected route receipts

The following route receipts used FastAPI-RS `2756140f0a5fad750d11120b668e3bf5899fa102`
and Starlette-RS `4139a72449bf5751e8902fb1c7175ee7f191d338`; they are historical
and do not update the current-main evidence above. On the dirty Uvicorn-RS draft
based on `86e72e181d00feca1b4db7f30377d5d9d4345b83`, the H2
`http2.path-query-routing` case passed once with no PyO3 in the locked graph.
Its receipt is `target/kata-progress/native-composition-h2-isolated/receipt.json`
(SHA-256 `14f0e0620074b80e805fdaa7ef0a1bca5f1de4aee429a4079f1100f96e1be7e8`).
The H1 `http1.path-query-routing` case also passed once for
`GET /items/42?tag=green`; its receipt is
`target/kata-progress/native-composition-h2-isolated/h1-path-query-routing-receipt.json`
(SHA-256 `f6232b730071886d116f2a2dad7e291ae8b5968180e08e848475d9d5f2de138e`).
The other 15 manifest inputs passed once each; the batch receipt is
`target/kata-progress/native-composition-h2-isolated/remaining-15-cases-receipt.json`
(evidence ID `fd9a40b9335a42e081c785de`; SHA-256
`0eebcccdd1c00093916cd2f7452cd670d07cf3b9bf46086ef090321a2f43874a`).

The earlier 17-input result (51/51 across three repeats) used a now-removed
`fastapi-rs-native` crate and remains historical. The 17-input hosted result
uses the preserved FastAPI-RS feature-branch snapshot; it is not current-main
evidence. The mainline result above is one local source-bound repetition, not
hosted CI or a release gate. The native API covers a small Rust handler slice;
it does not claim Python FastAPI/Pydantic equivalence.
