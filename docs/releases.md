# Release guide

This guide defines how to prepare and publish the first release of uvicorn-rs.
Candidate assembly, Cargo/PyPI publication, GitHub Releases, and documentation
deployment are separate steps. A successful build is not a published release.

Use these state labels precisely:

- **Prepared:** source or workflow is ready for a later gate.
- **CI-proven:** the exact clean commit passed the named hosted checks.
- **Published:** the registry or GitHub Release accepted the artifact.
- **Registry-visible:** the exact version can be resolved from the registry.
- **Consumer-verified:** an isolated downstream project installed and exercised
  the exact published version.
- **Released:** the authorized distribution decision and required verification
  are complete.

## Distribution boundaries

| Channel | Distribution | Scope |
|---|---|---|
| Cargo | native-app-contract, uvicorn-rs-h3, uvicorn-rs-h3-quinn, uvicorn-rs | Python-free Rust libraries. This repository does not currently ship a standalone native executable. |
| PyPI | uvicorn-rs-py | Optional Python compatibility client for standard Python ASGI applications. It is not required by the Python-free Rust library. |
| Documentation | README, MkDocs site, and docs.rs | Repository docs deploy through GitHub Pages; crate API docs are generated from published Cargo archives. |

The Python distribution remains named `uvicorn-rs-py`. The current checkout now includes the `uvicorn` command and import namespace, but their behavior is incomplete and has not passed the versioned compatibility gates. The four Rust crates were published at `0.1.0` from clean commit `9eccb4fb8c7f27269e99c3af194feb4a2a8f7709` on 2026-10-22 as a one-time crates.io bootstrap for Trusted Publishing setup. The Python package is still unpublished. The Cargo bootstrap is not a complete application release and does not close the remaining candidate gates. Release verification must inspect the installed wheel and keep the Cargo server independent of Python.

The Cargo workspace packages and Python package currently declare version 0.1.0.
All published Cargo packages require Rust 1.85 or newer, the workspace MSRV
verified by the locked CI lane.
The PyPI package requires Python 3.9 or newer and uses the cp39-abi3 wheel ABI.
The wheel matrix builds Linux x86-64, macOS ARM64, and Windows x86-64 artifacts.
Those targets do not imply Linux ARM64, musl, or universal macOS wheels.

The native Cargo dependency order is native-app-contract, uvicorn-rs-h3,
uvicorn-rs-h3-quinn, then uvicorn-rs. Publish each dependency and confirm its
registry visibility before publishing a dependent.

## Release workflow model

The release flow uses the staged artifact model in the
[Pillow-RS release workflow](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/release.yml)
and its
[separate documentation workflow](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/docs.yml):
validate an immutable source identity, build and verify artifacts once, carry
checksummed artifacts between jobs, and isolate publishing permissions from
build and test jobs.

This repository adapts that pattern for first publication. The Release candidate
workflow does not publish. The manual Publish packages workflow defaults to
prepare-only, revalidates the exact tag and candidate artifact, and grants
short-lived OIDC publishing permission only to selected publisher jobs. The
four Cargo names now exist; configure Trusted Publishing on each crate before
using the Cargo publisher jobs. The PyPI pending publisher is reported
configured by the project owner. No release workflow creates or moves a tag.

### Cargo bootstrap publication record

The following immutable `0.1.0` archives were published from clean commit
`9eccb4fb8c7f27269e99c3af194feb4a2a8f7709`. Each registry checksum was checked
against the exact local archive after upload:

