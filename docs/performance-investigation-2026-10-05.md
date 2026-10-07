# October 5 performance investigation

A general end-to-end speed improvement over Uvicorn or Hypercorn is **not proven**.
The frozen October 5 comparison qualifies one workload: WebSocket connection
handshakes were 1.59× faster than stock Uvicorn across three valid matched
repetitions, with lower CPU and latency. Each handshake run completes a fixed
500 operations with a short observation window; its RSS samples are sparse.
Fresh comparisons use public error logging and automatic lifespan. Most HTTP
timings remain excluded by host contention; stock Hypercorn's H3 path also
failed correctness checks. These measurements belong to their archived source
and binary identities, not the current checkout.
The retained changes remove an observed HTTP/1 body-copy path and reap completed
HTTP/3 tasks during acceptance. The latter reduced observed peak RSS substantially
in a separate target-only diagnostic.

Raw reports, rejected rows, logs, source/native identities, dependency records,
and profiling evidence are in
[`performance-investigation-2026-10-05`](../benchmarks/results/performance-investigation-2026-10-05/).
The current checkout includes a later HTTP/3 application-close correction.
Its 460-case attribution gate, three full repeats, 221-case normal-wheel parity,
and exclusion audit passed on October 6; those correctness results do not
refresh the performance measurements. Throughput, CPU and latency gains for
the current source require qualifying paired runs.

The shared-write normal build uses a borrowed scalar/vectored buffer enum to
share write-error handling. Its source `81c239…`, native `8f69af…` and passing
213-case public parity, formatting and Clippy receipts are frozen in
[`current-normal`](../benchmarks/results/performance-investigation-2026-10-05/current-normal/).
The measured HTTP/3 task-reaping build has source `313fc3…` and native
`b11f16…`; its normal build receipts are in
[`current-normal-h3-reaping`](../benchmarks/results/performance-investigation-2026-10-05/current-normal-h3-reaping/).
The October 5 source `c7bd49…` adds a coverage-only failure after a completed H3
response; its saved normal artifact is `0e13bb…`. The first expanded 450-case
attempt passed individual attribution but failed full repeats and left two
native regions unobserved. Fresh 451-case verification adds a structured
held-response cancellation contract. That fresh run passed 451/451 attribution
and three complete 451-case repeats with zero failures, infrastructure errors
or retries. LLVM reports 4,778/4,778 native regions and 3,371/3,371 lines covered.
The matching unfiltered MCP check also passed with zero gap groups and
`source: matches_receipt`, `tests: passed`. The
[full archived proof](../benchmarks/results/performance-investigation-2026-10-05/http3-task-reaping-coverage/archive-manifest.json)
binds that report to the fresh instrumented native `d2323f…`. The saved normal
binary `0e13bb…` passed 214/214 public parity cases and all three coverage-seam
exclusion cases. Its portable identity stayed exactly equal before parity,
after parity, after the exclusion audit and after documentation updates. The
[normal proof](../benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/normal-gates-receipt.json)
retains the two earlier invalid identity attempts as well as the successful run.
The earlier memory
measurement applies to `b11f16…`, not to an unmeasured binary. Each proof applies
to its named build. These checks do not substitute for timed comparisons.

## Current normal-build comparisons

The current source `c7bd49…` / native `0e13bb…` run planned 177 rows at three
repetitions, five-second load, one-second warmup and concurrency 64, plus
declared workload overrides. Every category retained the exact pre-parity
source/native/app/client/dependency identity. The four complete categories
passed all 138 response/lifecycle checks; H3 retained one Rust sample before
the reference failed. The suite remains `incomplete_categories`.
The [raw run and derived analysis](../benchmarks/results/performance-investigation-2026-10-05/final-normal-c7-categories/analysis.md)
retain every exclusion, checkpoint, server log and exact gate.

| Category | Completed rows / planned | Correctness failures | Individually valid timings | Qualified workload comparisons |
| --- | ---: | --- | ---: | ---: |
| HTTP/1.1 | 72 / 72 | 0 | 14 | 0 |
| HTTP/2 | 42 / 42 | 0 | 3 | 0 |
| HTTP/3 | 1 / 39 | Hypercorn: 16 header timeouts | 1 | 0 |
| WebSockets | 18 / 18 | 0 | 10 | 1 |
| Lifespan/shutdown | 6 / 6 | 0 | 0 | 0 |

