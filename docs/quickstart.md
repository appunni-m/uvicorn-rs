# Run a Python ASGI app

This guide starts the example from a repository checkout. As of 2026-11-09,
version 0.3.3 is being prepared. The immutable `v0.3.2` candidate was not
published because its performance verifier looked for stock Uvicorn in the
candidate environment instead of the separate oracle environment. Check the
[release status](releases.md) before installing a registry version.

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

After `uvicorn-rs` 0.3.3 is available on PyPI:

```sh
python -m venv .venv-uvicorn-rs
. .venv-uvicorn-rs/bin/activate
python -m pip install "fastapi" "uvicorn-rs[standard]==0.3.3"
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

Exact-main CI [#746](https://github.com/appunni-m/uvicorn-rs/actions/runs/42508611884)
passed on commit `d0648cc0a4479b246dc7423b22a2b80f333d6193`. Installed-wheel
parity passed against Uvicorn 0.54.0 on Linux x86-64 and macOS ARM64 (786/786
cases each) and Windows x86-64 (759/759 applicable cases; 27 POSIX-only cases
are inapplicable). The candidate package and clean-consumer checks passed on
Linux, macOS, and Windows, including the CPython 3.9 wheel consumer. The unified
matrix passed all 1,453 cases through three ASGI and three native repeats, with
15,061/15,061 regions and 11,075/11,075 lines. An independent Coverage-MCP
receipt is not required; the exact-source raw report and its identities are
recorded in the CI artifact.

The matched ordinary-FastAPI benchmark [#371](https://github.com/appunni-m/uvicorn-rs/actions/runs/42503892704)
completed on the same commit across Linux x86-64, Linux ARM64, and macOS ARM64.
HTTP/1.1 validated-route results regressed; HTTP/2 and HTTP/3 results vary by
workload. This evidence supports no broad FastAPI speedup claim. The historical
Linux ARM64 upload timeout did not recur in the completed matrix or focused
trace, so its cause remains unknown and it is not claimed as fixed. See the
[compatibility status](uvicorn-compatibility.md) and [support matrix](support-matrix.md)
for scope and limitations. The maintainer will run their own real FastAPI
application trial after repository release qualification.
