# Release candidates

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

The release candidate is built from a reviewed commit. The current candidate
workflow packages three `uvicorn-rs-py` wheels, an sdist, and two Python-free
Rust crate archives (`native-app-contract` and `uvicorn-rs`). The native
crates are library packages; this repository does not currently provide a
standalone native executable.

## Release status snapshot (2026-10-18; exact-source run 39082487352)

No release candidate bundle or tag is established. Hosted CI run
[39081302848](https://github.com/appunni-m/uvicorn-rs/actions/runs/39081302848)
completed successfully on feature-branch commit
[`0c68cecfb89433703639006065ef51935b1c8018`](https://github.com/appunni-m/uvicorn-rs/commit/0c68cecfb89433703639006065ef51935b1c8018)
All nine jobs passed: installed-wheel public parity, the three-repeat unified
parity/fault-coverage job, Rust formatting/lints/features/docs, Rust 1.85
MSRV, pinned native FastAPI-RS composition, platform packaging, and Python
floor. Its coverage artifact is available; Coverage-MCP review remains
outstanding. Linux x86-64 passed source archive rebuild, Python-free Rust
archive packaging, and complete public parity on the candidate wheel. Windows
and macOS built and installed ABI3 wheels but skipped source and Rust archive
consumer checks. This successful run is not exact-current-source evidence.

Exact-head run
[39082487352](https://github.com/appunni-m/uvicorn-rs/actions/runs/39082487352)
for `8161db582` is in progress. The preceding documentation snapshot at
`b45d7446b750029867ad44f3e5950bdb4a630e4b` has CI run
[39084568469](https://github.com/appunni-m/uvicorn-rs/actions/runs/39084568469)
pending. This follow-up records the completion of run 39081302848 and will
receive its own exact-commit CI run after the push.

Packaging evidence on run 39081302848 is not yet a release bundle. The run is
also on a feature branch, not `main`; the release workflow selects successful
CI for the exact commit on `main`. Current `main` is
[`36c1c92bfd2cf8ce960fc468314879b2c3c7590b`](https://github.com/appunni-m/uvicorn-rs/commit/36c1c92bfd2cf8ce960fc468314879b2c3c7590b).
This checkout contains changes newer than run 39081302848, so that successful
run is not exact-source evidence for the current source. Exact-commit hosted
checks are still required.

The full performance gate remains open. The latest full three-system matrix,
[run 39036702600](https://github.com/appunni-m/uvicorn-rs/actions/runs/39036702600),
failed correctness gates on all three systems. The checked-in decision is
`scope_revised`: `uvicorn-rs-py` remains a compatibility and regression path
without a general speed claim, while performance claims target Python-free
Rust-native composition. Focused local FastAPI measurements, including the
HTTP/2 chunk-streaming result, the HTTP/1 upload probes, and the WebSocket echo
diagnostic in the
[benchmark record](benchmark-status.md), are diagnostic and do not replace a
qualified exact-commit multi-system matrix.

The standalone Rust crate remains blocked by the external package dependency
path for the vendored H3 framing correction; see the package-consumer
investigation below. A release candidate still needs complete platform
artifacts, extracted Rust archive consumers, exact-source hosted checks,
Coverage-MCP review, performance acceptance, and final support, deployment,
and release documentation. No package publication or GitHub release is
performed by these workflows.

### Superseded release status snapshot (2026-10-17; main 951c67b)

No release candidate is established. Current `main` is
[`951c67b15faa8eef047432604e5a1785dd18776b`](https://github.com/appunni-m/uvicorn-rs/commit/951c67b15faa8eef047432604e5a1785dd18776b),
which adds a focused benchmark workflow and report for the normal-build FastAPI
route comparison. Current-head CI
[39031849683](https://github.com/appunni-m/uvicorn-rs/actions/runs/39031849683)
is pending. Focused normal-build benchmark
[39031849682](https://github.com/appunni-m/uvicorn-rs/actions/runs/39031849682)
passed its response, lifecycle, and shutdown gates with five valid asyncio
pairs and four valid uvloop pairs, but Rust measured 0.652×/0.726× Uvicorn
throughput and 1.96×/1.75× server CPU per request. The retained run and scope
revision are documented in the [benchmark record](benchmark-status.md) and
[`performance-acceptance.json`](performance-acceptance.json). This focused run
does not replace the required complete exact-commit multi-system matrix.

Older CI
[39024130047](https://github.com/appunni-m/uvicorn-rs/actions/runs/39024130047)
passed its unified coverage matrix and the native composition, installed-wheel
parity, MSRV, Rust quality, and Windows package jobs on `77e1f425`. Linux
candidate-wheel parity is still running and macOS packaging is queued; these
results do not replace the required check on the current head. The earlier exact-head run
[39023002405](https://github.com/appunni-m/uvicorn-rs/actions/runs/39023002405)
was cancelled and is not a pass.

Prior CI
[39020268579](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579)
on `aa4c93836f5e2147462837bbd8b1bde6c0ebe84e` passed 749/749 unified cases
with three ASGI and three native repeats, 9,004/9,004 regions, and 6,636/6,636
lines. Installed-wheel parity, Rust quality/MSRV, and pinned native composition
also passed. Linux, Windows, and macOS package artifacts and the declared
Python-floor job passed. These results predate `93d1217` and do not establish
exact-head acceptance.

The full multi-system performance gate remains open. Matrix run
[39020268578](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268578)
on `aa4c938` is terminal but incomplete: Linux x86-64 and macOS ARM64 category
runs completed; Linux ARM64 failed the H3 correctness gate in
`many-response-chunks`. A same-source focused rerun passed five correctness
and shutdown repetitions but does not resolve the intermittent failure. The
qualified workload ratios show repeated HTTP/1.1 and WebSocket regressions;
the small stock-FastAPI validated route also ran at 0.654–0.870x Uvicorn
throughput on qualified Linux pairs, with higher server CPU per request. HTTP/2
and HTTP/3 results vary substantially by workload and system. These results
do not establish a general speedup. See the [benchmark record](benchmark-status.md)
for the category table, exact inputs, and limits.

The exact-source Coverage-MCP receipt is also pending. Hosted CI proves
9,004/9,004 regions and 6,636/6,636 lines on an earlier commit, but the report's
MCP status is `awaiting_query`. The prior local projection query and timed-out
exact-commit query were for older report 39011984443 and do not review report
39020268579. No source-verified, fully paginated receipt exists for that report
yet. Current-head CI and exact-head coverage remain open. See the
[coverage record](coverage.md).
The repository workflows do not publish packages or create releases.

The standalone Rust crate remains blocked by the documented vendored `h3`
framing fix not being carried by its external package dependency path. The
workspace parity result does not establish that the published Rust crate
contains the fix; see the package-consumer investigation below.

## Prior release status snapshot (2026-10-17; superseded by run 39011984443)

This is a timestamped historical snapshot. Its pending/running descriptions
record the state before run 39011984443 completed; the current status is in the
section above.

No release candidate is established. Commit `e2a39c55594eb4aab2ac922c2e9128e970ca7f7e`
is on `main`. Its focused Linux ARM64 HTTP/3 comparison passed all response
and shutdown checks and produced four valid matched timing pairs for the
1 MiB FastAPI response workload. The measured 24.38× throughput result is
limited to that focused workload; the [benchmark record](benchmark-status.md)
shows the full multi-system run still failed on intermittent Hypercorn HTTP/3
response-header timeouts on macOS ARM64 and Linux ARM64.

Exact-source CI run
[39011984443](https://github.com/appunni-m/uvicorn-rs/actions/runs/39011984443)
is still running its three-pass coverage matrix for the preceding commit. CI
for the current main head is queued behind it. The Python packaging,
Python-floor, clean-source coverage, and complete multi-system performance
gates have not yet passed on the current commit. The repository workflows do
not publish packages or create releases.

The standalone Rust crate also remains blocked by the documented vendored
`h3` framing fix not being carried by its external package dependency path. The
workspace parity result does not establish that the published Rust crate
contains the fix; see the package-consumer investigation below.

## Previous release status snapshot (2026-10-17; superseded by e2a39c5)

No release candidate is established. The latest clean CI run
[38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888)
on `27de9f3ac7d259a3a9b612c3247ab2c60eb27306` passed Rust quality and MSRV
checks, installed-wheel public parity, pinned native FastAPI-RS composition,
and all 712 indexed cases. Its older manifest measured 8,496/8,650 regions and
6,486/6,592 lines (154 regions and 106 lines missing); package-artifact and
Python-floor jobs were skipped. The preceding run 38828501018 had 155 regions and 107 lines
missing.

The latest local unified run on the current dirty worktree executed and passed
748/748 cases (534 ASGI, 214 native), all three ASGI and native repeats, and
measured 8,997/8,997 executable source-span regions plus 6,629/6,629
normalized physical executable lines. Attribution and repeats had zero
failures, infrastructure failures, retries, or unrun cases. Coverage-MCP
matches source/build and reports zero missing regions or lines with
`tests=passed`; the offline evidence checker independently reconstructed the
retained profiles and passed. This local result is not clean committed-source
or hosted release evidence; see the
[coverage record](coverage.md#current-unified-coverage-status-2026-10-17) for
its identities and limitations.

Benchmark run
[38828500975](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975)
passed exact-binary parity and the FastAPI-only comparison on all three
platforms. All three category jobs failed. Each Linux system had two Rust
HTTP/1 upload timeouts; macOS completed 30 matched H1 pairs, but 27/30 Rust
throughput ratios were below Uvicorn and the median ratio was 0.748×. HTTP/2
emitted native connection-error diagnostics, Linux x86-64 Hypercorn/uvloop
HTTP/3 `fixed` timed out waiting for response headers, and lifecycle analysis
rejected the expected Rust TCP graceful-timeout diagnostic. There is no
complete qualified performance result. The local worktree contains
uncommitted tracked changes; the hosted evidence is from the clean commit and
does not include those edits.
Three focused hosted H2 diagnostics passed five correctness repetitions each: Linux x86-64 `protocol-scope` ([run 38863229176](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176)), Linux ARM64 `protocol-scope` ([run 38863847199](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863847199)), and macOS ARM64 `request-upload` ([run 38864179333](https://github.com/appunni-m/uvicorn-rs/actions/runs/38864179333)). The Linux x86-64 diagnostic was rerun as attempt 7 on the same commit; its five correctness checks passed, with four timing-valid samples and the refreshed [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176/artifacts/12078313679). None of these single-server diagnostics has a matched Hypercorn comparison. They did not reproduce the generic connection error, identify the original matrix failure, or clear the benchmark gate.

The focused HTTP/3 malformed-frame parity case
`http3.truncated-data-frame-recovery-after-protocol-error` passed 1/1 on the
current local source. It observes `H3_FRAME_ERROR` (`0x106`) for a DATA frame
whose declared payload is truncated at clean stream FIN, as required by
[RFC 9114 §7.1](https://www.rfc-editor.org/rfc/rfc9114.html#section-7.1).
This result exercises the workspace build, which patches crates.io `h3` to
the [local vendored source](../vendor/h3/src/frame.rs); it does not prove that
the standalone Rust crate archive contains or uses that patch. The
`uvicorn-rs` manifest still declares
registry `h3 = "0.0.8"`, and `cargo package --list -p uvicorn-rs` does not
include `vendor/h3`. The focused `cargo package --manifest-path
crates/uvicorn-rs/Cargo.toml --allow-dirty --locked --no-verify` command exits
101 because the versioned `native-app-contract` dependency cannot be resolved
from the crates.io index. Cargo nevertheless left a diagnostic archive at
`target/package/uvicorn-rs-0.1.0.crate`; its presence does not make the failed
package command valid release evidence. Its embedded Cargo VCS stamp records
`c2de34a08a0b5083f830cc59c88182378a7d1a81` with `dirty: true`. I extracted it
into a temporary consumer, supplied only the unpublished `native-app-contract`
from the local checkout, and built the Python extension against the archive
with registry `h3 0.0.8` and no `vendor/h3` patch. The adapter used dirty local
revision `27de9f3ac7d259a3a9b612c3247ab2c60eb27306` (Python 3.12.13, Rust
1.98.1, macOS ARM64). The focused
`http3.truncated-data-frame-recovery-after-protocol-error` input then failed:
the oracle completed the upload and returned a healthy follow-up response;
the extracted target reported an ASGI disconnect, produced no peer close code,
and panicked inside registry `h3 0.0.8` at `frame.rs:57` with “There is still
data to read, please call poll_data() until it returns None.” The target's
follow-up response remained healthy, but the required `H3_FRAME_ERROR`
(`0x106`) behavior was absent. The workspace parity pass still exercises the
patched vendored source only. Do not accept the standalone Rust crate archive
for external consumption until its publishable dependency path carries the
framing correction and the extracted-archive case passes. The candidate
evidence generator records this in `publication_blockers`, and candidate
verification rejects non-empty blocker lists.

The release workflows do not publish packages or create tags. The release
candidate remains blocked by the dirty uncommitted changes and incomplete
qualified performance evidence; the old hosted coverage failure must be
replaced with clean release-candidate evidence before release acceptance.

### Earlier status snapshot (historical)

As of the earlier 2026-10-16 snapshot, a release candidate was not established. Exact-source CI
[run 38790016719](https://github.com/appunni-m/uvicorn-rs/actions/runs/38790016719)
on commit `5a32e3c0d84a02c95fe8a3f01712c895419ea571` has passed Rust quality,
Rust 1.85, native FastAPI-RS composition, and installed-wheel public parity.
Its unified coverage job completed all 717 indexed cases and reported
8,654/8,654 regions and 6,521/6,521 lines. The evidence checker then failed
because the report producer's pending Coverage-MCP request text differed from
the checker's required contract. A later commit corrected the producer/checker
wording. Main has since
advanced through archive packaging fixes to
`6c00d536c52f8f9dd2dc90ac67eb12bd0c58ca59`. Those hosted results predate the
native TCP/TLS integration described below; the corrected coverage gate still
needs a source-matched hosted receipt.

An earlier local 717-case/three-repeat report is from a dirty source
snapshot and is not evidence for this commit. Multi-system benchmark
[run 38787712815](https://github.com/appunni-m/uvicorn-rs/actions/runs/38787712815)
completed on Linux x86-64, Linux ARM64, and macOS ARM64, but every platform
stopped in HTTP/2 before all 140 rows were recorded. The run measured older
commit `5cb4b7b84`. Its artifacts retain the failed inputs; focused current-source
replays of all three HTTP/2 failure classes passed correctness, but host CPU
activity invalidated their timings. No qualified performance result is
available. The previously reported
`http1.disconnect-before-first-asgi-receive` discrepancy also passed as a
single local parity case on the current checkout. See the
[coverage record](coverage.md#current-unified-coverage-status-2026-10-17)
and [benchmark status](benchmark-status.md).

An earlier working-tree unified-coverage attempt ran the 506-case Python
matrix three times: repeats one and two passed 506/506; repeat three passed
505/506. The only failed observation was
`http3.concurrent-stream-load-slow-reader-resource-bound`, where the RSS
stability check returned false after otherwise healthy load, completed
responses, and follow-up requests. The focused case then passed twice on the
updated process-tree RSS sampler, including the 16-stream load, response
hashes, zero active tasks, stable resource rounds, and a healthy follow-up.
The native 206-case matrix completed two repeats before the local runner was
stopped. This is focused working-tree evidence, not a complete post-fix
coverage receipt; the exact-source hosted run remains required.

The workflows upload candidate artifacts but do not publish Rust crates
to crates.io, Python packages to PyPI, create a GitHub Release, or create or
move tags. The project is licensed under
[BSD-3-Clause or MIT](../LICENSE), at the recipient's option, with copyright
© 2026 Appunni M and the original Uvicorn/Hypercorn license notices retained.

## Earlier state before c2de34a (superseded)

The latest complete CI results cited here cover commit
[`5a32e3c0d84a02c95fe8a3f01712c895419ea571`](https://github.com/appunni-m/uvicorn-rs/commit/5a32e3c0d84a02c95fe8a3f01712c895419ea571).
Main has since advanced to `6c00d536c52f8f9dd2dc90ac67eb12bd0c58ca59`; the
native TCP/TLS integration in the current worktree has no hosted run yet. CI
[run 38790016719](https://github.com/appunni-m/uvicorn-rs/actions/runs/38790016719)
has four completed jobs, all successful: installed-wheel public parity, Rust
1.85, Rust formatting/lints/features/documentation, and pinned native
FastAPI-RS composition. Its unified coverage job completed 717/717 indexed
cases and measured 8,654/8,654 regions and 6,521/6,521 lines, but its evidence
check failed on mismatched pending Coverage-MCP request wording. The producer
wording has been aligned with the checker. The single local rerun of
`http1.disconnect-before-first-asgi-receive` passed with
matching oracle and target observations: a disconnect event followed by a
reusable connection returning status 200 and the same response body.

Benchmark
[run 38787712815](https://github.com/appunni-m/uvicorn-rs/actions/runs/38787712815)
finished with failed HTTP/2 category jobs on all three systems. HTTP/1, HTTP/3,
WebSocket, and lifecycle categories completed, but the overall result is
incomplete. The run measures older commit `5cb4b7b84`; it cannot qualify the
current source. The latest complete FastAPI comparison remains run #27 and did
not show a broad gain. No tag or verified candidate has been created.

### Previous run #29 diagnostics (2026-10-14)

The retained HTTP/2 failure is isolated to the Rust asyncio `large-response`
workload: all 10,185 client requests passed and the server exited cleanly, but
its log contained one `BrokenPipe` peer-close diagnostic. The focused local
replay passed with no diagnostic. The current dirty benchmark gate permits
only one exact occurrence for Rust HTTP/2 and still rejects other errors. The
Linux HTTP/3 failure was the Hypercorn asyncio reference timing out on
`protocol-scope` in repetition five; its focused local replay passed. Local
timings from both focused replays were invalid because unrelated host CPU load
was high. A focused current-source stock-FastAPI `fastapi-fixed` run on
2026-10-16 passed all 12 response and shutdown checks, but only four timing
samples passed the per-sample host guard; no asyncio or uvloop pair reached
three valid repetitions. A follow-up preflight rejected before another timing
run. These replays establish case correctness, not a performance result.

### Historical release-gate snapshot (2026-10-16)

This table preserves the release-gate view from October 16. It predates the
749-case hosted report and run 39013640499; use the current status above and
the linked coverage and benchmark records for present evidence.

These gates apply to the requested Rust-native server and thin Python client
architecture. Kata records the work under `ec8x` and `wb4y`; candidate assembly
is tracked by `zep3`.

| Pending gate | Current evidence | Required completion |
|---|---|---|
| Canonical Rust transport and thin Python adapter (`sw8s`) | With default `native-tcp`, the Python ASGI path delegates HTTP/1.1, HTTP/2 over TCP/TLS, and HTTP/3 over Quinn to the Python-free `uvicorn-rs` crate. Python ASGI scope/events and app execution still cross the asyncio/PyO3 boundary. The native Rust service preserves H3 request trailer frames; the ASGI 2.5 adapter presents request body bytes only because the specification defines a response-trailers extension but no request-trailers event. Current dirty-source local coverage passed 748/748 cases, all six full repeats, 8,997/8,997 regions, 6,629/6,629 lines, Coverage-MCP, and offline evidence validation. Clean committed-source and hosted acceptance remain pending. | Verify the native H3 trailer contract and the documented ASGI boundary on the reviewed commit, preserve Python loop, context, callable, exception, lifespan, disconnect, cancellation, and streaming behavior, and keep the support matrix explicit. Do not invent a standard ASGI request-trailer event. Then measure the path against matched Uvicorn workloads. |
| Native framework composition (`wb4y`) | The pinned native FastAPI-RS composition inputs passed 17/17 once in exact-source hosted CI run 38862681888 on `27de9f3`. | Retain the Python-free dependency graph and verify each composition behavior claimed by the released support matrix. Composed TLS/H3, WebSockets, and full framework lifecycle remain outside the current hosted evidence. |
| Python compatibility matrix (`sw8s`) | An abi3 Python floor and individual framework/oracle versions are recorded; a maintained client compatibility matrix is not implemented. | Publish and exercise the exact Python, asyncio/uvloop, ASGI, and upstream integration combinations claimed by each Python client after transport migration. |
| Unified coverage on current source | The current local dirty-source run passed 748/748 cases in three ASGI and three native repeats, with no retries or infrastructure failures. It measured 8,997/8,997 regions and 6,629/6,629 normalized physical executable lines. Coverage-MCP and offline evidence validation passed on matching source/build receipts. Latest clean CI run 38862681888 passed 712 cases but its older manifest measured 8,496/8,650 regions and 6,486/6,592 lines. | Bind the passing 748-case matrix and 100% report to the reviewed release-candidate commit with exact-source hosted evidence. Add or change cases only if that source-bound run exposes a concrete gap or failure. |
| Representative performance (`wh9k`, `k8ft`) | Multi-system run 38828500975 passed parity and FastAPI-only comparison. The Linux H1 category also failed: two Rust upload rows on each Linux system timed out in libcurl after about 15.4–18.0 seconds, followed by Starlette `ClientDisconnect`; macOS completed H1 with 30 matched pairs, 27/30 below Uvicorn and median throughput ratio 0.748×. HTTP/2 emitted a generic connection diagnostic on all systems, one Linux x86-64 Hypercorn/uvloop HTTP/3 fixed-workload header timeout occurred, and lifecycle diagnostic normalization rejected an expected timeout. Three later focused H2 hosted runs passed five correctness repetitions each but did not reproduce the H2 connection error. A single local macOS replay of the 1 MiB/1 KiB-chunk H1 upload passed on both servers, but host contention invalidated timing and did not reproduce the Linux timeout. `performance-acceptance.json` remains `not_proven`. | Diagnose the Linux upload timeout and retained full-matrix HTTP/2 error, resolve the HTTP/3 timeout and lifecycle normalization, then complete the exact-commit matrix with at least three valid repetitions per workload/loop/system and retain throughput, latency, CPU, memory, and source/build identities. Reassess the performance scope against the matched FastAPI evidence; do not claim a broad gain from the current results. |
| Clean commit and hosted CI (`zep3`) | Main commit 27de9f3 has passing Rust quality and MSRV checks, installed-wheel public parity, and native composition; all 712 hosted parity cases passed. Local current-source coverage now passes 748 cases, all six repeats, 100% regions/lines, Coverage-MCP, and offline validation, but the evidence is from a dirty worktree. Benchmark gates remain incomplete and the worktree has uncommitted tracked changes. | Review and commit the intended changes, then run only the hosted gates affected by those changes. Require clean exact-source coverage and benchmark receipts before candidate assembly. |
| Packaged consumer evidence (`zep3`) | Exact-source CI verified the installed normal wheel's public parity. Release artifact jobs were skipped; no candidate bundle has been produced or inspected. | Verify the three supported wheels, sdist, and two Rust archives from the final clean commit, including fresh installed consumers, Python floor, extracted Rust archive builds, licenses, versions, and checksums. |
| Standalone Rust crate H3 dependency | The workspace parity case passes and records the RFC-required `H3_FRAME_ERROR` (`0x106`) with the workspace-only `vendor/h3` patch. A focused consumer build from the diagnostic `.crate` instead resolved registry `h3 0.0.8`; the same malformed-frame input failed because the ASGI app saw disconnect, no peer close code was observed, and the dependency panicked at `frame.rs:57`. The oracle completed the upload and the same-connection follow-up remained healthy. | Make the framing correction available through a publishable dependency path for external Rust consumers. Rebuild a clean archive from the selected dependency source and rerun only this malformed-frame case against that extracted archive. Keep standalone `.crate` distribution blocked until it passes. |
| Performance acceptance in candidate verification (`wh9k`, `k8ft`; release gate `zep3`) | Run 38828500975 is complete but incomplete as evidence: its category jobs failed and `performance-acceptance.json` remains `not_proven`. | Complete the correctness-gated matrix on the exact release commit and record measured gain claims or a documented scope revision. Candidate assembly rejects `not_proven`, partial/stale artifacts, and unsupported or underqualified claims. |
| Immutable candidate and final documentation (`zep3`) | No current candidate or tag exists. | Reconcile support, deployment, feasibility, benchmark, and coverage claims with the final evidence; assemble the bundle from the successful CI run/attempt; verify the annotated tag object and commit; retain candidate manifests and SHA256SUMS. Keep generated logs, profiles, and coverage reports out of Git. |

The current workflow stops at a verified candidate artifact. Registry
publication and a public GitHub Release remain outside this workstream. Native
Rust applications compose the library into their executable; a standalone
native CLI is not part of the selected package contract.

### Performance acceptance gate

The tag workflow selects a completed benchmark run for the exact commit on
`main`. All three platform jobs and the aggregate job must have succeeded. It
downloads the aggregate by artifact ID, checks GitHub's artifact digest, and
revalidates the run and artifact metadata before assembling the candidate.
The verifier recomputes each platform result from retained evidence, checks
the full source and dependency identities, and inspects the retained native
extension bytes for coverage or diagnostic instrumentation. Linux x86-64 is
also compared byte-for-byte with the normal-build native extension used by the
candidate parity audit.

The decision record must cover the maintained stock-FastAPI HTTP/1 workload
inventory. A gain claim needs three or more valid matched repetitions for each
claimed workload, event loop, and system, with throughput, latency, CPU, and
RSS measurements present; throughput or latency must support a gain claim,
while CPU and RSS provide required resource context. A scope revision must cite
a checked-in document and retained qualified measurements. A complete matrix
on its own is not a gain claim. The current record is `scope_revised`: Python
ASGI remains the compatibility and regression path; performance claims target
Python-free Rust-native application composition. The exact-commit focused result
supports that revision, but candidate verification still requires a complete
exact-commit multi-system artifact. The prior run 39020268578 is incomplete
because Linux ARM64 failed an HTTP/3 correctness gate. No tag can currently
produce a verified candidate. The gate does not publish packages, create a
public release, or create or move tags.

### Historical focused migration and coverage evidence

Kata `xzf9` added two native application-panic recovery contracts. The focused
eight-case run passed without retries or infrastructure failures; the readiness
case also detected the original failure in an isolated copy with containment
removed. That snapshot contained 641 inputs (511 ASGI and 130
native). Its selected evidence does not satisfy the full coverage gate or
replace the last 639-case baseline. See the
[coverage record](coverage.md#selected-native-panic-recovery-evidence).

Kata `dsna` adds an explicit native service-error policy as a transport-migration
prerequisite. Six propagation inputs and a default H3 service-error control
brought that measured inventory to 648 (511 ASGI, 137 native). The focused run
passed 16/16, and all six default-policy negative controls detected the intended
abort/reset mismatch. This does not route Python through the native transport
or close an aggregate release gate. See the
[selected policy evidence](coverage.md#selected-native-service-error-policy-evidence).

Four subsequent connection-limit inputs brought that snapshot's inventory to
652 (511 ASGI, 141 native). Ten selected configuration inputs and controls
passed once; oversized TCP/TLS/H3 admission limits return a typed error before
hooks, and the exact H3 runtime ceiling still serves. This does not replace
the full coverage, hosted CI, or performance release gates. See the
[selected coverage evidence](coverage.md#selected-native-connection-limit-evidence).

Nine native TCP EOF inputs bring the current inventory to 661 (511 ASGI,
150 native). Eighteen affected inputs and controls passed once with complete
attribution and no retries. They prove factual raw EOF observation after
response completion, distinguish HTTP/2 stream reset and server shutdown, and
preserve responses after peer write-half closure. This is a historical
661-case snapshot. The later 717-case source-bound report also includes the
opt-in Proactive held-service cases over cleartext and TLS, with complete and
incomplete uploads; it passed three repeats but is still dirty local evidence.
The Python ASGI TCP/TLS path now uses the native transport, but these
generic native cases do not by themselves establish ASGI disconnect delivery.
See the
[selected EOF evidence](coverage.md#historical-selected-native-tcp-eof-evidence).

Normal native CI selects 149 target contracts and retains the one declared
fault contract in unified coverage. A normal build rejects that fault input;
it no longer substitutes a peer reset and reports a false fault pass. Three
normal controls and the instrumented fault case passed their focused checks.
This lane correction is tracked by Kata `rh4d`; see the
[normal and instrumented lane evidence](coverage.md#normal-and-instrumented-native-case-lanes).

Hosted CI [run #110](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430762)
completed with failure. The installed normal wheel passed the complete public
input matrix (243/243), the two Starlette comparisons, and the transient
systemd shutdown case. Rust 1.85 library compilation passed. The Rust quality
job failed because Clippy also linted two intentional panic fault inputs in
[`native_core_contracts.rs`](../crates/uvicorn-rs/examples/native_core_contracts.rs).
The current worktree keeps all-target Clippy enabled and uses
`std::panic::resume_unwind` only in the test-only fault injector, without a
`clippy::panic` allow or expectation. The targeted all-feature Clippy check for
that example passes locally on Rust 1.98.1. A clean hosted CI run for this
exact source is still required. The
integrated native dependency graph
excludes PyO3, but its live composition job fails compiling the pinned
Starlette-RS source: `file_response.rs:89` declares an unnecessary `mut`, and
that checkout denies `unused` warnings. The current worktree caps dependency
lint levels to warnings only for this composition smoke; the separate
uvicorn-rs workspace lint gate remains warning-denied. This was the status at
run #110 and is superseded for the pinned composition slice by the dedicated
jobs in [run 38828501018](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828501018/job/116741620164)
and the latest [run 38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888/job/116848350492).
The latest job passed all 17 H1/H2 inputs with Uvicorn-RS `27de9f3`, FastAPI-RS
`f438a7c`, and Starlette-RS `b4c8a65`, and verified that the integrated
normal/build dependency graph contained no PyO3. The parent workflow still
failed its separate unified coverage gate; its package-artifact and Python-floor jobs
were skipped. This does not supersede the other run #110 failures or establish
a release candidate.

Hosted CI #110 completed its then-current 633-case unified run, but coverage
was below its 100% gate: 7,322/7,380 regions and 5,383/5,417 lines (58 regions and 34 lines
remain uncovered). Platform package and Python-floor jobs were skipped because
of the failed gates. The hosted coverage artifact is retained on run #110;
the exact-source Coverage-MCP review remains a separate release requirement.

Benchmark [run #25](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949)
passed exact-binary public parity on all three systems, but every platform
category job is now terminal with failure. FastAPI-only comparisons had 39/40
timing-valid rows on each Linux system and 2/40 on macOS; all three report
`not_proven`. Stock FastAPI HTTP/1 completed 300/300 correct, timing-valid rows
on each Linux system. macOS stopped at row 124 with four upload correctness
failures (121–124). HTTP/2 stopped on all systems at the unexpected native
diagnostic gate. HTTP/3 stopped on all systems with incomplete results: Linux
Hypercorn large-response checks received fewer than the expected 1 MiB, and
macOS Hypercorn/uvloop timed out waiting for response headers. WebSocket
completed 60/60 valid rows on every system; lifecycle completed 20/20 on Linux
and 19/20 on macOS. These partial categories do not establish a complete
three-system result or a performance gain. The multi-system evidence
aggregation passed, but the documentation job could not create a PR under the
Actions permissions. Run #24 produced no data because its protocol-client path
was wrong; #25 exercises the path correction. See
[benchmark status](benchmark-status.md).

The last full-manifest local attribution report is dirty and therefore does
not clear the hosted release gate. It predates the current HTTP/1 upgrade
helper refactor, so it is a baseline rather than exact-current-source evidence.
Run
`01b6a2a77b06431bbfa132a91bb6de91` passed all 639 cases once (511 ASGI and 128
native), with zero case, infrastructure, or transient failures. It used dirty
source SHA-256
`8c27b2b471e00b746f17d1db95af5d06317782d87df66359bdfaf0bd9cb0fb4f` at
revision `796dee690ca83654cddb97131dc1dee37de96bcd`. Coverage measured
7,373/7,414 regions and 5,420/5,444 lines, leaving 41 regions and 24 lines
uncovered. Coverage-MCP matched the source receipt and fully paginated 176
region groups over nine pages and 22 line groups over two pages; its `tests`
status is `failed` because gaps remain. The run has no complete-repeat matrix
and does not meet the 100% coverage gate. The exact report SHA-256 is
`387aa56d0d4800165a2f6ad8975558f4b056028492119c4b383c585c32dac3b4`; the
build ID is
`31cf4c67bd6305451dd6e5b6fa7d3d0fa92bb30b3f0d4099eb8e3be0f999f4b1`.

The historical focused report at
`target/asgi-coverage-kata-20261014/connection-upgrade-helper-focused/full-report.json`
passed three existing native protocol cases (HTTP/1 WebSocket, HTTP/2 request,
and HTTP/3 request). Coverage-MCP matched its source receipt and found no gaps
in `insert_http1_upgrade_extension`. This selected run verifies that snapshot's
focused refactor only; it does not replace a full current-manifest report or satisfy the 100%
coverage and three-repeat release gates.

The prior 638-case aggregate (`658dbb240d2c42cabaa2727a380ed71f`, source SHA
`a04e92df09a3b53e73649e7f9258b9a6b7fdecbffbc1d1861e90bbc2d929fbc7`) is now
historical. The 639-case report includes the newer native input
`http1.native-websocket-close-reply-flush-failure-preserves-source` and
supersedes the 638-case report for one-pass attribution only. Three complete
repeats, zero missing regions and lines, and a clean exact-commit hosted run
remain pending.

The preceding 635-case local report passed three repeats on the then-current
511-case ASGI and 124-case native manifests, but measured 7,329/7,371 regions
and 5,384/5,408 lines, so it also missed 100% and predates the current
manifest. Three native cases were individually exercised in selected
instrumented reports before the 638-case full attribution run; the 639-case
manifest adds the WebSocket close-reply flush case. The last 639-case report
includes all four for one-pass attribution. The two
HTTP/3 lifecycle cases,
`native.lifecycle-http3-omitted-hooks-still-serves` and
`native.lifecycle-http3-zero-connection-limit-rejected`, both passed selected
instrumented runs; Coverage-MCP reported `source=matches_receipt` and
`tests=passed`. These are not full-matrix results. The added HTTP/1
listener-reaping case was run with
the HTTP/1 and TLS lifecycle cases in another selected instrumented report;
all three passed, and Coverage-MCP matched the source and test receipts. That
report also is not full-matrix evidence. A broader selected report ran all 71
native HTTP/1, TLS, and HTTP/2 inputs successfully, but still showed uncovered
`next_listener_event` regions in Coverage-MCP. The last 639-case full-source
report confirms remaining gaps on its pre-refactor source; three complete
current-manifest repeats, 100% regions
and lines, zero-gap Coverage-MCP results, and a clean exact-commit hosted run
remain required. See the
[coverage record](coverage.md#current-unified-coverage-status-2026-10-17).

The release-preparation changes make both Rust library manifests publishable and give
`uvicorn-rs` a versioned `native-app-contract` dependency. The Linux CI package
job now builds both `.crate` archives, and the release verifier checks their
source members, licenses, dependency metadata, versions, checksums, and
embedded Cargo commit/clean-tree identity. The release-evidence step also
builds each extracted archive with the contract crate locally substituted for
its not-yet-published registry version. The crate READMEs now include install
metadata and usage guidance; `uvicorn-rs` has a compiled minimal Tower server
example, and `native-app-contract` has a lifecycle-hook doctest.

On 2026-10-13, local `cargo package --list --allow-dirty` included the README,
license notices, and minimal example in the `uvicorn-rs` archive (13 files,
135.8 KiB uncompressed) and the README/license files in the lifecycle contract
archive (9 files, 9.5 KiB uncompressed). Both archives built and verified with
exact Rust 1.85.0. The `uvicorn-rs` package build substituted the local
`native-app-contract` source because its registry version is not published.
The lifecycle doctest passed 1/1, warning-denied rustdoc passed for both
crates, and Clippy passed for the minimal server example. Version
synchronization and the prior extracted-archive checks also passed. These
commands used `--allow-dirty` only for local package
inspection; the archives record a dirty source tree and are not candidate
evidence. The changes still need a clean commit and hosted CI; no candidate
bundle has validated the new native artifacts. The release workflow remains
candidate-only and does not publish to crates.io or PyPI or create a GitHub
Release. The support matrix now distinguishes the legacy ASGI probe workload
count from the 15-workload stock-FastAPI H1 category matrix.

Refreshed local Rust archive checks on 2026-10-14 measured 9.8 KiB for
`native-app-contract` and 148.4 KiB for `uvicorn-rs` (uncompressed). Both
archives passed exact source, dependency, license, and VCS inspection, and
their extracted trees compiled in dependency order. Seven added unsafe-path
controls were rejected. The archives and consumer receipt are under ignored
`target/native-archive-final-20261014/`; the receipt records the dirty source
state. This remains local package verification, not hosted release evidence.

The following run-by-run notes are historical attempts, not the current
release-candidate status.

The parser-aware EOF experiment remains isolated. Its cleartext cases pass
against the patched Hyper copy, but the TLS and pipeline comparison found two
candidate failures: raw TCP FIN over TLS can turn into `UnexpectedEof` before
the held response, and a TLS pipeline can lose its follow-up request. See the
[native runtime ADR](adr/0003-rust-native-service-contract.md#peer-closure-and-request-lifetime)
for inputs and limits. This prototype is not installed in production.
RFC 9112 §9.6 says a TCP half-close neither delimits an HTTP request nor implies
that the client cannot read its response. RFC 8446 §6.1 requires TLS
`close_notify` before transport closure so truncation remains detectable; raw
TLS FIN stays a separate error case.

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
`http1.disconnect-before-first-asgi-receive` before timing, while the last
observed Linux jobs passed parity and entered category measurements. The
hosted artifact shows Uvicorn returned `http.disconnect` and uvicorn-rs returned
`http.request` followed by `http.disconnect`; the cause remains unconfirmed.
A clean local wheel from the same commit passed the case 60/60 times. See the
reproduction receipt (`benchmarks/results/2026-10-10/ci13-disconnect-exact72-repro/README.md`).
At the time of that historical run, the checkout was dirty; no release
candidate was assembled from it.

Local dirty-working-tree evidence is useful but does not qualify a release.
The latest local ASGI coverage receipt records 5,561/5,561 regions and
3,997/3,997 lines for the dirty 2026-10-12 source, with three complete 511-case
repeats and no Coverage-MCP gaps. It does not provide hosted or clean-commit
release evidence, and no normal-build parity run was included. A 2026-10-12
`uvicorn-rs-py` candidate wheel passed a narrower local consumer smoke, recorded
in the wheel receipt (`benchmarks/results/2026-10-12/uvicorn-rs-py-wheel-consumer/report.md`).
The stock FastAPI matrix also includes correctness-gated multi-protocol
measurements. These results do not come from a clean exact-main candidate with
successful hosted gates. No tag or release was created. See
[coverage](coverage.md) and [benchmark status](benchmark-status.md) for
evidence and limits.

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
macOS reproduction archive (`benchmarks/results/2026-10-08/macos-arm64-run35-local-reproduction/`).
That manifest is explicitly `local preparation` with `source_dirty: true` and
does not establish a release candidate.

Hosted CI run [37566368036](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036)
on main commit `9d05c72` passed Rust quality, MSRV, and the installed-wheel
public parity/deployment job, including both framework comparisons and the
transient systemd stop. Its independent unified coverage job failed with exit
code 1, and the package candidate jobs were skipped because they depend on
coverage. The artifact and exact job status are recorded in the
framework/deployment evidence index (`benchmarks/results/framework-integration-2026-10-07/evidence-index.json`);
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
| Normal native contracts | Every `target-contract` native input on the normal Rust build; retain the manifest and selection hashes and leave `fault-contract` inputs in unified coverage |
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
Its declared Rust source inventory is the Python adapter's `src/lib.rs`, the
native server's `lib.rs`, `http3.rs` and `websocket.rs`, and
`native-app-contract/src/lib.rs`. The contract crate has no executable counters;
the other four files contribute to the measured denominator under the coverage
builder's feature configuration and `cfg(coverage)` failure seams. Python,
dependencies, optional `runtime-diagnostics`, other platform cfg branches and
the complete official ASGI conformance suite are outside that denominator.
A coverage failure or incomplete repeat fails CI; there is no reduced threshold
or automatic retry into a passing receipt.

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
| Native Rust source archives | Ubuntu 24.04 | `native-app-contract` and `uvicorn-rs` package inventories, metadata, licenses, safe extraction and locked dependency-ordered compilation |

The wheel tag is `cp39-abi3`; the Python 3.9 job validates that ABI floor on
Linux, not every protocol on every Python/OS combination. Linux builds use the
runner's native environment. The recorded wheel tag determines its actual
platform/glibc requirement; this workflow does not claim manylinux2014,
Linux ARM64, musl or universal macOS binaries. No cross-compiled artifact is
presented as a native execution result.

`scripts/check_installed_wheel.py` rejects imports from the editable checkout
and compares the imported native bytes with the supplied wheel. Platform build
manifests bind package hashes, source inputs, version, commit, toolchain and
consumer evidence. The raw package set has exactly three wheels, one Python
source archive, two native Rust source archives, three manifests, three platform
consumer receipts, one source-consumer receipt and the Linux full-parity report
(14 files). Assembly verifies wheel metadata/tags/RECORD, licenses,
normal native markers, source inputs and expected platforms. Repository-only
benchmark archives, test harnesses, coverage profiles, keys and environments
are excluded from distributions.

Maturin 1.14.1's `sdist` command has no `--locked` option. This workspace uses
`sdist-generator = "git"` so the archive keeps the reviewed root manifest,
lockfile, and every Cargo workspace member. The Cargo generator removes unused
workspace members from `Cargo.toml` but leaves `Cargo.lock` unchanged; the
resulting archive cannot rebuild with `--locked`. Keep workspace members such
as `tools/http3-probe` in the source archive. The source checker verifies the
manifest and member inventory, then the rebuild uses
`maturin build --release --locked`, checks input equality before and after
building, and retains the build log. Version agreement includes
`Cargo.toml`, `pyproject.toml`, `Cargo.lock` and `uv.lock`; the workflows do not
hardcode the install version.

## Assemble an immutable tagged candidate

First commit the complete source, input matrix, workflows, examples and
packaging metadata together. The current worktree adds both Rust library
crates to the candidate bundle, binds their source and dependency metadata to
the build evidence, and locally verifies their archives with Rust 1.85.0;
hosted validation of these changes is still pending. Require a clean checkout
and successful complete
`CI` on `main` for that exact commit. A maintainer can then request candidate
assembly by pushing an annotated `vMAJOR.MINOR.PATCH` tag for that commit.

[Release candidate](../.github/workflows/release.yml) follows the immutable
artifact/evidence pattern used by `fontdone` and `image-slash-star`. It gathers
the three Python wheels, source archive, two Rust crate archives and their
matching CI evidence. Publication remains disabled:

1. Verify the remote annotated tag object resolves to the checked-out commit,
   including when checkout materializes only its peeled commit.
2. Require exact tag/manifest/lockfile version agreement and a clean checkout.
3. Find a successful complete main CI run for that same commit.
4. Download only that run's three Python wheel artifacts, Linux source archive
   and Rust crate archives, normal parity, seam-exclusion audit, complete
   unified coverage and Python-floor evidence.
5. Verify package identities and retained evidence, then write bundle checksums
   and a candidate record containing version, tag, commit and CI run ID.
6. Retain the complete candidate bundle for 90 days.

Missing, expired, incomplete or mismatched artifacts fail assembly. Rerun main
CI on the exact commit when evidence expires. Do not move an existing tag to
repair a failure. The workflow has no credentials or permissions for registry
publication, OIDC authentication, repository writes or GitHub Release creation.

## Public release decision

Candidate verification, hosted CI success and public publication are separate
states. A public release additionally needs an explicit distribution decision
that names both Rust crates (`native-app-contract` and `uvicorn-rs`) and whether
to publish the optional `uvicorn-rs-py` compatibility client, reviewed release
notes, the current support/known-limit matrix, exact-source Coverage-MCP
review, source-bound performance evidence (or a reviewed performance-scope
revision), and green hosted evidence. If the Rust crates are published to
crates.io, publish `native-app-contract` before `uvicorn-rs`, which depends on
its registry version. `starlette-rs-py` and `fastapi-rs-py` are owned by their framework
repositories. Experimental H3 limitations and workload-specific benchmark
results remain visible. Use a clean proven commit; do not distribute the dirty
local preparation artifacts as an official release.

The current version notes are in [CHANGELOG.md](../CHANGELOG.md). Keep them in
the `Unreleased` section until a clean candidate has passed the exact-commit
gates and a distribution decision is made.

Dependabot proposes weekly Cargo and GitHub Action updates. Review those
updates and their exact pins before accepting them into a candidate.
