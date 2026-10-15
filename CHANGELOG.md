# Changelog

Notable user-facing changes are listed here. An `Unreleased` entry describes
work in progress; it does not mean a candidate has passed the release gates or
that a package has been published.

## 0.1.0 (Unreleased)

### Added

- Candidate packaging for the Python-free `uvicorn-rs` server library and the
  runtime-neutral `native-app-contract` crate, alongside the optional
  `uvicorn-rs-py` compatibility client.
- Commit-bound Rust crate archive inspection and clean extracted-archive
  consumer builds in release evidence.

### Compatibility

- No server behavior or protocol compatibility claim changes as part of this
  packaging work. See the [support matrix](docs/support-matrix.md) for the
  current documented contract and limitations.
