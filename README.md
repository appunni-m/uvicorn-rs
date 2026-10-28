# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status

The `asgi-lifespan-protocol-rs` and `uvicorn-rs` 0.2.1 crates are published
to crates.io from clean source commit
`d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`. Their checksums and provenance
are recorded in [release status](docs/releases.md). The PyPI distribution
`uvicorn-rs` has not had its first upload.

PR #19 is a draft at head
`4a429684d5fd92c1068c7776093452cca1ccfc90`. CI
[#455](https://github.com/appunni-m/uvicorn-rs/actions/runs/40652026006)
passed the installed-wheel public parity matrix **702/702** on Linux x86-64
and passed the Rust, native-composition, and release-handoff jobs. Its unified
coverage job failed: one of three parity repeats hit a timing-sensitive fault
contract, and the report measured 13,801/13,983 regions and 10,165/10,263
lines. Two focused local fault-contract cases now pass 1/1 each: the shutdown
event-ordering case and `fault.asgi-event-type.extract`, whose fixture now
reaches the intended injected error. These selected cases do not establish
full coverage; an exact-source 100% report and accepted independent
Coverage-MCP review remain open. The same 702-case matrix passed locally on
macOS ARM64 at the PR head; that is local evidence, not a hosted receipt. The
dirty worktree adds two WebSocket event-context cases, one HTTP/2 Early Hints
validation case, and two HTTP/2 response-trailer validation cases. These
selected groups pass 5/5 against Uvicorn and the target, but the full 707-case
set has not run on this source. Full Uvicorn compatibility, complete matched
benchmarks, and hosted exact-source candidate consumers remain open. No 0.2.2
release tag or package has been published.

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
