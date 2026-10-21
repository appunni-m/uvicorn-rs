# uvicorn-rs-h3

`uvicorn-rs-h3` is the HTTP/3 protocol implementation used internally by the
Rust-native `uvicorn-rs` crate. Version 0.1.0 is published on
[crates.io](https://crates.io/crates/uvicorn-rs-h3/0.1.0). Its Rust library
name remains `h3`; the distinct package name lets the server depend on this
maintained fork without colliding with the upstream registry package. Most
applications should depend directly on `uvicorn-rs`, which pulls this crate in
transitively. It does not depend on the Python adapter. Consumers need Rust
1.85 or newer, matching the Uvicorn-RS workspace MSRV.

This package is based on the MIT-licensed `h3` 0.0.8 source from
[hyperium/h3](https://github.com/hyperium/h3). The upstream license and source
README are retained in this repository. The fork carries two receive-path
corrections:

- Empty HTTP/3 DATA frames are skipped without treating them as end-of-body.
- A DATA frame truncated by a clean QUIC FIN returns `UnexpectedEnd`, allowing
  the HTTP/3 layer to report the required `H3_FRAME_ERROR`.

The corresponding live parity cases are maintained in the parent repository.
This fork uses its own crates.io package name so published `uvicorn-rs`
archives receive these corrections without relying on workspace patches.

The package is MIT licensed. See [`LICENSE`](LICENSE) for the retained upstream
license text.
