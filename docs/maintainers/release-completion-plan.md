# Release completion plan

This is the execution guide for the open Kata tasks, agreed from the maintainer's
2026-10-28 request to define concrete work and prepare a build for their own real
FastAPI evaluation. Kata remains the system of record. The maintainer will run
their application trial; collecting their application or running its load is not
a prerequisite for completing the repository work.

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
- The current manifest has 137 operations and 89 execution profiles. Those counts
  describe its inventory, not completeness of upstream compatibility.
- Platform acceptance uses the existing CI profiles: Linux x86-64, macOS ARM64,
  Windows x86-64 on CPython 3.12.13, plus the declared Python 3.9 wheel-consumer
  check. Other Python versions need their own evidence before being claimed as
  tested. The Python floor check does not establish Uvicorn 0.54.0 parity there.
- Each accepted receipt identifies the clean source, manifest/input digests,
  binary or package hash, environment, command, result, and workflow attempt.
  A PR merge ref and its branch head are different revisions: retain both and
  let the existing identity validators decide applicability.

No original release gate is waived by this plan. Historical measurements remain
historical. A task closes on its own deliverable; downstream publication gates
belong to the release tasks rather than being copied into every prerequisite.

## Execution order and stopping rules

### Current receipts — 2026-10-31 (PR run #528; overall conclusion cancelled)

