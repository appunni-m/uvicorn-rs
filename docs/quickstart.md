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

The latest exact-source PR run, CI #618, passed 784/784 cases on Linux x86-64
and macOS ARM64. Windows passed 756/757 applicable cases, with zero behavior
mismatches and one stock-Uvicorn oracle shutdown timeout; its full candidate
artifact and consumer checks remain incomplete. The custom HTTP/WebSocket
protocol, `ssl_context_factory`, and response-capacity cases passed on all three
systems. This is not a completed three-platform release gate. The 0.3.0
distribution remains unpublished. See the
[compatibility status](uvicorn-compatibility.md) and
[support matrix](support-matrix.md) for scope and remaining gates. The
maintainer will perform the real-application trial after the repository
release gates are complete.
