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

## Current release status (2026-10-26)

`asgi-lifespan-protocol-rs` 0.2.1 and `uvicorn-rs` 0.2.1 have been published
to crates.io from clean commit
`d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`. Their archive SHA-256 values are
`44adef2e2648be1514aebe33ddc1dcc5267dae67abd8d31f1aff7ded7ce16235` and
`0662828f3f852f4960a034e734b2a281765e40b29388d4e8469230e5d4e52fcf`,
respectively. The server archive was reproduced with registry dependency
resolution after removing the workspace path patch from candidate packaging.
The PyPI distribution `uvicorn-rs` 0.2.1 has not been uploaded.

This is a Cargo publication, not a completed project release. PR #19 remains a
draft; its current full coverage job is still running on the PR branch. The
exact-main coverage gate, independent Coverage-MCP receipt, complete three-
system benchmarks, compatibility gates, exact-main candidate bundle, and clean
downstream consumers remain open. `release.yml` only publishes from `main`
after it verifies the tagged candidate and all attached evidence. Do not call
the local Cargo publication a verified PyPI release candidate.

## Distribution boundaries

| Channel | Distribution | Scope |
|---|---|---|
| Cargo | asgi-lifespan-protocol-rs, uvicorn-rs | Python-free Rust libraries. HTTP/3 protocol and Quinn transport code ship inside `uvicorn-rs` behind its `http3` feature. |
| PyPI | uvicorn-rs | Optional Python compatibility client for standard Python ASGI applications. It is not required by the Python-free Rust library. |
| Documentation | README, MkDocs site, and docs.rs | Repository docs deploy through GitHub Pages; crate API docs are generated from published Cargo archives. |

The confirmed PyPI distribution name is `uvicorn-rs`, following the project's `pillow-rs` naming convention. It provides the `uvicorn` import namespace, `uvicorn` command, and `python -m uvicorn` entry point for in-place use. The root Cargo/PyO3 integration package remains `uvicorn-rs-py` internally; that is not the PyPI distribution name. The package also retains its `uvicorn-rs-py` console alias. The exact compatibility scope is recorded in the [support matrix](support-matrix.md); these names do not imply full Uvicorn parity. The Cargo and Python package versions are 0.2.1. The two 0.2.1 Cargo crates have been published as recorded above; the PyPI distribution remains unpublished. Local artifacts from earlier source commits are retained below as historical evidence and are not the exact-main workflow bundle.

The historical 0.1.0 Cargo bootstrap is recorded below. A registry API check on 2026-10-25 returned HTTP 404 for the then-removed `uvicorn-rs`, `uvicorn-rs-h3`, and `uvicorn-rs-h3-quinn` names; the subsequent `uvicorn-rs` 0.2.1 publication is recorded above. The old H3/Quinn package identities are not current release targets. The `uvicorn-rs` package vendors the H3 protocol and Quinn adapter source behind `http3`; it does not depend on separate project-owned H3 crates. `asgi-lifespan-protocol-rs` is the current lifecycle-contract package. The Python adapter depends on `uvicorn-rs`; Rust-native frameworks can depend on `uvicorn-rs` without Python.

The Cargo workspace packages and Python package declare version 0.2.1. The
Cargo archives are published; the PyPI version is still absent.
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
attempt to republish 0.2.0 with different bytes. The synchronized 0.2.1 Cargo
archives have now been published with clean provenance; PyPI `uvicorn-rs` 0.2.1
remains the pending first distribution. HTTP/3 has no separate project-owned
package.

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
publication records. Do not publish separate H3 or Quinn crates. The 0.2.1
Cargo crates were published manually from a clean source commit; crates.io
Trusted Publishing is not yet verified for future Cargo publisher jobs. No
release workflow creates or moves a tag.

