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
not yet implemented. A few exposed defaults still have behavior gaps, which
are called out in the table. Where a parity receipt checks only startup
diagnostics, that limit is stated in the option description.

| Option | Default | Description |
| --- | --- | --- |
| module:attribute | Required | Import a module attribute, including nested attributes. CLI commands search the current working directory; `--app-dir` prepends a chosen directory. The application can also come from `UVICORN_APP`. |
| --host HOST | 127.0.0.1 | TCP bind host and, when TLS is enabled, QUIC bind host. |
| --port PORT | 8000 | TCP/QUIC port; zero asks the OS to select a port. |
| --backlog INTEGER | 2048 | Set the pending TCP connection queue in the Rust listener. A live module-CLI parity case uses a non-default value and completes an HTTP request. The operating system may clamp the requested queue size; this does not configure QUIC. |
| --timeout-keep-alive INTEGER | 5 | Close an idle persistent HTTP/1.0 or HTTP/1.1 connection after this many seconds. A focused module-CLI parity case sets one second, waits two seconds, and confirms the same connection is closed. HTTP/2 and HTTP/3 connections are unaffected. |
| --http {auto,h11,httptools,zttp} | auto | Selects the Rust-native HTTP engine. `auto`, `h11`, and `httptools` use HTTP/1.1; `zttp` uses HTTP/1.1 unless paired with `--http2`. The adapter does not import or depend on zttp. Parser-specific malformed-request behavior is not established. |
| --http2 | Disabled | Enables HTTP/2 over TLS ALPN and cleartext prior knowledge when `--http zttp` is selected, matching Uvicorn's opt-in setting while using the Rust protocol implementation. A local aggregate run passed all 27 maintained HTTP/2 parity cases against Uvicorn 0.54.0 with zttp 0.0.34 on macOS ARM64 and CPython 3.12.13; the HTTP/2 category benchmark and hosted release evidence remain pending. |
| --ws auto | auto | `auto`, `websockets-sansio`, `wsproto`, and legacy `websockets` are accepted and route to the native WebSocket implementation. Focused selector cases cover diagnostics and text/binary exchange; they do not establish complete backend parity. |
| --ws-per-message-deflate BOOL | true | When enabled, negotiates `permessage-deflate` if offered by the client; `false` disables negotiation. Focused Python API parity cases verify compressed text echo with normal close and verify the disabled setting. A selected raw-frame comparison also verifies one fragmented compressed text message is reassembled and delivered as one ASGI event. Other extension parameter combinations and full backend parity remain unverified. |
| --ws-max-queue INTEGER | 32 | `auto`, `websockets-sansio`, and `wsproto` do not consume this backend-specific setting. The legacy `websockets` selector passes it to a bounded native ASGI receive-message channel. One live `--ws-max-queue 1` case delays the ASGI reader and verifies three messages arrive before a normal close. The Rust bound counts complete messages; upstream `websockets` applies its high-water mark to frames, so other thresholds, fragmented-message behavior, and flow-control timing remain unverified. |
| --ws-ping-interval SECONDS | 20.0 | Send server-initiated WebSocket Ping frames at this interval. A non-positive value disables pings. An infinite positive interval, NaN, or a value beyond Rust's `Duration` range is treated as never firing; use `None` or zero to disable pings explicitly. The Rust driver sends a four-byte payload and schedules the next ping after a matching Pong. |
| --ws-ping-timeout SECONDS | 20.0 | Close the WebSocket with code 1011 and reason `keepalive ping timeout` when the peer does not return the matching Pong before the deadline. `None` through `uvicorn.run()` or `uvicorn_rs.Server` disables the timeout; a negative value is an immediate timeout after the first Ping; NaN is treated as unbounded. Positive infinity or a finite timeout beyond Rust's `Duration` range is unbounded. Focused Python API parity cases verify the negative, NaN, and unbounded timeout behavior against Uvicorn 0.54.0. |
| --workers INTEGER | `WEB_CONCURRENCY` or 1 | Explicit `0` and `1` use one process; `WEB_CONCURRENCY=0` also selects one process. Focused module-CLI comparisons verify two workers serve a live HTTP/1.1 request and stop on SIGINT with either `--workers 2` or `WEB_CONCURRENCY=2`. Separate cases verify replacement after one worker exits and after a POSIX worker stops answering health checks. Repeated failure policy, dynamic worker-count signals, and other socket/platform combinations remain unverified. |
| --timeout-worker-healthcheck SECONDS | 5 | Controls worker health checks when the multi-process supervisor restarts workers. A live `Config`/`Server` case checks a non-default value with `workers=1`; a focused POSIX module-CLI case uses a 2-second timeout and compares replacement after an unresponsive worker against Uvicorn. Windows health-check behavior and repeated failures remain unverified. |
| --interface {auto,asgi3,asgi2,wsgi} | auto | ASGI 3 is the default. ASGI 2 is adapted to ASGI 3, and WSGI is adapted through Uvicorn's WSGI middleware. Focused requests cover both ASGI 2 and WSGI selection. WSGI `lifespan="auto"` fallback behavior is compared through `uvicorn.run()` and the module CLI, including configured logging. Focused POST cases cover finite request bodies and chunked transfer bodies with one, two, and 64 data chunks through uvicorn.run() and the module CLI. WSGI application-factory serving is covered through both entry points. A pre-response WSGI application exception has focused parity through both entry points; errors after response start and other failure classes remain unverified. Large or streaming uploads, response backpressure, and other response-iterator patterns also remain unverified; the delayed response-iterator handshake covers first-byte delivery only. |
| --loop {none,auto,asyncio,uvloop,zuvloop} | auto | Select the Python event loop. `none` uses the default asyncio loop; `auto` uses uvloop when installed, otherwise asyncio. `zuvloop` requires its optional package. A `module:factory` value loads a custom event-loop factory. Tokio remains the Rust network runtime. |
| --log-config PATH | Built-in Uvicorn config | Load a `.ini`, `.json`, or `.yaml` logging configuration. All three formats have focused parity through `uvicorn.run()` and `python -m uvicorn`; the module CLI also reads `UVICORN_LOG_CONFIG`. YAML requires PyYAML, included in the `[standard]` extra. |
| --log-level {critical,error,warning,info,debug,trace} | info | Set the server and application log threshold. Warning-level filtering has focused parity through the module CLI and `uvicorn.run()`; `UVICORN_LOG_LEVEL=debug` and an explicit `--log-level warning` overriding that environment value have focused module CLI parity. Other levels and environment combinations remain unverified. |
| --access-log/--no-access-log | Enabled | Enable or suppress request access events. `--no-access-log` and `uvicorn.run(access_log=False)` have focused parity cases. |
| --use-colors/--no-use-colors | Automatic | Force or disable ANSI colors in default server and access logs. Focused module CLI comparisons exercise both switches, and `use_colors=True` is compared through `uvicorn.run()`, observing color sequences in captured logs. |
| --lifespan {auto,on,off} | auto | `off` prevents the app from receiving ASGI lifespan events. This behavior has focused live parity on macOS ARM64 / CPython 3.12.13. Focused API and module CLI cases verify that an app exception before startup under `on` leaves the server unstarted and exits with code 3. Other strict-mode failure classes remain unverified. |
| --app-dir PATH | Current directory | Add a directory to the application import path. |
| --env-file PATH | Unset | Load application environment variables before importing the app. One focused CLI parity case confirms a pre-existing process value wins over the same key in the file. Requires `python-dotenv`, included in the `[standard]` extra. CLI and programmatic factory behavior have focused parity cases. |
| --root-path PATH | Empty | Set `scope["root_path"]` and prefix `scope["path"]`. Preserve `scope["raw_path"]` as the original HTTP path bytes, excluding the query string and configured prefix. Focused HTTP/1.1 contract inputs cover ASCII prefixes through the API and module CLI, plus a Unicode prefix, and check all three scope values against ASGI expectations. Uvicorn 0.54.0 includes the prefix in `raw_path`, so response-body parity is not claimed for those cases. |
| --header NAME:VALUE | None | Add a default response header. HTTP/1.1 parity covers a value containing a colon and repeated identical `--header` options preserving duplicate values; `uvicorn.run` accepts equivalent `headers=[("Name", "value")]` pairs in a focused API case. |
| --server-header/--no-server-header | Enabled | Include or omit the default `Server: uvicorn` response header. The disabled behavior is covered by the focused header-policy case. |
| --date-header/--no-date-header | Enabled | Include or omit the default `Date` response header. The disabled behavior is covered by the focused header-policy case. |
| --reset-contextvars | Off | Run each HTTP request in a fresh empty `contextvars.Context`. Focused HTTP/1.1 parity inputs compare default inheritance and reset behavior, and `uvicorn.run(reset_contextvars=True)` verifies the public Python API against Uvicorn 0.54.0. Lifespan and WebSocket calls keep their existing context behavior. |
| --factory | Off | Call the imported application with no arguments. |
| --ssl-certfile PATH | Unset | PEM certificate chain. Supply it together with --ssl-keyfile to enable TLS and experimental HTTP/3. |
| --ssl-keyfile PATH | Unset | PEM private key paired with --ssl-certfile. |
| --ssl-keyfile-password TEXT | Unset | Password for a PKCS#8 `ENCRYPTED PRIVATE KEY` PEM. Traditional encrypted PEM formats have not been qualified. |
| --ssl-version INTEGER | `ssl.PROTOCOL_TLS_SERVER` | The default allows TLS 1.2 and 1.3. `ssl.PROTOCOL_TLSv1_2` restricts TCP HTTPS to TLS 1.2; QUIC keeps TLS 1.3 as required by HTTP/3. TLS 1.0 and 1.1 remain unsupported by Rustls. |
| --ssl-cert-reqs INTEGER | `ssl.CERT_NONE` | Selects client-certificate policy: `CERT_NONE`, `CERT_OPTIONAL`, or `CERT_REQUIRED`. When a CA bundle is provided, presented client certificates are verified against it. |
| --ssl-ca-certs PATH | Unset | PEM trust bundle for verifying client certificates when `--ssl-cert-reqs` requests client authentication. |
| --timeout-graceful-shutdown SECONDS | None | Maximum time to drain active work. The default `None` has no deadline, matching Uvicorn; an explicit value bounds the drain. A focused parity case verifies the default can wait more than 10 seconds for lifespan shutdown. |
| --limit-concurrency INTEGER | Unset | Return HTTP 503 when active connections or request tasks reach this limit. Focused HTTP/1.1 comparisons verify limit 1 through the CLI, `uvicorn.run()`, and `Config` with `Server.run()`; other limits and protocols remain unverified. |

