# Run a Python ASGI app

This guide runs the current development prototype from a repository checkout.
There is no PyPI release yet, and the prototype is not a drop-in Uvicorn
replacement.

## Before you start

You need `uv`, CPython 3.12, and Rust 1.85 or newer. From the repository root,
install the locked development environment and start the example:

```sh
uv sync --python 3.12
uv run uvicorn examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

The server binds to loopback so it is reachable only from this machine. In a
second terminal, send a request:

```sh
curl -i http://127.0.0.1:8000/
```

The response should have status `200` and a text body beginning with
`GET / 1.1`. Press Ctrl-C in the server terminal to request shutdown.

## Run your own app

Use an import string in `module:attribute` form. Start the command from a
directory where the module can be imported, or set `PYTHONPATH` to include your
application directory:

```sh
uv run uvicorn myapp.asgi:app --host 127.0.0.1 --port 8000
```

The current prototype loads the named object directly. It does not invoke
application factories and supports only the options listed in the
[configuration guide](configuration.md).

## Before using it instead of Uvicorn

The `uvicorn` name in this checkout does not yet provide Uvicorn's full CLI,
Python API, worker, reload, or deployment behavior. Do not remove Uvicorn from
an application environment expecting a compatible replacement. Check the
[replacement status](uvicorn-compatibility.md) before planning a migration.