Release direction (2026-10-25): the maintainer authorized a coordinated Cargo
and PyPI release and specified local Cargo publication first. The local
publication was completed on 2026-10-26: `asgi-lifespan-protocol-rs` was
published before its dependent `uvicorn-rs`, and both registry artifacts were
verified. PyPI `uvicorn-rs` remains pending. The local workflow offers
`prepare-only`, `cargo`, `pypi`, and `cargo-and-pypi`; its combined path waits
for the Cargo publisher jobs before publishing to PyPI. This does not bypass candidate
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
were local candidate artifacts, not the exact-main candidate workflow bundle.
At that earlier preflight, the checkout also had uncommitted server source, so
those hashes did not describe its dirty worktree or the subsequently published
archives.
The first local `cargo publish` attempt for `asgi-lifespan-protocol-rs 0.2.1`
was rejected with HTTP 403 because the configured token lacked publish
permission. After the maintainer saved a replacement token through Cargo's
login prompt, both 0.2.1 crates were published locally. The successful
publication checksums and `.cargo_vcs_info.json` source commit are recorded in
the current status above; this supersedes the earlier failed attempt.

### Current candidate state (2026-10-26)

The local branch is `codex/uvicorn-rs-consolidation` at
`9b6b766bf07349556a0226b5ea5cd06af1437893`; it is one local commit ahead of
the pushed PR head `d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`. `origin/main` is
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. PR #19 is open and draft, and no
version tag exists. The local commit removes the Cargo workspace path patch
from release packaging so the archive can match registry bytes. CI run
[`40267125476`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40267125476)
is running on the pushed PR head: Rust quality, native FastAPI composition,
installed-wheel parity (500/500), release-contract, and MSRV jobs passed; the
complete three-repeat coverage job is still in progress. This PR run does not
meet the release workflow's requirement for a tagged exact-main candidate.

Latest local PyPI artifact check (2026-10-26): `uv build
--out-dir target/release-candidate/pypi` built the sdist
`uvicorn_rs-0.2.1.tar.gz` (SHA-256
`978321f9caa54d0708a19f7635ca7c5e6c95ab75e6eb669168baa1f132590fed`) and the
macOS ARM64 abi3 wheel
`uvicorn_rs-0.2.1-cp39-abi3-macosx_11_0_arm64.whl` (SHA-256
`5631ff719daf284403b19db4824e0a8618b4acbedcf9a635ef33e60fc529359d`). Both
declare PyPI name `uvicorn-rs` and version 0.2.1. An isolated CPython 3.13.14
environment installed the wheel; the `uvicorn` namespace and native extension
resolved inside that environment, and both `uvicorn --version` and
`python -m uvicorn --version` succeeded with compatibility version 0.54.0.
These local artifacts came from the dirty checkout and do not replace the
exact-main, multi-platform candidate bundle or its clean registry-consumer
receipts.

The earlier dirty-checkout package preflight hashes above are not registry
artifacts. The published 0.2.1 crates instead have the checksums and clean
source provenance recorded at the top of this guide. A registry-resolving
`cargo package --no-verify --locked --offline` build reproduced the published
`uvicorn-rs` checksum after the path patch was removed. The package archives
are registry-visible, but exact-main candidate verification and clean
downstream consumer receipts remain outstanding.

Hosted benchmark run
[`40228012455`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455)
has completed with failure. It used earlier branch commit
`7811b2392b60cd8eadc8a951c1eff47d57ace2d6`: Linux x86-64 passed its parity and
category job; macOS ARM64 stopped before timing after an oracle-side timeout in
`websocket-tls.text-round-trip-with-query-and-subprotocol` (468 cases passed,
one infrastructure failure, one not run); Linux ARM64 passed parity and the
FastAPI comparison, then failed the HTTP/3 `large-response` correctness gate
against Hypercorn asyncio in repetition 2 after receiving 904,262 bytes instead
of the expected 1,048,576. Its checkpoint has no completed HTTP/3 report. The
same selected macOS parity case passed once locally, but this does not establish
the hosted timeout's cause. The run's Linux ARM64 HTTP/1 artifact contains 20
timing-valid, zero-failure `fastapi-upload-1m-write-1k` rows at concurrency 8;
the earlier upload timeout was not reproduced, and its cause remains unknown.
There is no validated three-system aggregate or release performance claim. On
`main` commit
`86e72e181d00feca1b4db7f30377d5d9d4345b83`, unified coverage run
[`39689988928`](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988928)
reported 10,962/11,375 regions and 8,130/8,438 lines, below the 100% gate. No
accepted independent Coverage-MCP receipt is bound to that exact source. No
clean candidate artifact or consumer receipt is bound to the current branch
commit. At the time of that historical main-commit audit, no Cargo or PyPI
upload had occurred; the later local Cargo publications are recorded above.

