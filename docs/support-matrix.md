# ASGI support matrix

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

## Product boundary

The chosen architecture makes `uvicorn-rs` the Rust-native server and keeps
Python support in thin compatibility clients: `uvicorn-rs-py`,
`starlette-rs-py`, and `fastapi-rs-py`. The Rust-native FastAPI-RS →
Starlette-RS → Uvicorn-RS path does not load Python. The Python ASGI path uses
`uvicorn-rs-py` and necessarily calls Python application code through the
ASGI boundary.

The workspace packages the PyO3 extension as `uvicorn-rs-py` and the
Python-free Tower server as `uvicorn-rs`. The default `native-tcp` build routes
HTTP/1.1, HTTP/2 over TCP/TLS, and HTTP/3 over Quinn through the Rust server
crate. Python ASGI callables, event conversion, and the asyncio loop remain at
the Python/PyO3 boundary. The default `native-tcp` feature is the supported
deployment path. `--no-default-features` retains a legacy protocol path for
migration diagnostics and is compile-checked, but it is not live-parity,
coverage, or benchmark tested and is not a supported deployment configuration.
Python compatibility matrices across supported Python and upstream
framework/server versions are not implemented yet. The old Python
distribution name, import path, Cargo shape, and CLI are not backward-
compatibility requirements.

The planned Python compatibility surfaces have separate scopes. `uvicorn-rs-py`
will publish Python/runtime and standard ASGI support, plus exact upstream
Uvicorn versions for any integration it implements. That does not imply full
Uvicorn CLI/API compatibility; those behaviors require their own explicit
claims and cases. `starlette-rs-py` and `fastapi-rs-py` will publish tested
Python framework combinations for Starlette and FastAPI respectively. A passing
generic ASGI test does not itself establish framework-version support, and no
full Cartesian product of versions is implied. Uvicorn versions used only as
parity oracles are not automatically supported API versions.

### Current verified coverage and open review (2026-10-17)

