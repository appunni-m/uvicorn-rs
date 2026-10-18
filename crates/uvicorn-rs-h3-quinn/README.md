# uvicorn-rs-h3-quinn

`uvicorn-rs-h3-quinn` is the Quinn transport adapter paired with
[`uvicorn-rs-h3`](https://github.com/appunni-m/uvicorn-rs/tree/main/crates/uvicorn-rs-h3).
Its Rust library name remains `h3_quinn`; the distinct Cargo package name lets
the adapter share maintained H3 protocol types in standalone registry
consumers after both packages are published.

This package is based on the MIT-licensed `h3-quinn` 0.0.10 source from
[hyperium/h3](https://github.com/hyperium/h3). Its source README and upstream
license are retained in this repository. The adapter keeps the upstream
`h3-quinn` transport API used by `uvicorn-rs`.

The `datagram` feature is not included. HTTP/3 datagrams are outside the
supported `uvicorn-rs` surface. See the parent repository's support matrix for
protocol-level support details.

The package is MIT licensed. See [`LICENSE`](LICENSE) for the retained upstream
license text.
