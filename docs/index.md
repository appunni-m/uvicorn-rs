# uvicorn-rs documentation

`uvicorn-rs` is an experimental Rust-native ASGI server project. The Cargo
crate is the Python-free Rust service runtime. `uvicorn-rs-py` is a separate,
thin compatibility adapter for Python ASGI applications and their asyncio
event loop.

The Python ASGI adapter is not currently a generally faster replacement for
Uvicorn. Performance evidence is workload-specific, and some measured Python
FastAPI workloads regress. The project keeps compatibility claims in the
[ASGI support matrix](support-matrix.md) and performance claims tied to
reproducible measurements.

## Start here

- Configure the Python adapter and CLI: [configuration](configuration.md).
- Check protocol and lifecycle support: [support matrix](support-matrix.md).
- Understand runtime ownership: [architecture](architecture.md).
- Integrate Rust-native services: [native FastAPI composition](native-fastapi-composition.md).
- Run or interpret comparisons: [benchmarks](benchmarks.md) and [current results](benchmark-results.md).
- Review release readiness: [release process](releases.md).

Rust-native Starlette and FastAPI integration is an independent path. The
Python compatibility adapter remains separate, and Starlette-RS does not
depend on this server.

## Project routes

- [Repository README](https://github.com/appunni-m/uvicorn-rs#readme)
- [Contributing](https://github.com/appunni-m/uvicorn-rs/blob/main/CONTRIBUTING.md)
- [Security policy](https://github.com/appunni-m/uvicorn-rs/blob/main/SECURITY.md)
- [Support expectations](https://github.com/appunni-m/uvicorn-rs/blob/main/SUPPORT.md)
- [License](https://github.com/appunni-m/uvicorn-rs/blob/main/LICENSE)
