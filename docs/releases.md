# Release guide

This guide defines how to prepare and publish uvicorn-rs releases.
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
| Cargo | asgi-lifespan-protocol-rs, uvicorn-rs | Python-free Rust libraries. HTTP/3 protocol and Quinn transport code ship inside `uvicorn-rs` behind its `http3` feature. |
| PyPI | uvicorn-rs | Optional Python compatibility client for standard Python ASGI applications. It is not required by the Python-free Rust library. |
| Documentation | README, MkDocs site, and docs.rs | Repository docs deploy through GitHub Pages; crate API docs are generated from published Cargo archives. |

The confirmed PyPI distribution name is `uvicorn-rs`, following the project's `pillow-rs` naming convention. It provides the `uvicorn` import namespace, `uvicorn` command, and `python -m uvicorn` entry point for in-place use. The root Cargo/PyO3 integration package remains `uvicorn-rs-py` internally; that is not the PyPI distribution name. The package also retains its `uvicorn-rs-py` console alias. The exact compatibility scope is recorded in the [support matrix](support-matrix.md); these names do not imply full Uvicorn parity. The coordinated clean candidate version is 0.2.1: lifecycle version 0.2.0 is already occupied by a dirty-source archive, while the consolidated server crate and PyPI distribution have no published 0.2.1 version. A local Cargo-only 0.2.1 candidate now exists at clean commit `7754895262c7b1d7baa2e9595277a81607634d38`; its archives were reproduced with Cargo 1.85.0 and are recorded below. The candidate is not the exact-main workflow bundle. No PyPI wheel or sdist has been assembled, and neither 0.2.1 crate is published.

The historical 0.1.0 Cargo bootstrap is recorded below. The maintainer has removed the old `uvicorn-rs` release and is removing the standalone `uvicorn-rs-h3` and `uvicorn-rs-h3-quinn` identities. A crates.io API check on 2026-10-25 returned HTTP 404 for all three names; this confirms they are not currently registry-resolvable, but does not establish that a new `uvicorn-rs` publication will be accepted. Recheck availability immediately before any Cargo release. The new `uvicorn-rs` package vendors the H3 protocol and Quinn adapter source behind `http3`; it does not depend on separate project-owned H3 crates. `asgi-lifespan-protocol-rs` is the current lifecycle-contract package. The Python adapter depends on `uvicorn-rs`; Rust-native frameworks can depend on `uvicorn-rs` without Python.

The Cargo workspace packages and Python package now declare candidate version
0.2.1. This is an unreleased version selection, not release evidence.
All published Cargo packages require Rust 1.85 or newer, the workspace MSRV
verified by the locked CI lane.
The PyPI package requires Python 3.9 or newer and uses the cp39-abi3 wheel ABI.
The wheel matrix builds Linux x86-64, macOS ARM64, and Windows x86-64 artifacts.
Those targets do not imply Linux ARM64, musl, or universal macOS wheels.

`asgi-lifespan-protocol-rs` 0.2.0 is registry-visible with checksum
`3b16049a572461b03e8b1eebe2723933e369f81ce17ecfbfdeafb7fd2cb16f68`. Its
published archive records source commit
`86e72e181d00feca1b4db7f30377d5d9d4345b83` with `dirty: true` in
`.cargo_vcs_info.json`. The archive's crate sources match the current draft,
but this provenance is not clean-source release evidence. Do not rebuild or
attempt to republish 0.2.0 with different bytes. Because the candidate gate
requires clean provenance for both Cargo archives and the project keeps the
Cargo and Python versions synchronized, the next candidate uses 0.2.1 for the
lifecycle crate, server crate, and PyPI distribution. HTTP/3 has no separate
project-owned package.

## Release workflow model

