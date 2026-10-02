# CLI and Python API

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
| `--graceful-timeout SECONDS` | `10` | Time to drain active work after shutdown begins before remaining Python tasks are cancelled. |

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
graceful shutdown and then propagates cancellation after native cleanup.

The class currently has no documented hot-reload, worker, or reconfiguration
API. It is a local source API; the project has not published a wheel or source
distribution.
