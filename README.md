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

PR #19 remains a draft. CI
[#466](https://github.com/appunni-m/uvicorn-rs/actions/runs/40807137734)
checked committed head `51c6e4920644d1a4e6fdd9f9ae9571ec8d2d7e61`, based on
`main` at `86e72e181d00feca1b4db7f30377d5d9d4345b83`. Rust quality/MSRV,
native FastAPI-RS composition, release handoff, and the installed-wheel public
parity matrix passed 717/717 on Linux x86-64 and macOS ARM64. Windows stopped
before cases because its oracle dependency check still required `uvloop`, which
is unavailable on that platform. The unified three-repeat coverage matrix
attributed all 1,071 cases but missed the 100% gate: 13,962/14,134 regions and
10,290/10,377 lines. Linux and macOS candidate jobs built their artifacts, but
the identity recorder failed because the pinned `maturin` executable was not
on PATH; Linux clean-consumer checks passed, and the macOS candidate wheel
passed 717/717 parity. Local working-tree fixes make `uvloop` platform-specific
and resolve the pinned Maturin version through `uvx`; these fixes still need
one hosted exact-source run. See [CI #466](https://github.com/appunni-m/uvicorn-rs/actions/runs/40807137734),
[coverage evidence](docs/coverage.md), and [parity evidence](docs/parity.md).

Docs run
[#183](https://github.com/appunni-m/uvicorn-rs/actions/runs/40807137733)
passed for the then-committed source. Independent Coverage-MCP acceptance, full
Uvicorn 0.54.0 compatibility across the declared OS/Python matrix, the hosted
candidate artifact bundle and clean consumers, and parity-first benchmark
evidence remain open. No 0.2.2 release tag or package has been published.

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
