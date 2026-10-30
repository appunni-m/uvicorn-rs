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

## Current release gates (2026-10-30)

The release set is one Python-free **uvicorn-rs** server crate with HTTP/3
behind its optional **http3** feature, the separate
**asgi-lifespan-protocol-rs** crate, and the PyPI distribution **uvicorn-rs**
implemented by the optional internal **uvicorn-rs-py** adapter. The publisher
is **.github/workflows/release.yml**; **candidate.yml** only builds and verifies
candidates. The PyPI trusted publisher is **appunni-m/uvicorn-rs / release.yml
/ pypi**. Both crates.io Trusted Publisher entries already exist for
**appunni-m/uvicorn-rs / release.yml / crates-io**. The user confirmed the
lifecycle publisher is already configured; do not add duplicates.

PR #19 remains a draft. The current branch is
`codex/uvicorn-rs-consolidation` at **872d0d6ff770d5815a250d39fac2dfb66d70c0e3**;
it has not been merged to `main` at
**86e72e181d00feca1b4db7f30377d5d9d4345b83**. The latest completed full
candidate/parity CI run is
[#489](https://github.com/appunni-m/uvicorn-rs/actions/runs/40999924044),
from older commit `27733501e05cda09b11ce5b28cc22e51e4c4d1ff`. Linux candidate,
composition, Rust quality, and MSRV jobs passed. macOS parity had one WSGI
module-CLI log-event failure. Windows parity passed 682 cases, failed six
multi-worker shutdown cases, recorded six infrastructure errors, and left two
TLS cases unrun. Its unified coverage job completed all 1,331 cases but failed
the 100% gate at 14,033/14,203 regions and 10,340/10,424 lines. These outcomes
do not qualify the current branch.

Focused Windows follow-ups passed the six selected worker cases 6/6 in
[#492](https://github.com/appunni-m/uvicorn-rs/actions/runs/41006402856) and
the TLS stream-drain case 1/1 in
[#493](https://github.com/appunni-m/uvicorn-rs/actions/runs/41007521764). Three
Windows HTTP/3 cases passed in
[#495](https://github.com/appunni-m/uvicorn-rs/actions/runs/41008650687), but
the valid report records three cleanup infrastructure errors: two Hypercorn
log files remained locked after their server processes exited, and the profile
temp directory then failed to clean up. The current working change asks the
Hypercorn oracle to shut down gracefully on Windows. Focused CI
[#496](https://github.com/appunni-m/uvicorn-rs/actions/runs/41009518264), on the
current branch commit above, passed the same three HTTP/3 cases with zero failed,
not-run, or infrastructure cases. Its parity report is artifact 12956958252
(SHA-256 `fbd1a1c796b00bbd58ab891cf011780d310e1e951bc1bcc7f644d67b86dc093e`);
the `parity.json` SHA-256 is
`dafe3010594bcd56b6363968b31f948319f2e1c57391631f0fe4686b0c17cf7c`. These
focused runs are not full parity. The newest full coverage measurement on the
branch is #489, above; the earlier `main` report from
[#39689988928](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988928):
10,962/11,375 regions and 8,130/8,438 lines. It is not bound to the current
branch. No full parity or coverage run has yet qualified current commit
`872d0d6ff770d5815a250d39fac2dfb66d70c0e3`, and no accepted independent
Coverage-MCP review exists for it.

The full benchmark run
[#39689988939](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988939)
is incomplete: Linux x86-64 and macOS ARM64 passed, while Linux ARM64 failed in
Hypercorn's HTTP/3 slow-reader case. The HTTP/1 upload timeout also remains
unresolved. Current FastAPI results do not establish a broad speed gain; one
route was slower. Do not repeat the benchmark matrix until parity is complete.

The last saved GitHub settings audit found active **Protect main** and
**Protect version tags** rulesets. Main requires pull requests and configured CI
checks with zero required approvals for the sole maintainer. Version tags
`v*` allow creation while blocking updates, deletion, and force-push. The
`pypi` and `crates-io` environments are restricted to `main`; `appunni-m` is
the reviewer and self-review is allowed for the sole maintainer. Do not publish
until exact-source coverage, independent review, full compatibility, completed
parity-first benchmarks, and candidate artifacts/consumers pass.

Direct registry API checks on 2026-10-30 show crates.io versions
`uvicorn-rs` 0.2.1 and `asgi-lifespan-protocol-rs` 0.2.1 as current, while
PyPI returns 404 for `uvicorn-rs`. The 0.2.1 Cargo releases are registry-visible
from an earlier source; they are not evidence for the current branch. The
current source declares 0.2.2, but there is no clean exact-source candidate,
no 0.2.2 tag or package, and no first PyPI upload. Verify candidate bytes and
consumers before dispatching the authorized release workflow.

## Registry and packaging audit (2026-10-27; earlier source snapshot)

The published Cargo versions are `asgi-lifespan-protocol-rs` 0.2.1 and
`uvicorn-rs` 0.2.1, both from clean commit
`d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`. Their archive SHA-256 values are
`44adef2e2648be1514aebe33ddc1dcc5267dae67abd8d31f1aff7ded7ce16235` and
`0662828f3f852f4960a034e734b2a281765e40b29388d4e8469230e5d4e52fcf`,
respectively. A current registry lookup still reports 0.2.1 as the newest
version for each crate. PyPI has no `uvicorn-rs` project release yet. The old
`uvicorn-rs-h3` and `uvicorn-rs-h3-quinn` names return 404 and are not release
targets.

The local draft targets version 0.2.2. The release-version check passes for the
PyPI distribution, private root adapter, both Cargo crates, and lockfiles.
Cargo metadata lists only `asgi-lifespan-protocol-rs` and `uvicorn-rs` as
publishable workspace packages; dirty-source package file lists were inspected
for both. These checks do not make the current artifacts upload-eligible: the
checkout is on `codex/uvicorn-rs-consolidation` at
`5b1ec29201c963d8590c989b07318bb7366d7922` with 132 changed or untracked
entries, and there is no clean 0.2.2 candidate or tag.

On exact `main` commit `86e72e181d00feca1b4db7f30377d5d9d4345b83`, unified
coverage CI run
[`39689988928`](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988928)
reported 10,962/11,375 regions and 8,130/8,438 lines. The later dirty-branch
PR receipt `40317129093` applies to an earlier snapshot: subsequent edits to
`src/lib.rs`, `crates/uvicorn-rs/src/lib.rs`, and
`crates/uvicorn-rs/src/websocket.rs` changed its source identity. Current-source
selected receipts pass the HTTP/1.0 concurrency case, invalid-DER CA rejection,
and compressed WebSocket close-without-code case 1/1 each. Two accepted Yawc
session error contracts also passed 2/2 in
`target/asgi-coverage/coverage-yawc-session-errors-final-20261027.json`; this
is selected-case evidence, not full-suite coverage. The later Rust error-mapping
fix, WebSocket close-path simplification, and parity input additions make the
earlier full draft report stale for the current source and inventory; full
coverage and an accepted independent Coverage-MCP review are still required.

Benchmark run
[`39689988939`](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988939)
is incomplete: Linux x86-64 and macOS ARM64 passed, while Linux ARM64 failed in
Hypercorn's HTTP/3 slow-reader case. The earlier HTTP/1 upload timeouts were not
reproduced by later exact-main rows, but the retained failing logs do not show
the first cause. The 2026-10-27 host snapshot showed heavy contention, so no
clean local timing reproduction was started.
The results do not establish a general FastAPI performance gain. Docs run
[`39689989003`](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689989003)
passed for the committed source, but the current draft documentation still
needs a clean release build. Full Uvicorn compatibility, a clean exact-source
candidate, clean downstream consumers, full coverage, accepted Coverage-MCP
review, and complete three-system benchmarks remain open.

The maintainer confirmed that the exposed Cargo token was revoked. The
2026-10-27 crates.io account audit showed no generated API tokens; do not
request or reuse the revoked token. The initial 2026-10-27 crate-settings audit
found no Trusted Publisher entries. Authenticated checks of both crate settings
pages confirmed entries for owner `appunni-m`, repository
`appunni-m/uvicorn-rs`, workflow `release.yml`, and environment `crates-io`.
The `release.yml` Cargo jobs use that environment and GitHub OIDC. The `crates-io`
and `pypi` GitHub environments are restricted to `main`, require reviewer
`appunni-m`, allow the sole maintainer to approve (Prevent self-review is off),
disable administrator bypass, and contain no secrets or variables. The PyPI
pending publisher is for project `uvicorn-rs`, repository `appunni-m/uvicorn-rs`,
workflow `release.yml`, and environment `pypi`.

No 0.2.2 package or tag has been published. The release workflow remains
blocked until the exact-source evidence gates pass and clean candidate artifacts
and consumers are verified.

## Distribution boundaries

| Channel | Distribution | Scope |
|---|---|---|
| Cargo | asgi-lifespan-protocol-rs, uvicorn-rs | Python-free Rust libraries. HTTP/3 protocol and Quinn transport code ship inside `uvicorn-rs` behind its `http3` feature. |
| PyPI | uvicorn-rs | Optional Python compatibility client for standard Python ASGI applications. It is not required by the Python-free Rust library. |
| Documentation | README, MkDocs site, and docs.rs | Repository docs deploy through GitHub Pages; crate API docs are generated from published Cargo archives. |

The confirmed PyPI distribution name is `uvicorn-rs`, following the project's `pillow-rs` naming convention. It provides the `uvicorn` import namespace, `uvicorn` command, and `python -m uvicorn` entry point for in-place use. The root Cargo/PyO3 integration package remains `uvicorn-rs-py` internally; that is not the PyPI distribution name. The package also retains its `uvicorn-rs-py` console alias. The exact compatibility scope is recorded in the [support matrix](support-matrix.md); these names do not imply full Uvicorn parity. Cargo 0.2.1 was published from an earlier source commit, so the current-source candidate is synchronized to version 0.2.2. The Cargo manifests, Python project metadata, and lockfiles now say 0.2.2 in the local checkout, and the version synchronization check passes. Inspection artifacts were built from dirty HEAD `5b1ec29201c963d8590c989b07318bb7366d7922`: both Cargo archives, the PyPI sdist, and one macOS ARM64 abi3 wheel. Extracted-archive default and `http3` consumers and isolated Python install/import/CLI checks passed. The Cargo archives record `dirty: true`, so these are not clean, upload-eligible candidate artifacts. PyPI remains unpublished; no clean exact-source candidate or tag has been verified.

The historical 0.1.0 Cargo bootstrap is recorded below. A registry API check on 2026-10-25 returned HTTP 404 for the then-removed `uvicorn-rs`, `uvicorn-rs-h3`, and `uvicorn-rs-h3-quinn` names; the subsequent `uvicorn-rs` 0.2.1 publication is recorded above. The old H3/Quinn package identities are not current release targets. The `uvicorn-rs` package vendors the H3 protocol and Quinn adapter source behind `http3`; it does not depend on separate project-owned H3 crates. `asgi-lifespan-protocol-rs` is the current lifecycle-contract package. The Python adapter depends on `uvicorn-rs`; Rust-native frameworks can depend on `uvicorn-rs` without Python.

The published Cargo workspace packages are 0.2.1. The local candidate
manifests declare 0.2.2. Dirty-source inspection artifacts exist as described
above; no clean candidate archives are verified. PyPI 0.2.2 is absent.
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
Cargo crates were published manually from a clean source commit. The current
crates.io settings confirm per-crate Trusted Publisher entries for owner
`appunni-m`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`, and
environment `crates-io`. The 0.2.2 path uses the staged `release.yml` OIDC jobs.
No long-lived Cargo token is needed for that path.
No release workflow creates or moves a tag.

Release direction (2026-10-25): the maintainer authorized a coordinated Cargo
and PyPI release and specified local Cargo publication first. The 0.2.1 local
publication was completed on 2026-10-26: `asgi-lifespan-protocol-rs` was
published before its dependent `uvicorn-rs`, and both registry artifacts were
verified. PyPI `uvicorn-rs` remains pending. Dirty-source 0.2.2 inspection
artifacts have been prepared, but no clean current-source candidate has passed
its release gates. The local workflow offers
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

### Candidate state (2026-10-26; historical)

The local branch is `codex/uvicorn-rs-consolidation` at
`dcfb66dcbe73217af730fbec08723cf38499106`, two local commits ahead of the
pushed PR head `d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`; the worktree is
dirty. `origin/main` is `86e72e181d00feca1b4db7f30377d5d9d4345b83`. PR #19 is
open and draft, and no version tag exists. A local commit removes the Cargo
workspace path patch from release packaging so the archive can match registry
bytes. CI run [`40267125476`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40267125476)
completed: Rust quality, native FastAPI composition, installed-wheel parity
(500/500), release-contract, and MSRV passed; coverage failed. Its report
records merge revision `a8bb19f9333ced7a6cbd65b0aeaefb340eee0d77`, while the
artifact is associated with PR head `d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`;
the seven measured Rust source-file hashes match that head. The current dirty
worktree changes `src/lib.rs` and `crates/uvicorn-rs/src/websocket.rs`, so the
hosted report does not cover the current local source. This PR run does not
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

The retained coverage artifact for PR run
[`40267125476`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40267125476)
has report SHA-256
`75e3f167b3735a630848c739ad350afc47c49d63986cbf223fbf3982c47a084f` and build
ID `64316cd3913dd0ef86ee149e98bf9abdf8d13ecba4f0df8a88dd379af675f5ff`. It
reports 12,676/12,879 regions and 9,418/9,539 lines across 57 uncovered
function groups; the source-hash-verified PR head has 203 regions and 121 lines
to cover. All 1,061 attributed cases passed, with three verification runs
recorded. Coverage-MCP remains `awaiting_query`; its exact-main report query
timed out after 60 seconds, so there is no independent receipt. The local
selected WebSocket and Python API coverage reports cover only their selected
cases and do not replace a full report for the current dirty source.

Registry state (2026-10-26): both Cargo 0.2.1 crates are published and their
registry checksums match the values recorded above. PyPI returns HTTP 404 for
`uvicorn-rs` 0.2.1, so the first PyPI upload remains pending.

GitHub release-control audit (verified in Chrome on 2026-10-27): the repository has an active
[`Protect main` ruleset](https://github.com/appunni-m/uvicorn-rs/rules/25771026)
(ID `25771026`) scoped to `refs/heads/main`. It blocks branch deletion and
force-pushes, requires pull requests and ten named GitHub Actions status
checks, and grants no bypass. It requires zero approving reviews and does not
require the branch to be up to date with its base. Those settings allow the
sole maintainer to merge while keeping PR and CI gates; add a reviewer when
another maintainer joins. The active
[`Protect version tags` ruleset](https://github.com/appunni-m/uvicorn-rs/settings/rules/25819488)
(ID `25819488`) targets `refs/tags/v*`. It allows creating matching tags while
blocking updates, deletion, and force-pushes; its bypass list is empty. The
ruleset currently matches zero tags. The classic protected-tags page has no
entries.

The `crates-io` and `pypi` GitHub environments were verified in repository
Settings on 2026-10-27. Both require `appunni-m` as reviewer, allow the sole
maintainer to approve by disabling Prevent self-review, and restrict deployments
to `main`. Administrator bypass is disabled, and neither environment has
secrets or variables. Add a distinct eligible reviewer when another maintainer
joins. The PyPI Trusted Publisher tuple is project
`uvicorn-rs`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`, and
environment `pypi`; the pending publisher record has not been verified through
a publication. Both crates.io Trusted Publisher entries are now verified as
recorded above. The local Cargo archive hashes and standalone H3 archive
consumer are verified, but the exact-main candidate workflow bundle, PyPI
distribution, and clean consumer checks remain outstanding. The two Cargo
0.2.1 packages have been published locally; no release tag or PyPI publication
has occurred.
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

This guide describes the release gates. The dated status above is a snapshot,
not a live status feed. Check the GitHub Actions runs and retained artifacts
for the exact clean `main` commit under review. Do not rely on a run for an older
commit, a partial matrix, or a status snapshot copied into documentation.
Missing or expired artifacts
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

1. Keep the verified `Protect main` and `Protect version tags` rulesets in
   force. The main ruleset currently requires PRs and ten CI checks with zero
   approving reviews and no up-to-date requirement; the tag ruleset allows new
   `v*` tags and blocks updates, deletion, and force-pushes. Both crates.io
   Trusted Publisher entries are verified for the current crate identities.
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
manual-publish requirement for enabling crates.io Trusted Publishing. The
current settings pages show the same Trusted Publisher entry on each crate:
owner `appunni-m`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`,
and environment `crates-io`. Do not try to publish different 0.2.1 bytes. The
combined workflow will publish PyPI only after Cargo jobs succeed or are
skipped because the exact candidate bytes are already visible.

For future Cargo releases, verify the candidate bundle's `SHA256SUMS` and
compare each `.crate` byte-for-byte with a clean package build. The selected
`release.yml` path uses the verified per-crate crates.io Trusted Publisher
entries for owner `appunni-m`, repository `appunni-m/uvicorn-rs`, workflow
`release.yml`, and environment `crates-io`. Do not put a long-lived
Cargo token in workflow inputs or GitHub secrets. If the OIDC publisher is not
available, stop and resolve that setup before releasing.

### First PyPI publication

The PyPI Trusted Publisher for `uvicorn-rs` is configured with owner
`appunni-m`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`, and
environment `pypi`. No PyPI version has been uploaded. Recheck the project name
before publication. The publish
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
