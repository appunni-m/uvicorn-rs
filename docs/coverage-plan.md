# Plan: deterministic black-box coverage for the ASGI server

## Current evidence status (2026-10-07)

**Current-source attribution, native coverage, and normal-build parity pass**
for the recorded source/build. The inventory declares 490 workflows across 70
input files: 238 oracle-parity cases and 252 target-only contracts. The source
passed all 490 attribution cases and three complete repeats with zero failures,
infrastructure errors, retries, or cases not run. The report records
5,108/5,108 native LLVM regions and 3,608/3,608 lines (100%); unfiltered
Coverage-MCP has zero gap groups, `source: matches_receipt`, and `tests:
passed`. This is default-feature `cfg(coverage)` evidence for `src/lib.rs` on
macOS ARM64, not all repository code, all features, or complete ASGI
conformance. A normal non-instrumented local build passed all 238 public
parity cases. The installed-wheel exclusion audit is from a prior source
snapshot and must be repeated for release verification. The matrix also
records a 128-request HTTP/3 same-connection sequence in each of three full
repeats. Source/build identity and retained receipts are documented in
[current coverage evidence](coverage.md#current-full-verification-490-cases) and the
[490-case archive](../benchmarks/results/2026-10-07/famh-concurrent-load-acceptance/).

The historical 445-case snapshot recorded all 4,719/4,719 regions and 3,329/3,329
lines, with zero Coverage-MCP gaps and 445 passing attribution cases. Two full
repeats passed 445/445. The third had 436 passes, one graceful-drain adapter
infrastructure failure, and eight cases not run, with zero reported behavioral
mismatches. Its global `Cancelled` diagnostic came from shutdown while Hyper
could still be detecting a connection's HTTP version; the log had no connection
identity. The gate remained incomplete and MCP retained `tests: failed`.
Source, native, and receipts are preserved under
`build/asgi-coverage/unified-listener-result-policy-445-2026-10-05/`.
The existing plaintext/TLS drain inputs now hold a real partial-preface idle
connection and require its closure. The narrow cancellation correction and
stronger observation contract passed the preceding full verification. Those input
changes did not add cases, files, or operations.
The changed native passed seven targeted attribution cases without failures
or retries, including both stronger ordinary drains. The before/after artifact
audit verifies matching runner, fixture, manifest, input, environment, and Cargo
lock identities. Its follow-up full run was interrupted after 219 passing
attribution cases when reachable `HeaderMap::append` capacity panics were found.
Completed profiles remain tied to that source/build and cannot be merged with
the next source. The later 447-case source passed its separate instrumented
gate, and the current exclusion correction passed its own separate gate. See
[coverage results](coverage.md).

HTTP response and WebSocket acceptance header assembly now use fallible
`try_append` before committing response state or releasing task ownership. The
new target-only capacity support contracts use ordinary valid ASGI headers and
no native injection control. They retain the existing matrix/result envelope
and document the target's finite capacity without asserting a universal
accepted-header count or Uvicorn equivalence. The interruption does not justify
excluding any compiled regions from the next full denominator.
The corrected source passed nine attribution cases, including both new public
capacity contracts, with zero failures or retries. The before/after artifact
audit verifies the same harness, inputs, environment, and Cargo lock; the old
native produced two behavioral failures and two unexpected-panic
infrastructure failures. The new subset covers 2,909/4,732 regions and
1,970/3,332 lines. The fresh 447-case full gate subsequently passed all regions,
lines, attribution cases, and three complete repeats. Its normal-build
fault-exclusion audit failed. That source/build is now historical; no profiles
from the interrupted source were merged.

The preceding 444-case snapshot recorded all 4,717/4,717 regions and 3,328/3,328
lines, with zero Coverage-MCP gaps. Its gate remained incomplete: 443
attribution cases passed and one live Uvicorn TLS WebSocket handshake timed out.
All three full repeats passed 444/444 without behavioral or infrastructure
failures. Coverage-MCP retained `tests: failed`, so the complete attribution
requirement was unmet. Source, native, and MCP receipts are preserved under
`build/asgi-coverage/unified-result-state-444-2026-10-05/`.

The preceding 442-case snapshot passed attribution and three complete
matrix repeats with no mismatches, infrastructure failures, or retries. It
recorded 4,707/4,713 regions and 3,326/3,330 lines; Coverage-MCP identified six
gap groups and matched its source receipt. The measured source and native
binary are preserved under
`build/asgi-coverage/unified-result-policy-442-2026-10-05/`.
The strengthened plaintext/TLS shutdown cases then exposed retained listener
admission on the 444 native binary: both live comparisons failed only
`listener_closed_before_release`, with zero infrastructure failures. The
current source releases the listener before drains. Both strengthened cases
passed in the preceding 447-case full report. The new normal-build audit
passes, and the current instrumented gate also passes after the exclusion correction.
The clean committed-source release baseline is also outstanding.

The historical report at
`build/asgi-coverage/unified-423-final-2026-10-05/coverage-report.json`
records **4,356/4,356 LLVM regions and 3,060/3,060 lines (100%)**. Per-case
attribution matches the aggregate profile union. Its attached Coverage-MCP
receipt reports zero gap groups, `source: matches_receipt`, and `tests: passed`.
A normal release build for that snapshot contained no fault-control markers,
exposed no fault CLI option, and ignored an armed fault file in an existing
live HTTP parity case.
That snapshot passed Clippy with all features in normal and coverage-only
configurations. These checks must be repeated with the current panic, unwrap,
and expect lint policy.

That report indexed 423 cases across 67 files: 208 oracle-parity cases and 215
target-only fault contracts. Every attribution case and all three complete
matrix repeats passed with zero behavioral or infrastructure failures and no
retries. The recorded 100% applies only to that source/build and validator.

The measured source set is `src/lib.rs` in the default native configuration,
with coverage-only fault seams enabled. Optional `runtime-diagnostics` code,
dependencies, Python code, and other platforms are outside this denominator.
No project Rust files or regions were excluded. That checkout was dirty at
revision `cf9bf062133721b094e914f49ed8f54c613eb30f`; repeat on clean committed
source before treating this as a release baseline. The complete source/build
identities and scope are in [coverage results](coverage.md).

## Goal and decision

Raise measured Rust source coverage to 100% for the audited production Rust source while retaining the existing manifest-backed, live parity matrix and its input-only protocol cases. Keep one test runner, one case/result format, and one authoritative coverage report. Add one standardized case family: **fault-injection workflows**.

Ordinary cases continue to compare live wire behavior against the pinned Uvicorn or Hypercorn oracle. A Rust-only injected failure has no equivalent stimulus in those servers, so it must be labeled and evaluated as a fault-contract case, never reported as Uvicorn parity. Both modes feed the same source/build coverage union and case-to-region attribution report. Verification mode remains visible as case metadata; it does not split the coverage denominator or create a second coverage ledger. Only the behavioral parity pass rate is scoped to oracle-backed cases.

Do not add duplicate requests just to increase counts, exclude source regions to improve the percentage, or claim branch coverage when the report does not contain branch detail.

## Historical baseline from the previous coverage snapshot

| Measure | Value in recorded snapshot |
|---|---:|
| Full live matrix | 329/329 passed in each of 3 complete runs; 0 failures in those runs |
| Oracle-backed parity | 183/183 passed in each run |
| Target-only fault contracts | 146/146 passed in each run |
| LLVM regions in `src/lib.rs` | 3,697 / 3,853 (95.95%); 156 missing |
| LLVM lines in `src/lib.rs` | 2,574 / 2,651 (97.10%); 77 missing |
| LLVM branch detail | Not present in exported report |
| Coverage-MCP | 49 function groups; source matches receipt; tests passed |

The runner output is
`build/asgi-coverage/unified-lifespan-retained-callables-2026-10-04/coverage-report.json`.
It contains all 329 case rows, their individual profile receipts and region
hits, the aggregate region/line summary, and all 156 uncovered regions. Each
of the three matrix runs passed 329/329 with no infrastructure errors or
transient retries. `case_attribution_complete` and
`profile_union_matches_attribution` are true; all 329 cases have attribution
profiles.

Coverage-MCP ingested the compact report at
`build/asgi-coverage/unified-lifespan-retained-callables-2026-10-04/mcp-ingest/coverage-report.compact.json`.
Its parsed JSON matched the runner output before the Coverage-MCP pages were
attached. The sidecar receipt records the runner report digest it derives from,
and the four saved page objects contain all 49 gap groups. Coverage-MCP reports
3,697/3,853 regions with `source: matches_receipt` and `tests: passed`.

This measurement finished at 2026-10-04T13:03:46Z on a dirty working tree at
revision `cf9bf062133721b094e914f49ed8f54c613eb30f`. The run source/input digest
is `4eac10ffaf879ed17f33043dbca96e35dc9ffb89c841be8414c2ad478281c73c`;
`src/lib.rs` SHA-256 is
`9f2fc5513e93ce9acba8bc504c3f61a68b7acab5da613d22d6a7d954c9b984a3`. The
instrumented extension SHA-256 is
`cc451a45c12bf98da7b4ffcccd7a64182fb1bf9fb6335e5a6a4854a4d8a0139b` and the
build ID is `4f30e39076a8204529ae60cbe773540bd2fbbd91f7d94e2aafa5b6e8110f66c0`.
The report records the Cargo lock digest, platform, Python/Rust versions, input
and source digests, all three matrix receipts, and per-case profiles.

**Historical execution status:** the unified report, Coverage-MCP provenance,
case attribution, and three-repeat correctness gate are complete for that
measured working tree. The 100% region/line gate was not met: 156 regions and
77 lines remained. That snapshot's matrix contained 183 oracle-parity rows and 146
fault-contract rows. Fault contracts and compile-gated failpoints are
implemented; normal-build exclusion and complete source coverage remain
separate gates.

## One unified coverage and attribution report

Produce one authoritative `coverage-report.json` for the complete selected case
matrix and exact instrumented source/build. It contains both the aggregate
LLVM/Coverage-MCP result and enough per-case evidence to answer “which case
triggered this region?” without switching reports or guessing from test names.

```json
{
  "type": "llvm.coverage.json.export",
  "version": "...",
  "data": [],
  "uvicorn_rs_unified": {
    "schema": "uvicorn-rs-coverage/unified@1",
    "run": {
      "source": {"revision": "...", "sha256": "..."},
      "build": {"native_extension_sha256": "..."}
    },
    "matrix": {
      "selected": 0,
      "executed": 0,
      "passed": 0,
      "case_results": [
        {"case_id": "...", "verification": "oracle-parity", "status": "passed"},
        {"case_id": "...", "verification": "fault-contract", "status": "passed"}
      ]
    },
    "coverage": {
      "summary": {
        "regions": {"covered": 0, "total": 0},
        "lines": {"covered": 0, "total": 0}
      },
      "regions": [
        {"id": "...", "file": "src/lib.rs", "start": {"line": 1, "column": 1}, "end": {"line": 1, "column": 2}, "hit_by": ["..."]}
      ],
      "uncovered_regions": [],
      "coverage_mcp": {"status": "measured"}
    }
  }
}
```

This abbreviates the implemented report shape; placeholders and zero counts
illustrate its structure, not measurement results. LLVM data and the runner
extension are in the same JSON document. Coverage-MCP reads that document,
and its receipt is attached under `coverage.coverage_mcp`.
The builder joins the parity runner's case receipts and per-case region hits.
Run each case in an
isolated target process (or otherwise give its instrumented server process a
case-specific LLVM profile destination), export that case's hit set, and union
the profile data for the single aggregate numerator/denominator. Keep raw
profiles as reproducibility artifacts, not as separately maintained coverage
results. Verify that the union of all `hit_by` sets exactly matches the
aggregate covered-region set before publishing.

Store the attribution relation once, as `coverage.regions[].hit_by`. Derive a
case's region IDs by filtering that list for its case ID; verify the inverse
mapping in the runner without serializing a duplicate array in every case
receipt. This preserves complete bidirectional lookup in the one report and
bounds its size for direct Coverage-MCP ingestion.

Every compiled region in the declared source set appears exactly once in the
report. A covered region lists every case that reached it; an uncovered region
has an empty `hit_by` and a candidate workflow, disposition, and next action.
Case rows show verification policy and behavioral result in the same table, so
parity outcomes remain interpretable while all passing case classes contribute
to one coverage percentage. Failed or incomplete runs may help diagnose gaps,
but cannot satisfy the complete-matrix coverage gate. If Coverage-MCP cannot
consume attribution fields directly, an adapter should join its aggregate
result and per-case LLVM exports into this single published report; do not
publish competing “parity coverage” and “fault coverage” reports.

Use source/build identity in every region key. Line coordinates alone are not
stable across source revisions. For the current fixed source, a region key may
combine source hash, file, function identity, start/end coordinates, and LLVM
region kind. New builds produce a new report identity rather than silently
merging stale hit maps.

## One standardized case model

The current implementation keeps one manifest-backed case model but uses
protocol-specific input objects and adapters. It declares `manifest@2`,
`input@7`, `result@3`, and one unified coverage extension. Cases identify a
profile and operation; fault-contract rows also name an allow-listed fault and
an observable invariant. The current runner does not yet implement a generic
multi-action `scenario`/`stimulus` envelope. The following JSON is a future
design target, not the current input schema:

```json
{
  "schema_version": 2,
  "case_id": "fault.http1.scope-build-memory-error",
  "verification": "fault-contract",
  "profile": "http1",
  "scenario": "http.request-and-follow-up",
  "fault": {
    "point": "scope.http.asgi.version.set-item",
    "kind": "python-exception",
    "name": "MemoryError",
    "occurrences": 1
  },
  "stimulus": [
    {"action": "server.start", "timeout_ms": 5000},
    {"action": "http.request", "method": "GET", "path": "/scope"},
    {"action": "http.expect_contract", "id": "request-fails-cleanly"},
    {"action": "http.request", "method": "GET", "path": "/health"},
    {"action": "http.expect_contract", "id": "follow-up-request-succeeds"},
    {"action": "server.shutdown", "grace_ms": 1000}
  ]
}
```

This proposed envelope remains unimplemented. In it, `scenario` selects a
reusable action template; `stimulus` supplies its concrete protocol input and
timeouts. The `expect_contract` references stable runner-owned invariants, not
golden server output. For `oracle-parity`, the same action sequence is executed
against target and reference and normalized observations are compared. For
`fault-contract`, the oracle is `not-applicable` and the named contract is
checked against target observations. Both produce the same case-result
envelope: case ID, verification mode, selected/executed/result status,
normalized event trace, process exit, cleanup status, and case-specific
coverage-profile reference. The report joins those case rows to the single
region attribution map and aggregate. Protocol adapters may normalize
frame/message boundaries, but must preserve logical ordering, status, headers,
body bytes, close codes, ASGI events, and lifecycle outcomes.

The common scenario lifecycle is `server.start -> ready -> stimulus ->
observe -> cleanup -> follow-up`. Every scenario has bounded connect/read/stop
deadlines, an explicit disconnect/cleanup action, and a process/socket leak
check. A case may contain multiple protocol actions, which is necessary for
backpressure, cancellation, follow-up health checks, and graceful shutdown.
The recorded matrix had 183 oracle-parity rows across the declared HTTP,
WebSocket, lifespan, startup, and server-API slice. A future generic scenario
adapter must preserve their stimuli and normalized observations before replacing
the protocol-specific input format.

### Reusable scenario catalog

Use these named workflows as parameterized templates; each case is a row of the
existing parity manifest, not a new runner or an ad hoc test script.

| Scenario family | Shared action pattern | Required observations | Verification modes |
|---|---|---|---|
| `http.request-and-follow-up` | Start; send one request; collect response; send follow-up; stop | Status, headers, exact body bytes, ASGI event order, process health | Oracle parity; injected bridge/handler fault contract |
| `http.body-upload` | Start; send body in fixed chunks; optionally truncate/reset; collect outcome; follow-up; stop | ASGI `http.request` chunk sequence and `more_body`, disconnect event, response/close, cleanup | Oracle parity for valid/malformed wire cases; fault contract for internal channel errors |
| `http.response-stream` | Start; request stream route; hold/read client at selected checkpoints; release or disconnect; follow-up; stop | Logical body bytes/order, backpressure progress, disconnect/cancellation, task cleanup | Oracle parity where transport permits; fault contract for closed queues/task errors |
| `websocket.session` | Start; connect; accept/reject; send/receive parameterized frames; close/reset; follow-up HTTP; stop | Handshake result, frame type/payload/order, close code/reason, ASGI events, task cleanup | Oracle parity for expressible frames; fault contract for internal queue/upgrade/task errors |
| `lifespan.start-stop` | Start process; exchange startup; optionally serve probe; exchange shutdown; stop | Startup/shutdown event sequence, process exit/error, no orphaned task | Oracle parity for app-visible lifecycle; fault contract for internal channel/join/deadline failure |
| `server.startup-failure` | Reserve resource or configure TLS; start; observe failure; release resource; start again | Error category, exit policy, listener/resource cleanup, second start result | Oracle parity for shared public config; target fault contract for selected internal failures |
| `server.graceful-drain` | Start; hold HTTP/WS/H3 work; request shutdown; release or let deadline expire | Accepted work completion/abort, lifespan shutdown order, exit deadline, no leaked socket/task | Oracle parity for public behavior; fault contract for forced task/join failures |
| `transport.disconnect` | Start; send partial request/frame; FIN/RST/stream reset; wait; follow-up; stop | ASGI disconnect delivery, task cancellation, transport close, server remains usable | Oracle parity when the reference exposes the same transport; fault contract for synthetic I/O errors |

The manifest must make protocol-specific client operations explicit (`http1`,
`http2`, `http3`, WebSocket, TLS) while sharing lifecycle, deadlines, trace
shape, contracts, and cleanup. Do not normalize away behavior that the support
matrix promises. If an oracle cannot represent a transport stimulus, label the
case target-only and keep it out of the parity numerator.

Case execution must declare one of two verification policies:

1. **Oracle parity:** run the same ordinary workflow against target and reference, then compare live public observations.
2. **Fault contract:** run the target with exactly one allow-listed failpoint, exercise it over a real process/socket/lifecycle boundary, and verify a stable invariant such as request fails without corrupting subsequent requests, startup fails cleanly, or shutdown leaves no server task running. Record the oracle as not applicable with the fault reason.

Use the existing parity result envelope for selected/executed/passed/failed/not-run accounting, with the policy and failpoint in the evidence metadata. Increment the input schema version when this is implemented; reject unknown failpoint names, duplicate case IDs, invalid policy combinations, and fault cases missing their network/lifecycle stimulus.

## Fault-injection design constraints

- Compile failpoints only into the dedicated instrumented test build, using an explicit Cargo feature or compile-time cfg. Production wheels and normal release binaries must contain no active control path.
- Keep the failpoint registry typed and allow-listed. A case can activate one point at a time; avoid arbitrary Rust function names or free-form panic/error injection from the environment.
- Production code propagates operational failures through `Result`/`PyResult`
  and represents ownership invariants in types. The main crate and HTTP/3
  probe deny panic, unwrap, and expect lints. The coverage-only exception to
  Clippy's panic lint is scoped to the `coverage_panic` helper for task
  unwind/mutex poisoning contracts; it is absent from normal builds. Each
  process's expected hook source, messages, and counts must match exactly.
  There is no runtime panic allow list.
- Prefer named operation boundaries, for example `scope.http.asgi.version.set-item`, over source line numbers. Line numbers move; IDs should remain stable through refactors.
- Exercise the actual boundary result path: inject a `PyErr`/typed Rust error at the wrapper around the operation whose `?` propagation is being measured. Report synthetic injected `MemoryError` as error-path coverage, not as proof that CPython's allocator failed.
- For channels, tasks, sockets, listeners, and deadlines, fail at the narrowest boundary that preserves the real caller and cleanup path. Do not count an early return that skips the error-handling code under review.
- Every failpoint must have a documented externally observable invariant and a black-box trigger. A failpoint with no observable assertion is not an acceptable coverage case.
- Keep normal parity cases input-only and oracle-backed. Keep fault cases in the same runner but clearly separate from oracle equivalence claims.

## Workstreams and case plan

### 0. Freeze a trustworthy baseline

1. Record commit/revision, dirty state, Rust/Python versions, OS/architecture, Cargo lock digest, extension digest, manifest/fixture/runner digests, instrumentation flags, and LLVM report digest.
2. Ensure every case profile and aggregate coverage result comes from the same source and instrumented build. Do not union profiles across source changes.
3. Add or enable the Coverage-MCP receipt metadata needed for it to report source/build identity and test status as verified.
4. Store selected case IDs, verification modes, pass receipts, case-to-region hits, uncovered regions, and aggregate totals in the one coverage report; retain raw profiles as supporting evidence.

**Historical status (329-case snapshot): complete for that measurement.** All 329 cases passed in each of three complete matrix runs. The separate
per-case attribution sweep passed all 329 cases with no transient
infrastructure failures. Coverage-MCP identifies the source/build and reports
`matches_receipt` with `tests: passed`. The checkout was dirty, so the recorded
source hash—not the revision alone—identifies the measured state.

**Exit gate:** passed for the recorded source/build; repeat after each source or
case change.

### 1. Add naturally triggerable protocol cases first

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.

Before adding failpoints, use true client inputs for any uncovered behavior that can happen on a real deployment. The current matrix covers H1 malformed-final-chunk disconnect, incomplete-upload reset, early-response drain and response-stream reset; H2 partial-upload reset/cancellation and a healthy sibling stream; and H3 body errors, close/cancellation handling and follow-up health. Its H3 one-connection sequence serves 128 requests with 128 request-body pumps joined in each of three full repeats. Remaining candidates must first be reconciled against existing cases and named requirements:

- HTTP/2 client disconnect while response flow control is blocked, and broader simultaneous-stream cancellation races.
- HTTP/3 raw `RESET_STREAM` frame interoperability and response-stream failure while sending. The current body-pump cases do not prove that a particular QUIC reset frame was received.
- WebSocket raw data/control-frame faults, immediate FIN/RST and queued sends while closing; retain existing handshake, echo, denial, disconnect and shutdown cancellation coverage.
- TLS handshake stall during server shutdown and occupied-port bind failure, if the current listener cases do not exercise the same externally visible contract.
- Audit remaining ASGI event-field conversions (missing/wrong types, both/neither WebSocket payloads, receive-after-disconnect, completion before the final response body) against existing parity and fault-contract mappings before adding cases.

Each candidate must name the missing function/region it targets before it is added. Run the same bytes/protocol workflow against the pinned oracle when that oracle supports the protocol. Preserve only cases that add source coverage, expose a behavior mismatch, or establish a distinct support-matrix claim.

**Exit gate:** Every feasible network/ASGI branch discovered by Coverage-MCP is either reached by an oracle-backed case or classified as requiring an injected internal fault.

### 2. Python/PyO3 bridge and ASGI object construction

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.


The largest unreachable-looking groups are scope construction and PyO3 event conversion. Add named fault points around fallible construction/extraction sites in:

- HTTP and WebSocket scopes (`build_scope`, `build_websocket_scope`);
- HTTP request/disconnect messages (`make_http_request_message`, `AsgiIo::receive`);
- HTTP response start/body conversion and queue sends (`AsgiIo::send`);
- WebSocket receive/send and message queueing (`WebSocketIo`, `queue_websocket_message`);
- lifespan receive/send event construction (`LifespanIo`);
- `set_scope_state`, `classify_asgi_event_type`, module initialization, and PyO3 method wrappers.

For each operation class, inject representative errors for allocation/construction and extraction/conversion; enumerate a distinct named failpoint only where it leads to a separate Rust error edge. Verify the Python exception reaches the ASGI app boundary or maps to the documented transport failure, the process remains alive, and a follow-up ordinary request succeeds where appropriate.

**Important:** one generic “raise somewhere” hook will not cover all `?` edges. Fault selection must reach the exact operation boundary and preserve subsequent cleanup.

**Exit gate:** no missing bridge-construction/error-propagation region remains in the Coverage-MCP report.

### 3. HTTP body, response, and cancellation paths

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.


Use real HTTP workflows first, then targeted failpoints for channel/task states that a client cannot create:

- `pump_http_request_body`: data, end-of-stream, body-frame error, receiver closed, peer close, and cancellation.
- `AsgiIo::receive`: queued request, empty queue requiring a bridge future, disconnected flag, connection-close notification, lock contention, and closed sender.
- `AsgiIo::send`: response-start success/duplicate/disconnect, status/header/body extraction errors, body queue available/full/closed, and send wait cancelled.
- `AsgiBody::poll_frame` and `poll_app_task`: chunk available, no chunk, app pending/completed/raises/panics, final body seen/not seen, and task join error.
- `handle_request` / `handle_request_parts`: invalid start, other app error, app returns before start, response starts before app error, and dropped connection.

The live observations should include response status/body or connection closure, app event order, task cleanup, and a follow-up request. Do not assert exact traceback strings or socket read chunk boundaries.

**Exit gate:** HTTP/1, HTTP/2, and HTTP/3 transport outcomes are each either oracle-compared or explicitly recorded as target fault-contract cases.

### 4. WebSocket state machine and task paths

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.


Build one parameterized WebSocket workflow family covering:

- handshake accept/reject/early app return/error and accept-header conversion;
- connect delivery; text and binary receive; normal close with/without code/reason; malformed frame and abrupt EOF;
- send before accept, duplicate accept, send with neither/both payloads, valid text/binary, close before/after accept, close twice, send after disconnect;
- outgoing queue available/full/closed, app completes with queued frames, app error, app cancellation, client close, and server shutdown while accepted;
- upgrade cancellation/failure and connection-close notification.

Use existing raw-wire support or add a low-level WebSocket stimulus adapter only for frame inputs the standard client library cannot express. Use injected channel/task failures for states not reachable from a valid client. Do not add several unrelated WebSocket test harnesses; all variants are rows in the same workflow schema.

**Exit gate:** all missing WebSocket driver/IO/handshake regions are covered and the app-visible disconnect code/reason behavior is compared where the oracle exposes it.

### 5. Lifespan and server lifecycle

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.


Extend the lifecycle matrix around the existing startup/shutdown cases:

- startup and shutdown complete, failed, unsupported, unexpected event, app return, and raised exception;
- receive channel closed before/while startup or shutdown; event sender closed; task panic/join failure;
- caller cancellation during startup, a held HTTP request, WebSocket session, idle TLS handshake, and lifespan shutdown;
- zero/short graceful deadline, connection drain expiry, WebSocket task drain expiry, HTTP/3 task expiry, and lifespan shutdown timeout;
- bind collision and TLS configuration/handshake failures.

Use external signals/control files or the existing public server API as workflow stimuli; inject only the internal join/accept/timeout failures that OS/client actions cannot select deterministically. Assert cleanup order, process exit policy, lifespan events, and whether the listener is reusable.

**Exit gate:** each server lifecycle branch has a deterministic completion or injected-fault case and no orphan task/socket remains.

### 6. HTTP/3 connection and stream failures

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.

The historical zero-length HTTP/3 DATA-frame investigation encountered a
Hypercorn timeout and the pinned `h3` receive API treating an empty frame as
`None`. The empty-chunk consumer path is now covered by
`fault.http3.body-pump-empty-data-frame-preserves-upload`, which injects one
empty chunk at the receive boundary and checks the subsequent real upload.
That target-only result does not establish wire-level empty-frame
interoperability; an independent wire client is still needed for that claim.


The current 490-case report has no missing native regions in its declared Rust source scope. The body-pump slice covers request-body errors, cancellation/close selectors, disconnect delivery, bounded pump joining, and same-connection follow-up behavior. Keep that measured coverage distinct from unresolved transport claims: add an ordinary H3 probe for raw request-stream reset and response-write failure where the client can trigger them; use a named target fault contract only when a real client cannot select the internal error deterministically. Invalid ASGI response handling and endpoint/connection-close behavior remain governed by their existing matrix cases; do not duplicate them without a distinct requirement.

Keep Hypercorn as the same-protocol oracle for ordinary H3 inputs. Mark injected endpoint/stream failures as target fault-contract results. Preserve clear separation from Uvicorn performance parity claims.

**Exit gate:** no missing H3 region remains; H3 cases are deterministic across three runs or are implemented as single-point injected scenarios with bounded timeouts.

### 7. Rust task/runtime, TLS, and module registration

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The later 447-case report passed attribution, three complete repeats, native coverage, Coverage-MCP, and normal-build exclusion after the correction; it is a historical snapshot superseded by the current 490-case report.


Cover the remaining supervisor and adapter error paths:

- `serve_forever`: join failures, listener accept failure, HTTP/3 endpoint setup, graceful drain deadline and task abort;
- TLS configuration: valid/invalid/mismatched key, QUIC conversion error, TLS accept interrupted by shutdown;
- Python task bridge: cancellation before poll, cancellation during poll, completion callback, future drop, join failure;
- `ConnectionIo`: EOF, read error, write error, flush/shutdown behavior;
- native module registration and PyO3 binding error returns.

Use real occupied-port, reset, and cancellation workflows where deterministic; use compile-gated fault points for internal errors or generated binding registration errors. A module-init error may require a separate instrumented import subprocess because no request can run before the module loads.

**Exit gate:** all remaining regions are mapped to a named workflow/failpoint and produce an externally observable result; no production test-control path is enabled.

## Current gap inventory

**The current report has zero missing native regions, lines, and unfiltered
Coverage-MCP function groups.** The 490-case report measures 5,108/5,108 regions
and 3,608/3,608 lines with passing attribution, three complete repeats, and a
matching MCP receipt in the retained
[evidence archive](../benchmarks/results/2026-10-07/famh-concurrent-load-acceptance/).
The historical 423-case report also recorded zero missing regions and zero
Coverage-MCP function groups. Its complete one-page receipt is at
`build/asgi-coverage/unified-423-final-2026-10-05/coverage-mcp-receipt.json`.
The historical tables below describe earlier source/build inventories.
For future changes, measure the new source, then use its exact region IDs and
source/build receipts to choose cases. Do not reuse historical coordinates.

## Historical Coverage-MCP function-group inventory (336-case report)

The table below is the complete 50-group inventory returned for the old
336-case report at
`build/asgi-coverage/unified-336-empty-h2-2026-10-04/coverage-report.json`.
The report records 3,801/3,937 covered regions, with 136 missing. Missing
observation counts can overlap and must not be summed to calculate that
region total. Sampled spans are bounded examples; the report retains every
uncovered region and its exact case attribution.

| Function group | Missing observations | Sampled source spans |
|---|---:|---|
| `uvicorn_rs::serve_hyper_connection::<tokio_rustls::server::TlsStream<uvicorn_rs::ConnectionIo<tokio::net::tcp::stream::TcpStream>>>::{closure#0}` | 12 | 2843:43–2843:44; 2845:13–2845:23; 2845:24–2845:30; 9 more omitted |
| `<uvicorn_rs::LifespanRuntime>::start::{closure#0}` | 11 | 1917:85–1917:86; 1958:32–1958:37; 1959:29–1959:43; 8 more omitted |
| `uvicorn_rs::serve_http3_connection::{closure#0}` | 9 | 2928:81–2928:82; 2940:13–2940:18; 2964:9–2964:17; 6 more omitted |
| `<uvicorn_rs::AsgiBody>::poll_app_task` | 8 | 2288:32–2288:49; 2297:19–2297:24; 2298:13–2298:36; 5 more omitted |
| `uvicorn_rs::serve_http3::{closure#0}` | 8 | 2869:54–2869:59; 2909:9–2909:20; 2909:21–2909:30; 5 more omitted |
| `<uvicorn_rs::LifespanRuntime>::shutdown::{closure#0}` | 6 | 2035:25–2035:30; 2035:35–2035:110; 2047:20–2047:25; 3 more omitted |
| `uvicorn_rs::serve_forever::{closure#0}::{closure#8}` | 6 | 2624:87–2624:88; 2630:87–2630:88; 2642:33–2642:39; 3 more omitted |
| `uvicorn_rs::serve_forever::{closure#0}` | 6 | 2723:9–2723:36; 2724:15–2724:42; 2724:43–2724:48; 3 more omitted |
| `uvicorn_rs::handle_http3_request::{closure#0}` | 6 | 2974:61–2974:62; 3005:18–3005:19; 3007:52–3007:53; 3 more omitted |
| `uvicorn_rs::pump_h3_request_body::{closure#0}` | 6 | 3027:13–3027:19; 3031:70–3031:76; 3040:21–3040:29; 3 more omitted |
| `uvicorn_rs::handle_websocket_request_inner::{closure#0}` | 5 | 3465:54–3465:55; 3498:43–3498:44; 3503:48–3503:49; 2 more omitted |
| `uvicorn_rs::handle_request_parts::{closure#0}` | 4 | 3254:58–3254:59; 3258:54–3258:55; 3277:54–3277:55; 1 more omitted |
| `<uvicorn_rs::PythonTaskFuture as core::ops::drop::Drop>::drop::{closure#0}` | 3 | 1030:29–1030:48; 1030:49–1030:51; 1034:17–1034:18 |
| `<uvicorn_rs::LifespanRuntime>::start::{closure#0}::{closure#5}` | 3 | 1959:49–1959:54; 1959:55–1959:60; 1959:61–1959:63 |
| `uvicorn_rs::pump_http_request_body::{closure#0}` | 3 | 2148:86–2148:92; 2177:78–2177:84; 2185:78–2185:84 |
| `uvicorn_rs::handle_request_inner::{closure#0}::{closure#0}` | 3 | 3140:30–3140:38; 3140:39–3140:44; 3140:49–3140:57 |
| `uvicorn_rs::drive_websocket::<hyper_util::rt::tokio::TokioIo<hyper::upgrade::Upgraded>>::{closure#0}` | 3 | 3672:71–3672:72; 3762:67–3762:68; 3770:9–3770:10 |
| `uvicorn_rs::cancel_python_task::{closure#0}` | 2 | 1046:13–1046:19; 1051:13–1051:19 |
| `<uvicorn_rs::AsgiIo>::receive` | 2 | 1192:79–1192:80; 1211:52–1211:62 |
| `<uvicorn_rs::AsgiIo>::receive::{closure#1}` | 2 | 1237:27–1237:31; 1246:25–1246:26 |
| `uvicorn_rs::poison_websocket_handshake_mutex::<core::option::Option<tokio::sync::oneshot::Sender<uvicorn_rs::WebSocketHandshake>>>::{closure#0}` | 2 | 1702:13–1702:14; 1703:9–1703:10 |
| `<uvicorn_rs::LifespanRuntime>::start::{closure#0}::{closure#2}` | 2 | 1893:14–1893:15; 1910:77–1910:78 |
| `<uvicorn_rs::AsgiBody as http_body::Body>::poll_frame` | 2 | 2377:21–2377:45; 2378:21–2378:38 |
| `uvicorn_rs::load_tls_configs::{closure#6}` | 2 | 2481:21–2481:42; 2481:43–2481:50 |
| `uvicorn_rs::serve_forever::{closure#0}::{closure#5}` | 2 | 2714:28–2714:33; 2714:44–2716:18 |
| `uvicorn_rs::serve_http3::{closure#0}::{closure#0}` | 2 | 2901:24–2901:29; 2901:40–2903:14 |
| `uvicorn_rs::serve_http3_connection::{closure#0}::{closure#2}` | 2 | 2956:24–2956:29; 2956:40–2958:14 |
| `uvicorn_rs::handle_request_parts::{closure#0}::{closure#1}` | 2 | 3194:10–3194:11; 3208:65–3208:66 |
| `uvicorn_rs::handle_websocket_request_inner::{closure#0}::{closure#2}` | 2 | 3434:43–3434:44; 3447:11–3447:12 |
| `uvicorn_rs::handle_websocket_request_inner::{closure#0}::{closure#3}` | 2 | 3544:32–3544:37; 3552:29–3554:22 |
| `<uvicorn_rs::ActiveHttpRequest as core::ops::drop::Drop>::drop` | 1 | 801:9–801:10 |
| `<uvicorn_rs::PythonTaskFuture as core::ops::drop::Drop>::drop` | 1 | 1039:9–1039:10 |
| `<uvicorn_rs::AsgiIo>::__pymethod_receive__` | 1 | 1169:12–1169:13 |
| `<uvicorn_rs::WebSocketIo>::__pymethod_receive__` | 1 | 1407:12–1407:13 |
| `uvicorn_rs::discard_websocket_handshake_sender::<tokio::sync::oneshot::Sender<uvicorn_rs::WebSocketHandshake>>` | 1 | 1712:9–1712:10 |
| `<uvicorn_rs::LifespanIo>::__pymethod_receive__` | 1 | 1764:12–1764:13 |
| `<uvicorn_rs::LifespanIo>::receive::{closure#0}::{closure#0}` | 1 | 1774:32–1774:50 |
| `<uvicorn_rs::LifespanIo>::receive::{closure#0}` | 1 | 1774:83–1774:84 |
| `<uvicorn_rs::LifespanRuntime>::start::{closure#0}::{closure#3}` | 1 | 1917:26–1917:44 |
| `<uvicorn_rs::ServerControl>::__pymethod_shutdown__` | 1 | 2068:12–2068:13 |
| `uvicorn_rs::wait_for_connection_close::{closure#0}` | 1 | 2195:9–2195:15 |
| `<uvicorn_rs::ConnectionIo<tokio::net::tcp::stream::TcpStream>>::poll_read_after_eof` | 1 | 2238:13–2238:32 |
| `uvicorn_rs::serve` | 1 | 2423:68–2423:69 |
| `uvicorn_rs::load_tls_configs` | 1 | 2482:10–2482:11 |
| `uvicorn_rs::serve_forever::{closure#0}::{closure#9}` | 1 | 2661:29–2661:30 |
| `uvicorn_rs::serve_connection::{closure#0}` | 1 | 2790:59–2790:65 |
| `uvicorn_rs::serve_hyper_connection::<uvicorn_rs::ConnectionIo<tokio::net::tcp::stream::TcpStream>>::{closure#0}` | 1 | 2847:23–2847:24 |
| `uvicorn_rs::handle_request_inner::{closure#0}` | 1 | 3140:58–3140:59 |
| `uvicorn_rs::build_websocket_scope` | 1 | 3799:39–3799:40 |
| `uvicorn_rs::_native` | 1 | 4068:60–4068:61 |
## Measurement and rollout gates


1. **Per-batch feedback:** add a bounded case batch, run it through the live runner, and attribute its profile to those case IDs. Compare its marginal gain against the one accepted source/build baseline, then update the single cumulative report. Preserve zero-gain cases when they expose a protocol regression or important contract; do not create parity-only and fault-only coverage baselines.
2. **Full correctness gate:** after the matrix is complete, run every oracle-backed and fault-contract row. Require selected = executed = passed, zero mismatches, zero infrastructure errors, and repeat three times on the same instrumented build. Keep verification modes on each row so the oracle denominator remains clear.
3. **Coverage gate:** the union across every passing case mode must report 100% of LLVM regions and lines for the explicitly declared source set in one report, with verified source/build/run receipts and complete case-to-region attribution. Branch coverage remains “unavailable” until the measurement format supplies branch detail; do not infer it from line/region coverage.
4. **Normal-build gate:** build without test-fault instrumentation and verify the normal server CLI/API has no faultpoint option or environment variable. Only then can this become a CI coverage gate.
5. **Documentation gate:** update [the support matrix](support-matrix.md), [coverage results](coverage.md), and [parity contract](parity.md) with the exact boundary between oracle parity and injected-fault behavior.

## Risks and honest limits

- A test-only synthetic `MemoryError` proves error propagation at the named Python C-API call boundary; it does not prove recovery from actual system-wide CPython allocator exhaustion.
- A fault-injected Rust result is not an oracle-equivalence result. Keep its verification label and result visible beside oracle cases, but aggregate all passing modes into the same source-region coverage percentage and attribution map. Do not publish separate parity-coverage and fault-coverage denominators.
- Per-case profiling must not silently omit child server processes, module-import subprocesses, or shutdown paths. Isolate profiles by case and target process, verify profile flush/completeness, and reject an aggregate whose profile union does not equal its per-case hit map.
- Coverage alone does not prove behavior quality. Each injection needs a meaningful external invariant and follow-up cleanup assertion.
- Rust-generated PyO3 glue and platform-specific error arms may not be controllable after module import. If they remain unreachable after the fault seam is implemented, report the exact residual and do not quietly exclude it.
- The current report records 5,108/5,108 native regions and 3,608/3,608 lines, with passing attribution, three complete repeats, and matching Coverage-MCP. The normal non-instrumented local build passes all public oracle cases; the installed-wheel exclusion audit applies to the prior source snapshot and must be repeated before release. Historical reports retain their own source/build scope. This does not cover optional diagnostics, every platform, the full ASGI specification, or performance. The measured checkout was dirty, so run the gates on the committed source before using it as a clean release baseline.

## Maintenance after completion

1. Keep the `input@7`/`result@3` workflow contract and one authoritative report. The generic `scenario`/`stimulus` envelope above remains a proposal, not another implemented test family.
2. Add ordinary live parity inputs for reachable behavior; add a single named fault contract for deterministic internal failures. Retain meaningful regression cases even when they add no regions.
3. Use Coverage-MCP incremental comparisons only with fixed Rust source, instrumentation, and region inventory. A changed build requires a new full measurement.
4. After source or input changes, pass every attribution case and three complete repeats. Require zero missing regions/lines, exact profile-union attribution, and attached matching MCP receipts.
5. Verify normal release builds contain no active fault control. The historical audit is referenced in its unified report; repeat it for the changed native source.
6. Repeat on clean committed source before establishing a release or hosted CI baseline. The current instrumented gate and local normal-build parity passed; repeat the installed-wheel exclusion audit. No package was published.

The historical 336-case table above preserves the earlier gap investigation.
It does not describe the current source. Future batches must retain their own
measurement identity and meaningful public outcomes.
