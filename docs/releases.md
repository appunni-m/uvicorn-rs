# Release guide

This guide defines how to prepare and publish uvicorn-rs releases.
Candidate qualification and registry/GitHub publication run as an automated
tag-triggered workflow chain. Documentation deployment remains a separate
workflow. A successful build alone is not a published release.

Use these state labels precisely:

- **Prepared:** source or workflow is ready for a later gate.
- **CI-proven:** the exact clean commit passed the named hosted checks.
- **Published:** the registry or GitHub Release accepted the artifact.
- **Registry-visible:** the exact version can be resolved from the registry.
- **Consumer-verified:** an isolated downstream project installed and exercised
  the exact published version.
- **Released:** the authorized distribution decision and required verification
  are complete.

<a id="current-release-gates-2026-11-04"></a>
<a id="current-release-gates-2026-11-05"></a>
<a id="current-release-gates-2026-11-06"></a>
<a id="current-release-gates-2026-11-07"></a>
<a id="current-release-gates-2026-11-08"></a>
<a id="current-release-gates-2026-11-09"></a>
<a id="current-release-gates-2026-11-10"></a>

## Current release status (2026-11-10)

Version 0.3.4 is being prepared on `develop` as a fix-forward after immutable
tag `v0.3.3` failed candidate qualification. Main commit
`a8cef4ccaa32859553718017ad65d7fdad61769c` passed CI #774, the complete
three-system benchmark #381, and docs deployment. Candidate run #4 passed its
exact-source coverage recheck but failed performance acceptance. No 0.3.3
Cargo or PyPI artifacts were published; the `v0.3.3` tag remains immutable.

