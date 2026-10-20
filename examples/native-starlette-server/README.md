# Uvicorn-RS + Starlette-RS native HTTP prototype

This executable composes the Python-free `uvicorn-rs` server with
Starlette-RS's native `Tower::Service` application. It does not import Python,
construct ASGI dictionaries, or make Starlette-RS depend on Uvicorn-RS.

The example exercises streamed request-body consumption, path/query access,
streamed response frames, an application error before response commitment, and
a response-body error after commitment. This executable currently opens a
cleartext HTTP/1.1 listener. The reusable server library also exposes
`serve_tls` for HTTP/1.1 and HTTP/2 selected by ALPN, and an HTTP/3 entry point
for a caller-configured Quinn endpoint. The live contract manifest verifies
those paths with a test-only certificate. WebSocket transport is not
implemented. Native application-lifecycle hooks are not ASGI lifespan support
and are not consumed by this example.

## Run it

The local workspaces are expected side by side under a common `work/`
directory so the example's relative path dependency can resolve. This is a
local cross-worktree prototype; its Starlette-RS source is not pinned to a
committed revision yet because the current native service implementation is
still uncommitted in that repository. The reproducible, pinned multi-repository
example remains an open acceptance item in Kata issue `wb4y`.

From the Uvicorn-RS repository root:

```sh
cargo run --manifest-path examples/native-starlette-server/Cargo.toml --locked -- 127.0.0.1:8080
```

Send a request with a streamed body:

```sh
curl --http1.1 --no-buffer -X POST --data-binary 'hello' \
  'http://127.0.0.1:8080/items/7?lang=en'
```

The body is `id=7;query=lang=en;body=hello`. The endpoint stores the incoming
`Bytes` frame handles, then moves them into response frames; it does not copy
the body payload while crossing the Starlette service boundary. It does buffer
the request explicitly in the example handler before responding.

The `/fail` route returns an application error before headers; the server maps
it to an empty 500 response. The `/body-error` route commits a 200 response,
sends `partial-response`, and then terminates the body stream with an error.

Stop the process with Ctrl-C to exercise the server's graceful connection
drain. This prototype has no current-source Starlette composition or performance
receipt. The reusable Rust server's maintained native contract inventory and
latest evidence are summarized in the
[ASGI and native-server evidence record](../../docs/maintainers/asgi-support-evidence.md);
those contracts are separate from this example.
It has separate input-driven socket contracts for
disconnect during a partial HTTP/1.1 upload, a slow HTTP/1.1 response reader,
a dropped HTTP/2 response body, and HTTP/2 graceful drain. The upload case sends 7 bytes against a
declared 1 MiB body, confirms the service consumed the prefix, closes the
client, observes the body-stream error and application-future cleanup, and
checks that a follow-up request succeeds. The slow-reader case checks that
fewer than 512 of 2,048 generated frames are polled during the observation
interval and that disconnect drops the body producer. The HTTP/2 reset case
checks that dropping one response body drops its producer and leaves the same
connection able to serve a follow-up request. A separate HTTP/2 slow-reader
case applies the same 64 MiB/32 KiB/200 ms polling bound, then resets the stream
and checks producer cleanup and follow-up health on that connection. These
cases do not exercise the Starlette composition. The prototype has no
performance evidence.

Run the core contract inputs separately with:

```sh
cargo run -p uvicorn-rs --example native_core_contracts --locked -- tests/native-core/manifest.json
```

The maintained native contract inventory and its current validation status are
recorded in the [ASGI and native-server evidence record](../../docs/maintainers/asgi-support-evidence.md).
The core cases verify that `ConnectionInfo` in each request's extensions
reports the TCP peer address over HTTP/1.1 and HTTP/2, reports no TLS metadata
for cleartext, and exposes negotiated `http/1.1` or `h2` ALPN on TLS sessions.
Input-only error contracts also verify that readiness, service, and committed
response-body failures retain their original `io::Error` type and message in
the opt-in observer, along with the peer address, over HTTP/1.1; an HTTP/2
service-failure case verifies the same error boundary. These are target-only
core contracts, not ASGI or Uvicorn parity cases.
