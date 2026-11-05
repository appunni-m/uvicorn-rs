# Release completion plan

This is the execution guide for the open Kata tasks, agreed from the maintainer's
2026-10-28 request to define concrete work and prepare a build for their own real
FastAPI evaluation. Kata remains the system of record. The maintainer will run
their application trial; collecting their application or running its load is not
a prerequisite for completing the repository work.

## Active release goal — 2026-11-05

The current user-provided release goal requires an accepted independent
Coverage-MCP review bound to the final clean source and its exact raw unified
coverage report. This supersedes the 2026-11-04 waiver below. Require every
unfiltered region and line page, matching source/build receipts, passing test
status, no remaining observations, and the actual MCP transcript and receipt.
Candidate qualification must revalidate that receipt against the same source,
run, artifact, and report. Do not synthesize or manually assemble review pages.

The raw coverage gate remains 100% for regions and lines, with three passing
ASGI and native repeats, complete attribution, and zero failures or
infrastructure retries. Retain the source, run/attempt, artifact ID/digest,
report/context hashes, build identity, and revalidate them during candidate
qualification.

## Historical owner decision — 2026-11-04 (superseded)

At the time, the project owner waived independent Coverage-MCP review while
retaining the exact-source 100% raw coverage gate. The active release goal now
reinstates the independent review requirement; the remaining raw coverage and
identity requirements continue to apply.

## Exact-main evidence update — 2026-11-04

CI #661 passed on `feb955d2758166ad8c4b519903fd1318b29e7d2d`: 1,453 unified
coverage cases passed, with three ASGI and three native repeats and 100%
coverage (14,965/14,965 regions; 10,984/10,984 lines). Raw artifact
13313323556 has GitHub digest
`sha256:d7ce785d590e7195be7eaa57e7761b8acb182ac4475599e2ab43cbd45567745d`.
The main CI package and consumer jobs for Linux x86-64, macOS ARM64, Windows
x86-64 and the Python 3.9 floor passed.

Benchmark #283 completed the exact-source Linux x86-64, Linux ARM64 and macOS
ARM64 matrix. Its aggregate artifact 13313622768 has digest
`sha256:99b295b2b5fcea8d04604aa8e3b55f16919403a48ed1fa94c716d9b2474931aa`.
The HTTP/1 FastAPI validated route is slower on all six system/loop pairs;
H2/H3 gains vary by workload, and WebSocket text echo regresses. No general
FastAPI performance advantage is claimed. Raw-only candidate/release evidence
workflow changes are on `develop`; candidate assembly and publication still
require the reviewed changes on `main` and a candidate for the resulting
commit.

Focused upload diagnostic #284 ran only `fastapi-upload-1m-write-1k` on Linux
ARM64 at the same exact-main source. Rust and Uvicorn completed 2,307 and 3,227
requests, respectively, with zero failures and passing lifecycle gates; the
15-second client timeout remained unchanged. Both ASGI traces report no receive
wait above 100 ms. Artifact 13315456620 has SHA-256
`18f2d482353e1427c32cecade84d7da960d389a35ed31ec2fbd982e0af8671a8`. Tracing
invalidates timing, and no stalled request was available to trace. Keep `nbmg`
open for review of the missing first-failure evidence; this run is neither a
root-cause finding nor a performance result.

## Upload timeout investigation correction — 2026-11-04

