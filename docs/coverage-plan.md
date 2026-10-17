# Plan: unified black-box coverage for the ASGI adapter and Python-free Rust runtime

## Current acceptance status (2026-10-17)

The latest local aggregate executed all 748 ASGI/native cases and measured
8,997/8,997 executable source-span regions and 6,629/6,629 physical executable
lines. Attribution passed 748/748. All three ASGI repeats (534/534 each) and
all three native repeats (214/214 each) passed with zero failures,
infrastructure failures, retries, or unrun cases. Coverage-MCP fully
paginated the matching-source/build report, found zero missing regions or
lines, and reported `tests=passed`. The offline evidence checker independently
reconstructed the retained profiles and passed without rerunning cases.

The report is bound to dirty revision
`27de9f3ac7d259a3a9b612c3247ab2c60eb27306`, source SHA-256
`f1627a340a49b8d62d74b2630e4e3e43136461e98ab018328a9294173b332ada`, report
SHA-256
`cc83cf9928c2f8bf924ab94463b75a4d6d9d0dfb0a0830387663ef135c50c197`, and MCP
pages receipt SHA-256
`c884c4db25dee6192adb9f667b2306d8f2ca832fd0654463ea2a9a718932bc5f`.
The exact report path, instrumented extension hash, run identity, build ID,
and context receipt are recorded in [coverage status](coverage.md#current-unified-coverage-status-2026-10-17).
The remaining acceptance gate is an exact-source hosted run on the reviewed
release-candidate commit. Add cases only if that run exposes a concrete gap
or failed behavior.

## Historical full-source baseline (2026-10-15)

The latest completed full-source report for its recorded source snapshot is
`target/asgi-coverage/current-696-fault-fixes-20261015/full-report.json`.
It ran that snapshot's 696-case manifest: 511 Python ASGI and 185 Python-free
native cases. Attribution passed 696/696 with zero failures, infrastructure
failures, retries, or unrun cases. Three full ASGI repeats passed 511/511
each and three native repeats passed 185/185 each; all repeats had zero
transient infrastructure failures, and attribution matches the aggregate.

This is a historical source-bound baseline, not a full-source result for the
current worktree. The latest hosted status and current selected-case evidence
are maintained in [coverage status](coverage.md#current-unified-coverage-status-2026-10-17).

The report measures 8,123/8,288 LLVM regions and 6,094/6,215 lines. Coverage
therefore remains below the 100% gate by 165 regions and 121 lines. Coverage-MCP
fully paginated 210 region groups and 89 line groups, with matching source/build
identity and `tests=passed`; its aggregate gate remains incomplete. The exact
source/report hashes and per-file totals are in the
[unified coverage record](coverage.md#current-unified-coverage-status-2026-10-17).

The gap inventory for this snapshot used this full run rather than the earlier
689-case baseline. It identifies server-inapplicable `h3::quic` client
adapter methods separately from real request, peer-stop, response-write, and
peer-reader failure paths, and specifies the public assertions or deterministic
fault contracts required to exercise each candidate. Do not add duplicate
inputs when the existing HTTP/3 cancellation and lifecycle cases already
prove the same outcome. Keep generated reports, profiles, logs, and MCP
receipts under ignored `target/`.

### Earlier full-coverage snapshot: t6zz v6

Unified schema v7 declares 511 Python ASGI cases and 164 Python-free native
cases (675 total). The t6zz v6 exact-source report is
`target/asgi-coverage/t6zz-final-acceptance-20261015-v6/full-report.json`.
It records run ID `53b90df8098b43c0ab702742581d37ad`, source SHA-256
`edf9189996750cb42c7cbabbe7d3238556f24a40ae84fc0fad6f740f2cd8c368`, and
report SHA-256
`87949c1c2582ec68dbf15cbec6e1d5f23cb47e1981226094741b1775d2f112db`, at
revision `1bde9cee0bb89618a30c3fc01b04af183f709c7b` with a dirty worktree.

All 675/675 attribution cases passed with zero failures or retries: 243
oracle-parity, 268 ASGI fault-contract, 156 native target-contract, and 8
native fault-contract cases. Three ASGI repeats passed 511/511 each, and three
native repeats passed 164/164 each; every repeat had zero transient
infrastructure failures. Per-case attribution matches the aggregate. Normalized
LLVM source-span coverage is 7,655/7,655 regions and 5,706/5,706 lines. The source-bound
Coverage-MCP receipt reports `source=matches_receipt`, `tests=passed`, matching
build identity, and zero missing aggregate regions or lines. It contains 9
region pages, 1 line page, 163 per-function-instantiation diagnostic groups,
and zero line groups. The source-span totals are the gate; grouped rows retain
monomorphization detail.

Astra review's native execution-order mismatch and HTTP/3 delivery-barrier
findings are resolved. Strict validation passed on this fresh v6 report,
independently replaying the aggregate and all 675 isolated case profiles.
Kata `t6zz` is locally complete. This is a dirty source snapshot; a clean
committed-source run and hosted CI remain release validation.

### Implementation results

R2 and R3 were resolved with `watch::Receiver::wait_for`, removing manual
channel-closed fallback loops. R4 is exercised by
`http1.shutdown-timeout-drains-completed-connection-and-aborts-held-sibling`.
R5 moves HTTP/3 request cancellation to the connection supervisor, which aborts
and drains sibling request tasks after QUIC connection closure.

The final two error paths use narrowly scoped fault contracts with observable
recovery assertions. `fault.http1.upgrade-receiver-closed-keeps-service-healthy`
closes the upgrade receiver while the service is polling it, then verifies a
healthy follow-up request. `fault.http1.native-websocket-derived-accept-key-header-value-error-recovers`
forces the fallible derived accept-key header conversion to fail, verifies the
handshake is rejected, and checks a later request. These are coverage-build
fault contracts, not oracle parity inputs. No panic, unsafe code, or source
exclusion was added.

The HTTP/3 peer-stop shutdown case
`http3.peer-stops-critical-control-stream-then-shutdown` observes STOP_SENDING
transmission, then requires a later ACK batch with no bytes in flight and no
intervening packet loss or congestion. Its client-only observer delegates to
Quinn's default Cubic controller, and a client keepalive ensures another ACK
batch can arrive. Twenty normal-build repetitions passed, followed by the
instrumented attribution case and all three native matrix repetitions.

Keep generated reports, profiles, logs, and MCP receipts under ignored
`target/`; do not commit them. The report and detailed gap-to-case attribution
are summarized in [current unified coverage status](coverage.md#current-unified-coverage-status-2026-10-17).

The manifest includes
`native.lifecycle-http3-startup-error-prevents-serving`: an input-driven H3
startup failure case that verifies the listener does not begin serving when
the application startup hook fails. It passed in the full 633-case diagnostic
as well as its selected unified run at
`target/asgi-coverage/2026-10-13-h3-lifecycle-startup-selected/coverage-report.json`.

The current manifest also includes active TCP/TLS HTTP/1 upgrade-registration
cases and lifecycle-enabled WebSocket handshake/message cases over TCP and
TLS. The two lifecycle/WebSocket cases passed together in the selected report
`target/asgi-coverage/2026-10-13-lifecycle-websocket-selected/coverage-report.json`.
Focused reports do not close the full-source coverage gate.

An earlier complete-scope report before the shutdown and upgrade changes is
`target/asgi-coverage/2026-10-14-current-595-single/coverage-report.json`.
It covers the then-current 511 ASGI and 84 native cases, all passing once with
complete attribution and no case or infrastructure failures. It measured
6,900/6,960 regions and 5,061/5,093 lines. Coverage-MCP retrieved all 111
region groups and 30 line groups with `source=matches_receipt`; it reported
`tests=failed` because that older report had 60 region and 32 line gaps. This is
an incomplete historical diagnostic, not a coverage pass.

After that report, the redundant per-connection graceful-shutdown timer was
removed; its existing held-response case passed in a focused run. The native
manifest gained four HTTP/1 upgrade-session cases covering a successful
handoff/drain, handler error, unavailable upgrade, and registration after
connection close. They passed 4/4 in one selected unified run at
`target/asgi-coverage/2026-10-13-native-upgrade-contracts-refactor/coverage-report.json`;
the selected result has 673/7,072 regions, 550/5,177 lines, and complete case
attribution. Its source SHA-256 is
`2c3558737f2f4643c4848b3c0d0438a1f245dcf1b4d2835b65b0282cfbaf0a3f`. The exact
report's uncovered-region list had no `ConnectionUpgrade` function symbols,
while a matching-source Coverage-MCP query returned five groups for that API.
Those groups describe function instantiations rather than the union of source
spans. Schema v7 makes the distinction explicit and independently reconstructs
the aggregate and per-case source-span hit sets from retained profiles. These
selected reports are historical; current totals and repeat results appear at
the top of this page.

The HTTP/3 request-body source was then measured with the selected case
`http3.empty-request-body-is-consumed-through-eof` in
`target/asgi-coverage/current-http3-empty-body-eof-refactor/coverage-report.json`.
The input passed 1/1 with complete attribution and no retries. That selected
measurement had an executable denominator of 6,957 regions and 5,088 lines;
the selected case covered 683 regions and 601 lines, so it is not aggregate
coverage evidence.
The edit removed a `data_finished` state that could not persist across a poll:
`poll_recv_data(None)` immediately polls trailers; when trailers are pending,
the body returns `Pending` and polls data again on the next call. The empty-body
input separately verifies the public request-body EOF and size-hint behavior.
The existing `http3.empty-data-frame-does-not-end-request-body` case also
passed 1/1 after the edit, preserving the empty-DATA-then-later-DATA behavior.
The historical 629-case matrix ran once with one infrastructure failure and
59 region / 34 line gaps. It predates the historical 633-case report above.
That snapshot did not establish three complete repeats or zero-gap acceptance.

The initial four native HTTP/1.1 WebSocket inputs passed in a selected unified
run at `target/asgi-coverage/2026-10-13-native-websocket-h1-final/coverage-report.json`.
They cover text/binary and Ping/Pong exchange, close handling, shutdown, a
malformed key, and an unoffered subprotocol. The report has complete
attribution, but is not aggregate coverage evidence.

The expanded 12-case native HTTP/1.1 WebSocket selection passed 12/12 in one
unified run at
`target/asgi-coverage/2026-10-13-native-websocket-handshake-expansion/coverage-report.json`.
The new cases exercise a non-GET method, wrong WebSocket version, a decoded key
of the wrong size, a missing `Connection: Upgrade` token, an empty offered
subprotocol token, reserved response-header rejection, single-use
subprotocol selection, and preservation of an application response header.
Per-case region attribution is complete, with no case failures, retries, or
infrastructure failures. The report records 868/7,384 regions and 699/5,420
lines for this selected subset and is not aggregate coverage evidence. HTTP/2
and HTTP/3 WebSockets, TLS WebSockets, and Python ASGI mapping remain open.

The RFC-reviewed 13-case HTTP/1.1 WebSocket selection passed 13/13 in one
unified run at
`target/asgi-coverage/2026-10-13-native-websocket-rfc-contract-final/coverage-report.json`.
It adds a wrong `Upgrade` token rejection, requires the unsupported-version
response to advertise `Sec-WebSocket-Version: 13`, and checks the required
`Upgrade: websocket` and `Connection: Upgrade` response headers on successful
handshakes. These checks follow [RFC 6455 §4.2.2](https://www.rfc-editor.org/rfc/rfc6455#section-4.2.2)
and [§4.4](https://www.rfc-editor.org/rfc/rfc6455#section-4.4). Per-case
attribution is complete, with zero failed cases, infrastructure failures, or
transient retries. The selected run records 868/7,384 regions and 699/5,420
lines; its source SHA-256 is
`37901559958c25922e123eab1a080ec353b63654431416099ffc54eb82a5eeb1`. The
report is selected-subset evidence; the aggregate 100% gate remains open.

The latest selected report is
`target/asgi-coverage/current-http1-graceful-timeout-consolidated/coverage-report.json`.
The existing native case
`http1.graceful-shutdown-timeout-aborts-held-response` passed 1/1 after server
task-error handling was consolidated. Coverage-MCP matched the report receipt
and passed the case result; its focused region query at
`crates/uvicorn-rs/src/lib.rs:1086` returned zero gap groups. The report covers
498/6,960 regions and 410/5,093 lines for this selected run, not the aggregate.
The change shares cancellation classification between ordinary connection
joins and abort draining while retaining the distinct error log messages. It
was captured from the working tree immediately before commit `b3abb4e3a`; the
receipt records `dirty=true` and binds the exact source files.

The two focused native cases for a peer close during HTTP/3 connection
creation passed together in
`target/asgi-coverage/current-h3-init-close-final/coverage-report.json` with no
retry or infrastructure failure. The selected report is useful for its input
and source attribution; it does not establish aggregate coverage. The next
work is to classify remaining gaps by concrete public behavior and add only
input-driven cases or named fault contracts that exercise those behaviors.
The new
`http3.lifecycle-shutdown-bounds-pending-handshake` case passed 1/1 without a
retry in
`target/asgi-coverage/current-http3-pending-handshake-shutdown-final/coverage-report.json`.
The client verifier remains blocked until the server returns
`GracefulShutdownTimedOut`; lifecycle shutdown completes, and the peer is then
released and joined. Coverage-MCP reports `source: matches_receipt` and
`tests: passed`; the concrete lifecycle specialization has no missing regions
at the endpoint-idle shutdown path. This selected case does not establish the
full matrix or aggregate coverage.
Do not add cases for uninstantiated generic placeholders or private
implementation lines. At that stage the matrix had passed once, but three
repeats, 100% regions and lines, and fully paginated Coverage-MCP acceptance
were outstanding. Schema v4 retained function-instantiation-aware region IDs,
indexed `hit_by` attribution, per-profile hashes, independent LLVM replay,
exact artifact checks, and fully paginated MCP row identity. Python line and
branch coverage remain outside the Rust denominator.

The added native case
`http3.response-cancel-before-finish-keeps-connection-usable` passed once with
complete attribution and no retries or infrastructure failures. It exercises
the empty response body after headers, QUIC `STOP_SENDING`, body release, error
observation, and same-connection recovery in both harness apps. Its selected
report remains Git-ignored at
`target/asgi-coverage/current-http3-response-cancel-before-finish/coverage-report.json`.
The attribution map selects concrete function instantiations with positive
counts for `http3.rs:489-491`, while the raw LLVM export also contains a
zero-count generic `handle_http3_request::<_, _>` row at that span. The
focused Coverage-MCP region query returned the generic row as one missing
group; its line query at 491 returned zero missing groups. The raw line
segment at 491 is a boundary (`hasCount=false`), and line 492 has an execution
count. These results refer to different generic and concrete instantiations;
the report's `hit_by` attribution does not cover every raw instantiation. Do
not add a synthetic input just to reach the generic placeholder. The selected
report is not aggregate evidence.

The case reaches the response-send path through both `ContractApp` and
`LifecycleApp`, but its observer checks only for some connection-phase error.
It does not identify `finish().await` or its result, so this is indirect
evidence for the finish path.

## Original goal and case-model decision

The goal is 100% measured Rust source coverage for the audited production source while retaining the manifest-backed live parity matrix. The case-model decision permits declared fault-contract workflows alongside oracle-backed inputs in the same runner and report. The request to implement `t6zz` superseded the earlier documentation-only investigation. Two explicit coverage-build fault contracts now exercise the defensive receiver-closure and derived-header conversion errors, with public recovery assertions. Their ownership and input-invariant proofs remain in Kata `pmnm` and `z2gq`; no natural wire input is claimed for those paths. See [current acceptance status](#current-acceptance-status-2026-10-17).

Ordinary cases compare live wire behavior against the pinned Uvicorn or Hypercorn oracle. A Rust-only injected failure has no equivalent stimulus in those servers, so it must be labeled as a fault-contract case, never reported as Uvicorn parity. Both modes feed the same source/build coverage union and case-to-region attribution report. Verification mode remains visible as case metadata; it does not split the coverage denominator or create a second coverage ledger. Only the behavioral parity pass rate is scoped to oracle-backed cases.

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

The JSON below is a historical schema sketch, not the current report schema.
The current runner, evidence checker, and Coverage-MCP receipt attacher use
`uvicorn-rs-coverage/unified@8`. Region attribution uses the exact source span
across Rust monomorphizations, so an input that executes a region in one
generic instantiation is not reported as a gap merely because another
instantiation is LLVM's maximum-summary representative. Physical line totals
are the unique executable source lines from LLVM LCOV `DA` records. The runner
requires the LCOV line set and hit-line set to match the corresponding union
of executable region spans exactly. The standard LLVM file/aggregate summaries
and `coverage.summary` use this normalized source basis. The original LLVM
file and aggregate summaries remain in `coverage.source_files[].llvm_summary`
and `coverage.llvm_summary`; raw LLVM function-instantiation counters remain
in the function rows. `coverage.line_validation` records the per-file counts
used to confirm the line/span match.

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
`input@8`, `result@4`, and one unified coverage extension. Cases identify a
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

## Original workstreams and case plan (historical)

The numbered workstreams below preserve the implementation plan and candidate
cases from earlier measurements. They are historical planning material, not
a live source-coverage backlog. Review the [historical gap inventory](coverage-current-gaps-2026-10-15.md)
for the remaining measured gaps and verification work. Full source coverage
does not establish full protocol or ASGI conformance.

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
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.

Before adding failpoints, use true client inputs for any uncovered behavior that can happen on a real deployment. The matrix at that snapshot covered H1 malformed-final-chunk disconnect, incomplete-upload reset, early-response drain and response-stream reset; H2 partial-upload reset/cancellation and a healthy sibling stream; and H3 body errors, close/cancellation handling and follow-up health. Its H3 one-connection sequence served 128 requests with 128 request-body pumps joined in each of three full repeats. Remaining candidates must first be reconciled against existing cases and named requirements:

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
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.


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
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.


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
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.


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
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.


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
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.

The historical zero-length HTTP/3 DATA-frame investigation encountered a
Hypercorn timeout and the pinned `h3` receive API treating an empty frame as
`None`. The empty-chunk consumer path is now covered by
`fault.http3.body-pump-empty-data-frame-preserves-upload`, which injects one
empty chunk at the receive boundary and checks the subsequent real upload.
That target-only result does not establish wire-level empty-frame
interoperability; an independent wire client is still needed for that claim.


The 2026-10-11 506-case report is a historical source snapshot. Its body-pump
slice covers request-body errors, cancellation/close selectors, disconnect
delivery, bounded pump joining, and same-connection follow-up behavior. The
2026-10-12 unified v4 563-case inventory now supersedes its source-coverage result for the
recorded PyO3 source, but does not close the separate wire-level questions:
test raw H3 request-stream reset and response-write failure where a real client
can trigger them. Use a named target fault contract only when a client cannot
select the internal error deterministically. Existing cases already govern
invalid ASGI responses and endpoint/connection-close behavior; add no duplicate
case without a distinct requirement.

Keep Hypercorn as the same-protocol oracle for ordinary H3 inputs. Mark injected endpoint/stream failures as target fault-contract results. Preserve clear separation from Uvicorn performance parity claims.

**Exit gate:** no missing H3 region remains; H3 cases are deterministic across three runs or are implemented as single-point injected scenarios with bounded timeouts.

### 7. Historical candidate list: Rust task/runtime, TLS, and module registration

**Historical status (423-case source/build): complete for that measured
region inventory.** Its three full repeats passed with no region or line gaps.
The 447- and 506-case reports are historical source snapshots. At the time, the 2026-10-12 unified v4 563-case inventory superseded those
source-coverage results. The 2026-10-15 report supersedes that historical
snapshot; see [latest evidence](coverage.md#current-unified-coverage-status-2026-10-17).
Normal-build parity and fault-control exclusion remain unverified for this
exact source.


This candidate list predates the latest 675-case report and is not an
instruction to add cases. The full current source-span inventory is covered;
use [current unified coverage status](coverage.md#current-unified-coverage-status-2026-10-17)
before proposing any further coverage change. The following list is retained
as historical planning context only:

- `serve_forever`: join failures, listener accept failure, HTTP/3 endpoint setup, graceful drain deadline and task abort;
- TLS configuration: valid/invalid/mismatched key, QUIC conversion error, TLS accept interrupted by shutdown;
- Python task bridge: cancellation before poll, cancellation during poll, completion callback, future drop, join failure;
- `ConnectionIo`: EOF, read error, write error, flush/shutdown behavior;
- native module registration and PyO3 binding error returns.

## Historical gap inventory (2026-10-12 report)

The source-bound gap map for this historical snapshot was attached to the full report at
`target/asgi-coverage/2026-10-12-tls-shutdown-v3/coverage-report.json`; its
fully paginated raw MCP receipt is
`target/asgi-coverage/2026-10-12-tls-shutdown-v3/coverage-mcp-pages.json`.
Coverage-MCP found 122 region-gap groups and 64 line-gap groups, and the report
retains all 115 uncovered regions with per-case attribution. The remaining
region and line gaps are concentrated in `crates/uvicorn-rs/src/lib.rs` and
`crates/uvicorn-rs/src/http3.rs`; `src/lib.rs` has no uncovered regions or
lines. The largest sampled region groups are in HTTP/3 serving and connection
handling, listener acceptance, request handling, and lifecycle futures.

Use the report's exact spans and MCP group samples to inspect each candidate.
The counts in function groups can overlap and do not add up to the number of
missing regions. Preserve test cases that have zero marginal coverage if they
assert useful regression behavior. Do not combine profiles across source or
manifest changes or reuse historical coordinates. See [current coverage
status](coverage.md#current-unified-coverage-status-2026-10-17) for the exact
source, report, and build identities.

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
- The 5,561-region report is historical adapter-only evidence for `src/lib.rs`; it does not cover the current four-executable-file denominator. The t6zz v6 schema-v7 snapshot in [the unified coverage record](coverage.md#current-unified-coverage-status-2026-10-17) passed 675-case attribution, three repeats of each matrix, full source-region and line coverage, the source-bound Coverage-MCP receipt, and strict offline profile replay. It predates the current native transport edits; only a 35-case selected run has been rerun so far. Clean committed-source and hosted release checks remain separate.

## Maintenance after completion

1. Keep the `input@8`/`result@4` workflow contract and one authoritative report. The generic `scenario`/`stimulus` envelope above remains a proposal, not another implemented test family.
2. Add ordinary live parity inputs for reachable behavior; add a single named fault contract for deterministic internal failures. Retain meaningful regression cases even when they add no regions.
3. Use Coverage-MCP incremental comparisons only with fixed Rust source, instrumentation, and region inventory. A changed build requires a new full measurement.
4. After source or input changes, pass every attribution case and three complete repeats. Require zero missing regions/lines, exact profile-union attribution, and attached matching MCP receipts.
5. Verify normal release builds contain no active fault control. The historical audit is referenced in its unified report; repeat it for the changed native source.
6. The local exact-source gate is complete. Repeat on clean committed source and run hosted CI before establishing a release baseline. No package was published.

The historical 336-case table above preserves the earlier gap investigation.
It does not describe the current source. Future batches must retain their own
measurement identity and meaningful public outcomes.