For a custom INI, JSON, or YAML logging file, pass its path at the command line
or through the Python API:

~~~sh
uvicorn examples.hello_asgi:app --log-config logging.json
~~~

~~~python
import uvicorn

uvicorn.run("examples.hello_asgi:app", log_config="logging.json")
~~~

Without certificate and key files, the prototype accepts cleartext HTTP/1.1 and HTTP/2 prior knowledge. With both files, TLS uses ALPN for HTTP/1.1 and HTTP/2; experimental HTTP/3 uses QUIC. Protocol and lifecycle cases are listed in the [support matrix](support-matrix.md).

Ctrl-C and SIGTERM request shutdown. By default the prototype runs ASGI lifespan startup before serving and lifespan shutdown after draining or cancelling active work. With `--lifespan off`, it skips calling the application with a lifespan scope while HTTP scopes still receive an empty `state` mapping. The Python API accepts the same setting as `uvicorn.run(app, lifespan="off")` or `Config(app, lifespan="off")`.

The same root-path setting is available through `uvicorn.run(app,
root_path="/mounted")` and `--root-path /mounted`. Focused HTTP/1.1 contract
cases verify the resulting `root_path`, prefixed `path`, and original request
`raw_path`. The ASGI HTTP scope defines `raw_path` as the original HTTP path
component bytes, excluding the query string, so it does not include a
configured `root_path`. Uvicorn 0.54.0 adds that prefix to `raw_path`; the
contract cases check uvicorn-rs against the ASGI scope expectations and compare
only exit code, response receipt, shutdown signal, and timeout state with
Uvicorn. Uvicorn also rejects a
Unicode prefix before the ASGI app runs. Other protocols remain unverified.
See the [support matrix](support-matrix.md) and
[maintainer evidence](maintainers/uvicorn-0.54.0-contract.md).

