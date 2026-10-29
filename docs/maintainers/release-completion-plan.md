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

1. CI
   [#466](https://github.com/appunni-m/uvicorn-rs/actions/runs/40807137734)
   completed on committed PR head
   `51c6e4920644d1a4e6fdd9f9ae9571ec8d2d7e61`, against `main` at
   `86e72e181d00feca1b4db7f30377d5d9d4345b83`. Rust quality/MSRV, native
   framework composition, release-evidence handoff, and 717/717 installed-wheel
   parity on Linux x86-64 and macOS ARM64 passed. Its unified three-repeat
   matrix attributed all 1,071 cases but missed the 100% gate at 13,962/14,134
   regions and 10,290/10,377 lines. The artifact is ID `12870939134`, archive
   digest `sha256:592368538dcbff0ba373ca9b3640676b80cc1ca7fc7abc572f8a0682f71b7a89`,
   report SHA-256 `d2f1dc778284e3736b9783fd50e3f19589c0608db04a42ee3c380e81c11597a6`.
   Windows parity stopped before its cases because the oracle dependency check
   required unavailable `uvloop`; Linux and macOS candidate identity recording
   failed because pinned `maturin` was not on PATH. Linux consumer checks
   passed, and the macOS candidate wheel passed 717/717.

   The local uncommitted fix makes `uvloop` platform-specific, selects asyncio
   on Windows, and records Maturin through the pinned `uvx` invocation. Focused
   syntax, manifest/platform selection, and pinned-tool checks passed. The PR
   workflow cancels its previous run when a new commit is pushed. Run only the
   affected selected parity and evidence groups locally, then commit and push
   the platform/evidence fix and aligned documentation with any related
   coverage inputs as one reviewed batch. Use one hosted run for that changed
   source. Docs run #183 passed for the previously committed source; the
   updated pages need a fresh deployment.

   CI #466 is gap-mapping evidence, not coverage acceptance: its recorded Rust
   source hashes match the branch, but the local manifest and runner changes
   are not included. Coverage-MCP could not return an independent receipt after
   its daemon failed health checks and timed out following restart. The saved
   LLVM report maps 6 regions / 4 lines in `crates/uvicorn-rs/src/http3.rs` and
   166 regions / 83 lines in `src/lib.rs`; see
   [coverage status](../coverage.md#current-unified-coverage-status-2026-10-29).
   The old macOS TLS fixture issue is covered by #466's 717/717 hosted macOS
   parity receipt. Do not rerun unchanged local matrices.
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

**Close with:** Accepted Cargo/PyPI bytes and consumers, all existing release
gates including benchmarks/coverage/review proven, and release controls verified
against the actual workflow and environment identities. This task is a child of
m8mx and depends on compatibility and candidate evidence. It does not block
compatibility acceptance or the start of benchmarks.

## m8mx — Publish and verify the consolidated release

**Work:** Once zep3, x3az and v5fe qualify, use a valid new version if registry
state requires it. Recheck the exact source, immutable tag, selected artifacts
and current registry state, then execute the maintainer-authorized combined
Cargo/PyPI release. Publish lifecycle before server; use the exact accepted
wheels/sdist. Use the existing Trusted Publisher environments. Reconcile any
already-published version by checksum rather than attempting to overwrite it.

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