The qualified WebSocket workload measures completed connection handshakes at
its declared concurrency one. Both servers use uvloop, the same ASGI app and
native client. These are medians of three matched runs; latency percentiles
are per-run percentiles, not pooled observations.

| WebSocket handshake metric | Uvicorn | Rust |
| --- | ---: | ---: |
| Completed handshakes/s | 3,771.4 | 5,997.3 |
| p50 / p95 / p99 (ms) | 0.245 / 0.381 / 0.474 | 0.146 / 0.281 / 0.312 |
| Observed server CPU per handshake (µs) | 188.9 | 112.4 |
| Median sampled peak server RSS (MiB) | 32.0 | 26.5 |

The median of same-repetition Rust/Uvicorn throughput ratios is 1.590. This
qualifies local handshake performance only. Echo, HTTP throughput and overall
server performance cannot be inferred from it. The checkout was frozen but
dirty, the load was closed-loop on the same machine, and three repetitions
are a descriptive gate rather than a statistical significance test.

### Consumed-request H3 failure

The additive `protocol-scope-consumed-request` app reads through the final
request event and checks `http_version=3;bytes=1`. Both servers ran that same
app with optional client GREASE disabled. Rust completed 107,619 correct
requests. Hypercorn completed 13,291 correct requests and then failed 16
response-header waits; its server log was empty. The measured reference
client exited nonzero, so no speed or resource ratio is accepted.

A separate lower-load replay at concurrency four and four QUIC connections
passed all six response/lifecycle samples. Five timings were host-invalid;
one passed individually and no paired ratio qualifies. At concurrency sixteen,
both first-repetition samples passed responses but were host-invalid. Rust's
second repetition failed the diagnostic gate on the client's application-close
code zero. Both [c4](../benchmarks/results/performance-investigation-2026-10-05/h3-consumed-c4/)
and [c16](../benchmarks/results/performance-investigation-2026-10-05/h3-consumed-c16/)
attempts retain their original client identity and failures.