The release flow uses the staged artifact model in the
[Pillow-RS release workflow](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/release.yml)
and its
[separate documentation workflow](https://github.com/appunni-m/pillow-rs/blob/main/.github/workflows/docs.yml):
validate an immutable source identity, build and verify artifacts once, carry
checksummed artifacts between jobs, and isolate publishing permissions from
build and test jobs.

This repository adapts that pattern for the next release. The Release candidate
workflow (`candidate.yml`) does not publish. The manual Release workflow
(`release.yml`) defaults to prepare-only, revalidates the exact tag and candidate
artifact, and grants short-lived OIDC publishing permission only to selected
publisher jobs. The bootstrap audit preserves four historical Cargo
publication records. The maintainer removed the old `uvicorn-rs` release and is
removing the `uvicorn-rs-h3` and `uvicorn-rs-h3-quinn` identities; current API
lookups for those three names return HTTP 404. Do not publish separate H3 or
Quinn crates. Recheck `uvicorn-rs` name availability before a future Cargo
release. Configure Trusted Publishing for the two current crate identities
before using Cargo publisher jobs. No release workflow creates or moves a tag.

Release direction (2026-10-25): the maintainer authorized a coordinated Cargo
and PyPI release and specified local Cargo publication first. Publish
`asgi-lifespan-protocol-rs` before its dependent `uvicorn-rs`, verify both
registry artifacts, then publish PyPI `uvicorn-rs`. The local workflow still
offers `prepare-only`, `cargo`, `pypi`, and `cargo-and-pypi`; its combined path
waits for the Cargo publisher jobs before publishing to PyPI, but it does not
replace the requested local first publication. This does not bypass candidate
gates: release still requires a clean tagged commit on `main`, a successful
exact candidate artifact, all required release evidence, configured publisher
trust, and the typed confirmation.

Local Cargo candidate status (2026-10-25): the clean 0.2.1 archives were built
with Cargo 1.85.0 from commit `7754895262c7b1d7baa2e9595277a81607634d38`.
`asgi-lifespan-protocol-rs` contains 9 files and has SHA-256
`cd5b25c7629a0d32a31babc5fc95e16fe5e6731080620dfff40409388d09051b`; `uvicorn-rs`
contains 72 files and has SHA-256
`b734ee2131a5abb48f368fa0a16896b43fd397f3de26841ff7d16d46626d8461`. The
local standalone H3 archive consumer passed against those exact archives,
observing H3 error 262 and a successful request on a fresh connection. These
are local candidate artifacts, not the exact-main candidate workflow bundle.
The current checkout has uncommitted edits, including server Rust source, so
these archive hashes remain bound to the clean commit above and do not describe
the current dirty worktree. That commit has no hosted candidate workflow
result.
The local `cargo publish` attempt for `asgi-lifespan-protocol-rs 0.2.1` was
rejected with HTTP 403 because the configured token lacks publish permission;
the version remains absent and no upload occurred. Do not retry until local
Cargo credentials are refreshed. The PyPI wheel and sdist have not been built.

GitHub release-control audit (2026-10-25): the repository has an active
[`Protect main` ruleset](https://github.com/appunni-m/uvicorn-rs/rules/25771026)
(ID `25771026`) scoped to `refs/heads/main`. It blocks branch deletion and
force-pushes, requires pull requests and ten named status checks, and grants no
bypass. The ruleset requires zero approving reviews and does not require the
branch to be up to date with its base, so those additional review/freshness
protections are not enabled. No tag ruleset was found, and the classic
protected-tags page had no entries; release-tag protection remains unverified.

GitHub's `pypi` environment was inspected in repository Settings on
2026-10-25. Deployments are restricted to `main`; Required reviewers is enabled
with `appunni-m` as the sole reviewer; Prevent self-review is disabled so the
sole maintainer can approve a deployment; and the environment has no secrets
or variables. Add a distinct eligible reviewer when another maintainer joins.
The maintainer reports the pending PyPI Trusted Publisher tuple as project
`uvicorn-rs`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`, and
environment `pypi`. These observations confirm configuration only. The local
Cargo archive hashes and standalone H3 archive consumer are verified, but the
exact-main candidate workflow bundle, PyPI distributions, registry visibility
and consumer checks, crates.io publisher setup, and the remaining release
acceptance gates are outstanding. No release tag or PyPI package has been
published.
Registry check (2026-10-25): `asgi-lifespan-protocol-rs` 0.2.0 is visible with
the checksum and dirty-source provenance recorded above. API lookups for
`uvicorn-rs`, `uvicorn-rs-h3`, and `uvicorn-rs-h3-quinn` return HTTP 404. The
`uvicorn-rs` name's reuse or publication eligibility has not been tested; the
previous cooldown timestamp has passed, so do not rely on the old cooldown
statement. Verify availability before any future Cargo publish.

### Cargo bootstrap publication record

The following historical `0.1.0` archives were published from clean commit
`9eccb4fb8c7f27269e99c3af194feb4a2a8f7709`. Each registry checksum was checked
against the exact local archive after upload. Current crates.io API lookups for
these old names return HTTP 404; retain this as publication history, not as a
claim that the versions remain available from the registry:

| Crate | Registry | SHA-256 |
|---|---|---|
| `native-app-contract` | crates.io (historical; no longer API-resolvable) | `ceaa890b28b5587e45ef8740dc8530e172dcfca18a96c5ea9e25260d02531ba0` |
| `uvicorn-rs-h3` | crates.io (historical; no longer API-resolvable) | `809379da49a0f299dfd0a88c69ab0e0a948e806edbfbcc087e3e358783b52ae7` |
| `uvicorn-rs-h3-quinn` | crates.io (historical; no longer API-resolvable) | `a5b2a3fc559156fbf948fd4838e5c2ed860223add8bfd2ce376cc4d5b2306375` |
| `uvicorn-rs` | crates.io (historical; no longer API-resolvable) | `064b0037134e06a7eb16aa4cbd967c5ac2ecdeb5418ba5a71552809e46f485ce` |

These rows preserve the verified publication checksums from the historical
bootstrap; current crates.io API lookups for these names return HTTP 404. Cargo
archives include the source commit in `.cargo_vcs_info.json`; a candidate built
from a later commit will have different archive bytes even if crate sources did
not change. Do not treat the historical records as proof that the full
compatibility, coverage, or performance gates passed.

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

1. Recheck the live `main` ruleset and decide the required review policy; enable
   up-to-date checks if desired, and verify a tag ruleset that prevents
   unauthorized version-tag creation or mutation while allowing the authorized
   release maintainer. Configure and verify crates.io Trusted Publishing for
   both current crate identities.
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
[Release candidate workflow](https://github.com/appunni-m/uvicorn-rs/blob/main/.github/workflows/candidate.yml) assembles a
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

The candidate includes three Python wheels, a source distribution, two Cargo
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

The maintainer authorized Cargo and PyPI publication together. The combined
`cargo-and-pypi` path keeps both Cargo jobs gated on registry preflight and the
verified candidate, then permits PyPI publication only after the Cargo jobs
finish successfully or are skipped because the exact bytes already exist.

The separate
[Release workflow](https://github.com/appunni-m/uvicorn-rs/blob/main/.github/workflows/release.yml) is dispatched
from main with an existing annotated tag. It defaults to prepare-only and
requires the exact typed confirmation PUBLISH vX.Y.Z before publication.

Prepare-only verifies the tag, exact candidate artifact and checksum manifest,
package contents, version, and registry state. Publication requires a separate
explicit maintainer decision. Do not publish from a dirty checkout or bypass a
failed candidate gate.

### Cargo Trusted Publishing setup

The lifecycle crate `asgi-lifespan-protocol-rs` 0.2.0 has been published and
an isolated consumer check was previously reported as passing. The registry
archive's `dirty: true` source provenance means that check does not establish a
clean-source release artifact. Its exact registry checksum must be recognized
before reusing the version; publishing different bytes as 0.2.0 is not valid.
The clean candidate therefore uses 0.2.1 for both Rust crates and the PyPI
distribution so its source provenance and synchronized version checks match
the exact reviewed commit.
The earlier `uvicorn-rs` release was removed by the maintainer; the current
crates.io API returns 404 for the name. Recheck name availability immediately
before publication. crates.io requires the first release of a crate to be
published manually before Trusted Publishing can be configured ([crates.io
team guidance](https://blog.rust-lang.org/2025/07/11/crates-io-development-update-2025-07/)).
After all candidate gates pass, bootstrap `uvicorn-rs` 0.2.1 from the exact
clean candidate using a secure local Cargo credential, publish the lifecycle
dependency first, and compare each registry checksum with the candidate. Then
configure Trusted Publishing for both crate identities. The combined workflow
will publish PyPI only after Cargo jobs succeed or are skipped because the
exact candidate bytes are already visible.

After the candidate gates pass and the maintainer authorizes release, verify
the candidate bundle's `SHA256SUMS`, compare the server `.crate` byte-for-byte
with a clean package build, then publish only after the name-reuse window opens.
Use a narrowly scoped, short-lived maintainer credential through an approved
local credential provider; do not put it in workflow inputs or GitHub secrets.
Configure crates.io Trusted Publishing for the current crate identities with
owner `appunni-m`, repository `uvicorn-rs`, workflow `release.yml`, and
environment `crates-io` where required.

### First PyPI publication

The pending PyPI Trusted Publisher for `uvicorn-rs` is configured with owner
`appunni-m`, repository `uvicorn-rs`, workflow `release.yml`, and environment
`pypi`. No PyPI version has been
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
| Cargo archives | Inventories for the lifecycle contract and `uvicorn-rs`, normalized metadata, project and vendored licenses, safe extraction, locked compilation with HTTP/3 off and on, and the standalone H3 consumer. |

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
