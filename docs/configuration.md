# Configure the current prototype

This page documents the checkout's current uvicorn-rs-py command and Python API. It is not the future Uvicorn-compatible reference. The current command does not provide all Uvicorn options; see [Uvicorn replacement status](uvicorn-compatibility.md).

## CLI

~~~sh
uv run uvicorn-rs-py examples.hello_asgi:app --host 127.0.0.1 --port 8000
~~~

The current options are:

| Option | Default | Description |
| --- | --- | --- |
| module:attribute | Required | Import the module and retrieve the named object. The object must be an ASGI 3 callable. Factories are not invoked. |
| --host HOST | 127.0.0.1 | TCP bind host and, when TLS is enabled, QUIC bind host. |
| --port PORT | 8000 | TCP/QUIC port; zero asks the OS to select a port. |
| --loop {asyncio,uvloop} | asyncio | Python event loop for the ASGI application. Install uvloop separately to use it. Tokio remains the Rust network runtime. |
| --certfile PATH | Unset | PEM certificate chain. Supply it together with --keyfile to enable TLS and experimental HTTP/3. |
| --keyfile PATH | Unset | PEM private key paired with --certfile. |
| --graceful-timeout SECONDS | 10 | Non-negative integer grace period for transport and request cleanup. |

Without certificate and key files, the prototype accepts cleartext HTTP/1.1 and HTTP/2 prior knowledge. With both files, TLS uses ALPN for HTTP/1.1 and HTTP/2; experimental HTTP/3 uses QUIC. Protocol and lifecycle cases are listed in the [support matrix](support-matrix.md).

Ctrl-C and SIGTERM request shutdown. The prototype runs ASGI lifespan startup before serving and lifespan shutdown after draining or cancelling active work.

## Tokio blocking-pool limit

The optional UVICORN_RS_MAX_BLOCKING_THREADS environment variable sets the maximum size of Tokio's blocking pool. If unset, Tokio uses its default. The value must be a positive integer; malformed values and zero fail server initialization. This setting does not change the Tokio core worker count, and it is not a Uvicorn option.

## Python API

The current checkout exposes uvicorn_rs.Server:

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

Call serve from the event loop that should own the application. Cancelling its task requests shutdown, waits for cleanup, then propagates asyncio.CancelledError. Startup, bind, application, and lifespan failures propagate to the caller.

## Not available in the current prototype

The current checkout does not provide the uvicorn command, uvicorn imports, the upstream run/Config/Server API, application factories, Uvicorn environment settings, reload, worker processes, or the full Uvicorn socket and protocol option set. These are compatibility goals, not current features. Use upstream Uvicorn if you need them today.
