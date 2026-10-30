# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status (2026-10-30)

The release target is a Python-free `uvicorn-rs` server crate with HTTP/3
behind `http3`, the separate `asgi-lifespan-protocol-rs` crate, and the PyPI
distribution `uvicorn-rs`. The optional `uvicorn-rs-py` package remains the
internal Cargo/PyO3 adapter. The publisher is `.github/workflows/release.yml`;
`.github/workflows/candidate.yml` verifies candidates. No package or tag has
been published from this consolidated source. See
[release status](docs/releases.md).

The latest completed candidate checks are from CI
[#486](https://github.com/appunni-m/uvicorn-rs/actions/runs/40982217403),
which tested prior PR head `8d64ab95c5ec756e47459061fa6d5e73491397b5` against
`main` at `86e72e181d00feca1b4db7f30377d5d9d4345b83`. Linux installed-wheel
parity passed 718/718; macOS ARM64 candidate parity passed 718/718. Linux
candidate wheel/sdist, clean-consumer checks, and Python-free Cargo package
checks passed. Windows parity was incomplete: 684/689 executed cases passed,
with worker shutdown failures, infrastructure failures, and a TLS oracle
failure. The Windows consumer lane did not complete.

The current PR head includes a focused shutdown-order fix and parity log
normalization; two selected multi-worker cases pass locally on macOS ARM64.
The hosted coverage run on the prior head did not produce a report before this
follow-up, so exact-source 100% coverage and independent Coverage-MCP review
remain open. Those CI results are bound to the prior source. Full
Windows/Uvicorn compatibility, clean candidate artifacts and consumers for
every supported platform, and the matched benchmarks remain release gates.
Benchmark work follows parity. See
[coverage evidence](docs/coverage.md), [parity evidence](docs/parity.md), and
[replacement status](docs/uvicorn-compatibility.md).

The Python adapter is **not yet a drop-in Uvicorn replacement**. If your
application depends on Uvicorn's full command-line, Python API, worker, or
reload behavior, keep using upstream Uvicorn for now.

The consolidated `uvicorn-rs` crate provides a Rust library, not a standalone
server executable. Cargo publication does not qualify the Python adapter or
complete the project's release gates. See
[release status](docs/releases.md).

The PyPI distribution is named `uvicorn-rs`, following the project's
`pillow-rs` naming convention, and is pending its first release. It provides
the `uvicorn` command and import namespace after the compatibility and release
gates pass. The root Cargo/PyO3 integration package remains named
`uvicorn-rs-py` internally and is not published as the PyPI distribution. The
source checkout exposes these command and import names, but only selected
paths have been compared with Uvicorn 0.54.0; broad CLI, Python API, and
process-behavior parity remains unverified. See
[replacement status](docs/uvicorn-compatibility.md) for the tested surface
and remaining gaps.

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
