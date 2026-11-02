# Deployment guidance

The `uvicorn-rs` 0.3.0 PyPI release is still being qualified and is not
published. The latest exact-source PR run is CI
[#618](https://github.com/appunni-m/uvicorn-rs/actions/runs/41451660747), on
`develop` head `87ab887` and clean merge revision `a1e1f47`. Its Uvicorn 0.54.0
installed-wheel parity passed 784/784 on Linux x86-64 and macOS ARM64. Windows
passed 756/757 applicable cases with zero behavior mismatches and one
stock-Uvicorn oracle shutdown timeout; its candidate package and consumer
steps did not complete. The named custom HTTP/WebSocket protocol,
`ssl_context_factory`, and response-capacity cases passed on all three systems.
The unified coverage matrix completed three repeats of 1,184 ASGI and 259
native cases, but the 100% gate failed at 14,861/14,895 regions and
10,915/10,933 lines. Independent Coverage-MCP review and matched FastAPI
benchmarks remain release gates. Use the
[support matrix](support-matrix.md) to check the tested surface, then evaluate
the released candidate with your application before deploying it.

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

The Python CLI includes Uvicorn-style worker and reload controls. The
maintained parity matrix checks process startup, request serving, shutdown,
worker replacement, reload, signal handling, and socket cases against Uvicorn
0.54.0 on every platform-applicable input. Windows excludes 27 inputs that
require Unix-domain sockets, inherited POSIX descriptors, a Unix-only listener
transfer, or POSIX-only worker signals and health checks. See the
[compatibility evidence](uvicorn-compatibility.md) for the exact run and the
[support matrix](support-matrix.md) for remaining untested combinations. Keep
an upstream rollback environment available during your application trial.

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

Frameworks that expose a standard ASGI 3 application can be tried with the
candidate. The maintained parity matrix uses Uvicorn 0.54.0 as its reference;
it does not replace an application-specific trial or the official ASGI
conformance suite. Follow the [FastAPI evaluation guide](fastapi-evaluation.md)
and consult [ASGI support](support-matrix.md) before deployment.