PR #19 remains draft/open against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. Full CI
[#528](https://github.com/appunni-m/uvicorn-rs/actions/runs/41127272457) ran on
head `8a17d982a7b98a0074ab7e56acad4c508d9d2c73`, merge ref
`10929063e0dfb420d6ebb7210922ad805528039d`.

The overall workflow conclusion is cancelled. Individual completed job
receipts below are recorded by their own result; a successful sub-job does not
turn the workflow into a passing CI run.

Linux installed-wheel parity passed 718/718. The Linux 0.2.2 candidate and its
clean consumers passed; artifact `13012012115` has SHA-256
`656ad0235e3ac25f1680966992e318dd6ce8cc8e0ba4011e242a6743ed13235`, and its
build-manifest SHA-256 is
`085e0903bd8d4f52c0a183b7ab4f44edb4d48f04b05ac4428e8a451bd09b83e4`. Windows
candidate parity completed 691 cases: 688 passed, 3 failed, and zero had
infrastructure failures. Its artifact `13012838178` has SHA-256
`ab0a3f293329a4cbdbcf2c4be47e9bee4bcee4af9a0ec6975712e0b75144b962`. The
failures are `python-api.module-cli-two-workers-stop-on-sigterm`,
`python-api.module-cli-web-concurrency-two-workers-serve-request`, and
`python-api.module-cli-explicit-workers-overrides-web-concurrency`; all served
HTTP 200, but process timeouts/exits and shutdown log counts differed. Signal
ordering and root cause remain unconfirmed. macOS candidate verification was
cancelled. Rust formatting/lints, feature builds, Rust docs/no-Python checks,
MSRV, release-evidence contracts, native FastAPI-RS composition, Linux clean
consumers, and separate docs deployment run #215 passed.

The #528 three-repeat coverage report completed with all 1,340 indexed cases
attributed, but missed the 100% gate at 14,137/14,252 regions and 10,411/10,465
lines. Artifact `13016632517` has archive SHA-256
`4674397eba67621d60dd06f3f1cdb9793e83d9ba7bedfb9b64eacf9dca4177e7`; its
report source SHA-256 is
`56d4ce12ebf5dddcad815968f622ac22f5fd6cfd1f8f52212b670d2d7da4fd24` and its
native-extension SHA-256 is
`c7e901b397b55d2d72bbedf9ad85eb7c4c213a97246ee2e3c3b5d8df472b5041`.
Independent Coverage-MCP review remains open because the report is not yet
zero-gap.

The local H2 parity runner captures the event baseline before request
submission and waits up to two seconds for case-required app events before its
final snapshot. `http2.response-trailers-without-te` passed 1/1 locally; the
current Linux hosted parity also passed 718/718. This is runner observation
evidence and does not change server behavior.

Focused Windows run [#530](https://github.com/appunni-m/uvicorn-rs/actions/runs/41137831335)
on head `158b82b4e0364f439f2390a694bbd53e0849f03c` passed all three failed
case IDs (3/3, no infrastructure failures) with opt-in shutdown tracing. Both
oracle and candidate returned HTTP 200, exited 0 without timing out, and had
matching normalized shutdown events. Artifact `13016614526` has SHA-256
`d8497ab002d4199ec58c4b873ef7569e7bfe3348c8c92284603df812fcbd1bd3`. This
does not replace a full Windows matrix receipt or prove the root cause of the
earlier differences. Do not start a new benchmark before compatibility passes.

The earlier selected-case coverage batch added expected Debug/Display output
checks to the existing coverage-only source-chain fault path. The affected case
passed 1/1 with no retries or repeats and complete attribution. The selected report is
`target/coverage-batch/default-header-source-chain-asserted.json` (SHA-256
`f043e8c35779b7ce0e1d26e20e88d573c75c26393f7fe552869fa695923fcecf`); it binds
to dirty `src/lib.rs` SHA-256
`5be5c51b29d1a5e8fe533f1c20b259b196471435ac7634384c703f79fc26a9a3` and native
extension SHA-256
`c5890f6e4a134d0d7cae9c387551ad28b0d6630a4e438a24de48c115c83960c2`. The
source change is now committed, but this dirty selected-case receipt remains
diagnostic only; the clean #528 full report is authoritative and still has
nonzero gaps.

The publisher entries, main/tag rulesets, and release environments have been
verified; the maintainer confirms both crates.io Trusted Publisher entries are
already configured. A 2026-10-30 registry check lists Cargo 0.2.1 for both
release crates and no PyPI `uvicorn-rs` project. No 0.2.2 candidate, tag, or
published package is accepted. No benchmark has started after the parity-first
direction; the older Linux ARM64 HTTP/3 benchmark remains incomplete. Do not
publish until the exact-main gates pass.

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
contract. Use `tests/parity/inputs/cli.json` and the relevant Python API inputs.
For a missing mapping, name the parameter and exact observation before adding a
case. A setting that affects serving needs a live behavioral observation, not
only successful parsing. Resolve all inventory mismatches and ignored options.

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

## 7t4g — Coverage-MCP recovery and exact-report handoff

**Work:** Diagnose the service/import failure once from its current logs. Use the
existing canonical-report projection (`scripts/project_coverage_mcp.py`) and
handoff tooling rather than repeatedly importing the large raw report. Recover
in an isolated store when necessary; preserve the shared database and unchanged
raw CI artifact. Query and retain every region and line page for the passing
source, attach the receipt, strict-check it offline and publish the existing
reviewed handoff artifact for the exact main run/attempt.

**Close with:** Complete zero-gap independent page chains with source/build
identity, successful attachment/offline verification, and one digest-checked
handoff artifact selected by the candidate workflow. A timeout, pending status,
raw LLVM summary, or synthetic receipt cannot satisfy this task.

## nbmg — HTTP/1 upload timeout root cause

**Work:** After compatibility passes, select only Linux ARM64
`fastapi-upload-1m-write-1k` at the recorded 1 MiB/1 KiB/concurrency-8 settings.
Retain client callback/upload counts, server read/queue/cancellation events and
monotonic timestamps. Trace the first stalled boundary, not the later
ClientDisconnect. Keep the 15-second client timeout. Limit the first diagnostic
batch to three attempts; if it does not reproduce, record that and the missing
evidence instead of launching an unrelated matrix.

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
tag, selected artifacts and current registry state. For the 0.2.2 candidate,
the maintainer requested local Cargo publication before PyPI. The 2026-10-30
crates.io API snapshot shows both crate names at unyanked 0.2.1, so 0.2.2 is an
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
