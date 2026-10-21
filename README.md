# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status

The experimental Rust crates are published on crates.io as version `0.1.0`;
the Python adapter is not published on PyPI. The Python adapter is **not yet a
drop-in Uvicorn replacement**. If your application depends on Uvicorn's full command-line,
Python API, worker, or reload behavior, keep using upstream Uvicorn for now.

The published Cargo packages provide a Rust library, not a standalone server
executable. The initial Cargo publication does not qualify the Python adapter
or complete the project's release gates. See [release status](docs/releases.md).

The planned Python distribution name is `uvicorn-rs-py`; it provides the
`uvicorn` command and import namespace after the compatibility and release
gates pass. The current checkout has those entry points, but only a small
prototype command and an incomplete Python API. The initial compatibility
reference is Uvicorn 0.54.0. See [replacement status](docs/uvicorn-compatibility.md)
for what is and is not available.

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
- [Uvicorn replacement status and migration](docs/uvicorn-compatibility.md)
- [ASGI and protocol support](docs/support-matrix.md)
- [Deployment guidance](docs/deployment.md)
- [Benchmark results and evidence limits](docs/benchmark-results.md)

For contributing, security reporting, support expectations, architecture, and
release information, see [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[SUPPORT.md](SUPPORT.md), and the [documentation site](https://appunni-m.github.io/uvicorn-rs/).

The project is not affiliated with the Uvicorn project. It is available under
[BSD-3-Clause or MIT](LICENSE), at your option.
