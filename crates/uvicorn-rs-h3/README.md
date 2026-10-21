# uvicorn-rs-h3

`uvicorn-rs-h3` is the HTTP/3 protocol dependency used by the Rust-native
`uvicorn-rs` crates. Its Rust library name remains `h3`; Cargo publishes this
maintained fork under the distinct package name `uvicorn-rs-h3`. Once the first
release is published, standalone Cargo consumers can resolve it from crates.io.
It does not depend on the Python adapter. Consumers need Rust 1.85 or newer,
matching the Uvicorn-RS workspace MSRV.

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