Historical ARM64 failures occurred under both event loops. Artifact
12103983742 from run
[#39036702600](https://github.com/appunni-m/uvicorn-rs/actions/runs/39036702600)
records `uvicorn-rs-asyncio` failures in repetitions 2, 3 and 5, plus a
`uvicorn-rs-uvloop` failure in repetition 5. A later ARM64 run
[#39185987961](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987961)
records `uvicorn-rs-uvloop` failures in repetitions 2 and 3. In the later
artifact, both libcurl records show all 1 MiB supplied and uploaded, no response
bytes or status, no first response byte, a 15-second timeout, and
`new_connections=0` (the failing attempt reused an HTTP/1.1 connection).
The exact failed transfers were worker 2 / attempt 4 and worker 3 / attempt 25;
both had 1 MiB of upload-callback bytes and 1 MiB reported uploaded, with zero
downloaded bytes. The retained server log is empty, so there is still no server
request ID or first-stall event for either transfer.
FastAPI then observed `ClientDisconnect`; that is the timeout consequence, not
the first divergence.

Focused diagnostic [#287](https://github.com/appunni-m/uvicorn-rs/actions/runs/41862563840)
on commit `372463a438bcce50df6850077175e6097e7aa378` used
`uvicorn-rs-asyncio` and `uvicorn-asyncio-httptools`: the focused workflow
hard-coded asyncio. Its three 30-second samples completed with zero failures,
and all traced Rust requests delivered the full 1 MiB body to ASGI. Focused
diagnostic [#288](https://github.com/appunni-m/uvicorn-rs/actions/runs/41879387733)
on `af6c544cbac9ed99756772b2cfe355dc341c789a` selected uvloop and likewise
completed three 30-second Linux ARM64 samples with zero timeouts. That run
printed every request trace and generated hundreds of megabytes of logs, which
could perturb scheduling. The trace now retains bounded per-request events in
memory and emits only a request that lasts at least 100 ms, reports an abnormal
read/queue/cancellation event, or delivers fewer bytes than Content-Length. The
record also states the expected byte count and why it was emitted. The next
diagnostic is limited to this same Linux ARM64 uvloop upload pair, ten attempts,
concurrency eight, and the unchanged 15-second timeout. This is an explicit
follow-up to the user's request for more trace and a root cause; it is not a
broad matrix or performance measurement. No runtime cause or fix is established
yet.

## Upload timer hypothesis — 2026-11-05

Comparing the failing source from run #391859 with current `develop` found one
HTTP/1 request-body-path change that falls between the failure and the
non-reproducing current runs. The failing source `94c89b79` recreated
`sleep_until(deadline)` on each body-pump loop. Commit `3fe4206bc` changed that
to a pinned, resettable Tokio `Sleep`; both versions use the same 5 ms batch
window. Current trace run #289 used the pinned version and had ten clean 30 s
samples, but its Python ASGI timing wrapper changes scheduling, so it is not a
controlled comparison. This is a plausible lead, not a confirmed cause.

The focused upload-trace mode runs the historical 5 s workload without the
Python timing wrapper and can select the old recreated timer only in a
`runtime-diagnostics` build. It retains libcurl's callback/progress trace and
the bounded Rust body-pump/ASGI trace; warm-up failures retain the same partial
client metrics as measured failures.

Same-source A/B evidence is now available. Run [#295](https://github.com/appunni-m/uvicorn-rs/actions/runs/41903988660)
used the pinned timer for three Linux ARM64 / uvloop pairs; run [#296](https://github.com/appunni-m/uvicorn-rs/actions/runs/41905701684)
used the recreated timer for three pairs. Both kept the 1 MiB body, 1 KiB
writes, concurrency eight, and 15 s client timeout fixed. All 12 candidate and
reference rows passed with zero failures. Candidate median throughput was
530.9 requests/s pinned and 532.9 requests/s recreated; reference medians
were 644.7 and 645.8 requests/s. The trace artifacts contain no per-request
event records because no request failed or exceeded the 100 ms trace threshold.
These diagnostic timings are invalid as performance evidence. The result does
not support the timer refactor as the timeout cause, though the small sample
cannot rule out a rare schedule-sensitive race.

The historical failure rows all reused their HTTP/1.1 connections
(`new_connections=0`). The planned focused discriminator was a matched
`Connection: close` workload against the existing persistent-connection case,
keeping Linux ARM64, uvloop, 1 MiB body, 1 KiB writes, concurrency eight, and
the 15 s timeout fixed. The diagnostic C client now reports completed
transfer counts split into new and reused connections; a two-request loopback
check confirmed that persistent and `Connection: close` modes produce the
expected counts. The changed input was limited to three attempts; no matrix
was run. No runtime fix is claimed until a failing trace identifies the first
stalled boundary and a focused regression passes.

The bounded comparison is complete on source `422c731fcf45cbd77c4a4ce2c1ecd20b8cedfbb5`.
Run [#302](https://github.com/appunni-m/uvicorn-rs/actions/runs/41919147440)
replayed the persistent-connection input for three Linux ARM64 / uvloop pairs
with the request-level client, ASGI, and Rust traces enabled. All six rows had
zero failures. Each candidate row opened eight connections and reused them for
the remaining 14,685, 15,333, and 15,038 transfers. Across the retained slow
candidate traces, 24–29 of 32 ASGI requests per repetition matched a libcurl
trace; maximum body-frame, ASGI receive, and body-queue waits were 12.92 ms,
14.42 ms, and 14.47 ms. Artifact `13367385136`, ZIP SHA-256
`f09478e6c992bb8fcabf5de88a2e60244c4c4b13ebfd89c338743e0d739adf3d`.

Run [#303](https://github.com/appunni-m/uvicorn-rs/actions/runs/41921247555)
changed only the client connection policy to `Connection: close`, again for
three matched Linux ARM64 / uvloop pairs. All six rows had zero failures. Every
candidate request used a new connection; none were reused. The retained slow
candidate traces matched 23–27 of 32 ASGI requests per repetition to libcurl.
Artifact `13366034345`, ZIP SHA-256
`c9d2fe4404cd562571b288ed79f30f159a06ba073b9e0929c500e631b2252259`.

Neither workload reproduced the historical 15 s timeout, so neither supplies
a failing request ID or a first-divergence boundary. The old failures being on
reused connections makes connection reuse a lead, but current persistent
connections also pass; reuse is not established as a cause. Both runs include
runtime and ASGI instrumentation and have invalid timing for performance
claims. Keep `nbmg` open and do not repeat these inputs without a new trigger
source-level lead.

## Targeted historical request traces — 2026-11-05

The original worker/attempt IDs were used as the selector for run
[#304](https://github.com/appunni-m/uvicorn-rs/actions/runs/41926096472), on
source `cc387d56da792057e9002dcd601a90232743fba9`. The focused trace-only run
selected Linux ARM64, uvloop, `fastapi-upload-1m-write-1k`, three 5 s samples
with 1 s warmup, concurrency 8, 1 MiB uploads in 1 KiB callbacks, the
recreated body-batch timer, and the unchanged 15 s timeout. It traced only
workers `2:4` and `3:25`, without the ASGI timing wrapper. Artifact
`13370345234`, ZIP SHA-256
`5e20189668deda55cd6749538d19b9f4d2b707fc885a62c690b27dd7a34a3eb8`.

All six selected candidate transfers and all six matched Uvicorn transfers
completed with zero failures. Each selected transfer reused its connection
(`new_connections=0`); candidate client durations were 9.59–18.58 ms. For each
candidate request, the Rust pump read and offered exactly 1 MiB, ASGI received
1 MiB, and the response completed with status 200. Maximum selected ASGI
receive wait was 6.65 ms and maximum body-queue send wait was 4.39 ms. No
15-second stall occurred, including at the exact worker/attempt positions and
with the timer behavior from the historical source. These diagnostics have
invalid timing for performance evidence.

This weakens the hypotheses that the observed attempt positions, connection
reuse alone, or the timer refactor are sufficient triggers. The traces show a
complete request path, not the first stalled boundary from the historical
failure. No production behavior change is supported. Keep `nbmg` open pending
a captured failure with a request ID or a new, concrete trigger.

## Live upload checkpoints — 2026-11-05

Review of the trace lifecycle found that request events were emitted only when
the traced request was dropped. A task that remained pending through client
timeout and process cleanup could therefore lose the live state at the actual
stall. The focused diagnostic build now emits a bounded one-second snapshot
only for requests carrying the selected upload trace ID. Checkpoints identify
whether the Rust pump is waiting for another Hyper body frame, blocked sending
body data to the ASGI queue, or the application is waiting in `receive()`. Each
event retains elapsed wait duration and the existing per-request byte totals;
the final drop record remains available, and the report parser deduplicates
events repeated across snapshots. Normal builds and nonselected requests do
not enable heartbeat timers.

The focused parser and trace-ring tests pass, and both the normal and
`runtime-diagnostics` Cargo checks pass. This adds observability, not a runtime
fix. The next useful measurement is one focused Linux ARM64/uvloop replay of
`fastapi-upload-1m-write-1k` with the same 1 MiB body, 1 KiB writes, concurrency
8, and 15 s timeout. Keep `nbmg` open until a timeout trace names the first
stalled boundary or a matching historical-kernel replay reproduces the event
order. Do not run a benchmark matrix from this diagnostic.

## Fixed contract and evidence

- PyPI distribution: `uvicorn-rs`; imports and command: `uvicorn`; optional
  command alias: `uvicorn-rs-py`. The internal Cargo/PyO3 package remains
  `uvicorn-rs-py` and is not a crates.io release target.
- Cargo releases: `asgi-lifespan-protocol-rs`, then the Python-free `uvicorn-rs`.
  HTTP/3 is optional under `http3`. No separate H3 or Quinn package is published.
- Publisher: `.github/workflows/release.yml`. `candidate.yml` builds and verifies
  candidates. Documentation deployment is separate.
- Compatibility authority: the pinned Uvicorn 0.54.0 source in
  [the public contract](uvicorn-0.54.0-contract.md). Use the existing
  `tests/parity/manifest.json`, its indexed inputs, `tests/native-core/manifest.json`,
  and `examples/native-fastapi-contracts/manifest.json`. Do not create a second
  operation inventory or require arbitrary combinations outside this contract.
- The current manifest has 151 operations and 90 execution profiles. Those counts
  describe its inventory, not completeness of upstream compatibility.
- Platform acceptance uses the existing CI profiles: Linux x86-64, macOS ARM64,
  Windows x86-64 on CPython 3.12.13, plus the declared Python 3.9 wheel-consumer
  check. Other Python versions need their own evidence before being claimed as
  tested. The Python floor check does not establish Uvicorn 0.54.0 parity there.
- Each accepted receipt identifies the clean source, manifest/input digests,
  binary or package hash, environment, command, result, and workflow attempt.
  A PR merge ref and its branch head are different revisions: retain both and
  let the existing identity validators decide applicability.

The owner decision above changes only the independent-review requirement.
Historical measurements remain historical. A task closes on its own deliverable;
downstream publication gates belong to the release tasks rather than being
copied into every prerequisite.

### Release audit — 2026-11-03 (PR #21 / CI #637–639)

The following completed-source receipts precede the recycling removal.
[CI #640](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412)
qualifies the changed runtime: Linux/macOS each pass 786/786 and package
consumers; the Python 3.9 floor, exact-archive standalone H3 rejection/recovery
and macOS replacement/rollback checks pass. Windows packaging stops after a
stock SIGBREAK shutdown timeout. Focused #641 captures its TCP recovery and
the known startup failure together; raw parity stays failed and the composed
gate requires both signatures plus a clean candidate. Its updated checker
still needs hosted acceptance. The original coverage job remains running;
do not restart it merely because Windows failed. Full final-main evidence and
the normal three-system benchmark remain required.

Changes are developed on `develop` and promoted through
[PR #21](https://github.com/appunni-m/uvicorn-rs/pull/21).
[CI #637](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084)
passes Linux and macOS public parity (786/786 each), their candidate checks,
the Python 3.9 wheel consumer, Rust quality/MSRV and native composition. Its
clean producer is `00f38c82dd869ba0dcc7068cbc5cc769cd0f6294`. Its unified
matrix passes all 1,451 cases and three full verification repeats, measuring
14,809/14,809 regions and 10,894/10,894 physical source lines. The job fails
after measurement because the validator incorrectly requires raw LLVM
function-line totals to equal unique physical source-line totals. The repair
independently replays LCOV line and hit sets from the retained objects/profile
and preserves raw JSON counter checks. Twelve focused regression checks and
an actual retained-object fixture pass; cross-host replay also reproduces
the captured report's exact line sets and raw JSON. Recorded Linux toolchain
acceptance then passes in [CI #639](https://github.com/appunni-m/uvicorn-rs/actions/runs/41629464593),
which strictly replays every retained case and aggregate profile with the
recorded Linux LLVM bytes. Its audit archive SHA-256 is
`7379fcf882c2ab804fc4328539ac97e8f9694d70f6db35b913c984b99b5f4584`.
Coverage task `b8k7` is closed for this producer. The Windows raw matrix is 758/759,
with one stock-Uvicorn startup crash, so its package qualification stopped.

[Focused CI #638](https://github.com/appunni-m/uvicorn-rs/actions/runs/41624376500)
then exercises only the three affected Windows inputs on the pushed source.
All three candidate lifecycle contracts pass. Raw parity retains the two
stock-reference defects, accepted only through the separate startup and
shutdown policies. It does not replace full final-source Windows packaging.
See the [current compatibility record](../uvicorn-compatibility.md#current-status-2026-11-02)
for artifact identities and the exact acceptance scope.

Actual Coverage-MCP review of CI #637 completes all 45 region pages and one
line page with source `matches_receipt`, tests passed and zero gaps. Receipt
SHA-256 is `4f77ad641d4105dfa1f66ff757cf30dcf2d8957a5a466496b5a407ad92ee8330`;
attachment passes. This review is bound to the captured producer, not final
main. The hosted exact-main handoff remains open under `7t4g`.

Interim `[skip ci]` commits avoid broad unchanged reruns while focused tooling
and Windows checks qualify their changes. Required PR checks remain pending;
complete final-source CI is still required before merge and release. Coverage
acceptance precedes benchmark timing; independent Coverage-MCP review remains
required by the active release goal. Compatibility
task `x3az` and all ten children are closed. The capped Linux ARM64
[upload diagnostic #275](https://github.com/appunni-m/uvicorn-rs/actions/runs/41632864829)
completes three candidate/reference pairs with zero failures; it does not
reproduce the historical timeout or establish its cause. Its instrumented
rows are diagnostic only.

The `peer-read-comparison` dispatch mode uses the fixed plan in
`tests/performance/peer-read-comparison.json`: four ordinary-FastAPI workloads,
both event loops, five adjacent on/off pairs per cell and one Tokio worker.
It builds the control in a separate checkout and empty Cargo target, verifies
13 affected parity cases on each installed normal wheel, and retains every
attempt and rejected sample. Local timing was rejected before sampling because
of unrelated CPU load. [Focused run #277](https://github.com/appunni-m/uvicorn-rs/actions/runs/41635726267)
built both Linux ARM64 wheels, then stopped before parity or timing because
the driver resolved the oracle virtualenv's Python symlink to a base
interpreter without Uvicorn. The driver now preserves that executable path;
a regression check imports a package available only in the virtualenv.
No performance result or retention decision comes from the failed run.
The earlier run #276 was cancelled
before parity or timing after its selector incorrectly started full jobs;
the corrected selector admits only `full` dispatch to the full matrix.

The completed [on/off experiment #278](https://github.com/appunni-m/uvicorn-rs/actions/runs/41636866892)
retains 39 valid pairs from its 40-pair plan on Linux x86-64. The workflow
failed only during analysis; the installed-Python identity join is repaired and
the existing rows pass offline analysis without new measurements. Upload gains
are mixed and the small-response uvloop guard regresses, so the frozen retention
rule rejects recycling. Commit `893fd9202057c89eb8cbfff127a747e51a55dc41`
removes the return-buffer channel and preserves the read bound and behavioral
contracts. Its clean normal macOS ARM64 wheel passes all 13 affected installed
parity cases and strict source/native verification. The [decision record](../benchmark-status.md#buffer-recycling-decision-and-arm64-trace-2026-11-03)
retains benefits, regressions, invalid rows and exact evidence identities.

Focused ARM64 H3 trace #279 passes 40 requests with zero failures and clean
shutdown; it does not reproduce the old missing-stream lookup. Its timing is
invalid and no unchanged diagnostic repeat is planned. The upload investigation,
three-system normal benchmarks, final candidate, merge and publication remain
open. The buffer removal changes Rust source, so CI #637's accepted coverage
and independent review remain historical; collect final-source coverage and
the exact-main review handoff before release.

### Earlier release audit — 2026-11-03 (PR #21 / CI #629)

Implementation remains on `develop` and promotion remains
[PR #21](https://github.com/appunni-m/uvicorn-rs/pull/21). CI
[#629](https://github.com/appunni-m/uvicorn-rs/actions/runs/41582985537)
tests runtime batch `a2a02070fe573c61b84aed90f4f48bdb5f267131` through clean
merge source `1c8f16c80e4ac5115c9282037b30473d0016c04a`. Linux public parity
passes 786/786 and its candidate package/consumer checks pass. Rust quality,
MSRV, native composition and release-evidence contracts pass. macOS and Windows
candidate parity and full coverage are still running at this audit snapshot.
[Documentation #261](https://github.com/appunni-m/uvicorn-rs/actions/runs/41582985534)
passed for the runtime batch, before this documentation refresh.

CI #627 completed all 1,449 unified cases and three complete verification
repeats, but failed coverage at 14,754/14,756 regions and 10,866/10,867 lines.
The runtime batch adds normal/fault inputs for completed-application body
teardown and simplifies redundant WebSocket deadline dispatch. Seven related
selected checks pass; the full new report must confirm 100% coverage. The
Coverage-MCP projection now maps recorded checkout paths to repository-relative
source receipts; focused handoff checks pass. Its accepted final-source review
and reviewed handoff remain pending. This reporting-only fix is commit
`a015ec0de570edef1fe28a8ddcc86cd40256218e` and does not alter server behavior.

The stock Windows oracle remains unstable. CI #627 completed 757/758 comparisons
with one stock-Uvicorn worker listener failure/replacement. Controlled untraced
Server 2025 run
[#630](https://github.com/appunni-m/uvicorn-rs/actions/runs/41583517779)
completed 15 selected comparisons, with 14 passing and one stock-Uvicorn SIGINT shutdown hang;
the candidate completed all 15 cleanly. The runner-image hypothesis did not
resolve the failure. The failed comparison remains visible and unchanged
reruns are not planned. The required Server 2022 platform gate remains open.
After compatibility acceptance, the bounded upload diagnostic, matched
three-system FastAPI measurements and buffer-reuse decision still precede final
artifact qualification and publication. No release tag or package was published
by this audit. The maintainer will run their own FastAPI application trial after
repository acceptance.

### Earlier release-candidate snapshot — 2026-11-02 (PR #21 / CI #618)

Open [PR #21](https://github.com/appunni-m/uvicorn-rs/pull/21) promotes
`develop` head `87ab887b07c7d2f54b868dec16b115f93026ca69` to `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. CI #618 has completed. Its
candidate manifests bind the Linux and macOS artifacts to clean merge source
`a1e1f47b46be6e2c9419639baed02e71f2c41b75`. Active implementation remains on
`develop`; `main` changes through PR #21 only.

The side-branch audit is complete. Current remote tips for
`codex/windows-worker-groups`, `codex/uvicorn-rs-compat-hooks`, and
`codex/uvicorn-rs-coverage-events` are ancestors of `develop`; the Python
license-manifest fix on the latter has an equivalent patch already in
`develop`. `codex/windows-oracle-signal-trace` has one unique test-only signal
trace refinement. `codex/windows-shutdown-diagnostic` has five unique commits
adding environment-gated diagnostics and a test worker-count override. These
are diagnostic changes, not missing product fixes; no PRs exist for the listed
branches, and no branch needs to be checked out or merged separately.

CI [#618](https://github.com/appunni-m/uvicorn-rs/actions/runs/41451660747)
passes Rust quality/MSRV/features/docs, native contracts, native FastAPI-RS
composition, release-evidence contracts, Linux and macOS public parity, and
Linux/macOS candidate artifact consumers. Public Uvicorn 0.54.0 parity is
784/784 on Linux x86-64 and 784/784 on macOS ARM64. Windows x86-64 is 756/757,
with zero behavior mismatches and one stock-Uvicorn two-worker shutdown-timeout
infrastructure failure. Focused Windows run #619 passes that case 1/1; it does
not replace the full Windows result. The Windows candidate job stopped after
parity, so its package, consumer, and archive steps did not run. The Python 3.9
wheel-floor job was skipped after that failure.

The failed input is
`python-api.module-cli-web-concurrency-two-workers-serve-request`. In this
attempt the stock Uvicorn oracle received SIGINT, terminated both workers,
finished worker 4724, then remained waiting for worker 7812 until the harness
timeout. The candidate returned HTTP 200, exited cleanly, and reported clean
shutdown for both workers. The captured trace does not identify why the oracle
worker did not exit; it supports an oracle-side infrastructure timeout, not a
candidate behavior mismatch. The focused #619 signal trace passed, but CI #618
is terminal and its Windows candidate job stopped before packaging and consumer
verification. After the final compatibility/source batch is pushed, the
exact-source PR run must finish the Windows matrix and candidate
packaging/consumer steps; the old #618 result cannot qualify changed source.

Exact-source Linux candidate bundle [13146517275](https://github.com/appunni-m/uvicorn-rs/actions/runs/41451660747/artifacts/13146517275)
and macOS bundle [13146676910](https://github.com/appunni-m/uvicorn-rs/actions/runs/41451660747/artifacts/13146676910)
have matching manifest hashes and passing clean consumers. Linux includes both
intended Cargo crates, the `uvicorn-rs` wheel, and sdist. No Windows candidate
bundle is available. See [release evidence](../releases.md) for archive and
payload checksums.

The unified report completed three ASGI repeats of 1,184/1,184 cases and three
native repeats of 259/259 cases, with no failures, infrastructure failures,
retries, or unrun cases. Its 100% gate failed at 14,861/14,895 executable
regions and 10,915/10,933 lines (34 regions and 18 lines missing). The report
is artifact 13149969193, bound to clean merge revision
`a1e1f47b46be6e2c9419639baed02e71f2c41b75`; its archive SHA-256 is
`5524656c4c47090361551e83540090e6fb078f5ab534560efa85b86546ab2f56` and
report SHA-256 is
`8d7cbfd7abbb2fd8322bb12725a5a48386c4459ae5a1de4c2bcce5b7c565e636`.
Independent Coverage-MCP review requires a later successful, source-bound
report. Matched three-system ordinary-FastAPI benchmarks remain incomplete and
follow the user's parity-first order. The Linux ARM64 upload timeout and
incomplete HTTP/3 comparison still need resolution; current partial results do
not establish a broad performance gain.

Docs CI #256 passed for PR head `87ab887`, before the current local refresh.
At this snapshot, PR #21 still points to `87ab887`; local status commit
`844cbd3`, focused coverage commit `9525807`, and this documentation refresh
are not covered by CI #618 or Docs #256. The local strict MkDocs build passed with
`uv run --with-requirements requirements-docs.txt python -m mkdocs build --strict`;
the documentation inventory found no errors. CI must revalidate these commits
on PR #21 after `develop` advances.
The maintainer will run their own FastAPI apps after repository acceptance.

The Linux and macOS bundles are tied to CI #618 and are not final release
artifacts until every gate passes on the accepted source. Rebuild or recheck
all platform candidates from the final qualified source before publication.
Do not merge PR #21 or publish Cargo/PyPI while coverage, independent review,
full compatibility, benchmarks, docs, or Windows candidate verification remain
open. After qualification, publish Cargo locally first as requested, then PyPI
`uvicorn-rs` through `release.yml`.

### Earlier release-candidate snapshot — 2026-11-01 (PR #21 / CI #594)

Draft [PR #21](https://github.com/appunni-m/uvicorn-rs/pull/21) promotes
`develop` to `main`, from base `86e72e181d00feca1b4db7f30377d5d9d4345b83`
to source head `f487bb5e40e3f3d6fdf07900a0ec859f1cb83968`. It replaces PR #19,
which used `codex/uvicorn-rs-consolidation` and was closed unmerged to keep the
promotion path on `develop`.

Exact-source CI [run 41301339884](https://github.com/appunni-m/uvicorn-rs/actions/runs/41301339884)
passed the Linux x86-64 installed-wheel public matrix 782/782 against Uvicorn
0.54.0, with zero failures, infrastructure failures, or not-run cases. Public
parity artifact `13082121608` has archive SHA-256
`bb84397472d5ef533eeb47a456ddd9d4159fb91748e24ce33a977eeddbd4b82b`; its wheel
SHA-256 is `61935e8b31c7cdd33f4bc8973934470e873f40e696d72843a5e4844d3078a1f8`.
The report includes the custom protocol, `ssl_context_factory`, HTTP/1 upload,
HTTP/3 early-app-return, and response-header overflow rows, all passing on
Linux. The clean-source Linux candidate bundle (artifact `13081613812`, archive
SHA-256 `050677288013ec15b0549065e816462244947aa9ec83aaaf7b56aacf31c0f041`)
passed the Linux wheel and rebuilt-sdist consumers plus native Cargo consumer
checks for both release crates, including the optional `http3` feature. All
seven manifest-listed payload hashes match; the manifest records clean source
at merge ref `9250f89800a3404a0789be0d2c39a56844cb063b`. Rust formatting/lints,
MSRV, feature builds, rustdoc, native HTTP contracts, and pinned native
FastAPI-RS composition also passed. Windows x86-64 candidate parity completed 755 cases: 750 passed, zero
behavioral mismatches, and five infrastructure failures in two-worker CLI
shutdown. The Windows candidate job failed before package and consumer steps
(artifact 13082273455). Focused run #595 timed out in the stock Uvicorn oracle
before candidate execution (artifact 13083216067). The three-repeat unified parity/coverage step for head f487 was active when
this report was updated; no final total is recorded here. Follow-up develop
commit 79549a84d broadcasts worker shutdown signals before waiting for
acknowledgements. CI #594 predates this commit, so focused Windows parity, a
new exact-source coverage result, and an accepted independent review receipt
are still required on the follow-up head.
macOS ARM64 installed-wheel parity passed 782/782 (artifact `13082370703`,
SHA-256 `a34c8c8502c46d4d48bb8d6182ad6b0ed637d04f5d9593af8a646c333781d9d1`).
Its clean candidate wheel consumer passed (artifact `13082505341`, archive
SHA-256 `96c664511c67cb147263682c1b2dfe9e9f13b53db7b93ab6e8bdb31919b7b375`,
wheel SHA-256 `dc8f51b4345686328e5c5afa7ee9af974e12eb9a20ca432938a2fa9f37795897`).
Documentation run
[41301339893](https://github.com/appunni-m/uvicorn-rs/actions/runs/41301339893)
passed. The follow-up head 79549a84d must pass focused Windows parity and a fresh
full CI run before PR #21 can leave draft or merge.

## Execution order and stopping rules

### Windows worker shutdown diagnosis — 2026-11-01

PR #19 CI [#559](https://github.com/appunni-m/uvicorn-rs/actions/runs/41229020477)
completed on head `4477b96d9fe2828d8f99e4f47945bcb202e59d8c` (merge ref
`38302d39fe623fbb484c44b22c9b11e38c690223`). The Windows installed-wheel
matrix executed 727 cases: 724 passed, zero behavior mismatches, 3
infrastructure failures, and zero not-run cases. Two failures were Uvicorn
oracle shutdown timeouts; one was a candidate shutdown timeout. Traces from
focused runs #560 and #561 establish that Ctrl+C reached only one worker in the
failing observation and both workers in the passing observation. CPython's
Windows multiprocessing spawn creates worker processes without
`CREATE_NEW_PROCESS_GROUP`; Uvicorn's Windows supervisor then sends
`CTRL_BREAK_EVENT` to worker PIDs, which are not separate console process
groups.

The candidate gives each Uvicorn worker its own process group so the supervisor
can target it with Ctrl+Break. The focused oracle uses a test-only shim for the
same process creation flag. Its app, CLI arguments, supervisor signal, and
compared results stay unchanged. This platform process group change makes
graceful shutdown deterministic; it does not claim stock Uvicorn already sets
the flag.

Focused run [#562](https://github.com/appunni-m/uvicorn-rs/actions/runs/41235353193)
on `a2908d3ac2b77e72e21ad5538c03f323ee8d4078` passed two of three cases. In
`python-api.module-cli-two-workers-serve-request`, the oracle timed out after
only worker 3832 recorded SIGBREAK; the candidate did not report a shutdown
failure. The trace omitted the supervisor `os.kill` requests because it watched
`SIGBREAK` (21) while Windows `CTRL_BREAK_EVENT` is passed as 1.

The corrected trace was used in focused run [#563](https://github.com/appunni-m/uvicorn-rs/actions/runs/41236381416)
on `b65e402a54ececa66297bd3f4e18fbb1ec6061c3`. The remaining case passed 1/1
with zero infrastructure failures. Artifact `13055747302` (SHA-256
`d41593e296eef99528f7bb9f8c08de1dde92f0b35da067af9da38181e4fe3f5a`) records
both workers created with `CREATE_NEW_PROCESS_GROUP` (`512`), per-worker
`CTRL_BREAK_EVENT` (`1`) requests, and both workers handling `SIGBREAK` (`21`)
before clean exit. The other two focused cases passed in #562, and candidate
runtime code was unchanged between the runs. The prior oracle-only timeout may
still reflect nondeterministic delivery; the final Windows matrix must pass on
the release candidate before compatibility is accepted.

### Exact-source PR validation — 2026-11-01 (CI #586)

At the time of this CI run, PR #19 was open and draft against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`, with pushed head
`d5f983c43615df5990abfc73fcfc73a3460a86c7`. Exact-source CI
[run 41281097988](https://github.com/appunni-m/uvicorn-rs/actions/runs/41281097988)
passed Rust formatting/lints, feature builds and strict docs, the minimum Rust
version, the artifact/Coverage-MCP handoff contract, and the 17-input native
FastAPI-RS composition. Linux x86-64 parity passed 755/755 and its candidate
artifact/consumer passed (artifact `13073349195`, SHA-256
`32c5f281febbe84bd7dda7b1017b2a6afa87667fee1e93a16e287a9eb6bd573b`).

macOS ARM64 parity passed 754/755. The single mismatch was
`python-api.module-cli-worker-restarts-after-two-crashes`: response and process
outcomes matched, but the target logged an extra `client disconnected before
response start` event. The focused native macOS follow-up with the pending
15-second client-probe timeout passed 1/1; hosted full-matrix validation remains
pending.

Windows x86-64 executed 682 cases: 678 passed, none had behavioral mismatches,
46 were not run, and four infrastructure failures occurred. The candidate had
shutdown timeouts in two worker cases. The Uvicorn oracle timed out waiting for
a worker in the explicit-worker case and hit `WinError 10053` in the HTTP/1
upload case. Focused Windows run #587 on the same head passed both selected
candidate worker cases; the oracle trace recorded no handler-entry event for one
worker after `CTRL_BREAK_EVENT`, and the supervisor timed out waiting for it.

Only Linux candidate package/consumer qualification passed. The three-repeat
unified coverage job remains active; no independent current-source
Coverage-MCP receipt or complete platform candidate qualification is available.
Keep the PR head unchanged until all active parity, coverage, and package
verification jobs reach terminal results. Then record their measured totals and
artifact identities, run an independent Coverage-MCP review on the exact clean
source, and carry the verified package artifacts and consumer receipts into
candidate assembly. Start the
matched three-system ordinary-FastAPI benchmark only after full parity passes.
Benchmarks use one Tokio thread and report system/workload details alongside
throughput, latency percentiles, CPU, and memory. The maintainer will perform
their real-application trial after repository acceptance.

The 0.3.0 changelog entry is included with maintainer authorization. No 0.3.0
package or tag has been published. The publication sequence remains clean local
Cargo publication of the lifecycle crate, then the server crate, followed by
the `release.yml` PyPI-only action. The latest registry audit found 0.2.1 as the
latest Cargo version and no PyPI `uvicorn-rs` release.

### Earlier PR validation — 2026-11-01 (CI #583)

At the time of this CI run, PR #19 was open and draft against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`, with pushed head
`e0eb4e4989509d0c8a0adac5de78c256f625b4b0`. CI run
[41272503277](https://github.com/appunni-m/uvicorn-rs/actions/runs/41272503277)
passed the installed-wheel public matrix 755/755 on Linux x86-64 and macOS
ARM64. Windows x86-64 ran 728 cases: 727 passed and one failed in
`http1.upload-remains-after-one-asgi-receive`, with zero infrastructure
failures. Rust quality, MSRV, and the pinned 17-input native FastAPI-RS
composition passed. The macOS ARM64 candidate artifact and consumer passed;
the Linux x86-64 candidate artifact job failed before compilation because the
Rust toolchain download timed out. The three-repeat unified coverage job is
still active.

The local release worktree contains four commits through `4dc186f6f` ahead of
the pushed PR head, plus documentation updates recording
the current parity, coverage, release, architecture, and composition evidence.
The functional changes include a deterministic handshake for the Windows
upload parity fixture, a refreshed standalone H3 consumer lock, and a CLI
evidence note. The selected upload case passed 1/1 locally on macOS; hosted
Windows validation is pending. Do not push while the coverage job is active
because a PR push cancels it. After it reaches a terminal state, push the batch
and run the exact updated source once. Coverage remains unaccepted until the
exact final source reaches 100% and receives its independent review.
Benchmarks remain behind complete compatibility and parity.

No 0.3.0 package or tag has been published. The release sequence remains
clean local Cargo publication of the lifecycle crate then the server crate,
followed by the `release.yml` PyPI-only action. The registry audit dated
2026-11-01 found 0.2.1 as the latest Cargo version and no PyPI `uvicorn-rs`
release.

### Earlier diagnosis — 2026-10-31 (CI #537)

[CI #537](https://github.com/appunni-m/uvicorn-rs/actions/runs/41175891140)
finished all 1,370 cases and three verification repeats without case or
infrastructure failures. Coverage is 14,239/14,270 regions and 10,505/10,523
lines; the remaining 31 regions and 18 lines are in the Python adapter. Its
canonical report SHA-256 is
`977b37d6f24af9045d5949acca38d28b153f652e3397c8969fe0192f88126a6a`,
bound to merge source `97acb84b93ad23ed0d4bf4d55f857a49fa46e6ba`.
This is diagnostic evidence for subsequent changes, not acceptance of them.

The follow-up fixes a startup-controller loss: dropping the acknowledgement
owner after readiness previously let the server continue without acceptance
being acknowledged. Rust now closes the listeners, completes lifespan cleanup,
and reports the startup error. The new successful-shutdown fault plus the
existing custom-loop startup case pass 2/2 in
`target/ci537/startup-ack-final/coverage-report.json` (SHA-256
`51a77fedf514ea2ee4cce6e0aaa5968a768a4f563b8d7fb712d0d23cff6448fc`).
The shutdown-error variant and the existing console/TLS case pass 2/2 in
`target/ci537/startup-ack-shutdown-error/coverage-report.json`. Adapter Clippy
passes with warnings denied. These selected receipts do not establish a full
coverage total or close the lifecycle task.

The maintainer requires compatibility, a demonstrated improvement, or the
applicable specification; documenting an exception is insufficient. At the
time of this diagnosis, custom Python HTTP/WebSocket protocol classes and
`ssl_context_factory` were unimplemented. The oversized-trailer probe was also
unresolved because the oracle response exceeded the probe client's decoder
limit. The focused follow-up below records the subsequent hook implementation
and raises that finite budget to establish live oracle parity for the
candidate's trailer-overflow fix. Those local results do not close the broader
compatibility inventory.

### Compatibility follow-up 2026-10-31

The extension hooks were implemented after the preceding diagnosis. Focused
live Uvicorn 0.54.0 parity passed all six affected custom HTTP/WebSocket
protocol and TLS factory cases on the current local source; the receipt is
`target/kata-progress/custom-hooks-2026-10-31/current-hook-parity.json` (SHA-256
`75467f1cc662df6c5555a2b1f161c135609cf5602be28a7f698ef75ef352c110`). This
does not close the full imports/API or platform compatibility inventories.

The current `http` 1.5.0 `HeaderMap` holds at most 24,576 distinct entries. The
native adapter now retains additional validated HTTP/1 and HTTP/2 response
fields in an ordered sidecar. Hyper's HTTP/1 encoder restores field order with a
linear index; Hyper's HTTP/2 date-header path checks for an existing value
before attempting an insertion into a full map.

On the dirty candidate source digest
`b24a0afdeaf86abdefd85a27f10685241dba1ad14d328fbff6dcf57604b3468a`, the
installed macOS ARM64 wheel
`target/kata-progress/http-capacity-h1-h2-datefix-20261031/wheels/uvicorn_rs-0.3.0-cp39-abi3-macosx_11_0_arm64.whl`
(SHA-256 `9f5cf2360113ee1d797d2f7bb9ad2df102205ac534ccdc2fb6774228220a5dac`)
passed all four selected HTTP/1 capacity rows against Uvicorn 0.54.0: 24,575,
24,576, and 32,769 fields, plus the installed-wheel overflow support case. The
rows are in
`target/kata-progress/http-capacity-h1-h2-datefix-20261031/parity.json`
(SHA-256 `32910cf2e1f9ec75f52e92a14a2b3c359883578865a8a64a8453e08482e205d7`);
the combined report also contains an HTTP/2 row whose required-observation
fixture was incomplete at that point, so its batch summary is 4/5 rather than
green.

The same installed wheel then passed the focused HTTP/2 response-header case
against Hypercorn 0.18.0. It delivers 24,576 fields with the expected count and
digest, completes the stream, and serves `/scope` on the same connection. The
current case receipt is
`target/kata-progress/http-capacity-h1-h2-datefix-20261031/http2-parity.json`
(SHA-256 `71ba3054d0b55453688f45996ea10078a751295e166092725cf0b404d3d960e7`).
The first H2 probe exposed a real `HeaderMap::entry(DATE)` capacity panic after
the response was formed; the retained diagnostic is
`target/kata-progress/http-capacity-h1-h2-20261031/http2-backtrace.json`
(SHA-256 `244f29161520a9969f80a5c3fd5facc491c8281d69883963da9b39af748063d1`).
The bounded presence-check/`try_append` fix is included in the passing wheel.
These are local dirty-source receipts; they do not replace the hosted protocol
matrix.

CI #546 on source `399b94e` recorded 750/751 installed-wheel parity cases; its
only mismatch was the old 24,576-trailer fixture, which included the response
header generator's `Content-Length` field as a trailer. The corrected fixture
now excludes that field, and the current selected batch passes the valid
24,576-trailer case plus the 24,577 and 32,769 overflow cases.

The response-trailer follow-up exercises 24,576, 24,577 and 32,769 distinct
trailers with the client's finite 2 MiB decoded header-list budget. It replaces
the obsolete target-only reset contract with live parity against the pinned
Hypercorn 0.18.0 HTTP/2 reference. The installed macOS ARM64 wheel
`target/trailer-overflow-wheels/uvicorn_rs-0.3.0-cp39-abi3-macosx_11_0_arm64.whl`
(SHA-256 `a78e0dae82eec99cad7b05983983017f65fbe0f86540eb549ba698587550ba4f`)
passes all three cases, matching trailer count and digest, stream completion,
both application send-return events, and healthy same-connection `/scope`
responses. The selected report is
`target/kata-progress/trailer-overflow-parity-20261031/parity.json` (SHA-256
`1ddc653d52b81725c1e9bc492de13295ac063397b1cb4f1e27e18afa3739db2f`); it
records 3/3 passed, no failures or infrastructure errors, and source digest
`40e2475961a2b6e04a5e31d9546cca0a37e893c0b4a32b456ee957ca2884ae36`. Local
formatting, all-feature Cargo check, and strict adapter Clippy pass. This run
used a dirty worktree, so it is focused development evidence; consume the
resulting exact-source hosted checks before it qualifies release.

The same compatibility follow-up fixes WebSocket accept-header overflow in the
Python ASGI adapter using the workspace-only patched-Hyper `HeaderOrder`
sidecar. Its raw-wire case sends 32,769 application fields, including repeated
`x-capacity-repeat` values at opposite ends of the sequence, and compares the
101 handshake, all application fields, cleanup events, and a healthy `/scope`
request with Uvicorn 0.54.0. The installed macOS ARM64 wheel
`target/kata-progress/ws-header-capacity-20261031/wheels/uvicorn_rs-0.3.0-cp39-abi3-macosx_11_0_arm64.whl`
(SHA-256 `fbc0f6c65cd7483a6e926230551aeab7f00d24cf3205fc1e15724fad629b281f`)
passes the selected case 1/1. Oracle and target report the same application
field digest `888c26f0d53fd3d783ebd0f6430234b3764417c4ddef6c42ad007d9b26a21219`.
The report is
`target/kata-progress/ws-header-capacity-20261031/parity.json` (SHA-256
`494517adfb248fdbb7eb3886533b38a19cc214d3e1a77cbfb33c73af40b9ea8f`), bound
to dirty source digest
`8e0d13358f332c88153c9f5dafb57ba47e05fd6326d34c64b6e450d9518fd796`. This
focused local receipt does not qualify the release source. PR #19 CI #547 ran
before this case was added. Its public runner completed 753/753 comparisons,
but the evidence checker rejected the declared
`python.api.server-lifespan-auto-fallback` / `uvicorn-rs-shutdown-trace`
normalization. The local checker now handles that exact pair; hosted verification
is pending. The unified coverage job remained in progress at last inspection.

The TLS floor has a standards-based proof in
`target/ci537/obsolete-tls-controlled/coverage-report.json` (SHA-256
`241768145fed4745e7ca57654e4ccd7e1111cc028a2585dd6a5401c4cc7a6381`):
two public cases pass against Uvicorn 0.54.0. Each sends a TLS 1.0 or 1.1
ClientHello on the wire, checks rejection, admits an otherwise identical
TLS 1.2 control, and completes a healthy HTTPS request. No extension was rebuilt
for these input/runner-only changes. RFC 8996 requires non-negotiation; it does
not mandate equal alert descriptions. The oracle's EOF and target's fatal
protocol-version alert remain visible in the receipt and are not compared.
The first diagnostic's unjustified required alert code failed and is retained
in `target/ci537/obsolete-tls/`; it is not accepted evidence. This establishes
the default listener's version floor, not custom TLS-factory compatibility.

[CI #539](https://github.com/appunni-m/uvicorn-rs/actions/runs/41183934112)
qualifies head `dae3c94bc51ea23f3be6358023a637edf2093ff5`. Its native
composition job found nested consumer locks omitted from the 0.3.0 bump.
The follow-up synchronizes all three consumer locks and the standalone H3
registry requirement. All three pinned dependency graphs resolve offline with
`--locked` and exclude PyO3; the refreshed native-Starlette example compiles.
Receipts are in `target/ci537/consumer-lock-verification.json` and
`consumer-starlette-build-current.log`. The version guard now checks these
inputs before full CI jobs start. Focused selected jobs stay independent.
No runtime suite was repeated for this metadata correction; let #539 finish
before advancing the PR again.

The Linux normal wheel in #539 passed all 738 public cases, then its exclusion
audit rejected a starred expansion in `FAULT_POINTS`: the audit deliberately
uses literal AST extraction rather than executing the runner. Follow-up
`0a8c86ff5` restores a literal registry retaining all 329 native selectors and
adds an early release-evidence regression check. A fresh normal macOS 0.3.0
wheel passes the repaired three-case binary/public audit, with every exclusion
check passing (`target/normal-audit-030-receipt/receipt.json`, SHA-256
`87ec21bb44177d866bffe890d31656249d5c5081489ff8b000e511cad5fb7c83`).
Both acknowledgement-owner-loss regressions also pass on that installed normal
wheel (`target/normal-audit-030-startup.json`, SHA-256
`3e0d42dd5dccc3ea2c148bbc159cb339c2b345933c9866365a6e88857f546a8d`).
These are selected normal-build receipts at `0a8c86ff5`; they do not turn
#539's failed job into an accepted full run.

### Earlier receipts — 2026-10-31 (full run #536 and focused follow-up)

At the time of this earlier report, PR #19 was draft/open against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. The h11 adapter/parser fix is committed at
`6342b20402bf0cceabd8eafde3f067e1620bafba`; its runtime-source SHA-256 is
`c00038a3885178b4bb1146fc315a51eb70c5e149a1742a16d3bdada8c7bee50f`. The
latest completed full hosted run is
[CI #536](https://github.com/appunni-m/uvicorn-rs/actions/runs/41151116481).
Its Rust quality, feature, MSRV, native-composition, release-evidence and Linux
artifact jobs passed. Coverage completed all 1,351 indexed cases and all three
verification repeats, but missed the gate at 14,137/14,251 regions and
10,410/10,463 lines. All 114 uncovered regions and 53 lines are in `src/lib.rs`.
The canonical report SHA-256 is
`336eadc77922d0f981039c1ec8ad18c35229bf2199811ea960ceb7e9e98eea32`;
its recorded merge ref is `15cf322f9f005b4823167620d0d17c570b992ff2`.
Documentation #217 passed separately.

Normal installed-wheel parity passed on Linux. macOS passed 728/729; the WSGI
multi-chunk case differed only by a conditional background-drain log during
immediate shutdown. Windows passed 698/702; four h11 cases had identical live
oracle/target wire behavior and exit code 3, but stored fixture expectations
required POSIX exit 0. Follow-up `bec2da6a2` removes those stored expectations,
retains every live comparison field, rejects shared process timeouts, and uses
the existing bounded post-response settling input for both multi-chunk WSGI
cases. All six affected cases pass against the rebuilt normal wheel on macOS.
Windows acceptance still needs a hosted receipt for the follow-up source.

The coverage-events follow-up also includes nine passing HTTP/2 response-event
fault cases, shared control borrows and header insertion error handling. The
next adapter batch consolidates lifespan task results, cancellation cleanup and
legacy cipher initialization; checks TLS boundary failures and provider fallback;
observes dropped startup waiters; and exercises cancellation after socket bind,
including a closed-port check after `serve()` returns. Focused receipts are
retained under `target/ci536/`: lifespan refactor 7/7, corrected cipher selection
6/6, cancellation/upload 9/9, and bound-port cleanup 2/2. The initial TLS batch
retains its three unconsumed-fault failures; only the corrected input batch is
passing evidence. These are diagnostic subsets, not a new full coverage total.
Strict Clippy and formatting pass for the batch. Promote one reviewed batch and
consume its full hosted report before making any full-matrix acceptance claim.

That batch was promoted at `9b0309406704e1d03c5f3e99a416f2b634d5f749`.
[CI #537](https://github.com/appunni-m/uvicorn-rs/actions/runs/41175891140)
completed its full coverage and Linux installed-wheel matrix; separate
[Documentation #218](https://github.com/appunni-m/uvicorn-rs/actions/runs/41175891137)
passed. Its Cargo 1.85 job rejected the newly expanded multiline inline
dependency table before compiling. Follow-up `c4d148a58` restores compatible
TOML syntax and passes the four required Rust 1.85 checks locally. The hosted
platform-artifact jobs depend on MSRV, so this run cannot supply new macOS or
Windows acceptance receipts.

The next focused follow-up shares the atomic startup transition, TCP listener
inspection, and fallible TLS protocol builder without removing their failure
handling. Existing startup/TLS boundary cases pass 10/10, including cancelled,
failed, and successful readiness. Bound/inherited TCP inspection and the native
HTTP/3 default-header failure pass 6/6. These receipts are retained in
`target/ci536/transitions/` and `target/ci536/listener-headers/`; the new header
case brings the ASGI inventory to 1,112 cases. Strict Clippy and formatting pass.
That follow-up predates the completed full report above; no benchmark has started.

The next batch fixes a confirmed Content-Length completion mismatch: after the
wire body was complete, the adapter incorrectly rejected a valid empty ASGI
body event when the client closed. It now drains those events through the
application's terminal send. A live input retains all three completed send
observations. A second live input verifies returning without required HTTP/2
trailers. Their focused checks, including the WSGI final-body neighbor, pass
3/3 in `target/ci536/body-completion-fixed/`.

The adapter also preserves parser-specific CONNECT admission: httptools rejects
an authority-form URL with HTTP 400 before the concurrency check, whereas h11
accepts it and can return HTTP 503. This is a Rust request-target policy; the
Python integration only selects the configured parser's policy. The standalone
Rust default continues to accept authority-form targets. A seven-case batch
covering both parser selections, HTTP/1.0 admission, observer failure,
Content-Length completion, missing HTTP/2 trailers and WebSocket close-send
failure passes 7/7 in `target/ci536/authority-policy-fixed/`. The separate native
configuration/debug contract passes 1/1 in `target/ci536/authority-native-config/`.
The inventory now contains 1,119 ASGI cases. The first CONNECT probe's 400/503
mismatch and the initial unarmed WebSocket fault attempt remain failed
diagnostics; their corrected inputs are the passing receipts.

CI #537's Linux normal wheel passed all 731 live parity cases, then failed the
strict evidence check on duplicate `serve_raised` and `serve_timed_out` JSON
fields. The duplicate metadata is removed, and manifest/input loading now
rejects duplicate fields before building or executing cases. This fixes the
evidence failure; it does not turn that hosted job into a passing receipt.
Rust 1.85 all-feature compilation and the CI's applicable strict Clippy modes
pass locally for this follow-up. A broader Clippy invocation without the
required coverage cfg failed on the existing coverage-only contract example
and vendored H3 test lints; it is not a supported CI check or passing evidence.

The WebSocket timer now uses an optional sleep guarded by the presence of a
deadline, instead of an async branch that waits forever when keepalive is
disabled. Existing timed-out, timeout-disabled, infinite-interval and
keepalive-disabled inputs pass 4/4 in `target/ci536/optional-keepalive/`.

A clean normal macOS ARM64 abi3 wheel from `52c9e74a8d604d8489a71db387077cbcbb5ae753`
passes installed-package HTTP/lifespan/context/cancellation and CLI/TLS/shutdown
checks, plus all nine affected public parity inputs (9/9, zero failed,
infrastructure-failed or not-run). Receipts are in `target/normal-52c9e74a8/`.
Wheel SHA-256: `26261cd60703aa911a3598dcd99a945262a88840fa06783ba5c437bca4700192`;
consumer report: `9f8782c926bca881fbb35ff18ff22e14286b095b786e7b2f0de9a7a8aeda2763`;
parity report: `ff09f9f6eee7e1e8b9ccb8b76265b18bfba1016e40b39fda577e58d943debcc0`.
This is selected normal-build evidence, not a complete platform or release
candidate receipt. The existing native concurrency-observer contract now
also disables HTTP/1 authority-form admission during its HTTP/2 control,
verifying the HTTP/1-only policy does not change the H2 response. That selected
case passes 1/1 in `target/ci536/h2-admission-policy/`.

Focused Windows [CI #538](https://github.com/appunni-m/uvicorn-rs/actions/runs/41180292641)
passed twelve affected public cases at `6f0cbda07`; all other CI jobs were
skipped in that mode. It did not repeat #537's full coverage run.
The documentation refresh removes stale current-status
claims and corrects the CLI map: the pinned Uvicorn 0.54.0 command does declare
`--http2`. README documentation links are absolute so the PyPI description can
resolve them. The strict MkDocs build and structural documentation audit pass;
the audit's only review item is unlabeled fences in vendored H2 contributor docs.

The Linux installed-wheel public parity in #531 passed 719/719. Windows ran
692 cases: 689 passed and three two-worker shutdown cases failed. Their only
input changes since that run add a one-second startup settle. Focused Windows
[#534](https://github.com/appunni-m/uvicorn-rs/actions/runs/41145100547) and
Linux [#535](https://github.com/appunni-m/uvicorn-rs/actions/runs/41145558362)
each pass the three current worker inputs 3/3 with zero infrastructure
failures. The full local macOS ARM64 / CPython 3.12.13 installed-wheel run on
exact head `ed60fef` passed 719/719, zero failed/infra/not-run; receipt
`4f0fd48142f34ddd931639928a6daf4d`, report SHA-256
`17215002f939d255069c6fef20f0c1cd43ca1d17e981e2c29d2e6edbb6a07780`. This
case-level union does not replace one full exact-current-input hosted Linux
and Windows matrix.

The #531 three-repeat coverage job has completed, attributing 1,341/1,341
indexed cases, but fails both 100% gates: 14,137/14,252 regions and
10,411/10,465 lines. Artifact `13022180254` has archive SHA-256
`95e4eed1095c0068fcd4423ff2c122e3ae1bd35aabfe05ff7d81cd4af03cf5da`; the
report binds to source SHA-256
`9acb1ef935d10af060a0e41a39d33d4b4484cb75c079c2ee33d277a4eceed6ed` and
native extension SHA-256
`7203618868604435f0db762af850704452bd722c8c2fce54f14ad50e481e40db`. It
ran against the earlier merge ref, so it is diagnostic rather than an exact
receipt for the current input set. Independent Coverage-MCP review remains
open; no large archive has been downloaded again.

Other #531 jobs: Linux 0.2.2 candidate artifact and clean consumers passed;
Windows candidate verification failed after the worker parity failure, and
macOS candidate verification was cancelled. Rust formatting/lints, feature
builds, Rust docs/no-Python checks, MSRV, release-evidence contracts, and
native FastAPI-RS composition passed. The separate docs deployment run #215
passed for earlier docs; current edits need a new deployment receipt.

The CLI/settings surface now has a 52-parameter map and 118-case argv/environment
index at [`uvicorn-cli-option-map.md`](uvicorn-cli-option-map.md). Six new live
module-CLI WebSocket cases passed locally 6/6 on the preceding runtime. Four new
h11 boundary cases exposed early rejection and HTTP 431 instead of 400. The
adapter/parser fix now passes those four plus the expanded-header case 5/5,
including a 1 KiB limit. Receipt `4e60b47b7f194528b326a9619456db01`, report SHA-256
`3850085052d81114891c617ea7fdf101b4cd2734dc8de49412c8bf6c46de6f06`. These are local
dirty-draft subset receipts. `9kbx` and `x3az` remain open for complete hosted
acceptance of the committed source and current inputs.

The publisher entries, main/tag rulesets, and release environments are
configured. The maintainer confirms both crates.io Trusted Publisher entries
are already present, and the PyPI `uvicorn-rs` pending publisher for
`release.yml` / environment `pypi` is saved. A 2026-10-30 registry check lists
Cargo 0.2.1 for both release crates and no PyPI `uvicorn-rs` project. No 0.2.2
candidate, tag, or package is accepted for publication. The older Linux ARM64
HTTP/3 benchmark remains incomplete; the user's parity-first direction keeps
all new benchmarks blocked until compatibility passes.

The local H2 parity runner captures the event baseline before request
submission and waits up to two seconds for case-required app events before its
final snapshot. This runner change has no server behavior effect.

### Prior platform receipts — 2026-10-30 13:28 UTC

Full-mode CI [#506](https://github.com/appunni-m/uvicorn-rs/actions/runs/41045789961)
completed from branch commit `5a3866e125afdc454c7f61ad94a45669d2e59d82`,
against `main` at `86e72e181d00feca1b4db7f30377d5d9d4345b83`. Its
installed-wheel parity passed 718/718 on Linux x86-64 and 718/718 on macOS
ARM64. Linux and macOS candidate artifacts and clean consumers passed. Windows
x86-64 executed 691 cases: 689 passed and two failed:
`python-api.module-cli-two-workers-serve-request` and
`http1.upload-remains-unread-after-early-response`. Its candidate consumer
steps were skipped after the parity failure. The unified three-repeat coverage
job completed at 14,032/14,203 regions and 10,343/10,428 lines, below both
100% gates; the report and its source-bound artifact are retained locally.

Focused coverage batch on 2026-10-30 added a coverage-only response-finalization
fault selector and two HTTP/1 fault-contract cases for invalid configured
default-header names and values. Both selected cases passed with complete case
attribution and observed a closed connection; each per-case profile covered
all eight regions of `invalid_default_header_error`. The selected report is
`target/completion/coverage-default-header-finalization.json`, SHA-256
`bfeb37ad737ab2f16043b26243321e610b50c902a89aef95bc9fb166184b639e`; its
source digest is `ff885bc0a79cad1f710e8a2f57cbb63b1e70687759c0a3da4094e8369e3ce208`.
It was built from a dirty working tree and is diagnostic subset evidence only. The
retained full report projection still lists those eight regions as missing.
The full coverage gate and independent review remain open.

The next focused coverage batch adds six HTTP/2 response-event fault cases in
`AsgiIo::send`: early-hint disconnect/channel closure and trailer
disconnect/channel closure/channel backpressure/full-send closure. All six
fault cases passed with complete attribution and consumed selectors. The
existing successful early-hints and negotiated-trailers cases passed 2/2 on
the same instrumented source. Fault report SHA-256 is
`7195d53c48890deaf796ebc15e69f7b4a810bf59df7c240c797b09ecca117436`; success
report SHA-256 is
`5f3f8cc9a6f027b4e80eb13be50b1e0b96915ff2f9f855d9f59546952d912fa1`. Both
bind to source digest
`95fc7f8fa9c39625d59d189aa4cf622096388505a907c6cc098963639e9b6f1d` and native
extension SHA-256
`e2ba67fd41950c85637b42821da2f9a30d87a983d83e049aaea821544eca13ad`. These
selected reports document the changed paths only. They do not replace the full
three-repeat coverage gate or independent Coverage-MCP review.

The worker case's Uvicorn oracle returned HTTP 200 but did not exit within its
12-second shutdown bound: the captured log ends while the parent waits for a
child. The candidate exited with code 0. The early-upload case recorded no
response status or body from the oracle; the candidate returned HTTP 200 with
`upload-ignored`. Neither failure's cause is confirmed. Focused run #507 passed
both inputs, but that alone does not establish a full Windows pass.

Focused Windows run
[#507](https://github.com/appunni-m/uvicorn-rs/actions/runs/41050476209),
from branch commit `dc720811219e24a04f79c87774c9b9878d3e5528`, selected those
two cases and passed 2/2 with no failures, infrastructure failures, or not-run
cases. Its commits and native-extension hash differ from #506, so it did not
replace the failed full Windows lane.

The early-upload failure was traced to the parity harness writing the remaining
request body after the response while Windows can report
`ConnectionAbortedError`. Commit `f3b54549a3243523c475551cbcf83e241f2b93b4`
now treats that error like the existing broken-pipe/reset outcomes for this
deliberate post-response write. Focused Windows run
[#510](https://github.com/appunni-m/uvicorn-rs/actions/runs/41056892023) on
that commit selected only `http1.upload-remains-unread-after-early-response`
and passed 1/1, with zero failures, infrastructure failures, or not-run cases.
Its report and native-extension hashes are retained in
`target/completion/focused-windows-510.zip` and the extracted local completion
directory.

Focused Windows run
[#511](https://github.com/appunni-m/uvicorn-rs/actions/runs/41057465056)
selected only `python-api.module-cli-two-workers-serve-request` on the same
commit and passed 1/1, with zero failures, infrastructure failures, or not-run
cases. On Windows Server 2022 AMD64 / CPython 3.12.13, both Uvicorn 0.54.0 and
the installed candidate served HTTP 200 with matching bodies and exited 0
without timeout. The clean target revision is `f3b54549a3243523c475551cbcf83e241f2b93b4`;
manifest SHA-256 is `ad378727082f70c19ca003d64f0e2c4ddb6083a584853cb229499d228c72e348`,
Python API input SHA-256 is `a2b21acd01a3fdff2af61a55182c3b725a51c59bed639d8588b7b61b4778a27c`,
runner SHA-256 is `34aceefefacb4a196c6917b43dd5dbcbe2adf2fa11647b436a7d2ed6231dc9af`,
and native extension SHA-256 is
`621524090a99a8aa8f1a22b7a443cfbb4f93e362929327fa97d23340a314a4ca`. Artifact
12976754359 has SHA-256
`ef0712618965f4fe6bb9c744d7d28bed54d16acfcc03ed4aa5e822db5cfd9e77`; the
parity report SHA-256 is
`d2bea7f2836456438b314a9fe128f82d7c4d0bfa608e9f864993d9ba065c8ceb`.

Focused Linux run
[#512](https://github.com/appunni-m/uvicorn-rs/actions/runs/41058428280)
selected only `http1.upload-remains-unread-after-early-response` on the same
commit and passed 1/1 on Linux x86-64 / CPython 3.12.13. Artifact 12978226870
has SHA-256
`dd8f71974d78c507a198731d35e18745e223512fa2bbdbd54cd018fb3bfac16b`; report
SHA-256 is
`29a624de9fa145629736ce4a5d487c83bde7236b0b97c775053e3ad3964d58d0`. The
installed wheel consumer smoke also passed. The selected case has current
HTTP/1 input SHA-256
`9199b7421b01f767bc0208e212b7586a7168df0124246fdc267d84d54d1cfe5b` and
native-extension SHA-256
`700979d131e71a2c74ae044a2fcded061b71ac29c1678e96d19fa32530b52170`.

The same changed upload input passed 1/1 on a clean local macOS 15.7.7 ARM64 /
CPython 3.12.13 checkout at `f3b54549a3243523c475551cbcf83e241f2b93b4`.
The local report is `target/completion/mac-upload-current-clean.json`,
SHA-256 `557f58828a78a43df8a406d05a103a932ccb1b1b80cdbc671fed9474e12c29a7`;
its runtime source SHA-256, manifest, input and runner hashes match #512. It
has zero failures, infrastructure failures, or not-run cases.

`4fvf`'s all-platform installed-wheel matrix is now complete as a case-level
composition. Full #506 ran 718/718 on Linux x86-64, 718/718 on macOS ARM64,
and 689/691 on Windows x86-64. All three full reports have the same 211
runtime-source file hashes and source SHA-256 `c5b9c9bcce020d9d674b9af59393ae705d9c6d471ec07f5f4ce3510522f54a4d`
as the current f3 receipts, with the same manifest. The only normal-matrix
input changed since #506 was the early-upload case; it has current-source
passing replacements on all three platforms. The only parity-runner change
adds `ConnectionAbortedError` handling to that case's deliberate post-response
write. The two #506 Windows failures are replaced by #510's upload pass and
#511's worker pass. The resulting matrix is 718/718 Linux, 718/718 macOS, and
691/691 Windows, with no failed, infrastructure-failed, or not-run cases. This
is a receipt composition, not a claim that one workflow ran all three full
matrices at the f3 commit. The automatic pull-request run #509 was canceled
after focused checks began and is not evidence.

No benchmark has started, following the maintainer's parity-first direction. PR
#19 remains a draft against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`; exact-main checks, complete Windows
consumer qualification, independent coverage review, complete Uvicorn
compatibility, and benchmark evidence remain outstanding. Current branch head
before this focused local batch is
`f3b54549a3243523c475551cbcf83e241f2b93b4`; since #506, changes include the
parity runner's Windows exception classification, its indexed HTTP/1 input,
the release workflow/version guard, documentation, and the current
coverage-only default-header finalization selector with two fault-contract
inputs. The selected coverage report is dirty and does not qualify as the
clean full-source gate. The local strict MkDocs build passed for the prior
plan update on Python 3.12.13 with the hash-locked `requirements-docs.txt`
dependencies.

1. The previous full-mode CI run was
   [#497](https://github.com/appunni-m/uvicorn-rs/actions/runs/41031606350),
   on branch revision `255ec35af35d44c78423d35c4cb9ee539c7a4ab5` against
   `main` at `86e72e181d00feca1b4db7f30377d5d9d4345b83`. Rust quality, MSRV,
   native FastAPI-RS composition, and release-evidence checks passed. Linux
   installed-wheel parity selected 718 cases: 715 passed, no behavior
   mismatches were reported, one infrastructure case failed, and two later TLS
   cases were not run. The failing active-response stream case raised Broken
   pipe; its target log shows the ASGI send failed with “client disconnected
   before response body.” The graceful-timeout message in the same profile is
   from the immediately preceding TLS cancellation case, which passed. The
   failed active-stream run has no shutdown trace, so its ordering and cause
   remain unknown. macOS/Windows candidate parity and the Python-floor job were
   skipped after Linux parity failed. Three-repeat coverage completed at
   14,032/14,203 regions and 10,343/10,428 lines, below the 100% gate.

   Focused Linux run #499 passed the active-stream case once without retaining
   a trace. Exact-source focused CI
   [#500](https://github.com/appunni-m/uvicorn-rs/actions/runs/41036703998), on
   branch revision `3ff0999665f8face9dbb8bf03984b734e4293d22`, passed the
   active-stream, reset-during-shutdown, and unfinished-handshake cases 3/3
   with zero failures, infrastructure errors, or not-run cases. Artifact
   12967259667 retains shutdown traces. The successful trace shows shutdown
   wakeup, listener drain completion, and lifespan shutdown completion; it
   does not reproduce or explain the full-run failure. Focused Linux #501
   selected the preceding held-request cancellation and active-stream TLS
   cases; the first passed and the second reproduced the ASGI send failure. Its
   trace shows a readiness probe accepted after SIGTERM and then canceled. The
   one-second graceful-timeout line belongs to the preceding cancellation case,
   so the active-stream cause remains unresolved. Focused Linux #502 on
   `ee236c8bdfc0b2f270853a40a6ff3c4feb20db43` passed the same two cases 2/2 and
   confirmed the expected one-second and three-second Rust timeouts; the active
   connection completed and drained. This pass does not explain #501. The current branch has no
   full-source platform matrix yet. Do not start benchmarks until complete
   compatibility parity passes. Coverage and independent review remain
   mandatory release gates.
2. Audit the fixed compatibility inventory and architecture against current
   source. List each concrete missing or mismatched contract item with its owner,
   existing case or new input needed, and observable acceptance. Descriptions
   such as "broader behavior unverified" are not actionable work items.
3. Fix related failures and coverage gaps in batches. Run selected affected
   cases locally. Push one reviewed batch, then consume its hosted full run.
4. Close compatibility once its behavioral and platform evidence passes.
   Benchmarks then run on a frozen normal build, using one Tokio worker thread.
   Coverage and independent review remain mandatory release gates.
5. Merge after the PR correctness/parity/quality gates pass. Obtain the required
   exact-main CI, independent review, benchmarks, and package-consumer receipts.
   PR evidence is not silently relabeled as main evidence.
6. Assemble the complete bundle, qualify controls and bytes, then perform the
   already-requested Cargo/PyPI release and verify the registries.

The repaired dependency chain is:

```text
9kbx + gjpr + dv25 + dhfq + 4fvf -> x3az -> wh9k -> zep3 -> v5fe -> m8mx
sw8s -> wb4y -------------------------------------> zep3
b8k7 -> 7t4g -------------------------------------> zep3
nbmg + jpf3 + v7a1 are benchmark children of wh9k
ec8x closes after its required children and linked native acceptance complete
```

`v5fe` belongs under `m8mx`, not under `x3az`: release qualification cannot be a
prerequisite for the compatibility gate that permits benchmarks to start.
Publication still waits for all gates. Candidate artifacts may be built and
inspected before publication; creating a build is not release acceptance.

Keep at most three implementation areas active: compatibility/architecture,
coverage, and review-tool recovery. A fresh full report is justified by a changed
source/input/build or an identified execution failure. A finished unchanged
passing slice is reused while its full identity remains applicable.

For an infrastructure failure, inspect the failed process or job and fix the
identified cause. An observation timeout is not permission to restart a live job.
For an unreproduced failure, retain a bounded diagnostic outcome and the missing
evidence; do not close a root-cause task as fixed. Do not lower coverage, increase
the upload timeout, discard failed benchmark samples, or relabel unsupported
behavior to obtain completion.

## 9kbx — CLI, settings, and diagnostics

**Work:** Audit all 52 declared upstream Click parameters, their environment
bindings, aliases, defaults, validation, and precedence against the pinned
contract. The complete declaration and case map is
[`uvicorn-cli-option-map.md`](uvicorn-cli-option-map.md). It indexes all 118
`cli.json` process inputs and links the live `module-cli` cases. The six new
WebSocket cases passed their selected local group; the four new h11 boundary
cases exposed a runtime mismatch that is now fixed and passes the five-case
h11 group. Consume one full hosted matrix for this reviewed batch. Resolve
any inventory mismatch or ignored option found in that review; do not repeat
unchanged passing groups.

**Close with:** A complete parameter-to-case mapping; all mapped cases pass on
their applicable CI platforms with argv, output, and exit status retained.
Platform-inapplicable settings are justified by the upstream contract. Release
artifacts and benchmarks do not block this task's closure.

## gjpr — Imports and programmatic API

**Work:** Map the documented imports, signatures, `run`, `Config`, `Server`,
app loading/factories, ASGI2/ASGI3/WSGI, middleware, logging, and workers to the
existing `python-api` inputs. Check actual serving, lifecycle, context and error
behavior for each entry point. Turn every remaining contract gap into a named
case rather than adding unrelated combinations.

**Close with:** No missing public-inventory row or signature mismatch, and all
applicable installed-wheel Python API cases pass on the declared CI profiles.
Keep unsupported Python-version claims out of the user documentation.

## dv25 — Protocol and lifecycle compatibility

**Work:** The HTTP/2 response-header ordering mismatch is fixed in the vendored
`h2` encoder and already has a strict `http2.response-headers-preserve-asgi-order`
input plus a focused local oracle receipt. Verify that input in the current
hosted source run and retain the HTTP/1 ordering receipts. HTTP/3's client
observation passes through `http::HeaderMap` and cannot establish raw wire
field order; preserve that limitation in the support docs. One uncompressed
and one per-message-deflate compressed fragmented WebSocket text input are now
in the matrix; both pass as selected local oracle comparisons. Continue with
other extension parameters and queue behavior only where the pinned upstream
contract requires it. Audit
existing streaming, flow-control, TLS, proxy, disconnect, cancellation,
lifespan, limit and shutdown cases before adding inputs. Keep HTTP/3 extensions
distinct from behavior actually provided by Uvicorn 0.54.0.

**Close with:** Each required protocol/lifecycle contract row has a passing live
case and no known mismatch remains in the promised surface. Native request-end
reasons are asserted only where the driver can prove them. A documented known
mismatch still blocks a full drop-in claim.

## dhfq — Workers, reload, listeners, and process control

**Work:** Finish the finite contract table for TCP/IPv6/UDS/fd/pre-bound sockets,
multiple workers, crash and health-check replacement, reload include/exclude,
request limits, graceful shutdown and supported signals. Reuse the existing
POSIX signal/reload cases. Add or fix Windows-applicable inputs and preserve
upstream platform restrictions. Observe child replacement, served responses,
exit codes, listener ownership and process cleanup.

**Close with:** All required controls have passing applicable platform evidence,
no orphan process/listener remains, and the one-Tokio-thread model is documented.
An option-name match alone does not qualify operational behavior.

## 4fvf — Parity inventory, execution, and platform evidence

**Work:** Reconcile the pinned contract with the existing manifest and indexed
inputs. For every mandatory surface, record its case IDs and owning task; assign
each concrete gap to 9kbx, gjpr, dv25 or dhfq. Retain input-only cases, real
upstream execution, generic comparisons, first differences and strict source
identity. Run macOS/Windows package and parity jobs alongside unified coverage;
they produce independent platform evidence and do not need the coverage report.
The overall CI/candidate gate still fails closed unless coverage also passes.
Consume existing valid platform receipts and run only missing or invalid lanes.
Diagnose why a platform lane did not execute rather than treating its absence
as a behavioral failure.

**Close with:** A complete inventory mapping and green installed normal-wheel
matrix on all applicable CI platforms, with zero failed/infrastructure/not-run
cases. The Python floor consumer is reported separately from versioned parity.
Coverage attribution and fault cases do not substitute for this normal lane.

## x3az — Compatibility acceptance and user documentation

**Work:** Audit the five compatibility children above against the pinned public
contract. Reconcile `docs/support-matrix.md`, the contract reference, install,
replacement, deployment and rollback instructions with the accepted receipts.
Make the public tested OS/Python surface explicit. Keep release engineering and
historical measurements out of the basic application-running instructions.

**Close with:** All five required compatibility children close, the current
support claims match their exact evidence, and the installation/rollback path
works on the declared profiles. This task proves compatibility; publication,
benchmark completion and candidate acceptance are downstream in v5fe/m8mx.

## sw8s — Canonical transport and thin ASGI boundary

**Work:** Audit root `src/lib.rs` against the native crate for each listener,
HTTP/1, HTTP/2, HTTP/3, TLS/QUIC and WebSocket driver. Retire redundant legacy
drivers or document an explicitly required path with its own live evidence.
Rust owns transport, body flow control, connection/session lifetime and draining.
The adapter owns Python scheduling, context, callable/error transfer and ASGI
event conversion. Check shared WebSocket upgrade/session and shutdown paths.

**Current production ownership map (source review):**

| Responsibility | Current owner | Boundary |
| --- | --- | --- |
| TCP/TLS/UDS accept loops, TLS handshake, HTTP/1 and HTTP/2 connection handling, response body flow, connection drain | `crates/uvicorn-rs/src/lib.rs` | The PyO3 crate binds configured TCP/UDS sockets and builds the TLS acceptor; its `Service<Request<Incoming>>` converts requests to ASGI calls. The native crate owns the accept loop, TLS handshake and Hyper connection after the bound listener/acceptor are passed in. |
| QUIC endpoint, HTTP/3 connection and request streams | `crates/uvicorn-rs/src/http3.rs` and `crates/uvicorn-rs/src/http3/` | `http3` gates the QUIC dependency and server implementation. The PyO3 crate passes a native endpoint and an ASGI service to `uvicorn_rs::serve_http3`. |
| WebSocket frame parsing, upgrade I/O, session lifetime and close/drain | `crates/uvicorn-rs/src/websocket.rs` | The adapter translates between native WebSocket messages and ASGI events; it does not parse or serialize frames. |
| Python imports/API, event-loop scheduling, context propagation, ASGI scope/events, lifespan and Python error transfer | root `src/lib.rs` | This is the language boundary. It also resolves Python-facing settings and constructs the native services. |
| Older HTTP/1/HTTP/2 driver and the older HTTP/3 service | root `src/lib.rs` | `build.rs` sets `uvicorn_rs_native_transport` for normal builds, so the HTTP/1/HTTP/2 fallback is excluded. The older HTTP/3 service is retained only for coverage fault contracts and is selected only by the coverage harness. It is not a normal runtime alternative. |

This is a source ownership map, not closure evidence. The current hosted run's
native composition job checks the Python-free dependency graph, while the full
ASGI/native lifecycle matrix remains the required behavioral evidence. If the
coverage-only HTTP/3 path is removed, move its fault-contract coverage to the
native driver in the same reviewed change.

**Close with:** A file/API ownership map with no unintended duplicate transport,
passing affected ASGI/native lifecycle cases, and no Python/PyO3 dependency in
the native server graph. Preserve the original streaming, cancellation and
disconnect behavior; moving names or shrinking files is not acceptance.

## wb4y — Native framework composition acceptance

**Work:** Finish sw8s; audit the pinned FastAPI-RS and Starlette-RS dependency
graph and the existing `examples/native-fastapi-contracts` inputs. Verify the
sole FastAPI implementation composes through Starlette-RS and Uvicorn-RS using
Rust values. Exercise every protocol/lifecycle behavior claimed for this native
path through existing native inputs or add a named missing integration input.
Keep framework-owned Python bindings in their respective repositories.

**Close with:** Clean pinned source and lockfile identities, a Python-free
normal/build graph, passing claimed native integration inputs, and accurate
support limits. The existing 17-input composition pass is reused for its actual
scope; it does not prove missing TLS/H3/lifecycle cases. Comparative Python
FastAPI timing remains in wh9k, not a new native-framework benchmark project.

## b8k7 — Complete region and line coverage

**Work:** Use the latest completed exact-source unified report. Export its
uncovered file/function/spans into a worklist; associate each gap with an
existing reachable public input or deterministic target-only fault contract.
Batch adjacent gaps by function. For each batch, show its selected case pass
and attributable new hits before proceeding. Investigate an apparent mapping
gap against the raw LLVM profile/source identity before adding another case.

**Close with:** One clean source/build report has 100% executable regions and
lines, complete per-case attribution and three complete passing repeats with no
case, infrastructure, retry or unrun failure. Record integer totals and hashes.
Independent acceptance of that report is tracked by 7t4g; neither gate is waived.

## 7t4g — Coverage-MCP review of the final exact-source report

**Work:** After the final-source unified coverage job passes, use the existing
canonical-report projection (`scripts/project_coverage_mcp.py`) and handoff
tooling rather than repeatedly importing the large raw report. Query Coverage-
MCP 0.16.0 for every unfiltered region and line page. Preserve the shared
database and unchanged raw CI artifact. Retain the complete MCP transcript,
source/build identity, passing test status, and accepted receipt; attach and
strict-check the handoff artifact for the exact final-source run and attempt.

**Close with:** Complete zero-gap independent page chains with matching
source/build identity and passing tests, successful attachment/offline
verification, and one digest-checked handoff artifact selected and revalidated
by candidate qualification. A timeout, pending status, raw LLVM summary, or
synthetic receipt cannot satisfy this task.

## nbmg — HTTP/1 upload timeout root cause

**Work:** After compatibility passes, select only Linux ARM64
`fastapi-upload-1m-write-1k` at the recorded 1 MiB/1 KiB/concurrency-8 settings.
Retain client callback/upload counts, server read/queue/cancellation events and
monotonic timestamps. Trace the first stalled boundary, not the later
ClientDisconnect. Keep the 15-second client timeout. Limit the first diagnostic
batch to three attempts; if it does not reproduce, record that and the missing
evidence instead of launching an unrelated matrix.

The focused stage workflow uses one selected candidate/reference loop pair and
one planned repeat by default; it allows up to ten diagnostic repeats. For the
historical failure, select `focused-fastapi-stage`, `linux-aarch64`, `uvloop`,
and `fastapi-upload-1m-write-1k` only after the preceding acceptance gates. The
workload overrides concurrency to eight. Its `runtime-diagnostics` build and
`UVICORN_RS_UPLOAD_TRACE=1` opt-in
record client PID/worker/attempt IDs in a diagnostic request header. The same
IDs join libcurl callback counts and first/last callback timestamps, Rust body
frame/queue/cancellation events, and the ASGI receive/send/cancellation timeline.
Client callback size does not imply TCP packet or socket-write boundaries.

Rust retains the last 128 events independently for each traced request, plus
cumulative read/offered/delivered byte counts and explicit dropped-event counts.
The ASGI wrapper retains the slowest 32 requests per path and the last 128
events in each. Monotonic offsets have wall-clock calibration and recorded
calibration uncertainty; do not assert cross-process ordering finer than those
bounds. The recorded uncertainty is the clock-sampling window, not a guarantee
of nanosecond wall-clock accuracy; clock resolution and wall-clock adjustments
also matter. Prefer within-process monotonic order and request-ID correlation
when identifying a stall. Rust events describe framed body reads, not raw
socket reads. A killed process can lack terminal traces, which remains missing
evidence. Failed warmup and measured client JSON is retained in
`partial_client_metrics`, including the first failure's correlation ID. These
instrumented samples are diagnostic only; the normal three-system benchmark
still compares both asyncio and uvloop without this opt-in.

**Close with:** A supported root cause and corrected behavior, plus a focused
public regression when the defect is in the server, and passing exact-source
workload execution. A client/load defect needs equivalent evidence and a
corrected matched workload. An unreproduced outcome remains pending review;
it is not a claimed fix or a qualified performance result.

## jpf3 — Matched stock-FastAPI H2/H3 workloads

**Work:** Reconcile the existing H2/H3 workload lists with validated route,
Python CPU, upload, large response, chunked response and slow-reader behavior.
Use the same ordinary FastAPI/Starlette/Pydantic app and protocol-appropriate
Hypercorn baseline. Confirm real negotiation, identical request bytes and load,
and response/body/lifecycle correctness before timing. Preserve failed reference
cells, including the historical ARM64 slow-reader failure, as invalid evidence.

**Close with:** Every declared system/workload has a complete matched correctness
result and the original required metrics/identities. Plan five repeats; require
at least three valid matching pairs for any published descriptive comparison.
An unsupported reference cell is explicitly unrankable, not a measured win;
the whole matrix cannot be called complete while a required cell is absent.

## v7a1 — Decide whether to retain peer-read recycling

**Work:** Preserve the existing experiment refs and select one bounded ownership
implementation. Compare the same clean source with recycling enabled/disabled;
keep the copy into `ReadBuf` explicit. Reuse affected TCP/Unix upload, partial
read, EOF/error, reset, cancellation and resource-bound parity cases. Measure
the existing upload workloads with a small-response guard, one Tokio worker,
and paired normal builds. Retain allocation evidence when it can be measured
reliably; do not infer allocations from throughput.

**Close with:** Either a repeatable improvement in a named metric beyond matched
control variation without material regression, or rejection/removal of the
optimization with retained evidence. Three pairs are descriptive, not proof of
statistical significance. Do not keep tuning an unqualified optimization or
delete its preservation refs. Final integrated coverage/review remain release
requirements even after the experiment's decision is recorded.

## wh9k — Complete the performance evidence and decision

**Work:** Once x3az passes, freeze the exact normal server/client build and run
the maintained FastAPI-only category matrix on Linux x86-64, Linux ARM64 and
macOS ARM64. Use Uvicorn for H1/WebSocket/lifecycle and Hypercorn for H2/H3;
match Python, app, loop, request bytes, load and settings within every pair.
Use one Tokio worker, five planned repeats and at least three valid matched
pairs. Resolve the required children before accepting the aggregate.

**Close with:** A complete source-bound matrix reporting throughput, p50/p95/p99,
server/client CPU, CPU per request, RSS, available thread attribution and every
rejected sample, plus a workload-specific gain/regression decision. Re-evaluate
`docs/performance-acceptance.json` against this evidence. Its existing
`scope_revised` decision is not proof of a Python FastAPI improvement, and a
native Rust result cannot fulfill the Python comparison. No gain must be stated
plainly; a changed performance objective requires an explicit scope decision,
not a silently substituted success claim. The maintainer's own app trial is
outside this repository benchmark task.

## zep3 — Assemble the immutable candidate evidence

**Work:** After compatibility, native acceptance, coverage, independent review
and benchmark evidence qualify, assemble artifacts from the clean main source.
Use the existing Linux/macOS/Windows packaging jobs, Python-floor consumer,
`verify_release_candidate.py` and standalone H3 archive consumer. Inspect both
Cargo archives, wheel/sdist metadata, versions, licenses, names and hashes.
Verify extracted-archive default/http3 consumers without workspace patches;
the H3 consumer retains malformed-frame error 262 and fresh-connection recovery.

**Close with:** A complete checksum-bound bundle, clean consumers, exact run and
attempt identities, source/build/manifest/package digests, and current docs.
Record any candidate tag object and peeled commit and verify immutability.
This task assembles and verifies; registry upload is owned by m8mx.

## v5fe — Qualify artifacts and release controls

**Work:** Inspect the zep3 bundle and verify required main checks, main/version-tag
protection, `pypi` and `crates-io` environments and Trusted Publisher tuples for
`appunni-m/uvicorn-rs` / `release.yml`. Keep the sole-maintainer self-approval
configuration already requested. Verify no retired package is in the publish
inventory and that replacement/uninstall/rollback consumers pass.

The 2026-10-30 GitHub settings audit found the active `Protect main` and
`Protect version tags` rulesets, plus `pypi` and `crates-io` environments
restricted to `main`, with `appunni-m` as reviewer and self-review prevention
off. The maintainer confirms both crates.io Trusted Publisher entries already
exist; do not create duplicates. PyPI publisher identity is recorded as
`uvicorn-rs` / GitHub / `appunni-m/uvicorn-rs` / `release.yml` / `pypi`.

**Close with:** Accepted Cargo/PyPI bytes and consumers, all existing release
gates including benchmarks/coverage/review proven, and release controls verified
against the actual workflow and environment identities. This task is a child of
m8mx and depends on compatibility and candidate evidence. It does not block
compatibility acceptance or the start of benchmarks.

## m8mx — Publish and verify the consolidated release

**Work:** Once zep3, x3az and v5fe qualify, recheck the exact source, immutable
tag, selected artifacts and current registry state. For the 0.3.0 candidate,
the maintainer requested local Cargo publication before PyPI. The 2026-10-30
crates.io API snapshot shows both crate names at unyanked 0.2.1, so 0.3.0 is an
update, not a first publication. From a separate clean checkout of the exact
accepted tag, compare both `cargo package --locked` archives with the candidate;
publish `asgi-lifespan-protocol-rs` first, wait for its exact index checksum,
then publish dependent `uvicorn-rs`. Use a short-lived token restricted to both
crate names and `publish-update`, entered locally through Cargo; logout and
revoke it after use. Verify registry checksums and clean consumers, then run
`release.yml` on `main` with action `pypi` to publish the exact accepted
wheel/sdist without selecting Cargo publisher jobs. Recheck the registry before
retrying any upload; never overwrite an existing version. Do not publish while
any required release gate is open.

**Close with:** Registry versions and bytes match the accepted candidate,
registry-based Cargo/Python consumers pass, documentation/docs.rs reflects the
release, and the user receives package/version/install/rollback information.
An uploaded job or a candidate build alone is not verified publication.

## ec8x — Final migration acceptance

**Work:** Audit every required child and linked native acceptance against its
concrete receipt. Verify default and optional feature paths, Python-owned event
loop/context behavior, release bytes/consumers, documentation and the measured
performance decision. Preserve historical failures and the difference between
Python ASGI and native framework evidence. Do not edit changelogs.

**Close with:** All required tasks are actually complete and no claimed supported
surface, required artifact, consumer, metric or release gate lacks evidence.
Use a requirement-by-requirement closure audit, not an accumulation of status
comments. Do not manufacture completion to meet a date.

## Current candidate version

The synchronized candidate is **0.3.0**. The parser-specific admission fix adds
the public `ServerConfig::http1_allow_authority_form` field to the exhaustive
0.2.1 struct, requiring a minor bump for Rust callers with complete struct
literals. Cargo/Python manifests and workspace lock entries are synchronized.
Historical 0.2.2 receipts retain their original source and version. The release
version guard, locked offline Cargo metadata, locked offline uv validation, and
strict documentation build pass for the updated metadata.

Focused Windows CI [#538](https://github.com/appunni-m/uvicorn-rs/actions/runs/41180292641)
passed all 12 selected cases at `6f0cbda07`, with zero infrastructure failures.
Its artifact SHA-256 is
`531fbd2a57e6ad3034e9ca061d98f946584e6741e03ec722f14193672cf9ffb6`;
the parity report SHA-256 is
`99f044e32fe5840a3e6bee04faab928d314be05fb01f71e4daa73166800ecc80`.
This subset does not replace the full current-platform acceptance run.

## Focused commands and evidence reuse

Use an isolated pinned upstream interpreter at `target/uvicorn-oracle/bin/python`
and the project's prepared candidate environment. Do not install upstream
Uvicorn over the candidate's `uvicorn` files. Commands below are examples of the
maintained selectors; substitute the affected case IDs discovered in the audit.

```sh
uv run --group benchmark python scripts/run_parity.py \
  --oracle-python target/uvicorn-oracle/bin/python \
  --case-id http1.scope-query-header-and-body \
  --output target/completion/selected-parity.json

uv run --group benchmark python scripts/run_parity.py \
  --oracle-python target/uvicorn-oracle/bin/python \
  --profile cli --profile python-api \
  --output target/completion/api-cli-parity.json

uv run --group benchmark python scripts/run_unified_coverage.py \
  --oracle-python target/uvicorn-oracle/bin/python \
  --case-id http1.scope-query-header-and-body \
  --matrix-repeats 0 --case-infra-retries 0 --matrix-infra-retries 0 \
  --output target/completion/selected-coverage.json \
  --artifacts-dir target/completion/selected-coverage-artifacts
```

Repeat `--case-id` for a related batch. Use `native:<id>` for a native coverage
case. Selected coverage is debugging evidence; it does not pass the full gate.
Run the hosted three-repeat job once after the source batch is ready. Do not
run another full local matrix merely to duplicate the hosted run.

For focused Windows parity, dispatch `.github/workflows/ci.yml` in
`focused-windows-parity` mode with one or more comma-separated case IDs (up to
20). It builds and installs the candidate wheel, compares only those cases
with the isolated Uvicorn oracle, and retains the candidate's raw shutdown
trace in the artifact beside the parity report. Use it for Windows-specific
fixes before a broad run. Focused receipts can replace specific rows from an
older full matrix only when runtime source-file hashes, manifest, platform,
oracle and dependencies match, the per-case input is unchanged or rerun, and
any changed harness behavior is isolated to the replaced cases. Record both
the base and replacement receipts and their build identities. This produces an
auditable case-level matrix without presenting separate runs as one workflow;
do not reuse a failed row or infer unexecuted cases. Full mode remains the
default for manual CI runs.

For a qualified normal benchmark build, follow [benchmark preparation](../benchmarks.md#run-the-complete-comparison-with-one-command-interface):
build all required binaries first, capture identity, run normal public parity
once on that binary, then supply both receipts to `run_benchmark_categories.py`.
Use repeated `--category` selectors, or one category with `--workloads`, for an
identified diagnostic. The final hosted comparison uses all declared systems
and workloads. Do not change source, rebuild, or install packages between the
identity capture, parity and timing.

## Today's completion checkpoint

The task definitions and dependency repair can finish immediately. Full closure
depends on actual results: the existing coverage job has a 150-minute limit,
platform artifact jobs allow 60 minutes, and exact-main CI plus the benchmark
matrix and publication checks are additional work. These limits are not ETAs.
It is not credible to promise all gates will pass today before the gap report
and remaining compatibility work are known.

At each checkpoint record one of: accepted with receipt, failed with first
difference, live job with its handle, or blocked with the exact missing input.
The deliverable for the maintainer's own trial is a verified wheel/registry
version, its checksum/source, honest benchmark report, and
[FastAPI evaluation instructions](../fastapi-evaluation.md).
