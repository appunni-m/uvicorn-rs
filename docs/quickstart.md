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

PR #24 CI [#718](https://github.com/appunni-m/uvicorn-rs/actions/runs/42337079980)
passed installed-wheel Uvicorn 0.54.0 parity on Linux x86-64 (786/786), macOS
ARM64 (786/786), and Windows x86-64 (759/759 applicable cases). Candidate
packages and clean consumers passed on all three systems and on the CPython 3.9
floor. Unified coverage passed all 1,453 cases through three ASGI and three
native repeats at 15,061/15,061 regions and 11,075/11,075 lines, with a complete
Coverage-MCP review reporting zero gaps. This is PR-source evidence; exact-main
coverage and review must still bind to the final release commit.

The complete three-system benchmark [#364](https://github.com/appunni-m/uvicorn-rs/actions/runs/42325915265)
passed matrix validation on earlier source `e8b5d6b`. Ordinary-FastAPI HTTP/1.1
validated-route throughput is below Uvicorn on all six system/loop pairs, and
WebSocket text echo is slower; H2/H3 results vary by workload. It supports no
broad FastAPI speedup claim and cannot satisfy the exact-main benchmark gate.
Focused upload diagnostic [#365](https://github.com/appunni-m/uvicorn-rs/actions/runs/42340595289)
did not reproduce the historical HTTP/1 timeout or establish its cause. The
maintainer will perform the real-application trial after repository release
qualification. See the [compatibility status](uvicorn-compatibility.md) and
[support matrix](support-matrix.md) for current evidence.
