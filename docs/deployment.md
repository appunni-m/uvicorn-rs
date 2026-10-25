# Deployment guidance

The current Python ASGI client is an unpublished `uvicorn-rs` PyPI distribution
prototype, not a supported Uvicorn replacement. Keep upstream Uvicorn for
deployments that need its full CLI, worker, reload, proxy, or process-management
behavior. This guide is for evaluating the current checkout in a controlled
environment.

## Bind and run

The default bind address is `127.0.0.1`, which accepts connections only from
the same machine. To test from another machine, select an address deliberately
and restrict access with your network controls:

```sh
uv run uvicorn myapp.asgi:app --host 0.0.0.0 --port 8000
```

Start the command from a directory where `myapp.asgi` can be imported, or set
`PYTHONPATH` to include the application directory. The current command accepts
only the options listed in the [configuration guide](configuration.md).

## Process management

For experiments, run the server under a process manager so it can capture
logs, restart the process, and request shutdown. Run it as a dedicated
unprivileged user and set the working directory and `PYTHONPATH` explicitly.

The Python CLI has a multi-process supervisor when `--workers` is greater than
one. Selected parity cases on macOS ARM64 verify two-worker startup, request
serving, SIGINT shutdown, replacement after one worker exits, and replacement
after a POSIX worker stops answering health checks. The health-check case uses
a 2-second timeout and confirms both Uvicorn and this checkout log a worker
replacement, serve a request, and shut down cleanly. The server does not
provide a health endpoint. Repeated restart policy, worker-count signals,
reload filters, startup-failure handling, and broader platform and socket
combinations remain unverified. See the
[support matrix](support-matrix.md) before relying on multi-process behavior.
Use upstream Uvicorn when your deployment depends on unverified worker or
reload behavior.

The current prototype handles Ctrl-C and SIGTERM and has a configurable
`--timeout-graceful-shutdown`. Allow additional process-manager shutdown time for
application cleanup. This timeout does not qualify arbitrary applications or
host shutdown behavior.

## TLS and network ports

Provide both `--ssl-certfile` and `--ssl-keyfile` to enable TLS on TCP. TLS advertises
HTTP/1.1 and HTTP/2 through ALPN. The current prototype also enables
experimental HTTP/3 on QUIC using the same configured port, so a firewall must
allow both TCP and UDP when using this mode. The private key must be readable
by the server's service account. See the [support matrix](support-matrix.md)
for protocol limits.

## Frameworks

Frameworks that expose a standard ASGI 3 application can be tried through the
prototype. Selected integration cases have been exercised, but this is not a
claim of full compatibility with every Starlette, FastAPI, or ASGI feature.
See [ASGI support](support-matrix.md) and [Uvicorn replacement status](uvicorn-compatibility.md).
