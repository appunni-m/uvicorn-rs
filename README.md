# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status

The 2026-10-27 registry audit recorded Cargo 0.2.1 releases from the earlier
crate layout. The maintainer has since reported removing the old `uvicorn-rs`
crate entry. A current crates.io API check from this environment returned
HTTP 403, so the registry's current state is not independently confirmed;
the release workflow must resolve it in its preflight. The PyPI
`uvicorn-rs` project API returned 404, so the distribution has not had its
first upload. See [release status](docs/releases.md).

PR #19 remains a draft. CI #457 checked source commit
`4f7a29635d7b14151be02b409515f0cf290f7b5c`, based on `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`; its receipts do not cover later
commits. In CI
[#457](https://github.com/appunni-m/uvicorn-rs/actions/runs/40672760253), the
release-handoff, native framework composition, minimum-Rust, and Rust
formatting/lint/feature/documentation jobs have passed. The installed-wheel
public parity job passed 707/707 cases on Linux x86-64 with zero failures or
infrastructure errors; its artifact is
[retained by CI](https://github.com/appunni-m/uvicorn-rs/actions/runs/40672760253/artifacts/12809014899).
The exact-source three-repeat coverage job is still running, so no current
coverage result is available. Documentation deploy
run [#174](https://github.com/appunni-m/uvicorn-rs/actions/runs/40672760286)
passed.

The prior-head CI run [#456](https://github.com/appunni-m/uvicorn-rs/actions/runs/40668578840)
passed 707/707 public parity cases on Linux x86-64 for commit
`1c5a9a7fca45e6e4e985cf775ef844bc1fd37e83`; that result does not cover the
current head. Its coverage job was canceled when the new source run started.
The independent Coverage-MCP receipt, full OS/Python Uvicorn compatibility
matrix, parity-first benchmark evidence, and hosted exact-commit candidate
consumers remain open. No 0.2.2 release tag or package has been published.

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
