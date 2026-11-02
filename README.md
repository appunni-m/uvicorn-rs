# uvicorn-rs

A Rust-first server for Python ASGI applications and Rust services.

## Release status — 2026-11-02

The planned Python distribution is **`uvicorn-rs`**. It provides the `uvicorn`
import namespace, `uvicorn` command, and `python -m uvicorn` entry point. The
optional internal Cargo/PyO3 adapter remains `uvicorn-rs-py`. The Rust release
contains one Python-free `uvicorn-rs` server crate with HTTP/3 behind the
optional `http3` feature, plus `asgi-lifespan-protocol-rs`.

The 0.3.0 candidate is not published. PR #21 tests develop head
87ab887b07c7d2f54b868dec16b115f93026ca69; its candidate artifacts identify
the clean merge source as a1e1f47b46be6e2c9419639baed02e71f2c41b75. CI #618
has completed. Its three-repeat unified matrix passed all 1,184 ASGI and 259
native cases per repeat, but failed the 100% coverage gate at 14,861/14,895
regions and 10,915/10,933 lines (34 regions and 18 lines missing). Linux
x86-64 and macOS ARM64 Uvicorn 0.54.0 parity each pass 784/784. Windows has
756/757 applicable cases pass, zero behavioral failures, and one stock-Uvicorn
two-worker shutdown-timeout infrastructure failure. Focused Windows run #619
passed that case 1/1, but the full Windows candidate artifact and consumer
checks remain incomplete. The custom HTTP/WebSocket protocol, `ssl_context_factory`,
and HTTP/1, HTTP/2, and WebSocket capacity cases passed on all three systems.
Linux and macOS candidate artifacts and clean consumers pass; the Linux bundle
contains the intended Cargo archives, the `uvicorn-rs` wheel, and sdist.
Documentation build #256 passed for the earlier PR source; the local docs
refresh still needs a hosted check, and deployment is skipped until merge.
Independent Coverage-MCP review and matched three-system FastAPI benchmarks
remain release gates. Existing partial measurements do not establish a general
performance advantage. See
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
