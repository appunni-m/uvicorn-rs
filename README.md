# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status (2026-11-01)

The target release is a Python-free `uvicorn-rs` server crate with HTTP/3
behind `http3`, the separate `asgi-lifespan-protocol-rs` crate, and the PyPI
distribution `uvicorn-rs`. The optional internal Cargo/PyO3 adapter remains
`uvicorn-rs-py`; the PyPI package provides the `uvicorn` imports and command.
`.github/workflows/release.yml` publishes, while `candidate.yml` verifies
artifacts. Both crates.io Trusted Publisher entries and the PyPI publisher are
already configured. A read-only registry check on 2026-11-01 confirmed both
Cargo crates at 0.2.1 and no PyPI `uvicorn-rs` release. The 0.3.0 candidate is
not release-qualified.
See [release status](https://appunni-m.github.io/uvicorn-rs/releases/).

The latest hosted [CI #583](https://github.com/appunni-m/uvicorn-rs/actions/runs/41272503277)
checks PR #19 at `e0eb4e4989509d0c8a0adac5de78c256f625b4b0` against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. Installed-wheel public parity
passed 755/755 on Linux x86-64 and macOS ARM64. Windows x86-64 passed 727/728;
the only failure was the HTTP/1 upload-arrival parity case. Rust quality, MSRV,
and native FastAPI-RS composition passed. The macOS candidate artifact and
consumer passed; the Linux candidate build stopped before compilation when
the Rust toolchain download timed out. Unified coverage is still running, and
the local deterministic upload-fixture correction awaits hosted Windows
validation. The [completion plan](https://appunni-m.github.io/uvicorn-rs/maintainers/release-completion-plan/)
records source identities, remaining gates, and focused receipts.

The Python package is **not yet a drop-in Uvicorn replacement**. Keep using
upstream Uvicorn if your application relies on the full Uvicorn command-line,
Python API, worker, reload, or process-control contract. Benchmarks remain
behind complete parity; the existing Linux ARM64 HTTP/3 benchmark is incomplete
and does not establish a general speed gain. See [coverage evidence](https://appunni-m.github.io/uvicorn-rs/coverage/),
[parity evidence](https://appunni-m.github.io/uvicorn-rs/parity/), [replacement status](https://appunni-m.github.io/uvicorn-rs/uvicorn-compatibility/),
and [benchmark evidence](https://appunni-m.github.io/uvicorn-rs/benchmark-results/).

## Try the current prototype

From a development checkout with `uv`, CPython 3.12, and a Rust toolchain
installed:

```sh
uv sync --python 3.12
uv run uvicorn examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl -i http://127.0.0.1:8000/
```

You should receive HTTP 200 and a text body beginning with `GET / 1.1`. This
checkout command is for evaluating the prototype; it does not mean the package
is published or Uvicorn-compatible. See [the quickstart](https://appunni-m.github.io/uvicorn-rs/quickstart/)
and [current options](https://appunni-m.github.io/uvicorn-rs/configuration/).

## What to expect

Python applications still execute on their Python event loop, and Python
application code remains subject to the GIL. Current measurements do not show
a general performance advantage over Uvicorn for Python ASGI applications;
see the [benchmark results](https://appunni-m.github.io/uvicorn-rs/benchmark-results/).

Rust applications can use the Python-free `uvicorn-rs` library. The server is
independent of Starlette-RS and FastAPI-RS; those frameworks do not need it as
a runtime dependency. See [native Rust integration](https://appunni-m.github.io/uvicorn-rs/native-fastapi-composition/).

## Documentation

- [Run a Python ASGI app](https://appunni-m.github.io/uvicorn-rs/quickstart/)
- [Install, replace, or roll back Uvicorn](https://appunni-m.github.io/uvicorn-rs/uvicorn-compatibility/)
- [ASGI and protocol support](https://appunni-m.github.io/uvicorn-rs/support-matrix/)
- [Deployment guidance](https://appunni-m.github.io/uvicorn-rs/deployment/)
- [Benchmark results and evidence limits](https://appunni-m.github.io/uvicorn-rs/benchmark-results/)

For contributing, security reporting, support expectations, architecture, and
release information, see [CONTRIBUTING.md](https://github.com/appunni-m/uvicorn-rs/blob/main/CONTRIBUTING.md), [SECURITY.md](https://github.com/appunni-m/uvicorn-rs/blob/main/SECURITY.md),
[SUPPORT.md](https://github.com/appunni-m/uvicorn-rs/blob/main/SUPPORT.md), and the [documentation site](https://appunni-m.github.io/uvicorn-rs/).

The project is not affiliated with the Uvicorn project. It is available under
[BSD-3-Clause or MIT](https://github.com/appunni-m/uvicorn-rs/blob/main/LICENSE), at your option.
