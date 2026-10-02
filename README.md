# uvicorn-rs

`uvicorn-rs` is an independent Rust network server for Python ASGI 3 applications. The working name is provisional and comes from this workspace; the project is not affiliated with the Uvicorn project. Its CLI is `uvicorn-rs`, and its Python module is `uvicorn_rs`.

The Rust data plane currently supports HTTP/1.1, HTTP/2, and experimental HTTP/3. Python asyncio or optional uvloop owns application tasks, context, and exceptions. The server also implements bounded HTTP streaming, HTTP/1.1 WebSockets, ASGI lifespan, disconnect reporting, Python task cancellation, and graceful shutdown. See the [support matrix](docs/support-matrix.md) for tested behavior and limits.

The general performance gate failed across the completed category matrix: the server beats Uvicorn `asyncio + h11` on the fixed HTTP/1.1 case, but loses to Uvicorn `uvloop + httptools` there and regresses heavily on multi-chunk HTTP/1.1 responses. HTTP/2 and HTTP/3 compare favorably with Hypercorn on several cases, with higher CPU in many runs; those are not Uvicorn comparisons. Treat this as a protocol/interoperability prototype, not a faster or production replacement. Per-run results and category medians are in the [feasibility report](docs/feasibility.md) and [machine-readable summary](benchmarks/results/category-summary-2026-10-02.json).

`starlette-rs` is optional and remains an independent framework. This project does not install, import, bundle, or declare it as a runtime dependency. An optional [integration example](examples/starlette_rs_asgi.py) and [probe](scripts/probe_starlette_rs.py) can be run when `starlette-rs` is installed separately.

## Run

Use Python 3.12 and Rust 1.83 or newer for the checked development setup:

```sh
uv sync --python 3.12
uv run uvicorn-rs examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

The CLI accepts `module:app`, `--host`, `--port`, `--loop asyncio|uvloop`, `--certfile`, `--keyfile`, and `--graceful-timeout`. uvloop is optional. Supplying a certificate and key enables HTTPS with HTTP/1.1 and HTTP/2 over TCP plus HTTP/3 over QUIC on the same port. Cleartext HTTP/2 accepts prior-knowledge h2c. HTTP/3 is experimental.

## Black-box protocol probes

```sh
uv sync --python 3.12 --group benchmark
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
```

For the optional `starlette-rs` check, install that project separately and run `uv run python scripts/probe_starlette_rs.py`.

## Architecture and performance

- [ADR 0001: Rust runtime and Python asyncio bridge](docs/adr/0001-runtime-and-asyncio-bridge.md)
- [ASGI support matrix](docs/support-matrix.md)
- [Feasibility benchmark history](docs/feasibility.md)
- [HTTP/1.1 category runner](scripts/run_http_category_bench.py)
- [HTTP/2 category runner](scripts/run_h2_category_bench.py)
- [HTTP/3 category runner](scripts/run_h3_category_bench.py)
- [WebSocket category runner](scripts/run_websocket_category_bench.py)
- [Lifecycle runner](scripts/run_lifecycle_bench.py)

The benchmark runner compares the same HTTP/1.1 ASGI app and load client against Uvicorn's asyncio/h11 and uvloop/httptools configurations. It has fixed-response and streamed-response workloads. Uvicorn does not provide HTTP/2 or HTTP/3 baselines, so those protocols require a separately named ASGI server for performance comparisons. No package has been published.
