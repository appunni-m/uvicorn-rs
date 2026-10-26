# Benchmark and release-gate status

<!-- BEGIN GENERATED LATEST ATTEMPT -->
## Latest automated benchmark attempt

- Run: [40228012455 (attempt 1)](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455)
- Commit: [`7811b2392b60cd8eadc8a951c1eff47d57ace2d6`](https://github.com/appunni-m/uvicorn-rs/commit/7811b2392b60cd8eadc8a951c1eff47d57ace2d6)
- Recorded: 2026-10-25T23:51:23Z
- Category matrix job: `failure`
- Aggregate job: `failure`

This attempt did not produce a validated three-system aggregate or a complete performance report. Partial per-system measurements remain in this run's artifacts. The [previous complete report](benchmark-results.md) remains the latest complete measurement; inspect the [workflow artifacts and logs](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455) for this attempt.
<!-- END GENERATED LATEST ATTEMPT -->

## Focused HTTP/3 diagnostic (2026-10-26)

Focused trace run
[40255991178](https://github.com/appunni-m/uvicorn-rs/actions/runs/40255991178)
used current branch commit
[`35e548f08d1a4248488fc1351ed8850e7c80f23c`](https://github.com/appunni-m/uvicorn-rs/commit/35e548f08d1a4248488fc1351ed8850e7c80f23c)
on Linux ARM64 with Hypercorn asyncio, `slow-reader-backpressure`, and one
repetition. It completed 40 requests and 40 MiB of response data with no client
failures. The workload overrides the workflow's top-level concurrency input:
its effective concurrency was 2. Diagnostic tracing invalidates timing. The
[retained trace artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/40255991178/artifacts/12622154441)
contains no `stream_lookup_missing` or `h3_decode_error` event. It records
normal stream removal followed by later close notifications after removal.

This does not reproduce or explain the earlier
[main-commit failure](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988939):
Hypercorn raised `KeyError(52)` in slow-reader repetition 4, after which the
client recorded two response-header timeouts. The retained failure log lacks
event ordering, and the focused trace uses a different source commit. The
ordering and cause therefore remain unconfirmed; neither run supplies complete
three-system performance evidence.

The local optimization host preflight on 2026-10-26 also rejected timing
because unrelated CPU exceeded 100% aggregate and a process exceeded 25% for
two consecutive intervals. No timing workload started. Its receipt is
`target/kata-progress/v7a1-host-preflight-goal-resume-20261026.json` in the
maintainer checkout.

## Latest run diagnosis (2026-10-25)

Performance run [40228012455](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455)
used branch commit
[`7811b2392b60cd8eadc8a951c1eff47d57ace2d6`](https://github.com/appunni-m/uvicorn-rs/commit/7811b2392b60cd8eadc8a951c1eff47d57ace2d6),
which predates the current dirty checkout. Linux x86-64 passed its exact-binary
parity and category job. macOS ARM64 failed before timing when the Uvicorn
oracle timed out in
`websocket-tls.text-round-trip-with-query-and-subprotocol` (468 cases passed,
one infrastructure failure, one not run). Linux ARM64 passed parity and the
FastAPI comparison, then failed the HTTP/3 correctness gate during
`large-response` against Hypercorn asyncio in repetition 2: the client received
904,262 bytes where the response declared and required 1,048,576 bytes. The
retained checkpoint has no completed HTTP/3 report, so no HTTP/3 performance
result can be ranked. See the [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455/artifacts/12612492171),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455/artifacts/12614726014),
and [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/40228012455/artifacts/12615290088).

The Linux ARM64 HTTP/1 category includes 20 rows for
`fastapi-upload-1m-write-1k` at concurrency 8 across four server configurations
and five repetitions. All 20 rows were timing-valid with zero failures, so this
run did not reproduce the earlier HTTP/1 upload timeout. It does not identify
that timeout's cause. The macOS parity failure and Linux ARM64 HTTP/3 failure
mean this attempt is incomplete three-system evidence; make no release
performance claim from it.

Offline trace of the retained Linux ARM64 artifact narrows the HTTP/3 failure
to a Hypercorn stream-close race. The failed client request is request 86 in
`large-response`; stream IDs for client-initiated bidirectional requests advance
by four, giving stream ID 340. Hypercorn 0.18.0 raised `KeyError(340)` at
`H3Protocol.handle` while indexing `self.streams[event.stream_id]` for a
`DataReceived` event. Its H3 adapter removes entries on `StreamClosed` and
does not guard that later lookup. The workload is a GET with no request body;
the H3 probe calls `finish()` after sending its headers. In the pinned aioquic
1.3.0 source, a bare FIN can produce an empty `DataReceived` event. These
observations establish that Hypercorn handled `DataReceived` after the stream
mapping had been removed. The archive does not record the event payload or its
timestamp, so identifying it as the empty FIN and attributing the truncated
response to the UDP task crash remain supported inferences. Hypercorn has an
open upstream change for this exact late-`DataReceived` case in
[PR 334](https://github.com/pgjones/hypercorn/pull/334); the pinned 0.18.0
changelog records the preceding stream-removal change
([changelog](https://github.com/pgjones/hypercorn/blob/main/CHANGELOG.rst)).
This remains a correctness failure in the reference cell, so no HTTP/3 timing
from the incomplete run can be ranked.

## Latest run diagnosis (2026-10-22)

Performance run [39689988939](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988939)
measured exact `main` commit
[`86e72e181d00feca1b4db7f30377d5d9d4345b83`](https://github.com/appunni-m/uvicorn-rs/commit/86e72e181d00feca1b4db7f30377d5d9d4345b83).
The Linux x86-64 and macOS ARM64 category jobs passed. Linux ARM64 passed
public parity and the FastAPI comparison, then its category job failed in
HTTP/3 `slow-reader-backpressure`: Hypercorn 0.18.0 asyncio raised
`KeyError: 52` while indexing `self.streams[event.stream_id]` in repetition 4.
The client completed 28/40 requests and recorded two response-header timeouts.
See the [Linux ARM64 category artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988939/artifacts/12392116838)
and [aggregate artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988939/artifacts/12392708725).

The aggregate job succeeded in validating and retaining partial evidence, but
the matrix job failed and the run did not produce a complete validated
three-system comparison. The failed Hypercorn cell is correctness-invalid and
must not be ranked. Passing cells remain in the per-system artifacts and may be
assessed individually when their own response and timing gates pass; they do
not repair the failed cell or complete the release matrix. The retained artifact
has no per-stream event trace, so
the suspected late `DataReceived` after `StreamClosed` ordering remains a
source-supported hypothesis, not a confirmed root cause. HTTP/3 upload remains
excluded for Hypercorn after its separate response-header timeout. Treat the
HTTP/3 matrix as incomplete and make no release performance claim from this
run. This run describes the committed package graph; it does not validate the
uncommitted single-crate consolidation draft.

The Linux ARM64 HTTP/1 artifact separately records six FastAPI upload
workloads across four server configurations and five repetitions: 120 rows in
total, all timing-valid with zero failures, including all 20 rows for
`fastapi-upload-1m-write-1k`. This later run did not reproduce the HTTP/1 upload
timeouts from [run 39036702600](https://github.com/appunni-m/uvicorn-rs/actions/runs/39036702600).
It does not explain that earlier failure; its available logs show the client
timeout before Starlette `ClientDisconnect` without an earlier server fault.
The separate HTTP/3 failure still leaves the three-system run incomplete.

## Earlier parity-gate failure (run 39508168315)

Run `39508168315` used commit
[`87b888b5`](https://github.com/appunni-m/uvicorn-rs/commit/87b888b5c364d087dc389076846d7474ba3a15e9), before the HTTP/3 shutdown-parity correction in
[`8a0a0e11`](https://github.com/appunni-m/uvicorn-rs/commit/8a0a0e116). Its three platform jobs stopped at the exact-binary parity gate, before timing. The eight failures were the HTTP/3 peer-close cases listed below. Their protocol observations matched; the differing field was process exit status: Hypercorn's oracle exited `0`, while uvicorn-rs was terminated with `-15` (SIGTERM).

Current `main` compares HTTP/3 peer-close termination and protocol outcome without requiring those server-specific process exit codes to match. Each of the eight affected inputs was replayed individually against the live Uvicorn oracle at `ecf185f19`; all eight passed with zero infrastructure failures:

- `http3.peer-close-h3-no-error`
- `http3.peer-close-unknown-zero`
- `http3.peer-close-registered-h3-datagram`
- `http3.peer-close-registered-h3-general-protocol-error`
- `http3.peer-close-registered-qpack-decompression-failed`
- `http3.peer-close-reserved-grease`
- `http3.peer-close-unknown-above-base-range`
- `http3.peer-close-unknown-maximum-u62`

This identifies that earlier hosted failure as an outdated comparison rule,
not a reproduced HTTP/3 runtime mismatch. That attempt produced no timing data;
it is separate from the later HTTP/3 reference failure described above.

> **Evidence path note:** Paths under `benchmarks/results/` and ignored `target/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

## Current-source FastAPI upload call-path profile (macOS ARM64; 2026-10-21; diagnostic only)

Matched Samply profiles captured the stock FastAPI `POST /upload/1048576`
workload on an Apple M3 Pro running macOS 15.7.7. Both used CPython 3.12.13,
FastAPI 0.142.4, Starlette 1.7.0, Pydantic 2.13.5, uvloop 0.23.0, and
httptools 0.8.0. The reference was verified stock Uvicorn 0.54.0 from the
isolated oracle environment; its installed `RECORD` hashes matched. Rust was
1.98.1. The request uploaded 1 MiB in 1 KiB writes at concurrency 8. Each run
used a 1-second warmup, 5-second load, and Samply 0.13.1 at a 1 ms sample
interval. The analyzed profile covered 5.036 seconds of Rust load and 5.064
seconds of Uvicorn load. Both correctness gates passed: 1,410 Rust requests and
1,768 Uvicorn requests completed without failures.

The profiles were captured from `main` at commit
[`0d59870cf81b431d8ba17604191bdd139b060d54`](https://github.com/appunni-m/uvicorn-rs/commit/0d59870cf81b431d8ba17604191bdd139b060d54),
source SHA-256
`3b7304604203c8aac29e1c1e0aea5c2f93164a1d9f24ba0a7b02cec42fd6bf6a`, and a
stable Rust extension SHA-256
`cc8e625ec743c384ea371be3c3aa1608532d726f72171c6990a66c5c694fba73`.
Uvicorn's receipt reports version 0.54.0 and the isolated package path; the
candidate environment's separate runtime identity is not the Uvicorn server
identity.

| Observation | uvicorn-rs | Uvicorn |
| --- | ---: | ---: |
| Sampled CPU weight attributed to Python image | 4.60% | 41.25% |
| Sampled CPU weight attributed to `_native.abi3.so` | 17.55% | — |
| Sampled CPU weight attributed to `libsystem_kernel.dylib` | 63.46% | 40.05% |
| Per-thread CPU weight on Tokio-named threads | 79.49% across 9 threads | — |
| Per-thread CPU weight on Python thread | 20.51% | 100.00% |
| Threads with a sampled Tokio blocking-pool `Inner::run` frame | 9 | 0 |

Within the Rust profile, inclusive stacks include `pump_peer_read` at 35.34%,
Tokio `TcpStream::poll_read_priv` at 34.04%, and `AsgiIo::receives` at 11.51%.
These values overlap and must not be added. The analyzer now detects Tokio's
blocking-pool loop from both demangled and Rust v0-mangled symbols; its earlier
pattern missed these frames and incorrectly reported zero. Uvicorn's largest
exclusive Python frame was `_PyEval_EvalFrameDefault` at 22.36% of sampled CPU
weight.

This is a diagnostic profile, not a speed comparison: sampling perturbs
scheduling, the runs were separate, and their request counts are not rankable.
System shared-cache function names remain unresolved, so the large
`libsystem_kernel.dylib` share does not identify a specific system call. The
profile narrows investigation toward the Rust request-body/socket-read path and
runtime scheduling; it does not prove which causes the measured HTTP/1 gap or
justify a new runtime setting or SIMD change. Full receipts, profiles, and the
analyzed report remain local-only under
`target/wh9k-samply-current-main-{rs,uvicorn}-20261021/` and
`target/wh9k-samply-current-main-20261021/`.

## FastAPI WebSocket text echo and text-buffer candidate (Linux x86-64; 2026-10-21)

This focused benchmark used the stock FastAPI app's 32-byte WebSocket text
echo route, 32 concurrent connections, a 1-second warmup, 5-second samples,
five repetitions, and seed `20261021`. It ran on an AMD Ryzen 5 2600X host
(12 logical CPUs, Linux `7.0.0-38-generic`) with CPython 3.12.13 and Rust
1.91.1. Both environments used FastAPI 0.142.4, Starlette 1.7.0, Pydantic
2.13.5. The verified reference was stock Uvicorn 0.54.0; `httptools` was
0.8.0, `websockets` was 17.1, and `uvloop` was 0.23.0. The same Rust
`tokio-tungstenite` client binary was used in both reports. All requests
matched their expected echo and every server shut down cleanly.

The table reports medians over each server's timing-valid rows. Baseline
Uvicorn/asyncio repetition 3 was excluded for unrelated host CPU activity,
leaving four matched asyncio pairs; the other baseline pair and all candidate
pairs had five valid repetitions.

| Build / server | Loop | Valid rows | Messages/s | p50 / p95 / p99 ms | Server CPU µs/message | Server RSS MiB | Client CPU µs/message | Client RSS MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Main Uvicorn | asyncio | 4/5 | 20,732 | 1.520 / 1.768 / 1.838 | 48.0 | 48.88 | 35.5 | 8.79 |
| Main uvicorn-rs | asyncio | 5/5 | 8,504 | 3.930 / 5.322 / 5.680 | 196.2 | 55.72 | 42.7 | 8.32 |
| Main Uvicorn | uvloop | 5/5 | 24,788 | 1.241 / 1.554 / 1.602 | 40.2 | 51.13 | 32.2 | 8.90 |
| Main uvicorn-rs | uvloop | 5/5 | 16,166 | 2.169 / 2.642 / 2.854 | 102.8 | 58.22 | 33.4 | 8.80 |
| Candidate Uvicorn | asyncio | 5/5 | 21,288 | 1.422 / 1.767 / 1.804 | 46.9 | 48.31 | 34.9 | 8.81 |
| Candidate uvicorn-rs | asyncio | 5/5 | 8,381 | 3.961 / 5.446 / 5.888 | 198.4 | 55.77 | 41.4 | 8.34 |
| Candidate Uvicorn | uvloop | 5/5 | 22,863 | 1.333 / 1.587 / 1.616 | 43.5 | 50.93 | 33.8 | 8.86 |
| Candidate uvicorn-rs | uvloop | 5/5 | 15,917 | 2.154 / 2.711 / 2.928 | 104.1 | 58.50 | 33.9 | 8.84 |

The baseline's Rust server CPU was 4.1 times Uvicorn under asyncio and 2.6
times Uvicorn under uvloop for this workload. These totals identify a server
cost gap, not the responsible function or thread. The Rust candidate carried
Tungstenite's existing UTF-8 buffer through the incoming queue instead of
allocating an intermediate Rust `String`; PyO3 still creates the Python `str`
required by ASGI. Its median throughput was 1.4% lower under asyncio and 1.5%
lower under uvloop than main, with slightly higher server CPU and p95 latency.
Because the reports ran sequentially, those small shifts do not establish
causality, and this change showed no repeatable performance gain. The
implementation was later cherry-picked to `main` as `4a28c7a94` and remains in
the current runtime; that code decision does not change this benchmark result
or support a performance claim. The original experimental branch
`codex/ws-text-ownership` remains preserved.

The main report is bound to commit `58ed76536b21a687fb37c38f3b275fc756fcf537`
and source SHA-256
`c6b26abf783c4221270b77da3a087ae174c2f8acbec77f94ed5644d7ccdf5ac8`; its
extension hash was stable at
`fe8862b21378fe3ea263919827fb364e375dc09c8b462256cafa0c3823f44efb`. The
candidate is commit `956a03ee453208d5f1b701579d5d9a6f5c0a849e`, source SHA-256
`1a3db6f22c3c866300533c7e977159c5e03a596c925021d0a3110c01ee9ef026`, with
stable extension hash
`00eba443136bb086e30efdc6e7f43ae047b933b88e0eb5d3286eb1011abbe863`. Both
used the same benchmark-client SHA-256
`3264cf234af4dcead659dd4e5b16005b62096ad698649f36450d6649b8`. The
focused `websocket.text-and-binary-round-trip` parity case passed on current
main and the candidate on Linux x86-64; the candidate also passed locally on
macOS arm64. Raw reports and server logs remain in
ignored `target/wh9k-websocket-2026-10-21/` and
`target/wh9k-websocket-candidate-2026-10-21/`; no report or log is committed.

## Peer-read buffer reuse candidate (Linux x86-64; 2026-10-21; diagnostic only)

This experiment compared `main` with a candidate that recycles bounded
`BytesMut` buffers in the proactive peer-read path. It used the stock FastAPI
`POST /upload/1048576` route, sending a 1 MiB body in 1 KiB writes at
concurrency 8. Both cohorts used CPython 3.12.13, FastAPI 0.142.4, Starlette
1.7.0, Uvicorn 0.54.0, Rust 1.91.1, Node 22.15.0, and the same AMD Ryzen 5
2600X Linux host (12 logical CPUs, kernel `7.0.0-38-generic`). Each used a
1-second warmup, 5-second sample window, five repetitions, and seed
`20261021`. The verified Uvicorn oracle and complete response-body checks were
used in both cohorts. The candidate cohort ran first; the main cohort followed
about two minutes later.

All 20 rows in the main cohort and all 20 candidate rows passed response and
server-lifecycle checks. The timing guard accepted all 20 main rows and 19/20
candidate rows; candidate asyncio repetition 4 was excluded for unrelated host
CPU activity. The table gives medians over timing-valid rows. Delta is the
candidate change relative to main.

| Loop | Valid rows main/candidate | Req/s main/candidate | Latency p50 / p95 / p99 ms main/candidate | Server CPU µs/request main/candidate | Server RSS MiB main/candidate | Client CPU µs/request main/candidate | Client RSS MiB main/candidate |
|---|---:|---:|---:|---:|---:|---:|---:|
| asyncio | 5/5, 4/5 | 976.6 / 987.9 (+1.2%) | 7.90 / 11.30 / 13.19; 7.71 / 11.62 / 14.23 | 1,689.5 / 1,641.9 | 59.73 / 59.46 | 983.2 / 1,031.5 | 96.09 / 99.03 |
| uvloop | 5/5, 5/5 | 1,221.7 / 1,186.7 (-2.9%) | 5.71 / 10.36 / 12.40; 5.85 / 10.59 / 12.71 | 1,117.6 / 1,159.0 | 61.52 / 61.71 | 914.3 / 917.0 | 97.94 / 99.63 |

The small asyncio throughput increase did not repeat under uvloop, and p95
latency rose in both candidate rows. The Uvicorn asyncio control also moved
from 881 req/s in the candidate cohort to 1,078 req/s in the later main cohort,
showing substantial between-cohort variation. These sequential runs therefore
do not establish a causal or repeatable gain. Four focused candidate parity
probes passed: H1 upload streaming, H1 slow-reader resource bounds, H2 upload,
and WebSocket text/binary round-trip. The candidate is not merged to `main`.

The measured main revision was `1f46d48d48beb7320c34a094820c8b7de0634bd7`
with stable source SHA-256
`1ef85731054342f297f3cdae01fc9492c6afca0962eaf4ea2c30be191f72895f` and
native extension SHA-256
`7d8d0e5fbaab1f39ea65ffc1ed2ab256494c750a15c6c4e23cb1c549547abf24`. The
measured candidate was the same tree as local experiment commit
`0277e3e7abbd77562e813356f91b923edca31883` (candidate build revision
`768ae0a7caebfb78798ca1b81d160bbba62a390b`), with stable source SHA-256
`ce1a28e26480dc05b54143b04111e3055c960645b2614bfe67ebe231d0822343` and
native extension SHA-256
`a704c7832ad1f0b6b3ed888fa24fba9b8384d38d8a2d4aa3118830b0096bfa87`. The
raw reports remain outside Git under the Linux host's ignored `target/`
directories; no report or server log is committed.

## Tokio blocking-pool cap decision (2026-10-17)

The completed Linux x86-64 FastAPI upload comparison found no repeatable
benefit from limiting Tokio's blocking pool. Uvicorn was faster in all twelve
matched workload/loop cells; the Rust/Uvicorn throughput ratios ranged from
0.247x to 0.445x. The custom runtime cap and its five startup contracts were
removed. See the [complete measurements](benchmark-results.md#final-tokio-blocking-pool-cap-experiment-2026-10-17)
and the [benchmark runbook](benchmarks.md#historical-tokio-blocking-pool-cap-experiment).

## Focused current-main upload-timeout reproduction (Linux x86-64; 2026-10-20; unqualified)

This one-repetition reproduction used a clean detached worktree at exact main
commit `161af844cddefacd52504eb2edc4aeb931427105` on the AMD Ryzen 5 2600X
Linux x86-64 host (12 logical CPUs, kernel `7.0.0-38-generic`). Both Python
environments used CPython 3.12.3, FastAPI 0.142.4, Starlette 1.7.0, Pydantic
2.13.5, uvloop 0.23.0, and httptools 0.8.0; the reference was stock Uvicorn
0.54.0. Rust was 1.91.1. The native C client used libcurl 8.5.0 and retained
the 15-second request timeout.

The input was FastAPI `POST /upload/1048576`: a 1 MiB request body sent in 1
KiB writes at concurrency 8, with a 1-second warmup and 5-second sample. One
sample ran for each server under asyncio. Uvicorn completed 3,059 requests and
uvicorn-rs 2,312; both had zero request failures, matched every response body,
and shut down cleanly. Neither run reproduced the timeout.

Unrelated host CPU activity peaked at 209.2% of one core, so the timing guard
rejected both rows. Their observed values are diagnostic only, not a
performance comparison:

| Server | Requests/s | p50 / p95 / p99 ms | Server CPU µs/request | Peak server RSS MiB | Timing status |
|---|---:|---:|---:|---:|---|
| Uvicorn + asyncio + httptools | 610.8 | 13.16 / 16.04 / 17.71 | 1,625 | 56.61 | Invalid: unrelated host CPU |
| uvicorn-rs + asyncio | 461.5 | 17.28 / 20.64 / 22.09 | 3,179 | 62.31 | Invalid: unrelated host CPU |

The benchmark source digest was
`4972c0199c597e6adc0270e17e682e4271457fb7aaf7903b0c60b233f8e611e4`; the
native extension SHA-256 was
`bcd02ee53b7aa97c2a30d565b22142666b46b305e1c95568efa60fe8295663dd` before
and after both samples. Raw JSON and logs remain outside Git in
`/home/appunni/work/uvicorn-rs-main-161af/target/`. This non-reproduction does
not establish a root cause or justify a server change. The timing cannot be
used to rank the servers.

## Earlier current-main FastAPI upload attempts (Linux x86-64; 2026-10-20; unqualified)

These source-tree attempts used a clean detached worktree at then-current
`origin/main` commit `0bd5877529e8f8b7434b7f7ab1852c0753f5e642` on an AMD Ryzen 5 2600X
host (12 logical CPUs, Linux x86-64, kernel `7.0.0-38-generic`). It built the
Rust release cdylib with `cargo build --release --locked` and loaded it from the
worktree through `PYTHONPATH`; it did not measure an installed wheel or a fresh
Python environment. The matched Python environment used CPython 3.12.13,
FastAPI 0.142.4, Uvicorn 0.54.0, uvloop 0.23.0, and httptools 0.8.0; Rust was
1.91.1 and the Node.js load client was 22.15.0.

The only workload was FastAPI `POST /upload/1048576`, sending a 1 MiB body in
1 KiB client writes at concurrency 8, with a 1-second warmup, 5-second samples,
and five repetitions for each server/loop variant. All 20 rows passed response
body checks and server shutdown checks. Host activity invalidated 17 timing
rows: only one Uvicorn/asyncio row and two Uvicorn/uvloop rows were valid, with
zero valid Rust rows. The report therefore has no qualified matched pair and
null aggregate performance metrics. It provides no speed, latency, CPU, or
memory conclusion. Raw JSON and per-row logs remain on the host at
`/home/appunni/work/uvicorn-rs-main-bench-20261020/target/benchmark-categories/fastapi-upload-1m-write-1k.json`.

The host uses `perf_event_paranoid=4`, which prevented on-CPU perf sampling.
A second run with the same workload and settings completed all 20 rows, with
18 timing-valid rows: Rust/asyncio had 3/5 valid rows and each other server/loop
variant had 5/5. The independent valid-row medians were:

| Loop | Server | Valid rows | Requests/s | p50 / p95 / p99 ms | Server CPU µs/request | Peak RSS MiB |
|---|---|---:|---:|---:|---:|---:|
| asyncio | Uvicorn | 5/5 | 993.8 | 7.79 / 11.90 / 13.59 | 946.5 | 55.1 |
| asyncio | uvicorn-rs | 3/5 | 829.1 | 9.52 / 12.55 / 14.22 | 2,012.5 | 57.9 |
| uvloop | Uvicorn | 5/5 | 761.7 | 10.14 / 13.92 / 15.56 | 1,302.2 | 56.4 |
| uvloop | uvicorn-rs | 5/5 | 970.5 | 8.16 / 11.71 / 13.84 | 1,556.8 | 60.6 |

These are per-server medians, not a complete matched-pair result: two
Rust/asyncio rows were invalidated by unrelated host CPU activity. The
uvloop-only numbers are a signal to investigate, not a repeatable multi-workload
gain. The second report is retained on the host at
`/home/appunni/work/uvicorn-rs-main-bench-20261020/target/benchmark-categories/fastapi-upload-1m-write-1k-repeat-2.json`
with SHA-256
`b09e77270a907aa25366629d6b996f21722c660a334e1afcd18c66124e082bbc`.
Neither local attempt qualifies performance acceptance; use a quiet, isolated
host and require matched valid repetitions before drawing a conclusion.

## Latest qualified hosted FastAPI upload comparison (GitHub run #148; 2026-10-20)

[Run #148](https://github.com/appunni-m/uvicorn-rs/actions/runs/39388518337)
completed its correctness-gated comparison on experimental commit
[`6ca0cb4b46ca4fdb0ed87d548e4cb984e084e716`](https://github.com/appunni-m/uvicorn-rs/commit/6ca0cb4b46ca4fdb0ed87d548e4cb984e084e716).
The [raw artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39388518337/artifacts/12248129429)
contains all 20 rows, per-server logs, source and extension identities, and
the excluded timing row.

This measured ordinary FastAPI 0.142.4 with CPython 3.12.13 on a
four-logical-CPU Linux ARM64 runner (kernel `7.0.0-1017-azure`, glibc 2.39).
Rust was 1.98.1; the reference was Uvicorn 0.54.0 with httptools 0.8.0, and
the native libcurl client was 8.5.0. The app handled
`POST /upload/1048576` with `Request.body()`: each request carried 1 MiB in
1 KiB client writes, at concurrency 8, with a 1-second warmup, a 5-second
measurement window, and five repetitions per server. Both servers used
persistent HTTP/1.1 connections. Every measured response status and complete
body matched the workload oracle. Four asyncio pairs and all five uvloop pairs
qualified; Uvicorn asyncio repetition 1 was excluded because the runner
observer detected unrelated host CPU activity.

| Loop | Matched repetitions | Throughput, Uvicorn → Rust (Rust/reference) | p50 / p95 / p99 ms, Uvicorn → Rust | Server CPU µs/request, Uvicorn → Rust | Peak server RSS MiB, Uvicorn → Rust | Client CPU µs/request, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| asyncio | 2–5 (4 pairs) | 654 → 514 req/s (0.784×) | 12.37 / 16.71 / 19.42 → 15.37 / 20.64 / 23.13 | 1,471 → 1,876 | 56.28 → 60.66 | 4,416 → 4,359 |
| uvloop | 1–5 (5 pairs) | 643 → 552 req/s (0.859×) | 12.49 / 17.00 / 20.30 → 14.35 / 19.34 / 21.77 | 1,496 → 1,643 | 58.38 → 62.04 | 4,475 → 4,425 |

For this workload, uvicorn-rs had lower throughput and higher latency and
server CPU per request under both event loops. Client CPU per request was
similar, which points to extra server-side work as a measurement signal; these
measurements do not identify the responsible function or prove a cause. The
closed-loop client does not represent an open-loop offered-rate test, and the
latencies include client work. This is one workload on one system, not a
multi-system performance result or a release-wide claim.

The run also repeated the earlier lifecycle observation: all five normal-build
uvicorn-rs asyncio and all five uvicorn-rs uvloop repetitions shut down with
return code 0, without forced cleanup, panic, or native-error diagnostics. The
intermittent SIGSEGV from [run #143](https://github.com/appunni-m/uvicorn-rs/actions/runs/39383067488)
did not recur in this comparison. Its root cause remains unknown.

## Focused per-thread CPU profile for FastAPI upload (Linux x86-64; 2026-10-20; diagnostic only)

A one-repetition signal-gated CPU profile ran the same stock FastAPI
`POST /upload/1048576` request-body workload on Linux x86-64 (AMD Ryzen 5
2600X, 12 logical CPUs, kernel 7.0.0-38-generic), using commit
[`6ca0cb4b46ca4fdb0ed87d548e4cb984e084e716`](https://github.com/appunni-m/uvicorn-rs/commit/6ca0cb4b46ca4fdb0ed87d548e4cb984e084e716).
Both environments used the same CPython 3.12.3 executable, FastAPI 0.142.4,
Starlette 1.7.0, Pydantic 2.13.5, and httptools 0.8.0. Uvicorn was 0.54.0;
the client was Node.js 25.1.0. The request carried 1 MiB in 1 KiB writes at
concurrency 8, with a 1-second warmup and 5-second sample. Every response
passed its status/body check and both servers shut down cleanly.

Rust was built with `rustc 1.91.1`. Both Python environments resolve to the
same `/usr/bin/python3.12` executable (SHA-256
`e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f`). The
measurement guard saw stable source inventory
`a0468533b651759cf3a8ba1443fe27584f6e9050156b37666aa6b2e6861d44f4` and
native extension
`6e90e8679e53ecace87e42e03ab3cb5494d35a6a197bb5d6231ff3d535915081` before
and after each row.

| Server | Completed requests | Process CPU | Python event-loop thread CPU | Other server-thread CPU | CPU/request |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + asyncio | 3,872 | 4.905 s | 4.905 s | <0.001 s | 1,273 µs |
| uvicorn-rs + asyncio | 4,646 | 8.027 s | 3.829 s | 4.198 s | 1,750 µs |

The host observer reported unrelated CPU activity peaks of 177.2% during the
Rust sample and 189.4% during the Uvicorn sample. The runner marked both rows
unrankable, and this one repetition is not a performance comparison. Its
per-thread counters show that the Rust process used less CPU on the Python
event-loop thread while spending 4.198 CPU seconds on other process threads.
The native runtime configures one Tokio async worker; the OS snapshot contained
seven threads named `tokio-rt-worker`, with one using 3.099 CPU seconds and the
other six using 1.100 seconds combined. The snapshot records thread CPU and
names, not which Tokio task ran on each thread, so it does not identify a
function-level cause.

The body bridge has one required copy direction and one zero-copy direction.
For incoming requests, Rust retains Hyper's body chunks as `Bytes`, then
materializes the immutable Python `bytes` required by the ASGI `http.request`
event. A single chunk uses one Python allocation and copy; multiple chunks are
copied directly into one final Python allocation. The diagnostic counter
`http_request_python_bytes_copied` records the copied payload size. For an
application response whose body is Python `bytes`, PyO3's `Bytes` extractor
uses `PyBackedBytes` as the owner of `bytes::Bytes`, so Rust can retain and
write the original immutable payload without copying it. A `bytearray` response
is accepted by this extractor but is copied into Rust-owned storage. These
observations describe the current bridge; they do not establish that body
materialization is the cause of the measured CPU difference. Eliminating the
request-side copy while preserving the ASGI `bytes` contract would require a
different boundary representation, so the Rust-native service path remains the
route that removes Python payload materialization entirely.

The signal-gated report, per-thread profiles, source/bootstrap copies, and
server logs are local-only ignored artifacts under
`target/benchmark-diagnostics/20261020-cpu/loopcpu/`. A separate `py-spy`
capture showed PyO3 and `make_http_request_message` on the Rust request path;
its samples are wall-time stacks, so they do not quantify CPU cost. The next
useful measurement is a repeat at a quiet host load, followed by permitted
on-CPU function profiling before changing the bridge. The normal hosted ARM64
run #148 remains the performance comparison for this workload.

### Second single-repetition attempt (rejected by host-load guard)

A repeat of the same 1 MiB upload workload used the same clean source and
native-extension identities. Both servers passed body validation and shut down
cleanly, with zero request failures. It again failed the host-load guard:
unrelated CPU activity peaked at 215.1%, so these timing values are diagnostic
only and cannot rank either implementation.

| Server | Completed requests | Throughput | p95 latency | Process CPU | CPU/request |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + asyncio | 4,607 | 920.6 req/s | 12.15 ms | 4.748 s | 1,031 µs |
| uvicorn-rs + asyncio | 4,615 | 922.2 req/s | 13.53 ms | 7.127 s | 1,545 µs |

The close observed throughput and higher Rust CPU are not performance evidence
because unrelated host work invalidated the sample. Per-thread CPU still
showed 3.529 seconds on the Rust Python event-loop thread and 3.599 seconds on
other server threads. The complete diagnostic artifacts remain in the ignored
`target/bench-profile/loopcpu-matched-upload-20261020-run3/` directory of the
diagnostic worktree. The measurement used the same source digest and extension
SHA-256 listed above.

## Earlier focused FastAPI benchmark attempt (GitHub run #98; 2026-10-19; unqualified)

GitHub Actions run [#98](https://github.com/appunni-m/uvicorn-rs/actions/runs/39277104993)
completed with failure on `main` at commit
[`0bd5877529e8f8b7434b7f7ab1852c0753f5e642`](https://github.com/appunni-m/uvicorn-rs/commit/0bd5877529e8f8b7434b7f7ab1852c0753f5e642).
The focused Linux ARM64 job used Ubuntu 24.04.5, kernel
`6.17.0-1022-azure`, and a four-core Neoverse-N2 runner. It used CPython
3.12.13, Rust 1.98.1, GCC 13.3.0, libcurl 8.5.0, FastAPI 0.142.4, Uvicorn
0.54.0, uvloop 0.23.0, and httptools 0.8.0. It measured the stock FastAPI
`POST /upload/1048576` route, which consumes the full 1 MiB request with
`Request.body()` and returns its byte count. The client limited each libcurl
upload callback to 1 KiB. The effective workload concurrency was 8, with a
5-second load window, 1-second warmup, and five repetitions. The dispatch-level
requested concurrency was 64; the per-workload metadata and all raw rows record
the effective concurrency of 8.

The artifact contains 20 rows. One Rust/asyncio row was excluded for unrelated
host CPU activity. Two Rust/uvloop rows failed correctness gating: libcurl
timed out after 15 seconds on repetitions 2 and 3. Both failures report the
full 1 MiB submitted by libcurl, zero response bytes, no response status or
first-byte time, and `new_connections=0` (the worker reused its persistent
HTTP/1.1 connection). In both server logs, FastAPI's `Request.body()` raises
Starlette `ClientDisconnect`; Starlette's error middleware then tries to start
a response after the client has disconnected, and the Rust ASGI adapter
rejects that late response start. These are downstream effects of the client's
timeout, not evidence that the application raised an unrelated error. The
tracebacks also establish that the application did not receive the complete
body before the timeout. Libcurl's upload count is bytes submitted by the
client, not proof that the server delivered them to ASGI. Server shutdown
passed for valid rows; the failed rows do not have a passed lifecycle
assessment. This brackets the failure to the request-consumption path before
response headers; it does not identify whether protocol reading, body-pump
backpressure, task scheduling, or Python delivery is the stalled operation.
The benchmark job is unqualified despite having four valid asyncio matched
pairs and three valid uvloop matched pairs, because the run contained request
failures.

The runner's older client reports completed requests divided by wall time
including post-window drain. It did not retain completion timestamps relative
to the 5-second deadline. Since each of the eight client workers has at most
one request in flight, at most eight completions can occur during drain. The
following conservative bounds use `(requests - 8) / 5s` through `requests /
5s` per row, then take the median of matched per-repetition Rust/Uvicorn
ratios. These are descriptive bounds, not exact in-window counts or a
statistical-significance claim.

| Loop | Valid matched repetitions | Median paired load-window throughput ratio, Rust/Uvicorn | Median p50 / p95 / p99 ms, Uvicorn → Rust | Server CPU µs/request, Uvicorn → Rust | Peak server RSS MiB, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: | ---: |
| asyncio | 4 (repetitions 2–5) | 0.714–0.718× | 10.861 / 15.343 / 18.211 → 7.272 / 11.030 / 110.932 | 1,245 → 2,293 (+84%) | 56.90 → 58.78 |
| uvloop | 3 (repetitions 1, 4, 5) | 0.764–0.768× | 10.939 / 15.004 / 17.546 → 8.829 / 14.084 / 18.999 | 1,303 → 1,956 (+50%) | 58.45 → 62.02 |

The run therefore indicates a workload-specific sustained-throughput gap of
about 28% with asyncio and 23% with uvloop among the valid matched samples.
Server CPU per request is higher in both comparisons. Reported client CPU per
request is similar for asyncio and lower for the Rust/uvloop rows, so client
CPU alone does not explain the difference. Rust/asyncio's median per-run p99
is elevated by two long-tail repetitions even though its median p50 and p95
are lower. These measurements show extra server-side work and unstable tails;
they do not attribute that work to a particular Rust function.

For this Python-only FastAPI workload, the server has to move request-body
events from the Rust HTTP runtime across the ASGI/Python boundary. The Rust
bridge batches Hyper body segments, then materializes each ASGI body message as
Python `bytes`; `Request.body()` subsequently buffers the body in Python. The
HTTP/1.1 code also uses a bounded request channel between the body pump and
ASGI receiver. These are concrete places to measure. They are not proof that
the boundary copy or channel caused the timeouts or the full throughput gap.
The earlier instrumented ASGI-stage run measured about 1 MiB of Python-byte
materialization per request, but its timing was invalid for performance
ranking. The focused connection-policy diagnostic below did not reproduce the
ARM64 timeout. It also cannot identify the receive-path stall because it used a
different CPU architecture, Rust compiler, and HTTP client. A same-client
reproduction and receive-path timing are still needed before selecting an
optimization.

### Same-source x86 connection-policy diagnostic (2026-10-19; diagnostic only)

A focused comparison used the run #98 source revision and native extension on
Linux x86-64 (AMD Ryzen 5 2600X, 12 logical CPUs), with CPython 3.12.13,
FastAPI 0.142.4, Starlette 1.7.0, Pydantic 2.13.5, Uvicorn 0.54.0, uvloop
0.23.0, and httptools 0.8.0. The normal release extension was built with
`rustc 1.91.1`; the ARM64 run used Rust 1.98.1. The benchmark sent the same
stock FastAPI 1 MiB `Request.body()` upload in 1 KiB client writes at
concurrency 8, with a 1-second warmup, 5-second load window, and three
repetitions per server and mode. Both servers used uvloop; Uvicorn used
httptools. This host lacked libcurl development headers, so the driver used
Node.js 22.15.0. The ARM64 run used the native libcurl client.

The input comparison left the HTTP/1.1 default persistent connection policy
unchanged in one mode and added `Connection: close` in the other. Results are
medians across three samples; all 12 rows had zero request failures, valid
timing under the harness, and passed server lifecycle checks.

| Connection policy | Median drain-inclusive req/s, Uvicorn → Rust | Median paired 5-second rate-ratio bound, Rust/Uvicorn | Median p50 / p95 / p99 ms, Uvicorn → Rust | Server CPU µs/request, Uvicorn → Rust | Client CPU µs/request, Uvicorn → Rust | Peak server RSS MiB, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HTTP/1.1 default persistence | 795 → 947 | 1.130–1.134× | 9.77 / 13.98 / 16.69 → 8.12 / 12.64 / 15.79 | 1,220 → 1,571 (+29%) | 1,126 → 984 | 56.45 → 61.66 |
| `Connection: close` | 585 → 744 | 1.256–1.262× | 13.20 / 18.93 / 21.11 → 10.61 / 13.99 / 16.09 | 1,681 → 1,953 (+16%) | 1,370 → 1,182 | 54.13 → 59.47 |

The completed requests-per-second medians include the client's completion
drain. The client does not record completion timestamps relative to its
five-second deadline, so the paired ratio bounds allow up to eight in-flight
requests to complete during drain. Client CPU/request includes process setup,
drain, and reporting overhead. Closing each connection reduced the
per-server median completed rate by about 21% for Rust and 26% for Uvicorn;
neither server timed out or disconnected. This does not support connection
reuse alone as the cause of the ARM64 failure. In this three-repetition x86
diagnostic Rust completed requests faster, while consuming more server CPU per
request. The host observer recorded unrelated desktop activity reaching 0.90
of one core, and the client, CPU architecture, and compiler differ from run
#98. Treat these numbers as a diagnostic comparison, not as a qualified
performance claim or a reversal of the ARM64 result.

The locally retained report and driver are
`target/benchmark-diagnostics/20261019-connreuse/uvicorn-rs-connreuse-0bd5877-debug1.json`,
`target/benchmark-diagnostics/20261019-connreuse/uvicorn-rs-connreuse-0bd5877-debug1.jsonl`,
and `target/benchmark-diagnostics/20261019-connreuse/uvicorn-rs-connreuse-probe.py`.
They are ignored local artifacts. The measured source inventory SHA-256 was
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7`; the
native extension SHA-256 was
`518e629c7b91906e4adda77f85675e297ffbd090a85e07084abae4d369fc528c`.

The [focused job log](https://github.com/appunni-m/uvicorn-rs/actions/runs/39277104993/job/118144250781)
and [raw benchmark artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39277104993/artifacts/12198097403)
retain the report, all per-repetition rows, environment, and server logs. The
measurement source inventory SHA-256 was
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7` before
and after the run.

### Hyper HTTP/1.1 read-buffer cap diagnostic (2026-10-19; not adopted)

To test whether Hyper's connection-buffer limit contributed to the focused
FastAPI upload cost, I changed only `builder.http1().max_buf_size(...)` in a
detached worktree at the run #98 source commit: from 64 KiB to 256 KiB. The
limit bounds Hyper's HTTP/1 connection buffer; it is not a request to allocate
that amount for every connection ([Hyper 1.11.1 builder source](https://docs.rs/hyper/1.11.1/src/hyper/server/conn/http1.rs.html)).
The 256 KiB change was not applied to this checkout.

The workload was stock FastAPI 0.142.4 / Starlette 1.7.0,
`POST /upload/1048576` with `Request.body()`, 1 MiB per request in 1 KiB Node.js
22.15.0 client writes, concurrency 8, one-second warmup, and a five-second
measurement window. Both servers used CPython 3.12.13 and uvloop 0.23.0;
Uvicorn 0.54.0 used httptools 0.8.0. The Uvicorn process used a separate
environment with the same pinned Python dependencies and no `uvicorn_rs`
module. Host: AMD Ryzen 5 2600X, Linux x86-64, 12 logical CPUs; Rust 1.91.1.

Each reported row had zero request failures and passed graceful shutdown. All
three 256 KiB pairs passed the timing gate. The baseline needed four attempts:
three pairs were timing-valid, while one Rust row was excluded for unrelated
host CPU activity of 113.7% of one core. That invalid row passed behavior and
shutdown. The paired ratios below are medians of the valid per-run
Rust/Uvicorn ratios; per-server rates and resource values are medians over the
same paired rows. The rate is the harness's reported completed requests per
second, not a claim that the two processes ran under identical instantaneous
host load.

| Variant | Valid pairs | Median Uvicorn → Rust req/s | Median paired Rust/Uvicorn rate ratio | Median p50 / p95 / p99 ms, Uvicorn → Rust | Server CPU µs/request, Uvicorn → Rust | Peak server RSS MiB, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 64 KiB baseline | 3 | 752 → 901 | 1.205× | 10.24 / 14.26 / 16.61 → 8.51 / 12.84 / 16.33 | 1,322 → 1,701 (+29%) | 56.2 → 61.3 |
| 256 KiB cap | 3 | 999 → 952 | 0.954× | 7.04 / 13.79 / 16.58 → 8.01 / 12.56 / 16.22 | 847 → 1,569 (+85%) | 55.6 → 60.7 |

The Rust-only median moved from 901 to 952 req/s and from 1,701 to 1,569
server CPU µs/request, but the paired comparison did not improve: the baseline
ratios were 1.239×, 1.205×, and 1.137×; the 256 KiB ratios were 1.191×,
0.954×, and 0.764×. Uvicorn's measured rate also varied substantially across
these short runs, so the result does not establish that the buffer change
caused either a gain or a regression. It provides no evidence that this cap
explains the ARM64 upload timeout. I am not adopting the change; a quieter,
same-host alternating comparison or the same focused case on a clean runner is
needed before treating a small Rust-only median shift as a performance win.

Baseline source inventory SHA-256:
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7`; baseline
native extension SHA-256:
`518e629c7b91906e4adda77f85675e297ffbd090a85e07084abae4d369fc528c`.
The isolated 256 KiB variant source inventory SHA-256 was
`dd7410f61000cc14d960a3499aba2de5072bf5477267507a23c9d57c94c6b0c2`; its
native extension SHA-256 was
`22d1e3e78374e4490cd4b07161df49a9e53716c1bcca0cf56e9d2cf86c8c34e8`.
The local raw reports, rejected baseline sample, per-row logs, and benchmark
driver are retained under
`target/benchmark-diagnostics/20261019-bufcap/uvicorn-rs-bufread-20261019/`;
these are ignored diagnostic artifacts, not release benchmark results.

## FastAPI upload per-thread CPU diagnostic (2026-10-19; diagnostic only)

I ran one profile pair on the Linux x86-64 host for the same stock FastAPI
`POST /upload/1048576` workload: `Request.body()`, 1 MiB request bodies sent in
1 KiB writes, concurrency 8, CPython 3.12.13, FastAPI 0.142.4, Starlette 1.7.0,
and uvloop 0.23.0. Uvicorn 0.54.0 used httptools 0.8.0 from its isolated oracle
environment; uvicorn-rs imported the native extension built from the exact
source checkout at commit
[`0bd5877529e8f8b7434b7f7ab1852c0753f5e642`](https://github.com/appunni-m/uvicorn-rs/commit/0bd5877529e8f8b7434b7f7ab1852c0753f5e642).
Both rows had zero request failures and passed graceful shutdown.

| Server | Completed requests | Server CPU | Event-loop thread CPU | Other server-thread CPU |
| --- | ---: | ---: | ---: | ---: |
| Uvicorn + uvloop | 3,635 | 4.95 s; 1,365 µs/request | 4.95 s | 0.00 s |
| uvicorn-rs + uvloop | 4,669 | 7.28 s; 1,572 µs/request | 2.75 s | 4.53 s |

This single short pair is not rankable: the host observer saw large unrelated
CPU bursts, and the profiler deliberately marks its output diagnostic-only.
It does show the workload split. The Python event-loop thread used about 2.2 s
less CPU with uvicorn-rs, while the Rust server process used about 2.3 s more
total CPU and about 15% more server CPU per completed request. The per-thread
snapshot recorded one dominant Tokio-named thread at 3.99 s and six smaller
Tokio-named threads totaling about 0.54 s. `src/lib.rs` configures one Tokio
async worker. The additional thread names are consistent with Tokio's blocking
pool, but the snapshot does not identify each thread's task.

### Runtime-counter follow-up (one Rust-only diagnostic run)

I rebuilt the exact source with the `runtime-diagnostics` feature and ran only
the same upload case against uvicorn-rs. It passed the body oracle and graceful
shutdown; host CPU activity again invalidated its timing. Runtime counters
cover server startup, warmup, measurement, and drain, so the normalized values
below use the 5,676 counted requests (the load window itself completed 4,847).

| Counter | Per request | What it measures |
| --- | ---: | --- |
| Immediate ASGI receives | 2.31 | `receive()` calls answered from the ready Rust queue |
| Pending receive futures | 3.69 | `receive()` calls returned as PyO3 futures |
| HTTP body data frames | 65.01 | Hyper body frames read by Rust |
| Python body-byte materializations | 6.00 | ASGI `http.request` messages / Rust-to-Python byte conversions |
| Bytes copied into Python | 1,048,576 | Full 1 MiB request body per request |
| Byte materialization elapsed time | 210 µs | Time inside `Bytes`-to-Python-bytes conversion; elapsed time, not a CPU counter |
| Python task scheduling delay | 133 µs | Time from scheduling an ASGI task until its Python loop callback runs |
| Python attach wait | 49.6 µs | Time acquiring the GIL to register the ASGI task |

The measured body pump batches about 65 Hyper data frames into six ASGI body
messages per request. Of those six `receive()` calls, about 3.69 wait for data
and return a PyO3 future. In `pyo3-async-runtimes`, completing each such Rust
future schedules a `spawn_blocking` callback that attaches to Python and
resolves the captured event-loop future. That makes roughly 3.69 blocking-pool
completion jobs per request a concrete candidate for the additional server
CPU. The earlier per-thread profile's extra Tokio-named threads are consistent
with this path, but do not identify those jobs individually. The byte-copy
counter also confirms one full body copy into Python, split across six
materializations. The measured conversion duration is about 210 µs per request;
this is elapsed time rather than CPU time, so it cannot be treated as an
additive share of the 1.57 ms/request CPU reading from the earlier pair.

This narrows the optimization target to receive completion scheduling and
message batching. It does not yet assign CPU to either one: elapsed conversion
and scheduling-wait counters are not CPU profiles, and the waits overlap across
concurrent uploads. Any bridge change should first preserve body streaming,
backpressure, loop ownership, context, and cancellation, then rerun this one
correctness-gated upload case before expanding the matrix. The runtime-feature
extension used for this run had SHA-256
`069452323d65f533adaa545cc6a2caf758e1e6aeb0a5ebd21f6749c51f66c085`; the
normal extension was restored after the diagnostic.

### Request-body batch-cap experiment (2026-10-19; not adopted)

I changed only `HTTP_REQUEST_BODY_BATCH_BYTES` from 256 KiB to 512 KiB in an
isolated build, kept the 5 ms flush deadline, and ran the same single FastAPI
upload workload for five repetitions per version. Both versions used the same
stock FastAPI/Uvicorn environments, CPython 3.12.13, uvloop 0.23.0, and Linux
x86-64 host. Every row passed request correctness and graceful shutdown. The
512 KiB build also passed the single
`http1.request-streaming-progress-before-upload-complete` parity case.

| Body batch cap | Valid Uvicorn/Rust pairs | Body messages / pending receives per request | Median Rust req/s | Median Rust CPU µs/request | Median paired Rust/Uvicorn rate ratio | Median paired CPU/request ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 256 KiB | 3 of 5 | 6.00 / 3.69 | 952.5 | 1,553 | 1.299× | 1.148× |
| 512 KiB | 5 of 5 | 4.00 / 2.83 | 919.0 | 1,596 | 1.212× | 1.257× |

The 256 KiB pair medians use only repetitions 1, 4, and 5; two Rust rows were
excluded for unrelated host CPU activity. The 512 KiB run had five valid
matches, but the host still showed intermittent unrelated CPU load and the
two variants were measured sequentially. These are a focused diagnostic, not
a release performance claim. The 512 KiB cap reduced body messages and
pending receives, but its median Rust rate was 3.5% lower and its CPU per
request was 2.8% higher than the valid 256 KiB Rust rows. It supplies no
repeatable gain, so I did not adopt it.

A separate 1 MiB-cap counter run reduced body messages to 2.35 and pending
receives to 1.74 per request, but increased 5 ms timeout flushes to 0.35 per
request. It also passed the upload oracle and streaming-progress parity case;
its instrumented timing is not suitable for a performance comparison. Raising
the cap trades fewer Python crossings for longer buffering and more timeout
flushes. The current evidence favors keeping 256 KiB while measuring the
`future_into_py` completion path directly.

The normal 256 KiB build's source inventory SHA-256 was
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7`, and its
native extension SHA-256 was
`22d1e3e78374e4490cd4b07161df49a9e53716c1bcca0cf56e9d2cf86c8c34e8`. The
512 KiB build source inventory SHA-256 was
`b3b59edc53c4e83dee9b7518ae56cbf43be48e53f2eaee044308b9161959205d`, and its
native extension SHA-256 was
`e9ad56c309dd4c970e72b8bb123dbb2790207943350c35fc188faa27f768bc94`. The
source and native extension were restored to the 256 KiB build afterward.

Reports, per-row logs, parity outputs, and instrumented counter runs are
retained under
`target/benchmark-diagnostics/20261019-loopcpu/`. They are ignored local
diagnostics and are not release benchmark results.

Raw per-thread profile, runtime counters, bootstrap, logs, and benchmark
identity are retained under
`target/benchmark-diagnostics/20261019-loopcpu/fastapi-upload-loopcpu-20261019-3/`.
The runtime-counter report is under
`target/benchmark-diagnostics/20261019-loopcpu/receive-future-counters-20261019/`.
The measured source inventory SHA-256 was
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7`; the
native extension SHA-256 was
`518e629c7b91906e4adda77f85675e297ffbd090a85e07084abae4d369fc528c`.

## Previous qualified focused FastAPI matched timing (GitHub run #97; 2026-10-19)


GitHub Actions run [#97](https://github.com/appunni-m/uvicorn-rs/actions/runs/39269349267)
completed successfully on `main` at commit
[`0bd5877529e8f8b7434b7f7ab1852c0753f5e642`](https://github.com/appunni-m/uvicorn-rs/commit/0bd5877529e8f8b7434b7f7ab1852c0753f5e642).
The focused Linux ARM64 job used CPython 3.12.13 on a four-logical-CPU
`aarch64` runner and measured only `fastapi-upload-1m-write-1k`, with actual
concurrency 8, 5-second samples, a 1-second warmup, and five repetitions. The
normal release build ran without runtime or ASGI-stage instrumentation. Every
measured response status and complete body matched the workload oracle. The
report qualifies matched pairs for diagnosis: four asyncio pairs (the first
Uvicorn row was excluded for unrelated host CPU activity) and five uvloop pairs.
This minimum sample is descriptive, not a statistical-significance claim.

| Loop | Matched pairs | Drain-inclusive completed req/s Uvicorn → uvicorn-rs | p50 / p95 / p99 ms Uvicorn → uvicorn-rs | Server CPU µs/request Uvicorn → uvicorn-rs | Peak server RSS MiB Uvicorn → uvicorn-rs |
| --- | ---: | ---: | ---: | ---: | ---: |
| asyncio | 4 | 745.439 → 330.287 requests/s (0.449×) | 10.961 / 14.984 / 17.368 → 8.383 / 12.307 / 17.257 | 1,273.335 → 2,035.306 | 57.381 → 59.463 |
| uvloop | 5 | 760.512 → 516.541 requests/s (0.659×) | 10.558 / 14.823 / 16.772 → 9.715 / 13.947 / 16.651 | 1,282.119 → 1,754.098 | 57.586 → 62.426 |

The old client stopped initiating requests after each five-second window, then
waited for in-flight requests to finish. Its `duration_seconds` and
`requests_per_second` include that completion drain. Uvicorn rows took about
5.005 seconds, while Rust rows took 5.006–9.850 seconds. This makes the table's
drain-inclusive rate mix sustained throughput with tail completion time; the
0.449× and 0.659× ratios overstate the steady-state throughput gap.

The artifact records successful request counts but not each completion time
relative to the five-second deadline. With concurrency 8, at most eight of the
successful responses per row can fall in the final drain. Bounding in-window
completions by `requests - 8` and `requests` gives these median matched-pair
ranges:

| Loop | Uvicorn completions per load-window second | Rust completions per load-window second | Rust/Uvicorn matched ratio bound |
| --- | ---: | ---: | ---: |
| asyncio | 744.6–746.2 | 553.2–554.8 | 0.728–0.732× |
| uvloop | 759.6–761.2 | 608.4–610.0 | 0.806–0.810× |

This is a real workload-specific throughput regression of about 27% with
asyncio and 19% with uvloop, but it is smaller than the old drain-inclusive
metric suggested. Rust server CPU per request is about 60% and 37% higher,
respectively. Client CPU per request is lower for Rust, so client CPU alone
does not explain the server-side cost. The long drain shows that a small number
of Rust requests complete well after the load window; the old p50/p95/p99
summaries omit the mean, p99.9, maximum, and completion timestamps, so they do
not identify those requests' exact tail latencies or the code-level cause.

The local client now records the number of responses completed before the
deadline, drain duration, mean, p99.9, and maximum latency separately. These
fields have not yet been collected in a hosted benchmark. The next unprofiled
focused run must collect them before selecting an optimization. This result
does not justify a general claim about all workloads or protocols.

The raw [focused job log](https://github.com/appunni-m/uvicorn-rs/actions/runs/39269349267/job/118117253524)
and [benchmark artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39269349267/artifacts/12194532177)
retain all 20 rows, per-repetition logs, environment details, and the matched
summary. The report source SHA-256 is
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7`.

A separate 2026-10-19 Samply profile used this workload, uvloop, and
concurrency 8 on the local macOS ARM64 host. It is diagnostic only and is not
source- or platform-matched to run #97: the local dirty-checkout source digest
was `94759d964b8248de92ef8329d6c467f8cf683f38f2f120ae42c544716d7a1772`,
while the hosted report source digest was
`c36b5211008d29accfc39390ce2ec51814d97ef7138e54e65ad35c09e15f8fa7`. The
candidate profile attributed 70.96% of sampled server CPU to `libsystem_kernel`
(function names unresolved), 13.96% to the native extension, and 3.84% to
Python. The Uvicorn profile attributed 41.71% to `libsystem_kernel`, 38.47% to
Python, and 3.46% to the allocator. These shares are samples, not a valid
benchmark or a causal decomposition. Nine Rust threads were named
`tokio-rt-worker`; the name does not mean nine async scheduler workers, and the
profile did not identify a sampled Tokio blocking-pool loop. The unresolved
kernel frames and source/platform difference prevent attributing the hosted
regression to a call site. Do not select a code change from this profile alone.

Next diagnostic step: profile the exact hosted source on Linux for this one
workload, with usable native call stacks and the same request settings, then
change one identified cost at a time and rerun its correctness-gated matched
comparison. Do not treat the earlier instrumented run below as a timing
comparison.

## Previous focused FastAPI ASGI-stage diagnostic (GitHub run #96; 2026-10-19)

GitHub Actions run [#96](https://github.com/appunni-m/uvicorn-rs/actions/runs/39266186575)
completed successfully on `main` at commit
[`0bd5877529e8f8b7434b7f7ab1852c0753f5e642`](https://github.com/appunni-m/uvicorn-rs/commit/0bd5877529e8f8b7434b7f7ab1852c0753f5e642).
The focused Linux ARM64 job used Ubuntu 24.04.5, CPython 3.12.13, and the
`fastapi-upload-1m-write-1k` workload. Its command requested concurrency 64,
10 repetitions, 5-second samples, a 1-second warmup, and seed `20261019`.
However, the maintained workload overrides requested concurrency and the
recorded JSON rows show actual concurrency 8. This is the concurrency-8 upload
workload; the requested command-line value was not the effective value.

The job enabled both runtime counters and per-ASGI-stage timing. All 40 rows
completed with zero request failures, clean server lifecycle, zero unexpected
panics, and zero unexpected native errors. However, **0/40 rows had valid
timing**: ASGI instrumentation invalidated every row, and unrelated host CPU
activity also invalidated one or more Uvicorn rows. The rates and timings below
are diagnostic observations only, not comparative performance evidence.

| Server | Rows | Observed requests/s median* | Observed server CPU/request median* | ASGI app wall p50 median* | ASGI receive p50 median* | Valid timing rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn, asyncio + httptools | 10 | 739.5 | 1,271 µs | 7.55 ms | 7.21 ms | 0/10 |
| uvicorn-rs, asyncio | 10 | 364.3 | 2,057 µs | 6.41 ms | 6.11 ms | 0/10 |
| Uvicorn, uvloop + httptools | 10 | 741.7 | 1,274 µs | 7.81 ms | 7.46 ms | 0/10 |
| uvicorn-rs, uvloop | 10 | 401.8 | 1,928 µs | 5.90 ms | 5.57 ms | 0/10 |

\* Instrumented diagnostic values; invalid for ranking or release acceptance.

The ASGI application-call p50 and `receive()`-await p50 were lower in the
candidate rows, while observed server CPU per request was higher. Time outside
the ASGI `send()` and `receive()` awaits was similar at p50 (about 0.20 ms for
Uvicorn and 0.22 ms for uvicorn-rs). This does not point to FastAPI route work
as the dominant difference, but it does not isolate a Rust call site: stage
await durations and scheduler wait counters are elapsed wall time, not CPU
samples.

The Rust bridge recorded about four receive bridge futures per request and
materialized about 1 MiB of request data into Python `bytes` per request, with
roughly 115 µs median materialization time. The inspected `RequestBody` path
keeps Hyper `Bytes` segments until the ASGI message is received, then copies
directly into the final Python `bytes` object; it does not build an additional
contiguous Rust body buffer first. This establishes where the Python boundary
copy occurs, not that eliminating it alone would recover the CPU difference.
Further attribution needs a valid uninstrumented benchmark and CPU profiling
with usable call stacks.

The [focused job log](https://github.com/appunni-m/uvicorn-rs/actions/runs/39266186575/job/118106262803)
and [diagnostic artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39266186575/artifacts/12193203840)
retain the full rows and stage observations. The source SHA-256 was
`4ec950204b09ea80f6b94527ff2643daec8a9dfb2279e93592769bd75e1f57dc`; the
native extension SHA-256 was
`06ccb56731b23f73f49ae248d70dff456fa28074087b477d0b1fa50604fdc350`.

## Previous full-matrix validation and performance attempt (2026-10-19)

CI run [39205955886](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955886)
passed on clean main commit
[5b279d48ddf60bb26380914eaf32b13717a647fb](https://github.com/appunni-m/uvicorn-rs/commit/5b279d48ddf60bb26380914eaf32b13717a647fb).
The run passed its 761-case unified matrix with three complete repeats,
9,300/9,300 source-span regions, 6,880/6,880 normalized executable lines,
installed-wheel parity 251/251, native composition, MSRV, and package gates.
Independent Coverage-MCP review remains pending.

The matching three-system benchmark run
[39205955881](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955881)
completed public parity and the FastAPI-only comparison on all three systems.
The category matrix is incomplete: Linux x86-64 and macOS ARM64 completed their
category sequences, while Linux ARM64's HTTP/2 category exited early without a
complete category report. The aggregate validator produced a
`validated_partial_matrix`; its qualified samples are useful for diagnosis but
do not form a complete three-system performance result. No new complete
performance report is accepted.

The run retains the [partial aggregate report](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955881/artifacts/12168986006)
and the [Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955881/artifacts/12169045771),
[Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955881/artifacts/12169131079),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955881/artifacts/12168264712)
system bundles for 90 days. The failed HTTP/2 row-level evidence remains in
the Linux ARM64 bundle; the hosted job summary does not name the row. No new
full benchmark matrix was started; the focused local replay is recorded below.

The retained Linux ARM64 log and JSONL identify the stop: HTTP/2
`request-upload-small-chunks`, `uvicorn-rs-uvloop`, repetition 2, with four
connections, concurrency 64, and 16 target streams per connection. The client
sent 65,536-byte POST bodies in 1,024-byte chunks. It completed 1,516 requests
and then recorded 15 timeouts waiting for complete responses over 20.443 s;
the first failure was `HTTP/2 request timed out waiting for a complete
response`. The server log contains a client TCP reset after that timeout. This
does not locate the original stall or prove the reset caused it. Neighboring
candidate cases passed, including the same workload's first uvloop repetition
and the asyncio repetition, so the evidence is intermittent and does not yet
identify a cause.

A single-case replay on macOS ARM64 (Apple M3 Pro, 2026-10-19) completed one
five-second repetition without a request failure: 15,470 requests at 3,084.7
requests/s, with p50/p95/p99 of 19.89/31.56/38.69 ms. This is not a valid
comparison or performance sample: it has no matched Uvicorn row, used a
different OS/host, and unrelated processes consumed roughly five CPU cores
during the measurement. Its receipt marks performance evidence `not_proven`.
It therefore fails to reproduce the client timeout under this local attempt,
but does not clear the hosted Linux ARM64 failure. No full matrix was rerun.

The documentation build and GitHub Pages deployment for this source are
complete. These CI and docs results do not imply Uvicorn CLI/API compatibility
or a published Cargo/PyPI release.

## Previous exact-source release-candidate checkpoint (2026-10-19)

The clean main source was
[`94c89b79c1f2a8e5f90b2171ee28ca929444a7f5`](https://github.com/appunni-m/uvicorn-rs/commit/94c89b79c1f2a8e5f90b2171ee28ca929444a7f5).
Exact-source CI
[39185987997](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987997)
passed: installed-wheel parity was 251/251, the unified matrix passed 761/761
cases across three repeats with 9,300/9,300 regions and 6,880/6,880 lines, and
the native composition, MSRV, and three platform package jobs passed. The
independent Coverage-MCP review of its hosted report remains pending.

The exact-source three-system performance run
[39185987961](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987961)
is **incomplete and fails the release performance gate**. Public parity passed
on Linux x86-64, Linux ARM64, and macOS ARM64, but the maintained category
phase failed on both Linux systems:

| System | Category failure | Detail |
| --- | --- | --- |
| Linux x86-64 | `fastapi-upload-1m-write-1k` | Candidate timed out in repetition 2 under asyncio and repetition 5 under uvloop. |
| Linux ARM64 | `fastapi-upload-1m-write-1k` | Candidate timed out in repetitions 2 and 3 under uvloop. |
| Linux ARM64 | H3 `slow-reader-backpressure` | Hypercorn reference timed out waiting for response headers in repetition 4; this is a reference-side failure, not a Rust result. |
| macOS ARM64 | Category analysis completed | One system is not sufficient for the required matching three-system result. The category summary is mixed: H1 and WebSocket regressions coexist with H2 and H3 gains. |

For the Linux HTTP/1 upload timeouts, libcurl reports that it submitted the full
1 MiB request body but received no response headers before its 15-second
timeout: `curl_uploaded_bytes=1048576`, `curl_downloaded_bytes=0`, response
code `0`, and zero start-transfer time. This brackets the stall after client
upload and before response start; it does not yet identify the first stalled
server operation. All four failed transfers also report `new_connections=0`:
libcurl reused the worker's persistent HTTP/1.1 connection for the failing
request. That makes a single-case persistent-versus-`Connection: close`
comparison a useful discriminator, but it does not prove keep-alive handling is
the cause. The detailed category logs and raw reports are preserved in
the run artifacts: [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987961/artifacts/12161035715),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987961/artifacts/12160483016),
[macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987961/artifacts/12160154308),
and [matrix aggregate](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987961/artifacts/12160508366).

The separate documentation workflow
[39185988011](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185988011)
passed strict site build and artifact upload. Deployment stopped at
`configure-pages` because repository Pages is not configured for GitHub
Actions. No performance claim, release-candidate bundle, tag, package
publication, GitHub Release, or public documentation deployment is supported
by these results. See [release status](releases.md) for the full first-release
gates and owner setup.

### Later focused upload replay (Ubuntu x86-64, 2026-10-19)

The maintained `fastapi-upload-1m-write-1k` workload was also run from a clean
diagnostic checkout at `32eb14cc711d5cc3c1da2f2e7889dba35fd86ebc`, using the
same stock FastAPI app, 1 MiB body, 1 KiB client writes, concurrency 8, and five
repetitions. All 20 rows passed complete response checks with zero request
failures. The run used Node.js 22.15.0 because libcurl was unavailable. It
provided five matched repetitions for asyncio and four for uvloop; the
remaining Uvicorn uvloop row was excluded for unrelated host CPU activity.

| Loop | Matched repetitions | Median paired throughput ratio, Rust/Uvicorn | p95 latency, Uvicorn → Rust | Server CPU/request, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: |
| asyncio | 5 | 0.856× | 12.56 → 14.01 ms | 1,097 → 2,034 µs |
| uvloop | 4 | 1.081× | 13.96 → 12.65 ms | 1,168 → 1,654 µs |

The host was an AMD Ryzen 5 2600X with 12 logical CPUs. This diagnostic uses a
different source revision from the exact release-gate commit and a Node.js
client instead of the libcurl client that timed out in the hosted matrix. It
does not reproduce or explain that failure, and it is not multi-system release
evidence. The report is retained in the user's Ubuntu work folder at
`/home/appunni/work/uvicorn-rs-bench-32eb14c/target/fastapi-match/`;
`fastapi-upload-1m-write-1k.json` has SHA-256
`1453b5ea4635338e273ff31b6c1f6fc9bde1c83352fdd68183b1e6f97d980d85`.

### Focused upload ASGI-stage diagnostic (Ubuntu x86-64, 2026-10-19)

The exact-source `94c89b79c1f2a8e5f90b2171ee28ca929444a7f5` server extension
was replayed against the maintained stock FastAPI `POST /upload/1048576`
workload. The client uploaded 1 MiB in 1 KiB writes at concurrency 8. Each
server/loop pair ran five 5-second repetitions after a 1-second warmup, using
the same native libcurl C client (libcurl 8.5.0). The ASGI profiling wrapper
was enabled to time each application's `receive` and `send` awaits. It leaves
ASGI messages unchanged but adds measurement overhead. The extension SHA-256
was `44dd8bf5b2267da7e11a1209c5e01a88a91ad24c7ac7e5a54338cdace9a7ee98`.

All 20 rows passed complete request/response checks and graceful server
shutdown; no upload timeout reproduced. The host monitor observed unrelated
CPU activity, and the ASGI instrumentation marked all rows timing-invalid.
The observed throughput and latency below are diagnostic output only and must
not be compared as performance results. Across repetitions, the instrumented
ASGI `receive` p50 was consistently higher in uvicorn-rs; its p50 was close to
the full FastAPI app-call wall time. This points to the request-body receive
path as the next area to inspect, but does not identify the Rust operation
responsible or explain the hosted 15-second stalls.

| Server | Completed rows | Observed requests/s median* | Observed response p50 median* | ASGI receive-await p50 median (range) |
|---|---:|---:|---:|---:|
| Uvicorn, asyncio | 5/5 | 683.1 | 11.07 ms | 8.99 ms (8.70–10.02) |
| uvicorn-rs, asyncio | 5/5 | 523.6 | 15.04 ms | 12.74 ms (12.50–13.08) |
| Uvicorn, uvloop | 5/5 | 652.7 | 11.55 ms | 9.47 ms (8.90–9.67) |
| uvicorn-rs, uvloop | 5/5 | 555.8 | 14.11 ms | 12.10 ms (11.33–12.23) |

\* Instrumented and host-contended; invalid for ranking or release acceptance.

The raw JSON and per-sample logs remain ignored on the Ubuntu host at
`/home/appunni/work/uvicorn-rs-upload-exact-94c/target/fastapi-stage/`.
This single-host diagnostic is not a release benchmark and does not replace a
clean, uninstrumented, correctness-gated multi-system rerun.

### Uninstrumented upload comparison on the same host (2026-10-19)

The same workload was then measured without the profiling wrapper, from a
clean checkout at commit `94c89b79c1f2a8e5f90b2171ee28ca929444a7f5`, using the
same extension hash and libcurl 8.5.0 client. The host was Linux
`7.0.0-38-generic` on an AMD Ryzen 5 2600X. All 20 server samples passed the
body and lifecycle gates with zero failures. All five asyncio pairs qualified
for timing; four of five uvloop pairs qualified, with the fifth Rust uvloop
sample excluded for unrelated host CPU activity.

| Loop | Matched pairs | Throughput, req/s | p50 latency, ms | p95 latency, ms | p99 latency, ms | Server CPU, µs/request | Peak RSS, MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| asyncio | 5 | 723 → 525 (0.722×) | 10.44 → 15.20 | 15.64 → 18.92 | 20.15 → 22.56 | 1,367 → 2,843 (2.08×) | 54.71 → 56.88 |
| uvloop | 4 | 692 → 574 (0.824×) | 11.18 → 13.60 | 15.62 → 18.08 | 19.49 → 23.02 | 1,436 → 2,312 (1.63×) | 58.11 → 60.28 |

Values are Uvicorn → uvicorn-rs medians over the same valid repetition IDs;
throughput ratios are median same-repetition ratios. This focused result shows
uvicorn-rs slower on this FastAPI upload workload on this host. It does not
identify the underlying receive-path operation and cannot satisfy the required
three-system performance gate. The report's source SHA-256 is
`e6e9791a2c6f4f3dfaaf579d260a76ee57d8b4dc743f2d8a19bcab3998b30f72`, its
native extension SHA-256 is
`44dd8bf5b2267da7e11a1209c5e01a88a91ad24c7ac7e5a54338cdace9a7ee98`, and its
JSON SHA-256 is
`522fe444802e56076db4c7affc69b3acdaf548abd57063b1ff588c546a2ac910`. The
ignored report is
`/home/appunni/work/uvicorn-rs-upload-exact-94c/target/fastapi-stage/fastapi-upload-1m-write-1k-uninstrumented.json`.

Source inspection identifies a candidate to isolate, not a proven cause:
`pump_http_request_body` currently coalesces up to 256 KiB and uses a 5 ms
maximum batch wait. The 5 ms setting was selected from a separate 64 KiB-write
comparison; it does not establish an effect on this 1 KiB-write workload. An
older instrumented probe on commit
`dd6ed00f551c02196544ae9452c7b0747452a422` observed about 65 Hyper body frames,
11.3–11.8 ms per request waiting for a frame or batch flush, 1.1–1.3 ms waiting
to send to the bounded request channel, about four byte-threshold flushes, and
only 0.007–0.009 5 ms timer flushes per request. The probe used a different
source revision and diagnostic build; it points toward body delivery and
handoff scheduling but cannot attribute the current slowdown. It also makes a
wait-only 1 ms versus 5 ms comparison a weak discriminator for this workload.

The higher-value next experiment is a normal-build, same-host comparison of the
current 256 KiB body-batch limit with a 1 MiB limit, holding the 5 ms maximum
wait constant. Run only `fastapi-upload-1m-write-1k` first, check source and
extension hashes around each sample, and require at least three matching valid
pairs per loop. A prior 256 KiB versus 1 MiB trial on older source had only two
valid candidate pairs and suggested slightly lower CPU alongside higher RSS
and worse tail latency; it did not justify changing the default. Any new
candidate must also retain the existing request-streaming-progress and
resource-bound correctness results, and show a repeatable gain without
unacceptable tail-latency or RSS cost before the default changes.

## Focused FastAPI fixed-route comparison attempt (Linux x86-64, 2026-10-18)

A normal release wheel built from the dirty worktree at commit
`0b12d28ce8e3e4a64339fe556c8b01705dd90032` was compared with Uvicorn on the
stock FastAPI `/fixed` route. The frozen environment used CPython 3.12.13,
FastAPI 0.142.4, Starlette 1.7.0, Uvicorn 0.54.0, uvloop 0.23.0, httptools
0.8.0, Rust 1.98.1, and an AMD Ryzen 5 2600X host with 12 logical CPUs. The
load was concurrency 64, 5-second samples, 1-second warmup, five repetitions,
seed `20261018`; both asyncio and uvloop server pairs were included.

This host lacked `curl-config`, so the maintained client selected its Node.js
fallback. Node.js 24.22.0 came from the official archive and its SHA-256 was
checked against the published checksum file. The same Node client was used
for all four servers; its CPU was close to one logical CPU during samples, so
client saturation is an additional interpretation limit compared with the
native libcurl benchmark path.

All 20 rows returned the exact expected status and complete body, passed the
server lifecycle gate, and recorded zero request failures, unexpected native
errors, or panics. The official focused analyzer nevertheless classified the
attempt as `incomplete_or_unqualified`: unrelated host CPU activity invalidated
18/20 timing rows, leaving no same-repetition valid pair for either loop.

| Loop | Uvicorn valid rows | uvicorn-rs valid rows | Matched valid repetitions |
| --- | ---: | ---: | ---: |
| asyncio | 1/5 | 1/5 | 0 |
| uvloop | 0/5 | 0/5 | 0 |

The raw rows contain throughput, p50/p95/p99, server CPU per request, and RSS,
but the analyzer intentionally emits no comparison medians when there are no
qualified matched samples. Do not use the raw rates as a performance result.
The host passed the read-only preflight before timing; the later in-run CPU
activity shows that this short preflight did not predict stability across the
full sample window. This dirty-branch diagnostic does not satisfy release
performance acceptance. Retry only this workload after the host is quiet or
on an isolated runner, preferably with the native libcurl client.

Ignored local evidence is retained at
`target/benchmark-diagnostics/2026-10-18/current-fastapi-fixed-linux-x86_64/`.
The raw report SHA-256 is
`f43d3d2181dae62dc12f55072c1a9438717cde3081c0c6696dd7a0367ba37a7a`; the
focused summary SHA-256 is
`34e3b3271851203914d19f2363e5140dedd75bc258ab491dbb7c785094e9402a`; and the
accepted host-preflight receipt SHA-256 is
`db455fa02604cfa1432d85b97c581d1390a8557d66e7e87ca7838c7478a7360b`.

## Current-source FastAPI fixed-route profile and Mac timing rejection (2026-10-18)

On the dirty worktree at commit `0b12d28ce8e3e4a64339fe556c8b01705dd90032`,
matched Samply profiles captured the stock FastAPI `/fixed` route under
uvloop on macOS ARM64. Both profiles used CPython 3.12.13, FastAPI 0.142.4,
Starlette 1.7.0, Uvicorn 0.54.0, uvloop 0.23.0, concurrency 32, a 1-second
warmup, and a 10-second load. Every response body passed. The profile
instrumentation is diagnostic and perturbs execution; it does not produce
timing or CPU-per-request evidence.

| Profile | Requests | Sampled process CPU weight | Python thread | Tokio worker |
| --- | ---: | ---: | ---: | ---: |
| `uvicorn-rs` | 125,274 | 10,631 ms | 6,890 ms | 3,741 ms |
| Uvicorn | 217,192 | 9,485 ms | 9,485 ms | 0 ms |

The Rust profile places about 35% of its sampled process CPU weight on one
Tokio worker; Uvicorn's sampled work is on its Python thread. The dominant
inclusive paths include Tokio request tracking and `handle_request_parts`,
while the largest exclusive rows include unresolved `libsystem_kernel.dylib`
addresses. Inclusive rows overlap and the system frames are not symbolicated,
so this does not identify one function to optimize. The per-server raw
profiles are retained locally under
`target/benchmark-diagnostics/2026-10-18/current-fastapi-fixed-uvloop-samply-uvicorn-rs/`
and `...-samply-uvicorn/`; their profile SHA-256 values are
`c2658a595318f5a489de6c60d10b504cc3d71d478c6879e05f7b33b4bc29677e` and
`39de510ef56a44f0600453d767db8a675545d5e28aba12efb93fca1b4a0c5e5b`. Both
used native extension SHA-256
`5db6a995af9eac0932f88bb4fb515bac34ec9df54f63e7debcebf12dd2d5cc30`.

Demangling the retained Rust frames shows `PyGILState_Ensure` at 2,369 ms
inclusive (22.29% of Rust's sampled process CPU weight),
`handle_request_parts` at 2,903 ms inclusive, and Tokio `Context::run_task` at
3,699 ms inclusive. These values overlap; they are not additive and do not
measure exclusive GIL-acquisition cost. `AsgiIo::send` is 142 ms inclusive.
The profile therefore points toward the per-request Python/GIL and Tokio
dispatch boundary as the next investigation, not SIMD or body-copy work; it
does not prove the cost of either or qualify a speed result. The normal
benchmark was host-rejected, so any code change still needs a clean matched
re-measurement.

A separate unprofiled five-repetition attempt on this host passed response
and shutdown checks for six rows, then stopped with all timings rejected for
unrelated CPU activity (roughly 330–380% aggregate). It has no final category
report and is not rankable. Its ignored JSONL checkpoint is
`target/benchmark-diagnostics/2026-10-18/current-fastapi-fixed-macos-arm64-uvloop.jsonl`.
The currently available Linux x86 host was also busy with an unrelated Rust
compile during the follow-up check. Retry the same single workload only after
the host preflight accepts; neither diagnostic changes the server's
performance status.

## Rejected HTTP/1 inline-application-task candidate (Ubuntu x86-64; 2026-10-18)

The candidate removed the per-request Tokio task spawn on the HTTP/1 path by
polling the Python application future inline; HTTP/2 and HTTP/3 task tracking
were unchanged. Five focused parity inputs passed before timing:
`http1.response-first-chunk-before-app-completion`,
`http1.response-reset-cancels-held-application`,
`http1.final-response-completes-before-app-return`,
`http2.response-stream-reset-cancels-app`, and
`http3.client-cancels-large-response-after-headers`. The benchmark then ran
only the stock FastAPI `/fixed` workload, with full status/body checks and
server shutdown checks on every row.

Baseline and candidate used the same Ubuntu x86-64 AMD Ryzen 5 2600X host,
CPython 3.12.3, FastAPI 0.142.4, Starlette 1.7.0, Uvicorn 0.54.0, uvloop
0.23.0, Node.js 25.1.0, concurrency 64, a 1-second warmup, 5-second samples,
five repetitions, and seed `20261018`. Both read-only host preflights passed.
The same Uvicorn + uvloop + httptools reference was included in each run.
All five Rust baseline and candidate rows passed response and lifecycle gates;
the baseline reference had four valid rows and the candidate reference had
five. Rust comparisons use all five matching repetition IDs.

| Rust + uvloop metric | Baseline | Inline candidate |
| --- | ---: | ---: |
| Throughput, requests/s | 7,105.6 | 6,789.3 |
| p50 latency, ms | 7.70 | 9.31 |
| p95 latency, ms | 16.86 | 12.35 |
| p99 latency, ms | 19.66 | 14.41 |
| Server CPU, µs/request | 186.4 | 197.1 |
| Peak server RSS, MiB | 54.52 | 53.91 |

The median same-repetition throughput ratio was `0.957×` candidate/baseline
(4.3% lower); server CPU per request increased 5.6% and p50 latency increased
20.3%. p95 and p99 were lower, but this is not an overall throughput gain.
On the four reference repetition IDs valid in both runs, Uvicorn throughput
changed by less than 1%, providing a check against large run-to-run drift.
Reject and discard this optimization.

The experiment was performed on base commit `5e2ed84b` with an uncommitted
candidate; the candidate report records `dirty_target=true`, so neither run
is release performance evidence. Source and native extension identities were
stable within each run and differed only for the candidate build. The source
and original extension were restored after measurement. The retained reports
and source patch are ignored local artifacts:
baseline JSON (local-only maintainer artifact)
(SHA-256 `29d43821b1e6515b0acfe66742c1a7512d94886c22279271ac6287dcefe65bac`),
candidate JSON (local-only maintainer artifact)
(SHA-256 `15b34e5e0a1730fd1432a2af84b11d8d57ba5d53cfe532d67d4ab6c4bc47088b`).

## Focused exact-source FastAPI upload attempts (Ubuntu x86-64; 2026-10-18)

The authorized Ubuntu host ran the `fastapi-upload-1m-write-1k` workload on
exact source commit
[`5df87f191abe3a16a393fcca980017e15178b70a`](https://github.com/appunni-m/uvicorn-rs/commit/5df87f191abe3a16a393fcca980017e15178b70a).
It sent 1 MiB request bodies in 1 KiB client chunks at concurrency 8, with five
5-second repetitions and a 1-second warmup. The four compared configurations
were Uvicorn and `uvicorn-rs` on asyncio and uvloop. The host was an AMD Ryzen
5 2600X with 12 logical CPUs; both used CPython 3.12.13, FastAPI 0.142.4,
Uvicorn 0.54.0, uvloop 0.23.0, and the Node.js 22.15.0 HTTP/1.1 client.

Both attempts passed all 20 response and server-shutdown checks, with no
request failures. In the first attempt, unrelated host activity rejected
18/20 timings. A retry began after a preflight sample showed 92% CPU idle; the
timing guard accepted 7/20 rows and rejected 13 for unrelated activity. That
retry contains one raw same-repetition valid pair per loop (asyncio repetition
5 and uvloop repetition 3), below the required three pairs per loop.

An exact-source follow-up on local commit
`7cbc1ddcd2cbee162a5e1c3e8c440910ed12cca7` used the same workload, host,
software versions, and 20-row design. It passed
all 20 response and shutdown checks, and recorded the Node executable SHA-256
(`c43f3f73f6917481d2364daf7b7bf8c4fc4a7643580b4626f13f003131ec8716`). The
timing guard accepted only two rows: Rust/uvloop repetition 2 and
Uvicorn/uvloop repetition 4. They are not a matched repetition, and no asyncio
row qualified, so the report contains zero matched pairs. The client identity
gap is fixed in this run, but host contention still prevents performance
interpretation. Its ignored raw report is
`exact 7cbc run` (local-only maintainer artifact)
(SHA-256 `abde05482fb9bb65cf8cbdeae49298558c823d75bcea5b3d868f4410fccc40be`).

A later retry on the same local source commit completed its 20 rows without
request, shutdown, or lifecycle failures, but must be discarded entirely: its
shared virtual environment imported `uvicorn_rs` and the native extension from
`/home/appunni/work/uvicorn-rs`, whose checkout was
`599a9b5be5cdeb579c2a0059ab9e924f7bfb3828`, not the measured `7cbc1dd`
worktree. The imported checkout had different Rust and CLI source
hashes. Although the runner recorded the measured worktree's clean commit, it
did not verify the actual Python package root. The benchmark evidence now
records that root and rejects package imports resolved under another Git
checkout. The retry remains ignored and excluded from every performance
comparison: `misbound retry` (local-only maintainer artifact)
(SHA-256 `6c871750678bc65a11cc1480a7c24b2ffaacad16952b895a329467c69b50967a`).

The summary validator also rejected the 5df retry's two pairs because the
Node.js client binary was not fingerprinted (`client_sha256_before` and
`client_sha256_after` were empty). The 7cbc follow-up records that executable
identity, but still has no matched timing pairs. These attempts do not provide
a throughput or latency comparison and do not identify the cause of the
previously observed Rust CPU excess. Host
`perf_event_paranoid=4` also prevents the available on-CPU call-stack profiler
from resolving Rust function costs.

These focused diagnostics are not the multi-system release matrix. The ignored
raw reports are
`first attempt` (local-only maintainer artifact)
(SHA-256 `3d615a1d4f7e89786c116466be13a58fcf0ed6081803907406671388d14e1ad0`)
and
`timing retry` (local-only maintainer artifact)
(SHA-256 `1befc73b9aa636660f850ea51517d4fca3da6d8e21c50536e2f65ad22699956f`).
Both record source fingerprint
`befff8ef619b18b70582d8714cd61a660496133c975111e7f0b88993da46f092` and
normal native extension SHA-256
`7136e0edaf84b0900300c0e38bcb8bf8efa68fd3a7cfb13bf5e2f69a81fffa73`.
Keep both results classified as `not_proven`; do not use them to claim a
speedup or regression ratio.

### Corrected exact-source matched run (commit `5e2ed84b`; Ubuntu x86-64)

The benchmark harness now records the imported Python package root and fails
if it resolves under a different Git checkout than the measured source. The
ten-repetition follow-up ran the stock `examples.bench_fastapi` FastAPI,
Starlette, and Pydantic stack only; it did not use FastAPI-RS or Starlette-RS.
It sent a 1 MiB request body in 1 KiB client writes at concurrency 8, with a
1-second warmup and 5-second samples. The host was an AMD Ryzen 5 2600X with
12 logical CPUs. The environment used CPython 3.12.13, FastAPI 0.142.4,
Starlette 1.7.0, Pydantic 2.13.5, Uvicorn 0.54.0, uvloop 0.23.0,
httptools 0.8.0, and Node.js 22.15.0.

All 40 requests and server lifecycle checks passed. Thirteen of 40 timing rows
were excluded by the unrelated-host-CPU guard; the remaining rows include
four matched asyncio repetitions and five matched uvloop repetitions, both
above the minimum of three. The worktree was clean, source and binary
identities remained stable, and Python plus the native extension loaded from
the exact measured worktree. Native extension SHA-256 was
`7136e0edaf84b0900300c0e38bcb8bf8efa68fd3a7cfb13bf5e2f69a81fffa73`; the
Node executable SHA-256 was
`c43f3f73f6917481d2364daf7b7bf8c4fc4a7643580b4626f13f003131ec8716`.

Metrics below are medians over the valid matched repetitions. Throughput ratio
is the median of the per-repetition Rust/Uvicorn ratios. Each pair compares the
same event loop and workload; do not compare the asyncio and uvloop columns as
one pooled result.

| Metric (Uvicorn / uvicorn-rs) | asyncio (4 matched) | uvloop (5 matched) |
| --- | ---: | ---: |
| Throughput, requests/s (Rust/Uvicorn ratio) | 963.5 / 812.4 (0.854×) | 764.7 / 935.3 (1.159×) |
| p50 latency, ms | 7.86 / 9.64 | 10.19 / 8.42 |
| p95 latency, ms | 12.43 / 13.07 | 14.62 / 12.22 |
| p99 latency, ms | 14.59 / 14.91 | 16.59 / 14.55 |
| Server CPU, µs/request | 956 / 2,007 | 1,284 / 1,626 |
| Server peak RSS, MiB | 54.5 / 57.4 | 56.3 / 61.3 |
| Client CPU, µs/request | 1,071 / 1,056 | 1,160 / 1,002 |
| Client peak RSS, MiB | 98.4 / 95.6 | 96.9 / 96.6 |

On this workload, uvicorn-rs with uvloop had 15.9% higher throughput and lower
latency percentiles, at 27% more server CPU and about 5 MiB more peak server
RSS. With asyncio, uvicorn-rs had 14.6% lower throughput, higher latency, and
about 2.1× server CPU. This is a qualified result for one upload workload on
one x86-64 host, not evidence of a general speedup or the complete release
performance gate. The ignored raw report (local-only maintainer artifact)
has SHA-256 `53f135e7ba23380e24972767071a38b14c47952d01ce67f5df076de9c6448e59`;
the matched summary (local-only maintainer artifact)
has SHA-256 `1f73ea32c8b210ac406c3108084575185c2d9c2b8edfc97391d3869ee44672f8`.

A focused attempt to reproduce the historical x86-64
`fastapi-request-upload` timeout (1 MiB body, 64 KiB client writes, concurrency
64, uvicorn-rs with uvloop) did not start. Three fresh host preflights on the
exact `5e2ed84` worktree rejected timing. The first recorded unrelated
aggregate CPU of 109.6–152.0%, including a Python process using roughly
95–112% of one CPU; the third recorded 121.6–137.9%. The second also rejected
for aggregate activity over 100% and a process over 25% across consecutive
intervals. The receipts are ignored files in the remote worktree under
`target/benchmark-diagnostics/2026-10-18/`; they are not rankable benchmark
rows. No process was stopped. Retry only this workload after the host passes
preflight; these attempts give no evidence about server behavior.

## Latest hosted multi-system matrix (run 39100156717; source 025caf5)

The [ASGI performance matrix run 39100156717](https://github.com/appunni-m/uvicorn-rs/actions/runs/39100156717)
measured commit `025caf5b2f855c6a04a29692fba731e944d06559` on Linux x86-64,
Linux ARM64, and macOS ARM64. Its aggregate artifact is
[12127209607](https://github.com/appunni-m/uvicorn-rs/actions/runs/39100156717/artifacts/12127209607)
(SHA-256 `258f85b948ccb0d2dcf672f490fe7fc4f777d6749f42146a0327359cb42cbdb4`).
All systems used CPython 3.12.13, Rust 1.98.1, FastAPI 0.142.4, Starlette
1.7.0, Pydantic 2.13.5, Uvicorn 0.54.0, and uvloop 0.23.0, with five
repetitions, a 1-second warmup, and 5-second samples. Ordinary HTTP and
WebSocket workloads used concurrency 64; HTTP/3 used concurrency 1. Results
are system-specific and must not be pooled.

| System | HTTP/1 | HTTP/2 | HTTP/3 | WebSocket | Lifecycle | Matrix result |
| --- | --- | --- | --- | --- | --- | --- |
| Linux x86-64, AMD EPYC 9V45 (4 logical/2 physical CPUs) | 300 rows; 288 timing-eligible, 12 Rust upload failures | 140/140 valid rows | Incomplete; 64 rows retained | 60/60 | 20/20 | Partial; no qualified HTTP/1 pairs |
| Linux ARM64, Neoverse-N2 (4 cores) | 300/300 valid rows | 140/140 | Incomplete; 38 rows retained | 60/60 | 20/20 | Partial |
| macOS ARM64, M1 virtual host (3 vCPUs) | 300 rows; 281 timing-eligible, 19 host rejects | 139/140 timing-eligible | 122/130 timing-eligible | 60/60 | 20/20 | All categories completed; host-rejected timings excluded |

The x86 HTTP/1 failure is a correctness/availability result, not a timing
rejection: 12 Rust FastAPI upload rows were invalid, including seven native
libcurl transfers that timed out at the unchanged 15-second client limit.
Uvicorn reference rows had no failures. The client reported 1 MiB uploaded,
zero downloaded bytes, and status 0 in the retained timeout samples. A focused
Linux x86-64 replay with the same workload family but a Node.js client passed
five repetitions; that does not explain the libcurl timeout or the separate
ARM64 failures. The upload issue remains open and the timeout must not be
increased to hide the long tail.

The HTTP/3 category did not complete on either Linux system because its
Hypercorn oracle timed out waiting for response headers: x86-64 on
`large-response` repetition 2, and ARM64 during warmup of
`protocol-scope` repetition 5. Those are reference-side infrastructure
failures, not evidence of a Rust HTTP/3 regression. The retained target rows
are insufficient for a category comparison. macOS completed all HTTP/3
workloads, with eight timing samples rejected by its CPU guard.

The stock FastAPI-only validated-route comparison produced four matched pairs
per Linux system and shows a regression on this commit:

| System / loop | Rust/Uvicorn throughput ratio | p95 latency, Uvicorn → Rust | Server CPU, Uvicorn → Rust |
| --- | ---: | ---: | ---: |
| Linux x86-64 / asyncio | 0.634× | 5.230 → 14.199 ms | 98.5% → 121.1% |
| Linux x86-64 / uvloop | 0.695× | 4.908 → 11.944 ms | 98.7% → 120.2% |
| Linux ARM64 / asyncio | 0.755× | 12.852 → 18.364 ms | 95.0% → 122.2% |
| Linux ARM64 / uvloop | 0.864× | 12.840 → 16.459 ms | 95.0% → 121.8% |

The FastAPI Python-CPU workload was closer to parity (0.919× and 0.926× on
x86-64; near Uvicorn on ARM64), while Rust still showed higher p95 latency.
HTTP/2 comparisons use Hypercorn rather than Uvicorn: several fixed and large
response workloads favor Rust, while chunk-streaming gains are smaller and
vary by system. WebSocket results are mixed: handshake throughput favors Rust
(1.745×/1.580× on x86-64), while text echo (0.390×/0.661×) and 64 KiB binary
echo (0.532×/0.636×) trail Uvicorn. These category-specific results do not
support a general Python-ASGI speed claim. The checked-in decision remains
`scope_revised`: Python ASGI mode is a compatibility path; performance claims
must target the Python-free Rust-native composition.

This report predates source commit
`5df87f191abe3a16a393fcca980017e15178b70a` and the subsequent focused
benchmark tooling update; it is not evidence for that source revision or the
updated tooling. CI run
[39115660595](https://github.com/appunni-m/uvicorn-rs/actions/runs/39115660595)
passed, but it is tracked separately from this older multi-system benchmark.

### Focused exact-source upload recheck (Ubuntu x86-64; 2026-10-18)

On clean source commit `dd6ed00f551c02196544ae9452c7b0747452a422`, the
`fastapi-upload-1m-write-1k` workload sent 1 MiB bodies with a 1 KiB client
read cap at concurrency 8. CPython 3.12.3, FastAPI 0.142.4, Uvicorn 0.54.0,
and libcurl 8.5.0 were used on an AMD Ryzen 5 2600X host with 12 logical
CPUs. Five repetitions per server completed with zero client failures; the
historical 15-second upload timeout did not reproduce. The shared host CPU
guard accepted only two matched Rust/Uvicorn repetitions: the median
Rust/Uvicorn throughput ratio was 0.822, p95 latency ratio 1.190, and server
CPU per request ratio 1.84. Client CPU per request was nearly equal (1.01×).
Three Rust rows and one Uvicorn row were rejected for unrelated host CPU
activity, leaving fewer than the three valid pairs required for performance
acceptance. This points to extra server-side work on this upload path, but it
does not identify a function-level cause or resolve the earlier timeout.

The ignored raw report is
`fastapi-upload-1m-write-1k-dd6ed.json` (local-only maintainer artifact)
(SHA-256 `66fd4ccbae08201382fc2e067adc3c1cbb598a832d6864f539dc13831fbeadd3`).
Its measured source digest is
`0992f744ceb9cae8f9d0735b09141c9d3c5808d1afe3d934d0054a2945bf53b2`, and
the normal native extension digest is
`53922738aa0e2ed4bd5b38c5d26df2d77cd9cc74c1c85117bd01d7dfb42f67a0`.

### FastAPI request-body receive attribution (diagnostic only; 2026-10-18)

To locate the extra server CPU seen in the upload recheck, the exact clean
source was rebuilt with the opt-in `runtime-diagnostics` feature. The probe
wrapped the same FastAPI app with per-request ASGI stage timers and ran the
1 MiB upload with 1 KiB and 256 KiB libcurl read-callback caps, at concurrency
8, for three repetitions per server and loop. The C client, response checks,
Python environment, and source commit were unchanged. These timings are
diagnostic-only: stage instrumentation invalidates every timing row, and one
1 KiB Rust/asyncio row was also rejected for unrelated host CPU activity. All
24 rows completed with zero request failures; none qualifies as performance
evidence.

| Client read cap | Loop | Rust `receive()` p50 | Uvicorn `receive()` p50 | Rust app outside ASGI I/O-await p50 | Uvicorn app outside ASGI I/O-await p50 | Rust/Uvicorn `receive()` calls p50 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 KiB | asyncio | 13.414 ms | 9.020 ms | 0.443 ms | 0.346 ms | 6 / 5 |
| 1 KiB | uvloop | 12.642 ms | 11.104 ms | 0.372 ms | 0.415 ms | 6 / 5 |
| 256 KiB | asyncio | 8.086 ms | 6.759 ms | 0.409 ms | 0.295 ms | 6 / 5 |
| 256 KiB | uvloop | 7.542 ms | 6.602 ms | 0.375 ms | 0.321 ms | 6 / 5 |

The main measured difference sits in the awaited ASGI `receive()` path. The
FastAPI app stage outside ASGI I/O-awaits stayed around 0.37–0.44 ms p50; this
includes framework work and other awaits and is not CPU time. Converting each
1 MiB request body to Python `bytes` took about 217–237 μs per request. The Rust
runtime counted 5.47–5.66 receive bridge futures per request with 1 KiB client
reads and 4.35–4.63 with 256 KiB reads. This narrows the investigation to
streamed request-body delivery and its async bridge; it does not yet tell
whether time is spent waiting for Hyper body frames, batch flushes, queue
backpressure, or Python-loop scheduling. The receive timer includes all of
those waits.

Increasing the client callback cap reduced the measured `receive()` time for
both servers, while the diagnostic Rust/Uvicorn gap narrowed. Because every
row is diagnostic-only, treat this as directional attribution, not a speed
comparison. The follow-up body-pump probe below separates frame/flush waits
from bounded request-channel sends; it still cannot distinguish network pacing
from Hyper wakeups or queue backpressure.

The ignored raw reports are
`fastapi-upload-stage-dd6ed.json` (local-only maintainer artifact)
(SHA-256 `a8d06fa1531b9e2f0c440820942c93595955b661a39ffb06df6e2ab4005aeeeb`)
and
`fastapi-upload-256k-stage-dd6ed.json` (local-only maintainer artifact)
(SHA-256 `e103d2ae15fe82a9343aa0f81050d12b3f9d3896d2a1ef92ee4c432722d205c1`).
Both record commit `dd6ed00f551c02196544ae9452c7b0747452a422`, Python 3.12.3,
FastAPI 0.142.4, Uvicorn 0.54.0, and diagnostic extension SHA-256
`f351922af07a909ea4708f3727d6d8440fa8868046b90bd9b7d3fa14b24461e8`.

#### Rust HTTP body-pump breakdown (instrumented source; diagnostic only)

A second opt-in diagnostic patch added counters around the Rust request-body
pump. It records time in the select that awaits `Incoming::frame()` or the
batch timer, threshold and timer flush counts, Hyper data-frame and byte counts,
and bounded request-channel send waits. The measured source was commit
`dd6ed00f551c02196544ae9452c7b0747452a422` plus this diagnostics-only patch
(source SHA-256
`53bd0a4be5f3c02f2df5dc8eff6c25764b5187332291d47ca1993b34c1fd9681`); the
diagnostic extension SHA-256 was
`5ee9c9de5698a3f6deed644fab3ae447754f1ee39c52c9c450dc420493a3132c`. The
patch was gated by `runtime-diagnostics`; benchmark messages and handler
behavior were unchanged. Each input used three 2-second repetitions, no
warmup, concurrency 8, and seed `20261018`. All 24 rows completed without
request failures. Instrumentation invalidated every timing row, and one 256
KiB Rust/asyncio row also hit the host-CPU guard.

| Client read cap | Loop | Body-frame/flush select wait per request | Request-channel send wait per request | Hyper data frames/request | Threshold flushes/request | 5 ms timeout flushes/request | Rust receive bridge futures/request |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 KiB | asyncio | 11.818 ms | 1.297 ms | 65.093 | 3.990 | 0.009 | 5.461 |
| 1 KiB | uvloop | 11.341 ms | 1.096 ms | 65.148 | 3.990 | 0.007 | 5.750 |
| 256 KiB | asyncio | 5.934 ms | 2.198 ms | 64.999 | 3.958 | 0.000 | 4.388 |
| 256 KiB | uvloop | 5.432 ms | 2.249 ms | 65.007 | 3.948 | 0.000 | 4.585 |

The body-frame/flush wait roughly doubles for the 1 KiB client callback cap,
while the 5 ms batch timeout almost never fires. The queue sends take 1.1–2.2
ms per request, and the Rust receive bridge creates about 4.4–5.8 futures per
request. Python byte materialization remains about 0.25–0.28 ms for each 1 MiB
body. This points to body arrival and Rust/Python streaming handoffs as the
latency path; the counters do not separate network pacing from Hyper wakeups
or queue backpressure, and they are not CPU profiles. Do not tune batch size
or queue capacity from this evidence alone because that could change streaming
latency and memory bounds.

The ignored reports are
`fastapi-upload-pump-stage-dd6ed.json` (local-only maintainer artifact)
(SHA-256 `544210b37410097828a9d2534197a9568f6a50d9c042894e0c795552da2b7ae7`)
and
`fastapi-upload-256k-pump-stage-dd6ed.json` (local-only maintainer artifact)
(SHA-256 `db94c3926011f5799a7b23f7ef0cdfbbc814f193641dab7044cfd8bb44c546f9`).

#### Normal-build timing recheck (same 1 KiB upload)

The same workload was rerun without diagnostic instrumentation on clean commit
`dd6ed00f551c02196544ae9452c7b0747452a422`: five repetitions, 5-second
samples, 1-second warmup, concurrency 8, seed `20261018`, and the same
CPython/FastAPI/Uvicorn/libcurl stack. All 10 rows passed response and lifecycle
checks with zero request failures. Rust had two timing-valid repetitions;
Uvicorn had five. Only repetitions 4 and 5 formed valid same-repetition pairs,
below the required three-pair minimum. Their median Rust/Uvicorn ratios were
0.784× throughput, 1.300× p95 latency, and 1.93× server CPU per request. This
confirms a directional regression for this FastAPI upload workload, but does
not meet the evidence threshold for a published performance claim. The earlier
15-second upload timeout did not reproduce.

The normal-build report is
`fastapi-upload-1k-normal-dd6ed.json` (local-only maintainer artifact)
(SHA-256 `7369a818d9cd316a7a013ceb5da07f04e3e3942103012ec39e8a58cac41d7950`);
its ignored runner log is
`fastapi-upload-1k-normal-dd6ed.log` (local-only maintainer artifact).

#### Per-thread CPU attribution (signal-gated; diagnostic only)

The repository's `/proc/self/task/*/schedstat` profiler was then applied to
this same 1 MiB/1 KiB FastAPI upload on the clean `dd6ed00f551c02196544ae9452c7b0747452a422`
worktree. It ran three 5-second repetitions per server at concurrency 8, with
the same CPython 3.12.3, FastAPI 0.142.4, Uvicorn 0.54.0, and libcurl client.
All six rows had zero request failures and clean shutdown. Unrelated host CPU
activity invalidated every row's timing; treat the CPU split below as
diagnostic direction, not rankable performance evidence.

| Server | Process CPU per request, median | Python event-loop thread | Tokio-named threads | Tokio-named threads as share of Rust process CPU |
| --- | ---: | ---: | ---: | ---: |
| Uvicorn / asyncio / httptools | 1.634 ms | 1.634 ms | 0 ms | — |
| `uvicorn-rs` / asyncio | 3.093 ms | 0.872 ms | 2.216 ms | 72% |

For this transfer shape, nearly all of the Rust server's measured excess CPU
is outside its Python event-loop thread. One Tokio-named thread accounts for
about 1.88 ms/request; six additional Tokio-named threads together account
for about 0.33 ms/request. The Python event-loop thread uses less CPU per
request than Uvicorn in these samples. This points to Rust runtime/transport
and cross-runtime scheduling work in the upload path, rather than Python body
materialization (about 0.25 ms per 1 MiB) as the main CPU cost. Thread names
cannot distinguish Tokio's async worker from its blocking pool, and these
snapshots do not attribute CPU to functions. Linux `perf_event_paranoid=4`
blocks the available on-CPU call-stack profiler on this host, so the precise
Rust call sites remain unproven.

The ignored receipts are
`fastapi-upload-thread-cpu-dd6ed-http1-benchmark.json` (local-only maintainer artifact)
(SHA-256 `8dabec5ebf77b2e7c824a8e4c43850578bca755cbf1b8ee77199fd345345c2e8`)
and
`fastapi-upload-thread-cpu-dd6ed-profile-summary.json` (local-only maintainer artifact)
(SHA-256 `2ce69090d258c94a0f72b4fd9241d99c8c308ce7839ee1968b2110eb0c89a6b6`).
The installed normal extension SHA-256 was
`31d3046b8ecaa953a5953ca2eafd0c05af9503517fe566bd46553cd82e9e3bf7`; the
profiling script SHA-256 was
`6899b7a3fcb3ea0a83be8165181146adea3611d02d506e91cf37d34d8b63c9f2`.

## Focused FastAPI WebSocket connect-event fast path (Ubuntu x86-64; 2026-10-18)

The first ASGI WebSocket `receive()` returns `websocket.connect` immediately.
`WebSocketIo::receive` now constructs that event on the owning Python thread and
returns its dictionary directly, skipping a `future_into_py`/Tokio handoff for
this first event. The existing Python bridge already accepts either a direct
dictionary or an awaitable. Later receives, application execution, message
conversion, and the Python event loop remain unchanged; this removes one
bridge scheduling step rather than the Python boundary.

The workload used the same ordinary Python FastAPI/Starlette WebSocket app,
CPython 3.12.13,
Uvicorn 0.54.0, uvloop 0.23.0, a Rust WebSocket client, and an Ubuntu 24.04
AMD Ryzen 5 2600X host (6 cores/12 threads). Each cohort used seed `20261018`
and three repetitions. The handshake workload completed 500 connections per
repetition; the text-echo workload used 32 persistent connections, 32-byte
messages, and 5-second measured intervals. The baseline used clean source and
source-bundle and native-binary SHA-256 values `677389c6…` and
`0459657a…`. Candidate digests were stable at `8d5014e5…` and `c2031525…`;
the candidate receipt marks the target dirty and
`performance_evidence_status: not_proven`, so these figures are exploratory.
Every candidate sample passed timing, message/handshake correctness, and
graceful shutdown gates. The existing
`websocket.text-and-binary-round-trip` parity case also passed on the candidate.

| Workload/cohort | Server | Valid reps | Operations/s | p50 ms | p95 ms | p99 ms | Server CPU µs/op | Peak RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Handshake, baseline | `uvicorn-rs` + uvloop | 3 | 2,329 | 0.353 | 0.596 | 0.629 | 360 | 48.5 |
| Handshake, baseline | Uvicorn + uvloop | 3 | 1,638 | 0.532 | 0.752 | 0.931 | 520 | 49.9 |
| Handshake, candidate | `uvicorn-rs` + uvloop | 3 | 2,478 | 0.365 | 0.488 | 0.550 | 380 | 48.7 |
| Handshake, candidate | Uvicorn + uvloop | 3 | 1,577 | 0.560 | 0.777 | 1.080 | 520 | 50.0 |
| Text echo, baseline | `uvicorn-rs` + uvloop | 3 | 15,731 | 2.166 | 2.757 | 3.053 | 106.1 | 55.2 |
| Text echo, baseline | Uvicorn + uvloop | 3 | 23,203 | 1.390 | 1.569 | 1.704 | 42.9 | 51.1 |
| Text echo, candidate | `uvicorn-rs` + uvloop | 3 | 16,089 | 2.087 | 2.788 | 3.108 | 102.6 | 55.0 |
| Text echo, candidate | Uvicorn + uvloop | 3 | 23,897 | 1.262 | 1.578 | 1.785 | 41.6 | 51.1 |

The handshake candidate's median rate was 6.4% above its baseline and p95 was
18.1% lower; server CPU per handshake did not improve (380 vs 360 µs). The
Rust/Uvicorn throughput ratio moved from 1.42× to 1.57× in this focused
handshake workload. Persistent text echo changed only 2.3% in Rust throughput
and 1.1% in p95, while remaining at about 0.67× Uvicorn throughput and using
about 2.5× its server CPU per message. That is no clear steady-state echo gain
and shows the optimization is specific to connection setup. The candidate
does not establish a general FastAPI or server-wide speedup.

The local-only raw receipts are
`benchmarks/results/2026-10-18-ws-handshake-uvloop-baseline.json`,
`benchmarks/results/2026-10-18-ws-handshake-uvloop-fast-connect.json`,
`benchmarks/results/2026-10-18-ws-echo-uvloop.json`, and
`benchmarks/results/2026-10-18-ws-echo-uvloop-fast-connect.json`. They remain
ignored along with server logs and are not release artifacts. A clean committed
build and a repeat on an independent quiet host are required before treating
the handshake delta as accepted performance evidence.

## Focused FastAPI HTTP/2 chunk-streaming result (Ubuntu x86-64; 2026-10-18)

This matched experiment measured the stock FastAPI `StreamingResponse` route
`/chunks/256/4096`: 256 chunks of 4 KiB (1 MiB per response), HTTP/2 over TLS,
concurrency 64, four multiplexed client connections, a 1-second warmup, five
5-second repetitions, and seed `20261005`. The native Rust client verified
full response-body equality. Both servers used CPython 3.12.13, FastAPI
0.142.4, Starlette 1.7.0, Pydantic 2.13.5, and the same app. Hypercorn
0.18.0/asyncio is the HTTP/2 reference. The host was Ubuntu 24.04 on an AMD
Ryzen 5 2600X (6 cores/12 threads).

The clean baseline was commit `33a705dc93e0803043994f9c4b57831f2aafc38c`
before setting `TCP_NODELAY` on accepted Rust sockets. The baseline Rust
transport source hash is `1f760cb86d860109991f4c8565194e5d44522fd1f0fa4e552a1d79461bdb53db`.
The candidate uses the same base commit with the socket option enabled; its
Rust transport source hash is
`8f2c1169409781926632004a75b8f9d18dc92f55fbdbb2b3542c63023f551d29`. The
candidate's source and native binary fingerprints stayed stable during the
run. The working tree was dirty, so the receipt labels this a local paired
experiment and `performance_evidence_status: not_proven` rather than clean
release evidence.

| Build | Server | Valid reps | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Server CPU % elapsed | Peak RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | `uvicorn-rs` / asyncio | 5 | 7.0 | 8,935 | 9,196 | 9,196 | 43,594 | 29.2 | 49.7 |
| Baseline | Hypercorn / asyncio | 5 | 74.0 | 867 | 950 | 1,002 | 13,439 | 93.8 | 161.2 |
| TCP_NODELAY | `uvicorn-rs` / asyncio | 5 | 135.5 | 470 | 564 | 593 | 11,615 | 153.5 | 50.4 |
| TCP_NODELAY | Hypercorn / asyncio | 5 | 74.5 | 867 | 949 | 1,013 | 13,301 | 93.4 | 161.0 |

All five paired repetitions were timing-valid. Every row had zero request
failures, passed full response checks, and passed graceful shutdown. Relative
to the clean Rust baseline, the candidate delivered about 19.5× the throughput
and cut p95 latency by 93.9%. It reached 1.82× the Hypercorn throughput on
this workload. Rust's total CPU utilization was higher because it completed
more requests; CPU per request was 11.6 ms versus Hypercorn's 13.3 ms. Peak
RSS was about 50 MiB versus 161 MiB for Hypercorn.

The focused change matches asyncio's accepted-socket behavior by enabling
`TCP_NODELAY`. The preceding stage diagnostic showed most time for this
many-chunk response was spent waiting on the Rust bounded response queue. The
measured improvement is specific to this H2 chunk-streaming route; it does not
establish a general FastAPI or protocol-wide speedup. The coverage-only fault
contract `fault.http1.tcp-nodelay-option-error-closes-only-connection` passed
on the Ubuntu host, confirming that a socket-option failure closes that
connection while a follow-up connection still succeeds. This was one focused
case, not a full parity or coverage run.

The local-only raw receipts are
`benchmarks/results/2026-10-18-ubuntu-x86-h2-many-response-chunks/h2.json`
and
`benchmarks/results/2026-10-18-ubuntu-x86-h2-many-response-chunks-tcp-nodelay-final.json`.
The final receipt records FastAPI dependency versions, Rust workspace sources,
Cargo manifests, and the processor model. Server logs and coverage reports
remain excluded from the repository.

## Focused FastAPI upload measurement (Ubuntu x86-64; 2026-10-18)

This is one HTTP/1.1 workload, not a complete category or release benchmark.
It used the same FastAPI app and pinned environment on both servers: CPython
3.12.13, FastAPI 0.142.4, uvloop 0.23.0, Uvicorn 0.54.0 with httptools 0.8.0,
and Rust 1.98.1. The host was Ubuntu 24.04.5 on an AMD Ryzen 5 2600X
(6 cores/12 threads). The workload POSTed a 1 MiB body in 64 KiB client chunks
at concurrency 64, with a 1-second warmup, 5-second measurements, and five
repetitions. A native libcurl 8.5.0 C client checked every response status and
full body. The measurements use the closed-loop client and include client work in
latency; they do not use open-loop offered load or correct for coordinated
omission.

The baseline is clean commit `01658e119662a30ec88cf6cb09107abd28251e56` with
the 1 ms request-body batch wait. The candidate is clean commit
`33a705dc93e0803043994f9c4b57831f2aafc38c` and changes only
`HTTP_REQUEST_BODY_BATCH_MAX_WAIT` to 5 ms. Its raw receipt records
`dirty_target: false` and `performance_evidence_status: completed`. All rows
below had zero request failures and passed graceful server shutdown. The
baseline Uvicorn repetition 1 was excluded for unrelated host CPU activity;
the baseline medians therefore use matching valid repetitions 2–5. The
candidate had five valid repetitions for both servers.

| Build | Server | Valid repetitions | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Peak RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline, 1 ms | Uvicorn + uvloop + httptools | 4 | 1,109.8 | 56.9 | 61.4 | 66.2 | 894.6 | 105.3 |
| Baseline, 1 ms | `uvicorn-rs` + uvloop | 4 | 532.5 | 120.4 | 153.0 | 167.8 | 2,774.2 | 131.6 |
| Candidate, 5 ms | Uvicorn + uvloop + httptools | 5 | 1,091.6 | 57.9 | 62.0 | 63.8 | 907.3 | 106.3 |
| Candidate, 5 ms | `uvicorn-rs` + uvloop | 5 | 633.3 | 99.9 | 129.8 | 143.1 | 2,249.4 | 156.7 |

On this workload the 5 ms candidate improved `uvicorn-rs` throughput by 19%
over its 1 ms baseline and reduced p50/p95/p99 latency by 15–17% and server
CPU per request by 19%. Peak RSS increased by 25.2 MiB (19%). The throughput
ratio to Uvicorn rose from 48% to 58%; `uvicorn-rs` remained slower, with 2.09×
Uvicorn's p95 latency and 2.48× its server CPU per request. This is a useful local
optimization, not evidence that the Python ASGI server is faster than Uvicorn.
The configured coalescing window increases from 1 ms to 5 ms; both tested
streaming-progress cases passed with this bound.

An instrumented-only stage run helps explain the result but is not timing
evidence. The baseline Rust build made about 14–15 ASGI `receive()` calls per
1 MiB request; the 5 ms build made about 8. Median `receive()` awaited time
fell from about 117 ms to 90 ms. Uvicorn made about five receives and spent
about 47–51 ms in those awaits. The 5 ms batch window therefore reduced
Rust/Python receive crossings and the associated waiting in this workload.
The ASGI receive measurement is elapsed await time, not CPU time.

### Isolated Linux x86 upload-timeout probe

To check the intermittent HTTP/1 upload timeout from matrix run 39036702600,
the same `fastapi-request-upload` input was run on the supplied Ubuntu x86-64
host against Uvicorn and `uvicorn-rs`, both with uvloop: 1 MiB POST bodies,
64 KiB client writes, concurrency 64, a 1-second warmup, three 5-second
repetitions, and seed `20261005`. Both used CPython 3.12.13, FastAPI 0.142.4,
uvloop 0.23.0, Uvicorn 0.54.0, and httptools 0.8.0. The native C libcurl
client was unavailable in that work directory, so both servers used the same
Node.js 25.1.0 client with full response-body checks.

All six samples passed with zero request failures and clean shutdowns; the
timeout did not recur. The medians were:

| Server | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + uvloop + httptools | 1,051.0 | 58.4 | 72.5 | 87.5 | 946 | 105.3 |
| `uvicorn-rs` + uvloop | 645.9 | 97.9 | 126.3 | 154.5 | 2,213 | 158.9 |

The Rust server reached 61.5% of Uvicorn throughput on this input, with
1.74× p95 latency and 2.34× server CPU per request. This is not a clean
performance result: the worktree was dirty, the report records
`performance_evidence_status: not_proven`, the Linux CPU model field contains
only `x86_64`, and one sample saw a brief unrelated host CPU spike. The Node
client was the same for both servers and used less than one CPU core, but this
fallback-client run is not directly comparable to the earlier C-client H1
measurements. It also does not explain why the earlier multi-system run
timed out. Raw JSON, JSONL checkpoints, and provenance are in
`benchmarks/results/2026-10-18-ubuntu-x86-h1-upload-diagnostic/`.

The Rust runtime materialized one Python `bytes` body per message. The
instrumented counter measured about 0.25–0.28 ms for that materialization per
1 MiB request, far below the receive-await wall time. Avoiding this required
Python `bytes` construction cannot by itself explain or remove the observed
latency gap; request chunk delivery and bridge scheduling are higher-priority
targets for this case. This attribution is specific to `fastapi-request-upload`.

#### Clean five-repetition rerun (2026-10-18)

I reran this same single input from clean commit
`ddd44af6e2d2e4fb00f4eb716ae6e16a0549261b`: POST 1 MiB in 64 KiB writes,
concurrency 64, 1-second warmup, five 5-second repetitions, seed `20261018`.
The environment was CPython 3.12.13, FastAPI 0.142.4, Uvicorn 0.54.0,
uvloop 0.23.0, httptools 0.8.0, Rust 1.91.1, and Node.js 25.1.0. The host was
Linux 7.0.0-38-generic on an AMD Ryzen 5 2600X with 12 logical CPUs. The native
libcurl client was unavailable, so both servers used the same Node.js client
with full response-body checks. Its median CPU use was 61% of one core for
Uvicorn and 46% for `uvicorn-rs`.

The corrected report retained a host-rejected Rust repetition and still passed
the three-matched-repetition gate with repetitions 1, 3, 4, and 5. All ten
samples passed complete response checks with zero request failures; the
single invalid sample was excluded from the paired medians. Source identity
remained stable. The report source digest was
`165a1ce2c6dc2f1e364e4422a0b0af1089064a54f3ded9389af6917a72dc2c78`; the
measured source identity digest was
`416d54721b007b6243b109af7656bcea9535bbb0ffe56bd0a3df5303c36bce62`. The Rust
extension hash was
`0459657ad788852619313e9c136be5901e346c141dab5af5d684cc5db19d8658`, and the
report records `performance_evidence_status: completed` for this local pair.
The venv extension was not rebuilt for the two benchmark-script-only
commits `46a452afd` and `ddd44af6e`; its normal, uninstrumented binary hash
remained stable. The only Rust-source difference from the extension's prior
build is the coverage-only fault-point name, which is excluded from normal
builds. The receipt is a frozen-checkout measurement, not a build attestation.

| Server | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Client CPU µs/request | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + uvloop + httptools | 1,057.8 | 58.2 | 71.9 | 87.2 | 942 | 610 | 104.8 |
| `uvicorn-rs` + uvloop | 675.3 | 94.1 | 123.5 | 146.5 | 2,146 | 723 | 157.6 |

`uvicorn-rs` reached 63.8% of Uvicorn's throughput, with 1.72× p95 latency,
2.28× server CPU per request, and 1.50× peak RSS. The x86 timeout did not
recur. This result confirms the local slowdown on the 64 KiB upload workload;
it does not explain the earlier libcurl timeout or the separate ARM64 1 KiB
write failures, and the Node client makes it a single-host comparison rather
than a multi-system release result.

The request-body path already retains HTTP `Bytes` segments and copies them
directly once into the Python `bytes` object with `PyBytes::new_with`; it does
not first coalesce a second Rust buffer. A pending ASGI `receive()` uses
`pyo3-async-runtimes` `future_into_py`, whose completion path schedules Python
future resolution through Tokio `spawn_blocking`. That is a concrete runtime
handoff on the receive path and matches the observed Tokio-named thread CPU,
but it is not an exclusive CPU attribution or proof that this handoff accounts
for the full latency gap. The raw JSON receipt is
`benchmarks/results/2026-10-18-ubuntu-x86-upload-validated/fastapi-request-upload.json`
(471,625 bytes; SHA-256
`3b165c7f4c83bc380e4058262ed3dd4b8d96fbcb665948c7e562bcee2f9fefd5`).

The remaining server CPU difference is not yet attributed to individual CPU
frames. The host sets `perf_event_paranoid=4`, and `perf stat` rejected even a
user-space task-clock sample. A separate 99 Hz `py-spy --native` sample for
each server includes `epoll_pwait` and other wait stacks, so it is not treated
as on-CPU accounting. The two Speedscope profiles are retained for exploration;
a permitted on-CPU profiler is still needed to locate the residual CPU cost.

The 10 ms follow-up had only two common valid repetition IDs across the two
servers, below the benchmark's three-repetition minimum, so it is inconclusive
and is not used to select the setting. The 5 ms build passed the existing
`http1.request-streaming-progress-before-upload-complete` and
`http2.request-streaming-progress-before-upload-complete` parity cases, one
case per profile. In the push-triggered
[CI run 39066848395](https://github.com/appunni-m/uvicorn-rs/actions/runs/39066848395),
Rust quality, MSRV, native composition, and installed-wheel public parity have
passed. The unified parity/fault-coverage matrix also completed 753/753 cases
with three ASGI and three native repeats, 9,131/9,131 regions, and 6,741/6,741
lines. That run predates the current dirty checkout; the full performance
matrix has not been rerun for this change.

Local-only JSON receipts are in
`benchmarks/results/2026-10-18-ubuntu-x86-focused-upload/`: baseline and 5 ms
normal runs (including the clean exact-commit confirmation), their
diagnostic-only stage runs, the 10 ms trial, two parity results, and two
diagnostic-only Speedscope profiles. No server logs or coverage reports are
part of these receipts.

### Separate 1 KiB upload workload

The same 5 ms candidate commit was also measured on a distinct FastAPI input:
1 MiB POST bodies delivered in 1 KiB client writes at concurrency 8. This run
used five valid repetitions per server, with zero request failures and clean
shutdowns. It is an x86-64 result and does not clear the earlier ARM64
correctness failures for this workload.

| Server | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + uvloop + httptools | 626.7 | 12.62 | 16.65 | 18.40 | 1,580.1 | 57.9 |
| `uvicorn-rs` + uvloop | 561.8 | 14.32 | 17.55 | 19.18 | 2,376.6 | 60.5 |

On this case, `uvicorn-rs` reached 89.6% of Uvicorn throughput, with 1.05×
the p95 latency and 1.50× the server CPU per request. The receipt records
CPython 3.12.13, FastAPI 0.142.4, uvloop 0.23.0, Uvicorn 0.54.0, and the same
candidate source files before and after the run. This separate workload does
not measure the effect of the 5 ms setting against a 1 ms baseline; it only
compares both servers on the same 1 KiB-write input. Its local-only receipt is
`benchmarks/results/2026-10-18-ubuntu-x86-focused-upload/upload-1k-exact.json`.

#### Clean current-source replay with Node.js client (2026-10-18)

I repeated only this workload from clean commit
`ddd44af6e2d2e4fb00f4eb716ae6e16a0549261b` in the existing Ubuntu x86-64 work
folder. Both servers received the same FastAPI 1 MiB upload split into 1 KiB
writes, at concurrency 8, with a 1-second warmup and five 5-second
repetitions. The native libcurl client was unavailable, so both sides used
Node.js 25.1.0 and checked complete response bodies. The environment was
CPython 3.12.13, FastAPI 0.142.4, Uvicorn 0.54.0, uvloop 0.23.0, and httptools
0.8.0. The Tokio blocking-thread limit was unset. Source identity matched
before and after the run, and the uninstrumented native extension hash was
stable at
`0459657ad788852619313e9c136be5901e346c141dab5af5d684cc5db19d8658`.

All ten rows were timing-valid, had zero request failures, passed full-body
checks, and shut down cleanly. The table reports medians across the five
repetitions for each server:

| Server | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Mean server CPU (% of one core) | Client CPU µs/request | Mean client CPU (% of one core) | Peak server RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + uvloop + httptools | 785.2 | 9.88 | 13.84 | 15.51 | 1,266 | 91.0% | 998 | 71.7% | 57.1 |
| `uvicorn-rs` + uvloop | 963.5 | 8.20 | 11.45 | 13.28 | 1,566 | 137.9% | 876 | 75.4% | 62.4 |

On this run `uvicorn-rs` completed 1.23× as many requests per second and had
0.83× the p95 latency, while using 1.24× the server CPU per request and 1.09×
the peak server RSS. It handled this input faster in wall time, not with less
server CPU. The server process averaged 137.9% of one logical core for Rust
versus 91.0% for Uvicorn. This run used the server's one Tokio async worker
and left `UVICORN_RS_MAX_BLOCKING_THREADS` unset. That async-worker limit does
not cap process CPU at 100%, because Tokio's separate blocking pool can also
run work. The report has no per-thread CPU, so it cannot attribute the extra
CPU to a specific thread or bridge operation. The earlier timeout did not
recur, but this Node-client x86 run does not explain the ARM64 failures or the
earlier libcurl timeout. Its result must not be combined with the preceding
libcurl C-client table: the client implementation and source snapshot differ.
The raw ignored report is
`benchmarks/results/2026-10-18-ubuntu-x86-upload-validated/fastapi-upload-1m-write-1k.json`
(467,886 bytes; SHA-256
`9a9f6ab95de9eba970676c528648006fd440120d8b04f79d3471bdfd3f5002f4`).

### Ordinary FastAPI validated route

To check whether the gap was limited to request-body handling, the same clean
candidate commit was measured on FastAPI's validated `/items/7?repeat=3` route
at concurrency 64. The run used five valid repetitions per server, a 1-second
warmup, and 5-second samples; every row passed response checks and graceful
shutdown. Both servers used the same CPython 3.12.13, FastAPI 0.142.4, uvloop
0.23.0, Uvicorn 0.54.0, and httptools 0.8.0 environment. The native C client
was unavailable in this shell, so both servers used the benchmark's Node.js
25.1.0 fallback with full response-body checking.

| Server | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn + uvloop + httptools | 6,103.0 | 9.88 | 12.02 | 19.87 | 162.8 | 50.0 |
| `uvicorn-rs` + uvloop | 4,705.1 | 13.75 | 16.39 | 19.71 | 277.2 | 53.6 |

On this route, `uvicorn-rs` reached 77% of Uvicorn throughput, with 1.36× the
p95 latency and 1.70× the server CPU per request; p99 was near parity in this
five-repetition sample. Because this route does not read an upload body, the
remaining gap is not explained by request-body coalescing alone. The run shows
where more attribution is needed; it does not identify the responsible server
functions. Its local-only receipt is
`benchmarks/results/2026-10-18-ubuntu-x86-focused-upload/validated-route-exact.json`.

### Client-limited FastAPI `/fixed` diagnostic

A separate five-repetition `/fixed` run at concurrency 64 passed all response
checks and clean shutdowns, but the native C client was unavailable and the
Node.js 25.1.0 fallback consumed 97.2% of one CPU for Uvicorn (74.1% for Rust).
The harness host-activity guard marked the rows timing-valid; the Uvicorn-side
load generator was nevertheless close to its single-core limit. Treat the
throughput and latency values as client-limited diagnostics, not a rankable
server comparison. The raw receipt is
`benchmarks/results/2026-10-18-ubuntu-x86-focused-upload/fastapi-fixed-exact.json`.
A lower-concurrency check at concurrency 32 confirmed the same cap: the two
Uvicorn samples reached about 10.1k requests/s while the Node process used
95.0% and 98.8% of one CPU. That run was stopped after the first paired sample;
it retained that Rust/Uvicorn pair and one additional Uvicorn sample. Its
partial JSONL checkpoint is retained as
`benchmarks/results/2026-10-18-ubuntu-x86-focused-upload/fastapi-fixed-c32-diagnostic.jsonl`.
These samples are correctness evidence only and are not used for ranking.

## Focused HTTP/2 `protocol-scope` diagnostic (Ubuntu x86-64; 2026-10-18)

This focused comparison used the same clean commit, FastAPI app, native Rust
H2 probe, Python environment, and Ubuntu x86-64 host for both servers. The host
was Ubuntu 24.04.5 on an AMD Ryzen 5 2600X (6 cores/12 threads); the run used
CPython 3.12.13, Rust 1.91.1, and Hypercorn 0.18.0. The `protocol-scope`
workload sent GET `/protocol` over TLS with verified H2 ALPN, concurrency 64,
four client connections, 16 streams per connection, a 1-second warmup, 5-second
samples, and five repetitions. The native client checked status and every
response byte.

Because Uvicorn does not provide an HTTP/2 server, the reference is Hypercorn
asyncio. The Rust/asyncio and Hypercorn/asyncio runs were separate sequential
invocations (Rust first, reference second), not an interleaved randomized
comparison. The median figures below use four timing-valid Rust repetitions
and five timing-valid Hypercorn repetitions. Rust repetition 3 was excluded
for unrelated host CPU activity. All ten samples had zero request failures
and passed graceful shutdown; common valid repetition labels are 1, 2, 4, and
5, but separate runs mean they are not randomized within-run pairs. Neither
the focused harness reports qualifies this one-workload comparison as general
performance evidence.

| Server | Valid repetitions | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU µs/request | Peak RSS MiB | Client CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `uvicorn-rs-asyncio` | 4/5 | 5,640.8 | 11.33 | 17.64 | 20.57 | 218.6 | 48.1 | 19.9% |
| Hypercorn asyncio | 5/5 | 2,585.7 | 23.99 | 39.51 | 42.38 | 383.3 | 91.9 | 35.8% |

Across these valid-sample medians, Rust reached 2.18× the Hypercorn throughput,
with 0.47× p50, 0.45× p95, 0.49× p99 latency, 0.57× server CPU per request,
and 0.52× peak RSS. The native client was not saturated. This is promising
evidence for this small H2 scope response on this x86-64 host; it does not
establish a multi-workload, multi-system gain or explain the slower H1 FastAPI
results. The runs are diagnostic and should be followed by an interleaved
matched H2 workload set before using them in a release performance claim.

The candidate's five measured rows were fully checkpointed, but its first
invocation lacked `rustc` on the SSH `PATH` during final report generation. The
report was recovered from those rows after rechecking source, binary, client,
and dependency identities; no timing repetition was rerun. The reference run
used the corrected `PATH`. Local-only reports, JSONL checkpoints, metadata,
and server logs are in
`benchmarks/results/2026-10-18-ubuntu-x86-focused-h2-protocol-scope/`.

Both runs used clean commit `33a705dc93e0803043994f9c4b57831f2aafc38c` and
source digest
`5ac198689cc5331e30e808819c753603fc234661185f2ec8ff21d217bc49713e`.
The full parity/fault-coverage CI run
[39066848395](https://github.com/appunni-m/uvicorn-rs/actions/runs/39066848395)
passed 753/753 cases with three ASGI and three native repeats, 9,131/9,131
regions, and 6,741/6,741 lines. Its exact-source coverage report still awaits
Coverage-MCP review, and the run predates this dirty local checkout.

## Focused FastAPI WebSocket text-echo result (Ubuntu x86-64; 2026-10-18)

This normal-build diagnostic used the stock FastAPI `/echo` route with a
32-byte text payload, persistent WebSocket connections, concurrency 32, a
1-second warmup, five 5-second repetitions, and seed `20261018`. The same
CPython 3.12.13 environment served FastAPI 0.142.4, Starlette 1.7.0, and
Pydantic 2.13.5 through either Uvicorn 0.54.0 or `uvicorn-rs-py`; both servers
were tested with asyncio and uvloop 0.23.0. Uvicorn used the `websockets`
backend 17.1. The Rust client used persistent `tokio-tungstenite` connections
and validated the complete echoed message on every sample.

The host was Ubuntu 24.04.5 on an AMD Ryzen 5 2600X (6 cores/12 logical CPUs).
It passed the host preflight. All 20 rows completed with zero message failures
and clean shutdown; two rows were excluded for unrelated host CPU activity
(Rust/asyncio repetition 2 and Uvicorn/uvloop repetition 5). Each same-loop
pair has four matching timing-valid repetitions: asyncio repetitions 1, 3, 4,
and 5; uvloop repetitions 1 through 4. Table values are medians over those
same-repetition matches.

The raw report sets its overall `timing_valid` field to `false` because two
rows were excluded. The matched valid rows below are a focused diagnostic
subset; they are not a rankable benchmark result or release performance
evidence.

| Loop | Server | Matched reps | Messages/s | p50 ms | p95 ms | p99 ms | Server CPU µs/message | Server CPU % elapsed | Peak RSS MiB | Client CPU µs/message |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| asyncio | Uvicorn | 4 | 21,129 | 1.451 | 1.767 | 1.862 | 47.1 | 96.1 | 48.6 | 35.5 |
| asyncio | `uvicorn-rs` | 4 | 8,718 | 3.747 | 5.257 | 5.865 | 191.5 | 156.3 | 52.4 | 41.0 |
| uvloop | Uvicorn | 4 | 24,300 | 1.238 | 1.558 | 1.632 | 40.9 | 96.2 | 51.2 | 32.3 |
| uvloop | `uvicorn-rs` | 4 | 15,899 | 2.188 | 2.717 | 3.040 | 104.2 | 154.5 | 55.0 | 33.5 |

The median of same-repetition throughput ratios was 0.412× Uvicorn with
asyncio and 0.658× with uvloop. Rust p95 latency was 2.98× and 1.74× the
respective Uvicorn medians. Server CPU per echoed message was 4.07× and 2.55×
higher; sampled RSS was about 3.8 MiB higher in both comparisons. Client CPU
was similar. The client is closed-loop and latency includes client work; client
CPU includes setup, drain, and reporting. The run does not provide per-thread
or call-path attribution, so the higher server cost is measured but not
assigned to a specific Python/Rust stage. This diagnostic reinforces the
existing `scope_revised` decision for the Python ASGI path; it does not claim
that the Rust server is faster for this workload.

Before timing, `websocket.text-and-binary-round-trip` passed 1/1 on the same
normal build. The benchmark then checked each measured echoed text payload and
graceful shutdown. Reproduction command from the work folder:

```sh
.venv/bin/python scripts/run_websocket_category_bench.py \
  --workloads text-echo \
  --servers uvicorn-asyncio-websockets uvicorn-uvloop-websockets \
    uvicorn-rs-asyncio uvicorn-rs-uvloop \
  --duration 5 --warmup 1 --concurrency 32 --repetitions 5 \
  --seed 20261018 \
  --output benchmarks/results/2026-10-18-ubuntu-x86-websocket-text-echo/websocket.json
```

The report is bound to clean commit `ddd44af6e2d2e4fb00f4eb716ae6e16a0549261b`,
source digest
`aa0db14d4790535150a271705206596370b694389e2e958407f3c4b5002796a4`, native
extension SHA-256
`0459657ad788852619313e9c136be5901e346c141dab5af5d684cc5db19d8658`, and
benchmark-client SHA-256
`d0b7e86d0d3a529764611794c372fb82e12464c823d9cc1672e970227ae12457`. The
measured server, app, Python bridge, and WebSocket harness sources are unchanged
between that commit and the current branch head; this is one clean x86-64
workload, not a multi-system or release performance result. The current
performance decision remains `scope_revised`: no broad speed claim for the
Python ASGI client. The local-only raw report, JSONL, preflight, and logs are in
`benchmarks/results/2026-10-18-ubuntu-x86-websocket-text-echo/`; the raw JSON
SHA-256 is `c7a526684558001d17f9fc241253b460b3a9681c8dc714f3ba986d4c36b560c2`.

## Focused per-thread CPU profile for FastAPI HTTP/1.1 (Ubuntu x86-64; 2026-10-18)

This diagnostic profiled the ordinary FastAPI `fastapi-validated-route` with
concurrency 32, a 1-second warmup, and three 5-second repetitions per server.
Both sides used CPython 3.12.13, FastAPI 0.142.4, Starlette 1.7.0, and
Pydantic 2.13.5. Uvicorn 0.54.0 used asyncio and httptools 0.8.0; the Rust ASGI
client used asyncio. The same Node 25.1 HTTP/1.1 client checked complete
response bodies. The host was the same Ubuntu 24.04.5 / Ryzen 5 2600X system.

All six rows completed with zero request failures, stable source and extension
identities, and clean server shutdown. The diagnostic bootstrap took Linux
per-thread CPU snapshots from `/proc/self/task/*/schedstat` around the measured
load. The report is explicitly `diagnostic_only` with `timing_valid: false`;
its timing rows are not rankable or release performance evidence.

| Server | Requests/s | p95 ms | Server CPU µs/request | Python event-loop CPU µs/request | Tokio-named thread CPU µs/request | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Uvicorn / asyncio / httptools | 6,022 | 6.852 | 165.8 | 165.3 | 0 | 47.4 |
| `uvicorn-rs` / asyncio | 4,157 | 9.405 | 309.5 | 183.9 | 123.8 | 49.0 |

The matched diagnostic shows 0.69× Uvicorn throughput, 1.37× p95 latency, and
1.87× server CPU per request for this route. Within `uvicorn-rs`, about 60% of
measured server thread CPU was on the Python event-loop thread and 40% on
Tokio-named runtime threads. The Python event-loop cost was about 11% higher
per request than Uvicorn's; the Tokio-named group used another 124 µs/request.
The Rust source configures one Tokio async worker. The snapshot contains one
active Tokio-named thread and one with zero CPU and zero timeslices, but thread
names alone do not identify which runtime pool a thread belongs to: Tokio also
uses the configured name for blocking-pool threads. This profile measures the
named-thread group, not the async worker in isolation.

This locates CPU at the Python event-loop and Rust runtime-thread levels, but
does not attribute it to functions or individual ASGI handoffs. `perf_event_paranoid`
is 4 on the host, and no `py-spy` or `samply` executable was available for
call-stack sampling. The results support the measured CPU gap but do not prove
which protocol, scheduling, or bridge operation causes it. The client is
closed-loop and latency includes client work; client CPU also includes setup,
drain, and reporting.

Reproduction command in the provided work folder (Node 25.1 is installed under
NVM and must be on `PATH`):

```sh
PATH=/home/appunni/.nvm/versions/node/v25.1.0/bin:$PATH \
  .venv/bin/python scripts/profile_fastapi_loop_cpu.py \
  --workloads fastapi-validated-route \
  --servers uvicorn-asyncio-httptools uvicorn-rs-asyncio \
  --duration 5 --warmup 1 --concurrency 32 --repetitions 3 \
  --output-dir benchmarks/results/2026-10-18-ubuntu-x86-fastapi-validated-thread-profile-node25
```

The clean measured source is commit
`ddd44af6e2d2e4fb00f4eb716ae6e16a0549261b`, source digest
`4a282d79b3707254473849983aa57d8c6716c53b74570d9535205ab77a40d253`, and
normal extension SHA-256
`0459657ad788852619313e9c136be5901e346c141dab5af5d684cc5db19d8658`. The
profile script digest is
`6899b7a3fcb3ea0a83be8165181146adea3611d02d506e91cf37d34d8b63c9f2`. The
measured Rust server, Python bridge, FastAPI route, HTTP runner, and profile
script are byte-identical between this source commit and the current branch
head. The
local-only `http1-benchmark.json` SHA-256 is
`366b7bee16a43a894a8c93e6490a20968c836469604e71c6036eb16d83a40bf3`; the
`profile-summary.json` SHA-256 is
`3f22d98341dacee517d19d1d3024125c3deb4c1d394fb137c4ebbf33f5284f94`. The
entire receipt and per-row server logs remain in the ignored
`benchmarks/results/2026-10-18-ubuntu-x86-fastapi-validated-thread-profile-node25/`.

## Focused per-thread CPU profile for FastAPI WebSocket text echo (Ubuntu x86-64; 2026-10-18)

This diagnostic repeated the FastAPI `/echo` case with a 32-byte text payload,
persistent WebSocket connections, concurrency 32, a 1-second warmup, and three
5-second repetitions per server. It compared Uvicorn 0.54.0 using the
`websockets` 17.1 backend with `uvicorn-rs-py`, both under asyncio and using
the same Rust WebSocket client. The application and Python environment match
the five-repetition text-echo result above: CPython 3.12.13, FastAPI 0.142.4,
Starlette 1.7.0, and Pydantic 2.13.5. The host was Ubuntu 24.04.5 on an AMD
Ryzen 5 2600X (6 cores/12 logical CPUs).

All six samples completed with zero message failures, stable source and native
extension identities, and clean shutdown. The profile sampled Python event-loop
thread CPU with `time.thread_time_ns` and Linux per-thread scheduler CPU from
`/proc/self/task/*/schedstat`. The wrapper deliberately set every row to
`timing_valid: false` and `performance_evidence_status: diagnostic_only`; the
throughput and latency medians below are context for the CPU profile and must
not be used as rankable benchmark results.

| Server | Observed messages/s | Observed p95 ms | Server CPU µs/message | Python event-loop CPU µs/message | Tokio-named thread CPU µs/message |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uvicorn / asyncio / websockets | 21,138 | 1.752 | 47.1 | 46.7 | 0 |
| `uvicorn-rs` / asyncio | 7,967 | 5.800 | 210.5 | 64.3 | 144.4 |

In this unrankable profile, `uvicorn-rs` used 0.377× Uvicorn's observed
throughput, had 3.31× the p95 latency, and consumed 4.47× the server CPU per
message. The Python event-loop thread used about 38% more CPU per message than
Uvicorn. Tokio-named threads accounted for about 69% of the Rust server's
measured CPU in this run. Eight Tokio-named threads had CPU during each Rust
sample, even though the server configures one async Tokio worker. Tokio 1.53.1
uses the runtime's thread-name function for blocking-pool threads too, so this
count cannot be read as eight async workers.

The source provides a strong lead for the extra runtime CPU: each ASGI
WebSocket receive enters `future_into_py` in
[`WebSocketIo::receive`](https://github.com/appunni-m/uvicorn-rs/blob/main/src/lib.rs#L2950). The pinned
`pyo3-async-runtimes` 0.29 completion path dispatches Python future resolution
through `spawn_blocking`, attaches to Python, and schedules the result on its
owning event loop. This work recurs for awaited receives; the ordinary
WebSocket send path uses `try_send` and creates a future only when the bounded
queue is full ([send path](https://github.com/appunni-m/uvicorn-rs/blob/main/src/lib.rs#L3268)). That points to the receive
completion handoff as a high-value optimization target, but the thread snapshot
does not measure its individual cost or separate it from other Rust work.
Python event-loop CPU also includes native calls made on that thread. The
client is closed-loop, so its latency includes client work. These measurements
do not identify individual functions or prove a cause for the full CPU gap.

The next performance experiment is one host-clean, matched comparison of this
same echo input with the default pool and cap one. Both cap-one attempts so far
were rejected by the per-sample host guard, so no pool-cap performance claim is
qualified. If a clean run confirms the signal, check the cap against the
focused HTTP and lifecycle contracts before considering it as a default. A
code-level bridge change should target the per-receive completion handoff while
preserving asyncio loop ownership, `contextvars`, cancellation, and disconnect
semantics. Do not infer a Python-free native-path result from this Python ASGI
profile.

The measured source is clean commit
`ddd44af6e2d2e4fb00f4eb716ae6e16a0549261b`, source digest
`aa0db14d4790535150a271705206596370b694389e2e958407f3c4b5002796a4`, and
normal extension SHA-256
`0459657ad788852619313e9c136be5901e346c141dab5af5d684cc5db19d8658`. The
measured server, bridge, WebSocket benchmark, and profiling bootstrap sources
are byte-identical between that commit and the current branch head. The
out-of-tree wrapper is archived with the local-only report; its SHA-256 is
`74b6164ade1452876dd05a90e2703c2df1eedd012676ec165f67e0d67589b10f`, and the
bootstrap SHA-256 is
`8817a9c39cb9ccf70597780534c899a5561e0853c503623cbf8cc83711ac0f8f`. The
raw `websocket.json` SHA-256 is
`3f025beae48e90b009e71d33d3d0a3df287a9f22bf4222da52435b544aa5e8a2`; the
profile summary SHA-256 is
`7e32227c56900a6f00974bf1556df032956eb48e72e3ec1e897f162ecd1f6e95`. The
full local-only receipt, per-thread snapshots, wrapper, and server logs are in
`benchmarks/results/2026-10-18-ubuntu-x86-websocket-text-echo-thread-profile/`.

### Blocking-pool cap-one probes (host-contended; not a performance result)

I ran this same profile twice with `UVICORN_RS_MAX_BLOCKING_THREADS=1`. Both
runs passed all echo and shutdown checks, but the benchmark's per-sample host
guard rejected every row for unrelated CPU activity. A post-run preflight
rejected once because a process exceeded 25% CPU for two consecutive
intervals. A later preflight accepted, but the per-sample guard rejected all
six rows in the follow-up too. The two unqualified Rust runs observed medians
of 11,254 and 11,331 messages/s, 4.057 and 4.241 ms p95, and 145.8 and 143.2
server CPU µs/message, respectively, with two active Tokio-named threads in
both profiles. These readings repeat the same signal, but they are not
qualified pairs and do not establish a cap-one improvement or causal
relationship. The default-pool profile above is also from a different run.
Do not bypass the guard; stop timing on this host until it can keep a clean
per-sample window. The two ignored receipts, runner logs, and host-preflight
records are in
`benchmarks/results/2026-10-18-ubuntu-x86-websocket-text-echo-thread-profile-cap1/`
and
`benchmarks/results/2026-10-18-ubuntu-x86-websocket-text-echo-thread-profile-cap1-retest-after-preflight-accept/`.
The two raw report SHA-256 values are
`e3b4b5d361c81a121c6c63052d9f445166960e31faee39cb64bd3fadb46a1d9f` and
`eeb7ec5ec22201f05ae615f64505b69c12f9780e456e79263f99586161fe5d8c`; the
profile summary SHA-256 values are
`b46eeaf3317a9644cc4ba48cc9dea229e47373092330d9eb39e95e599dcb2c15` and
`3ed3b4bb073754bf77471f3636024e4ee4a7ed751d4fa7b8a5a28b76bdf13cbc`.

## Latest full multi-system matrix (run 39036702600; 2026-10-17)

The [matrix run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39036702600)
completed against clean main commit
`b27ee4dcf810c0815c7ff76af426bf1a27fd7d45`, but all three platform jobs
failed their category gate. Linux x86-64 and Linux ARM64 failed HTTP/1
correctness: the retained category reports list failed rows 102 and 128, 129,
137, and 140 respectively. macOS ARM64 failed the HTTP/2 category. The other
reported categories completed, but failures make this matrix ineligible as a
complete performance result. The failed step on all three systems was
“Run every maintained category sequentially and analyze matching valid
repetitions.” The artifacts retain the category reports and logs for focused
root-cause work.

### Failure diagnosis from the retained artifacts (2026-10-18)

The Linux HTTP/1 failures share a client-timeout signature. On x86-64,
`fastapi-request-upload` failed once on `uvicorn-rs-uvloop` at concurrency 64:
the libcurl client timed out after 2,785 completed 1 MiB uploads and about
2.9 GB of request data. On ARM64, `fastapi-upload-1m-write-1k` failed four
times on Rust servers at concurrency 8; that input sends 1 MiB bodies with a
1 KiB client read cap. Both reports use libcurl's 15-second request timeout.
The server logs show Starlette observing `ClientDisconnect` after the client
has timed out. They do not show why the stalled request exceeded the timeout,
so the Linux H1 issue remains open.

The current worktree adds client-side failure detail for future focused
reproductions: `first_failure.transfer` will report bytes passed to libcurl's
upload callback versus bytes libcurl reports uploaded, along with response
status and transfer-stage timings. This is not present in run 39036702600 and
does not identify bytes received by the server. It narrows the next failure
capture; it is not a diagnosis or performance measurement.

The telemetry was checked with one synthetic loopback timeout: the handler
accepted the request headers, did not read the upload body, and withheld its
response. At libcurl's 15-second timeout, the client reported 851,834 bytes
returned from its upload callback, 801,286 bytes uploaded, zero response bytes,
and no HTTP status. This confirms the failure record distinguishes client-side
upload progress from response progress. It is an instrumentation check, not a
reproduction of the FastAPI failure or proof of what reached the server socket.

The macOS HTTP/2 failure was different. `request-upload` on `hypercorn-asyncio`
failed in warm-up after 193 response-checked requests because the H2 probe's
connection driver did not stop within its five-second cleanup deadline. The
[`run_h2_category_bench.py`](https://github.com/appunni-m/uvicorn-rs/blob/main/scripts/run_h2_category_bench.py) config leaves
Hypercorn's default five-second keep-alive timeout in place. The retained
environment identifies Hypercorn 0.18.0; its local
`Config` default is `keep_alive_timeout=5.0`, matching the probe's old
peer-close allowance.
The H2 probe now allows ten seconds for this post-measurement cleanup; request
timing is captured before that wait in
[`http2.rs`](https://github.com/appunni-m/uvicorn-rs/blob/main/tools/http3-probe/src/bin/http2.rs). A focused local macOS
replay of only this workload and server passed both repetitions with zero
request failures and clean server shutdown. The replay's timing was rejected
because of unrelated host CPU activity; it validates cleanup handling, not
performance, and the hosted matrix has not been rerun.

A separate local macOS replay of the x86-64 H1 input on
`uvicorn-rs-uvloop` completed one repetition at concurrency 64 with 7,078
requests, zero failures, and clean server shutdown. Its timing was also
rejected for unrelated host CPU activity. This different-architecture replay
does not explain or clear the Linux upload timeouts.

This matrix predates the later branch changes, including
`a009d9ede77ad81a4d06c40dc4676b70119790fb` and the focused upload tuning
trial above; it is not exact-source candidate evidence for those changes. No
complete multi-system benchmark result is available for them. The current
decision in [`performance-acceptance.json`](performance-acceptance.json) is
`scope_revised`:
Python ASGI remains the compatibility and regression path, without a general
speed-superiority claim; performance claims target Python-free Rust-native
application composition. The remaining candidate gate still requires a
correctness-complete, qualified multi-system run on the exact release commit.

## Focused HTTP/2 candidate diagnostic (2026-10-17)

The Git-push-triggered [run 39025351808](https://github.com/appunni-m/uvicorn-rs/actions/runs/39025351808)
tested commit `a8d84d0a3b4a90d5737617a76a62be5395264110` on Linux x86-64. It ran
`examples.bench_fastapi:app` through `uvicorn-rs-asyncio` with CPython 3.12.13
and Rust 1.98.1. The selected `protocol-scope` workload used verified H2 ALPN,
concurrency 64, four client connections, five repetitions, a 1-second warmup,
and a 5-second measurement per repetition.

All five response and clean-shutdown checks passed. Repetition 1 was excluded
because the host monitor detected unrelated CPU activity, leaving four valid
timing rows. The table reports the median of those four rows; latency values
are medians of the per-row percentiles.

| Metric | `uvicorn-rs-asyncio` |
|---|---:|
| Throughput | 5,196.56 req/s |
| p50 latency | 12.37 ms |
| p95 latency | 19.52 ms |
| p99 latency | 23.07 ms |
| Server CPU | 243.65 µs/request (123.37% of elapsed time) |
| Client CPU | 14.03% of elapsed time |
| Peak server RSS | 48.64 MiB |
| Peak client RSS | 6.02 MiB |

This diagnostic ran only uvicorn-rs and has no matched Hypercorn result. It is
not a performance comparison and establishes no speedup. Source SHA-256 is
`fead54a838f7658419b8f0f621a9ca00bb13579b0322859b3b322e93d4208a08`; the
normal native binary SHA-256 is
`4ec09abc9b547370ea4bafbf1d4d5843551f4719d214d07e1e48c28ae5cba893`. The
[workflow artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39025351808/artifacts/12098656237)
contains raw repetitions, host observations, hashes, and server logs.

## Full three-system matrix result (2026-10-17)

The [matrix run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268578)
measures commit `aa4c93836f5e2147462837bbd8b1bde6c0ebe84e`. Exact-binary public
parity and selected FastAPI-only comparisons passed on all three systems.
Linux x86-64 and macOS ARM64 completed their category runs; Linux ARM64 stopped
at its H3 correctness gate during `many-response-chunks`. The Linux ARM64
artifact retained 90 of 130 H3 rows before stopping. The matrix is terminal but
incomplete as a three-system result.

The first divergence was on repetition 3 of `hypercorn-uvloop`: request 43
returned HTTP 200 with 4,096 response bytes in four data chunks where the
client expected 1,048,576 bytes; there was no Content-Length header. The
retained Hypercorn server log then reports its UDP task failing with
`KeyError(164)` while looking up the H3 stream in `protocol/h3.py` during
teardown. This is the observed sequence, not a proven root cause. It could be
an intermittent Hypercorn H3 stream-lifecycle failure or another interaction
in that reference/client path. The focused same-source
[run 39026041230](https://github.com/appunni-m/uvicorn-rs/actions/runs/39026041230)
passed all five full-response, lifecycle, and clean-shutdown repetitions;
four timing rows passed the host guard, but this reference-only run is not a
comparison. Causality remains unproven. The matrix failure invalidates the
affected H3 comparison and prevents a completed three-system aggregate. Do not
infer a Rust performance win from these partial rows.

The run predates the H3 cancellation case on `93d1217` and does not cover that
new conformance input. Runtime Rust sources, the Python bridge, and dependency
manifests are unchanged between this matrix source and current main
`76379e2d64abc33e01827a9f160223e761858779`. Current-head CI
[39026041176](https://github.com/appunni-m/uvicorn-rs/actions/runs/39026041176)
has not started its jobs yet. Older exact-head CI
[39024130047](https://github.com/appunni-m/uvicorn-rs/actions/runs/39024130047)
has passed unified coverage, native composition, installed-wheel parity, MSRV,
Rust quality, and the Windows package job on `77e1f425`. Its Linux candidate
wheel parity job is running and its macOS package job is queued. Those results
do not substitute for current-head CI.

## Cross-system category and FastAPI-only findings (2026-10-17)

The category ratios below are medians across qualified workload/loop pairs
within each system. They are not request-weighted aggregates or one overall
speed score. H1 and WebSocket use stock Uvicorn references; H2 and H3 use stock
Hypercorn references.

| Category | Linux x86-64 | Linux ARM64 | macOS ARM64 |
|---|---:|---:|---:|
| HTTP/1.1 | 0.663x (6/30 faster) | 0.651x (5/30 faster) | 0.730x (7/28 faster) |
| HTTP/2 | 2.208x (8/14 faster) | 2.495x (10/14 faster) | 2.958x (13/14 faster) |
| HTTP/3 | 2.259x (11/12 faster) | no qualified rows; correctness gate failed | 3.145x (10/12 faster) |
| WebSocket | 0.559x (2/6 faster) | 0.705x (2/6 faster) | 0.777x (2/6 faster) |

These medians hide workload reversals. HTTP/2 `many-response-chunks` measured
0.069x on Linux x86-64 and 0.083x on Linux ARM64, while macOS ARM64 was near
parity at 0.992x. HTTP/1.1 upload workloads reached 0.237x on Linux x86-64 and
0.265x on Linux ARM64. WebSocket text echo ranged from 0.365x to 0.487x across
the systems; handshake-only workloads were faster.

The stock FastAPI-only comparison used the same `examples.bench_fastapi:app`,
Python 3.12.13, FastAPI 0.142.4, Starlette 1.7.0, and Pydantic 2.13.5 for both
servers. Four selected pairs qualified on each Linux system; two of four
qualified on macOS. The small validated route exposes a repeated regression:

| System and loop | Rust/Uvicorn throughput | Server CPU per request, Rust/Uvicorn | p50, Rust/Uvicorn |
|---|---:|---:|---:|
| Linux x86-64, asyncio | 0.654x | 262 / 141 µs | 13.64 / 8.98 ms |
| Linux x86-64, uvloop | 0.705x | 226 / 130 µs | 11.94 / 8.25 ms |
| Linux ARM64, asyncio | 0.759x | 295 / 183 µs | 15.63 / 11.59 ms |
| Linux ARM64, uvloop | 0.870x | 260 / 185 µs | 13.72 / 11.75 ms |

For the Python CPU workload, Rust/Uvicorn throughput was 0.918x and 0.931x on
Linux x86-64, 0.963x and 0.984x on Linux ARM64, and 0.922x and 1.030x on macOS
ARM64 (asyncio/uvloop where available). Near parity on this Python-heavy route
contrasts with the small validated route and suggests fixed server-path work
is a substantial part of the latter gap. This is an inference from aggregate
measurements, not a profiled causal breakdown.

The source confirms several candidate costs: each Python app request is
scheduled onto its owning event loop with `call_soon_threadsafe`, then wrapped
in an asyncio task and completion callback ([`python_task_future`](https://github.com/appunni-m/uvicorn-rs/blob/main/src/lib.rs#L2508));
the Python bridge creates per-request async `receive` and `send` wrappers
([`_bridge.py`](https://github.com/appunni-m/uvicorn-rs/blob/main/python/uvicorn_rs/_bridge.py#L4)); and `build_scope` creates
Python scope dictionaries, header tuples, bytes, and address values for every
request ([`build_scope`](https://github.com/appunni-m/uvicorn-rs/blob/main/src/lib.rs#L7013)). The Rust server also uses
Hyper's HTTP/1 path while the reference uses Uvicorn's `httptools` backend.
The benchmark does not isolate any one of these costs.

Immutable Python `bytes` response bodies use PyO3's `bytes::Bytes` extraction
backed by `PyBackedBytes`, retaining the Python owner instead of copying the
response body into a Rust allocation. The validated GET has no request body, so
request-body materialization is not a likely explanation for that particular
route gap. HTTP upload workloads still materialize Python `bytes` ASGI request
messages from Rust body storage.

The locked [PyO3 dependency](https://github.com/appunni-m/uvicorn-rs/blob/main/Cargo.lock#L528) is 0.29.3. Its `Bytes`
extractor retains immutable Python `bytes` with `PyBackedBytes` and
`Bytes::from_owner`; for a Python `bytearray`, it copies into Rust-owned
immutable storage so later mutation cannot change a response while it is being
streamed. In the other direction, [`RequestBody::into_py_bytes`](https://github.com/appunni-m/uvicorn-rs/blob/main/src/lib.rs#L1962)
allocates and fills one Python `bytes` object per ASGI request message. A
segmented Rust batch is coalesced in that single materialization, so transport
segment count does not create one Python-body copy per segment. These are
source-level ownership facts, not measured CPU attribution. The bodyless
validated GET takes neither request-body conversion path.

The small-route result does not point to SIMD as the first optimization.
First isolate parser/runtime work, Python task scheduling, scope construction,
and ASGI send/receive stages with the existing diagnostic-only flags
`--require-runtime-diagnostics` and `--asgi-stage-diagnostics`. Instrumented
timing must not be treated as performance evidence. A sandboxed host preflight
could not enumerate processes. The read-only preflight with process access then
rejected all eight intervals: unrelated CPU ranged from 472% to 524%, with
multiple sustained processes above the guard. It started no benchmark. Its
ignored local receipt is
`target/benchmark-preflight/kata-continuation-20261017-escalated.json`; retry
the focused diagnostic only after a clean preflight or on a clean hosted
runner.

The matrix does **not** demonstrate a general performance gain over Uvicorn:
HTTP/1.1 and WebSocket category medians regress on all three systems, the small
FastAPI route regresses on every qualified Linux pair, and the full matrix is
incomplete. Keep the performance release gate open.

## Focused FastAPI ASGI-stage diagnosis (2026-10-17)

The hosted [run 39030988829](https://github.com/appunni-m/uvicorn-rs/actions/runs/39030988829)
completed on commit `96fc66a9b44f583478c90b4de9d60fce07714884` using Linux
x86-64, CPython 3.12.13, one Tokio worker, and the stock FastAPI workload
`fastapi-validated-route`. Three repetitions ran for each of four servers.
All twelve rows passed response checks, lifecycle checks, stable identity, and
clean shutdown. Host preflight passed. The [retained artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39030988829/artifacts/12100785359)
has SHA-256 `d953767bc30eb5f33155b822f178b4935e2818cf19e96162d09491a9de6ade32`.
Its measured source SHA-256 is
`bc8c9cc930c99532bb48e0da63fb26e37629144e0e9e2ca86e433350e75c0b11`; the
runtime-diagnostics extension SHA-256 is
`7116057ef6f3c50ef55df0b5432a3cbe8fd175901814c78af61d402342582589`.

Every row is intentionally marked timing-invalid because both Rust runtime
counters and the per-request FastAPI stage wrapper are enabled. The throughput,
latency, and CPU columns below are observations from an instrumented build, not
performance evidence. Stage columns are medians of the three repetition-level
percentiles and use one request as the unit.

| Server / loop | Observed req/s, non-rankable | Observed server CPU, non-rankable | ASGI app wall p50 | ASGI `send` wait p50 | App time outside ASGI I/O p50 |
|---|---:|---:|---:|---:|---:|
| uvicorn-rs / asyncio | 4,704.7 | 268.2 µs/request | 111.5 µs | 5.8 µs | 105.4 µs |
| Uvicorn / asyncio | 8,292.4 | 120.7 µs/request | 89.6 µs | 23.1 µs | 64.6 µs |
| uvicorn-rs / uvloop | 5,448.3 | 228.0 µs/request | 108.5 µs | 5.3 µs | 103.2 µs |
| Uvicorn / uvloop | 8,336.9 | 120.0 µs/request | 91.2 µs | 23.0 µs | 66.6 µs |

The Rust counters recorded one Python attachment and one Python task-starter
schedule per request. Their median accumulated wall time per call was 134.5 µs
and 77.3 µs under asyncio, and 118.2 µs and 34.5 µs under uvloop. They include
thread/task scheduling and callback work; they are not exclusive CPU or pure
GIL-wait measurements. The app-stage wrapper found no `receive()` calls, no
request-body bytes, and no request-body materialization/copy for this GET. The
response was 71 bytes over two ASGI sends, with no bounded response queue
backpressure. Request-body copy removal or SIMD applied only to body copying
cannot explain this workload's observed gap; the result does not assess SIMD
in HTTP parsing or other paths.

The measured Rust `send()` wait is shorter, while the ASGI app wall time and
the app time outside awaited `send()`/`receive()` are longer. That outside-I/O
time includes FastAPI route matching, parameter validation, response-model
serialization, Python execution, and any other awaits; it is not CPU time. The
evidence narrows the next measurement to per-request scheduling/task setup and
the Python ASGI execution path, but does not isolate a causal component. The
normal-build matched result below confirms this route regresses without
instrumentation; it still does not attribute the additional CPU to a specific
function or boundary operation.

## Focused normal-build FastAPI matched result (2026-10-17)

The hosted [run 39031849682](https://github.com/appunni-m/uvicorn-rs/actions/runs/39031849682)
compared the stock `fastapi-validated-route` workload on commit
`951c67b15faa8eef047432604e5a1785dd18776b`. Its
[retained artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39031849682/artifacts/12100423931)
has SHA-256 `bcd1e543e669b968867ea2657b7b5ad84dbd9483f90757321d78e414dbc9fcc5`.
This used the normal release wheel with runtime and ASGI-stage diagnostics
disabled. The accepted host preflight identified an AMD EPYC 7763 runner with
4 logical CPUs and 2 physical CPUs. The run used CPython 3.12.13, FastAPI
0.142.4, Starlette 1.7.0, Pydantic 2.13.5, Uvicorn 0.54.0, uvloop 0.23.0,
and httptools 0.8.0. Rust used one Tokio scheduler worker. The five-second
closed-loop load ran at concurrency 64 after a one-second warmup; it used a
bodyless GET and verified each complete response against the exact workload
oracle.

All 20 measured responses passed correctness, lifecycle, and shutdown checks.
Five repetitions formed valid asyncio pairs. Four formed valid uvloop pairs;
Uvicorn uvloop repetition 1 passed correctness and shutdown but was excluded
from timing for unrelated host CPU activity. The benchmark's pairwise medians
are:

| Loop | Matched reps | Uvicorn / Rust req/s (Rust ÷ Uvicorn) | Uvicorn / Rust p50 ms | Uvicorn / Rust p95 ms | Uvicorn / Rust p99 ms | Uvicorn / Rust server CPU µs/request | Uvicorn / Rust server RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| asyncio | 5 | 5,541 / 3,625 (0.652×) | 11.55 / 17.70 | 12.09 / 21.31 | 12.30 / 22.96 | 180.4 / 353.0 | 47.6 / 51.1 |
| uvloop | 4 | 5,469 / 3,996 (0.726×) | 11.46 / 16.07 | 12.22 / 19.12 | 22.77 / 20.52 | 182.2 / 319.0 | 50.4 / 53.6 |

For this route, Rust delivered 27–35% lower throughput while using 75–96%
more server CPU per request. Its p50 latency was 40–53% higher and p95 was
56–76% higher. The uvloop p99 median was lower for Rust in this one comparison;
the other tail results and the short closed-loop run should be interpreted
with the matched raw repetitions, not as a general latency claim. Client CPU
per request was 62.2 / 70.6 µs (Uvicorn / Rust) under asyncio and 66.1 / 69.5
µs under uvloop. Peak sampled server RSS was 47.6 / 51.1 MiB and 50.4 / 53.6
MiB, respectively.

The parity and host gates passed, but this is one workload on one hosted
runner, not a whole-server result or statistical-significance claim. The
load generator is closed-loop and does not correct for coordinated omission.
The measured source identity was
`0958da8681d648dea51f51fef39fb7872becbcd75e14031c32d16813ef854bee`; the
normal Rust extension SHA-256 was
`4ec09abc9b547370ea4bafbf1d4d5843551f4719d214d07e1e48c28ae5cba893`.

The request has no body, so request-body copying is not on this workload's
path. The server-process CPU delta is real for this run, but does not identify
whether it comes from protocol handling, scope creation, Python task
scheduling, bridge callbacks, or another component. The earlier instrumented
stage sample suggests the Python ASGI path is slower while Rust `send()` waits
are shorter; that is a lead for attribution, not proof of cause. The result
does not support SIMD or body-copy optimization as the first fix. It also does
not show the required performance gain, so the performance release gate stays
open. Continue with the underqualified H1 workloads and loop pairs, the small
WebSocket text-echo case, and the default/cap-1/cap-4 upload comparison after
their correctness gates; preserve the exact identities and rejected samples.

## Latest focused macOS HTTP/3 large-response comparison (2026-10-17)

Focused run [39013640218](https://github.com/appunni-m/uvicorn-rs/actions/runs/39013640218)
on commit `f815728ded987419123a786ce5a9c04c669c80cb` completed ten large-response
samples on macOS ARM64: five Hypercorn asyncio and five uvicorn-rs asyncio.
All response checks passed, and all servers shut down cleanly without force.
Only one of ten timing rows was valid; unrelated host CPU activity invalidated
the other nine, so there is no matched timing pair and no performance
conclusion. Artifact 12094156939 retains the samples and host observations.
The four-valid-pair Linux ARM64 result below remains scoped to one workload;
neither result closes the full multi-system benchmark gate.

## Focused matched HTTP/3 large-response comparison (2026-10-17)

The [focused run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39013025705)
on commit `e2a39c55594eb4aab2ac922c2e9128e970ca7f7e` compared Hypercorn and
uvicorn-rs with asyncio on one Linux ARM64 runner. Both served the same standard
FastAPI app (`examples.bench_fastapi:app`) under Python 3.12.13. The workload
was a bodyless HTTP/3 GET returning a cached 1 MiB response; server order was
randomized for each of five repetitions.

This exercises the Rust transport and HTTP/3 implementation with a real Python
FastAPI ASGI app. It does not remove the Python boundary, and it does not
measure a future Rust-native FastAPI/Starlette composition.

All five repetitions on both servers passed complete response validation and
clean, unforced shutdown. Rust repetition 1 was excluded from timing because
the monitor detected unrelated host CPU activity, leaving four valid matched
pairs (repetitions 2–5). The table reports each metric's median over that same
four-pair cohort.

| Metric | Hypercorn asyncio | uvicorn-rs asyncio | Change |
|---|---:|---:|---:|
| Throughput | 19.84 req/s | 483.74 req/s | 24.38× |
| p50 latency | 38.58 ms | 2.00 ms | 94.8% lower |
| p95 latency | 75.60 ms | 2.56 ms | 96.6% lower |
| p99 latency | 77.31 ms | 2.77 ms | 96.4% lower |
| Server CPU | 31,089 µs/request | 1,813 µs/request | 94.2% lower |
| Peak server RSS | 114.94 MiB | 49.06 MiB | 57.3% lower |

The valid per-repetition throughput ratios ranged from 23.91× to 26.48×.
This is a focused, single-workload Linux ARM64 result; it does not establish a
general or multi-system speedup and does not close the full benchmark gate. The
[raw artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39013025705/artifacts/12093617960)
retains all rows, validity reasons, hashes, and server logs.

## Latest multi-system benchmark attempt (2026-10-17)

The [multi-system run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490)
on commit `128aa2721aa78a289a93952539fa584d8412be14` did not produce a complete
three-system result. Linux x86-64 completed; macOS ARM64 and Linux ARM64 failed
the HTTP/3 `large-response` correctness gate when Hypercorn asyncio timed out
waiting for response headers (repetition 2 on macOS and repetition 5 on Linux
ARM64). A later focused Linux ARM64 run, above, passed all five Hypercorn and
all five Rust correctness/shutdown samples, so the timeout is intermittent and
still unexplained. Do not treat the focused pass as resolving the matrix
failure. The [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490/artifacts/12093376239),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490/artifacts/12093050892),
and [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39006451490/artifacts/12093037005)
retain each platform's raw results.

## Focused HTTP/2 close-diagnostic follow-up (2026-10-17)

The focused Linux x86-64 run
[39009246269](https://github.com/appunni-m/uvicorn-rs/actions/runs/39009246269),
commit `93669808`, stopped in repetition 2 after the client completed its
response checks with zero failures and its H2 drivers exited successfully. The
server exited cleanly without forced shutdown, with two exact `BrokenPipe`
connection diagnostics from distinct peer ports; the finalizer then allowed
only one. Repetition 1 completed 25,192 requests, but its timing was excluded
for unrelated runner CPU activity. The [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39009246269/artifacts/12092605687)
retains the raw rows and logs.

The earlier focused run
[39003779460](https://github.com/appunni-m/uvicorn-rs/actions/runs/39003779460)
used four client connections and logged one exact peer-close line in
repetitions 1 and 2, with no such lines in repetitions 3–5. Its five response
and shutdown checks passed; four timings passed the host guard. The pushed
change bounds this exact Rust H2 diagnostic to one per
configured client connection and continues to reject counts above the bound,
other server errors, response failures, driver failures, and unclean shutdown.

A local normal-wheel run of `protocol-scope` passed 5/5 response and shutdown
checks with zero peer-close lines. All five timing rows were excluded for
unrelated host CPU activity. A direct finalizer smoke check accepted 2/4 exact
diagnostics and rejected 5/4. These results validate the gate behavior; they
provide no performance evidence. Focused run
[39010673595](https://github.com/appunni-m/uvicorn-rs/actions/runs/39010673595)
later passed five Linux x86-64 `uvicorn-rs-asyncio` / `protocol-scope`
correctness and shutdown checks; four timings passed the host guard. It was a
target-only diagnostic, not a paired performance comparison. Exact-source CI
run [39011984443](https://github.com/appunni-m/uvicorn-rs/actions/runs/39011984443)
completed successfully on `e22df3a`. The later coverage run
[39020268579](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579)
passed its 749-case matrix and all reported source regions and lines. Current
exact-head CI [39024130047](https://github.com/appunni-m/uvicorn-rs/actions/runs/39024130047)
is in progress; its current state is summarized at the top of this document.

## Earlier full benchmark attempt (2026-10-17)

The [full matrix run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146)
measured commit
[`5dbd981332080e289ef416357606f49c8e2503b4`](https://github.com/appunni-m/uvicorn-rs/commit/5dbd981332080e289ef416357606f49c8e2503b4).
It did not complete across all three systems, so it does not qualify a
multi-system performance result.

| System | Outcome |
|---|---|
| Linux x86-64 | Stopped before timed categories: the installed wheel failed public parity at `http3.scope-preserves-duplicate-headers`. A later installed-wheel run on the current commit passed that case within 248/248 public cases, so no current mismatch is established; this matrix still has no qualified category result. |
| macOS ARM64 | Stopped in HTTP/2 `many-response-chunks` on `hypercorn-uvloop`; the H2 client connection driver did not shut down within its timeout. No complete multi-category result. |
| Linux ARM64 | All selected categories completed with qualified local pairs. In HTTP/2 `many-response-chunks`, uvicorn-rs throughput was 0.092× Hypercorn under asyncio and 0.084× under uvloop. Median throughput was about 6.97 vs 75.66 requests/s (asyncio) and 7.08 vs 84.28 requests/s (uvloop). This is a measured regression for that workload, not a cross-system conclusion. |

The same ARM64 run shows that HTTP/2 is not uniformly slower in Rust. On
`protocol-scope`, each server had five valid repetitions with zero failures;
uvicorn-rs reached 2.342× Hypercorn throughput under asyncio and 2.982× under
uvloop. Median rates were 5,894.7 vs 2,562.2 requests/s and 7,542.4 vs
2,533.0 requests/s. Rust p50/p95/p99 latency was 10.924/16.646/18.936 ms
under asyncio and 8.586/12.745/14.838 ms under uvloop; Hypercorn measured
24.211/35.689/36.679 ms and 24.469/36.517/37.470 ms. Rust server CPU per
request was 199/155 µs versus 390/394 µs; peak RSS was 48/50 MiB versus
95/97 MiB. These matched rows use the same ARM64 host and app. They coexist
with the chunk-streaming regression below and do not establish a category-wide
or multi-system win.

The ARM64 `many-response-chunks` rows also had substantially higher median p50
latency on uvicorn-rs (about 8.88 s under asyncio and 8.70 s under uvloop) than on
Hypercorn (about 0.85 s and 0.77 s). Server CPU per operation was about 27.8
ms and 19.8 ms for uvicorn-rs versus 13.2 ms and 11.85 ms for Hypercorn.
This gap is much larger in wall time than in server CPU: it points away from a
CPU-bound or byte-copy bottleneck as the first explanation and toward time spent
waiting for stream progress, backpressure, or scheduling. That is an inference
from aggregate CPU and latency, not a proven cause.

The same raw rows report a median of about 509 client `RecvStream.data()`
results per 1 MiB Rust response, versus about 70 for Hypercorn under asyncio
and 66 under uvloop. The counter records chunks returned by the H2 client API;
it is not a packet capture and does not establish wire-frame boundaries. It
does justify measuring whether response chunk granularity and transport
backpressure amplify per-send scheduling. The existing instrumented profile
collects ASGI send-await time, body-channel-full events and wait duration, and
final-body availability. A local preflight on 2026-10-17 rejected the host
because four unrelated Python processes each used roughly one core; no
instrumented profile was started.

The [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146/artifacts/12087490643),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146/artifacts/12089425539),
and [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38995794146/artifacts/12088867853)
retain the reports and logs.

A focused macOS ARM64 rerun
[completed](https://github.com/appunni-m/uvicorn-rs/actions/runs/39001707728)
the `hypercorn-uvloop` / `many-response-chunks` case with 5/5 response and
shutdown checks passing. All timing samples were rejected by the host CPU
guard, and the case has no matched Rust-server comparison. It is a correctness
diagnostic only. SHA-256 identities for `src/lib.rs`, the H2 category runner,
and the FastAPI benchmark app match the current checkout; later changes were
workflow selectors, release-evidence metadata, and documentation. This links
the diagnostic to current runtime source without presenting the run as an
exact-commit full matrix.

The [focused Linux x86-64 rerun](https://github.com/appunni-m/uvicorn-rs/actions/runs/39003779460)
on the current commit exercised only `uvicorn-rs-asyncio` / `protocol-scope`;
all five repetitions passed response and shutdown checks with zero unexpected
native errors or panics. Four timing rows passed the host guard; repetition 1
was excluded for unrelated host CPU activity. The four valid rows had median
throughput 5,175 requests/s, p50/p95/p99 latency 12.40/19.36/22.43 ms, server
CPU 244 µs/request, and peak RSS 48.6 MiB. The [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39003779460/artifacts/12090680106)
contains the raw rows. This target-only x86-64 diagnostic has no reference
server and must not be compared with the ARM64 rates above.

## Latest hosted benchmark attempt (2026-10-16)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975)
measured clean commit
[`c2de34a08a0b5083f830cc59c88182378a7d1a81`](https://github.com/appunni-m/uvicorn-rs/commit/c2de34a08a0b5083f830cc59c88182378a7d1a81).
Exact-binary public parity and the stock-FastAPI comparison completed on
Linux x86-64, Linux ARM64, and macOS ARM64. All three category jobs stopped
before the maintained matrix completed; no cross-system performance result is
qualified.

| System | First HTTP/2 failure | Other category failures |
|---|---|---|
| Linux x86-64 | `protocol-scope`, `uvicorn-rs-asyncio`, repetition 1. All client response checks and graceful shutdown passed; the server emitted `HTTP connection failed: connection error`. | H1: `fastapi-request-upload`, Rust/uvloop repetition 5 (concurrency 64), and `fastapi-upload-1m-write-1k`, Rust/asyncio repetition 5 (concurrency 8), each hit a libcurl timeout. H3 `fixed`, `hypercorn-uvloop`, repetition 2: 2,573 responses passed before one response-header timeout; Hypercorn's log was empty. Lifecycle analysis rejected the Rust TCP graceful-timeout diagnostic. |
| Linux ARM64 | `protocol-scope`, `uvicorn-rs-asyncio`, repetition 3, with the same generic connection diagnostic after successful responses and clean shutdown. | H1: `fastapi-upload-1m-write-1k`, Rust/uvloop repetition 4 and Rust/asyncio repetition 5 (both concurrency 8), each hit a libcurl timeout. Lifecycle analysis rejected the Rust TCP graceful-timeout diagnostic. |
| macOS ARM64 | `request-upload`, `uvicorn-rs-asyncio`, repetition 1, with the same generic connection diagnostic after successful responses and clean shutdown. | H1 completed all 300 rows without request failures. Lifecycle analysis rejected the Rust TCP graceful-timeout diagnostic. |

The H1 category processed all 300 planned rows on each system. Both Linux
systems had 298 correctness-eligible rows; macOS had 300. The four failed
Rust rows ran for about 15.4–18.0 seconds before libcurl reported
`Timeout was reached`. The affected Starlette handlers then observed
`ClientDisconnect`, and the Rust bridge logged a client disconnect before
response start. These errors invalidate the affected samples and fail the
Linux category jobs; their partial request rates are not performance data.
On macOS, 30 matched H1 workload/loop pairs qualified. Twenty-seven Rust /
Uvicorn throughput ratios were below 1.0; three were above 1.0. The median
ratio was 0.748× (range 0.452–1.042×). This is evidence against a broad H1
gain on that system, and does not provide the missing Linux measurements.

The retained platform artifacts are
[Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975/artifacts/12017648435),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975/artifacts/12018946775),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828500975/artifacts/12019086925).

### Focused hosted HTTP/2 diagnostic (latest rerun: 2026-10-17 local)

The [focused Linux x86-64 run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176)
ran only `protocol-scope` against `uvicorn-rs-asyncio` on `h2-debug` commit
`3d31e241cccfac939cb9403786f369d870f812da`. Attempt 7 completed all five
correctness and lifecycle repetitions with zero request failures, empty server
logs, and zero unexpected native errors or panic events. Repetitions 1, 3, 4,
and 5 passed the host timing guard; repetition 2 was excluded for unrelated
host CPU activity. Across the four valid samples, medians were 8,092
requests/s, 7.58/13.09/15.55 ms p50/p95/p99 latency, 155 microseconds of
server CPU per request, and 48.60 MiB peak server RSS. The retained
[attempt-7 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863229176/artifacts/12078313679)
has SHA-256
`8ccefead8c5144bd5ecf1859f0a663cdaaa7614ae51bc9bc7a2432450c71d58f`.

Two additional focused hosted runs tested Linux ARM64 and the macOS upload
case. Each completed all five correctness and lifecycle repetitions; all five
timing samples on both systems passed the host guard. There were zero request
failures, unexpected native errors, or generic connection diagnostics:

| System and workload | Workflow run and artifact | Timing-valid samples | Median throughput | Median p50/p95/p99 | Server CPU/request | Peak server RSS |
|---|---|---:|---:|---:|---:|---:|
| Linux ARM64, `protocol-scope` | [run 38863847199](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863847199), [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38863847199/artifacts/12030229138); commit `4057bc320bf054ece2b3a1b511f5adcc5a72e79a` | 5/5 | 5,855 req/s | 10.98/16.70/19.19 ms | 202 µs | 48.47 MiB |
| macOS ARM64, `request-upload` | [run 38864179333](https://github.com/appunni-m/uvicorn-rs/actions/runs/38864179333), [artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38864179333/artifacts/12030394350); commit `31cf827cb732cb19152df9f458accb4770fedb1d` | 5/5 | 370 req/s | 161.59/268.77/321.99 ms | 3,294 µs | 177.13 MiB |

These are target-only diagnostics with no matched Hypercorn reference. Their
timings do not establish a speedup or satisfy comparative performance
acceptance. Across the three focused hosted cases, the generic H2 connection
error did not recur; the original full-matrix failures remain unexplained.
The focused jobs do not cover other H2 workloads or runtime configurations.

The current local source replayed the macOS `request-upload` case once with
the same duration, warmup, concurrency, and server selection. Responses and
shutdown passed with an empty server log; unrelated CPU activity invalidated
the timing. This does not reproduce the hosted failure on Linux or prove a
performance gain. Three additional focused replays on the current local
source passed correctness and clean-shutdown checks:

| Case | Result | Timing |
|---|---|---|
| H3 `fixed`, `hypercorn-uvloop`, repetition 1 | 9,583 responses, zero client failures, empty server log, graceful shutdown | Invalid: unrelated CPU spiked above the host limit, including Codex Renderer activity. |
| H2 `protocol-scope`, `uvicorn-rs-asyncio`, repetition 1 | 38,117 responses, zero client failures, empty server log, graceful shutdown | Invalid: unrelated CPU exceeded the host limit, including `coverage-mcp` and `pillow-perfdb`. |
| H2 `protocol-scope`, `uvicorn-rs-asyncio`, repetitions 1–5 | All five repetitions had zero client failures, clean server exit, empty logs, and no unexpected native errors. | Invalid in all five repetitions: unrelated host CPU activity. |

The five-repetition H2 replay used 5-second duration, 1-second warmup, and
concurrency 64 on the local Apple M3 Pro. Source identity was stable at
`0b407a54c3baa9b0e33c3db3bad7b720ba686d6cbd4cb4c3daabf05093747918`; the
normal native extension identity was stable at
`2a5cbd4a2d4930430a51b65f9e6d8cbbabd894cf8c7dc43763d26ed44dfb0b3c`. The
timing rows are not performance evidence. The raw ignored report is
`target/benchmark-categories/h2-protocol-scope-singlecase-debug-current-20261016.json`.
This local M3 replay did not reproduce the generic HTTP/2 connection
diagnostic, so the hosted failure remains unresolved.

### Focused FastAPI upload failure replay (2026-10-17)

The current local source ran one matched repetition of
`fastapi-upload-1m-write-1k` on Uvicorn/asyncio and uvicorn-rs/asyncio, using
the stock FastAPI workload, 1 MiB requests sent in 1 KiB chunks, and
concurrency 8. Both servers completed all requests and graceful shutdown with
zero client failures. Throughput was 356.7 requests/s for Uvicorn and 351.5
for uvicorn-rs; p50 latency was 21.92 ms and 22.56 ms, respectively. Both
timing samples were rejected because unrelated host CPU activity ranged from
about 256% to 340% of one core. This single macOS replay does not reproduce
the hosted Linux timeout, and its measurements are not performance evidence.
It identifies no root cause and supports no code change by itself. The raw
ignored report is
`target/benchmark-categories/fastapi-upload-1m-write-1k-focused-uvicorn-vs-rs-asyncio-20261017.json`.

### Earlier generic HTTP/2 server diagnostic

The later H2 driver review found a separate benchmark-client race in the
previously locked `h2 0.4.19`: `SendRequest::poll` checked whether to close the
connection before snapshotting sender references. If the last sender was
dropped between that check and the snapshot, it could miss the self-wake and
leave the driver pending after responses completed. The probe now requires
`h2 0.4.20`, whose ordering snapshots references before the shutdown check and
wakes again when references disappear. The original hosted run remains
incomplete and is not retroactively repaired; reruns must use the fixed probe
and retain strict response, driver, and server-lifecycle gates. The H2 probe
uses the workspace lock, so Hyper's server-side transitive H2 dependency also
resolves to 0.4.20.

These local runs and the later focused hosted H2 diagnostics do not explain
the hosted H2 transport diagnostic or H3 timeout, and do not establish a
performance gain. Their Git-ignored
receipts are `target/benchmark-categories/h3-fixed-hypercorn-uvloop-retry2-20261016.json`,
`target/benchmark-categories/h2-protocol-scope-rust-asyncio-single-20261016.json`,
`target/benchmark-categories/h2-request-upload-rust-asyncio-exact-20261016.json`,
and `target/benchmark-categories/h2-protocol-scope-singlecase-debug-current-20261016.json`.

Latest clean hosted CI
[run 38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888)
on `27de9f3ac7d259a3a9b612c3247ab2c60eb27306` passed all 712 indexed cases,
Rust quality and MSRV checks, installed-wheel public parity, and pinned native
composition. Its older manifest measured 8,496/8,650 LLVM regions and
6,486/6,592 lines, leaving 154 regions and 106 lines uncovered; package and
Python-floor jobs were skipped. The preceding hosted run
[38828501018](https://github.com/appunni-m/uvicorn-rs/actions/runs/38828501018)
left 155 regions and 107 lines uncovered. A later local dirty-worktree
run executed and passed all 748 current cases (534 ASGI and 214 native), with
three clean full repeats of each matrix, and measured 100% executable
source-span and normalized physical-line coverage. Its aggregate remains
incomplete because one WebSocket TLS attribution attempt had a transient
infrastructure failure before a passing retry; a separate focused rerun then
passed cleanly. It does not replace a clean hosted release-candidate run.
The release candidate remains blocked by the failed category matrix,
`performance-acceptance.json` set to `not_proven`, and the need for clean
exact-source release evidence. See [release status](releases.md)
and the [current coverage record](coverage.md#current-unified-coverage-status-2026-10-17).

The latest local host-only preflight, recorded at
`target/benchmark-preflight/kata-finish-20261017-04.json`, sampled eight
0.25-second intervals on macOS 15.7.7 ARM64 (12 logical CPUs) and rejected
timing before launch. Unrelated aggregate CPU ranged from 300.3% to 316.8%;
three `python3.12` processes each reached 101.9–104.6% of one logical core.
The aggregate and repeated per-process guards rejected the host. No timing
benchmark started and no process was stopped. The receipt records process
names and PIDs only; command lines were not read. Recheck the host before
attempting a local matched pair.

## Previous completed hosted benchmark matrix: run #29 (2026-10-14)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330)
measured commit
[`1bde9cee0bb89618a30c3fc01b04af183f709c7b`](https://github.com/appunni-m/uvicorn-rs/commit/1bde9cee0bb89618a30c3fc01b04af183f709c7b).
Parity completed on all three systems. The category step failed on each
system because HTTP/2 stopped before all 140 planned rows were written.
HTTP/3 also stopped early on Linux x86-64 and Linux ARM64; the retained Linux
output includes a Hypercorn asyncio `protocol-scope` request that timed out
waiting for response headers. macOS completed all 130 HTTP/3 rows. WebSocket
completed 60/60 rows and lifecycle completed 20/20 rows on every system.

| System | FastAPI-only HTTP/1 | HTTP/1 categories | HTTP/2 | HTTP/3 | WebSocket | Lifecycle |
|---|---:|---:|---:|---:|---:|---:|
| Linux x86-64 | 40/40 rows; 39 timing-valid | 300/300; 300 timing-valid | incomplete; 140 planned | incomplete; 130 planned | 60/60 | 20/20 |
| Linux ARM64 | 40/40 rows; 39 timing-valid | 300/300; 300 timing-valid | incomplete; 140 planned | incomplete; 130 planned | 60/60 | 20/20 |
| macOS ARM64 | 40/40 rows; 5 timing-valid | 300/300; 232 timing-valid | incomplete; 140 planned | 130/130; 117 timing-valid | 60/60 | 20/20 |

The completed HTTP/1 rows had zero correctness failures. Timing validity does
not establish a speedup: the standalone FastAPI comparisons are
`not_proven`, and the broader category matrix is incomplete. The latest
complete multi-system FastAPI comparison remains run #27 below; its median
Rust/Uvicorn throughput ratios were below 1.0 on all three systems, so it did
not demonstrate a broad gain.

The workflow used Python 3.12.13, Rust 1.98.1, five repetitions, five seconds
per timed sample, one second of warmup, and concurrency 64 (HTTP/3 concurrency
1). The [Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330/artifacts/11884090964),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330/artifacts/11884251396),
and [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38537208330/artifacts/11885435428)
retain category JSONL checkpoints and logs. The HTTP/2 failure's specific
sample-level cause is not present in the job summary; the retained artifacts
are needed to diagnose it. This run does not satisfy performance acceptance.

## Focused local FastAPI HTTP/1 workload (2026-10-16)

A single `fastapi-fixed` workload was run on Apple M3 Pro / macOS 15.7.7 with
the same stock FastAPI app on Uvicorn and `uvicorn-rs-py`, under asyncio and
uvloop. The run used Python 3.12.13, Rust 1.98.1, concurrency 64, a one-second
warmup, five-second samples, and three repetitions per server. All 12 samples
passed response correctness and graceful shutdown, and source identity stayed
stable. The initial host preflight accepted, but unrelated CPU activity rose
during the run. The per-sample guard accepted only 4 of 12 timings: Uvicorn
asyncio 1/3, Rust asyncio 2/3, Uvicorn uvloop 0/3, and Rust uvloop 1/3. No
matched pair has the required three valid repetitions. A follow-up host
preflight rejected before another timing run because unrelated CPU exceeded
the aggregate and process limits. These rows do not establish a ratio or
performance result. The raw report and logs are local-only under
`target/benchmark-categories/2026-10-16/fastapi-fixed-single.json`.

## Previous hosted benchmark matrix: run #27 (2026-10-14)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006)
measured commit
[`ef9680c8e34fb2bf1c959b94d832f61cbf580213`](https://github.com/appunni-m/uvicorn-rs/commit/ef9680c8e34fb2bf1c959b94d832f61cbf580213).
Exact-binary parity and all correctness checks in the separate stock-FastAPI
comparison passed on all three systems. All platform category jobs stopped in
HTTP/2 after successful response checks because the server logged
`connection task failed: connection error`; each server shut down cleanly. The
underlying I/O error remains unknown. The category diagnostic gate remains
strict; a focused local follow-up is recorded below.

| System | HTTP/1 | HTTP/2 | HTTP/3 | WebSocket | Lifecycle | Qualified pairs |
|---|---|---|---|---|---|---:|
| Linux x86-64 | 300/300 rows; 30/30 pairs | 27/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| Linux ARM64 | 300/300 rows; 30/30 pairs | 2/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| macOS ARM64 | 300/300 rows; 24/30 pairs | 53/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 44 |

The HTTP/1 rows compare a stock Python FastAPI app under Uvicorn and
`uvicorn-rs-py`; they do not use FastAPI-RS or Starlette-RS. Each Linux system
qualified all 30 workload/event-loop pairs;
macOS qualified 24. The table reports medians of matched per-pair Rust/Uvicorn
ratios, so architectures are not combined.

| System | Qualified H1 pairs | Rust higher throughput | Throughput ratio, median | p95 latency ratio, median | Server CPU/operation ratio, median | Server RSS ratio, median |
|---|---:|---:|---:|---:|---:|---:|
| Linux x86-64 | 30/30 | 7/30 | 0.765 | 1.497 | 1.549 | 1.010 |
| Linux ARM64 | 30/30 | 5/30 | 0.793 | 1.460 | 1.575 | 1.013 |
| macOS ARM64 | 24/30 | 5/24 | 0.835 | 1.198 | 1.357 | 1.016 |

The current Python ASGI path has no broad speed advantage in this run: median
throughput is below Uvicorn on all three systems, and median server CPU per
operation is higher. The macOS timing exclusions and incomplete HTTP/2
categories also mean the matrix does not qualify the full required workload
inventory. These are measured outcomes, not release performance acceptance.

The workflow used Python 3.12.13 and Rust 1.98.1, five repetitions, five
seconds per timed sample, one second of warmup, concurrency 64 (HTTP/3
concurrency 1), and independent hosted Linux x86-64, Linux ARM64, and macOS
ARM64 runners. See [benchmark methodology](benchmarks.md) and the
[generated multi-system report](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11879148475).
The [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11878788763),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11879906195),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526995006/artifacts/11879698658)
artifacts retain the raw rows and server logs. The evidence aggregates to
`validated_partial_matrix`; it does not satisfy the performance gate.

## Focused HTTP/2 diagnostic probe (2026-10-14)

After changing the local server diagnostic to print Hyper's `Debug` error,
five normal-build repetitions of HTTP/2 `large-response` on
`uvicorn-rs-asyncio` passed all response checks and exited cleanly. All five
server logs were empty, so the hosted connection error did not recur and the
new diagnostic did not capture its underlying cause. The host guard rejected
all five timing samples for unrelated CPU activity; this is not performance
evidence. The probe used working-tree source SHA-256
`a74b6c7d799d1fa5080f0a7064fb8c23b4671b89449dc83e16f3449d4a907dd9` and is
retained only under Git-ignored `target/h2-debug-format-20261014.jsonl` and
`target/h2-debug-format-20261014.artifacts/`. It does not resolve the hosted
failure or replace the complete benchmark matrix.

## Previous hosted benchmark matrix: run #26 (2026-10-14)

The [run](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313)
passed public parity and the separate stock-FastAPI HTTP/1 comparison on all
three systems. The category jobs and overall matrix are incomplete, so this
run does not establish a three-system performance result or a speedup.

| System | HTTP/1 | HTTP/2 | HTTP/3 | WebSocket | Lifecycle | Qualified pairs |
|---|---|---|---|---|---|---:|
| Linux x86-64 | 300/300 rows; 30/30 pairs | 47/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| Linux ARM64 | 300/300 rows; 30/30 pairs | 48/140 rows; incomplete | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 50 |
| macOS ARM64 | 124/300 rows; incomplete | 140/140 rows; 12/14 pairs | 130/130 rows; 12/14 pairs | 60/60 rows; 6/6 pairs | 20/20 rows; 2/2 pairs | 32 |

The macOS HTTP/1 category recorded four correctness failures in the 1 MiB
upload workload using 1 KiB client writes at concurrency 64. All four server
profiles failed during warm-up with client send errors; FastAPI observed
`ClientDisconnect`. Linux HTTP/2 stopped in the Rust/asyncio `large-response`
workload after successful client response checks, followed by the generic
`uvicorn-rs: connection task failed: connection error` diagnostic. The
failures occurred at repetition 2 on x86-64 and repetition 3 on ARM64; server
shutdown was clean. Their shared cause is not established.

The separate FastAPI-only comparison produced all 40 planned rows without
correctness failures on each system. It qualified 4/4 workload/loop pairs on
each Linux system and 0/4 on macOS because of timing exclusions. This comparison
uses stock FastAPI and Starlette under Uvicorn and uvicorn-rs; it does not use
FastAPI-RS or Starlette-RS.

The [matrix artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11873134174)
and [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11874197074),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11873189132),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38515000313/artifacts/11874001693)
artifacts retain source-bound receipts, raw rows, reports, and logs for 90
days. The artifacts aggregate to `validated_partial_matrix`: 50 qualified
pairs on each Linux system and 32 on macOS. Partial pairs are descriptive
evidence only and do not satisfy performance acceptance.

Focused local follow-ups validated the two failing inputs after harness
changes. The HTTP/1 upload passed once on all four server/loop profiles at
concurrency 8 with response and lifecycle gates passing. The HTTP/2
large-response probe completed 4,071 requests with no client failures and a
clean server exit after the client sent GOAWAY and drained pending frames.
Both runs rejected timing because unrelated local CPU activity exceeded the
guard. These probes do not confirm the fixes on hosted runners or provide
performance evidence. The next complete hosted matrix must validate the
workload changes.

The status/docs job also failed: it tried to stage per-run files under the
Git-ignored `benchmarks/results/` directory. The workflow now keeps generated
reports and logs in 90-day Actions artifacts and proposes documentation-only
changes on its automation branch. Repository Actions permissions cannot
create pull requests, so the workflow provides a compare link for manual
review.

## Local host preflight (2026-10-14)

The latest eight-sample macOS ARM64 preflight rejected benchmark timing before
launch. Unrelated CPU use ranged from 114.9% to 228.1% of one logical core;
`python3.12` remained near one core across the samples, and `rustfmt` briefly
used 97.1%. The decision followed the existing aggregate and sustained-process
guard. No timed benchmark started and no process was stopped. The receipt is
Git-ignored at
`target/benchmark-preflight/kata-finish-20261014-retry1.json` and records HEAD
`796dee690ca83654cddb97131dc1dee37de96bcd`. The FastAPI benchmark remains
unqualified; retry after a clean preflight.

## Previous hosted benchmark matrix: run #25 (2026-10-13)

The matrix
[38418430949](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949)
passed exact-normal-binary public parity on all three systems. All three
platform category jobs are now terminal failures. The multi-system evidence
validation job passed as an aggregation check, but the required categories did
not complete and there is no validated three-system performance result.

The preliminary FastAPI-only HTTP/1 comparison produced 40 planned rows on
each system with no correctness failures. It had 2 timing-valid rows on macOS
and 39 on each Linux system; all three reports say `not_proven`. The full
stock-FastAPI HTTP/1 category completed 300/300 correct, timing-valid rows on
each Linux system. macOS stopped at 124 rows: rows 121–124 failed during the
1 MiB upload workloads, and 75 rows were timing-valid. Its trace ends in
Starlette `ClientDisconnect` while reading the upload body.

The complete Linux HTTP/1 reports qualified all 30 FastAPI workload/event-loop
pairs on each system, with five matched repetitions per pair. The ratios below
are medians of the 30 per-pair Rust/Uvicorn ratios; they summarize the recorded
workloads and do not combine samples from different machines.

| System | Qualified pairs | Rust faster | Throughput ratio, median (range) | p95 latency ratio, median | Server CPU per operation ratio, median | Server RSS ratio, median |
|---|---:|---:|---:|---:|---:|---:|
| Linux x86-64 | 30/30 | 6/30 | 0.713 (0.450–1.402) | 1.565 | 1.764 | 1.008 |
| Linux ARM64 | 30/30 | 6/30 | 0.844 (0.436–1.463) | 1.369 | 1.563 | 1.014 |

These measurements show no broad speed advantage for the current Python ASGI
server path: throughput was lower in 24 of 30 pairs on each Linux machine, and
median server CPU per operation was higher. They do not identify which layer
caused the overhead. The reports compare FastAPI under Uvicorn with FastAPI
under the current `uvicorn-rs-py` implementation; they do not measure the
separate Python-free Rust application composition path. This evidence fails the
project's performance objective and must not be presented as a release gain.

HTTP/2 stopped on all three systems when the server diagnostic gate rejected
`uvicorn-rs: connection task failed: connection error`; shutdown itself was
clean. HTTP/3 also stopped on all three: the Linux Hypercorn reference failed
large-response body-length checks (192,037 or 251,633 bytes received versus
1,048,576 expected), while macOS Hypercorn/uvloop timed out waiting for
protocol-scope response headers. The logs do not establish whether these H3
failures share one cause. WebSocket completed 60/60 correct, timing-valid rows
on every system. Lifecycle completed 20/20 on both Linux systems and 19/20 on
macOS. Those passing categories do not make the whole matrix complete.

The aggregate validator marked the result `validated_partial_matrix`. Its
artifact reports 38 individually qualified workload/reference pairs on each
Linux system and 8 on macOS; the separate FastAPI-only comparison qualified 4
pairs on each Linux system and none on macOS. These counts are partial
descriptive evidence, not a substitute for complete categories or a
cross-system performance claim. The [aggregate evidence artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949/artifacts/11829521030)
contains the generated comparison report and source manifests.

The benchmark docs job failed because GitHub Actions could not create a PR;
commit documentation updates through the normal repository workflow. The
category logs and partial reports are retained in the
[run #25 artifacts](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430949).

Run #24
([38354960306](https://github.com/appunni-m/uvicorn-rs/actions/runs/38354960306))
produced no parity or timing rows because the protocol clients were looked up
under `tools/http3-probe/target/release/` instead of repository
`target/release/`. The parity and category scripts now use the workspace output
directory, and run #25 has passed hosted parity with those paths. The #24
benchmark documentation job could not create a PR under the repository's
Actions permissions; documentation updates must be reviewed and committed
through the normal repository workflow.

## Latest local benchmark preparation (2026-10-13)

The exact normal build passed **243/243** parity cases at commit
`957143ab5f810be861183bde0c239d558f78fefb`. The measured source
(`src/lib.rs` SHA-256
`ea149b5821a398f62c5a7762a83774040ae15ae0b268c28d921e4c61f3e54f47`),
normal extension (`8e7a060c5bdd9e1bd5d1c4d5bbcd5136de739208f7eccdbbd80963f235dcc64f`),
benchmark scripts, and lockfiles are unchanged in the current checkout. Since
parity commit `957143ab5f810be861183bde0c239d558f78fefb`, the Python adapter
source, extension, dependencies, benchmark scripts, and parity cases are
unchanged; later commits affect the independent native crate, native contract
example, manifest, docs, and ignore rules. The 243/243 parity receipt therefore
still matches the benchmark input without another parity run.

The post-parity host preflight rejected three windows before timing began.
Unrelated CPU measured 128.7–245.2%, 238.9–268.8%, and 214.7–243.3% across
the three receipts. No timed rows were produced and no processes were stopped.
The receipts are in the local-only
`benchmarks/results/2026-10-13/kata-finish-20261013-1/` directory and are
excluded from Git.

A new eight-sample preflight on clean `main` commit
`a851386cc252fed04c95e3c4fbddc342c630351c` also rejected before timing.
Unrelated aggregate CPU ranged from 35.4% to 156.2%; a Google Chrome Helper
renderer exceeded 25% for four consecutive intervals and peaked at 104.8%,
while a Codex renderer reached 25.5%. The receipt records
`timing_benchmark_started: false`; no process was stopped. Its JSON is
local-only at
`target/benchmark-preflight/wh9k-a851386cc-preflight-1.json` and is excluded
from Git.

The next benchmark work is limited to the underqualified matched pairs once a
host window passes preflight. The full parity suite does not need to be
repeated unless its code or input identity changes. This preparation
establishes no repeatable performance gain.

### Latest FastAPI HTTP/1 measurement attempt (2026-10-13)

After the host preflight accepted on `cc485f3b4`, one normal-build run measured
the 15 selected stock-FastAPI HTTP/1 workloads against Uvicorn `httptools` on
asyncio and uvloop. Each server/workload used three repetitions, five seconds
per sample, one second warmup, and concurrency 64. All **180/180** rows passed
response checks and server lifecycle checks; there were no request failures,
unexpected native errors, or panic events. The per-row CPU guard rejected
**151/180** timing rows for unrelated host CPU activity. The analyzer found
**zero qualified workload/loop pairs** with three matching valid repetitions,
so it emitted no ratios or performance medians. This run provides no evidence
of a speedup or regression. Raw rows, logs, and analysis remain local under
`target/benchmark-categories/wh9k-cc485f3b4/` and are excluded from Git. No
full parity or coverage suite was repeated.

## Previous hosted ASGI matrix: run 38122909359

The hosted matrix ran on clean commit
[`9b2d8aaf`](https://github.com/appunni-m/uvicorn-rs/commit/9b2d8aaf321666eb365b1fa69d39029233d0ece0).
The aggregate job validated a **partial** matrix; each platform job stopped in
the sequential category step, so this run does not establish a complete
three-system performance result. Its FastAPI validated-route throughput was
below Uvicorn on all three systems: 0.676×/0.700× on Linux x86-64,
0.769×/0.936× on Linux ARM64, and 0.671×/0.683× on macOS ARM64 (asyncio /
uvloop). The [matrix report and digest manifest](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696763811)
and the [Linux x86-64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11697233690),
[Linux ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696963085),
and [macOS ARM64](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696818454)
artifacts retain the raw category logs outside Git. They expire on 2027-01-09;
no benchmark logs or raw reports are committed.

The incomplete categories stopped at different boundaries:

| System | Category and failing input | Observed failure |
|---|---|---|
| Linux x86-64 | HTTP/2 `protocol-scope`, Rust/uvloop, repetition 5 | The response check passed, then the server logged only `connection task failed: connection error`. Shutdown exited cleanly; the underlying error is not identified. |
| Linux ARM64 | HTTP/2 `many-response-chunks`, Rust/asyncio, repetition 4 | The response check passed, then the same generic Rust connection error was logged. Shutdown exited cleanly; the underlying error is not identified. |
| Linux ARM64 | HTTP/3 `fixed`, Hypercorn/uvloop, repetition 2 | The client timed out waiting for response headers. Hypercorn logged an unhandled `KeyError(0)` while looking up an H3 stream; the cause of the missing response is not established. |
| macOS ARM64 | HTTP/1 FastAPI upload, 1 MiB body in 1 KiB writes, Rust/uvloop, repetition 1 | libcurl reported 31 send failures across 110 requests. FastAPI observed `ClientDisconnect`, followed by the server's disconnect-before-response-start error. The trigger remains unconfirmed. |

These observations do not establish one shared failure cause or a complete
performance ranking. Only individually qualified matched pairs are reported.

The docs updater pushed commit [`94f68885`](https://github.com/appunni-m/uvicorn-rs/commit/94f68885d3455383a806c606b53781fe7be7b7a2)
to `automation/benchmark-results`, then failed in the final “Propose the
updated results documentation” step (job
[`114433266672`](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/job/114433266672#step:5:76)).
The GitHub Actions job log confirms that the branch push succeeded, but
`gh pr create` was rejected with `GitHub Actions is not permitted to create or
approve pull requests (createPullRequest)`. The workflow requested
`pull-requests: write`; the effective Actions policy still blocked PR creation.
The docs update is on the pushed branch, but no PR was opened. This permission
failure is separate from the aggregate benchmark result.

The separately attached `asgi-category-benchmarks-macos-arm64 (1).zip` has
SHA-256 `92e2cd68d8afb38a367b6e789fc5143e6ff054b7cf7b3ab3298466692ee7091a`,
identical to the [macOS artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696818454)
above. It adds no new benchmark
samples. Its HTTP/1 category stopped after 120/300 rows when a 1 KiB upload
case failed in the libcurl client; FastAPI then observed a client disconnect.
The analyzer withholds all H1 ratios because the category is incomplete. The
other categories produced 14 HTTP/2, 12 HTTP/3, 6 WebSocket, and 2 lifecycle
matched descriptive pairs. The H1 experiment and its interpretation limits
are recorded in [the local retries section](#h1-benchmark-source-retries-interrupted-by-host-load-2026-10-12)
below.

The later attached `asgi-category-benchmarks-macos-arm64.zip` has SHA-256
`e556828c831dbec775a3da4a58445d96e60453f0874711b028717566b38593a3`. It
contains 11 preparation files, including the detailed parity report, but no
timed category results. That report records the exact old first-receive
mismatch: Uvicorn returned `http.disconnect`, while uvicorn-rs returned
`http.request` followed by `http.disconnect`; both follow-up responses were
200 and both connections remained usable. The report ran clean revision
`72dfa51` and had 239/240 parity cases pass.

The old fixture waited a fixed 50 ms after its app checkpoint. The driver
closed the client after observing that checkpoint, then waited 250 ms before
releasing the app; the fixture did not wait for that release. So the first
the fixed delay did not order the first `receive()` after the driver's
post-close settle interval. The fixture now waits for the release marker. The corrected case
passed one focused run plus 10 repeats locally with matching oracle and target
observations. This identifies a test synchronization flaw but does not prove
the old runtime correct or incorrect for an immediate post-disconnect receive,
and it is not a hosted rerun. See the archived-row review and repeat
evidence (`benchmarks/results/2026-10-12/http1-disconnect-before-first-receive-repro/README.md`).

The Tokio blocking-pool experiment passed 243/243 public parity cases with the
default, 1-thread, and 4-thread settings. Its first timing slice has one
qualified descriptive pair: default pool, stock FastAPI, 1 MiB request body,
64 KiB client callback cap, three host-valid repetitions per server. Uvicorn
handled 4,149 requests/s and Rust 3,840 (0.925×); Rust p50/p95/p99 and observed
server CPU were higher. The setting comparison is incomplete: cap 1 had no
qualified pairs, and cap 4 has not been timed. See the full experiment
report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/README.md`).

Twelve earlier consecutive host preflights (receipts 5–16) rejected before
benchmark startup. The latest of those samples found
`mediaanalysisd` at 66.2–100.9% of one core, `qemu-system-aarch64-headless`
reached 28.7% in one interval, and aggregate unrelated CPU ranged from 94.8%
to 140.1%, with consecutive samples over the aggregate threshold. No process
was stopped. Subsequent short windows accepted for the default and cap-1 runs,
but the per-row guard still rejected noisy rows. Ten later cap-4 preflights
rejected; the first (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-4-host-preflight.json`)
and latest (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-4-host-preflight-retry-9.json`)
receipts show the aggregate and sustained-process guards. Three subsequent
focused cap-1 preflights rejected under the same guards; see the latest
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-1-focused-preflight-retry-2.json`).
Eighteen resumed preflights also rejected before timing: `mediaanalysisd` used
29.3–101.5% of one core, `qemu-system-aarch64-headless` reached 78.7%, and
aggregate unrelated CPU ranged from 56.2% to 279.6%. The latest sample found
`mediaanalysisd` at 29.3–96.1% and aggregate unrelated CPU at 56.2–115.2%.
No process was stopped.
See the first (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-1.json`)
and latest (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-18.json`)
receipts.
See the current experiment
status (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/current-run-status.md`).
The latest goal-continuation preflight also rejected before timing: unrelated
aggregate CPU ranged from 115.1% to 178.8%, a `python3.12` process used
94.6–100.6% of one core throughout all eight intervals, and
`qemu-system-aarch64-headless` reached 79.6% in one interval. The receipt
records process names and PIDs only; no benchmark started and no process was
stopped. See the latest receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-goal-continuation-20261012.json`).
The intended comparison isolates stock FastAPI 1 MiB uploads with 64 KiB and
256 KiB client writes against Uvicorn on the same asyncio loop. No performance
claim about pool-cap effects follows from this partial timing evidence.

A fresh standalone host preflight after the profile review rejected as well:
the process named `python3.12` used 85.3–104.3% of one core in all eight
intervals, and unrelated aggregate CPU ranged from 100.4% to 151.4%. The
receipt captures names and PIDs, not the process command. No timed benchmark
started in that rejected window and no process was stopped. Later short windows
accepted for default and cap 1, but the cap comparison remains incomplete. See
the preflight receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-post-doc-audit.json`).

### HTTP/2 benchmark-client shutdown check (2026-10-12)

The two hosted HTTP/2 failures had successful client response checks, clean
server-process exits, and one generic Rust connection-error line. The H2 load
client previously discarded its connection-driver result and returned without
explicitly draining the driver. It now drops all request senders, waits for
each driver to finish its GOAWAY/TLS shutdown, and fails the client correctness
gate if a driver reports an error or does not stop within five seconds.

The local check passed six of six rows across three repetitions each of
`protocol-scope` and `many-response-chunks`: response checks passed, server
lifecycle gates passed, and no unexpected native diagnostics were recorded.
Only two rows passed the host timing guard, below the three-repetition
threshold; this is a teardown correctness check, not a performance result. The
raw report and server logs (`benchmarks/results/2026-10-12/http2-client-shutdown-20261012/README.md`)
record the command, source identity, host, and exclusions. A hosted rerun is
still needed to confirm whether this client lifecycle defect explains the
previous intermittent server diagnostic.

## Local FastAPI results

### Recorded FastAPI-only subset (macOS ARM64, 2026-10-11)

The archived run used stock FastAPI, Starlette, and Pydantic on CPython 3.12.13,
with concurrency 64 and five planned repetitions. Its selected HTTP/1 subset
completed 40/40 response-checked rows; one row was excluded by the host timing
guard. These measurements are from clean commit `9b2d8aa`, not the current
worktree. Uvicorn's `httptools` implementation is the reference for both loop
pairs.

| FastAPI workload / loop | Rust/Uvicorn throughput | p50, Uvicorn → Rust | p95, Uvicorn → Rust | Server CPU µs/request, Uvicorn → Rust |
| --- | ---: | ---: | ---: | ---: |
| Validated route / asyncio | 0.671× | 7.109 → 11.481 ms | 14.612 → 22.294 ms | 121.2 → 202.0 |
| Validated route / uvloop | 0.683× | 6.213 → 9.793 ms | 12.460 → 19.037 ms | 107.1 → 173.8 |
| Python CPU handler / asyncio | 0.991× | 117.5 → 124.5 ms | 161.2 → 183.8 ms | 1,958.8 → 2,062.9 |
| Python CPU handler / uvloop | 0.938× | 108.0 → 118.3 ms | 146.8 → 183.1 ms | 1,731.7 → 1,881.5 |

The lightweight validated route exposes materially higher Rust request-path
cost in this Python integration. When the Python handler spends much longer
computing, throughput is close to Uvicorn's and the same extra fixed cost is a
smaller share of total time. This localizes the gap to work around the
application path, but does not attribute it to a specific parser, Tokio stage,
or Python bridge function. The containing five-category matrix remains
incomplete because HTTP/1 stopped during a separate upload workload; its other
protocol results cannot turn these rows into an overall speed claim. The
[hosted matrix artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/artifacts/11696763811)
records the raw per-system rows and digest manifest; its partial status is
summarized above.

### H1 benchmark-source retries interrupted by host load (2026-10-12)

The attached macOS ZIP was an exact duplicate of the previously analyzed
artifact. Two fresh local attempts used the captured dirty source snapshot and normal
native extension, which passed **243/243 public parity cases** before timing.
Both initial host preflights accepted, but unrelated CPU activity returned
during the 300-row HTTP/1 runs. The first stopped after 41 rows (zero response
failures, 24 timing-valid, 17 host-rejected); the retry stopped after 22 (zero
response failures, 9 timing-valid, 13 host-rejected). Both strict analyses
withheld ratios because category completion and identity gates were incomplete,
and both post-stop preflights rejected. Do not combine the partial attempts or
draw a performance conclusion. See the attempt ledger and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/README.md`).

### H1 benchmark-source route and fixed-response batch (2026-10-12)

A separate complete 40-row selected-subset run passed all response checks; 30
rows passed the timing guard and three workload/loop pairs qualified. The
validated FastAPI route measured 0.900× Uvicorn throughput under asyncio and
0.966× under uvloop. The fixed response measured 0.750× under asyncio; its
uvloop pair had only two valid repetitions. The qualified pairs used 9.0–20.1
µs more aggregate server-process CPU per operation. This does not isolate the
CPU between the Python event loop, PyO3 bridge, and Rust networking. The
source-bound report and raw rows (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-route-fixed/README.md`)
record the exact identity and limits. These results cover two of 15 H1
workloads and do not establish an overall speedup.

### H1 benchmark-source response workloads (2026-10-12)

A separate 60-row batch covered large responses, many response chunks, and
small response chunks. All correctness rows passed; 50 timing rows passed the
host guard and five workload/loop pairs qualified. Throughput versus Uvicorn
was 0.871× and 0.931× for large responses, 0.956× for many chunks under
asyncio and 1.275× under uvloop, and 0.920× for small chunks under asyncio.
Small chunks under uvloop had only two valid repetitions. Rust used more
aggregate server-process CPU in all five qualified pairs; the measurements do
not attribute that CPU to a particular Python or Rust function. The report
and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-response-workloads/README.md`)
record the source identity, latency, CPU, RSS, exclusions, and limits. Across
the two completed H1 subsets, results show regressions on several workloads
and one uvloop streaming win; they do not show a broad speedup.

### H1 benchmark-source request-upload workloads (2026-10-12)

A 120-row batch exercised six upstream FastAPI upload cases: 1 MiB request
bodies with 64 KiB, 1 KiB, 16 KiB, 256 KiB, and 1 MiB client writes, plus a
64 KiB body sent in 1 KiB writes. All correctness rows passed; 60 passed the
host timing guard, and five workload/loop pairs qualified. Throughput versus
Uvicorn was 0.648× / 0.686× for the standard 64 KiB writes, 1.001× / 0.995×
for 1 KiB writes, and 0.649× for 256 KiB writes under asyncio. Rust used more
aggregate server-process CPU in all five qualified pairs. The remaining cases
did not have enough matching valid repetitions. The report and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-workloads/README.md`)
record the exact identities and limitations. The workload-dependent results
point to request-upload handling for deeper profiling; they do not identify a
specific hot function or establish an overall speedup.

The 1 KiB-write near-parity rows are client-limited: the load generator used
about 10.4–10.8 CPU cores at the observed rate on this 12-core machine. In the
better-loaded 64 KiB-write cases, Rust's 8.8–10.3 ms p50 gap exceeds the
0.27–0.33 ms server CPU increase by a wide margin. The current evidence points
toward receive delivery or waiting latency, but does not identify the precise
stage. The client setting is a cap on libcurl read-callback returns, not a
guarantee of socket-write or packet boundaries.

The post-run host preflight rejected another timed batch before it started:
unrelated aggregate CPU peaked at 134.4% of one core, and `mediaanalysisd`
used 72.4–105.2% across all eight intervals. A later preflight still rejected
with that process above 25% in every interval. No result-grade timing was
started during the rejected windows. A separate diagnostic-only upload profile
ran under host load; every timing row was rejected, while thread snapshots and
sampled stacks identified a possible PyO3 `spawn_blocking`/GIL completion cost.
That observation motivates a controlled pool-limit A/B, but does not quantify
the cause. See the profile report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-profile/README.md`),
preflight receipts (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-h1-rest.json`),
and retry (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-profile-next-2.json`).
The latest host check also rejected before timing: `mediaanalysisd` remained at
63.2–87.9% of one core in all eight intervals, with unrelated aggregate CPU
peaking at 115.9%. A retry 30 seconds later also rejected, with aggregate
unrelated CPU peaking at 290.0% and `mediaanalysisd` remaining at 65.5–87.2% in
all intervals. See the first receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-20261012.json`)
and retry (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry1-20261012.json`).
A second retry rejected too: `mediaanalysisd` remained at 56.6–85.9% in all
intervals, and aggregate unrelated CPU peaked at 136.4%. See the second retry
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry2-20261012.json`).
A third retry rejected as well: unrelated aggregate CPU peaked at 214.2%,
`mediaanalysisd` used 55.1–87.8%, and a `python3.12` process used 86.0–100.5%
in all intervals. No benchmark started and no process was stopped. See the
third receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry3-20261012.json`).
A fourth retry rejected 45 seconds later: `mediaanalysisd` remained at
51.6–98.4%, `rustc` at 94.0–103.5%, and aggregate unrelated CPU peaked at
220.1%. No benchmark started. See the fourth receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry4-20261012.json`).
A fifth preflight 60 seconds later rejected as well: `mediaanalysisd` used
70.8–75.5%, `rustc` used 94.3–101.5% in all intervals, and aggregate CPU
peaked at 211.9%. See the fifth receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry5-20261012.json`).
A fresh preflight on continuation also rejected, with aggregate CPU peaking at
200.3%, `mediaanalysisd` at 50.6–80.4% in all intervals, and a `python3.12`
process at 95.8–97.1% in three intervals. No timing began. See the
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-1.json`).
A second continuation preflight rejected too: aggregate CPU peaked at 227.1%,
`mediaanalysisd` used 46.8–73.5% in all intervals, `git` used 27.5–32.0% in
seven, and `rustc` briefly used 101.1%. See the receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-2.json`).

### Recorded dirty-source five-category run (2026-10-11)

The normal extension passed **243/243 public parity cases** before timing.
The frozen run used upstream FastAPI 0.142.4, Starlette 1.7.0, Pydantic 2.13.5,
Uvicorn 0.54.0, Hypercorn 0.18.0, CPython 3.12.13, macOS 15.7.7 ARM64, and
one Tokio worker. No FastAPI-RS or Starlette-RS app or route was used. The
working tree was dirty at revision `3dcaeaa0caf47aca96412d15451ac6a1123ebb04`;
`src/lib.rs` SHA-256 was
`5ecbf23cbd9cb430be9af6c9f69399bc4c835eb4441c8f8794f4e3c881beca7d`, and the
normal native extension SHA-256 was
`5c23a4e33006b6183f3a0bba89b2506c3866be2d293b9cd49ebffb037c47b028`.

The five-category analysis (`benchmarks/results/2026-10-11/fastapi-current-full-category-20261011-retry1/analysis.md`)
and its raw rows keep each category and each host-rejected sample separate.
HTTP/1 completed all 300 planned rows with zero response failures, but only 20
passed the timing guard and **no H1 workload/loop pair qualified**. HTTP/2
stopped after 68/140 rows when uvicorn-rs could not bind its HTTP/3 endpoint
(`Address already in use`); all 68 collected rows had zero response failures.
HTTP/3 completed 130/130 rows (112 timing-valid, 10 qualified pairs), WebSocket
completed 60/60 (57 timing-valid, 6 pairs), and lifecycle completed 20/20 (14
timing-valid, 1 pair).

An isolated HTTP/2 retry (`benchmarks/results/2026-10-11/fastapi-current-full-category-20261011-http2-retry1/analysis.md`)
completed all 140 planned rows with zero response failures; 26 rows passed the
timing guard and two workload/loop pairs qualified. Its only qualifying
workload was protocol-scope, at 3.566× throughput under asyncio and 3.995×
under uvloop versus Hypercorn. This retry is a separate attempt and is not
pooled with the incomplete HTTP/2 category from the five-category run.

| Category and workload | Reference | Asyncio Rust/reference | Uvloop Rust/reference |
| --- | --- | ---: | ---: |
| HTTP/2 protocol-scope | Hypercorn | 3.566× | 3.995× |
| HTTP/3 large response | Hypercorn | 9.514× | 19.904× |
| HTTP/3 many response chunks | Hypercorn | 17.051× | 18.040× |
| HTTP/3 slow-reader backpressure | Hypercorn | 0.997× | 0.996× |
| WebSocket connection handshake | Uvicorn | 2.181× | 1.804× |
| WebSocket text echo | Uvicorn | 0.593× | 0.716× |
| WebSocket binary 64 KiB echo | Uvicorn | 1.029× | 1.060× |

These are workload-specific same-host results. They show large gains on some
HTTP/2 and HTTP/3 transfer cases, slower text WebSocket echo, near parity on
WebSocket binary echo and H3 slow-reader load, and no clean H1 result for the
that benchmark source. The full matrix is marked `incomplete_categories`; it does not
establish an overall server speedup. A passing host preflight did not guarantee
clean timing windows: the per-sample guard rejected 280/300 H1 rows and
114/140 rows in the isolated H2 retry because of unrelated host CPU activity.
Three matching repetitions are a descriptive evidence threshold, not a
statistical-significance claim.

Two fresh preflights before a focused H1 retry rejected the host before
starting timed work. `mediaanalysisd` used 73.1–98.2% and 68.7–94.8% of one
core; unrelated aggregate CPU reached 118.2% and 107.4%. Both receipts confirm
that no benchmark started: first (`benchmarks/results/2026-10-11/fastapi-current-h1-focused-retry-20261011/host-preflight.json`)
and second (`benchmarks/results/2026-10-11/fastapi-current-h1-focused-retry-20261011-2/host-preflight.json`).

The 2026-10-10 exact-source FastAPI category matrix (`benchmarks/results/2026-10-10/fastapi-current-matched-matrix-20261010/README.md`)
uses stock FastAPI on CPython 3.12.13, one Tokio async worker, and source
`1f222c0…` with normal extension `bf3cb99…`. It has 390/390 complete-matrix
correctness rows, 420 focused retry rows, and 192 deeper H1 rows. H1 fixed
requests regress against Uvicorn as concurrency rises; H1 upload diagnostics
locate latency in `receive()` delivery and the Rust/Python future bridge.
HTTP/1 streaming has near-parity rate with higher Rust CPU, while WebSocket
handshake and qualifying HTTP/2/3 workloads favor Rust. The per-workload table
and source-snapshot interpretation are in the report; there is no single
cross-protocol speed ratio.

### HTTP/3 request semantics

The H3 benchmark client now follows [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html)
for request content: ordinary GETs carry no content and omit `Content-Length`;
the route that consumes a body uses POST with one byte, and upload uses POST
with its configured body. HTTP specifications are the source of truth when a
wire-level compatibility observation conflicts with them.
The corrected-input smoke run (`benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/analysis.md`)
passed 24/24 response checks. Its 0.2-second duration is exploratory; although
the analyzer formed one matched H3 uvloop pair, the fresh host preflight had
rejected and the run is not a performance result. Older rows that sent a
one-byte GET body are a different input identity. See the [HTTP/3 request-shape
details](benchmark-results.md#http3-request-shape-correction-2026-10-11).
Thirteen subsequent preflights rejected timed work for aggregate unrelated CPU
above 100% of one core and a process above the per-process threshold in
consecutive intervals. The latest receipt (`benchmarks/results/2026-10-11/wh9k-after-native-core-20261011-1.json`)
records no benchmark start. In preflight 13, unrelated CPU ranged from
49.4–122.2% of one core and `mediaanalysisd` used 28.1–102.7% across eight
intervals. Preflight 12 recorded 119.0–172.3% aggregate activity, with a Codex
renderer peaking at 39.0% and a Chrome helper at 63.0%. Earlier rejected
receipts remain available beside the benchmark results.

Follow-up diagnostics now cover all 15 HTTP/1 workload variants with thread
CPU counters and add 320 response-checked stage rows for HTTP/2, HTTP/3, and
WebSockets. See the per-thread report (`benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md`)
and protocol-stage report (`benchmarks/results/2026-10-10/fastapi-current-protocol-stages-20261010/README.md`).
The stage timings are diagnostic-only; the ordinary matched matrix remains
the throughput, latency, process CPU, and RSS evidence.

A 32-byte WebSocket text-echo attempt on the recorded benchmark source passed 20/20 payload
checks, but all 20 timing rows failed the host-activity guard. Its
receipt (`benchmarks/results/2026-10-10/fastapi-current-ws-text-echo-20261010/README.md`)
records the attempt without making a small-frame speed claim.

The exact-source per-thread CPU retry covers 15 HTTP/1 workloads, four
server/loop variants, and five repetitions: 300 response checks passed and
193 timing captures passed the host and identity guard. Its paired CPU split
shows the Python loop near or below Uvicorn on most routes, with additional
work on Tokio-named threads for fixed requests, uploads, and chunked output.
The per-workload report (`benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md`)
keeps lower-count pairs and host-rejected captures visible. An earlier 228-row
attempt had no timing captures pass the guard; it remains in the
attempt receipts (`benchmarks/results/2026-10-10/fastapi-causal-profiling-20261010/attempts.md`).

The earlier focused diagnosis on source `6b164eb…` (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/README.md`)
adds per-thread CPU evidence and qualified upload, streaming, WebSocket, HTTP/2,
lifecycle, H3 chunked-response, and slow-reader follow-ups. It narrows the main
measured HTTP/1.1 upload cost to request-body delivery and the Python/Rust
async/bytes boundary; the Python CPU route stays near parity. For that
`6b164eb…` source, four shared clean 1 MiB-upload CPU profile repetitions measured
274.8 µs/request for Uvicorn and 547.5 for uvicorn-rs, including 374.2 µs on
Tokio-named threads. A later diagnostic profile covers all 11 H1 FastAPI
workloads with three clean matched per-thread CPU repetitions each on that
earlier source. These remain separate evidence; the current `1f222c0…` source
now has its own 15-workload CPU profile with varying clean-pair counts, linked
above. Neither report provides function-level CPU shares. The earlier-source
profile confirms that uvicorn-rs uses less Python event-loop CPU but adds CPU
on Tokio-named threads. Separately, the current matrix source `1f222c0…` has a
feature-gated upload diagnostic: p50 `receive()` wait is 21.334 ms for
uvicorn-rs and 12.997 ms for Uvicorn; app time outside awaited ASGI I/O is
0.117 ms versus 0.061 ms; Python-bytes materialization takes 73.0 µs. Those
instrumented timings do not rank throughput or isolate pure `memcpy` CPU
time. On source `1f222c0…`, normal-build H3 large and chunked responses qualify
at concurrency 1; the stage report adds attribution for those paths. No
higher-concurrency H3 capacity claim is available.

The full five-category report (`benchmarks/results/2026-10-10/fastapi-final-506/README.md`)
uses source hash `b5c1140…`. Its seven low-concurrency H3 comparisons and
20-repetition lifecycle results are historical evidence for that source.
The newer focused report above uses dirty working-tree hash `6b164eb…`: H1
uploads and small WebSocket echo remain slower; the Python CPU
route is near parity; H2 transfer cases favor Rust over Hypercorn; and two H3
workloads qualify at concurrency 1. H3 large-response and high-concurrency
results remain incomplete. Both reports are single-host evidence, not a
cross-platform performance claim. The captured dirty-source thread and stack
profiles point to receive-bridge scheduling and per-frame overhead; they do
not provide function-level CPU shares. The expanded per-thread profiles add
all 11 H1 workload categories but still do not resolve individual function CPU
shares. No SIMD hotspot was identified. A feature-instrumented follow-up
measured the full request `bytes` conversion path at about 73 µs per 1 MiB
upload, but it does not separate the allocator from the copy loop. A complete
allocation/copy ledger remains open; see the bridge and copy report (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/copy-time-runtime-diagnostics-retry2-20261010/README.md`).

A same-source request-body batch-threshold experiment compared the current
256 KiB default with a temporary 1 MiB threshold on FastAPI's 1 MiB upload.
The baseline reached three shared clean pairs; host contention left the
candidate below the three-pair gate. Its two isolated clean pairs suggest
small CPU savings alongside higher RSS and worse tail latency, but are not
enough to justify changing the default. The 256 KiB source and matching native
build are restored. See the threshold experiment receipt (`benchmarks/results/2026-10-10/fastapi-upload-threshold-ab-20261010/README.md`).

The dirty `6b164eb…` working tree passed 243/243 normal-build public parity
cases. The unified matrix passed 506/506 cases across three complete runs;
Coverage-MCP measured 5,518/5,518 regions and 3,960/3,960 lines. This does not
replace hosted exact-commit CI: run #50 on `e8148e4` has a WSS oracle timeout,
and the package and Python-floor jobs were skipped.

Two fresh local host preflights were rejected before timing. The latest
eight-interval sample found unrelated `rustc` at 96.9–100.8% and
`mediaanalysisd` at 74.8–95.8% of one core in every interval; aggregate
unrelated CPU was 187.1–214.1%. No benchmark process was started. The
first receipt (`benchmarks/results/2026-10-10/fastapi-current-host-preflight-20261010/README.md`)
and follow-up receipt (`benchmarks/results/2026-10-10/fastapi-current-host-preflight-retry2-20261010/README.md`)
retain the measurements and guard policy.

A third eight-interval sample at 14:35 UTC also rejected timing. Unrelated
aggregate CPU ranged from 116.6% to 251.4% of one core; `mediaanalysisd` was
over 25% in every interval, while `rustc` and the Codex renderer also exceeded
the guard in consecutive intervals. No benchmark process was started. See the
third preflight receipt (`benchmarks/results/2026-10-10/fastapi-current-host-preflight-retry3-20261010/README.md`).

The earlier 2026-10-09 full-category run used stock FastAPI, Starlette, and
Pydantic, with one configured Tokio worker. H1, H2, WebSocket, and lifecycle
completed 520 correctness rows and produced 32 workload/loop pairs with at
least three valid matched repetitions. H3 at concurrency 64 stopped on
Hypercorn reference timeouts and produced no valid pair. The newer low-load H3
follow-up is separate evidence and does not establish high-concurrency H3
performance.

The report fastapi-thread-cpu-attribution (`benchmarks/results/2026-10-09/fastapi-thread-cpu-attribution/README.md`)
adds 48 signal-gated CPU captures across four FastAPI H1 workloads, two event
loops, and both servers. Every response passed; 12/48 captures passed the
host/identity timing guard, so all CPU captures are diagnostic-only. A separate
direct timer measured the synchronous FastAPI CPU handler in 12 captures, all
with the guard passing. It found the Python handler near parity and the
largest extra process CPU on request-body receive paths. Exact native
function-level CPU shares and a complete allocation/copy ledger remain open.

The committed `e8148e4` per-thread CPU run (`benchmarks/results/2026-10-09/fastapi-thread-cpu-mach-current-source-run2/README.md`)
passed all 12 response checks and 11/12 host/identity guards. Its clean
1 MiB-upload rows attribute about 563 µs/request of uvicorn-rs CPU to
Tokio-named threads, with 22–23 runtime-named threads observed despite one
configured async worker. The Rust Python loop itself used slightly less CPU
than Uvicorn's. These measurements are for the committed source before the
later dirty `6b164eb…` capture and must not be merged with its 374 µs/thread
result. They remain diagnostic-only and do not identify hot functions.

The committed `e8148e4` upload write-size sweep (`benchmarks/results/2026-10-09/fastapi-upload-granularity-current/README.md`)
passed response checks and obtained three to five valid pairs per workload.
For 16 KiB–1 MiB client writes, uvicorn-rs delivered about half Uvicorn's
throughput and used about three times its server CPU. Separate receive-stage
counters showed 18 Rust ASGI body messages and 17.9 bridge futures per request
versus five Uvicorn receives, while Python-bytes copy volume stayed at one
payload. This strengthens the receive-bridge diagnosis; function-level CPU
shares remain open.

The latest native stack captures (`benchmarks/results/2026-10-09/fastapi-native-stack-attribution-run2/README.md`)
add 12 correctness-passing profiles of the same FastAPI routes across asyncio
and uvloop. They show upload time concentrated in `receive()` awaits, chunked
response time in bounded Rust `send()` waits, and multiple Tokio-named runtime
threads under load despite one async worker. These are diagnostic wall-time
samples, not CPU shares or rankable benchmark rows.

The local 494-case ASGI evidence archive (`benchmarks/results/2026-10-09/asgi-unified-coverage-494/`)
records 240 live oracle comparisons, 254 target-only fault contracts, three
complete repeats, 5,298/5,298 Rust regions, 3,753/3,753 lines, and 240/240
normal-wheel parity. This archive is dirty local evidence based on `f260d78`;
the current `e8148e4` source has the same `src/lib.rs` hash, but the archive is
not an exact-commit hosted verification.

A fresh normal-wheel rerun on the current `e8148e4` source passed all 240
public parity cases with zero behavioral or infrastructure failures. The
focused TLS-WebSocket case that timed out once in hosted CI passed three
consecutive local oracle comparisons. These runs used the same source and
native-extension hashes recorded above, but the checkout was dirty, so they
do not replace clean hosted evidence. Raw reports are
here (`benchmarks/results/2026-10-09/current-full-parity-recheck-240.json`)
and here (`benchmarks/results/2026-10-09/wss-oracle-exact-e8148e4-retry3/`).

A separate 2026-10-10 follow-up repeated that WSS input eight times on the
current working tree: seven passed and one was classified as an oracle
infrastructure timeout. The failure occurred while a preflight sample showed
unrelated `mediaanalysisd` and `rustc` using about one CPU core each; three
later standard attempts and three debug attempts passed. This supports a
load-sensitive timeout as a possibility, not a proven root cause, and the
follow-up is not an exact source/build or hosted CI gate. See the
WSS follow-up receipt (`benchmarks/results/2026-10-10/ci50-wss-oracle-followup-local-20261010/README.md`).

## Latest hosted correctness and release CI

CI [run 38087300590](https://github.com/appunni-m/uvicorn-rs/actions/runs/38087300590)
completed successfully on commit [`16ed349`](https://github.com/appunni-m/uvicorn-rs/commit/16ed349f0d1528b8e6f42536b3d406ce17799915).
All eight hosted jobs passed: exact installed-wheel public parity, the full
parity and fault-contract matrix with 100% native region and line coverage,
Rust quality and documentation, the Rust minimum, package verification on
Windows/Linux/macOS, and the declared Python-floor wheel. This establishes
those gates for that commit; it does not provide a validated performance
matrix or release-candidate bundle.

CI [run 38079929722](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929722)
also passed on `443c5cc`; see the benchmark matrix section below for the
separate performance workflow that failed after its parity gates.

## Historical hosted correctness and release CI (CI #54)

CI [run #54](https://github.com/appunni-m/uvicorn-rs/actions/runs/38045596633)
completed on `a93cdff`. Rust quality, Rust 1.85, and installed-wheel public
parity passed (240/240). Unified native coverage measured 5,298/5,298 regions
and 3,753/3,753 lines, but its first case-attribution pass completed 492/494:
one oracle failure and one target-adapter infrastructure failure. The oracle
case was `http3.concurrent-stream-load-slow-reader-resource-bound`. The
infrastructure case was
`lifespan.active-response-stream-drains-on-tls-shutdown`; its annotation says
the Rust connection task failed while draining the completed response during
shutdown with `tls handshake eof`. Three later complete matrix runs each
passed 494/494. The aggregate correctly remains incomplete because those
later repeats do not erase the first-pass attribution failures. CI runs the
case-attribution pass with `--case-infra-retries 0`, and its evidence checker
requires zero failed or infrastructure-failed case receipts. A fresh run must
complete attribution and all three repeats cleanly. The two named cases passed
four focused repetitions each on the clean local `a93cdff` worktree; that does
not establish the hosted cause. The hosted annotation does not expose the
HTTP/3 observations needed to establish why its parity check failed. No clean
release candidate is established by this run.

Follow-up inspection found that the TLS-drain case reports this adapter error
after its response-body, stream-finished, and connection-close assertions have
passed. Its listener-closure check used raw TCP probes even for TLS, which can
create an incomplete-handshake EOF if a probe is accepted during shutdown. A
local HTTPS-probe correction passed 10/10 TLS-drain runs on `a93cdff`, 3/3
neighboring HTTP-drain cases, 3/3 neighboring TLS fault cases, and 6/6 runs on
the candidate source used in those local runs. The hosted cause remains unconfirmed; details and
receipts are in the TLS-drain probe follow-up (`benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md`).

## Earlier hosted multi-system benchmark (run #11)

The [ASGI performance matrix run #11](https://github.com/appunni-m/uvicorn-rs/actions/runs/38045596557)
ran on `a93cdff` across Linux x86-64, Linux ARM64, and macOS ARM64. The x86-64
and macOS jobs failed the exact normal-binary parity gate before timing. ARM64
passed parity and ran the categories, but its analysis gate failed. The
aggregate and documentation-update jobs then failed, so there is no validated
three-system report. GitHub lists all three per-system artifacts, but their
contents and job logs require authenticated access in this environment.
The public run annotations alone are insufficient to diagnose the row-level
failures or support performance claims.

## Hosted follow-up validation

Commit [`b2ea48bc`](https://github.com/appunni-m/uvicorn-rs/commit/b2ea48bc25835f37eab41a0f408ea8e4072c4e92)
changes only the parity runner's TLS listener-closure probe. CI #55
([run 38058258362](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258362))
and ASGI performance matrix #12
([run 38058258390](https://github.com/appunni-m/uvicorn-rs/actions/runs/38058258390))
were triggered on that commit. At 2026-10-10 14:16 UTC, CI #55 showed Rust
quality and MSRV passing, installed-wheel parity passing 240/240, and unified
coverage still running. The old 494-case excerpt supplied for CI #54 reports
an infrastructure failure in the TLS-drain adapter check, not a response or
ASGI behavior mismatch. The local HTTPS-probe correction and focused receipts
are recorded in the TLS-drain probe follow-up (`benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md`).

At that snapshot, benchmark #12 remained in progress. Its Linux x86-64 job
failed the exact-binary step,
`Gate the exact normal binary on every indexed public parity case`; the FastAPI
control and sequential category steps were skipped, so this system produced no
timing data. GitHub exposes the artifact
`asgi-category-benchmarks-linux-x86_64` (SHA-256
`f0ad1637ad6a494f3f3a94977ffb8cc2a1b5871a56eacd8b83b743ff60a1d4c7`); its
archive download returns 401 without authentication, and the job-log endpoint
returns 403 with `Must have admin rights to Repository`. The public annotation
does not identify which parity case failed. Linux ARM64 and macOS ARM64 jobs
remain in progress; there is no validated aggregate yet.
The hosted runs use committed server source from `a93cdff` plus the runner-only
change in `b2ea48bc`; they do not validate the dirty Rust candidate measured
in the later local reports.

At 2026-10-10 14:53 UTC, CI #55 was terminal after 28m44s. Rust quality, MSRV,
and installed-wheel parity passed (240/240). Unified coverage attributed all
494 indexed cases and measured 5,298/5,298 regions and 3,753/3,753 lines, but
the gate failed in repeat 2: 486 cases passed, the target-only fault contract
`fault.http1.early-response-body-drain-terminal-frame` was classified as
infrastructure-failed (`request-body test fault was not consumed`), and seven
later cases were not run. The previous CI #54 HTTP/3 oracle failure is not the
failure reported by #55; the hosted HTTP/3 observations from #54 remain
unavailable, so its cause is still unconfirmed.

The fault contract passed three focused local repetitions on the same
`a93cdff` Rust source, using a selected-subset coverage invocation. Each run
attributed 2,002 regions and 1,449 lines; the focused report is incomplete by
design and does not satisfy the full coverage gate. See the
reproduction receipt (`benchmarks/results/2026-10-10/ci55-body-pump-fault-repro-a93-20261010/README.md`).

Commit [`72dfa51`](https://github.com/appunni-m/uvicorn-rs/commit/72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f)
adds bounded case-specific annotations to the benchmark parity step and is
now pushed to `main`. CI #56 completed successfully on this exact commit: the
installed-wheel parity, unified coverage, package, Python-floor, Rust quality,
and MSRV gates passed. ASGI performance matrix #13 is still running on the same
commit. Its macOS ARM64 job failed exact parity at
`http1.disconnect-before-first-asgi-receive` before timing; its Linux x86-64 and
Linux ARM64 jobs passed parity and the FastAPI control, then entered sequential
category measurements. No three-system benchmark aggregate is available yet.
The exact-commit local reproduction (`benchmarks/results/2026-10-10/ci13-disconnect-exact72-repro/README.md`)
passed the case 60/60 times with matching oracle and target observations. The
hosted artifact row is now retained: Uvicorn returned `http.disconnect`, while
uvicorn-rs returned `http.request` followed by `http.disconnect`; both
follow-up responses were 200 and both connections remained usable. The fixture
uses a 50 ms delay, which is not an acknowledgment that the Rust side observed
TCP EOF before its first ASGI receive. The cause remains unconfirmed. Benchmark
#13's macOS ARM64 job failed before timing, so it supplies no macOS performance
result; the last observed Linux jobs entered category measurements, but no
validated three-system aggregate is recorded. Benchmark #12 is terminal
without validated timing data: all three system jobs and aggregation failed,
with the Linux x86-64 parity gate stopping before timing.

A focused clean-source recheck on 2026-10-20 used current `origin/main`
`0bd5877529e8f8b7434b7f7ab1852c0753f5e642` on macOS ARM64, Python 3.12.13, and
Rust 1.98.1. The single input `http1.disconnect-before-first-asgi-receive`
passed 10/10 consecutive runs against stock Uvicorn 0.54.0. The target reported
`dirty: false`, source SHA-256
`7be314247077dad7463121dcc167d0f9562a1104df8c5bc1332973bda88f37ac`, and
extension SHA-256
`08cd62c448496f035e651b2b8993304e68bd2640a35939cf2c06a1a7e88d4fe2`. Both
servers observed `http.disconnect` and equal HTTP 200 follow-up responses with
the connection open. This later local result does not identify the cause of
the older hosted mismatch and supplies no performance measurement.

## Previous hosted benchmark matrix attempt: run #16

ASGI performance matrix [run #16](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730)
ran on clean commit [`443c5cc`](https://github.com/appunni-m/uvicorn-rs/commit/443c5cc64bbb23f79cfc21edb85f11bcab9199be).
GitHub's run and job-step metadata show that all three system jobs passed
environment setup, the release-wheel build, identity freeze, the exact-binary
public-parity gate, and the FastAPI-only comparison. All three then failed in
the sequential full-category step. The multi-system validation/render job
succeeded, while the documentation-update job failed when proposing the
updated results documentation. The available metadata does not identify which
category or check caused the three category-step failures, so this run does not
establish a validated multi-system performance result.

GitHub lists the unexpired [macOS ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11681132542),
[Linux x86-64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11681108761),
[Linux ARM64 artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11680829825),
and [aggregate artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38079929730/artifacts/11681333990).
Their hosted category logs and analysis are not present in this checkout.
Inspect the `run.json`, category JSON/logs, and `analysis.json` from those exact
artifacts before attributing the hosted failure.

A separate exact-source local run on commit `443c5cc` completed its public
parity gate (240/240) and all 650 category rows with zero recorded failures.
Its analysis and raw evidence (`benchmarks/results/2026-10-11/fastapi-exact-443c5cc-local-evidence/README.md`)
show 570/650 timing rows rejected for unrelated host CPU activity; only three
matched H1 pairs qualified. The 1 MiB upload measured 0.453× Uvicorn throughput
under asyncio and 0.544× under uvloop, while HTTP/2, HTTP/3, WebSocket, and
lifecycle had no qualified pairs. This local result confirms that host load
can prevent timing qualification but does not diagnose the hosted run #16
failure.

The latest local preflight, run 7, again rejected timing before starting a
benchmark: unrelated host CPU ranged from 101.0% to 156.7% of one core, and
`mediaanalysisd` used 74.4% to 100.5% in all eight intervals. See the
preflight receipt (`benchmarks/results/2026-10-11/kata-continuation-host-preflight-7/host-preflight.json`).

A fresh preflight after the HTTP/3 input correction also rejected timing before
starting a benchmark. Unrelated CPU reached 298.1% of one core; `homed` used
58.7% to 126.4% and `cloudd` used up to 76.4% across the rejected intervals.
The host guard rejected both aggregate and sustained per-process activity. See
the preflight receipt (`benchmarks/results/2026-10-11/h3-corrected-current-host-preflight-20261011-1.json`).

The earlier 78-row full H3 report is not validation of the corrected request
framing: its recorded source hashes for the H3 script and client were
`d3f11375` and `8e798372`, and its client binary hash was
`a6947902`. The current H3 script and client source hashes are `26567768` and
`34d464c5`, and the current binary hash is `c0ae1fce`. Exclude the earlier
report's zero-failure count from evidence for the correction; its raw rows (`benchmarks/results/2026-10-11/fastapi-kata-continuation-http3-20261011/http3.json`)
remain available for its original run identity.

The focused 24-row report matches the current H3 script, client source, and
binary identities. It covers `protocol-scope` and
`protocol-scope-consumed-request`, with zero request failures and 16/24
timing-valid rows. See its raw report (`benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/http3.json`).

The complete corrected H3 matrix subsequently finished with 130/130 planned
rows and zero request failures. Source, native-extension, and probe-binary
identities were stable before and after the run. The host guard accepted 69
timing rows and rejected 61 for unrelated host CPU activity. At least three
matched valid repetitions exist for `protocol-scope` and `fixed` under both
loops, `large-response` under both loops, and `protocol-scope-consumed-request`
under uvloop. The run analysis (`benchmarks/results/2026-10-11/h3-rfc-input-corrected-repeat-20261011-1.artifacts/README.md`)
reports their same-repetition throughput, latency, server CPU, and RSS ratios.
These are one local Mac run against Hypercorn, not a multi-system or repeated
release performance result. The chunked-response and slow-reader workloads
have no qualified pairs; H3 upload has no Hypercorn reference rows and no valid
Rust timing rows. The raw report (`benchmarks/results/2026-10-11/h3-rfc-input-corrected-repeat-20261011-1.json`),
JSONL checkpoints, and runner log retain all results.

Review of run #16's `443c5cc` client source found that it sent a one-byte body
with `Content-Length: 1` on every non-upload GET workload. The current
candidate sends bodyless GETs for ordinary requests and POST with one byte only
for the request-consuming workload, in accordance with RFC 9110's GET
semantics. The corrected full matrix passed its response checks. This input
correction does not by itself establish why run #16 exited nonzero; that still
requires the retained category log.

The first four post-run host preflights rejected timing before starting another
measurement. Unrelated CPU ranged 178.6–200.0%, 78.4–202.4%, 90.6–282.9%,
and 171.9–199.7% of one core across their eight intervals. The first recorded
`rustc` and `mediaanalysisd` above 25% in every interval; the third included
sustained `mediaanalysisd` activity. See preflight 1 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-1.json`),
2 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-2.json`),
3 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-3.json`),
and 4 (`benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-4.json`).
No process was stopped and no benchmark measurement began during these
preflights.

## Release candidate

No release-candidate bundle is ready. CI run `38087300590` passed its eight
hosted gates on clean commit `16ed349`. The newer ASGI benchmark matrix
`38122909359` stopped in the sequential category step on all three systems, so
it produced no validated multi-system performance result. Its docs-update job
pushed the evidence branch, then `gh pr create` failed because GitHub Actions
was not permitted to create or approve pull requests. No PR was opened. No tag,
GitHub Release or PyPI package was created at that historical snapshot. On
2026-10-22, the four Cargo crates were later bootstrapped at `0.1.0` from clean
commit `9eccb4f` to enable Trusted Publisher setup; this did not create a full
release candidate or complete the performance gate. See [release status](releases.md).

## Reproduction

Use the maintained setup and commands in the [benchmark guide](benchmarks.md).
Freeze the source, native extension, FastAPI app, clients, Python and
dependencies; pass the complete parity gate before timing; retain rejected
attempts; and report each protocol/reference separately. A failed reference
workload is incomplete evidence, not a performance result.

## Current-main FastAPI upload and body-batch trial (2026-10-20)

On `a22286c3c8120d811ac5e9d2cf8b86ce4f9559e3`, the maintained
`fastapi-upload-1m-write-1k` input completed five matched repetitions against
Uvicorn with zero client failures and clean shutdown. The input is a 1 MiB
FastAPI `Request.body()` upload sent in 1 KiB writes at concurrency 8. The
normal Rust build was slower on this workload: median throughput was 574.7
requests/s for uvicorn-rs and 701.8 for Uvicorn; the median same-repetition
Rust/Uvicorn throughput ratio was 0.837. Rust median p50/p95/p99 latency was
13.88/17.37/18.93 ms, server CPU was 2,307 µs/request, and peak RSS was 63.57
MiB. This does not reproduce the hosted 15-second timeout and does not explain
its cause.

The next isolated trial changed only
`HTTP_REQUEST_BODY_BATCH_BYTES` from 256 KiB to 1 MiB; the 5 ms maximum batch
wait stayed fixed. The selected black-box case
`http1.request-streaming-progress-before-upload-complete` passed with that
candidate. Both upload reports had ten timing-valid rows, zero request
failures, and clean lifecycle gates. The baseline's unrelated host CPU peak
was 33.7% of one core; the candidate report peaked at 97.9%. The runner
accepted the rows, but that host activity means the separate reports are
diagnostic rather than a clean optimization acceptance measurement.

| Batch cap | Median Uvicorn req/s | Median uvicorn-rs req/s | Median paired Rust/Uvicorn ratio | Rust p50/p95/p99 (ms) | Rust server CPU (µs/request) | Rust peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 256 KiB (current) | 701.8 | 574.7 | 0.837× | 13.88 / 17.37 / 18.93 | 2,307 | 63.57 |
| 1 MiB (trial) | 723.0 | 553.6 | 0.766× | 14.42 / 16.78 / 18.20 | 2,294 | 64.41 |

The 1 MiB trial did not improve throughput or median latency. Its small p95/p99
reductions came with lower throughput, slightly higher RSS, and no material
CPU reduction. No default change was retained; the source and installed wheel
were restored to the 256 KiB build. The timeout diagnosis remains open. The
next useful measurement is CPU attribution by thread and call path before
trying more batch-size variants.

Both reports used CPython 3.12.13, FastAPI 0.142.4, Starlette 1.7.0, Uvicorn
0.54.0, uvloop 0.23.0, httptools 0.8.0, a C/libcurl 8.5.0 client, and an AMD
Ryzen 5 2600X Linux x86-64 host with 12 logical CPUs. The host compiler was
rustc/cargo 1.91.1. The baseline and candidate source hashes were
`6f0122e7c11a42ccde20b14899132c69ae8aa111c7d5a8856278927b6a763640` and
`bb5f17aed4edb773cebc3df4f26c2f6da44898aa65b7d2fe22b5b2b9c694abd5`; their
native-extension hashes were `5e3e817db8a4947b3e2b53b9bc9cc863fc6a551169e5aa870b4efd92b935f1e4`
and `d834528a6fa558c837052c8063a28dd6b307aabd3a610b619feae69239ff6a46`.
Raw JSON and logs are retained locally, ignored by Git, under
`target/benchmark-evidence/fastapi-h1-upload-a22286c3/`; the JSON hashes are
`a0911d7956051368af9febff5b0bbe633843e4076beb45a71ce6e2f917aeda86` for the
baseline and `54406b8a789a3fc7e707037481c8ff6b08e1d6cd9fe0a6a135a3f13b1cd1f42a`
for the trial. These are single-host diagnostics, not a multi-system release
performance claim.

## Sampled CPU attribution for the FastAPI upload (macOS arm64; 2026-10-20; profiling only)

Samply captured one eight-second `fastapi-upload-1m-write-1k` run per server at
concurrency 8, using CPython 3.12.13, FastAPI 0.142.4, Starlette 1.7.0,
uvloop 0.23.0, httptools 0.8.0, and Uvicorn 0.54.0. The maintained C/libcurl
client verified every response. The profiling app adds ASGI timing hooks, so
these samples locate work; they are not a clean performance comparison.

The normal release Samply profiles attributed about 6.20 CPU seconds to
uvicorn-rs's primary Tokio worker and 1.72 seconds to its Python thread during
the load interval. Seven other Tokio-named threads used about 39–40 ms each.
Uvicorn's Python server thread used about 6.75 seconds; its four libuv worker
threads had negligible sampled CPU. These values sum the profiler's
`threadCPUDelta` samples. They are diagnostic only and are not qualified
CPU-per-request metrics.

A separate optimized build with Rust debug symbols located the hottest Rust
stacks in `serve_listener` → `peer_read::pump_peer_read` → Tokio's owned TCP
read → `mio`/`std::net::TcpStream::read`. This points to socket ingress and
request-body dispatch as the leading Rust-side cost in this workload. The
profile does not isolate memory copies from kernel read work, so it does not
establish a copy or SIMD bottleneck.

The symbol-enabled profile also resolved the extra Tokio-named threads: they
were Tokio blocking-pool workers, not additional Tokio async workers. Their
stacks lead through `pyo3_async_runtimes::generic::future_into_py_with_locals`
and `AsgiIo::receive`; most were parked and used about 12–14 ms of sampled CPU
each. The bridge completes each Rust future by scheduling Python result
delivery that must attach the GIL. The server still configures one Tokio async
worker (`TOKIO_WORKER_THREADS = 1`). The extra threads did not account for the
main CPU cost in this run.

This narrows the follow-up to the H1 socket-read/pump path and the per-future
Python completion bridge. It does not explain the slower Linux benchmark: the
Linux host disallows unprivileged `perf` sampling, and the macOS profile is a
different system with profiling instrumentation enabled. No production
optimization was retained from this evidence. Raw profiles and receipts stay
under ignored `target/profile-current-main/`.

## 32 KiB proactive TCP read chunks (Linux x86-64; 2026-10-21)

A focused normal-build A/B changed only the proactive TCP read chunk from 16 KiB
to 32 KiB. The workload was stock FastAPI `fastapi-upload-1m-write-1k`: a
1 MiB request body written in 1 KiB chunks, concurrency 8, 5 seconds of warmup
and measurement, and three repetitions. Both reports used CPython 3.12.13,
FastAPI 0.142.4, Starlette 1.7.0, Uvicorn 0.54.0, httptools 0.8.0, Node.js
22.15.0, rustc 1.91.1, and the same AMD Ryzen 5 2600X host. The client binary
hash was identical. The host preflight passed; all six rows in each report had
valid timing, zero request failures, and successful lifecycle checks.

| Proactive read chunk | Median Uvicorn req/s | Median uvicorn-rs req/s | Median paired Rust/Uvicorn ratio | Rust p50/p95/p99 (ms) | Rust server CPU (µs/request) | Rust peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 KiB | 890.9 | 860.1 | 0.966× | 9.114 / 12.141 / 13.725 | 1,897 | 60.75 |
| 32 KiB | 901.7 | 941.8 | 1.069× | 8.263 / 11.543 / 13.683 | 1,772 | 60.10 |

The 32 KiB candidate improved Rust throughput in all three corresponding
repetitions (4–16%), reduced server CPU in each repetition (5–12%), and lowered
median p95 by 0.60 ms. Uvicorn also had one unusually fast repetition in the
candidate report, so the paired ratio is sensitive to repetition alignment.
Treat this as a promising single-host result, not a multi-system release claim.
The change does not remove the proactive reader's input copy; larger chunks
may reduce read and channel scheduling overhead, but this run does not isolate
that mechanism.

The read-ahead bound increases from at most 48 KiB to 96 KiB per active
proactive TCP connection (two queued chunks plus one being consumed), adding up
to 48 MiB at the default 1,024-connection limit. The focused workload did not
show an RSS increase. Focused parity cases for request upload, streaming
progress, early response with unread upload, and disconnect while receive waits
passed on macOS arm64 and Linux x86-64. Broader category and high-concurrency
memory evidence is still required before release performance acceptance.

Baseline and candidate source hashes were
`14f37509aaf7a7c38f40ac4922e137a5930ca501ee69f20e65f6ef39432ab4b0` and
`120565c8f5747d3fd43c3a314c51c9ef4c6a9b0bb4f38ee07b43102ac8e9d1b9`; native
extension hashes were
`8b24e6c6c99239ba6a571ed511779b6769f426a116b9f2a505c0e694b0a6b557` and
`67b042b774bb30229bcce846e1675e31a2f2599a9f7faea3696f20b177e671ca`. Raw
reports and logs remain under ignored `target/` in the Linux work folder.

## Focused H3 replay after the Hypercorn failure (GitHub x86-64; 2026-10-20)

The earlier H3 category run recorded a `hypercorn-asyncio` failure in
`slow-reader-backpressure`: two header timeouts, while Hypercorn's log showed
an HTTP/3 `KeyError(48)` during stream lookup. Whether that server error caused
the timeouts is unconfirmed. A focused replay of that server/workload
completed three repetitions on the GitHub Linux x86-64 runner. Each repetition
served 40 requests and 40 MiB of response data, recorded zero request failures,
passed the server lifecycle gate, and left an empty server log. The replay did
not reproduce the earlier failure; its cause remains unknown.

The replay used CPython 3.12.13, Hypercorn 0.18.0, and rustc 1.98.1 on an
Intel Xeon Platinum 8573C runner with four logical CPUs. The three repetitions
had p95 latency of 252.72, 252.49, and 252.20 ms. This was a focused correctness
replay against Hypercorn, not a matched performance comparison. The full H3
category remains incomplete, so these results do not qualify an H3 speed claim.

Evidence: [focused replay on GitHub Actions](https://github.com/appunni-m/uvicorn-rs/actions/runs/39515929518)
and [earlier category run](https://github.com/appunni-m/uvicorn-rs/actions/runs/39471910457).

## Category benchmark logging/header parity audit (2026-10-21)

An audit of the maintained H1, H2, H3, and WebSocket command builders found
that reference servers ran with access logs disabled and the `Server` header
disabled, while the Rust server kept both defaults enabled. This adds per-request
logging work only to the candidate and makes the response-header workload
different. The prior timing rows therefore do not meet the matched-configuration
gate. Their case-level response checks and retained logs remain useful, but the
cross-server timing comparisons are diagnostic until rerun.

The category runners now explicitly disable access logs and `Server` headers
on both sides, set ERROR logging, and match `Date` header behavior per protocol:
enabled for H1, H2, and WebSockets; disabled for H3. Their report metadata now
states candidate and reference policy together. The current source's proactive
TCP read chunk is 64 KiB; the earlier 16/32 KiB performance comparison also
needs a corrected-command replay before its cross-server ratio is used as
performance evidence. No benchmark timing was collected as part of this audit.
Only the four command builders and these benchmark instructions/evidence notes
were changed; raw reports, logs, and coverage artifacts remain excluded from
Git.

## Focused matched H1 upload after command parity (Linux x86-64; 2026-10-21)

On main commit `c7a5e335f3f53cac8373db1e9fab2789d21859b0`, the normal release
wheel was measured against Uvicorn 0.54.0 using the corrected H1 commands. The
workload was upstream FastAPI 0.142.4 / Starlette 1.7.0 receiving a 1 MiB body
in 1 KiB writes at concurrency 8, with a 1-second warmup, 5-second load window,
and five repetitions. All 20 rows passed the response and lifecycle checks;
all five repetitions were timing-valid for each loop pair. The report marked
performance evidence `completed`, recorded stable source and extension
identity, and found no unrecorded dependencies. Both servers had access logs
disabled, `Server` headers disabled, and `Date` headers enabled; all server
logs were empty.

The host was Linux x86-64 with an AMD Ryzen 5 2600X and 12 logical CPUs. The
runtime was CPython 3.12.13, Rust 1.98.1, uvloop 0.23.0, httptools 0.8.0,
Uvicorn 0.54.0, and Node.js 22.15.0. The normal release wheel used one Tokio
worker. This remains an in-process Python FastAPI application: route handling
and application code execute in Python through the bridge.

| Event loop | Server | Median in-window requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Server CPU (µs/request) | Peak RSS (MiB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| asyncio | uvicorn-rs | 984.8 | 7.819 | 11.272 | 13.863 | 1,705 | 60.21 |
| asyncio | Uvicorn | 1,074.0 | 7.025 | 11.886 | 13.801 | 866 | 55.56 |
| uvloop | uvicorn-rs | 1,258.8 | 5.461 | 10.388 | 11.932 | 1,044 | 60.91 |
| uvloop | Uvicorn | 779.2 | 9.915 | 13.870 | 15.234 | 1,260 | 56.67 |

For this case, uvicorn-rs reached 0.917× Uvicorn throughput under asyncio and
1.616× under uvloop. Its median server CPU was 1.97× Uvicorn's under asyncio
and 0.829× under uvloop. Peak RSS was about 4.2–4.7 MiB higher on Rust. The
result shows that loop selection changes the measured outcome; it does not
establish a general server speedup or satisfy the multi-system/category release
gate. It also does not isolate Python execution, bridge cost, or memory copies.

The raw JSON, driver log, and per-server artifacts are retained under ignored
`target/focused-overhead/2026-10-21-c7a5e335f/`; the matching host copy remains
under `/home/appunni/work/uvicorn-rs-bench-overhead-c7a5e335f/target/`. These
files are not committed.

## Focused matched protocol and lifecycle slice (Linux x86-64; 2026-10-21)

One representative workload was measured for each maintained protocol
category, plus the lifecycle scenario. HTTP/1.1 used stock FastAPI 0.142.4 /
Starlette 1.7.0 and a 1 MiB upload written in 1 KiB chunks (concurrency 8).
HTTP/2 and HTTP/3 used `protocol-scope` against Hypercorn 0.18.0 (concurrency 64
and 1 respectively). The WebSocket case echoed 32-byte text messages from the
same FastAPI app (concurrency 32). Each protocol sample used a one-second
warmup, five-second measurement, and five planned repetitions. The lifecycle
scenario measured cold start, idle SIGTERM shutdown, and SIGTERM while one ASGI
request was held.

All reports used CPython 3.12.13 and Rust 1.98.1 on Linux x86-64, an AMD Ryzen 5
2600X with 12 logical CPUs. The pinned references were Uvicorn 0.54.0,
Hypercorn 0.18.0, uvloop 0.23.0, httptools 0.8.0, FastAPI 0.142.4, and
Starlette 1.7.0. H1, H2, H3, and WebSocket used matched access-log and
`Server`-header settings; `Date` was enabled for H1, H2, and WebSockets and
disabled for H3. Source identity was stable in every report and no unrecorded
dependencies were found.

Every request/message and lifecycle correctness check passed. H1 and WebSocket
had 20/20 timing-valid rows. H2, H3, and lifecycle each had 19/20 timing-valid
rows; the excluded row in each case failed the unrelated-host-CPU guard. Each
same-loop comparison retained at least four matching repetitions. Throughput
and resource values below are per-server medians; the ratio is Rust's median
divided by the reference median.

| Category and workload | Loop | Reference → Rust throughput | Rust/reference | Reference p50/p95/p99 (ms) | Rust p50/p95/p99 (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| H1 FastAPI upload, 1 MiB / 1 KiB writes | asyncio | 1,074.0 → 984.8 req/s | 0.917× | 7.025 / 11.886 / 13.801 | 7.819 / 11.272 / 13.863 |
| H1 FastAPI upload, 1 MiB / 1 KiB writes | uvloop | 779.2 → 1,258.8 req/s | 1.616× | 9.915 / 13.870 / 15.234 | 5.461 / 10.388 / 11.932 |
| H2 `protocol-scope` | asyncio | 2,620.6 → 5,622.3 req/s | 2.145× | 23.537 / 39.503 / 42.107 | 11.459 / 18.054 / 21.319 |
| H2 `protocol-scope` | uvloop | 2,559.5 → 6,598.0 req/s | 2.578× | 24.024 / 40.772 / 43.064 | 9.688 / 15.372 / 18.044 |
| H3 `protocol-scope` | asyncio | 1,370.2 → 2,254.8 req/s | 1.646× | 0.736 / 0.756 / 0.794 | 0.457 / 0.527 / 0.565 |
| H3 `protocol-scope` | uvloop | 1,465.8 → 2,382.3 req/s | 1.625× | 0.682 / 0.748 / 0.830 | 0.426 / 0.479 / 0.514 |
| WebSocket 32-byte text echo | asyncio | 21,780.5 → 9,099.6 messages/s | 0.418× | 1.420 / 1.737 / 1.805 | 3.672 / 5.034 / 5.595 |
| WebSocket 32-byte text echo | uvloop | 23,400.1 → 15,851.0 messages/s | 0.677× | 1.371 / 1.577 / 1.639 | 2.140 / 2.824 / 3.028 |

| Category and loop | Reference → Rust server CPU (µs/request or message) | Reference → Rust peak RSS (MiB) |
| --- | ---: | ---: |
| H1 asyncio | 866 → 1,705 | 55.56 → 60.21 |
| H1 uvloop | 1,260 → 1,044 | 56.67 → 60.91 |
| H2 asyncio | 378.391 → 222.703 | 92.094 → 50.387 |
| H2 uvloop | 386.380 → 190.591 | 94.492 → 52.992 |
| H3 asyncio | 725.442 → 432.203 | 109.387 → 48.645 |
| H3 uvloop | 676.723 → 395.471 | 111.275 → 51.320 |
| WebSocket asyncio | 45.705 → 182.912 | 48.477 → 54.684 |
| WebSocket uvloop | 42.462 → 104.663 | 50.949 → 57.203 |

The lifecycle measurements are separate observations, not request-throughput
results. Values are medians in milliseconds (reference → Rust); RSS is the
sampled server peak.

| Loop | Cold start to lifespan response | Idle SIGTERM to exit | Held-request SIGTERM to exit | Peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: |
| asyncio | 342.260 → 338.573 | 205.244 → 15.394 | 2,207.171 → 2,018.061 | 43.898 → 45.547 |
| uvloop | 342.442 → 342.902 | 219.652 → 7.328 | 2,224.131 → 2,034.127 | 46.922 → 48.170 |

These results are workload-specific. H2 and H3 were faster on this small
`protocol-scope` case, H1 changed direction with the event loop, and the Rust
WebSocket implementation was slower on 32-byte text echo. Lifecycle startup was
similar; measured shutdown was shorter for Rust in this scenario. They do not
establish a broad speedup, a high-concurrency H3 result, or a multi-system
release claim. More workload families and additional systems remain to be
measured.

The H2 runner accepted nine single `BrokenPipe` peer-close diagnostics from ten
Rust samples, each within its recorded limit of eight after the client had
validated responses and shut down its HTTP/2 driver; unexpected native errors
remained zero. Each Uvicorn WebSocket reference launch emitted the pinned
`--ws websockets` deprecation warning before timing; all 20 rows still passed
correctness and lifecycle checks. Raw JSON, JSONL checkpoints, logs, and
per-server artifacts remain under ignored `target/focused-overhead/2026-10-21-c7a5e335f/`
and the Linux work folder; no raw result or coverage report is committed.