Programmatic default response headers use `(name, value)` pairs, for example
`uvicorn.run(app, headers=[("X-Application", "example")])`. Focused API
parity cases verify delivery of a configured header and the order of duplicate
values.

`uvicorn.Config(app, env_file=".env")` and `uvicorn.run(app,
env_file=".env")` load the file before importing an application string or
calling its factory. The `uvicorn-rs[standard]` extra will include
`python-dotenv` after the PyPI distribution is published. For this source
checkout, install it into the active development environment with
`uv pip install python-dotenv`. The focused cases cover CLI and `uvicorn.run`
factory startup; other dotenv syntax and precedence combinations remain
unverified.

WebSocket keepalive uses the same `ws_ping_interval` and `ws_ping_timeout`
settings exposed by Uvicorn. A live CLI parity case verifies a server Ping, a
matching Pong, a second Ping, and the timeout close against Uvicorn 0.54.0.
It uses a 0.1-second interval and 0.3-second timeout. Focused Python API cases
also verify that a zero interval leaves an active connection usable after
idle, and that a negative timeout closes with code 1011 before an application
message is delivered. Two additional API cases match Uvicorn with a timeout of
`1e300` and an interval encoded as `1e9999` (positive infinity), respectively.
The oversized timeout remains unbounded; the interval case confirms that the
connection remains usable after idle but does not inspect Ping-frame emission.
Other timer values remain unverified.

## Python API

The `uvicorn` compatibility namespace provides the pinned `Config`, `Server`,
and `run` signatures. The basic single-process ASGI 3 server path uses the Rust
network runtime. Other `Config` settings still have compatibility gaps:

~~~python
import uvicorn

uvicorn.run("examples.hello_asgi:app", host="127.0.0.1", port=8000)
~~~

`--log-level` accepts `critical`, `error`, `warning`, `info`, `debug`, and
`trace`. The Python API also accepts integer logging levels through
`uvicorn.Config` and `uvicorn.run`. Focused comparisons verify the warning
threshold through `python -m uvicorn` and `uvicorn.run(..., log_level=30)`, and
verify `UVICORN_LOG_LEVEL=debug` and explicit warning-over-debug environment
precedence through the module CLI; they do not establish every level or
environment combination. Custom INI, JSON, and YAML
logging configurations are compared through both `uvicorn.run(log_config=...)`
and `python -m uvicorn --log-config ...`. YAML requires PyYAML, included in the
`[standard]` extra.
Access logging is enabled by default. Use `--no-access-log` or
`uvicorn.run(app, access_log=False)` to suppress request access events. Focused
comparisons cover both entry points.

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
