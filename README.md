# uvicorn-rs

A Rust-first server for Python ASGI applications and Rust services.

## Release status — 2026-11-02

The planned Python distribution is **`uvicorn-rs`**. It provides the `uvicorn`
import namespace, `uvicorn` command, and `python -m uvicorn` entry point. The
optional internal Cargo/PyO3 adapter remains `uvicorn-rs-py`. The Rust release
contains one Python-free `uvicorn-rs` server crate with HTTP/3 behind the
optional `http3` feature, plus `asgi-lifespan-protocol-rs`.

The 0.3.0 candidate is not published yet. PR #21's exact-source CI #615 on
`develop` commit `c28474a164cce437cf41ec12d7ebd789027f8637` passed the
maintained Uvicorn 0.54.0 installed-wheel parity matrix: 784/784 on Linux
x86-64, 784/784 on macOS ARM64, and 757/757 applicable cases on Windows
x86-64. The Linux, macOS, and Windows candidate artifact consumers and the
Python 3.9 wheel-floor check also passed. The docs deployment passed before
the current page refresh; the refreshed pages still need a docs build and
deployment. The latest hosted coverage run (#615) completed below its gate at
14,860/14,894 regions and 10,915/10,933 lines, with six startup-lifespan fault
contracts failing. A focused local fix makes those faults one-shot, and the six
selected cases now pass; a full exact-source coverage run is still required.
Independent Coverage-MCP review and matched three-system FastAPI benchmarks
also remain release gates. Existing partial measurements do not establish a
general performance advantage. See
[release status](docs/releases.md) and the [compatibility matrix](docs/support-matrix.md).

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
