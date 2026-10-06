# Implementation review: known gaps

The current source passes the 473-case attribution matrix and three complete
473-case repeats with zero failures, infrastructure errors, retries or cases
not run. The matrix has 225 oracle comparisons and 248 target-only contracts
across 70 input files and 64 operations. Native coverage is 5,106/5,106 regions
and 3,606/3,606 lines, with zero Coverage MCP gaps. The normal wheel passes
225/225 public comparisons and the 16-check exclusion audit with three selected
public cases. See the [current source/build receipt](coverage.md#current-full-verification-473-cases).
The 451- and 448-case results below are historical and do not attest the
current checkout.

This page separates measured failures from risks that still need targeted
evidence.

## Latest completed historical evidence

The historical shared-write matrix declares 448 cases across 70 input files and 61 operations: 213 live
oracle comparisons and 235 target-only contracts, including two public
header-capacity contracts. The named normal build passes all 213 public cases.
That instrumented source passes 448/448 attribution and three complete
448-case repeats with zero failures, infrastructure errors, retries or cases
not run. It measures 4,763/4,763 regions and 3,360/3,360 lines with zero
unfiltered MCP gap groups, a matching source receipt and tests passed. The
same source's normal exclusion audit passes all checks and its three selected
live cases. [Coverage evidence](coverage.md#current-full-verification-448-cases)
names exact source/build identities and preserves the local dirty-checkout
scope; it does not establish a release baseline or full ASGI conformance.

## Current transport changes and performance status

`ConnectionIo` now forwards scalar/vectored writes and the underlying vectored
capability. A borrowed buffer enum uses one fallible write handler, preserving
error/disconnect handling without allocating or copying payloads. A profile of
the earlier vectored candidate observed Hyper's flattening-copy path disappear
on plaintext H1. That wall-stack observation is not a throughput or CPU gain.
The H3 accept loop treats typed H3_NO_ERROR (`0x100`) and unknown remote
application close codes as clean peer closure, as RFC 9114 requires. The
input-driven public cases cover zero, reserved GREASE `0x21`, unknown `0x111`,
and maximum u62; registered HTTP/3-family codes `0x33`, `0x101`, and `0x200`
retain the error path. All close paths retain the owned request drain. The new
cases fail against the previous native build and pass after the correction.
They do not send a QUIC transport `CONNECTION_CLOSE` frame. In the pinned
stack, `h3-quinn` maps transport `ConnectionClosed` to `Undefined`, so
transport-level `NO_ERROR` currently follows the error path. That path remains
unverified and has semantics distinct from HTTP/3 application close codes
([RFC 9000 section 20.1](https://www.rfc-editor.org/rfc/rfc9000.html#section-20.1)).
The classifier also depends on the pinned `h3` 0.0.8 display text to
distinguish remote application closes.

The task-reaping source now joins completed HTTP/3 request tasks while accepting
new requests on a long-lived connection. Its 450-case attribution passed, but
the complete repeats stopped and two final-drain regions remained uncovered.
A controlled public GREASE A/B passed the 128-response sequence and clean-close
pair only with that sequence's GREASE disabled. The new generic held-response
accept-error workflow uses an existing point and requires remote `0x102`, real
stream failure, ordered cancellation/original error, application cleanup and a
healthy fresh request. Its selected instrumented case passed 1/1 and retained
those actual outcomes; the fresh 473-case full run passes attribution and all
three repeats, including both formerly missing final-drain spans. The
`stream_reset` observation uses the client's `recv_data` error convention;
actual remote application close, body-stream error, connection closure and
cleanup prove termination/cancellation. The latest full run rebuilt
instrumentation; [current evidence](coverage.md#current-evidence-status)
records the exact identities and native scope. The normal wheel passes 225
public cases and all 16 exclusion checks with three selected live cases.

The [October 5 investigation](performance-investigation-2026-10-05.md) retains
all 120 A/B rows and identity/profile receipts. None of its 90 optimization
timings qualified, so fixed-key/value caching and one-worker Tokio remain
unaccepted. Common-method caching was only drafted. Canonical behavior keeps
two workers, event-name interning, ordinary mapping/method lookups and the
existing method uppercasing path. Fresh five-category timing with matching
automatic lifespan and visible reference ERROR logs is pending.

## Historical correctness evidence

The earlier inventory declared 447 cases across 70 input files: 212
oracle-parity cases and 235 target-only contracts, including two public capacity
support contracts in the existing fault-contract envelope. That snapshot
completed regression, native coverage and normal-build exclusion verification.
Its source passed all 447 attribution cases and three complete repeats
with zero failures, infrastructure errors, retries, or cases not run. Its
report records 4,734/4,734 native
LLVM regions and 3,333/3,333 lines (100%); unfiltered Coverage-MCP has zero gap
groups and a matching passing receipt. This is default-feature `src/lib.rs`
with `cfg(coverage)` on macOS ARM64. The preceding source's normal-build audit failed from two
inactive service-error diagnostic literals; the corrected source's normal
audit passes all checks and three selected live cases. Its complete instrumented
gate also passed independently; the extension was restored to that audited
normal build at the time. [Coverage analysis](coverage.md)
preserves the historical 423-case 100% result and the subsequent incomplete
426-case result. The historical 445-case snapshot passed attribution and measured
every Rust source region and line with zero Coverage-MCP gaps, but remained
incomplete because its third full repeat had one graceful-drain adapter failure
and eight cases not run. Its first two repeats passed 445/445. The preceding
444-case snapshot had an attribution oracle TLS WebSocket handshake timeout
despite three passing full repeats. The earlier 442-case snapshot
missed six Rust regions and four lines. None of these snapshots certifies the
subsequent header-capacity correction or its new public support contracts.
The correction passed a nine-case attribution subset followed by the preceding
complete instrumented gate. No fresh performance comparison is available.
The historical 447-case gate also covered that correction after compiled fault exclusion.

The earlier historical full correctness matrix contained 346 cases: 195
oracle-parity cases and 151 target-only fault contracts. All cases passed
attribution and three full matrix repeats with no mismatches or infrastructure
retries. The unified report records 3,826/3,943 regions and 2,665/2,726 lines;
Coverage-MCP matched the source/build receipt and inspected all 48 missing
region groups. Coverage remained below 100% for that snapshot. The complete
official ASGI
conformance corpus has not been run. This is not a security audit or evidence
that the server is ready for public deployment.

The working-tree report for that 346-case snapshot is
`build/asgi-coverage/unified-current-2026-10-05/coverage-report.json`. It was
measured on CPython 3.12.13, Rust 1.98.1, and macOS ARM64 at dirty revision
cf9bf062133721b094e914f49ed8f54c613eb30f. A clean committed-source coverage
run and a fresh quiet-host performance run remain unverified.


<a id="measured-performance-gaps"></a>

## Historical measured performance gaps

| Finding | Evidence | Current action |
|---|---|---|
| Repeated Python string conversion and scope temporaries remain a profiling question. | The October 2 sampled H1 profile shows PyString::new / PyUnicode_DecodeUTF8Stateful under AsgiIo.send, plus string conversion in PythonTaskStarter; this is a call-path clue, not percentage attribution. The current source interns event names and uses Cow<str> for plain HTTP paths. | Re-profile this exact source on a quiet host before claiming optimization gain. |
| H1 fixed-response latency and CPU are worse than Uvicorn's fastest measured configuration. | In the provisional matrix, Rust+uvloop measured 39,894 requests/s, p50 1.58 ms, and 139% server CPU; Uvicorn uvloop+httptools measured 67,882 requests/s, p50 0.81 ms, and 94% CPU. | Repeat the correctness-gated matrix on an idle host before accepting a performance conclusion. |
| Some H1 streaming workloads have higher raw rate, but lower server CPU efficiency. | Rust+uvloop measured 2,226 vs 1,748 requests/s on 256 response chunks (179% vs 88% CPU) and 5,208 vs 3,724 on small response chunks (196% vs 99% CPU). After normalizing each sample's rate by server CPU, medians were 1.22k vs 2.00k and 2.65k vs 3.78k requests/s per core. | Treat both rate and efficiency figures as provisional. Profile CPU per request and per ASGI message before changing the bridge. |
| Python-heavy H1 workloads remain behind Uvicorn. | Provisional rate ratios were 0.74× for 32-header scope, 0.51× for contextvars, 0.55× for the synchronous-callable/awaitable case, and 0.43× for exception-to-500. | Attribute task scheduling, loop notifications, PyO3 calls, and message construction on an idle fixed workload. |
| Cross-runtime streaming waits are measurable. | The queue-16 instrumented run saw about 14.9 full sends per 256-chunk response and 24–31 ms accumulated send-wait per request. The timer includes bridge scheduling as well as channel delay; instrumented throughput is not comparable to ordinary runs. | Keep ASGI send ordering and backpressure. Profile bridge wakeups and channel occupancy before considering batching. |
| Large H1 response sampled RSS remains high after owner-backed extraction. | The 1 MiB response row's median sampled peak RSS was 127 MiB for Rust and 33.9 MiB for Uvicorn. Loopback clients used several CPU cores. | Collect allocation/lifetime profiles and move large-transfer clients off-host; RSS alone does not identify retained allocations. |
| H3 fixed-response sampled RSS is high. | The Rust+uvloop row's median sampled peak was 252.3 MiB at concurrency 4; the Hypercorn reference was 89.7 MiB. All H3 rows passed correctness, but the host was busy. | Profile connection/stream and buffer lifetimes on a quiet host before treating this as a leak or stable memory requirement. |
| WebSocket text echo consumes more CPU and is slower than Uvicorn in this run. | Rust+uvloop measured 60,525 messages/s at 244% CPU; Uvicorn uvloop measured 73,207/s at 94% CPU. The 64 KiB binary echo favored Rust in rate but also used more CPU. | Profile the PyO3 message bridge and frame path separately; retain full-message parity gates. |

The [October 4 run notes](../benchmarks/results/full-2026-10-04T113122Z/run-notes.md)
link the environment, every raw category report, and process snapshots. These
are exploratory medians from a contaminated host, not accepted speedup claims.

## Listener shutdown regression and correction

The strengthened existing graceful-drain workflow exposed retained TCP
admission over both plaintext and TLS. On the native binary measured by the
444-case snapshot, Uvicorn refused new connections while its process and held
response remained active; Rust kept accepting TCP connections into its backlog
until shutdown finished. Both comparisons failed only the declared
`listener_closed_before_release` observation. Complete response bytes,
application/lifespan events, established-connection close, and process
termination matched. The defending receipt at
`build/asgi-coverage/listener-admission-before-fix-2026-10-05/parity-result.json`
records two behavioral failures and zero infrastructure failures.

The current source explicitly drops the listener after the accept loop ends
and before task drains. The runner treats only connection refusal as listener
closure: a connect timeout can come from a full backlog, and a close racing
with a connect can reset the probe. Both outcomes are retried and are not
closure proof. Both ordinary cases now observe admission for one second within their
three-second grace, require the process and held response to remain active,
then release and verify the complete response and shutdown. The listener
ownership correction passed both cases within a seven-case targeted run with
zero failures or retries:
`build/asgi-coverage/listener-ownership-targeted-445-rst-aware-2026-10-05/coverage-report.json`.
The strengthened listener cases also passed the preceding complete gate. This
change did not resolve the separate request-body-pump ownership question at
that point; the follow-up is now covered under Code and operations.

## Idle protocol-detection cancellation

The full listener-fix snapshot passed all 445 attribution cases and two complete
repeats. The third repeat completed the held plaintext response but the adapter
then rejected the global shutdown diagnostic `Cancelled`. The server log did
not identify a connection, so it did not show an active-stream failure.
Inspection of pinned `hyper-util` 0.1.20 showed that cancelling a pending HTTP
version read through `graceful_shutdown()` returns a directly boxed
`std::io::ErrorKind::Interrupted`. Established HTTP/1.1 and HTTP/2 errors are
boxed `hyper::Error` values instead.

The implemented correction classifies that direct interrupted I/O result only in
the explicit graceful-cancellation branch. Other results retain the error
channel, including the ordinary connection-result branch. The harness keeps
its error-log assertion and adds a real idle TCP/TLS connection carrying the
partial HTTP/2 preface `PRI ` before the active held stream. Shutdown must close
that connection while the active response drains normally. These are stronger
stimuli and observations in the existing two ordinary cases, with no new case
family or fault seam. Both cases deterministically reproduced the old native's
strict `Cancelled` diagnostic rejection in
`build/asgi-coverage/protocol-detection-before-fix-2026-10-05/parity-result.json`.
That defending receipt contains two adapter infrastructure failures and zero
reported behavioral mismatches; it is not two oracle comparison failures.
The adjacent `before-identity.json` records the exact old native, source,
harness, fixture, manifest, and input digests. The changed native passed all
seven targeted attribution cases, including both stronger ordinary drains,
with zero failures or retries. Both live comparisons report the idle connection
closed and retain exact response/lifecycle parity. The artifact audit at
`build/asgi-coverage/protocol-detection-before-after-audit-2026-10-05.json`
verifies unchanged harness, fixture, manifest, input, environment, and Cargo
lock identities. That targeted evidence is now historical: the follow-up full
run was interrupted after 219 attribution passes for the header-capacity issue
below. The preceding 447-case source passed its separate complete gate.

## Header-map capacity failure

The pinned `http` crate's `HeaderMap::append` panics internally when its finite
capacity is exceeded. Both the HTTP response helper and WebSocket handshake
assembly called that infallible method. Ordinary valid ASGI header collections
can reach the failure, so the authored panic/unwrap/expect lint policy alone
does not close this dependency call path.

The implemented change uses `try_append`: HTTP headers are built before response
state is committed, and WebSocket handshake assembly retains its application
task guard until construction succeeds. Capacity failure retains the
original native error and the existing public failure/cleanup behavior through
`Result`. The capacity support cases supply 32,769 distinct valid header names
through the public ASGI boundary. They are target-only declared capacity
contracts, with no native injection and no equivalence claim against Uvicorn.
The exact usable header count depends on map growth, key distribution,
duplicates, and reserved handshake headers; the internal bucket ceiling is not
a stable public accepted-count limit.

The same two public-input contracts failed before the correction and each
produced an unexpected dependency panic at `http-1.5.0/src/header/map.rs:1433`.
The runner recorded two behavioral failures and two panic-hook infrastructure
failures even though both target processes exited zero. With the corrected
native, both contracts passed within a nine-case targeted attribution run with
zero failures or retries. HTTP recovered with a small 500 response; WebSocket
returned a 500 handshake and completed application cleanup; both healthy
follow-ups returned 200. The
`build/asgi-coverage/header-capacity-before-after-audit-2026-10-05.json`
receipt verifies unchanged inputs, harness, environment, and Cargo lock while
recording both source/native identities. Both contracts also passed the preceding
historical 447-case attribution and repeats. Both also pass the historical shared-write
448-case attribution, three full repeats and selected normal-build audit.
The strict unexpected-panic
hook checks remain enabled.

## Correctness and protocol coverage

- Focused black-box probes cover HTTP, streaming, HTTP/2, HTTP/3, WebSockets,
  lifespan, cancellation, disconnect, and one optional `starlette-rs` route.
  The complete ASGI 3 / HTTP-WebSocket 2.5 / lifespan 2.0 conformance corpus has
  not been run.
- HTTP/1.0, malformed framing, request-smuggling cases, exhaustive duplicate
  header and raw-target cases, HTTP/2 extended CONNECT, WebSocket fragmentation
  and extensions, and broad HTTP/3 loss/recovery interop remain unverified or
  unsupported. See the [support matrix](support-matrix.md) for per-feature
  status.
- The HTTP/3 implementation depends on experimental `h3` APIs. The October 4
  correctness-gated matrix passed 66 comparison rows against Hypercorn for its
  represented workloads; Hypercorn upload remains excluded. This is not a
  Uvicorn comparison, and broader interoperability remains unverified.

## Code and operations

- The Rust data plane is concentrated in `src/lib.rs`. Keeping one
  module has not yet been shown to cost runtime performance, but it makes
  protocol review and change isolation harder. A module split should preserve
  behavior and be measured independently.
- The Rust/Python boundary necessarily creates Python scope and ASGI message
  objects. Incoming body data and scope bytes currently copy into Python
  `bytes`; immutable outgoing Python `bytes` remain owner-backed in Rust.
  Exact built-in ASGI event names compare against interned Python strings and
  avoid a Rust `String` allocation. Fixed scope/message keys and Python method
  lookups still use ordinary strings; HTTP methods still use the existing
  uppercasing path. Wider key/value and worker-count experiments are unaccepted,
  and common-method caching was drafted only. Plain HTTP paths retain `Cow<str>`
  and avoid an intermediate Rust allocation. No isolated speed gain is claimed.
  See the [copy ledger](architecture.md#buffer-ownership-and-copies).
- HTTP body queues are bounded by item count, not by bytes per item, and there
  is no configurable body-size limit. Deployments must account for application
  behavior and transport defaults until resource limits are designed and
  verified.
- Request-body pump ownership is implemented and covered. `ServerContext` owns
  an H1/H2/H3 body-pump `JoinSet`; each request registers its pump there before
  starting its ASGI application. Pumps select on server shutdown, connection
  closure and per-request cancellation, and completed pumps are reaped while
  new requests arrive. H1 keeps draining after the app stops receiving so
  request framing can finish on a reusable connection. H2 stream cancellation
  reaches the pump token and can surface as `http.disconnect` on the owning
  ASGI loop. H3 body errors and a closed request receiver terminate that
  stream's pump. Shutdown joins pumps within the remaining transport grace
  period; if the period expires, it logs, aborts and drains the join set before
  `Server.serve()` returns. The 473-case unified matrix passes three repeats,
  and the normal wheel passes all 225 public comparisons. The 128-request
  one-connection HTTP/3 case returns 128 matching responses in each full repeat;
  its instrumented attribution records 128 body pumps joined. These cases do not
  establish unbounded-load or indefinite-upload resource ceilings: request
  queues are bounded by item count and no body-size limit is configured.
- Rust diagnostics use fallible best-effort stderr writes; structured logging
  and configurable access logs are not implemented.
- The manifest declares Python `>=3.9`. Full public parity uses CPython
  3.12.13 on macOS ARM64; an actual installed-wheel HTTP/loop/context/lifespan
  and cancellation smoke also passes on CPython 3.9.25. Linux, Windows,
  alternate interpreters and free-threaded CPython remain unverified locally.
- No package has been published. The repository now has BSD-3-Clause/MIT
  licensing with Appunni M's copyright and retained upstream notices. Hosted
  CI and a public distribution decision are still required for release.
- The benchmark client now sends explicit `0x100`; the server also handles
  unknown peer application codes per [RFC 9114 section 8](https://www.rfc-editor.org/rfc/rfc9114.html#section-8).
  Its regression inputs retain the previously failing code-zero replay and
  add reserved, out-of-range, and maximum-varint values. Existing registered
  close codes and internal/transport errors retain their error paths. Original
  benchmark failures remain preserved; updated repeated H3 performance
  comparisons have not been measured.

## Next performance work

1. Complete the correctness-gated five-category comparison on the exact audited
   normal build with matching automatic lifespan and visible ERROR logs. Keep
   matching binaries, app, Python, client, seed, and load settings; record both
   server and client CPU and p50/p95/p99 latency.
2. If valid paired timings are neutral, mixed or unavailable, use opt-in bridge counters and fresh
   native/Python profiles to compare fixed and chunk-heavy H1 paths. Then
   collect allocation/lifetime profiles for the 1 MiB H1 and fixed H3 cases;
   RSS samples alone cannot explain retained memory.
3. Change one behavior-preserving mechanism at a time and rerun interleaved A/B
   samples against Uvicorn `uvloop + httptools`. Do not accept a throughput-only
   win if CPU or latency regresses materially.

The next benchmark must include the existing category workload names and use
the same app, client, runtime, concurrency, duration, and machine for both
servers. SIMD is a candidate only if profiles show a dominant vectorizable
byte-processing loop; it cannot remove Python-visible ASGI events.
