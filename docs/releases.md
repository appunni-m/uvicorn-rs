# Release candidates

The project prepares wheel and source **candidates** from a reviewed commit.
`Cargo.toml` keeps `publish = false`; the workflows upload GitHub Actions
artifacts and do not publish to crates.io or PyPI, create a GitHub Release,
or create or move tags. The project is licensed under
[BSD-3-Clause or MIT](../LICENSE), at the recipient's option, with copyright
© 2026 Appunni M and the original Uvicorn/Hypercorn license notices retained.

## Current state

The original workflow revisions passed local Actionlint validation; action
SHAs were checked against their upstream GitHub revisions. The current
Windows-long-path and failure-annotation edits parse as YAML and await hosted
verification. Local Rust 1.85.0 default and all-feature checks pass. A macOS
ARM64 wheel was built and consumed in fresh CPython 3.12.13 and 3.9.25
environments, including a real HTTP request, caller loop/thread/context,
lifespan and public API cancellation. The source archive was also extracted,
rebuilt with locked dependencies and consumed in a fresh environment. Its
package inputs matched the checkout.

The October 5 release-preparation evidence below remains a historical
snapshot. Clean hosted CI run #35 passed 239/239 installed-wheel public parity
cases and all 491 unified coverage cases, with 5,121/5,121 regions and
3,624/3,624 lines. Its parity job also passed the normal-build fault-seam
exclusion audit. The local 2026-10-08 report strengthens the H2 EOF
fault-consumption assertion and passes 491/491 attribution cases plus three
complete repeats with full region and line coverage; Coverage-MCP reports zero
gaps. Hosted run #35 predates that assertion. Current package failures and the
local macOS reproduction are recorded below; no complete release candidate is
verified.

Hosted CI run [37672645704](https://github.com/appunni-m/uvicorn-rs/actions/runs/37672645704)
on clean commit `1a72c9b` completed with failure. Rust quality and MSRV passed;
installed-wheel public parity passed 239/239; unified coverage passed 491/491
cases with 5,121/5,121 regions and 3,624/3,624 lines. Package preparation did
not pass: the Windows checkout hit a tracked path-length error in retained
parity evidence; the pending workflow update enables Git's `core.longpaths`
before checkout. The Linux package, source rebuild and candidate-wheel parity
steps passed, but the build-manifest recording step failed; its detailed log
was not publicly retrievable, so the cause remains unknown. The macOS ARM64
wheel-build/consumer step also failed without a detailed public annotation.
The Python-floor job was skipped, and no platform candidate artifacts were
uploaded. This run is not a complete release candidate.

The hosted macOS failure did not reproduce locally. On macOS 15.7.7 ARM64 with
CPython 3.12.10, Rust/Cargo 1.98.1 and Maturin 1.14.1, the same wheel build and
exact-wheel consumer passed; `release_evidence.py record --allow-dirty` also
validated the package metadata, RECORD, licenses and native architecture. The
wheel, consumer receipt and local-preparation manifest are in the
[macOS reproduction archive](../benchmarks/results/2026-10-08/macos-arm64-run35-local-reproduction/).
The manifest is explicitly `local preparation` with `source_dirty: true`; this
does not explain the hosted failure or establish a release candidate.

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
