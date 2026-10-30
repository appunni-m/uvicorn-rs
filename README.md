# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status (2026-10-31)

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
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. CI
[#528](https://github.com/appunni-m/uvicorn-rs/actions/runs/41127272457)
completed on PR head `8a17d982a7b98a0074ab7e56acad4c508d9d2c73`. Linux
installed-wheel parity passed 718/718, and the Linux 0.2.2 candidate artifact
and clean consumers passed (artifact `13012012115`, SHA-256
`656ad0235e3ac25f1680966992e318dd6ce8cc8e0ba4011e242a6743ed13235`). Windows
candidate parity failed 688/691 with zero infrastructure failures; the three
failures concern two-worker shutdown and concurrency. macOS candidate artifact
checks were cancelled. The three-repeat coverage gate remains below 100% at
14,137/14,252 regions and 10,411/10,465 lines across 1,340 attributed cases.
Rust quality, MSRV, release-evidence checks, native
FastAPI-RS composition, and docs deployment #215 passed for head `8a17d98`.
The latest docs refresh still needs a documentation build and deployment.

All three Windows failures served HTTP 200. Their differences are in process
timeouts/exits and worker shutdown log counts; the signal ordering and root
cause remain unconfirmed. A focused oracle signal trace is committed locally
and will cover only the three failing inputs; it does
not change the parity expectations.

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