| Crate | Registry | SHA-256 |
|---|---|---|
| `native-app-contract` | [crates.io](https://crates.io/crates/native-app-contract/0.1.0) | `ceaa890b28b5587e45ef8740dc8530e172dcfca18a96c5ea9e25260d02531ba0` |
| `uvicorn-rs-h3` | [crates.io](https://crates.io/crates/uvicorn-rs-h3/0.1.0) | `809379da49a0f299dfd0a88c69ab0e0a948e806edbfbcc087e3e358783b52ae7` |
| `uvicorn-rs-h3-quinn` | [crates.io](https://crates.io/crates/uvicorn-rs-h3-quinn/0.1.0) | `a5b2a3fc559156fbf948fd4838e5c2ed860223add8bfd2ce376cc4d5b2306375` |
| `uvicorn-rs` | [crates.io](https://crates.io/crates/uvicorn-rs/0.1.0) | `064b0037134e06a7eb16aa4cbd967c5ac2ecdeb5418ba5a71552809e46f485ce` |

These are real crate releases, not placeholders, and cannot be overwritten. Cargo
archives include the source commit in `.cargo_vcs_info.json`; a candidate built
from a later commit will have different archive bytes even if crate sources did
not change. Future package versions must therefore be bumped if the candidate
source is not the recorded commit. Do not treat the published crates as proof
that the full compatibility, coverage, or performance gates passed.

## Check release readiness

This guide describes the release gates; it is not a live status report. Check
the GitHub Actions runs and retained artifacts for the exact clean `main`
commit under review. Do not rely on a run for an older commit, a partial matrix,
or a status snapshot copied into documentation. Missing or expired artifacts
do not count as evidence.

The current performance policy in
[performance-acceptance.json](performance-acceptance.json) makes no general
performance-superiority claim for the Python compatibility package. Claims are
limited to the workloads and Python-free Rust-native composition defined by
that policy. A release candidate still requires the complete, correctness-gated
three-system artifact; partial FastAPI results cannot satisfy that gate.

## Gates before candidate assembly

All evidence must bind to one clean reviewed main commit and the same package
version.

1. Configure a main branch ruleset or protection requiring CI, public parity,
   unified coverage, and documentation checks. Restrict version-tag creation
   to maintainers.
2. Pass complete CI, including the maintained live parity matrix, all three
   coverage repeats, 100% measured native regions and lines, exact Rust MSRV,
   installed-package checks, and native composition inputs.
3. Run Coverage-MCP against the complete, source-matched hosted coverage report.
   Use the [Coverage-MCP release handoff](coverage.md#release-coverage-mcp-handoff).
   Hosted CI coverage and independent Coverage-MCP review are separate evidence;
   the tag workflow requires one successful handoff for the same commit and CI
   run attempt.
4. Complete the correctness-gated three-system performance matrix. Require
   matching valid repetitions and report throughput, p50/p95/p99 latency,
   server CPU per operation, and sampled peak RSS. Keep stock FastAPI and
   Starlette workloads separate from Rust-native application measurements.
5. Build the Cargo and Python packages from the exact clean commit. Inspect
   archive contents, hashes, licenses, versions, and isolated consumers.
6. Pass the standalone H3 archive consumer described below.
7. Build and validate the maintained documentation. Configure GitHub Pages to
   use GitHub Actions before attempting deployment.
8. Verify registry names, publisher identities, protected GitHub environments,
   and reviewer requirements. Recheck current registry state immediately before
   publication.

A selected-case report, local archive build, old commit, partial benchmark, or
successful documentation build alone cannot satisfy the full candidate gate.

## Candidate assembly

The tag-triggered
[Release candidate workflow](https://github.com/appunni-m/uvicorn-rs/blob/main/.github/workflows/release.yml) assembles a
candidate from the exact successful main CI and performance artifacts. After
all gates pass and the maintainer authorizes a tag:

1. Create an annotated vMAJOR.MINOR.PATCH tag on the reviewed commit. Do not
   move or reuse a tag after a public artifact refers to it.
2. The workflow checks the remote tag object, tag/version agreement, clean
   checkout, main ancestry, and successful exact-commit CI and performance runs.
3. It downloads the exact retained artifacts, checks their workflow identity
   and digests, and verifies package identity and evidence.
4. It builds the independent consumer against the extracted Cargo archives and
   records the result in the candidate bundle.
5. It writes a candidate manifest and checksums and uploads the immutable
   bundle. Candidate assembly has no registry credentials or publication
   permissions.

The candidate includes three Python wheels, a source distribution, four Cargo
archives, and the exact parity, coverage, benchmark, Python-floor, and standalone
consumer evidence required by the verifier. Missing, expired, incomplete, or
mismatched artifacts stop assembly.

### Standalone H3 archive consumer

Cargo publication requires the exact uvicorn-rs archive to pass an external
consumer built from the candidate archives. It sends the maintained malformed
HTTP/3 frame input, requires the peer to observe H3_FRAME_ERROR (262), then
checks a healthy request on a fresh connection. RFC 9114 section 7.1 makes a
truncated final frame a connection error, so the failed connection cannot be
reused.

The receipt must identify the exact commit and archive hashes, show
source_dirty=false, use the extracted candidate archives rather than a
workspace patch, and record both the protocol error and fresh-connection
response. A local or dirty-source receipt is diagnostic only.

## Publication

The separate
[Publish packages workflow](https://github.com/appunni-m/uvicorn-rs/blob/main/.github/workflows/publish.yml) is dispatched
from main with an existing annotated tag. It defaults to prepare-only and
requires the exact typed confirmation PUBLISH vX.Y.Z before publication.

Prepare-only verifies the tag, exact candidate artifact and checksum manifest,
package contents, version, and registry state. Publication requires a separate
explicit maintainer decision. Do not publish from a dirty checkout or bypass a
failed candidate gate.

### Cargo Trusted Publishing setup

Configure each existing crate's Trusted Publisher for owner `appunni-m`,
repository `uvicorn-rs`, workflow `publish.yml`, and environment `crates-io`.
The publisher jobs use short-lived OIDC credentials; do not put a long-lived
crates.io token in GitHub secrets. Before any later upload, verify the exact
candidate version and checksum. The published `0.1.0` versions are immutable.

### First PyPI publication

The project owner reports that the pending PyPI Trusted Publisher for
`uvicorn-rs-py` is configured with owner `appunni-m`, repository `uvicorn-rs`,
workflow `publish.yml`, and environment `pypi`. No PyPI version has been
uploaded. The project name must be rechecked before publication. The publish
job accepts only the candidate's exact wheel and source-distribution filenames
and checksums. Do not add a long-lived PyPI token to GitHub secrets.

### GitHub Release

A GitHub Release is a separate distribution action. If authorized, create it
only after the intended Cargo/PyPI publication and registry verification.
Attach the exact candidate artifacts and SHA-256 manifest. Keep repository
write permission isolated to the release job.

## Documentation publication

The
[Documentation workflow](https://github.com/appunni-m/uvicorn-rs/blob/main/.github/workflows/docs.yml) builds every maintained
page with strict link validation, uploads the validated Pages artifact, and
deploys only from main after the build passes. It uses a separate
github-pages environment and does not publish packages.

Set repository Pages source to GitHub Actions and create the github-pages
environment before deployment. The expected site URL is
https://appunni-m.github.io/uvicorn-rs/. Verify the deployed pages after the
workflow succeeds. docs.rs pages become available from published crate
archives; inspect each crate's rendered API documentation after registry
publication.

## Package verification contract

| Artifact | Build and consumer evidence |
|---|---|
| Linux x86-64 wheel | Ubuntu 24.04 build; CPython 3.12.10 installed-wheel smoke and public live parity. |
| macOS ARM64 wheel | macOS 14 build; CPython 3.12.10 installed-wheel HTTP, context, lifespan, and cancellation checks. |
| Windows x86-64 wheel | Windows Server 2022 build; CPython 3.12.10 package-consumer checks. POSIX signal parity is not claimed. |
| Source distribution | Safe file inventory, required licenses and metadata, locked extracted rebuild, and fresh consumer. |
| Cargo archives | Package inventories, normalized metadata, licenses, safe extraction, locked dependency-ordered compilation, and the standalone H3 consumer for uvicorn-rs. |

The cp39-abi3 tag represents the declared Python 3.9 floor; the maintained
Python 3.9 lane verifies that ABI floor on Linux, not every protocol on every
Python/OS combination. Linux wheel builds use the hosted runner's native
environment. No manylinux2014, Linux ARM64, musl, or universal macOS wheel claim
is made.

The source distribution uses the Git sdist generator so it retains the reviewed
workspace manifest, lockfile, and Cargo workspace members needed by its locked
rebuild. Package verification checks the extracted archive rather than
inferring contents from the checkout. Repository-only benchmark outputs,
logs, coverage reports, keys, and environments are excluded from release
archives.

## After publication

For every exact version, verify registry visibility, checksum, and a fresh
consumer outside the repository checkout. Confirm the Cargo dependencies resolve
from crates.io and the Python wheel imports from the installed distribution.
Inspect docs.rs pages and the deployed documentation site. Keep release notes,
tag, package versions, candidate manifest, and checksums bound to the same
reviewed source.

The changelog remains under Unreleased until a candidate has passed the exact
commit gates and the maintainer has selected the distribution channels.
