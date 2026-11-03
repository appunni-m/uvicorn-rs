# uvicorn-rs

A Rust-first server for Python ASGI applications and Rust services.

## Packages and release availability

The Python distribution is **`uvicorn-rs`**. It provides the `uvicorn`
import namespace, `uvicorn` command, and `python -m uvicorn` entry point. The
optional internal Cargo/PyO3 adapter remains `uvicorn-rs-py`. The Rust release
contains one Python-free `uvicorn-rs` server crate with HTTP/3 behind the
optional `http3` feature, plus `asgi-lifespan-protocol-rs`.

Check the [release guide](docs/releases.md) for registry availability, exact
candidate identities and remaining acceptance gates. The
[compatibility evidence](docs/uvicorn-compatibility.md) records the tested
Uvicorn 0.54.0 inputs, platform/Python profiles and any separate acceptance
for a reference defect. Use accepted release artifacts for an application
trial; a source build or a successful job alone does not establish release
readiness. See the [benchmark results](docs/benchmark-results.md) for measured
workloads and regressions; they do not promise an improvement for your app.

## Try the source checkout

For a source preview, install `uv`, CPython 3.12, and Rust 1.85 or newer, then
run from the repository root:

```sh
uv sync --python 3.12
uv run uvicorn examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

In another terminal, request the example:

```sh
curl -i http://127.0.0.1:8000/
```

The response should have status `200` and a text body beginning with
`GET / 1.1`. Press Ctrl-C in the server terminal to request shutdown.

## Install for a FastAPI trial

After version 0.3.0 is published, create a clean environment for the candidate
and install its standard dependencies:

```sh
python -m venv .venv-uvicorn-rs
. .venv-uvicorn-rs/bin/activate
python -m pip install "uvicorn-rs[standard]==0.3.0"
python -m uvicorn myapp.main:app --host 127.0.0.1 --port 8000
```

Use a separate environment for upstream Uvicorn. Both distributions install
the `uvicorn` import namespace. The [FastAPI evaluation guide](docs/fastapi-evaluation.md)
describes a matched trial setup and rollback steps.

## What to expect

Python applications still run on their Python event loop and remain subject
to the GIL. The completed benchmark evidence does not yet establish a general
FastAPI performance advantage over Uvicorn. Rust applications can use the
Python-free `uvicorn-rs` library without depending on Starlette-RS or
FastAPI-RS at runtime; see [native Rust integration](docs/native-fastapi-composition.md).

## Documentation

- [Quickstart](docs/quickstart.md)
- [Install, replace, or roll back Uvicorn](docs/uvicorn-compatibility.md)
- [ASGI and protocol support](docs/support-matrix.md)
- [Configuration](docs/configuration.md)
- [Deployment guidance](docs/deployment.md)
- [FastAPI trial guide](docs/fastapi-evaluation.md)
- [Benchmark results and evidence limits](docs/benchmark-results.md)
- [Release gates](docs/releases.md)

For contribution, security, and support information, see
[CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[SUPPORT.md](SUPPORT.md).

The project is not affiliated with the Uvicorn project. It is available under
[BSD-3-Clause or MIT](LICENSE), at your option.
