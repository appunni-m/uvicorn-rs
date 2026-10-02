# Contributing

Thanks for taking an interest in `uvicorn-rs`. The project is an experimental
ASGI server; contributions should preserve the support matrix and avoid
promoting a targeted probe result into a general compatibility claim.

## Development setup

The checked local setup uses CPython 3.12.13, Rust 1.98.1, Cargo, and `uv`.
The manifest declares Rust 1.83 as the minimum; that exact toolchain has not
been verified. Set up the local environment with:

```sh
uv sync --python 3.12 --group benchmark
```

The optional benchmark group installs Uvicorn, uvloop, Hypercorn, and probe
clients. The server itself does not depend on Uvicorn, Hypercorn, uvloop, or
`starlette-rs` at runtime.

Run the version-pinned, input-only source/target matrix with:

```sh
uv run --group benchmark python scripts/run_parity.py
```

It exercises H1, H2, H3, WebSockets, disconnect delivery, and graceful
lifespan shutdown. See the [parity guide](docs/parity.md) for why Uvicorn is the
oracle for H1/WebSockets/lifespan and Hypercorn for H2/H3, and for the current
case scope. The latest local evidence is linked from the [support
matrix](docs/support-matrix.md); record a new result under a fresh filename.

## Before submitting

Run the Rust formatter, linter, and API documentation build:

```sh
cargo fmt --all -- --check
cargo clippy --all-targets --all-features --locked -- -D warnings
RUSTDOCFLAGS='-D warnings' cargo doc -p uvicorn-rs --no-deps --locked
```

The HTTP/3 probe utility is a separate Cargo manifest and has its own lockfile:

```sh
cargo fmt --manifest-path tools/http3-probe/Cargo.toml --all -- --check
cargo clippy --manifest-path tools/http3-probe/Cargo.toml \
  --all-targets --all-features --locked -- -D warnings
```

After building the extension, run the focused black-box probes for the behavior
you changed. For broad protocol or lifecycle changes, run the complete current
probe set:

```sh
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
```

The optional `starlette-rs` check requires installing that framework
independently. These probes do not replace the complete ASGI conformance suite,
which has not yet been run.

## Performance changes

Do not infer speed from language, SIMD availability, or a microbenchmark alone.
For performance changes, follow the [full benchmark setup and commands](docs/benchmarks.md).
Record the source revision/hash, machine, Python and dependency versions, load
parameters, correctness-gate result, throughput, latency percentiles,
server/client CPU, and sampled RSS. Use the same ASGI app and load client for
candidate and baseline. Do not overwrite an existing raw result file; give new
runs a distinct name. See [the feasibility report](docs/feasibility.md) for
current results and their limits.

## Documentation and changes

Update the support matrix when implementation status or evidence changes. Keep
performance statements scoped to the exact workload and environment. Explain
unsafe code only if the repository policy is deliberately changed; the main
crate currently forbids unsafe Rust. Keep `starlette-rs` optional and outside
the server's runtime dependencies.

The CI checks, artifact targets, and annotated-tag candidate process are
documented in [Release candidates](docs/releases.md). Do not publish or tag a
public release while licensing and the public distribution decision remain
unresolved.

## Project status

The repository's license has not been selected. Contributions are welcome for
review, but do not assume this source is licensed for redistribution. There is
no contributor license agreement or DCO configured. See [support](SUPPORT.md)
and [security reporting](SECURITY.md) for contact and disclosure expectations.
