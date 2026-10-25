# Changelog

Notable user-facing changes are listed here. An `Unreleased` entry describes
work in progress; it does not mean a candidate has passed the release gates or
that a package has been published.

## 0.2.1 (Unreleased)

### Added

- HTTP/3 protocol and Quinn adapter source moved into `uvicorn-rs` behind its
  `http3` Cargo feature; separate `uvicorn-rs-h3` packages are no longer built.
- Renamed the shared lifecycle contract package to
  `asgi-lifespan-protocol-rs`.
- Prepared release artifacts for the Rust server, lifecycle contract, and
  `uvicorn-rs-py` compatibility client.
- Commit-bound Rust crate archive inspection and clean extracted-archive
  consumer builds in release evidence.

### Compatibility

- No server behavior or protocol compatibility claim changes as part of this
  packaging work. See the [support matrix](docs/support-matrix.md) for the
  current documented contract and limitations.