The earlier full pull-request coverage run
[`40237012947`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40237012947)
used PR head `35e548f08d1a4248488fc1351ed8850e7c80f23c` and reported
12,502/12,711 regions and 9,280/9,415 lines. Coverage-MCP did not accept its
synthetic-merge source revision as an independent receipt for the exact local
checkout. The focused cases added since that run are not a replacement for a
new complete coverage run.

The newer PR run [`40267125476`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40267125476)
is still executing its full three-repeat coverage job on commit
`d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`; its report and independent
Coverage-MCP handoff are not yet available.

Registry state (2026-10-26): both Cargo 0.2.1 crates are published and their
registry checksums match the values recorded above. PyPI returns HTTP 404 for
`uvicorn-rs` 0.2.1, so the first PyPI upload remains pending.

GitHub release-control audit (2026-10-26): the repository has an active
[`Protect main` ruleset](https://github.com/appunni-m/uvicorn-rs/rules/25771026)
(ID `25771026`) scoped to `refs/heads/main`. It blocks branch deletion and
force-pushes, requires pull requests and ten named status checks, and grants no
bypass. The ruleset requires zero approving reviews and does not require the
branch to be up to date with its base, so those additional review/freshness
protections are not enabled. The active
[`Protect version tags` ruleset](https://github.com/appunni-m/uvicorn-rs/settings/rules/25819488)
(ID `25819488`) targets `refs/tags/v*`. It allows creating matching tags while
blocking updates, deletion, and force-pushes; its bypass list is empty. GitHub
Settings currently reports zero matching tags.
The classic protected-tags page has no entries.

The `crates-io` and `pypi` GitHub environments were inspected in repository
Settings on 2026-10-26. Both require `appunni-m` as reviewer, allow the sole
maintainer to approve by disabling Prevent self-review, and restrict deployments
to `main`. Administrator bypass is disabled, and neither environment has
secrets or variables. Add a distinct eligible reviewer when another maintainer
joins. The maintainer reports the PyPI Trusted Publisher tuple as project
`uvicorn-rs`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`, and
environment `pypi`; the pending publisher record has not been verified through
a publication. crates.io Trusted Publishing setup remains unverified. The local
Cargo archive hashes and standalone H3 archive consumer are verified, but the
exact-main candidate workflow bundle, the PyPI distribution, and clean
consumer checks remain outstanding. The two Cargo 0.2.1 packages have been
published locally; no release tag or PyPI publication has occurred.
Historical registry check (2026-10-25): `asgi-lifespan-protocol-rs` 0.2.0 was
visible with the checksum and dirty-source provenance recorded above. API
lookups for `uvicorn-rs`, `uvicorn-rs-h3`, and `uvicorn-rs-h3-quinn` returned
HTTP 404 before the 0.2.1 publication. This snapshot is superseded by the
current registry state above.

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
The clean 0.2.1 archives for both Rust crates have now been published manually
and their registry checksums are recorded above. This satisfies the first
manual-publish requirement for enabling crates.io Trusted Publishing, but that
publisher configuration remains unverified. Do not try to publish different
0.2.1 bytes. Future Cargo versions should use a new candidate version, compare
its archive checksums with the registry, and configure Trusted Publishing for
the two current crate identities. The combined workflow will publish PyPI only
after Cargo jobs succeed or are skipped because the exact candidate bytes are
already visible.

For future Cargo releases, verify the candidate bundle's `SHA256SUMS` and
compare the server `.crate` byte-for-byte with a clean package build. Use a
narrowly scoped, short-lived maintainer credential through an approved local
credential provider; do not put it in workflow inputs or GitHub secrets.
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
