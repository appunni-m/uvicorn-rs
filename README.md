# uvicorn-rs

A Rust-first ASGI server with a Python adapter for Python applications.

## Project status

The Rust server and the Python ASGI adapter are still experimental and have not been published to Cargo or PyPI. The current Python command is a small prototype interface; it is not yet a drop-in Uvicorn replacement.

The confirmed replacement target keeps the Python distribution named uvicorn-rs-py and provides the uvicorn command and import namespace. Upstream Uvicorn 0.54.0 is the initial pinned compatibility reference. The compatibility page explains what is planned, what works today, and how replacement and rollback will work after a compatible release.

There is no general performance claim. Python application code still runs on its Python-owned asyncio loop and crosses the ASGI boundary. Rust owns the network runtime, but this does not remove the Python GIL from Python application work.

## Run the current prototype

From a development checkout with Python and Rust toolchains configured:

~~~sh
uv sync --python 3.12
uv run uvicorn-rs-py examples.hello_asgi:app --host 127.0.0.1 --port 8000
~~~

In another terminal:

~~~sh
curl -i http://127.0.0.1:8000/
~~~

This uses the current prototype CLI. Its options and limitations are listed in the [configuration guide](docs/configuration.md).

## What runs where

For a Python ASGI application, Rust handles network listeners and protocol work. The Python application remains on its owning asyncio or uvloop event loop; Python callables, ASGI messages, context, and exceptions cross the PyO3 boundary. See the [ASGI support matrix](docs/support-matrix.md).

Rust applications can use the Python-free uvicorn-rs Cargo library through its server-neutral service contract. The server remains independent of Starlette-RS and FastAPI-RS; those projects do not need this server as a runtime dependency. See [native Rust integration](docs/native-fastapi-composition.md).

## Choose a guide

- [Run a Python ASGI app](docs/quickstart.md)
- [Uvicorn replacement status and migration](docs/uvicorn-compatibility.md)
- [Current prototype configuration](docs/configuration.md)
- [Deployment guidance](docs/deployment.md)
- [ASGI behavior and protocol support](docs/support-matrix.md)
- [Benchmark results and evidence limits](docs/benchmark-results.md)

Contributors and maintainers can find [contribution instructions](CONTRIBUTING.md), [security reporting](SECURITY.md), [support expectations](SUPPORT.md), [architecture](docs/architecture.md), [parity methodology](docs/parity.md), and the [release guide](docs/releases.md).

The project is not affiliated with the Uvicorn project. It is available under [BSD-3-Clause or MIT](LICENSE), at your option.
