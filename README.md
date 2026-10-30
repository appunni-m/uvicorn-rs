# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status (2026-10-30)

The target release is a Python-free `uvicorn-rs` server crate with HTTP/3
behind `http3`, the separate `asgi-lifespan-protocol-rs` crate, and the PyPI
distribution `uvicorn-rs`. The optional internal Cargo/PyO3 adapter remains
`uvicorn-rs-py`; the PyPI package provides the `uvicorn` imports and command.
`.github/workflows/release.yml` publishes, while `candidate.yml` verifies
artifacts. Both crates.io Trusted Publisher entries and the PyPI publisher are
already configured. crates.io currently lists both Cargo crates at 0.2.1;
PyPI has no `uvicorn-rs` release. The 0.2.2 candidate is not release-qualified.
See [release status](docs/releases.md).

PR #19 is still a draft against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. Its latest full run,
[#514](https://github.com/appunni-m/uvicorn-rs/actions/runs/41064798064),
passed Linux and macOS installed-wheel parity at 718/718 cases each. The
Windows lane reported four failures among 691 cases; its candidate consumer
steps were skipped. The unified three-repeat report measured 14,118/14,243
regions and 10,402/10,461 lines, below the required 100% gate. Rust quality,
MSRV, and native FastAPI-RS composition passed.

A later focused Windows diagnostic,
[#522](https://github.com/appunni-m/uvicorn-rs/actions/runs/41078744177),
passed one worker-precedence case on diagnostic commit `42f9c0f`. Its corrected
trace showed listener accept polls pending until shutdown cancellation, then
both workers drained. The earlier timeout did not reproduce, so this selected
pass does not establish full Windows parity or a confirmed root cause.

The Python package is **not yet a drop-in Uvicorn replacement**. Keep using
upstream Uvicorn if your application relies on the full Uvicorn command-line,
Python API, worker, reload, or process-control contract. Benchmarks remain
behind complete parity; the existing Linux ARM64 HTTP/3 benchmark is incomplete
and does not establish a general speed gain. See [coverage evidence](docs/coverage.md),
[parity evidence](docs/parity.md), [replacement status](docs/uvicorn-compatibility.md),
and [benchmark evidence](docs/benchmark-results.md).

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
is published or Uvicorn-compatible. See [the quickstart](docs/quickstart.md)
and [current options](docs/configuration.md).

## What to expect

Python applications still execute on their Python event loop, and Python
application code remains subject to the GIL. Current measurements do not show
a general performance advantage over Uvicorn for Python ASGI applications;
see the [benchmark results](docs/benchmark-results.md).

Rust applications can use the Python-free `uvicorn-rs` library. The server is
independent of Starlette-RS and FastAPI-RS; those frameworks do not need it as
a runtime dependency. See [native Rust integration](docs/native-fastapi-composition.md).

## Documentation

- [Run a Python ASGI app](docs/quickstart.md)
- [Install, replace, or roll back Uvicorn](docs/uvicorn-compatibility.md)
- [ASGI and protocol support](docs/support-matrix.md)
- [Deployment guidance](docs/deployment.md)
- [Benchmark results and evidence limits](docs/benchmark-results.md)

For contributing, security reporting, support expectations, architecture, and
release information, see [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[SUPPORT.md](SUPPORT.md), and the [documentation site](https://appunni-m.github.io/uvicorn-rs/).

The project is not affiliated with the Uvicorn project. It is available under
[BSD-3-Clause or MIT](LICENSE), at your option.
