# Run a Python ASGI app

This guide starts the current development prototype from a repository checkout. PyPI wheels are not published yet.

## Before you start

Use a checkout with the project's Python and Rust toolchains available. The local development setup is CPython 3.12; the Rust crate declares Rust 1.85 as its minimum supported version.

## Start the example

From the repository root:

~~~sh
uv sync --python 3.12
uv run uvicorn-rs-py examples.hello_asgi:app --host 127.0.0.1 --port 8000
~~~

In a second terminal, send a request:

~~~sh
curl -i http://127.0.0.1:8000/
~~~

The example responds with the request method, path, HTTP version, and request body. Press Ctrl-C in the server terminal to request graceful shutdown.

## Run your own app

The current command accepts an import string in module:attribute form. The module must be importable from the server process. The current prototype retrieves the named object directly; it does not invoke application factories.

~~~sh
uv run uvicorn-rs-py myapp:app --host 127.0.0.1 --port 8000
~~~

Use the [current configuration guide](configuration.md) for available options. For the planned uvicorn command and import compatibility, see [Uvicorn replacement status](uvicorn-compatibility.md). Do not use the current prototype as a drop-in replacement for Uvicorn.