| Gate | Current evidence | Status |
| --- | --- | --- |
| Exact-main parity and raw unified coverage | [CI #774](https://github.com/appunni-m/uvicorn-rs/actions/runs/42776625577), source `a8cef4cc` | Passed 1,455/1,455 cases; 15,120/15,120 regions and 11,120/11,120 lines. Rust/MSRV, native composition, installed-wheel parity, and platform package jobs also passed. Candidate #4 rechecked the raw coverage and passed. |
| Three-system ordinary-FastAPI benchmark | [Benchmark #381](https://github.com/appunni-m/uvicorn-rs/actions/runs/42796770165), source `a8cef4cc` | Linux x86-64, Linux ARM64, macOS ARM64, and aggregate validation passed. Results are workload-specific; no broad speedup claim is made. |
| Documentation deployment | [Docs run](https://github.com/appunni-m/uvicorn-rs/actions/runs/42789469772), source `a8cef4cc` | Passed for the source associated with `v0.3.3`; updated 0.3.4 documentation needs a new docs run. |
| `v0.3.3` tag-bound candidate | [Candidate #4](https://github.com/appunni-m/uvicorn-rs/actions/runs/42813769106) | Tag/version, package, consumer, and exact-source coverage checks passed. Performance acceptance failed because full dependency receipts contain machine-specific install paths and compiled-file hashes that differ across platforms. |
| 0.3.4 exact-source release gates | Corrected validator and synchronized version metadata are being prepared on `develop` | Pending PR merge, fresh main CI and raw coverage, full exact-source benchmark, docs deployment, and candidate assembly. |
| Cargo and PyPI publication | `release.yml` uses configured crates.io and PyPI Trusted Publishers | Pending successful 0.3.4 candidate qualification; GitHub Actions is the only publication path. |

Benchmark #381 completed on all three systems and aggregate validation passed.
The report scopes Hypercorn HTTP/3 reference-only failures without ratios and
keeps all candidate correctness and lifecycle checks. It is evidence for
`a8cef4cc` only. The 0.3.4 source changes release validation and package
versions, so a fresh full matrix on the exact merged source is required. No
broad FastAPI speedup claim is made; the maintainer's real-server trial follows
repository qualification.

The release set is the Python-free Cargo crate `uvicorn-rs` with HTTP/3 behind
the optional `http3` feature, `asgi-lifespan-protocol-rs`, and PyPI distribution
`uvicorn-rs` exposing the `uvicorn` command/imports. `uvicorn-rs-py` remains the
optional internal adapter. Do not publish separate `uvicorn-rs-h3` or Quinn
crates. Candidate qualification will use a new immutable `v0.3.4` tag and its
exact main-source evidence; after it passes, `release.yml` publishes the lifecycle
crate then the server crate through crates.io Trusted Publishing, verifies
their registry checksums, publishes PyPI, verifies registry bytes, and creates
the GitHub Release. Publisher entries and release controls are configured;
no local Cargo publish or token is used. The failed `v0.3.2` and `v0.3.3` tags
remain unpublished and will not be moved.

| Superseded CI #712 artifact | Artifact | ZIP SHA-256 | Contents and check |
| --- | --- | --- | --- |
| Linux x86-64 | [13523013492](https://github.com/appunni-m/uvicorn-rs/actions/runs/42255484334/artifacts/13523013492) | `f4e0f01dc354e64bdfa333e3cf21123bda2a0682caab38a8f3442ee3da600694` | Cargo archives, wheel, and sdist; package and clean-consumer checks passed |
| macOS ARM64 | [13524965653](https://github.com/appunni-m/uvicorn-rs/actions/runs/42255484334/artifacts/13524965653) | `44b2c6efc5775e363c720f810e0bf9313c224fa381c6b36b5b23f8f4f12922bf` | Wheel and package checks passed; clean consumer passed |
| Windows x86-64 | [13523938563](https://github.com/appunni-m/uvicorn-rs/actions/runs/42255484334/artifacts/13523938563) | `7ea545070d73360a0f15beb8f6b68f4edf00ccfe877e3501387ff8e4db6d6988` | Wheel and package checks passed; clean consumer passed |

An annotated version tag starts `candidate.yml`; a successful candidate
automatically starts `release.yml`. Release preflight recognizes configured
Trusted Publisher entries and publishes missing Cargo versions in dependency
order. PyPI publication follows exact Cargo registry verification. The
workflow then verifies registry bytes and creates the GitHub Release with
artifact attestations. Identical already-published versions are verified and
skipped. Build and test jobs have no registry credentials.

The exact-source raw coverage gate requires 100% regions and lines, a complete
passing matrix, and recorded source, run, artifact, report, context, build, and
matrix identities. Candidate assembly revalidates that evidence against the
tagged source commit. The immutable `v0.3.1`, `v0.3.2`, and `v0.3.3` candidates
did not qualify and their publication workflows did not publish. Version
0.3.4 must pass the same checks on its own exact source before publication.

## Workflow ownership

| Readiness pillar | Workflow | Purpose |
| --- | --- | --- |
| Reliability and correctness | `ci.yml` | Rust/MSRV/platform builds, public Uvicorn parity, native framework composition, fault contracts, and clean package consumers. |
| Coverage | `ci.yml`; optional `coverage-mcp-handoff.yml` | Exact-source 100% unified region/line coverage with recorded source-bound evidence. The handoff workflow is optional diagnostics and does not gate release. |
| Reliability evidence | `benchmark-categories.yml` | Matched three-system workloads and focused diagnostics; release qualification consumes only a complete exact-source matrix. |
| Automated release | `candidate.yml`, `release.yml` | Tag-triggered candidate assembly and publication. GitHub Trusted Publishing handles first and subsequent Cargo versions, then PyPI after Cargo checksum verification. |
| Documentation | `docs.yml` | Strict documentation build and main deployment; imports the selected main benchmark artifact after each matrix run so reports and status are current in the published site. |
| Upstream-only diagnostic | `upstream-uvicorn-windows-diagnostic.yml` | Reproduce the stock Uvicorn Windows worker issue; this is not a `uvicorn-rs` release gate. |

The reference-only Windows reproduction was moved out of `ci.yml` so it no
longer appears as a `uvicorn-rs` correctness gate. The focused parity and
coverage replay modes remain available in CI as diagnostics for those same
readiness areas.

### Earlier release-gate wording (2026-11-05)

At this 2026-11-05 snapshot, independent Coverage-MCP review was required for
the final clean source. The maintainer later removed that requirement.
Exact-source 100% regions and lines, a complete passing matrix, and recorded
artifact identities remain mandatory; Coverage-MCP review is optional. The
exact-main #661 report below is historical.

Exact-main CI [#661](https://github.com/appunni-m/uvicorn-rs/actions/runs/41802594662)
passed on `feb955d2758166ad8c4b519903fd1318b29e7d2d`: all 1,453 coverage
cases and three repeats passed, with 14,965/14,965 regions and
10,984/10,984 lines. Raw artifact [13313323556](https://github.com/appunni-m/uvicorn-rs/actions/runs/41802594662/artifacts/13313323556)
has SHA-256 `d7ce785d590e7195be7eaa57e7761b8acb182ac4475599e2ab43cbd45567745d`.
Linux x86-64, macOS ARM64, Windows x86-64 package and consumer jobs passed.
The matching [three-system benchmark #283](https://github.com/appunni-m/uvicorn-rs/actions/runs/41802594681)
passed on Linux x86-64, Linux ARM64 and macOS ARM64. Its aggregate artifact is
[13313622768](https://github.com/appunni-m/uvicorn-rs/actions/runs/41802594681/artifacts/13313622768),
SHA-256 `99b295b2b5fcea8d04604aa8e3b55f16919403a48ed1fa94c716d9b2474931aa`.
It qualifies 68/67/66 category pairs and 28/27/26 matched ordinary-FastAPI
pairs on those systems. HTTP/1 FastAPI validated-route throughput is lower on
all six system/loop pairs; H2/H3 results vary by workload, and WebSocket
text-echo is slower. The evidence makes no general FastAPI speedup claim.
Candidate assembly and publication wait for PR promotion of the revised
raw-coverage evidence workflow and a candidate for the resulting exact commit.

The release set is the Python-free **uvicorn-rs** crate with optional **http3**,
**asgi-lifespan-protocol-rs**, and the PyPI distribution **uvicorn-rs**.
The optional internal Cargo/PyO3 adapter remains **uvicorn-rs-py**.
**candidate.yml** verifies staged candidates; **release.yml** uses GitHub
Trusted Publishing for missing Cargo and PyPI versions, then verifies the
registry bytes before creating the GitHub Release. The configured publisher
tuples are `appunni-m/uvicorn-rs / release.yml / pypi` for PyPI and
`appunni-m/uvicorn-rs / release.yml / crates-io` for both crates.

The registry audit on 2026-11-03 at 09:20 UTC found both Cargo crates at 0.2.1
with no 0.3.0 version, and HTTP 404 for PyPI `uvicorn-rs`. Recheck the
registries immediately before publication.

### Earlier candidate evidence from PR #21

[CI #640](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412)
uses PR #21 head `8e0f792a7dc00597c580fb7ddc6d5222e0310ec2` and clean
merge source `f42a99b1555133be4ba5095a6f48fe4fb9ffa22f`, after peer-read
recycling was rejected and removed. Linux and macOS pass 786/786 public inputs,
package consumers and strict offline source/native checks. Rust quality,
features, minimum version and native composition pass. Unified coverage was
still completing its required repeats at that checkpoint, so a final report was
not yet available. A separate Coverage-MCP review is optional under the current
release policy.

| Candidate evidence | Artifact | Verification |
| --- | --- | --- |
| Linux x86-64 | [13234310894](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412/artifacts/13234310894) | Actual Cargo archives, wheel and sdist inspected; clean default/http3, wheel and rebuilt-sdist consumers pass |
| macOS ARM64 | [13233983122](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412/artifacts/13233983122) | Wheel RECORD/source/native identity and clean consumer pass; local replacement/uninstall/rollback passes |
| Python 3.9.25 | [13235318123](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412/artifacts/13235318123) | Exact Linux abi3 wheel consumer passes; this is not full Python 3.9 parity |
| Windows x86-64 | [Raw parity 13234834280](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412/artifacts/13234834280) | 757/759 raw passes, one reference SIGINT mismatch and one reference SIGBREAK infrastructure timeout; no candidate package bundle |

The inspected package SHA-256 values for this producer are:

| Package | SHA-256 |
| --- | --- |
| `asgi-lifespan-protocol-rs-0.3.0.crate` | `7bf50d79cdbe79f4360a474604cbf56d5281fb2f1326a3f8850f38dcaea794e5` |
| `uvicorn-rs-0.3.0.crate` | `e258b3f246721a8c7f958008ecf854fcfdfc290d093af9a046ccfe64885bbd43` |
| `uvicorn_rs-0.3.0-cp39-abi3-manylinux_2_34_x86_64.whl` | `2cc4b119424bcbbcddee777f9a7d20021ee3520d80130e6a7f1a56ffd43bb6d7` |
| `uvicorn_rs-0.3.0-cp39-abi3-macosx_11_0_arm64.whl` | `3d70ab009020699f059cc763b9b953ad592d390acf266e038afa0cc6c0dabcec` |
| `uvicorn_rs-0.3.0.tar.gz` | `1090fdab6800860a94e07c783f753679e49811d8c4ec24bbae1515ede77475c7` |

An independent local Rust 1.85.0 consumer of these exact extracted Cargo
archives passes malformed HTTP/3 DATA-frame rejection with error 262 and a
fresh-connection HTTP 200/healthy recovery. These are PR-source inspection
artifacts, not publication approval or a complete final-main bundle.

The Windows candidate serves requests and shuts down cleanly in both failed
reference cases. The existing SIGINT exception passes offline review.
SIGBREAK lacked recovery evidence, so the full job correctly failed.
[Focused CI #641](https://github.com/appunni-m/uvicorn-rs/actions/runs/41647390647/job/125956212708)
then captures the known startup listen failure plus one SIGBREAK worker hang;
one diagnostic TCP connection releases stock shutdown after the original
deadline. The candidate keeps its two original workers and exits zero within
the deadline. Raw parity remains failed. Offline review of the composed policy
requires both defect signatures and a clean candidate; hosted qualification
of the updated checker remains pending. See the
[compatibility contract](maintainers/uvicorn-0.54.0-contract.md#acceptance-of-known-differences).

The measured buffer decision is complete: recycling was removed after the
small-response uvloop regression failed the frozen retention rule. The
three-system ordinary-FastAPI matrix is now complete; the separate upload
timeout root-cause issue remains open because exact-main benchmark #283 and
the focused stage trace #284 did not reproduce it. The focused trace contains
no receive wait above 100 ms, so it does not identify the original stalled
boundary; see [benchmark status](benchmark-status.md#focused-exact-main-http1-upload-trace-2026-11-04).
[Documentation #264](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278411)
built successfully for its recorded source, with PR deployment skipped; this
subsequent documentation refresh needs its own strict build.

For version 0.3.4, after all gates pass, verify exact-main CI, raw 100% coverage
and benchmark evidence, assemble the complete candidate, and create the
immutable `v0.3.4` tag. The successful candidate automatically starts
`release.yml`, which publishes Cargo in lifecycle/server order and then PyPI
`uvicorn-rs` through GitHub Trusted Publishing. Verify registry bytes and clean
installs. The earlier `v0.3.3` tag remains unpublished and will not be moved. See the
[completion plan](maintainers/release-completion-plan.md).

## Registry and packaging audit (2026-10-27; earlier source snapshot)

This section preserves the earlier audit. The current status and workflow
instructions above supersede its branch, candidate and publication state.

The published Cargo versions are `asgi-lifespan-protocol-rs` 0.2.1 and
`uvicorn-rs` 0.2.1, both from clean commit
`d5caa7d7fbfa70a38abb78d2bfa729f2e7c9494e`. Their archive SHA-256 values are
`44adef2e2648be1514aebe33ddc1dcc5267dae67abd8d31f1aff7ded7ce16235` and
`0662828f3f852f4960a034e734b2a281765e40b29388d4e8469230e5d4e52fcf`,
respectively. The registry lookup at that audit reported 0.2.1 as the newest
version for each crate. PyPI has no `uvicorn-rs` project release yet. The old
`uvicorn-rs-h3` and `uvicorn-rs-h3-quinn` names return 404 and are not release
targets.

The local draft targets version 0.3.0. The release-version check passes for the
PyPI distribution, private root adapter, both Cargo crates, and lockfiles.
Cargo metadata lists only `asgi-lifespan-protocol-rs` and `uvicorn-rs` as
publishable workspace packages; dirty-source package file lists were inspected
for both. These checks do not make the current artifacts upload-eligible: the
checkout is on `codex/uvicorn-rs-consolidation` at
`5b1ec29201c963d8590c989b07318bb7366d7922` with 132 changed or untracked
entries, and there is no clean 0.3.0 candidate or tag.

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
earlier full draft report stale for the current source and inventory. This
historical snapshot recorded a temporary waiver of separate Coverage-MCP
review and later reversed it. The maintainer's current decision is that an
independent receipt is optional; exact-source raw 100% coverage remains
mandatory.

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
That earlier `release.yml` revision had Cargo jobs using that environment and GitHub OIDC; the current workflow publishes only PyPI. The `crates-io`
and `pypi` GitHub environments are restricted to `main`, require reviewer
`appunni-m`, allow the sole maintainer to approve (Prevent self-review is off),
disable administrator bypass, and contain no secrets or variables. The PyPI
pending-publisher record is registered for project `uvicorn-rs`, repository
`appunni-m/uvicorn-rs`, workflow `release.yml`, and environment `pypi`.

No 0.3.0 package or tag has been published. The release workflow remains
blocked until the exact-source evidence gates pass and clean candidate artifacts
and consumers are verified.

## Distribution boundaries

| Channel | Distribution | Scope |
|---|---|---|
| Cargo | asgi-lifespan-protocol-rs, uvicorn-rs | Python-free Rust libraries. HTTP/3 protocol and Quinn transport code ship inside `uvicorn-rs` behind its `http3` feature. |
| PyPI | uvicorn-rs | Optional Python compatibility client for standard Python ASGI applications. It is not required by the Python-free Rust library. |
| Documentation | README, MkDocs site, and docs.rs | Repository docs deploy through GitHub Pages; crate API docs are generated from published Cargo archives. |

The PyPI distribution is `uvicorn-rs`, following the project's `pillow-rs` naming convention. It provides the `uvicorn` import namespace, `uvicorn` command, and `python -m uvicorn` entry point for in-place use. The root Cargo/PyO3 integration package remains `uvicorn-rs-py`; that internal name and optional console alias are not the PyPI distribution name. The current source metadata declares target version `0.3.4`, Python `>=3.9`, Uvicorn-style base dependencies, and a `[standard]` extra. The immutable `v0.3.1`, `v0.3.2`, and `v0.3.3` tags did not pass candidate qualification; no candidate PyPI `uvicorn-rs` release is present in the registries. The 2026-11-01 read-only registry check found 0.2.1 as the latest published version of both Cargo crates; PyPI had no `uvicorn-rs` release. The exact compatibility scope is in the [support matrix](support-matrix.md). Historical `0.2.2` inspection receipts below are retained as historical evidence and do not describe the current candidate.

The historical 0.1.0 Cargo bootstrap is recorded below. A registry API check on 2026-10-25 returned HTTP 404 for the then-removed `uvicorn-rs`, `uvicorn-rs-h3`, and `uvicorn-rs-h3-quinn` names; the subsequent `uvicorn-rs` 0.2.1 publication is recorded above. The old H3/Quinn package identities are not current release targets. The `uvicorn-rs` package vendors the H3 protocol and Quinn adapter source behind `http3`; it does not depend on separate project-owned H3 crates. `asgi-lifespan-protocol-rs` is the current lifecycle-contract package. The Python adapter depends on `uvicorn-rs`; Rust-native frameworks can depend on `uvicorn-rs` without Python.

As of 2026-11-01, the published Cargo workspace packages are `asgi-lifespan-protocol-rs` 0.2.1 and `uvicorn-rs` 0.2.1; neither has a published 0.3.0 version. The current source declares 0.3.0, uses Rust 1.85 or newer, and builds a Python wheel with the cp39-abi3 ABI for Linux x86-64, macOS ARM64, and Windows x86-64. These are platform targets, not evidence of Linux ARM64, musl, or universal macOS wheels. The 0.3.0 candidate remains unpublished until the final exact-source gates pass.

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

`candidate.yml` starts on an annotated `vX.Y.Z` tag and requires successful
exact-commit CI, coverage review, three-system benchmark, and consumer evidence.
Only a successful candidate run triggers `release.yml`. That workflow selects
the exact candidate run and attempt, rechecks the tag, source, artifact digest
and candidate manifest, then publishes missing Cargo versions in dependency
order through crates.io OIDC. Pending Trusted Publisher entries allow the two
first crate versions to be published through this same workflow. It verifies
each crate checksum before publishing PyPI through the `pypi` trusted
publisher. Its final job verifies registry bytes, attests the candidate files,
and creates or verifies the GitHub Release.

The crates.io Trusted Publisher entries are configured in pending state for
the not-yet-published crate names. crates.io supports this initial state so the
first versions can use the same short-lived OIDC flow as later releases. Exact
prepublished bytes are verified and skipped. The release therefore has no
local publishing step or long-lived Cargo credential.

The GitHub release workflow owns first and subsequent Cargo publication. It
reproduces each candidate archive with the pinned Cargo toolchain and compares
the bytes before publishing. It publishes the lifecycle crate first, waits for
the exact registry checksum to become visible, then reproduces and verifies the
server archive before publishing it. Do not publish Cargo crates locally or
provide a local Cargo token.

Local `cargo publish --dry-run` checks on CI #636 source reproduced both
Linux candidate archive hashes on macOS with Cargo 1.98.1. They did not upload
a package and do not qualify later source. The current `release.yml` repeats
the archive identity check from the candidate and uses isolated short-lived
Trusted Publishing tokens after candidate success. It publishes the lifecycle
crate first, verifies its registry checksum, then publishes the server. No
workflow creates or moves a tag.

Release direction (2026-10-25): the maintainer authorized a coordinated Cargo
and PyPI release and specified local Cargo publication first. The 0.2.1 local
publication was completed on 2026-10-26: `asgi-lifespan-protocol-rs` was
published before its dependent `uvicorn-rs`, and both registry artifacts were
verified. PyPI `uvicorn-rs` remains pending. Dirty-source 0.2.2 inspection
artifacts have been prepared, but no clean current-source candidate has passed
its release gates. The 2026-10-30 registry API check confirms both 0.2.1
versions remain visible and unyanked. Earlier workflow revisions offered
manual Cargo/PyPI actions, and the 2026-11-06 snapshot temporarily put PyPI
before Cargo. The current workflow model replaces those manual steps: an
annotated tag starts candidate qualification, then successful candidate
completion automatically starts Cargo/PyPI publication and GitHub Release
creation. At that 2026-10-25 snapshot, first publication of each Cargo package
name required a local bootstrap; both names later existed, so subsequent
versions used OIDC. For the 0.3.0 release, crates.io pending Trusted Publisher
entries let `release.yml` publish both initial versions from GitHub. Release
still requires a clean tagged commit on `main`, a successful exact candidate
artifact, all required release evidence, and configured publisher trust.

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
environment `pypi`; automated publication remains unverified because no PyPI
release has run. Both crates.io Trusted Publisher entries are verified as
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
3. Record the exact-source raw coverage report and its artifact, report,
   context, build, and full-matrix identities. Require 100% of normalized
   regions and lines. A separate Coverage-MCP receipt is optional; candidate
   validation rechecks the raw report, artifact, and source identities before
   the tag can be published.
4. Complete the correctness-gated three-system performance matrix on the exact
   release commit. It may be triggered by a `main` push or a full
   `workflow_dispatch` run on `main`; candidate qualification accepts either
   only when all three platform jobs and the aggregate evidence job succeed.
   Require matching valid repetitions and report throughput, p50/p95/p99
   latency, server CPU per operation, and sampled peak RSS. Keep stock FastAPI
   and Starlette workloads separate from Rust-native application measurements.
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
all gates pass, pushing the annotated version tag is the release authorization:

1. Create an annotated vMAJOR.MINOR.PATCH tag on the reviewed commit. Do not
   move or reuse a tag after a public artifact refers to it.
2. The workflow checks the remote tag object, tag/version agreement, clean
   checkout, main ancestry, and successful exact-commit CI and performance runs.
   Performance evidence may come from a `main` push or a full manual dispatch
   on `main`, but must contain successful Linux x86-64, Linux ARM64, macOS
   ARM64, and aggregate evidence jobs from the selected run attempt. Focused
   dispatches cannot qualify.
3. It downloads the exact retained artifacts, checks their workflow identity
   and digests, and verifies package identity and evidence.
4. It builds the independent consumer against the extracted Cargo archives and
   records the result in the candidate bundle.
5. It writes a candidate manifest and checksums and uploads the immutable
   bundle. Candidate assembly has no registry credentials or publication
   permissions.
6. A successful candidate automatically triggers `release.yml`; no separate
   publication dispatch or typed confirmation is needed.

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

After candidate success, `release.yml` validates the exact artifact bundle and
checks registry state without credentials. It publishes every missing Cargo
version, including the first version of a pending-publisher crate, in
dependency order with short-lived OIDC tokens. It then publishes PyPI and
verifies all registry checksums. It creates the GitHub Release only after
registry verification. A mismatch or failed candidate gate stops publication.

### Cargo publisher configuration

The pending Trusted Publisher entry for each crate is `appunni-m / uvicorn-rs /
release.yml / crates-io`. The isolated Cargo publish job obtains a short-lived
OIDC token for both initial and later versions. Never supply a Cargo token
through workflow inputs or commit one to the repository.

### First PyPI publication

The PyPI Trusted Publisher for `uvicorn-rs` is configured with owner
`appunni-m`, repository `appunni-m/uvicorn-rs`, workflow `release.yml`, and
environment `pypi`. No PyPI version has been uploaded. Recheck the project name
before publication. The publish
job accepts only the candidate's exact wheel and source-distribution filenames
and checksums. Do not add a long-lived PyPI token to GitHub secrets.

### GitHub Release

The automated release job creates the GitHub Release only after Cargo and PyPI
checksums match the candidate. It attaches the verified crate archives, Python
distributions and a SHA-256 manifest, then records artifact attestations. Repo
write permission is limited to that final job.

## Documentation publication

The
[Documentation workflow](https://github.com/appunni-m/uvicorn-rs/blob/main/.github/workflows/docs.yml) builds every maintained
page with strict link validation, uploads the validated Pages artifact, and
deploys only from main after the build passes. It selects the triggering or
latest completed main benchmark aggregate and renders that report and attempt
status into the site build. It uses a separate github-pages environment and
does not publish packages.

Set repository Pages source to GitHub Actions and create the github-pages
environment before deployment. The expected site URL is
https://appunni-m.github.io/uvicorn-rs/. Verify the deployed pages after the
workflow succeeds. docs.rs pages become available from published crate
archives; inspect each crate's rendered API documentation after registry
publication.

## Package verification contract

| Artifact | Build and consumer evidence |
|---|---|
| Linux x86-64 wheel | Ubuntu 24.04 build; CPython 3.12.13 installed-wheel smoke and public live parity. |
| macOS ARM64 wheel | macOS 14 build; CPython 3.12.13 installed-wheel HTTP, context, lifespan, and cancellation checks. |
| Windows x86-64 wheel | Windows Server 2022 build; CPython 3.12.13 package-consumer checks. POSIX signal parity is not claimed. |
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
