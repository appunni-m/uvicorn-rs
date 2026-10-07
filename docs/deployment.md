# Deployment and framework integration

uvicorn-rs is an experimental single-process ASGI server. It loads an
importable module:attribute; it does not create application factories,
supervise workers, reload code, or configure proxy headers. The project has not
published a package. Build and install a wheel into the same environment as the
application and its Python dependencies.

## Start an application

```sh
uv run uvicorn-rs myapp.asgi:app --host 127.0.0.1 --port 8000
```

Run the command from a directory where myapp.asgi is importable. For a
service, set WorkingDirectory and PYTHONPATH explicitly. The default bind
address is loopback; choose a public or private interface deliberately.

Supplying both --certfile and --keyfile enables TLS on TCP and experimental
HTTP/3 on QUIC, on the configured port. TLS TCP advertises HTTP/2 and HTTP/1.1
through ALPN. The TLS private key must be readable by the service account. The
server has no separate flag to disable QUIC while retaining TLS.

The current CLI and its defaults are listed in the
[configuration reference](configuration.md#cli).

## Service-manager example

This example shows the documented process boundary for a Linux systemd
service. A Linux CI job is configured to exercise the installed wheel under a
transient systemd service and check the manager's stop path. The persistent
unit below is an example; CI does not install it into a host.

```ini
[Unit]
Description=Python ASGI application served by uvicorn-rs
After=network.target

[Service]
Type=exec
User=asgi
Group=asgi
WorkingDirectory=/srv/myapp
Environment=PYTHONPATH=/srv/myapp
ExecStart=/srv/myapp/.venv/bin/uvicorn-rs myapp.asgi:app --host 0.0.0.0 --port 8000 --graceful-timeout 10
Restart=on-failure
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

The TLS configuration also binds UDP for HTTP/3, so firewall rules must account
for both TCP and UDP on the configured port. TimeoutStopSec should leave
enough time for the server's separate transport, request, lifespan, and cleanup
stages plus application cleanup. These stages can make total shutdown longer
than --graceful-timeout; an application that suppresses cancellation can
outlive a cleanup window. The 60-second example is not a measured guarantee
for every application.

The installed-wheel check exercises module:app, an HTTP/1.1 request over TLS,
and POSIX SIGTERM while an ASGI request is held. It requires that the request
is cancelled, lifespan shutdown completes, and the process exits within five
seconds in that probe. The separate Linux CI check is configured to start the
exact installed wheel as a transient systemd service, send the manager's stop
request, and check request cancellation, lifespan completion, and successful
bounded exit.

To run the same service-manager probe on a Linux systemd host, first install
the exact candidate wheel into the Python environment used to invoke the
script, then run:

```sh
"$WORK/upstream-starlette/bin/python" "$ROOT/scripts/probe_systemd_deployment.py" \
  --wheel "$SERVER_WHEEL" --output "$WORK/systemd.json"
```

This requires `systemd-run`, `systemctl`, `journalctl`, and passwordless
`sudo -n` access to the system service manager. It creates a uniquely named
transient service, stops it in cleanup, and writes a receipt only after the
manager stop, held-request cancellation, lifespan shutdown, and exit checks
pass. It does not install or modify the persistent unit shown above.
The persistent unit example, launchd, container orchestration, and Windows
service-manager behavior are not directly tested.

Applications should provide their own readiness and health routes. There is no
built-in health endpoint, worker supervisor, restart policy, or log collector.
Use the service manager for process restart and log capture; configure TLS
certificate renewal outside the server.

## Test Starlette integrations

The black-box integration probe uses one shared application fixture and runs
it through both Uvicorn and an installed uvicorn-rs wheel. For each framework
environment, it compares lifespan state, HTTP request and response streaming,
background work, the HTTP 500 response from an application exception, and a
WebSocket handshake/subprotocol/text echo. Its JSON receipt records Python,
framework, server and native-extension identities, the complete observations,
and shutdown outcomes.

Use separate environments for upstream Starlette and starlette-rs-py. Both
distributions install a top-level starlette package; installing them
together can leave overlapping package files and make the selected framework
ambiguous. Neither distribution is a runtime dependency of uvicorn-rs.

Build the candidate and the pinned framework wheel:

```sh
ROOT=$PWD
WORK=$(mktemp -d /tmp/uvicorn-rs-integration.XXXXXX)
mkdir -p "$WORK/wheels"

uvx --from maturin==1.14.1 maturin build --release --locked \
  --interpreter .venv/bin/python --out "$WORK/wheels"
SERVER_WHEEL=$(find "$WORK/wheels" -maxdepth 1 -name 'uvicorn_rs-*.whl' -print -quit)

git init "$WORK/starlette-rs"
git -C "$WORK/starlette-rs" remote add origin https://github.com/appunni-m/starlette-rs.git
git -C "$WORK/starlette-rs" fetch --depth 1 origin 738c43362938896c268ca29b9a9a2a5942df510c
git -C "$WORK/starlette-rs" checkout --detach FETCH_HEAD
(
  cd "$WORK/starlette-rs"
  env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="--cap-lints warn" \
    uvx --from maturin==1.14.1 maturin build --release --locked \
    --interpreter "$ROOT/.venv/bin/python" --out "$WORK/wheels"
)
FRAMEWORK_WHEEL=$(find "$WORK/wheels" -maxdepth 1 -name 'starlette_rs_py-*.whl' -print -quit)
```

Install and run the upstream Starlette comparison:

```sh
uv venv --python 3.12 "$WORK/upstream-starlette"
uv pip install --python "$WORK/upstream-starlette/bin/python" \
  "$SERVER_WHEEL" "uvicorn[standard]==0.54.0" "starlette==1.6.0"
"$WORK/upstream-starlette/bin/python" "$ROOT/scripts/probe_starlette_rs.py" \
  --framework starlette --server-wheel "$SERVER_WHEEL" \
  --output "$WORK/upstream-starlette.json"
```

Install and run the separate starlette-rs comparison:

```sh
uv venv --python 3.12 "$WORK/starlette-rs-env"
uv pip install --python "$WORK/starlette-rs-env/bin/python" \
  "$SERVER_WHEEL" "uvicorn[standard]==0.54.0" "$FRAMEWORK_WHEEL"
"$WORK/starlette-rs-env/bin/python" "$ROOT/scripts/probe_starlette_rs.py" \
  --framework starlette-rs --server-wheel "$SERVER_WHEEL" \
  --framework-wheel "$FRAMEWORK_WHEEL" --output "$WORK/starlette-rs.json"
```

The probe uses the shared HTTP API subset implemented by both frameworks.
At the pinned starlette-rs revision, WebSocketRoute is not part of its
supported API, so the fixture handles its WebSocket scope with a plain ASGI
branch. That case validates the server's WebSocket transport and ASGI boundary;
it does not claim starlette-rs framework-level WebSocket route compatibility.
The results are selected integration evidence, not full framework or official
ASGI conformance.

The normal installed-wheel CI job is configured to build the pinned
starlette-rs wheel, run both isolated framework comparisons, compare their
receipts, and exercise the transient systemd stop path on Linux. A successful
hosted run for the current revision is still required before treating those CI
checks as evidence. The manual category workflow also runs the
starlette-rs comparison before performance sampling. See
[the support matrix](support-matrix.md#framework-and-deployment-evidence) for
the current recorded results and limits.

The pinned starlette-rs snapshot denies an `unused_mut` lint that is emitted
for its Linux build. The command caps lint severity only for this optional
third-party integration wheel; the uvicorn-rs build keeps its normal lint
settings, and the framework source is not modified.
