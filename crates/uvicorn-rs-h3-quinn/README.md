# uvicorn-rs-h3-quinn

`uvicorn-rs-h3-quinn` is the Quinn transport adapter used internally by
[`uvicorn-rs-h3`](https://github.com/appunni-m/uvicorn-rs/tree/main/crates/uvicorn-rs-h3).
Version 0.1.0 is published on
[crates.io](https://crates.io/crates/uvicorn-rs-h3-quinn/0.1.0). Its Rust
library name remains `h3_quinn`; the distinct Cargo package name lets the
adapter use the maintained H3 protocol package without colliding with the
upstream registry name. Most applications should depend directly on
`uvicorn-rs`, which pulls this crate in transitively. Consumers need Rust 1.85
or newer, matching the Uvicorn-RS workspace MSRV.

This package is based on the MIT-licensed `h3-quinn` 0.0.10 source from
[hyperium/h3](https://github.com/hyperium/h3). Its source README and upstream
license are retained in this repository. The adapter keeps the upstream
`h3-quinn` transport API used by `uvicorn-rs`.

The `datagram` feature is not included. HTTP/3 datagrams are outside the
supported `uvicorn-rs` surface. See the parent repository's support matrix for
protocol-level support details.

The package is MIT licensed. See [`LICENSE`](LICENSE) for the retained upstream
license text.
