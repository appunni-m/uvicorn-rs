# CLI and Python API

The HTTP/3 task-reaping source passes all 451 instrumented attribution cases
and three complete repeats with zero failures, infrastructure errors, retries
or cases not run. The matrix has 214 oracle comparisons and 237 target-only
contracts across 70 input files and 63 operations. Native coverage is
4,778/4,778 regions and 3,371/3,371 lines with zero unfiltered MCP gaps.
The restored normal build passes 214/214 public comparisons and all 15
exclusion checks with three selected live cases. See
[the current source/build receipt](coverage.md#current-full-verification-451-cases).
Passing 448-case results below belong to the earlier shared-write source
identified in [the coverage record](coverage.md#current-full-verification-448-cases);
they do not attest the changed checkout.

## CLI

The executable is `uvicorn-rs`. It imports an object by `module:attribute` and
serves that ASGI application:

```sh
uv run uvicorn-rs examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

| Argument | Default | Meaning |
|---|---|---|
| `module:app` | required | Import `module` and retrieve the named attribute. The object must be an ASGI callable; application factories are not invoked automatically. |
| `--host HOST` | `127.0.0.1` | TCP bind host and the address used for the QUIC endpoint when TLS is enabled. |
| `--port PORT` | `8000` | TCP and QUIC port in the range `0`–`65535`. |
| `--loop {asyncio,uvloop}` | `asyncio` | Python event-loop implementation used for the application. `uvloop` must be installed separately. Tokio remains the Rust network runtime. |
| `--certfile PATH` | unset | PEM certificate chain. Must be supplied together with `--keyfile`; enables TLS for TCP and QUIC. |
| `--keyfile PATH` | unset | PEM private key for `--certfile`. |
| `--graceful-timeout SECONDS` | `10` | Non-negative integer grace period, in seconds, used for the bounded shutdown stages. |

TLS TCP advertises HTTP/2 and HTTP/1.1 using ALPN. QUIC serves experimental
HTTP/3 on the same port. Without certificate/key files, the server accepts
cleartext HTTP/1.1 and HTTP/2 prior-knowledge (h2c). It does not support h2c
upgrade.

Ctrl-C and SIGTERM initiate shutdown. The server runs ASGI lifespan startup
before serving and lifespan shutdown after draining/cancelling active work.
Exact protocol and shutdown coverage is tracked in the
[support matrix](support-matrix.md).

## Python API

The `uvicorn_rs.Server` class can be embedded into a Python program:

```python
import asyncio

from uvicorn_rs import Server


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"hello"})


asyncio.run(Server(app, host="127.0.0.1", port=8000).serve())
```

`Server(app, host="127.0.0.1", port=8000, certfile=None, keyfile=None,
graceful_timeout=10)` exposes the same server options. Call `serve()` from the
event loop that should own the ASGI application. Cancelling its task requests
graceful shutdown and then propagates cancellation after the native shutdown
stages finish. Transport drain, request cleanup, lifespan shutdown, and lifespan
cleanup use separate windows, so total shutdown time can exceed
`graceful_timeout`. Python code that suppresses cancellation or exceeds a
cleanup window can remain unfinished; the server reports that condition.
See [shutdown ownership and stages](architecture.md#shutdown-ownership-and-stages).

The native runtime rejects a timeout beyond its supported monotonic deadline
range with `ValueError` before listeners or application tasks start. The exact
maximum depends on the platform's monotonic clock representation.

HTTP response and WebSocket acceptance headers have finite compiled storage
capacity inherited from the pinned `http::HeaderMap` implementation. It is not
a configurable option or a fixed public maximum number of accepted headers:
distinct names, duplicate values, and reserved handshake fields consume
capacity differently. Valid sufficiently large ASGI header collections can
exceed it. Fallible header assembly rejects excess capacity through the error
channel. Both target-only support cases passed the historical shared-write 448-case attribution
and all three full repeats, plus the same source's selected normal-build audit.
These declared capacity contracts are separate from the 213 public oracle
comparisons. See the [source/build receipt](coverage.md#current-full-verification-448-cases) and
[support matrix](support-matrix.md).

The class currently has no documented hot-reload, worker, or reconfiguration
API. It is a local source API; the project has not published a wheel or source
distribution.

The parity input's `close_error_code` controls its HTTP/3 test client. It adds
no server configuration option. Typed `H3_NO_ERROR` (`0x100`) is a clean peer
close; other acceptance errors keep their existing error path.
The sequence input's optional `h3_grease` boolean also controls only the test
client and defaults to `true`. The maintained 128-response workflow explicitly
uses `false`, supported by its selected instrumented public A/B; it adds no
server setting. The held-response accept-error workflow is a target-only
instrumented contract, not an application or deployment option. See
[the current workflow contracts](parity.md#current-http3-workflows).
