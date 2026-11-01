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

Exact-source CI #586 tested pushed PR head d5f983c43615df5990abfc73fcfc73a3460a86c7 against main at 86e72e181d00feca1b4db7f30377d5d9d4345b83. Rust quality/docs, MSRV, the artifact/Coverage-MCP handoff contract, and pinned native FastAPI-RS composition passed. Linux x86-64 installed-wheel parity passed 755/755; its candidate artifact and consumer passed (artifact 13073349195, SHA-256 32c5f281febbe84bd7dda7b1017b2a6afa87667fee1e93a16e287a9eb6bd573b). macOS ARM64 parity passed 754/755; the sole failure was python-api.module-cli-worker-restarts-after-two-crashes, whose HTTP response and process results matched but whose target log included an extra 'client disconnected before response start' event. A focused native macOS run with the pending 15-second client-probe timeout passed this case 1/1; the updated input still needs hosted full-matrix validation. Windows x86-64 executed 682 cases: 678 passed, zero behavioral mismatches, 46 were not run, and four infrastructure failures occurred. They were candidate shutdown timeouts in the two-worker environment and SIGTERM cases, a Uvicorn oracle shutdown timeout in the explicit-worker case, and a Uvicorn oracle HTTP/1 upload abort (WinError 10053). Focused Windows run #587 on the same source passed both candidate worker cases; its oracle timeout trace showed no handler-entry event for one worker after CTRL_BREAK_EVENT while the parent waited for it. Only Linux artifact/consumer qualification passed. macOS and Windows candidate artifact/consumer checks remain open. Three-repeat unified coverage is still running.
The [completion plan](https://appunni-m.github.io/uvicorn-rs/maintainers/release-completion-plan/) records source identities, remaining gates, and focused receipts.

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
