# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status (2026-10-30)

The release target is a Python-free `uvicorn-rs` server crate with HTTP/3
behind `http3`, the separate `asgi-lifespan-protocol-rs` crate, and the PyPI
distribution `uvicorn-rs`. The optional `uvicorn-rs-py` package remains the
internal Cargo/PyO3 adapter. The publisher is `.github/workflows/release.yml`;
`.github/workflows/candidate.yml` verifies candidates. As of 2026-10-30,
crates.io serves `uvicorn-rs` 0.2.1 and `asgi-lifespan-protocol-rs` 0.2.1;
PyPI has no `uvicorn-rs` release. The current 0.2.2 source has no clean,
exact-source candidate or release tag yet. See [release status](docs/releases.md).

The latest full candidate/parity run, CI
[#489](https://github.com/appunni-m/uvicorn-rs/actions/runs/40999924044),
used an older source commit and did not pass all parity cases. Follow-up
Windows-only runs passed the six selected worker cases in
[#492](https://github.com/appunni-m/uvicorn-rs/actions/runs/41006402856) and
the TLS stream-drain case in
[#493](https://github.com/appunni-m/uvicorn-rs/actions/runs/41007521764).
Three selected Windows HTTP/3 cases passed in
[#495](https://github.com/appunni-m/uvicorn-rs/actions/runs/41008650687), but
the run recorded three Hypercorn log-file cleanup errors (Windows sharing
violations) after the requests passed. The current working change asks the
Hypercorn oracle to shut down gracefully on Windows; only those three cases
need rerunning to verify that cleanup path.
The latest full coverage measurement is still the earlier `main` report:
10,962/11,375 regions and 8,130/8,438 lines. It is not a measurement of the
current branch. Exact-source full coverage, independent Coverage-MCP review,
complete compatibility, candidate artifacts and consumers, and parity-first
benchmarks remain open. See [coverage evidence](docs/coverage.md),
[parity evidence](docs/parity.md), and
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