The latest completed hosted coverage run
[39020268579](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579)
on commit `aa4c93836f5e2147462837bbd8b1bde6c0ebe84e` passed all 749 indexed
cases: 535 Python ASGI cases and 214 Python-free native Rust cases. Attribution
and three repeats of each matrix passed with zero failures, retries, or
unrun cases. The report measured 9,004/9,004 executable source-span regions
and 6,636/6,636 normalized physical executable lines. Its Coverage-MCP status
is still `awaiting_query`; see the
[coverage record](coverage.md#current-unified-coverage-status-2026-10-17).
Current committed main is `76379e2d64abc33e01827a9f160223e761858779`. Its
exact-head CI run
[39026041176](https://github.com/appunni-m/uvicorn-rs/actions/runs/39026041176)
has not started its jobs yet. Older run 39024130047 passed unified coverage on
`77e1f425`, including the newer H3 cancellation input. Its report is not an
exact-current-head result. These results establish the named live inputs only;
they do not imply complete Uvicorn CLI or API compatibility.

### Previous local 748-case aggregate (2026-10-17)

The local full-source aggregate executed all 748 manifest cases: 534
Python ASGI cases and 214 Python-free native cases. Three repeats of each
matrix passed, and coverage measured 100% executable source-span and
normalized physical-line coverage. The aggregate is marked incomplete because
one WebSocket TLS attribution attempt had a transient infrastructure failure
before a passing retry; a separate clean single-case rerun then passed. Its
fully paginated Coverage-MCP receipt matches source/build and reports zero
missing regions or lines, while recording the aggregate test status as failed.
The report is bound to a dirty worktree; it is not clean hosted release
evidence. The then-latest clean hosted run,
[38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888),
passed its older 712-case manifest but measured 8,496/8,650 regions and
6,486/6,592 lines, leaving 154 regions and 106 lines uncovered. It did not
describe the 748-case local snapshot discussed in this historical section.
These results describe tested
inputs and are not a claim of complete Uvicorn compatibility.

The exact report, source identity, MCP receipt, and clean-candidate gate for
that prior local aggregate
are recorded in the [unified coverage record](coverage.md#current-unified-coverage-status-2026-10-17).
The [2026-10-15 gap inventory](coverage-current-gaps-2026-10-15.md) describes
an earlier source snapshot and is historical guidance only. Generated reports
remain Git-ignored.

The 2026-10-12 dirty macOS ARM64 adapter-only receipt is historical: it verifies
its recorded root `src/lib.rs` hash, but covers neither the native workspace
sources nor a clean hosted release. At the time of this historical note, the
default `native-tcp` path had been exercised by the then-current source-bound
unified matrix, which included the Python ASGI and Python-free native cases.
That 748-case dirty-worktree
aggregate measured 100% of its executable regions and normalized lines, but
is marked incomplete after one attribution infrastructure failure before a
passing retry. It is not clean hosted release evidence. A narrower
candidate-wheel smoke passed on the current source; its per-run receipt is
Git-ignored.
The Python-free
`uvicorn-rs` crate currently has a 214-case live contract manifest covering
cleartext HTTP/1.1, cleartext HTTP/2 prior knowledge, TLS HTTP/1.1 and HTTP/2,
HTTP/3 over a caller-configured Quinn endpoint, and selected native HTTP/1.1
WebSocket handshakes and sessions. The historical 36-case
snapshot passed three sequential local repeats (108/108) on macOS ARM64; source
and input hashes are recorded in the local request-lifetime receipt, which is
Git-ignored; the historical contract and its limits are summarized here.
That receipt does not cover the current 214-case manifest. The current HTTP/3
service-panic recovery case passed its selected live run 1/1: it returns an
empty 500 before response commitment and keeps the same QUIC connection usable
for a recovery request. The current unified coverage status records its focused
result and remaining acceptance gates in [the coverage record](coverage.md#current-unified-coverage-status-2026-10-17).
The new HTTP/3 readiness-panic contract returns an empty 500 with a typed
readiness diagnostic and verifies recovery on the same connection. A new
HTTP/1 upgrade-handler panic contract verifies session termination, healthy
listener recovery, and bounded shutdown; that join failure is logged through
tracing. Both passed in an eight-case selected run with neighboring recovery
contracts. The deliberate panics are confined to the excluded example harness.
That selected result does not qualify its then-130-case native manifest or
the current 748-case unified coverage gate.
The native error policy now defaults to an empty 500 and optionally propagates
the original readiness/service error to the protocol driver. Six new live
inputs verify pre-header H1 connection termination or H2/H3 stream reset,
original typed diagnostics, recovery, and bounded shutdown. A default H3 service
error control and nine neighboring controls bring the selected pass to 16/16.
Changing only the policy to the default makes each propagation case fail its
abort/reset assertion. These policy-specific inputs exercise the native
service API. The default Python ASGI build uses the same native transport with
`ServiceErrorPolicy::Propagate`; the ASGI matrix separately exercises the
Python bridge and its error behavior. See the
[selected policy record](coverage.md#selected-native-service-error-policy-evidence).
The TCP `PeerReadHalfClosed` extension observes actual raw EOF, including below
TLS, and returns a typed unavailable result if observation ends without EOF.
The selected default `OnRead` EOF contracts and controls pass 18/18. They
verify response delivery after peer write-half closure, observation after
response completion, HTTP/2 reset remaining distinct from TCP EOF, and no TCP
extension on HTTP/3. They do not prove prompt notification during a held HTTP/1
service in the default mode. See the
[selected EOF record](coverage.md#historical-selected-native-tcp-eof-evidence).
The `Proactive` mode uses one raw reader future in the connection task and a
bounded input queue (two 16 KiB queued chunks plus one consumer chunk). The
Python ASGI adapter selects this mode for HTTP/1.1 and HTTP/2 TCP/TLS. Its cases
hold a service until raw EOF for bodyless and complete uploads over cleartext
and TLS, preserve incomplete-body errors, distinguish raw TCP FIN from TLS
`close_notify`, and map the documented peer terminations to ASGI
`http.disconnect`. The held-service case passed individually on the current
build; the broader source-bound report is dirty-worktree evidence, not a hosted
release result. Proactive mode adds one input copy; its paired performance
measurement remains open.
The HTTP/3 response-cancel cases now require the held service/body to drop
before release and then verify a recovery request on the same QUIC connection.
This tests Quinn `STOP_SENDING` while application readiness, service, or
response-body work is pending. Normal response completion is not treated as
peer cancellation. These cases exercise the Python-free native crate's HTTP/3
service API. The default Python ASGI build also delegates HTTP/3 transport to
that crate, but these native-only cases do not exercise Python event conversion
or the ASGI bridge on HTTP/3.
The 35-case instrumented selection passed all three HTTP/3 cancellation
inputs, 13 HTTP/1.1 raw-EOF inputs, 18 HTTP/3 request/transport regressions,
and a WebSocket close-receive cancellation contract. The ordinary build passed
the 33 target-contract inputs; HTTP/3 admission-closed and WebSocket
close-reply cancellation fault contracts run only under coverage
instrumentation. This is selected evidence and does not close the current
748-case unified coverage gate.
The current set includes an H2 stream-reset lifetime observation, a
synchronized H1 peer write-half-close case that completes the held response
while the connection-lifetime handle remains open, and 13 native HTTP/1.1
WebSocket cases. An earlier focused cleartext selection passed 13/13 with
complete per-case attribution and zero case failures, infrastructure failures,
transient infrastructure failures, or retries. Its historical report,
`target/asgi-coverage/2026-10-13-native-websocket-rfc-contract-final/coverage-report.json`,
records 868/7,384 regions and 699/5,420 lines for the selected run's executable
source set. It predates the last complete 628-case report and is selected-scope
evidence, not current aggregate coverage or an RFC 6455 conformance result.
Its Coverage-MCP follow-up matched the source
receipt and reported `tests: passed`, with 32 missing region groups and 17
missing line groups in `crates/uvicorn-rs/src/websocket.rs`. Keep-alive
upgrade-session and lifecycle-WebSocket inputs passed in their applicable full
or selected runs. The latest full-source status is summarized above. The last
639-case full report passed once on source that predates the current refactor.
Acceptance still requires three complete repeats, 100% region and line coverage, and
fully paginated zero-gap Coverage-MCP results. These cases do not complete the
full handshake inventory. Native TLS, HTTP/2, and HTTP/3 WebSockets, mapping
this transport to ASGI, and framework-native WebSocket integration remain
open.
The earlier 34-case package-promotion run is historical; its generated
per-run receipt is Git-ignored.
The seven HTTP/3 cases in that historical receipt cover QUIC/TLS/ALPN metadata,
streamed request bodies and trailers, response trailers, early response
streaming, a finite slow-reader backpressure/cancellation workload, and
graceful drain. Seven lifecycle cases exercise start-before-request ordering,
draining an active response before shutdown, startup and shutdown errors,
phase-specific hook timeouts, timeout cancellation, and typed error sources
across H1, H2, and H3. This prototype provides native framework hooks; it is not
ASGI lifespan protocol support or framework integration. The new native
`RequestLifetime` and `ConnectionLifetime` handles have one live H2 reset
contract: it observes `ServiceFutureDropped`, verifies the connection remains
open, serves a recovery request on that connection, and then observes
connection closure. The generic reason does not distinguish peer reset,
connection failure, or server cancellation and does not establish ASGI
`http.disconnect`. A target-only public input contract verifies that response-
side `STOP_SENDING` after request-body completion reaches a pending ASGI
`receive()` as `http.disconnect`, while a same-connection follow-up remains
healthy. Hypercorn 0.18.0 did not complete this same input with a disconnect
event, so the ASGI specification governs this case and the input is not counted
as oracle parity. A separate H3 held-app case verifies cancellation when no
receive is pending. Tracked HTTP/1 upgrade sessions remain an open
transport-consolidation gate. The opt-in error
observer preserves typed readiness, service, and committed response-body
causes with peer metadata; TLS cases verify
negotiated ALPN bytes in request extensions. This is separate from and not
covered by the ASGI matrix, and does not claim full RFC 9114 conformance. See
[the current unified coverage status](coverage.md#current-unified-coverage-status-2026-10-17),
[the Rust-native core row below](#supported-behaviors), and [latest hosted status](benchmark-status.md).

The project targets the ASGI 3 callable interface and implements a documented
subset of HTTP/WebSocket sub-specification 2.5 and lifespan 2.0. It implements
HTTP/1.1, HTTP/2, and experimental HTTP/3. The [ASGI behavior inventory](asgi-case-inventory.md)
maps declared behaviors to input case IDs and records known deviations and
unsupported extensions.
The historical shared-write inventory declares 448 cases across 70 input files and 61
operations: 213 live oracle-parity cases and 235 target-only contracts. Two of the target-only rows
declare public header-capacity behavior without native injection. **Historical shared-write
regression, native coverage, and normal-build exclusion verification are
complete for the named source/build.** All 448 attribution cases and three
complete 448-case repeats pass with zero failures, infrastructure errors, retries, or cases not run. The
historical report records 4,763/4,763 native LLVM regions and 3,360/3,360 lines
(100%); unfiltered Coverage-MCP has zero gap groups and a matching passing
source receipt. The scope is default-feature `src/lib.rs` with `cfg(coverage)`
on macOS ARM64. The corrected source passes every normal-build exclusion check
and three selected live cases: one HTTP oracle comparison and the two public
capacity support contracts. Its normal build independently passes all 213
public comparisons. That normal build was restored at the time of its audit.
See the [historical source/build and archive](coverage.md#historical-full-verification-448-cases-shared-write-source).

## Historical evidence

The earlier 447-case source measured 4,734/4,734 regions and 3,333/3,333
lines, passed attribution and three full repeats, and passed its corrected
normal exclusion audit. The subsequent 448-case generic-helper snapshot
measured aggregate 4,758/4,758 regions and 3,358/3,358 lines but retained seven
MCP function observations. Neither snapshot is the current denominator.

The preceding source passed all 447 attribution cases and three complete
447-case repeats with zero failures, infrastructure errors, retries, or cases
not run. Its instrumented report records 4,732/4,732 LLVM regions and 3,332/3,332 lines
(100%) with zero unfiltered Coverage-MCP gap groups, a matching source receipt,
and tests passed. This is default-feature `src/lib.rs` with `cfg(coverage)` on
macOS ARM64. Its first normal-build audit failed because two inactive fault
diagnostic literals remained; the corrected source passed a separate fresh
instrumented gate. The previous exact source/native and failed
normal audit are preserved.

The historical 445-case snapshot measured 4,719/4,719 Rust regions and 3,329/3,329
lines with zero Coverage-MCP gaps and passed all attribution cases. Two full
repeats passed 445/445; the third had 436 passes, one graceful-drain adapter
infrastructure failure, and eight cases not run. The gate remained incomplete
and MCP retained `tests: failed`. The idle-connection shutdown stimulus and
protocol-detection cancellation correction passed a targeted subset. Its
follow-up full run was interrupted after 219 attribution passes for reachable
header-map capacity panics; fallible header handling and public target-capacity
contracts required fresh source verification, supplied by the preceding report.
Fallible header handling passed a new nine-case attribution subset with zero
failures or retries, including both public capacity contracts. Its complete
447-case instrumented gate subsequently passed. The exclusion correction now
passes its normal audit and its separate full instrumented gate.
The preceding 444-case snapshot measured 4,717/4,717 Rust regions and 3,328/3,328
lines with zero Coverage-MCP gaps, but its full gate was incomplete: 443
attribution cases passed and one Uvicorn TLS WebSocket handshake timed out.
All three full repeats passed 444/444 with zero failures. Coverage-MCP retained
`tests: failed`. The listener ownership fix and strengthened plaintext/TLS
shutdown observations passed the preceding full report.
The historical 423-case matrix contained 208 oracle-parity cases and 215
separately labeled target-only fault contracts. All passed attribution and
three full repeats with no mismatches, infrastructure failures, or retries.
Its Coverage-MCP receipt verified 4,356/4,356 Rust regions and 3,060/3,060 lines
(100%) for that default native source/build. The preceding 447-case report independently
measures production panic removal, application ownership changes, and stricter
panic-hook validation; older profiles were not merged into it.
The preceding 426-case report was incomplete: 4,378/4,383 Rust regions and
3,071/3,072 lines were covered, per-case attribution had 425 passes and one
infrastructure failure, and each of three full repeats had 426 behavioral
passes and one infrastructure failure. Its unused-reference cancellation
issue was repaired before the later measurements.
The evidence below combines the declared matrix with clearly dated earlier
probes and benchmarks. Optional diagnostics, Python code, dependencies, other
feature combinations, and other platforms are outside the Rust denominator.
Dirty-working-tree evidence does not establish complete
Uvicorn compatibility or full ASGI conformance. See the [parity contract](parity.md),
[coverage analysis](coverage.md), and [feasibility report](feasibility.md).

## Supported behaviors

| Area | Status and live evidence | Limits |
|---|---|---|
| Rust-native server crate | **Current Python-free uvicorn-rs library.** It accepts generic Tower services over http request/response types and http_body::Body payloads. The shared native-app-contract crate adds optional startup/shutdown hooks without a runtime dependency. The current native manifest declares 214 live contract cases covering cleartext H1/H2, TLS H1/H2, and H3 over caller-configured Quinn; the current post-format report passed all 214 native cases in each of three repeats, but the aggregate is incomplete after one ASGI attribution infrastructure retry and comes from a dirty worktree. It is not hosted release evidence. The earlier 36-case receipt is historical and does not verify this manifest. The native request and connection lifetime handles now have one H2 reset contract: observe ServiceFutureDropped, confirm connection survival, recover on the same connection, then observe connection closure. The H1 half-close case holds a streamed response until the bodyless request is dispatched and the client shuts down its write side; the response completes with the connection-lifetime handle still open. Hyper HTTP/1 `half_close(true)` is enabled; the observed response-lifetime case is consistent with [the note in RFC 9112 §9.6](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.6), not the server-initiated staged teardown described there. Four earlier selected HTTP/1.1 upgrade-session inputs passed 4/4: successful handoff and drain, session-handler error observation, rejected registration without an available upgrade, and registration rejection after connection close. Two additional current-source cases exercise active registration over TCP and TLS and error-source propagation. A new keep-alive input sends two ordinary requests on one connection, verifies both responses, and exercises multiple failed upgrade sessions during connection teardown. Two cases exercise lifecycle-enabled WebSocket handshake, message exchange, and shutdown over TCP and TLS. A selected H3 lifecycle startup-failure input verifies that the QUIC listener does not serve before startup succeeds. These finite target-only contracts do not establish full protocol or WebSocket conformance. Seven H3 inputs cover QUIC/TLS/ALPN metadata, streamed request bodies and request trailers, response trailers, early streaming, bounded slow-reader flow control with producer cancellation, and graceful drain. An archived FastAPI-native composition run recorded 17 real-socket inputs
and three repeats (51/51) on an earlier dirty, path-linked sibling snapshot,
including H1/H2 request-body progress before upload completion. Its generated
receipt is Git-ignored and is not current composition evidence. The current [native composition example](../examples/native-fastapi-contracts/README.md) targets `fastapi-rs::native` in the sole FastAPI crate and passed 17 H1/H2 socket inputs once from clean detached checkouts at the revisions recorded in [composition evidence](native-fastapi-composition.md). The latest dedicated [hosted composition job](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888/job/116848350492) also passed these 17 inputs once, with a PyO3-free integrated dependency graph. Its parent workflow failed the separate unified 100% coverage gate, so this is not an all-green release result. | These are target-only service contracts, not Python FastAPI/ASGI parity or full protocol conformance. ServiceFutureDropped does not identify peer reset versus connection failure or server cancellation, and does not prove ASGI http.disconnect. The H1 input proves only the recorded half-close/response-lifetime behavior, not broad HTTP/1 conformance. The native lifecycle hook is not ASGI lifespan and is not yet consumed by Starlette-RS/FastAPI-RS. Native WebSocket TLS/H2/H3, composed TLS/H3, repeated composition, Python FastAPI parity, package release, and performance remain open. The hosted composition job is a one-time H1/H2 result from its recorded pinned revisions, not proof for the current dirty source or the full failed workflow. With the default `native-tcp` feature, the Python ASGI adapter delegates HTTP/1.1, HTTP/2 over TCP/TLS, and HTTP/3 over Quinn to this library; builds without that feature retain the legacy protocol implementation. The ASGI event bridge remains Python-backed. The current H3 adapter discards request trailer frames; ASGI 2.5 defines a response-trailers extension but no request-trailers event. The Python adapter therefore exposes request body bytes only, while the native Rust service preserves H3 trailer frames. H3 idle-reset delivery remains open. The HTTP/1.1 `ConnectionUpgrade` API now registers and drains application-owned upgrade sessions; a focused input verifies that lifecycle. The selected 13-case cleartext HTTP/1.1 WebSocket subset passes with per-case attribution, but the full handshake inventory, native TLS/H2/H3 WebSockets, ASGI mapping, and framework-native WebSocket integration remain open; H3 cases do not establish full RFC 9114 conformance or broad interoperability. Caller-supplied TLS/QUIC configuration and declared slow-reader bounds are limited to the cases; they are not performance or general memory-cap claims. See ADR 0003 and ADR 0004. |
| ASGI callable and Python loop | **Targeted cases pass.** Async apps, a synchronous callable returning an awaitable, execution on the loop that called `Server.serve()`, caller `ContextVar`, and standard event names carried by a `str` subclass are covered by [the HTTP probe](../scripts/probe_http.py) and HTTP/1.1 cases. Both asyncio and uvloop were measured. | Full protocol parity uses CPython 3.12.13. An installed-wheel HTTP/loop/context/lifespan/cancellation smoke also passes on CPython 3.9.25; this is not full Python-version parity. Other event loops and nested context/task combinations are unverified. |
| Context and exceptions | **Targeted cases pass.** Caller context crosses the boundary; an app exception produces HTTP 500 and retains the Python traceback. The exception benchmark checks 200 responses per sample at one in-flight request. | Exception benchmark samples are capped, short fixed-count runs. Exceptions at every ASGI message boundary and under concurrency are not covered. |
| Response completion and background work | **HTTP/1.1 and HTTP/2 live parity cases pass the historical shared-write full matrix.** The final ASGI body completes the response before application return, and the application's finite background work finishes afterward. The adapter transfers the application to a tracked observer when it emits the final frame. A target-only late native task-panic case checks response preservation and error logging. | Throughput and latency effects need a fresh benchmark. |
| HTTP/1.1 | **Implemented and exercised.** The probe checks request scope, upload, response status/body, exceptions, streaming, disconnect, and send-after-disconnect. The legacy ASGI probe benchmark defines 11 standard workloads plus two optional upstream FastAPI workloads when `fastapi-benchmark` is installed. This is a different harness from the maintained stock-FastAPI category benchmark, which covers 15 FastAPI workloads across routes, request bodies, and response streams. The October 4 historical run measured 11 available workloads across four configurations and three repetitions (132 rows); it predates the FastAPI workloads. FastAPI cases use upstream FastAPI, Starlette, and Pydantic, and do not use FastAPI-RS or Starlette-RS. | HTTP/1.0 scope and host synthesis have targeted parity cases; broader HTTP/1.0 behavior is unverified. Request-smuggling/security suites, malformed framing, and the complete HTTP edge-case inventory have not been run. |
| HTTP/2 | **Implemented; selected black-box cases pass, while the latest full category run remains unresolved.** TLS ALPN and cleartext h2c prior knowledge report `http_version == "2"`. A historical five-repetition full H2 category matrix recorded 140/140 correct rows across protocol scope, fixed response, 1 MiB response, many response chunks, 1 MiB upload, 64 KiB upload in 1 KiB pieces, and rate-paced slow-reader cases. In the latest multi-system run [38828500975](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975), all three H2 category jobs stopped after successful response checks and clean shutdown while logging a generic connection error. Subsequent focused hosted diagnostics passed five correctness repetitions each: Linux x86-64 `protocol-scope` ([run 38863229176](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176), four valid timing samples), Linux ARM64 `protocol-scope` ([run 38863847199](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863847199)), and macOS ARM64 `request-upload` ([run 38864179333](https://github.com/appunni-m/uvicorn-rs/actions/runs/38864179333)). The generic error did not recur. These target-only diagnostics have no paired Hypercorn result and do not establish comparative performance or resolve the intermittent full-matrix failure. A 32-stream synchronized slow-reader parity case also passes four rounds. | h2c upgrade is unverified. Extended CONNECT WebSockets are unsupported. Higher stream counts, packet loss, and broad flow-control stress remain untested. Hypercorn 0.18.0 is the same-protocol performance baseline because Uvicorn does not support HTTP/2. |
| HTTP/3 | **Experimental; targeted protocol/parity cases pass.** An archived October 4 66-row comparison checked responses against Hypercorn for its recorded inputs. Its metadata says non-upload requests carried a one-byte body, including ordinary GET workloads; those results are superseded and do not establish RFC-aligned GET correctness or comparable performance. Current ordinary GET workloads are bodyless; the consumed-request workload uses POST. Public cases verify an HTTP/3 response while a partial POST upload remains open, typed H3_NO_ERROR (`0x100`), unknown remote application close codes (zero, reserved GREASE, an unknown code, and maximum u62), and registered HTTP/3-family application codes. Unknown application codes follow the RFC 9114 clean-close behavior; registered codes retain their error path. | Hypercorn 0.18.0 upload cases remain excluded because its upload path failed earlier correctness gates. This comparison is not against Uvicorn, which has no H3 server. H3 uses experimental Rust dependencies. QUIC transport `CONNECTION_CLOSE` behavior is unverified; loss/recovery and broad interoperability remain open. The malformed short `Content-Length` case is a robustness/reference observation: it records the oracle's status only. [RFC 9114 §4.1.2](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.1.2) classifies a content-length mismatch as malformed and requires a detected malformed request/response to be treated as a stream error of type `H3_MESSAGE_ERROR`; the observed status is not a normative expectation and must not force parity. [RFC 9110 §9.3.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.1) says GET content has no generally defined semantics and a client SHOULD NOT generate it absent prior agreement. Response-body behavior for invalid framing remains outside the compatibility claim. WebSockets over HTTP/3 are unsupported. |
| HTTP/3 task ownership | **Historical 2026-10-12 adapter-only evidence:** the 511-case instrumented gate passed. It includes the held-response accept-error contract with remote `0x102` application-close termination, incomplete body, ordered cancellation/error diagnostics, application cleanup and a healthy fresh connection. The 128-request one-connection sequence passes all three repeats; instrumented attribution records 128 completed request-body pumps joined. A 16-stream slow-reader case passes three rounds with response fingerprints and resource checks. Clean and registered peer-close cases pass too. | The held-response injection is target-only and excluded from the normal build. The probe's `stream_reset` is a `recv_data` error convention and does not alone identify a QUIC `RESET_STREAM` frame. Higher stream counts, loss/recovery, and broad interoperability remain unverified. This local dirty-tree receipt is not hosted release evidence. See [current unified coverage status](coverage.md#current-unified-coverage-status-2026-10-17) and [workflow contracts](parity.md#current-http3-workflows). |
| Oracle-parity cases | **Historical 2026-10-12 adapter-only evidence:** the dirty-source instrumented matrix passed 243/243 oracle cases in attribution and each of three full repeats. The synchronous callable/awaitable, caller loop, context, HTTP, WebSocket, lifespan, protocol, concurrent load, and shutdown cases are represented by that matrix. H1, WebSockets, and lifecycle use Uvicorn 0.54.0; H2/H3 use Hypercorn 0.18.0 because Uvicorn has no matching server modes. See the [suite contract](parity.md) and [coverage results](coverage.md). | This is not a separate normal-extension parity run or a hosted clean-commit result. The 268 target-only contracts are not oracle parity; they include public-input support contracts as well as native fault cases. This does not provide the official full ASGI suite, a complete protocol security corpus, or Uvicorn CLI compatibility. |
| Response header order | **Known narrow ASGI deviation, measured by the three input-driven response-header cases.** H1/H2 observations record the wire sequence and show that the target groups fields by name while retaining each name's values in input order. The H3 probe parses fields through `http::HeaderMap`, so it does not establish raw wire order. The focused per-run receipt is Git-ignored. | ASGI HTTP 2.5 says response header order must be preserved. The current Python adapter does not preserve order across distinct field names on H1/H2. RFC 9110 §5.3 says order across different field names is not significant to HTTP semantics, while same-name value order is significant. This is HTTP-semantically valid but is not full ASGI response-order conformance. The documented contract preserves repeated values' per-name order; cross-name order is unspecified. See [RFC 9110 §5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3), the [ASGI HTTP specification](https://asgi.readthedocs.io/en/latest/specs/www.html), and the [behavior inventory](asgi-case-inventory.md#known-gaps-and-unsupported-surface). |
| HTTP scope and multiplexing | **Targeted cases pass on H1, H2, and H3.** The negotiated protocol version is checked; H2 clients multiplex requests over four TLS connections, and H3 clients multiplex over up to four QUIC connections. New input cases cover ordered duplicate fields on H1, duplicate fields and cookies on H2/H3, encoded path/query bytes, and matching custom `Host`/`:authority` values. | This is a focused scope inventory, not a complete pseudo-header or request-target corpus. H2/H3 combine repeated Cookie fields as `name=value; name=value` for oracle comparison, as allowed by ASGI. The H2/H3 clients and concurrency differ by transport; compare results within each protocol. |
| WebSocket scope | **Plain and TLS HTTP/1.1 cases pass against Uvicorn.** The fixture observes type, ASGI version, scheme, path, raw path, query bytes, headers, client/server, offered subprotocols, state, and disconnect/close details. The matrix also verifies that an empty `Sec-WebSocket-Protocol` list member is rejected with HTTP 400 before ASGI app dispatch. | The scope matrix does not cover every malformed handshake or optional WebSocket extension. WebSockets over HTTP/2 and HTTP/3 are unsupported. |
| Request streaming | **Passes the current uvicorn-rs-py black-box matrix on H1/H2/H3.** H1 cases verify incremental upload, incomplete-upload disconnect, early-response drain, and malformed final-chunk disconnect. H2 cases verify http.disconnect after complete and partial upload resets while a sibling stream remains healthy. H3 cases verify early response with an open upload, body-stream errors, cancellation and follow-up health. H1/H2/H3 performance workloads consume 1 MiB uploads; H1 and H2 also measure 64 KiB uploads in 1 KiB pieces. | ASGI disconnect results are specific to the existing PyO3 ASGI path. The separate native Tower API now exposes a generic request-lifetime end reason, and its H2 input observes service-future drop plus sibling connection survival; it does not identify the drop cause or prove ASGI http.disconnect. The H3 error-stop contract is target-only; this does not claim full QUIC reset-frame parity or exhaustive disconnect races under load. Request queues are bounded by item count, but no body-size or global byte limit is provided. This acceptance adds no new cap because the fixed workloads do not establish a safe general limit; any cap needs a separate compatibility decision and parity cases. Rust body chunks are copied into Python bytes when constructing ASGI events. |
| Response streaming and backpressure | **Passes targeted cases.** The H1 streaming probe checks ordered chunks and that response data arrives before the upload is closed. H1/H2/H3 benchmark cases include large and multi-chunk responses. Maintained H1/H2/H3 slow-reader benchmarks are cumulatively byte-paced at 4 MiB/s per connection; earlier raw timings remain historical. New synchronized H1/H2/H3 load cases compare body lengths and SHA-256 fingerprints while concurrent slow readers run, and require zero active app tasks and healthy follow-up requests. Immutable Python `bytes` response chunks are extracted as owner-backed Rust `Bytes`, avoiding a payload copy at that boundary. | The load cases are fixed concurrency and do not establish throughput or latency gains. The separate historical H1 streaming probe uses a 1 ms delay per read event; that probe is not the maintained byte-paced benchmark. Each chunk still crosses the Python ASGI boundary. |
| WebSockets | **HTTP/1.1 Upgrade implemented.** The live probe covers valid and malformed handshake keys/versions, empty subprotocol-list rejection before app dispatch, subprotocol negotiation, text/binary echo, pre-accept denial, disconnect, and shutdown cancellation. The latest five-repetition benchmark report records 60/60 correct rows across fresh handshakes, 32-byte text echo, and 64 KiB binary echo. A new 16-session echo load case compares message fingerprints across four slow-reader rounds and checks follow-up health and resource stability. | The handshake benchmark is a fixed 500 handshakes per sample at concurrency 1 to keep client ephemeral-port use bounded. The load case is not a throughput benchmark. Fragmentation, compression/extensions, malformed data frames, and extended CONNECT are untested or unsupported. |
| Disconnect and cancellation | **Targeted cases pass.** H1 disconnect receives and send-after-disconnect behavior, H2 response-stream reset cancellation, H3 client abort, and cleartext/TLS shutdown are checked. The new zero-grace lifecycle case resets 16 active HTTP/1.1 response clients and observes cancellation of all 16 ASGI tasks. Target-only cases cover repeated receives after H2 connection EOF and failures scheduling Python cancellation, with bounded shutdown and logged errors. | This does not cover every cancellation race under load or identical interrupted-transfer cases across each protocol. |
| CLI and deployment | **The current dirty-source macOS ARM64 `uvicorn-rs-py` 0.1.0 candidate wheel passed the installed consumer smoke:** module help, the installed `uvicorn-rs-py` console script, HTTP/lifespan/context/cancellation, TLS 1.3 with ALPN, and SIGTERM during a held request. The request was cancelled, lifespan shutdown completed, and the process exited within the 5 s bound. The generated per-run receipt is Git-ignored. An earlier [hosted Linux CI run](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036) also passed module:app startup and a transient systemd manager-stop probe on a pre-rename wheel. | The local smoke covers one macOS ARM64/Python 3.12 candidate wheel; it is not release or cross-platform evidence. The systemd result covers one transient service on Ubuntu 24.04; the persistent example unit, launchd, containers, and Windows service-manager behavior are unverified. No reload/watch, worker/process supervision, proxy headers, Uvicorn config files, Unix sockets, or general Uvicorn CLI compatibility. No package is published. See [deployment](deployment.md). |
| Process and runtime threads | **The current CLI runs one server process with one Tokio core worker.** ASGI tasks remain on the Python event loop that owns the app. | There is no `--workers` mode or process supervisor. Tokio's blocking pool can create additional threads for bridge work, so one Tokio worker does not mean a one-thread process. See [ADR 0002](adr/0002-worker-process-and-runtime-thread-model.md). |
| TLS and listeners | **Live TLS/ALPN cases pass the historical shared-write full matrix.** TCP negotiates H2 or HTTP/1.1; QUIC negotiates H3. HTTPS/HTTP3 use the configured port. Listener admission-close and typed protocol-detection cancellation pass the strengthened plaintext/TLS pair: admission closes, the partial-preface idle connection closes, and the active response drains. | Client certificate authentication, trusted proxy handling, configurable ALPN, and QUIC tuning are not provided. |
| Response and handshake header capacity | **Finite compiled capacity; both public contracts pass the historical shared-write selected normal-build audit.** They also passed the preceding full instrumented matrix. HTTP response and WebSocket acceptance maps inherit the pinned `http` crate's capacity. Valid large ASGI header collections can exceed it; fallible `try_append` preserves response state and task ownership. Same-input public cases return the small HTTP 500 or rejected WebSocket handshake, complete cleanup, and serve healthy follow-ups. | No configurable header-capacity option or stable accepted-header count is promised. Target-only capacity contracts are not Uvicorn parity and do not activate native injection controls. |
| Packaging and platform | **Hosted CI run [#39](https://github.com/appunni-m/uvicorn-rs/actions/runs/37692260364) on `a78b4a9` passed Linux, macOS, and Windows wheel consumers, Linux source-archive rebuild, candidate-wheel parity, and the CPython 3.9.25 consumer.** | This evidence is tied to `a78b4a9`, not the current main commit. No exact-current-commit candidate bundle exists and no package is published. Python 3.9 has package-consumer evidence, not full protocol parity; POSIX signal behavior is not verified on Windows. See [release status](releases.md). |
| Starlette frameworks | **The same shared app passed Uvicorn 0.54.0 vs the installed uvicorn-rs wheel on upstream Starlette 1.6.0 and on starlette-rs-py 0.1.0 from commit 738c43362938896c268ca29b9a9a2a5942df510c.** The macOS receipts and hosted Linux [CI run](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036) passed observations for lifespan state, streamed request body, three distinct response chunks, background work, HTTP 500, WebSocket handshake/subprotocol/echo, and lifespan shutdown. The server wheel has no runtime requirements and contains no framework package. See the evidence index (`benchmarks/results/framework-integration-2026-10-07/evidence-index.json`). | Selected app-level integration cases do not establish full Starlette or ASGI conformance. The pinned starlette-rs revision does not expose WebSocketRoute; its WebSocket case uses a plain ASGI branch to test the server transport, not framework-level WebSocket routing. The frameworks require separate environments because both own the starlette import namespace. On the recorded macOS run, Uvicorn completed lifespan cleanup and then re-raised SIGTERM (exit -15); uvicorn-rs exited 0. Process exit-code parity is not claimed. |
| Full ASGI conformance | **Not run.** The live probes below are focused black-box cases. | Passing these cases is not a claim that every ASGI 3, HTTP/WebSocket 2.5, or lifespan 2.0 requirement is covered. |
| Rust source coverage | **Historical 2026-10-12 adapter-only evidence:** the dirty-source local PyO3 ASGI-adapter report measured 5,561/5,561 LLVM regions and 3,997/3,997 lines. All 511 attribution cases and three 511-case repeats passed; Coverage-MCP found zero missing region/line groups with `source: matches_receipt` and `tests: passed`. See [coverage analysis](coverage.md). | This macOS ARM64 receipt is bound to the recorded dirty `src/lib.rs` and instrumented extension hashes. It does not cover the separate native `uvicorn-rs` crate, Python code, dependencies, other features/platforms, the official ASGI suite, or performance. Hosted run [38087300590](https://github.com/appunni-m/uvicorn-rs/actions/runs/38087300590) passed all eight gates on clean commit `16ed349`, which predates this local source. Do not use the instrumented extension for benchmarks. |
| Performance | **The latest exact-source FastAPI matrix completed H1, H2, WebSocket, and lifecycle correctness and produced 32 qualified workload/loop pairs.** It has no broad speed advantage: results vary by workload, and H3 at concurrency 64 stopped on Hypercorn reference timeouts. The [benchmark results](benchmark-results.md) link full throughput, p50/p95/p99 latency, CPU, RSS, and retained exclusions. | Local evidence is one M3 Pro/macOS/CPython environment from a dirty checkout. H1/WebSocket/lifecycle compare with Uvicorn; H2/H3 compare with Hypercorn. The automatic three-system run failed before producing an aggregate. Exact on-CPU function shares and total-allocation counts have not been measured. See [benchmark status](benchmark-status.md). |

### HTTP/3 request trailers at the ASGI boundary

The Python-free Rust service preserves HTTP/3 request trailers as
`http_body::Frame::trailers`. The standard Python ASGI adapter consumes those
frames and delivers the request body through ordinary `http.request` events;
it does not expose the trailers to the application. ASGI HTTP 2.5 defines
`http.request` with `type`, `body`, and `more_body`, and the ASGI extensions
specification defines response trailers but no request-trailer event. This is
an explicit Python ASGI support limit, not a claim that trailer fields are
part of the request body. See the [ASGI HTTP specification](https://asgi.readthedocs.io/en/stable/specs/www.html#request-receive-event)
and [ASGI HTTP trailers extension](https://asgi.readthedocs.io/en/latest/extensions.html#http-trailers).

The corresponding input remains a target-only support contract because the
pinned Hypercorn 0.18.0 HTTP/3 oracle raises `UnboundLocalError` while opening a
stream for the trailing HEADERS frame, before ASGI dispatch. A focused local run
of that single target case passed 1/1; it does not establish oracle parity or
clean-source release evidence. HTTP/3 permits a trailing HEADERS section after
the content ([RFC 9114, §4.1](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.1)).
Retain the target-only result until the oracle can execute this input.

The HTTP/3 malformed-frame probe sends a valid HEADERS frame and a DATA frame
whose declared payload is truncated by a clean stream FIN. RFC 9114 section 7.1
requires `H3_FRAME_ERROR`; the focused uvicorn-rs case observed code `0x106`
and verified a healthy fresh-connection response. Hypercorn's different ASGI
body events are retained in the parity result as diagnostics and are not used
as the expected behavior for this RFC case. See the [case notes](parity.md#current-http3-workflows).

## Live black-box probes

```sh
uv sync --python 3.12 --group benchmark --reinstall-package uvicorn-rs-py
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
```

Run the paired upstream Starlette and starlette-rs probes in separate
environments with an installed candidate wheel, as described in
[deployment and framework integration](deployment.md#test-starlette-integrations).

The historical merged category summary is in category-summary-2026-10-02.json (`benchmarks/results/category-summary-2026-10-02.json`); the October 4 historical separate per-category raw outputs are in full-2026-10-04T113122Z (`benchmarks/results/full-2026-10-04T113122Z/`). Rebuild the older merged H2 and summary artifacts with `uv run python scripts/assemble_category_results.py`. See [ADR 0001](adr/0001-runtime-and-asyncio-bridge.md) for the runtime decision, [the architecture page](architecture.md) for buffer ownership, and [the feasibility report](feasibility.md) for current performance results and their limits.

For a fresh, non-overwriting run of all five benchmark categories, including the
HTTP/2 and HTTP/3 matrices, use the [reproducible benchmark guide](benchmarks.md).
