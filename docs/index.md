# uvicorn-rs

Start with the task you want to complete. The current server is experimental and is not yet a replacement for Uvicorn.

## Start or configure a server

- [Run a Python ASGI app](quickstart.md)
- [Configure the current prototype](configuration.md)
- [Deploy and integrate](deployment.md)

## Check compatibility

- [Can I replace Uvicorn?](uvicorn-compatibility.md) — availability, current gaps, and future migration and rollback steps.
- [ASGI support matrix](support-matrix.md) — live-tested protocol, event, and lifecycle behavior.

The Rust server and Python adapter are experimental and have not been published. The Python adapter is not a drop-in Uvicorn replacement. The distribution will be named `uvicorn-rs-py` and provide the `uvicorn` command and import namespace; the checkout exposes those names, but not Uvicorn's full behavior yet.

## Project information

- [Benchmark results](benchmark-results.md)
- [Contributing](https://github.com/appunni-m/uvicorn-rs/blob/main/CONTRIBUTING.md)
- [Security reporting](https://github.com/appunni-m/uvicorn-rs/blob/main/SECURITY.md)
- [Support expectations](https://github.com/appunni-m/uvicorn-rs/blob/main/SUPPORT.md)
- [License](https://github.com/appunni-m/uvicorn-rs/blob/main/LICENSE)

Architecture decisions, detailed protocol evidence, coverage, benchmark methods, and release engineering are grouped under Maintainers in the site navigation.
