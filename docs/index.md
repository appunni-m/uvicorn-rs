# uvicorn-rs

Use these guides to run the current prototype, check what it supports, or understand the planned Uvicorn replacement.

## Start or configure a server

- [Run a Python ASGI app](quickstart.md)
- [Configure the current prototype](configuration.md)
- [Deploy and integrate](deployment.md)

## Check compatibility

- [Uvicorn replacement status](uvicorn-compatibility.md) — package name, command and import target, current limits, migration and rollback.
- [ASGI support matrix](support-matrix.md) — live-tested protocol, event, and lifecycle behavior.

The Rust server and Python adapter are experimental and have not been published. The current adapter is not a drop-in Uvicorn replacement. The target keeps the PyPI distribution name uvicorn-rs-py while providing the uvicorn CLI and imports after compatibility work and release gates pass.

## Project information

- [Benchmark results](benchmark-results.md)
- [Contributing](https://github.com/appunni-m/uvicorn-rs/blob/main/CONTRIBUTING.md)
- [Security reporting](https://github.com/appunni-m/uvicorn-rs/blob/main/SECURITY.md)
- [Support expectations](https://github.com/appunni-m/uvicorn-rs/blob/main/SUPPORT.md)
- [License](https://github.com/appunni-m/uvicorn-rs/blob/main/LICENSE)

Architecture decisions, detailed parity evidence, coverage, benchmark methods, and release engineering are grouped under Maintainers in the site navigation.
