# Historical unified coverage-gap inventory — 2026-10-15

> **Current status (2026-10-17):** This is a historical gap inventory, not a
> list of current missing regions. Latest completed hosted report
> [39020268579](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579)
> passed all 749 cases and three ASGI plus three native repeats with zero
> failures, infrastructure failures, retries, or unrun cases. It measured
> 9,004/9,004 source-span regions and 6,636/6,636 normalized physical lines.
> Its Coverage-MCP status remains `awaiting_query`; earlier MCP attempts were
> for report 39011984443 and do not review this report. Current main is
> `76379e2d64abc33e01827a9f160223e761858779`; its exact-head CI
> [39026041176](https://github.com/appunni-m/uvicorn-rs/actions/runs/39026041176)
> has not started its jobs yet. Older CI 39024130047 passed unified coverage
> on `77e1f425`; it is no longer the current-head check. The gap tables below describe older
> source snapshots only. See the [current coverage report](coverage.md#current-unified-coverage-status-2026-10-17)
> before proposing additional cases.

## Hosted coverage supersedes this gap inventory (2026-10-17)

Hosted run 39020268579 on commit `aa4c93836f5e2147462837bbd8b1bde6c0ebe84e`
measures 9,004/9,004 regions and 6,636/6,636 normalized physical lines. These
totals supersede the source snapshot and missing-region counts in the
historical tables below. Coverage-MCP acceptance is not established; see the
[current coverage record](coverage.md#current-unified-coverage-status-2026-10-17).


## Historical full-source evidence: 696-case snapshot

The historical exact-source report is
`target/asgi-coverage/current-696-fault-fixes-20261015/full-report.json`
(run `237b548248eb403993ab3bc593b99f99`, source SHA-256
`6fb2b5abedbdd73e6f8745587c807cbbdaacf74707a2ae23fbdff9abf290c2c2`).
It covers 696 cases: 511 Python ASGI and 185 Python-free native. All 696
attribution cases passed. Three ASGI repeats passed 511/511; three native
repeats passed 185/185. There were no failures, retries, or infrastructure
errors, and per-case coverage attribution matches the aggregate.

Coverage is **not 100%**: 8,123/8,288 LLVM regions and 6,094/6,215 lines
are covered. Coverage-MCP fully paginated the exact report over 11 region
pages (210 diagnostic groups) and five line pages (89 groups), reporting
`source=matches_receipt` and `tests=passed`. Its aggregate gate is
`incomplete` because 165 regions and 121 lines remain missing. The group
counts are per-function-instantiation observations and must not be added to
the aggregate missing totals.

| Source file | Missing regions | Missing lines | Current assessment |
| --- | ---: | ---: | --- |
| `crates/uvicorn-rs/src/http3/transport.rs` | 133 | 102 | Mix of server-role adapter errors and trait methods used by H3 clients, not this H3 server |
| `crates/uvicorn-rs/src/http3.rs` | 21 | 12 | Peer-stop observer outcomes and response-send error handling |
| `crates/uvicorn-rs/src/peer_read.rs` | 9 | 7 | Empty-buffer/read-after-error states and scalar-write fallback |
| `crates/uvicorn-rs/src/lib.rs` | 2 | 0 | Connection-vs-peer-read task completion ordering |
| **Total** | **165** | **121** | |

## Candidate input and contract plan

Each candidate below is a new input only if the current manifest does not
already assert the same observable behavior. A focused profile must prove the
named region is hit before a case is retained as a coverage addition. Keep
oracle parity cases separate from target-only fault contracts.

| Gap family | Candidate case/input | Required stimulus | Observable assertion |
| --- | --- | --- | --- |
| H3 accept error and connection-error conversion | `http3.peer-close-while-accept-waits-recovers` | Establish H3, leave the server waiting for a new request, then close the peer connection; separately exercise Quinn timeout if the adapter mapping is actually reached | Connection/request tasks retire, no unrelated stream is corrupted, and a new H3 connection gets `/ready`; retain only if the focused profile hits the intended conversion |
| H3 response-start send failure | `fault.http3.response-start-write-failure-recovers` | In a coverage build, fail the next `send_response` for one request after the ASGI app returns a valid response; follow with a healthy request on the same H3 connection | Fault is consumed, the failed stream is reset/closed, and the sibling `/ready` request succeeds |
| H3 response DATA send failure | `fault.http3.response-data-write-failure-recovers` | Stream a body, allow response headers, then inject one send-data failure at the transport boundary | First stream terminates without a connection-wide failure; sibling request succeeds; fault consumption is explicit |
| H3 response trailer send failure | `fault.http3.response-trailer-write-failure-recovers` | Send a valid response with trailers and fail only the trailer write | Data/header ordering remains valid, failed stream ends, sibling request recovers |
| H3 peer-stop observer error | `fault.http3.peer-stop-observer-error-recovers` | Make the request-scoped Quinn stop observer return its error outcome for one stream; if Quinn's error cannot be deterministically constructed, use a narrowly scoped coverage-only observer wrapper | Error is observed once, pending ASGI/body work is cancelled, only the affected stream ends, and a sibling request succeeds |
| H3 observer `Ok(None)` after local retirement | `fault.http3.local-send-retirement-preserves-response` | Return `Ok(None)` from the observer only after local send retirement while response work is still pending | The handler awaits the existing response work instead of treating local retirement as a peer cancel; complete body and sibling health are checked |
| H3 error display/source | Same observer-error case above | Drive `Http3RequestStreamError::PeerStop` through the public error observer/logging path | Verify typed source preservation and stream recovery; do not assert a complete error string or backtrace |
| H3 QUIC client adapter methods | `native.http3-client-adapter-round-trip` | Build an in-process QUIC peer and use `transport::Connection` through `h3::client`; issue one request, open/close streams, and close the connection | Peer receives the request and returns a valid response; this explicitly tests generic client-side adapter code absent from the server call graph |
| H3 QUIC read/write error mappings | Extend the client-adapter contract with peer reset, stop-sending, and connection-close phases | Cause protocol-level `ReadError::Reset`, `WriteError::Stopped`, and connection loss through a real peer; use a fault only for Quinn error variants a peer cannot produce | Correct `StreamErrorIncoming` category is delivered and later client/server operations remain isolated |
| H3 impossible stream-ID and misuse defenses | No remote input | A valid QUIC stream ID is already constrained to u62; `send_data` before `poll_ready` is an adapter contract violation | Do not fabricate a wire case. Either test the private adapter invariant in an instrumented contract or document it as outside externally reachable server behavior; do not use unsafe construction |
| Peer-read zero-capacity buffer | `native.http1.empty-read-buffer-contract` | At the private `AsyncRead` adapter boundary, poll once with a zero-capacity `ReadBuf` while the listener remains live | Immediate `Ready(Ok(()))`, zero bytes, no channel consumption, followed by a healthy HTTP request |
| Peer-read after terminal error | `fault.http1.read-after-reset-remains-error` | Abort a request upload after partial data, then make the HTTP stack poll the same reader again after the raw error is queued | The second poll remains an error, never false EOF; ASGI observes disconnect/error, task cleanup runs, and listener recovers |
| Peer-read scalar-write fallback | `native.http1.scalar-write-fallback-preserves-response` | In a coverage build, route one vectored write through the scalar fallback for a single response; the client cannot select Tokio's write method | Response status, duplicate headers, and exact body remain unchanged; normal build dispatch remains unmodified |
| Listener connection-vs-reader completion ordering | `http1.proactive-response-completes-with-reader-pending` | Use Proactive peer reading, send a complete request, leave the client write half open while the app completes the response, then close after response completion | Response is complete, the peer-read task is dropped/reaped, listener serves a follow-up request, and the focused profile hits the `connection` result arm |

## Call-graph findings: HTTP/3

The pinned dependency is `h3` 0.0.8 with `h3-quinn` 0.0.10. Source inspection
of `h3-0.0.8/src/connection.rs` shows that server initialization opens its
control, QPACK encoder, and QPACK decoder streams through
`Connection::poll_open_send`. This adapter delegates that method directly to
`h3_quinn::Connection`. The server then accepts incoming bidirectional streams.
The server does not call `Connection::opener()` or the custom
`OpenStreams::{poll_open_bidi, poll_open_send, close}` implementation.

The missing `poll_open_bidi` and opener paths are therefore client-role methods
required by `h3::quic::Connection`'s generic trait shape; a request to this
server cannot select them. Likewise, `BidiStream`'s unsplit send methods are
for client-style bidi use; the server parses an accepted request and splits
its stream before response sending. To retain literal all-source coverage
without exclusions, add the in-process `h3::client` adapter case above, not a
fabricated inbound request. If that requires exposing a coverage-only
entrypoint, keep it behind the coverage configuration and make the case drive
real QUIC/H3 frames rather than calling the line under test directly.

The following misses are defensive or internal transitions, not arbitrary
network values: an invalid u62 stream ID; send-before-ready; Quinn unknown
error variants not generated by a peer; zero-capacity `ReadBuf`; and Tokio's
choice to invoke scalar versus vectored writes. Use a narrowly scoped fault or
private adapter contract only when it also verifies a documented public
recovery, disconnect, or response-preservation behavior. Do not exclude
source regions or alter the coverage denominator to claim 100%.

## Source spans and follow-up

The machine-readable list of all 165 exact missing region IDs and source spans
is `coverage.uncovered_regions` in the report above. The source-file summaries
give exact missing line counts; the region spans can cross lines, so do not
derive line totals by counting unique region start lines.

Coverage-MCP receipt:
`target/asgi-coverage/current-696-fault-fixes-20261015/coverage-mcp-receipt.json`
(SHA-256
`8f193eaeeca041fe3446a79132ce049c0be53ee5cac26b0d826f5fde178e3a8d`).
Report SHA-256 after receipt attachment:
`246e9a0dcaece9425d18541d72a7a9e2d3e996fea0a2876efe115c93a6a9a3e6`.
All generated files remain under ignored `target/`.

Work order:

1. Add the genuinely external H3 peer-close and HTTP/1 completion inputs only
   where an existing case does not already assert the same outcome; run the
   selected instrumented profiles and retain only cases that hit a distinct
   missing region.
2. Add the `h3::client` adapter contract for server-inapplicable generic
   trait methods and protocol-generated resets/stops.
3. Add deterministic coverage-only faults for H3 send failures and observer
   error/local-retirement outcomes where peer timing cannot produce them
   reliably; assert stream isolation, response preservation, and sibling
   recovery.
4. Use explicit private adapter contracts for impossible Tokio call-shape
   states only if the public behavior under test is stated and verified; never
   claim that a remote ASGI input controls Tokio's internal method choice.
5. Rerun one exact-source full matrix only after the selected additions and
   source changes stabilize. Acceptance requires 100% source regions and
   lines, complete attribution, three clean repeats per lane, and fully
   paginated matching-source Coverage-MCP results.
