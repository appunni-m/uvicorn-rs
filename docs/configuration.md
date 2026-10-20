# Configure the Rust server and Python compatibility API

This page describes the current source-checkout interfaces. The `uvicorn`
namespace now exposes the Uvicorn 0.54.0 `run`, `Config`, and `Server` call
signatures, with serving routed through the Rust engine. Runtime compatibility
is still partial; see [Uvicorn replacement status](uvicorn-compatibility.md)
before relying on an option or API behavior.

## CLI

~~~sh
uv run uvicorn examples.hello_asgi:app --host 127.0.0.1 --port 8000
~~~

The CLI recognizes the pinned Uvicorn option names. The options below are the
current accepted subset; other explicitly selected settings are rejected as
not yet implemented. Where a parity receipt checks only startup diagnostics,
that limit is stated in the option description.

| Option | Default | Description |
| --- | --- | --- |
| module:attribute | Required | Import a module attribute, including nested attributes. The application can also come from `UVICORN_APP`. |
| --host HOST | 127.0.0.1 | TCP bind host and, when TLS is enabled, QUIC bind host. |
| --port PORT | 8000 | TCP/QUIC port; zero asks the OS to select a port. |
| --http auto | auto | Accepted and uses the native HTTP default. The focused parity case checks missing-app startup diagnostics only; request-level backend parity is not established. Explicit backend selections are rejected. |
| --ws auto | auto | Accepted and uses the native WebSocket default. The focused parity case checks missing-app startup diagnostics only; handshake and backend selection parity are not established by this CLI case. Explicit backend selections are rejected. |
| --workers {0,1} | Unset | Explicit `0` and `1` are accepted and use the existing single process. Other worker counts are rejected; process supervision is not implemented. Current CLI parity cases check startup diagnostics, not worker lifecycle behavior. |
| --timeout-worker-healthcheck SECONDS | 5 | Accepted with the single-process CLI path. Uvicorn uses this timeout only in its multi-process supervisor, so it has no effect with one worker. Multi-worker mode is not implemented. |
| --interface {auto,asgi3} | auto | ASGI 3 applications are supported. Explicit `asgi2` and `wsgi` selections are rejected. |
| --loop {auto,asyncio,uvloop,zuvloop} | auto | Select the Python event loop. `auto` uses uvloop when installed, otherwise asyncio. Tokio remains the Rust network runtime. |
| --lifespan {auto,on,off} | auto | `off` prevents the app from receiving ASGI lifespan events. This behavior has focused live parity on macOS ARM64 / CPython 3.12.13. Strict `on` failure behavior for apps without lifespan support is not yet verified. |
| --app-dir PATH | Current directory | Add a directory to the application import path. |
| --env-file PATH | Unset | Load application environment variables before importing the app. Requires `python-dotenv`, included in the `[standard]` extra. CLI and programmatic factory behavior have focused parity cases. |
| --root-path PATH | Empty | Prefix `scope["path"]` and `scope["raw_path"]`, and set `scope["root_path"]`. Focused parity covers an ASCII prefix on HTTP/1.1. |
| --header NAME:VALUE | None | Add a default response header. The CLI has an HTTP/1.1 parity case for a value containing a colon; `uvicorn.run` accepts the equivalent `headers=[("Name", "value")]` pairs, verified by a focused API case. |
| --server-header/--no-server-header | Enabled | Include or omit the default `Server: uvicorn` response header. The disabled behavior is covered by the focused header-policy case. |
| --date-header/--no-date-header | Enabled | Include or omit the default `Date` response header. The disabled behavior is covered by the focused header-policy case. |
| --factory | Off | Call the imported application with no arguments. |
| --ssl-certfile PATH | Unset | PEM certificate chain. Supply it together with --ssl-keyfile to enable TLS and experimental HTTP/3. |
| --ssl-keyfile PATH | Unset | PEM private key paired with --ssl-certfile. |
| --timeout-graceful-shutdown SECONDS | None | Maximum graceful shutdown time. The current native adapter applies a 10-second timeout when omitted. |

Without certificate and key files, the prototype accepts cleartext HTTP/1.1 and HTTP/2 prior knowledge. With both files, TLS uses ALPN for HTTP/1.1 and HTTP/2; experimental HTTP/3 uses QUIC. Protocol and lifecycle cases are listed in the [support matrix](support-matrix.md).

Ctrl-C and SIGTERM request shutdown. By default the prototype runs ASGI lifespan startup before serving and lifespan shutdown after draining or cancelling active work. With `--lifespan off`, it skips calling the application with a lifespan scope while HTTP scopes still receive an empty `state` mapping. The Python API accepts the same setting as `uvicorn.run(app, lifespan="off")` or `Config(app, lifespan="off")`.

The same root-path setting is available through `uvicorn.run(app,
root_path="/mounted")` and `--root-path /mounted`. The parity cases verify the
resulting `root_path`, prefixed `path`, and prefixed `raw_path` for HTTP/1.1.
Other protocols and non-ASCII prefixes remain unverified.

Programmatic default response headers use `(name, value)` pairs, for example
`uvicorn.run(app, headers=[("X-Application", "example")])`. Focused API
parity cases verify delivery of a configured header and the order of duplicate
values.

`uvicorn.Config(app, env_file=".env")` and `uvicorn.run(app,
env_file=".env")` load the file before importing an application string or
calling its factory. Install `uvicorn-rs-py[standard]` to include
`python-dotenv`. The focused cases cover CLI and `uvicorn.run` factory startup;
other dotenv syntax and precedence combinations remain unverified.

## Tokio blocking-pool limit

The optional UVICORN_RS_MAX_BLOCKING_THREADS environment variable sets the maximum size of Tokio's blocking pool. If unset, Tokio uses its default. The value must be a positive integer; malformed values and zero fail server initialization. This setting does not change the Tokio core worker count, and it is not a Uvicorn option.

## Python API

The `uvicorn` compatibility namespace provides the pinned `Config`, `Server`,
and `run` signatures. The basic single-process ASGI 3 server path uses the Rust
network runtime. Other `Config` settings still have compatibility gaps:

~~~python
import uvicorn

uvicorn.run("examples.hello_asgi:app", host="127.0.0.1", port=8000)
~~~

For an application-owned event loop, construct the server explicitly:

~~~python
import asyncio
import uvicorn

config = uvicorn.Config(app, host="127.0.0.1", port=8000)
server = uvicorn.Server(config)
asyncio.run(server.serve())
~~~

The lower-level `uvicorn_rs.Server` API remains available for Rust-server
integration:

~~~python
import asyncio

from uvicorn_rs import Server


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"hello"})


asyncio.run(Server(app, host="127.0.0.1", port=8000).serve())
~~~

Call `serve()` from the event loop that should own the application. Cancelling
the task requests shutdown, waits for cleanup, then propagates
`asyncio.CancelledError`. The Uvicorn-shaped API currently supports the
single-process ASGI 3 TCP path and selected TLS, factory, loop, and graceful
shutdown settings, including the focused `lifespan="off"` case. Matching
signatures do not imply that every Uvicorn setting is implemented.

## Not available in the current prototype

The compatibility API does not yet implement the complete Uvicorn settings,
logging, socket, interface-selection, reload, worker, or process-supervision contracts.
Unsupported runtime options must be checked against the
[compatibility matrix](uvicorn-compatibility.md); use upstream Uvicorn when
your application depends on an unqualified feature.
