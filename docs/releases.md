# Release candidates

The project prepares wheel and source **candidates** from a reviewed commit.
`Cargo.toml` keeps `publish = false`; the workflows upload GitHub Actions
artifacts and do not publish to crates.io or PyPI, create a GitHub Release,
or create or move tags. The project is licensed under
[BSD-3-Clause or MIT](../LICENSE), at the recipient's option, with copyright
© 2026 Appunni M and the original Uvicorn/Hypercorn license notices retained.

## Current state

CI #54
([run 38045596633](https://github.com/appunni-m/uvicorn-rs/actions/runs/38045596633))
on `a93cdff` passed Rust quality, Rust 1.85, and installed-wheel parity
(240/240). Unified coverage measured 5,298 regions and 3,753 lines, but its
first attribution pass ended at 492/494 with one HTTP/3 oracle failure and one
TLS-shutdown adapter infrastructure failure. Three later complete runs passed
494/494; the strict aggregate remained incomplete. The latest completed
three-system benchmark,
[run #11](https://github.com/appunni-m/uvicorn-rs/actions/runs/38045596557),
failed its x86-64 and macOS parity gates; ARM64 passed parity but failed
category analysis. The aggregate and documentation jobs failed, so there is
no validated system matrix. Artifacts were uploaded, but their contents and
job logs require authenticated access here.

Follow-up commit
[`b2ea48bc`](https://github.com/appunni-m/uvicorn-rs/commit/b2ea48bc25835f37eab41a0f408ea8e4072c4e92)
changes only the TLS listener-closure probe in the parity runner. CI #55
([run 38058258362](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258362))
and benchmark #12
([run 38058258390](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258390))
were triggered on that commit. CI #55 is terminal. Rust quality, MSRV, and
installed-wheel parity passed (240/240).
Unified coverage measured all 5,298 regions and 3,753 lines, but repeat 2
failed: 486 cases passed, `fault.http1.early-response-body-drain-terminal-frame`
was infrastructure-failed because its request-body fault was not consumed,
and seven later cases were not run. A focused local reproduction passed this
case three times on the same `a93cdff` Rust source, but it was a selected-subset
run and does not clear the full hosted gate. The hosted coverage artifact is
listed on the run page; detailed artifact access still requires
authentication.

Benchmark #12
([run 38058258390](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258390))
is terminal with no validated timing data. Its Linux x86-64 job failed the
exact normal-binary public parity gate before timing; all three system jobs and
the aggregate job failed. The artifact archive returns 401 without
authentication and the job-log endpoint returns 403 in this session.

Commit
[`72dfa51`](https://github.com/appunni-m/uvicorn-rs/commit/72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f)
adds bounded case-specific benchmark parity annotations and has been pushed
to `main`. CI #56
([run 38061568584](https://github.com/appunni-m/uvicorn-rs/actions/runs/38061568584))
passed the installed-wheel parity, unified 100% native coverage, platform
package, Python-floor, Rust quality, and MSRV gates on this exact commit.
Benchmark #13
([run 38061568654](https://github.com/appunni-m/uvicorn-rs/actions/runs/38061568654))
still has no validated aggregate: the macOS ARM64 job failed exact parity on
`http1.disconnect-before-first-asgi-receive`, while both Linux jobs passed
parity and began category measurements. A clean local wheel from the same
commit passed that case 10/10 times; see the
[reproduction receipt](../benchmarks/results/2026-10-10/ci13-disconnect-exact72-repro/README.md).
The hosted row-level observations remain unavailable, so the difference is
unexplained. The checkout remains dirty and no release candidate is ready to
assemble.

Local dirty-working-tree evidence is useful but does not qualify a release:
Coverage-MCP reports 5,532/5,532 regions and 3,974/3,974 lines for its
matching current-source receipt, and the stock FastAPI matrix includes
correctness-gated multi-protocol measurements. These results do not come from
a clean exact-main candidate with successful hosted gates. No tag or release
was created. See [coverage](coverage.md) and
[benchmark status](benchmark-status.md) for evidence and limits.

The original workflow revisions passed local Actionlint validation; action
SHAs were checked against their upstream GitHub revisions. Hosted runs #36 and
#37 confirm the Windows long-path setting lets checkout finish. Commit
`226ab13` excludes `.kata.toml` from distributions, compares packaged README
text with normalized line endings, and shortens failed wheel-consumer
annotations to keep the final traceback within the annotation limit. Local Rust
1.85.0 default and all-feature checks pass. A macOS ARM64 wheel was built and
consumed in fresh CPython 3.12.13 and 3.9.25 environments, including a real HTTP request, caller
loop/thread/context, lifespan and public API cancellation. The corrected
source archive was also safely extracted, rebuilt with locked dependencies,
and consumed in a fresh environment on macOS ARM64. Hosted run #39 later
verified the corrected commit across the platform package matrix.

The October 5 release-preparation evidence and hosted runs #35–#38 below are
historical. The local 2026-10-08 report strengthens the H2 EOF fault-consumption
assertion and passes 491/491 attribution cases plus three complete repeats with
full region and line coverage; Coverage-MCP reports zero gaps. Hosted run #39
on `a78b4a9` passed the CI and platform package gates for that commit. The
later run [#46](https://github.com/appunni-m/uvicorn-rs/actions/runs/37743481915)
on `f2a0cb3` passed normal installed-wheel parity (239/239) but failed its
unified coverage gate because one fault contract was not consumed; seven cases
were not run. An immutable tagged candidate bundle has not been assembled, and
representative performance superiority remains unproven.

Hosted CI run [37672645704](https://github.com/appunni-m/uvicorn-rs/actions/runs/37672645704)
on clean commit `1a72c9b` completed with failure. Rust quality and MSRV passed;
installed-wheel public parity passed 239/239; unified coverage passed 491/491
cases with 5,121/5,121 regions and 3,624/3,624 lines. Package preparation did
not pass: the Windows checkout hit a tracked path-length error in retained
parity evidence.

Hosted runs [#36](https://github.com/appunni-m/uvicorn-rs/actions/runs/37679543470)
and [#37](https://github.com/appunni-m/uvicorn-rs/actions/runs/37684421046)
confirm the checkout fix and pass Rust quality, Rust 1.85, installed-wheel
public parity (239/239), and unified coverage (491/491 cases, 5,121/5,121
regions, 3,624/3,624 lines). Package checks fail in both runs. Windows builds
and consumes the wheel, then its manifest check reports README line-ending
differences. Linux completes the source rebuild, installed-wheel consumer, and
candidate-wheel public parity, then its manifest check finds unreviewed
`.kata.toml` in the source archive. macOS builds and installs the wheel, but
the CLI consumer exits during TLS startup; the annotation is truncated before
the exception cause. Python-floor is skipped and no platform candidate
artifacts are uploaded.

Commit `226ab13` addresses the deterministic package failures and bounds the
macOS traceback annotation to its final 30 lines and 3,000
characters. Local verification built and inspected the 34-member sdist without
`.kata.toml`, accepted CRLF-converted PKG-INFO with the same README content,
rebuilt the archive with locked dependencies, and passed its fresh installed-wheel
consumer for HTTP/TLS/lifespan/shutdown.

Hosted CI [run #38](https://github.com/appunni-m/uvicorn-rs/actions/runs/37688528361)
on `226ab13` passed Rust quality, Rust 1.85, public installed-wheel parity
(239/239), and unified coverage (491/491 cases, 5,121/5,121 regions,
3,624/3,624 lines). The Linux package job, including source rebuild, candidate
wheel parity, and manifest recording, passed. The Windows package job and
manifest recording passed. The macOS wheel built and installed, but its CLI TLS
probe failed while Rustls parsed the generated certificate with
`ExtensionValueInvalid`; the Python-floor job was skipped and no complete
candidate is verified.

The TLS failure is in the probe certificate: Rustls reports
`ExtensionValueInvalid` when a certificate repeats an extension OID. The probe
previously inherited the host OpenSSL configuration while also supplying
extensions inline. The probe fix gives OpenSSL one explicit configuration and
generates a CA:FALSE server certificate with one extension set. A locally built
normal macOS abi3 wheel passed the installed-wheel HTTP,
TLS, ALPN, SIGTERM, lifespan, and cancellation consumer. Hosted run #39 later
verified this fix on macOS.

Hosted CI [run #39](https://github.com/appunni-m/uvicorn-rs/actions/runs/37692260364)
completed successfully on exact main commit `a78b4a925654ee0a5fb80814074ca2b0224bb094`.
Rust quality, Rust 1.85, installed-wheel parity (239/239), and unified
coverage (491/491 cases, 5,121/5,121 regions, 3,624/3,624 lines) passed. The
Linux x86-64 source archive rebuilt and passed its installed-wheel consumer;
all three platform wheel builds and installed-wheel checks passed. The exact
Linux candidate wheel passed full public parity, and the CPython 3.9.25 wheel
consumer passed. This verifies the deterministic TLS certificate probe on
hosted macOS. The uploaded Actions artifact digests are:

| Artifact | SHA-256 |
| --- | --- |
| Linux x86-64 candidate | `62b50e78d2c72eee703e34ab00cee5ecb010697f24fc600f3f702959be53b443` |
| macOS ARM64 candidate | `0b8cc5fa0e9b15d753a9e7f1514b0798105828ad6303b3e075fdae9fcf487923` |
| Windows x86-64 candidate | `168ca29f4c08b7c1ddafa3636a3d58842db29af8db79569e4c15197bdac66541` |
| Python 3.9.25 consumer | `b63c185cb1a727bb1dc74494eac8c1a567aa55a45b16c6e415d9c5f472a7c79c` |

Run #39 prepares CI artifacts only. No tag, immutable release-candidate
bundle, registry package, or GitHub Release was created.

An earlier macOS ARM64 reproduction used CPython 3.12.10, Rust/Cargo 1.98.1,
and Maturin 1.14.1. Its exact-wheel consumer passed, and
`release_evidence.py record --allow-dirty` validated package metadata, RECORD,
licenses, and native architecture. The wheel, consumer receipt, and
local-preparation manifest are in the
[macOS reproduction archive](../benchmarks/results/2026-10-08/macos-arm64-run35-local-reproduction/).
That manifest is explicitly `local preparation` with `source_dirty: true` and
does not establish a release candidate.

Hosted CI run [37566368036](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036)
on main commit `9d05c72` passed Rust quality, MSRV, and the installed-wheel
public parity/deployment job, including both framework comparisons and the
transient systemd stop. Its independent unified coverage job failed with exit
code 1, and the package candidate jobs were skipped because they depend on
coverage. The artifact and exact job status are recorded in the
[framework/deployment evidence index](../benchmarks/results/framework-integration-2026-10-07/evidence-index.json);
the failure cause remains unresolved. No hosted release-candidate bundle, tag,
or public release is complete. The benchmark's separately frozen binaries and
results are identified in [the investigation](performance-investigation-2026-10-05.md).

## Main CI gates

[CI](../.github/workflows/ci.yml) runs on `main`, `codex/**` branches, pull
requests and manual dispatch. Permissions are read-only and action references
use full commit SHAs. Superseded branch runs can be cancelled; immutable tag
candidate runs cannot cancel each other.
Main CI reruns replace their transient artifacts within the same workflow run.
Candidate assembly records the selected run attempt and rechecks its identity
and successful status after downloading and validating the evidence. A completed
tagged candidate bundle is uploaded without replacement.

| Gate | Contract |
| --- | --- |
| Rust quality | Formatting, Clippy with warnings denied, default/no-default/all-feature compilation and rustdoc; Rust 1.98.1 |
| Rust minimum | Locked library compilation on exactly Rust 1.85.0 |
| Normal public parity | Every current public input case against stock pinned references, using the installed normal wheel on CPython 3.12.13 |
| Normal-build exclusion | Native fault/LLVM/diagnostic controls absent, with three existing public cases and an armed control file ignored |
| Unified native coverage | Every indexed parity/fault-contract case attributed individually, three complete repeats, zero retries, 100% measured native regions and lines |
| Platform packages | Three actual abi3 wheels, per-platform installed-wheel checks, build manifests and archive inspection |
| Linux candidate parity | Complete public matrix on the exact Linux candidate wheel and its CPython 3.12.10/reference environment |
| Source consumer | Safe extraction, checkout input equality, locked rebuild, fresh wheel install and live package-consumer check |
| Python minimum | Install the exact Linux abi3 wheel on CPython 3.9.25 and execute the package-consumer check |

CI invokes live ASGI cases and package-consumer workflows. It does not invoke
Rust test executables or a Python unit-test runner. Structural checks validate
existing input contracts and evidence; they do not substitute for live parity.

The unified report keeps case-to-region attribution in one LLVM JSON document.
Its denominator is the default-feature `src/lib.rs` build with coverage-only
failure seams. Python, dependencies, optional `runtime-diagnostics`, other
platform cfg branches and the complete official ASGI conformance suite are
outside that denominator. A coverage failure or incomplete repeat fails CI;
there is no reduced threshold or automatic retry into a passing receipt.

Hosted CI checks the report directly. The external Coverage-MCP review is a
separate source-matched check and is not silently claimed by hosted CI. Before
a public release, retain that review for the exact proposed source/report as
described in [coverage](coverage.md).

## Package contract

| Artifact | Runner/interpreter | Verification scope |
| --- | --- | --- |
| Linux x86-64 wheel | Ubuntu 24.04, CPython 3.12.10 | Exact installed-wheel smoke and full public live parity |
| macOS ARM64 wheel | macOS 14, CPython 3.12.10 | Exact installed-wheel HTTP, loop/context, lifespan and API cancellation smoke |
| Windows x86-64 wheel | Windows Server 2022, CPython 3.12.10 | Same package-consumer smoke; POSIX signal parity is not claimed |
| Source archive | Ubuntu 24.04 | Required inputs/license/metadata, safe inventory, locked extracted rebuild and fresh consumer |

The wheel tag is `cp39-abi3`; the Python 3.9 job validates that ABI floor on
Linux, not every protocol on every Python/OS combination. Linux builds use the
runner's native environment. The recorded wheel tag determines its actual
platform/glibc requirement; this workflow does not claim manylinux2014,
Linux ARM64, musl or universal macOS binaries. No cross-compiled artifact is
presented as a native execution result.

`scripts/check_installed_wheel.py` rejects imports from the editable checkout
and compares the imported native bytes with the supplied wheel. Platform build
manifests bind package hashes, source inputs, version, commit, toolchain and
consumer evidence. The raw package set has exactly three wheels, one source
archive, three manifests, three platform consumer receipts, one source-consumer
receipt and the Linux full-parity report. Assembly verifies wheel metadata/tags/RECORD, licenses,
normal native markers, source inputs and expected platforms. Repository-only
benchmark archives, test harnesses, coverage profiles, keys and environments
are excluded from distributions.

Maturin 1.14.1's `sdist` command has no `--locked` option. The subsequent source
rebuild uses `maturin build --release --locked`, checks input equality before
and after building, and retains the build log. Version agreement includes
`Cargo.toml`, `pyproject.toml`, `Cargo.lock` and `uv.lock`; the workflows do not
hardcode the install version. No changelog update is part of this change.

## Assemble an immutable tagged candidate

First commit the complete source, input matrix, workflows and packaging
metadata together. Require a clean checkout and successful complete `CI` on
`main` for that exact commit. A maintainer can then request candidate assembly
by pushing an annotated `vMAJOR.MINOR.PATCH` tag for that commit.

[Release candidate](../.github/workflows/release.yml) follows the immutable
artifact/evidence pattern used by `fontdone` and `image-slash-star`, adapted to
Python wheels and a source archive:

1. Verify the remote annotated tag object resolves to the checked-out commit,
   including when checkout materializes only its peeled commit.
2. Require exact tag/manifest/lockfile version agreement and a clean checkout.
3. Find a successful complete main CI run for that same commit.
4. Download only that run's three platform package artifacts, normal parity,
   seam-exclusion audit, complete unified coverage and Python-floor evidence.
5. Verify package identities and retained evidence, then write bundle checksums
   and a candidate record containing version, tag, commit and CI run ID.
6. Retain the complete candidate bundle for 90 days.

Missing, expired, incomplete or mismatched artifacts fail assembly. Rerun main
CI on the exact commit when evidence expires. Do not move an existing tag to
repair a failure. The workflow has no credentials or permissions for registry
publication, OIDC authentication, repository writes or GitHub Release creation.

## Public release decision

Candidate verification, hosted CI success and public publication are separate
states. A public release additionally needs an explicit distribution decision,
reviewed release notes, the current support/known-limit matrix, exact-source
Coverage-MCP review and green hosted evidence. Experimental H3 limitations and
workload-specific benchmark results remain visible. Use a clean proven commit;
do not distribute the dirty local preparation artifacts as an official release.

Dependabot proposes weekly Cargo and GitHub Action updates. Review those
updates and their exact pins before accepting them into a candidate.
