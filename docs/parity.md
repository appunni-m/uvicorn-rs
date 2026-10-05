# ASGI server parity suite

The HTTP/3 task-reaping source passes all 451 instrumented attribution cases
and three complete repeats with zero failures, infrastructure errors, retries
or cases not run. The matrix has 214 oracle comparisons and 237 target-only
contracts across 70 input files and 63 operations. Native coverage is
4,778/4,778 regions and 3,371/3,371 lines with zero unfiltered MCP gaps.
The restored normal build passes 214/214 public comparisons and all 15
exclusion checks with three selected live cases. See
[the current source/build receipt](coverage.md#current-full-verification-451-cases).
Passing 448-case results below belong to the earlier shared-write source
identified in [the coverage record](coverage.md#current-full-verification-448-cases);
they do not attest the changed checkout.

## Correctness gate

The behavior gate is the manifest-backed, live source/target matrix, not a unit
test count. The live matrix observes the server boundary by starting real
reference and target server processes and replaying the same indexed network
workflows against each.

This follows the fixture-matrix approach used by `image-slash-star`/Pillow-RS,
adapted to a network server. Pillow-RS compares Rust operations with pinned
oracle fixtures; this server compares wire-visible behavior with a live,
version-pinned ASGI server because sockets, protocol state, streaming, and
lifecycle are part of the contract. Inputs contain stimuli only, not expected
responses. The Python contract checks validate the matrix and evidence format;
they are not substitutes for the live behavior comparisons.

The historical shared-write inventory contains 448 workflows across 70 input files and 61
operations: 213 oracle-parity cases and 235 target-only contracts in the
fault-contract envelope.
Of the latter, 233 select internal/client fault paths and two declare public
header-capacity behavior without native injection. Additions
cover shallow lifespan-state copying without rehashing keys, post-response
application shutdown, inline Python completion callbacks, eager-task
asynchronous cleanup, original task-setup exceptions, fallible native runtime
construction, a real non-DATA HTTP/3 response frame, and TLS response drain
after listener admission closes during shutdown. The existing plaintext/TLS
drain cases also hold an idle connection with the partial HTTP/2 preface `PRI `
and require that connection to close while the active response completes.
The historical shared-write denominator for claims of oracle parity is 213; fault
contracts are target-only. **The historical shared-write source's instrumented full regression,
coverage, and normal-build exclusion verification passed.** All 448 attribution
cases and three complete 448-case repeats pass with zero failures,
infrastructure errors, retries or cases not run. The report records
4,763/4,763 native LLVM regions and 3,360/3,360 lines; unfiltered Coverage-MCP has zero gap groups and a matching, passing
source receipt. The scope is default-feature `src/lib.rs` with `cfg(coverage)`
on macOS ARM64. The same source's normal build independently passes 213/213
public oracle comparisons, every exclusion check and three selected live cases:
one HTTP oracle comparison and both public capacity support contracts.
No unit tests were added; these cases use the same black-box workflow matrix.
The [historical shared-write receipt](coverage.md#current-full-verification-448-cases)
preserves matching source/native artifacts and links the normal audit and
defending evidence. That normal build was restored at the time of its audit.

The added `http3.peer-close-h3-no-error` case uses the ordinary
`http3.peer-close` workflow and request field `close_error_code: 256`
(`0x100`). The validator accepts explicit integer u62 wire codes only for
HTTP/3 completed ordinary requests. The workflow verifies exact response
bytes, a healthy request on a fresh connection, a scoped connection-error
diagnostic observation and graceful owned-process exit. It starts fresh
profile processes so earlier connection logs cannot contaminate its diagnostic
window. This field controls the test client; it is not a server CLI option.
Only typed `H3_NO_ERROR` is treated as clean close; numeric QUIC application
code `0` and other errors retain their existing classification.

## Current HTTP/3 workflows

`http3.sequential-responses-one-connection` sends 128 POST requests through
one connection and compares every response with live Hypercorn. Its maintained
input explicitly sets `h3_grease: false`. A controlled instrumented comparison
with `http3.peer-close-h3-no-error` passed both cases with GREASE disabled;
the enabled arm timed out receiving headers for the first reference request.
The selected pair also enables full-profile HTTPS readiness after lifespan
startup and public reference ERROR logging. The input controls the client,
defaults to `true` when omitted, and adds no server option. See the
[current source-bound evidence](coverage.md#current-evidence-status).

The target-only `http3.request-task-drain-on-accept-error` operation starts
`/stream-cancel-until-reset` and receives a real status-200 `first/` body chunk.
After the client barrier and the application's held-response event, the runner
arms the existing `http3.connection.accept-error` point and releases a second
request on that same connection. That request completes the pending unarmed
accept so the following accept can consume the fault. The first stream remains
owned until an actual remote application close is observed.

Its structured contract requires an incomplete first response with exactly
`first/`, a real body-stream error and remote close code `0x102`, consumption of
the point, request-task cancellation diagnostics before the original accept
error, exactly one application cancellation-cleanup event before follow-up,
no panic, and a healthy status-200 fresh request without reset. Actual body,
close code, stream error, trigger error, events and scoped server logs are
retained in `target_observation`. Missing barriers, client timeouts or local
closure fail execution; different actual outcomes fail the contract. The
original `fault.http3.connection-accept-error` first-accept case remains intact.
This new workflow passed its selected instrumented case (1/1), with actual
remote code 258, two cancelled-task join diagnostics before the original accept
error, the held/cancelled application events and a healthy fresh follow-up.
The [selected receipt](coverage.md#current-evidence-status) preserves its rich
observation and identities. The same case passes full attribution and all three
451-case repeats, and solely covers both formerly missing final-drain spans.
The `stream_reset` field follows the existing `recv_data` error convention;
actual remote application close `0x102`, `body_stream_error`,
`connection_closed` and cleanup establish connection-error termination and
cancellation. They do not independently identify a QUIC `RESET_STREAM` frame.

## Historical correctness evidence

The previous 447-case source independently passed attribution, three full
repeats, 4,734/4,734 regions, 3,333/3,333 lines and its corrected normal-build
exclusion audit. The later 448-case generic-helper snapshot passed all cases
and aggregate coverage but retained seven MCP function observations. Both
remain source-bound historical records in [coverage evidence](coverage.md);
their profiles do not certify the current source.

Seven attribution cases passed on the source before the header-capacity
correction, with zero failures or retries,
including the two strengthened plaintext/TLS drain cases. Both now match live
Uvicorn and report `idle_connection_closed: true`. The artifact audit verifies
that the before/after pairs used the same runner, fixture, manifest, inputs,
environment, and Cargo lock. The two old outcomes were strict diagnostic
adapter failures; the new outcomes are passing ordinary parity comparisons.
The follow-up full run stopped after 219 passing attribution cases when a
reachable capacity panic was found; it has no complete gate. Those profiles
retain their original source identity and cannot be merged with the corrected
source. See [coverage results](coverage.md) for the historical receipts.

Target-only capacity contracts are declared for valid ASGI response and
WebSocket acceptance headers that exceed the compiled Rust header-map
capacity. They use ordinary public input and the existing target-only envelope,
with harness-owned `public.*` identifiers and no native injection control.
They are declared support contracts, not Uvicorn parity or a new test kind.
Both passed on the corrected native within a nine-case attribution subset
with zero failures or retries. The same two inputs failed before the fix and
triggered two unexpected dependency panic hooks, independently rejected even
with zero target exit codes. The corrected source also passed the complete
preceding 447-case instrumented gate; see [the historical full receipt](coverage.md#historical-full-verification-447-cases-before-normal-build-exclusion-correction)
and [before/after audit](coverage.md#historical-targeted-verification-9-cases-fallible-header-assembly).

The historical 445-case snapshot passed every attribution case and measured all
4,719 Rust regions and 3,329 lines with zero Coverage-MCP gaps. Two full repeats
passed 445/445. The third recorded 436 passes, one adapter infrastructure
failure, and eight cases not run, with zero reported behavioral mismatches.
The plaintext graceful-drain adapter rejected a global `Cancelled` connection
diagnostic after the stream had completed. Its gate remained incomplete and
Coverage-MCP retained `tests: failed`. The strengthened idle-connection inputs
and cancellation correction passed the later historical 447-case full gate.

The preceding 444-case snapshot measured all 4,717 Rust regions and 3,328 lines,
with zero Coverage-MCP gaps, but its complete gate was incomplete: attribution
had 443 passes and one live Uvicorn TLS WebSocket handshake timeout. Each of
three full repeats passed 444/444 with zero mismatches or infrastructure
failures. Coverage-MCP retained `tests: failed`; the passing repetitions do
not replace the missing passing attribution case.

The preceding 442-case snapshot passed attribution and three complete
matrix repeats with zero behavioral or infrastructure failures and no retries:
211 oracle-parity cases and 231 target-only fault contracts. Its unified report
still missed six LLVM regions and four lines. The subsequent lifespan guard
changes and two new fault cases produced the later 444-case snapshot. The
listener ownership fix and strengthened shutdown observations then required a
new gate; the preceding 447-case report supplies that evidence without merging
older profiles.

The historical 423-case source/build passed per-case attribution and three
complete matrix runs, with zero behavior mismatches, infrastructure failures,
or transient retries. Its unified report recorded 100% default native Rust
region and line coverage. That receipt predates the ownership and panic-policy
refactor and does not certify the changed source or stricter panic validator.
See [coverage results](coverage.md) for configuration and source/build receipts.
The subsequent 426-case measurement was incomplete: per-case attribution
recorded 425 passes and one infrastructure failure; each full repeat recorded
426 behavioral passes and one infrastructure failure. Five Rust regions and
one line remained uncovered. The current runner repairs the unused-reference
shutdown-cancellation issue. The preceding 447-case source/build passed its own
complete instrumented gate.
When a supported behavior changes, add a mapped input case and update the
support matrix.

The parity runner starts the reference server and `uvicorn-rs` as separate
processes, imports the same ASGI app in each, sends the same input workflows,
and compares their live public observations. It does not contain golden
responses. This is a version-pinned, scoped compatibility check; passing it
does not establish complete ASGI conformance or full Uvicorn compatibility.

## Run it

Build the local extension and sync the pinned reference-server dependencies,
then execute the live parity input set:

```sh
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
uv run --group benchmark python scripts/run_parity.py
```

The default run selects oracle-parity rows. To include the compile-gated
fault-contract workflows in the same result envelope, first build the
instrumented extension and pass `--fault-contracts`:

```sh
uv run --python 3.12 --group benchmark python scripts/build_coverage_extension.py
uv run --python 3.12 --group benchmark python scripts/run_parity.py --fault-contracts
```

Fault contracts use the same workflow schema, server process, observations,
and coverage report. Their result records `verification: fault-contract`,
the allow-listed point, and `oracle_observation: null`. The historical 235
fault-contract cases cover HTTP, WebSocket, HTTP/2, HTTP/3, lifespan, server
startup, and native binding error paths. Their specific contracts verify
observable failure handling and cleanup; they are not oracle-equivalence cases.
The two `support.*` header-capacity rows use harness-only `public.*` selectors
and ordinary valid ASGI input. They do not write a native fault-control file.
They declare the target's finite-capacity rejection and recovery contract in
the same result envelope, and remain outside the oracle-parity denominator.

Production Rust errors propagate through `Result`/`PyResult`. Task-unwind and
mutex-poisoning contracts use the instrumented build's `coverage_panic` helper,
which is absent from production builds. The runner checks every Rust panic-hook
event against the exact source, message, and count expected for that process's
attempted fault cases. Extra, missing, or unexpected events fail verification.
This check runs independently of process-exit validation: an expected injected
panic does not excuse a nonzero exit or waive the declared shutdown policy.
An unexpected panic-hook event also fails verification when the process exits
successfully.

The default generated evidence file is `build/asgi-parity/result.json`. Choose
another destination with `--output PATH`; for example, save a reviewable run in
`benchmarks/results/`. The command fails if any manifest-pinned server or
protocol component differs, an adapter cannot start, a protocol client fails,
an observation differs, or a case is malformed. Every selected case appears
exactly once in the result, including cases marked `not_run` after an
infrastructure failure. Results include the per-input and manifest digests,
reference dependency versions, target checkout revision, native extension and
Cargo lock digests, parity runner and app-fixture digests, the HTTP/3 client
binary digest, individual observations, and selected/executed/passed/failed/
not-run counts. A dirty checkout is recorded as such; it is not release
evidence.

HTTP/2 and HTTP/3 cases build a small Rust HTTP/3 client and generate a
short-lived local certificate with OpenSSL. CI exercises all declared profiles.

## Oracle selection

| Profile group | Cases | Reference | Why |
|---|---:|---|---|
| HTTP/1.1, including TLS | 88 | Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0 | Same protocol and measured fast Uvicorn stack; includes HTTP parsing, ASGI events, streaming, disconnect, and WebSocket-upgrade validation. |
| WebSocket, including TLS | 41 | Uvicorn 0.54.0, uvloop 0.23.0, websockets 17.1 | Same HTTP/1.1 upgrade path, message flow, rejection, disconnect, and shutdown cases. |
| Startup configuration | 9 | Uvicorn 0.54.0 and the public `uvicorn_rs.Server` API | Same invalid-host and TLS startup configurations on both implementations. |
| Lifespan and shutdown | 34 | Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0 | Covers lifespan event/error shapes, shallow state copies, cancellation, listener closure before held-response release over plaintext/TLS, and Rust's public Server.serve() cancellation path. |
| HTTP/2 | 20 | Hypercorn 0.18.0, uvloop 0.23.0, h2 4.4.1, TLS ALPN, explicit ASGI mode | Uvicorn does not provide an HTTP/2 server profile. Includes empty final DATA, concurrent streams, reset, and final-response completion. |
| HTTP/3 | 22 | Hypercorn 0.18.0, aioquic 1.3.0, QUIC, explicit ASGI mode | Uvicorn does not provide an HTTP/3 server profile. Includes the 128-response sequence, explicit typed H3 clean close and a fresh connection afterward. |

The H2/H3 rows are same-protocol ASGI observations against Hypercorn. They are
not described as Uvicorn parity. Server versions and protocol components are
exact requirements in `tests/parity/manifest.json`; a version mismatch
invalidates a run rather than silently changing the oracle. The result also
records the exact Python/runtime versions and native-extension/Cargo-lock
digests for the target.

## Scope and comparison rules

The active manifest and input schema are `uvicorn-rs-parity/manifest@2` and
`uvicorn-rs-parity/input@7`; live artifacts use
`uvicorn-rs-parity/result@4`. This result revision records the Rust source digest
alongside the imported native digest; earlier archived reports retain their
original schema and identities.

`tests/parity/manifest.json` indexes input-only case files under
`tests/parity/inputs/`; a file can hold multiple cases for one profile. Inputs
contain request methods, paths, headers, body bytes, WebSocket messages,
disconnect workflows, and shutdown workflows. They do not contain expected
responses or previously captured server output. The
fixture app is shared source code imported in fresh, independent oracle and
target processes. Its exported ASGI callable is synchronous and returns an
awaitable. The Uvicorn adapter forces `--interface asgi3`; the Hypercorn
adapter uses its `asgi:` selector. Both then execute the same callable under
the ASGI 3 contract. The profile split keeps protocol-specific stimulus easy
to review; the runner also checks the indexed-file set against the files on
disk.
The previous combined input is retained in `tests/parity/archive/` because an
older result artifact records its digest.

The current cases cover:

- plaintext and TLS graceful shutdown that observes refused new connections
  while the process and held response remain active, then releases the response
  and checks its complete bytes, application events, and clean connection close;
  an idle connection carrying a partial HTTP/2 preface must also close without
  causing a transport-failure diagnostic;

- HTTP scope observations, query/header/body transport, status and response
  content type;
- invalid ASGI event and missing `response.start` handling over HTTP/2 and
  HTTP/3, including the empty HTTP/3 500 body matched to Hypercorn;
- a synchronous ASGI callable returning an awaitable, exercised by the HTTP/1.1
  live parity case;
- ordered response streaming and streamed request-body echo;
- H1/H2 response delivery before the app sends its final body event, and a
  response chunk delivered before the client finishes its upload;
- an HTTP/3 response completed while the client keeps a partial POST upload open;
- an application exception and an application-generated 404;
- the ASGI `http.disconnect` event after an incomplete HTTP/1.1 upload;
- WebSocket subprotocol selection, text and binary echo, and pre-accept denial;
- lifespan startup state, shutdown, and cancellation of an in-flight request;
- HTTP version reporting and body behavior over HTTP/1.1, HTTP/2, and HTTP/3.

The runner compares status, the application `content-type` response header,
and response bytes. `date` and server-identification headers are excluded by
declared policy because they identify the implementation/runtime. WebSocket
handshake status, negotiated subprotocol, and ordered text/binary messages are
compared. Lifecycle observations include the HTTP state response, process
termination, and ordered events recorded by the test app. The raw exit code is
retained diagnostically but is not required to match: Uvicorn re-raises its
handled signal after graceful cleanup, while `uvicorn-rs` exits normally after
cleanup. Traceback formatting is not
a wire-level API; application-error parity compares its public HTTP status and
body, while the existing focused bridge probe checks that the Python exception
is logged.

The `http3.upload-body-shorter-than-content-length` input deliberately violates
HTTP message framing. Its `http3.invalid-content-length-status` operation
compares only the response status because the reference server does not produce
a stable response body for this malformed request. The case does not claim
body parity or general malformed-framing compatibility.

The progressive streaming workflows use a fixture-app completion marker and
interleave upload and response reads. They prove that a response chunk arrived
while the application response was still open and that uploads can continue
after the first response chunk. Exact TCP read boundaries are intentionally
not compared: protocol implementations may merge or split network frames
without changing ASGI semantics. Backpressure timing,
malformed framing, broad request-security corpora, and the full ASGI test suite
remain separate work; see the [support matrix](support-matrix.md).

## Extending the inputs

Add a new case only when it maps to a declared operation and profile. Keep the
case input-only: do not put captured reference responses in the manifest or
inputs. Operations may declare positive contract invariants, such as a
completed shutdown or a response delivered before the application returns.
Both live implementations must satisfy those invariants as well as agree on
their observations. Target-only fault predicates belong in the runner and
must check public failure, cleanup, or follow-up behavior.
The adapter compares live outputs and stores any mismatches in the generated
result. Add a new oracle profile only for a protocol the current oracle cannot
serve, and state why that server is a valid same-protocol reference. Update the
support matrix when a new behavior is covered, and keep unsupported or
unmeasured cases explicit.

The input loader rejects unknown fields, unsupported schemas, duplicate case
IDs, unindexed files, undeclared profiles/operations, invalid body encodings,
unrepresented declared operations, and observed output fields embedded in
active cases. The runner validates these fail-closed properties before starting
servers and verifies that result accounting cannot omit a selected case. It
selects adapters by declared profile and workflow shape, never by case ID.

## CI evidence

Main CI executes the complete public matrix on an installed normal wheel and
retains its structured result, log, consumer check and normal-build exclusion
audit as `uvicorn-rs-public-parity` for 90 days, including failed runs. A concise
annotation identifies each failing case or infrastructure error.

The separate unified native report retains individual case attribution and
three full repeats as `uvicorn-rs-unified-coverage`. The Linux candidate wheel
also runs the complete public matrix on the exact shipping binary. The
evidence checker verifies current source, native, input and harness identities;
tag assembly requires clean receipts from successful CI on the exact commit.
The former Python unit-test module has been removed; maintained verification
uses these live workflows and evidence contracts. See [release gates](releases.md)
for platform scope and the separate Coverage-MCP review.
