# Changelog

Notable user-facing changes are listed here. An `Unreleased` entry describes
work in progress; it does not mean a candidate has passed the release gates or
that a package has been published.

## 0.3.6 (Unreleased)

The immutable `v0.3.5` candidate passed exact-source coverage, performance
acceptance, and the standalone HTTP/3 archive consumer, but failed its final
performance-artifact recheck because the workflow omitted the selected event
from that step's environment. No 0.3.5 artifacts were published. This
fix-forward passes the event identity to the recheck and prepares version
0.3.6; fresh exact-source gates and candidate qualification are required before
GitHub Actions can publish it.

### Fixed

- Use the shared benchmark certificate generator for the standalone archive
  consumer, trusting the CA while serving a `CA:FALSE` localhost leaf.
- Carry forward normalized dependency-version comparison across benchmark
  systems while retaining each platform's full lockfile and installed-file
  integrity checks.
- Pass the selected benchmark event to the final candidate-artifact
  revalidation step.

### Packaging

- Prepare the consolidated Cargo crates and PyPI `uvicorn-rs` distribution as
  version 0.3.6. GitHub Actions remains the only publication path.

## 0.3.5 (Unpublished candidate)

The immutable `v0.3.5` candidate passed the exact-source coverage and
performance rechecks and built the Cargo archives as a standalone HTTP/3
consumer. Its final performance-artifact recheck failed because the step did
not receive `PERFORMANCE_EVENT`. No Cargo or PyPI artifacts were published;
the tag remains immutable.

## 0.3.4 (Unpublished candidate)

The immutable `v0.3.3` candidate passed exact-source coverage and package
verification, but performance acceptance compared complete dependency
receipts across operating systems. Those receipts correctly contain
machine-specific install paths and compiled-file hashes. Version 0.3.4
normalized the cross-system dependency comparison while retaining each
platform's full lockfile and installed-file integrity checks. Candidate #5 for
`v0.3.4` then passed source coverage and performance acceptance but failed its
standalone HTTP/3 archive consumer because the test harness used its CA as the
server certificate. No 0.3.4 Cargo or PyPI artifact was published; its tag
remains immutable.

### Packaging

- The 0.3.4 Cargo crates and PyPI `uvicorn-rs` distribution were not published.
  GitHub Actions remains the only publication path.

## 0.3.3 (Unpublished candidate)

The immutable `v0.3.2` candidate passed exact-source CI coverage and the
three-system benchmark, but its release verifier rejected the stock Uvicorn
identity because it was recorded in the isolated oracle environment rather
than the candidate environment. No 0.3.2 Cargo or PyPI artifacts were
published. Version 0.3.3 corrected that earlier oracle-identity evidence
check, but its own immutable tag stopped at a second cross-system dependency
identity comparison. No 0.3.3 Cargo or PyPI artifacts were published; its tag
will not be moved.

### Fixed

- Suppress HTTP/3 response bodies for `HEAD`, `204 No Content`, and `304 Not
  Modified` responses instead of polling an ASGI body the protocol must omit.
- Validate the separately installed stock Uvicorn oracle against the benchmark
  environment receipt, lockfile, source hashes, and candidate dependency
  versions.

### Packaging

- Version 0.3.3 remains an unpublished candidate. Its exact-main coverage and
  package evidence are historical inputs for that candidate only; they do not
  qualify version 0.3.5.

## 0.3.2 (Unpublished candidate)

The immutable `v0.3.2` tag failed qualification because its release
performance verifier looked for stock Uvicorn in the candidate environment,
although the benchmark correctly isolated it and recorded a verified
`uvicorn_oracle` identity. No 0.3.2 Cargo or PyPI artifacts were published.
Version 0.3.2 also corrected the source-inventory mismatch found by the failed
0.3.1 candidate, but remains unpublished.

### Fixed

- Shared the benchmark workspace source inventory between capture and release
  verification so all Rust sources and Cargo manifests are checked consistently.

### Packaging

- Version 0.3.2 was an unpublished candidate; its immutable tag is retained.
  GitHub Actions remains the only publication path.

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
