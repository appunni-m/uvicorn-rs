# Run a Python ASGI app

This guide starts the example from a repository checkout. The `uvicorn-rs`
0.3.0 PyPI release is still being qualified; the tested candidate is not
published yet.

## Start the checked-out example

Install `uv`, CPython 3.12, and Rust 1.85 or newer. From the repository root,
install the locked development environment and start the example:

```sh
uv sync --python 3.12
uv run uvicorn examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

The server binds to loopback, so only this machine can connect. In another
terminal, send a request:

```sh
curl -i http://127.0.0.1:8000/
```

Expect status `200` and a text body beginning with `GET / 1.1`. Press Ctrl-C
in the server terminal to request shutdown.

## Run your own FastAPI app after release

Create an environment that contains your application dependencies and the
candidate server, but not upstream Uvicorn. Both distributions provide files
under the `uvicorn` import name, so keep them in separate environments.

After `uvicorn-rs` 0.3.0 is available on PyPI:

```sh
python -m venv .venv-uvicorn-rs
. .venv-uvicorn-rs/bin/activate
python -m pip install "fastapi" "uvicorn-rs[standard]==0.3.0"
python -m uvicorn myapp.main:app --host 127.0.0.1 --port 8000
```

Replace `myapp.main:app` with your application's `module:attribute`. If the
application uses a factory, add `--factory`:

```sh
python -m uvicorn myapp.main:create_app --factory --host 127.0.0.1 --port 8000
```

The [FastAPI evaluation guide](fastapi-evaluation.md) describes how to compare
the same application and dependencies with stock Uvicorn, collect operational
measurements, and restore upstream Uvicorn.

## Compatibility evidence

PR #24 CI [#716](https://github.com/appunni-m/uvicorn-rs/actions/runs/42310334382)
passed installed-wheel Uvicorn 0.54.0 parity, candidate consumers and unified
coverage at 100% regions and lines for synthetic merge source
`f8d25698b98e630e9d77e7da1bbc670c9ebb0fd4`. An accepted Coverage-MCP review is
bound to that PR source; final-main CI and a new final-source review remain
required. The full matched benchmark is incomplete after a Linux ARM64 HTTP/3
Hypercorn reference timeout. Current-source diagnostic
[#363](https://github.com/appunni-m/uvicorn-rs/actions/runs/42323833577) did not
reproduce the historical HTTP/1 upload timeout and is not performance evidence.
Final main-source candidate verification and PyPI publication remain pending.
See the [compatibility status](uvicorn-compatibility.md) and
[support matrix](support-matrix.md) for the current gates. The maintainer will
perform the real-application trial after repository release gates are complete.