The maintained benchmark client now closes with explicit `H3_NO_ERROR`
(`0x100`), as specified for a clean HTTP/3 close by
[RFC 9114](https://www.rfc-editor.org/rfc/rfc9114.html#section-5.2).
That client revision has not produced replacement timings. It also does not
The server's unknown-close-code gap was reproduced with code zero and corrected
in the public parity path. The regression inputs also exercise reserved GREASE,
an unknown value above the registered base range, and the maximum QUIC varint.
The fix preserves registered H3/QPACK/datagram errors. Fresh complete H3
coverage and benchmark runs after this source change are still required.

This failure differs from the earlier captured `KeyError` and GREASE-enabled
first-request timeout. Full request consumption and disabling GREASE did not
make the concurrency-64 comparison pass. A connection stall is a hypothesis;
the current evidence does not identify the transport/parser event that caused
it. No reference patch or increased response deadline was applied.

## Earlier category comparisons

The sequential run planned 171 rows with three repetitions, five-second load,
one-second warmup and concurrency 64, plus declared workload overrides. The
same apps, CPython 3.12.13, stock dependencies and clients ran on the same M3 Pro.
HTTP/1 and WebSockets used Uvicorn/uvloop; HTTP/2 and HTTP/3 used Hypercorn/uvloop.

| Category | Completed rows / planned | Response/lifecycle failures in completed rows | Individually valid timings | Qualified workload comparisons |
| --- | ---: | ---: | ---: | ---: |
| HTTP/1.1 | 72 / 72 | 0 | 2 | 0 |
| HTTP/2 | 42 / 42 | 0 | 0 | 0 |
| HTTP/3 | 1 / 33 | 0; reference warmup failed | 1 | 0 |
| WebSockets | 18 / 18 | 0 | 4 | 0 |
| Lifespan/shutdown | 6 / 6 | 0 | 0 | 0 |

The four complete categories contain 138 rows; HTTP/3 retains one Rust row and
the failed reference warmup. The analyzer marks the suite `incomplete_categories`.
Host CPU contention rejected 132 of the 139 completed timing rows. Deliberate
exception timings also remain unrankable because diagnostic costs differ.
All raw attempts, server logs, identities and the exact harness snapshot are in
[`categories-error-logs`](../benchmarks/results/performance-investigation-2026-10-05/categories-error-logs/).

A separate HTTP/1 retry completed 30 correct samples across fixed responses,
1 MiB responses, response chunks, 32-header scopes and context variables.
Eleven timings passed individually. Matching valid repetitions were fixed
`[2, 3]`, large response `[1, 3]`, and scope `[1]`; no workload reached the
required three matches. Its [raw evidence](../benchmarks/results/performance-investigation-2026-10-05/http1-clean-retry/)
also yields no qualified performance ratio. Invalid rows remain preserved.

### Stock Hypercorn HTTP/3 failure

Hypercorn 0.18.0/aioquic 1.3.0 crashed its UDP task with `KeyError(4140)` in
`hypercorn/protocol/h3.py` while indexing a removed stream. The remaining 64
requests timed out. A separate unchanged-client replay at concurrency 16 and
four QUIC connections reproduced `KeyError(72)` after 69 correct responses.
Concurrency one completed 1,974 correct responses in a one-second diagnostic.

The app legally responds after its first request event. Stock Hypercorn removes
stream bookkeeping when that app completes; a later DATA/FIN event can then
reach the unguarded stream lookup. This mechanism matches the captured stack;
packet-level ordering was not instrumented. Both reference crashes remain
correctness failures and cannot produce a Rust speed ratio. No reference source
was patched. The retained [H3 diagnostics](../benchmarks/results/performance-investigation-2026-10-05/h3-diagnostics/)
include the initial sandbox bind failure and both live replays.

The expanded correctness matrix exposed a separate H3 interoperability issue:
the 128-request connection case passed in isolation but timed out in complete
repeats. Source inspection found that pinned `h3` adds optional GREASE before
the first request's FIN, while pinned aioquic can omit the request-end event
when the last parsed frame is unknown. This matches an app waiting for its
final request event. In the controlled GREASE-on/off replay, the enabled setting
timed out waiting for Hypercorn's first response headers. With GREASE disabled,
both servers returned 128 identical responses and passed the peer-close case
with clean shutdown. Only that declared client setting changed; reference
source, deadlines, request bodies, headers and sequence length stayed fixed.
The [replay receipts](../benchmarks/results/performance-investigation-2026-10-05/http3-grease-interop/ab-receipt.json)
support a GREASE-dependent request-end failure. They do not directly trace
packet ordering or the reference parser's event dispatch. The public sequence
now declares GREASE disabled; the enabled failure remains archived.
HTTP/3 permits reserved frames, which receivers must ignore according to
[RFC 9114 section 7.2.8](https://www.rfc-editor.org/rfc/rfc9114.html#section-7.2.8).

## Historical original-build measurements

The earlier four-arm experiment completed 120 correct response samples. Only
15 timings passed the host-contention guard, all from the original-build arm;
none of its 90 optimization timings qualified. The interned-key and one-worker
experiments remain unaccepted.

The 1 MiB response workload has three valid matched Rust/Uvicorn repetitions.
Both used CPython 3.12.13, uvloop 0.23.0, the identical ASGI app and native
client, 64 persistent connections, a one-second warmup and three-second
samples on the same Apple M3 Pro. Uvicorn 0.54.0 used httptools 0.8.0.

| Median | Uvicorn | Original Rust build |
|---|---:|---:|
| Requests/s | 12,697 | 10,028 |
| p50 / p95 / p99 (ms) | 4.490 / 8.680 / 12.486 | 6.051 / 10.737 / 13.092 |
| Server CPU per request (µs) | 76.6 | 187.4 |
| Server CPU (% of one core) | 94.4 | 179.9 |
| Sampled server peak RSS (MiB) | 32.8 | 134.3 |
| Client CPU per request (µs) | 257.9 | 569.8 |

These are frozen dirty-checkout local results, not a release baseline. Other
original-build workloads lack three valid matched repetitions. The client is
on the same host and consumes several cores for large transfers. CPU totals
include the recorded client setup/drain/report boundary. Latency comes from
closed-loop load at each server's achieved throughput; it is not a comparison
at a fixed offered request rate. The complete reports preserve these limits.

## Concrete costs found

### A transport wrapper hid vectored writes

`ConnectionIo` implemented scalar `AsyncWrite::poll_write` but did not forward
`is_write_vectored` or `poll_write_vectored`. With locked Hyper 1.11.1, that
selected its flattening writer, which copied response body buffers into the
header/write buffer. Python-owned outgoing `Bytes` could therefore still incur
a later native copy.

The candidate forwards all three operations and shares the existing write
error/disconnect handling. Hyper can retain the original buffers and submit
header/body slices to `writev`. It adds no unsafe code and does not change ASGI
message types, ordering, ownership or backpressure.

| Sampled leaf path, large response | Original | Vectored candidate |
|---|---:|---:|
| Hyper `WriteBuf::buffer` → `memmove` | 907 | 0 |
| All `memmove` leaves | 942 | 46 |
| Scalar `__sendto` leaves | 4,740 | 0 |
| `writev` leaves | 0 | 5,178 |

The preserved profiler receipts pass payload, stable identity, sampler and
graceful-shutdown checks. These are wall-time stack observations, not CPU
shares or benchmark speed measurements. Client/app/Python/load configuration
matched; unrelated harness files changed between profiles. The effect was
observed on plaintext HTTP/1.1, so it does not establish an H2/H3/TLS gain.

### Completed HTTP/3 tasks accumulated on persistent connections

The request `JoinSet` previously joined completed tasks only when the connection
stopped accepting requests. Long-lived QUIC connections therefore retained
completed task allocations and their join bookkeeping. This does not establish
that each task retained its original Python objects or response payload.

Acceptance now selects completed request joins as well as new requests. One
shared `Result` handler reports join failures during acceptance and final drain.
Cancellation keeps priority; peer-close, acceptance-error abort and graceful
drain behavior remain. Tokio documents `join_next` as cancel safe in `select!`.
See the [pinned Tokio documentation](https://docs.rs/tokio/1.53.1/tokio/task/struct.JoinSet.html#method.join_next).

The defending case completes a real response, injects a coverage-only task
failure, observes the parent task error while the connection stays open, and
sends another request on that connection. The old implementation with the same
failure seam returns both correct responses but misses the timely diagnostic;
the current implementation returns both responses and reports the error before
peer closure. The original failure-before-response case remains separate. No
failure injection is included in normal release builds.

Five before and five after runs used the same protocol-scope app, client,
normal release settings, five-second load, one-second warmup, 64 workers and
four persistent QUIC connections. Every response passed status/body checks and
every server passed its graceful shutdown/diagnostic gate.

| Descriptive memory diagnostic | Before task reaping | After task reaping |
| --- | ---: | ---: |
| Median sampled peak RSS (MiB) | 614.3 | 33.0 |
| Sampled peak RSS range (MiB) | 467.3–657.9 | 30.9–37.2 |
| Completed requests per sample | 112,855–151,838 | 110,204–155,671 |
| Individually valid timing rows / total | 2 / 5 | 0 / 5 |

The median observed peak RSS decreased about 94.6%. These descriptive memory
values include all ten correct runs, including contention-invalid timings.
Completed work counts were not fixed, before runs preceded after runs, and
RSS is sampled process memory. The result supports this task-retention repair
on the local workload. No throughput, latency, CPU or cross-server speed ratio
is qualified. Preserve that scope when using the
[raw comparison and derived analysis](../benchmarks/results/performance-investigation-2026-10-05/h3-task-reaping/).

### The Python boundary causes thread handoffs

The fixed-response profile contains 5,907 thread samples with GIL acquisition
on the stack; 5,691 terminate in synchronization waits. Those counts span the
Python loop and both active Tokio workers and are not percentages of CPU or
request latency.

Rust constructs Python scopes and schedules ASGI tasks from its workers. The
app, task factory, context, cancellation and exception handling remain on the
captured Python event loop. Uvicorn's fast configuration performs network and
application work on its Python event loop, avoiding this particular cross-loop
handoff. That comparison already uses native uvloop/httptools components;
it does not compare Rust networking with an entirely Python network stack.
Reducing boundary work is the next architectural target.

Two smaller experiments were compiled and exercised: intern fixed HTTP
dictionary keys/immutable values, and then reduce Tokio workers from two to
one. Both passed their 30 measured response samples. Their timing guards
rejected every sample, so the checkout retains two workers and its existing
event-name caching. Common-method caching was only drafted and was not built.

SIMD should follow a measured hot byte-processing loop. It does not remove
task scheduling, GIL acquisition, Python object creation or ASGI-visible sends.
The large-response copy can be removed entirely before tuning copy instructions.

## Correctness and benchmark repairs

- Recognize typed `H3_NO_ERROR` (`0x100`) as a normal peer close and retain the
  owned request-task drain. Other acceptance errors keep their error path.
  The new wire-input case fails on the prior build and passes with the fix;
  the injected acceptance-error contract also passes.
- Rebuild the independent `starlette-rs` benchmark wheel coherently. Its stale
  editable native core did not match its Python constructor/callback ABI and
  produced 500s under Uvicorn. The external checkout was unchanged; the rebuilt
  wheel is installed only in this benchmark environment and the identical app
  now passes both servers' checks.
- Record normal native/client/source/dependency hashes before and after each
  sample; reject instrumentation, unexpected errors, forced shutdown and
  measured host contention. Preserve excluded samples and require three
  matching valid repetitions before comparing timings.
- Pace the slow reader by total body bytes instead of TCP callback count.
  Report complete child CPU accounting, sampled process-tree RSS and observer
  cost. Keep deliberate exception-to-500 performance rows unrankable.

The earlier four-arm H1 experiment used reference logging at `CRITICAL`.
Its selected apps passed their response checks, but that level suppresses
reference error diagnostics. Subsequent runners enable public error logging
so the diagnostic gate can inspect those errors. The historical rows remain
unchanged and are not promoted to proof of diagnostic parity.

The historical H1 reference also disabled lifespan while Rust used automatic
support detection. The revised H1/WebSocket comparisons enable automatic
lifespan on both servers. Their identical synchronous-callable fixture now
implements startup/shutdown while retaining its original HTTP response and
outer callable behavior. These fixture/configuration changes are fingerprinted;
the older timings cannot be substituted for fresh matched measurements.

## Next acceptance gate

The tracked [`run_benchmark_categories.py`](../scripts/run_benchmark_categories.py)
captures a normal binary/source/app/dependency identity before public parity,
requires the complete current public matrix on that exact binary, and runs
categories sequentially. Its pure JSON analyzer retains exclusions and requires
three matching valid repetitions before producing ratios. The separate
[manual benchmark workflow](../.github/workflows/benchmark-categories.yml) builds
normal wheels and clients, records the Linux environment and uploads failures.
It has been added and statically reviewed; its hosted execution remains unrun.

Two fresh host preflights after the `a78b4a9` TLS-probe fix still rejected
timing before any workload started. The 12-sample reports measured mean
unrelated aggregate CPU at 281.0% (maximum 319.4%; this sample overlapped a
transient compile) and 272.2% (maximum 315.9%; `mediaanalysisd` averaged 66.9%
of one core, with transient Python activity). The complete reports are
[preflight 1](../benchmarks/results/2026-10-08/benchmark-host-preflight-2026-10-07T215407Z.json)
and
[preflight 2](../benchmarks/results/2026-10-08/benchmark-host-preflight-2026-10-07T215514Z.json).
Neither report contains benchmark rows. A valid matched run still requires a
quiet local interval or an authenticated workflow dispatch.

Run these commands on an idle host. Compare HTTP/1.1/WebSockets with Uvicorn and
H2/H3 with unmodified Hypercorn. Retain every failed or excluded attempt. Accept
an end-to-end speed claim only after at least three valid matched repetitions
show a benefit with acceptable CPU, memory and tail latency across the affected
workloads. The failed legal early-response H3 workload remains visible. The
additive `protocol-scope-consumed-request` workload has its own declared app
identity; it consumes the request through the final ASGI event before responding
and checks the protocol version and received byte count. It runs the same app
on both stock Hypercorn and Rust. The current complete driver plan has 177 rows;
its concurrency-64 reference attempt failed as documented above. The consumed-request
workload declares GREASE disabled on the shared client for both servers. Existing
workloads keep their original enabled setting and failure evidence.

If profiles still identify boundary handoffs as dominant, prototype bounded
notification batching while preserving per-request loop/context/task-factory
behavior, FIFO admission, exceptions, cancellation, backpressure and shutdown.
That requires its own black-box parity and fault-contract evidence. See the
[benchmark guide](benchmarks.md) and [coverage report](coverage.md) for commands
and the exact scope of current verification.
