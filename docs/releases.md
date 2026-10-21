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

The Python distribution remains named `uvicorn-rs-py`. The current checkout now includes the `uvicorn` command and import namespace, but their behavior is incomplete and has not passed the versioned compatibility gates. No package is published. Release verification must inspect the installed wheel and keep the Cargo server independent of Python.

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
short-lived OIDC publishing permission only to selected publisher jobs.
First-time Cargo crate creation still requires a maintainer bootstrap because
Trusted Publishing is configured on an existing crate. No release workflow
creates or moves a tag.

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
   Hosted CI coverage and independent Coverage-MCP review are separate evidence.
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

### First Cargo publication

Trusted Publishing cannot create a crate that does not exist yet. After every
candidate gate passes, a maintainer must bootstrap the four first versions
from a clean checkout using narrowly scoped short-lived credentials. Never put
those credentials in GitHub secrets, repository files, chat, logs, or artifacts.
Check the exact registry version before retrying an upload.

Publish and verify in this order:

1. native-app-contract
2. uvicorn-rs-h3
3. uvicorn-rs-h3-quinn
4. uvicorn-rs

Wait until each dependency is registry-visible before publishing its dependent.
Verify each registry checksum and an isolated downstream consumer. Then
configure the crate's Trusted Publisher for owner appunni-m, repository
uvicorn-rs, workflow publish.yml, and environment crates-io. Later releases
use the workflow's short-lived OIDC publisher jobs.

### First PyPI publication

Register the pending PyPI Trusted Publisher for project uvicorn-rs-py with
owner appunni-m, repository uvicorn-rs, workflow publish.yml, and environment
pypi. The first upload creates the project. The publish job accepts only the
candidate's exact wheel and source-distribution filenames and checksums.
Do not add a long-lived PyPI token to GitHub secrets.

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
