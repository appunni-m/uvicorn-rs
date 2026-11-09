# Changelog

Notable user-facing changes are listed here. An `Unreleased` entry describes
work in progress; it does not mean a candidate has passed the release gates or
that a package has been published.

## 0.3.2 (Unreleased)

The immutable `v0.3.1` candidate tag failed qualification because the release
performance verifier did not include the workspace Rust files captured by the
benchmark. No 0.3.1 Cargo or PyPI artifacts were published. Version 0.3.2
aligns benchmark capture and acceptance source inventories; it introduces no
server behavior change and remains gated on exact-source release evidence.

### Fixed

- Shared the benchmark workspace source inventory between capture and release
  verification so all Rust sources and Cargo manifests are checked consistently.

### Packaging

- Prepare the consolidated Cargo crates and PyPI `uvicorn-rs` distribution as
  version 0.3.2. The `v0.3.1` tag is retained as an unpublished, failed
  candidate; GitHub Actions remains the only publication path.

## 0.3.1 (Unreleased candidate)

Version 0.3.1 reissued the 0.3.0 candidate source under a fresh version. The
immutable `v0.3.1` tag did not pass release-candidate qualification; its
performance verifier rejected the correct complete source inventory. No
0.3.1 Cargo or PyPI artifacts were published.

### Added

- Consolidated the Python-free Rust server as the `uvicorn-rs` crate. HTTP/3
  protocol and Quinn transport support are included behind the optional
  `http3` feature.
- Added the `uvicorn-rs` PyPI distribution with the `uvicorn` command and
  import namespace. The optional internal PyO3 adapter remains named
  `uvicorn-rs-py`.
- Kept the lifecycle contract as the separate `asgi-lifespan-protocol-rs`
  crate; HTTP/3 and Quinn are no longer separate project crates.

## 0.2.1

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
