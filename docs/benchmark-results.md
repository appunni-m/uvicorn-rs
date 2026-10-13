# FastAPI benchmark results

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

Each dated result is bound to the source and normal extension recorded in its
receipt. “Current source” in an older benchmark entry means current for that
measurement, not necessarily the present worktree. The latest 511-case coverage
run is instrumented correctness evidence and does not add performance samples.

## Samply CPU profiles of fixed H1 and uploads (2026-10-12)

Four correctness-passing Samply profiles used the same stock FastAPI 0.142.4
application, CPython 3.12.13, asyncio, Uvicorn 0.54.0 with httptools, and the
dirty uvicorn-rs source SHA-256
db4d8297c607fb722415c3dc2a0c5891cd05bbf582872e194dfb142283e7822a. The normal
Rust extension SHA-256 was
351c3d36f4b42ba1d4313c366c31a67a96e6b22e9e6a796cd5f9ca34b5a4823d. All
warmups and load responses passed; all servers shut down gracefully. The
profiles covered about 4.5 seconds of each nine-second load because Samply
started with the server and captured six seconds including startup and warmup.

| Workload | Server | Active load covered | Sampled process CPU weight | Threads with Tokio blocking-pool loop stacks |
|---|---|---:|---:|---:|
| Fixed response | uvicorn-rs | 4.58 s | 5.061 s | 1 |
| Fixed response | Uvicorn | 4.51 s | 4.450 s | 0 |
| 1 MiB request upload | uvicorn-rs | 4.55 s | 6.255 s | 32 |
| 1 MiB request upload | Uvicorn | 4.50 s | 4.432 s | 0 |

The single Tokio scheduler worker remains configured in the Rust source. The
32 upload threads are not 32 scheduler workers: their sampled stacks enter
Tokio's blocking-pool thread loop. During the fixed route, the Rust profile
attributed 1.528 s of sampled CPU weight to one Tokio-named thread; during
upload it attributed 4.147 s across 32 such threads. Uvicorn's profiles showed
one Python server thread.

In the Rust upload profile, the inclusive call path for the PyO3
AsgiIo.receive future accumulated 1.245 s (19.9% of sampled process CPU
weight); PyGILState_Ensure appeared in 1.058 s (16.9%). These values overlap
because they are caller-stack weights, not exclusive time. They point to
receive-bridge scheduling and GIL attachment as optimization targets, with
Tokio blocking-pool activity as a second measurable factor. They do not prove
that copying bytes is the dominant cost.

These are diagnostic profiles, not CPU-per-request or speed results. The OS
shared-cache functions remain unresolved, profiles perturb scheduling, and
only part of the load interval was sampled. At the time these profiles were
reviewed, the host-clean matched timing gate rejected the machine, so the next
performance step was the existing blocking-pool cap comparison after a clean
preflight. The raw profiles, source
snapshots, receipts, machine-readable analysis, and profile guide are in the
Samply attribution report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-samply-attribution/README.md`).
A subsequent eight-interval host preflight also rejected: unrelated aggregate
CPU was 100.4–151.4%, with a process named `python3.12` using 85.3–104.3% of one
core. That receipt did not start a timed run; later accepted windows allowed the
partial experiment below. See the preflight receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-post-doc-audit.json`).

## First blocking-pool cap timing slice (2026-10-12)

The first normal-build timing slice compared the same stock FastAPI 1 MiB
uploads at default Tokio blocking-pool settings and a cap of one. It ran on
macOS 15.7.7 / Apple M3 Pro with CPython 3.12.13 and Uvicorn 0.54.0
(`httptools`). Each setting used asyncio, concurrency 8, three planned
repetitions, five seconds of load, one second of warmup, and seed `20261012`.
The Tokio async scheduler remains one worker. Responses, body checks, and
shutdown passed; the per-row host guard determined which timings qualified.

The only qualified pair was the default pool for `fastapi-request-upload`
(1 MiB request body, 64 KiB libcurl read-callback cap): Uvicorn completed
4,149.3 requests/s and Rust 3,840.0, a 0.925× ratio. Median p50/p95/p99 were
1.918/2.088/2.215 ms for Uvicorn and 2.065/2.711/2.992 ms for Rust. Observed
server CPU was 240.5 versus 420.1 µs/request; server RSS was 113.0 versus
110.3 MiB. Client CPU was 153.2 versus 178.7 µs/request and client RSS 6.94
versus 6.69 MiB.

This is a descriptive three-repeat pair, not a statistical-significance claim.
It establishes the default-pool baseline for this run only. The default
256 KiB workload lacked valid paired repetitions. The cap-1 run passed all
response checks but host activity invalidated all Rust timing rows, so it has
no qualified pair. Cap 4 has not run: ten cap-4 preflights and eighteen resumed
preflights rejected before timing. Across the resumed checks, unrelated CPU
ranged from 56.2% to 279.6%, with `mediaanalysisd` above the per-process limit
in the latest receipt. No process was stopped. See the latest
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-18.json`).
The experiment report and raw results (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/README.md`)
preserve configuration, identities, exclusions, and receipts. No conclusion
about the cap's effect is supported yet.

## H1 benchmark-source retries stopped by host activity (2026-10-12)

The captured dirty benchmark source passed 243/243 public parity cases, and
each attempt's
initial host preflight accepted. Unrelated CPU load returned during both full
300-row HTTP/1 plans. The first stopped at 41 rows (zero response failures, 24
timing-valid, 17 host-rejected); the retry stopped at 22 (zero failures, 9
timing-valid, 13 host-rejected). The strict analyzer withheld throughput and
latency ratios because category completion and identity gates were incomplete.
Do not combine these partial attempts. See the attempt ledger and raw
evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/README.md`).
They are not performance results.

## FastAPI H1 benchmark-source route and fixed-response batch (2026-10-12)

The captured dirty benchmark source passed 243/243 public parity cases before
a complete 40-row selected-subset run on stock FastAPI. All response checks passed; 30
rows passed the host guard. Three pairs qualified: validated-route throughput
was 0.900× Uvicorn under asyncio and 0.966× under uvloop, while fixed-response
throughput was 0.750× under asyncio. The fixed-response uvloop pair had only
two valid repetitions. Qualified pairs used 9.0–20.1 µs more aggregate server
process CPU per operation. These totals do not identify whether the extra CPU
is in the Python app, bridge, or Rust network path. See the run report and raw
evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-route-fixed/README.md`).
The selected subset covers two of 15 H1 workloads and is not an overall
performance claim.

## FastAPI H1 benchmark-source response workloads (2026-10-12)

A separate 60-row batch covered large responses, many response chunks, and
small response chunks. All correctness checks passed; 50 timing rows were
accepted by the host guard and five workload/loop pairs qualified. Throughput
versus Uvicorn was 0.871× / 0.931× for large responses, 0.956× / 1.275× for
many chunks under asyncio / uvloop, and 0.920× for small chunks under asyncio.
Small response chunks under uvloop had only two valid repetitions. Rust used
more aggregate server-process CPU in every qualified pair. The source-bound
report and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-response-workloads/README.md`)
include latency percentiles, CPU, RSS, host exclusions, and interpretation
limits. These measurements do not establish an overall speedup.

## FastAPI H1 benchmark-source request-upload workloads (2026-10-12)

A 120-row batch exercised six upload cases on the same stock FastAPI app; all
correctness rows passed, 60 rows passed the host timing guard, and five
workload/loop pairs qualified. Throughput versus Uvicorn was 0.648× / 0.686×
for 1 MiB bodies written in 64 KiB chunks, 1.001× / 0.995× for 1 KiB chunks,
and 0.649× for 256 KiB chunks under asyncio. Rust used more aggregate server
CPU in all five qualified pairs. The other workloads lacked enough matching
valid samples. The source-bound report and raw evidence (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-workloads/README.md`)
include latency percentiles, CPU, RSS, host exclusions, and interpretation
limits. The input-size dependence suggests the receive path should be profiled,
but this data does not attribute the overhead to a specific function or
establish an overall speedup.

The apparent throughput parity for 1 MiB requests written in 1 KiB chunks is
client-limited: the load generator used about 33 ms CPU/request, equivalent to
roughly 10.4–10.8 cores at the observed rate on the 12-core machine, while the
server used about 1.0–1.3 ms/request. These rows do not establish server parity.
The “write chunk” setting is actually a cap on bytes returned from the
libcurl read callback; it does not guarantee TCP packet or socket-write sizes.
The upload report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-workloads/README.md`)
records the calculation and the separated-client follow-up.

## Replayed archived 1 KiB upload failure (2026-10-12)

The attached macOS ARM64 archive stopped its 300-row HTTP/1.1 plan at row 120.
Its Rust/uvloop 1 MiB upload with 1 KiB libcurl reads recorded 31 client send
failures and an ASGI `ClientDisconnect`. A focused current-dirty-build replay
completed all 20 samples with zero request failures, so the archived failure
did not reproduce. The source and native-extension hashes differ between the
runs, so this does not establish a fix or root cause. All 20 replay timings
were rejected for unrelated host CPU activity; no performance comparison is
available. See the replay report and raw artifacts (`benchmarks/results/2026-10-12/http1-upload-1k-current-20261012/README.md`).

The post-run host preflight rejected another timed run before it started:
unrelated aggregate CPU peaked at 134.4% of one core and `mediaanalysisd` used
72.4–105.2% across all eight intervals. A later retry still rejected, with
aggregate CPU peaking at 129.0% and that process above 25% in every interval.
No result-grade timing was started after those rejections. A later
diagnostic-only upload profile ran with the host guard rejecting; all profile
timing rows are explicitly unrankable. Its thread snapshots show one Tokio
async scheduler worker plus blocking-pool threads, and sampled stacks include
the PyO3 future-completion/GIL path. This is a testable overhead hypothesis,
not a measured CPU attribution. See the profile report (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-profile/README.md`),
host receipts (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-h1-rest.json`),
and retry (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-profile-next-2.json`).
The latest preflight also rejected before timing: `mediaanalysisd` used
63.2–87.9% of one core in all eight intervals and unrelated aggregate CPU
peaked at 115.9%. A retry 30 seconds later also rejected: aggregate unrelated
CPU peaked at 290.0%, and `mediaanalysisd` remained at 65.5–87.2% in every
interval. See the first check (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-20261012.json`)
and retry (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry1-20261012.json`).
A second retry also rejected, with `mediaanalysisd` at 56.6–85.9% of one core
in all eight intervals and unrelated aggregate CPU peaking at 136.4%. See the
second retry receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry2-20261012.json`).
A third retry rejected too: unrelated aggregate CPU peaked at 214.2%, while
`mediaanalysisd` used 55.1–87.8% and a `python3.12` process used 86.0–100.5%
in all intervals. It started no benchmark and stopped no process. See the
third receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry3-20261012.json`).
A fourth retry also rejected: `mediaanalysisd` used 51.6–98.4%, `rustc` used
94.0–103.5% in all intervals, and aggregate unrelated CPU peaked at 220.1%.
No benchmark started. See the fourth receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry4-20261012.json`).
A fifth preflight 60 seconds later rejected too: `mediaanalysisd` used
70.8–75.5%, `rustc` used 94.3–101.5% in all intervals, and aggregate CPU
peaked at 211.9%. See the fifth receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry5-20261012.json`).
A fresh preflight on continuation rejected too: aggregate unrelated CPU
peaked at 200.3%, `mediaanalysisd` used 50.6–80.4% in all intervals, and a
`python3.12` process used 95.8–97.1% in three. No timing began. See the
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-1.json`).
A second continuation preflight rejected as well: aggregate unrelated CPU
peaked at 227.1%, `mediaanalysisd` used 46.8–73.5% in all intervals, `git`
used 27.5–32.0% in seven, and `rustc` briefly used 101.1%. See the
receipt (`benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-2.json`).

The next workstream preflight also rejected before timing. `mediaanalysisd` used
25.6–91.9% of one core, `rustc` used 44.6–98.3% across consecutive samples,
and unrelated aggregate CPU peaked at 192.4%. The receipt confirms
`timing_benchmark_started: false`; no process was stopped. See the
preflight receipt (`benchmarks/results/2026-10-12/kata-workstream-host-preflight.json`).
A follow-up preflight rejected too: `mediaanalysisd` used 77.3–100.0% and
`rustc` 98.6–103.1% of one core in all eight intervals, while unrelated
aggregate CPU ranged from 198.8% to 222.1%. No timing started and no process
was stopped. See the follow-up receipt (`benchmarks/results/2026-10-12/kata-workstream-host-preflight-retry-1.json`).
A second follow-up also rejected: `mediaanalysisd` used 69.5–102.9% of one
core, and unrelated aggregate CPU ranged from 97.7% to 122.0% across the eight
samples. No timing started and no process was stopped. See the second follow-up
receipt (`benchmarks/results/2026-10-12/kata-workstream-host-preflight-retry-2.json`).
A third follow-up rejected after another 30 seconds: `mediaanalysisd` used
62.9–101.2% of one core, and aggregate unrelated CPU ranged from 87.3% to
136.4%, with consecutive samples above the aggregate threshold. No timing
started and no process was stopped. See the third follow-up
receipt (`benchmarks/results/2026-10-12/kata-workstream-host-preflight-retry-3.json`).
A fourth spaced preflight rejected as well: `mediaanalysisd` used 66.2–100.9%
of one core, `qemu-system-aarch64-headless` briefly reached 28.7%, and
unrelated aggregate CPU ranged from 94.8% to 140.1%, including consecutive
over-limit intervals. No timing started and no process was stopped. See the
fourth follow-up receipt (`benchmarks/results/2026-10-12/kata-workstream-host-preflight-retry-4.json`).

## Latest full-category attempt: exact commit `443c5cc` (2026-10-11)

A local run on the commit used by hosted benchmark #16 passed its 240/240
public parity gate and completed all 650 correctness-gated category rows with
zero recorded failures. It qualified only three matched H1 pairs; the other
570 timing rows were rejected for unrelated host CPU activity, and HTTP/2,
HTTP/3, WebSocket, and lifecycle produced no qualified pairs. The
source-bound report and raw archive (`benchmarks/results/2026-10-11/fastapi-exact-443c5cc-local-evidence/README.md`)
preserve the evidence. The recorded source hash was
`56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; all 59
source/harness identities in its receipts matched commit `443c5cc` when
reviewed.

| Qualified workload | Throughput ratio | p50, reference → Rust | Server CPU, reference → Rust |
|---|---:|---:|---:|
| H1 small response chunks, asyncio | 0.952× | 23.782 → 25.076 ms | 376.0 → 574.7 µs/request |
| H1 1 MiB upload, asyncio | 0.453× | 18.798 → 43.534 ms | 307.0 → 1,066.8 µs/request |
| H1 1 MiB upload, uvloop | 0.544× | 18.225 → 33.920 ms | 288.4 → 831.4 µs/request |

The H1 upload workload regressed substantially in this run. These three pairs
are a local exact-commit result, not a general speed claim and not an
explanation for the hosted #16 category-step failure. The latest host preflight
rejected another timing attempt before it started; preflight 10 (`benchmarks/results/2026-10-11/kata-continuation-preflight-http-spec-20261011-10/host-preflight.json`)
records the host activity. See [benchmark status](benchmark-status.md).

## HTTP/3 request-shape correction (2026-10-11)

The Rust H3 probe now sends ordinary GETs with no request content and no
`Content-Length` field. RFC 9110 says a sender SHOULD NOT include
`Content-Length` when a request has no content and its method does not
anticipate it, and that GET content has no generally defined semantics
([§8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6),
[§9.3.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.1)). The
dedicated consumed-request route accepts POST and reads its one-byte body; the
upload workload also uses POST. The body buffer is allocated once and reused
through `Bytes` clones.

The corrected-input run (`benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/analysis.md`)
passed 24/24 response checks and recorded the method, body length, and
`Content-Length` choice per workload. It used 0.2-second exploratory samples;
16/24 rows passed the per-sample host guard and the analyzer formed one H3
uvloop pair, but the fresh host preflight had rejected and the wrapper marks
performance evidence not proven. Do not use that short run's ratio as a
performance result. Historical rows using a one-byte GET body belong to a
different workload identity.

## Full FastAPI matrix with qualified timing rows (2026-10-10)

The complete matrix and focused retries (`benchmarks/results/2026-10-10/fastapi-current-matched-matrix-20261010/README.md`)
use stock FastAPI 0.142.4 on CPython 3.12.13, macOS 15.7.7 arm64 / Apple M3
Pro, with Rust 1.98.1 and one Tokio async worker. Uvicorn 0.54.0 is the HTTP/1.1,
WebSocket, and lifecycle reference; Hypercorn 0.18.0 is the HTTP/2 and HTTP/3
reference. The same 243-case public parity gate passed. The five-category run
passed 390/390 correctness rows, then protocol-focused retries passed another
420 rows. Qualified results include a 0.845× Uvicorn-matched fixed HTTP/1
route, near-parity WebSocket binary echo with higher Rust server CPU per
message, large HTTP/2 upload gains against Hypercorn, and large/chunked HTTP/3
response gains at concurrency 1. These are separate workload results, not a
single server speed ratio.

The hosted run #13 parity follow-up (`benchmarks/results/2026-10-10/hosted-parity-13-disconnect/README.md`)
completed with one HTTP/1.1 pre-receive disconnect mismatch on commit
`72dfa51`; that revision predates the post-close test barrier. A later attached
preparation archive preserved the exact row: Uvicorn returned
`http.disconnect`, while uvicorn-rs returned `http.request` followed by
`http.disconnect`. The old fixture's fixed 50 ms wait did not synchronize its
first `receive()` with the driver's 250 ms post-close delay. With the fixture
waiting on the driver's release marker, the corrected dirty local test input
passed one focused invocation and 10 repeats with matching observations. This
is local input synchronization evidence, not a hosted rerun or a production
behavior fix. The current host guard rejected timing because unrelated system
load exceeded its CPU threshold, so no benchmark was started. The two earlier
local full-suite attempts still each had one unrelated TLS infrastructure
failure; no new full-suite pass is claimed. See the archived-row review and
repeat evidence (`benchmarks/results/2026-10-12/http1-disconnect-before-first-receive-repro/README.md`).

The follow-up per-thread CPU report (`benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md`)
adds guarded CPU splits for 15 H1 FastAPI workload variants. The
protocol-stage report (`benchmarks/results/2026-10-10/fastapi-current-protocol-stages-20261010/README.md`)
adds 320 response-checked diagnostic captures across H2, H3, and WebSockets.
Both reports separate clean repeated pairs from host-rejected rows and keep
instrumented timing out of normal performance rankings.

The macOS native-stack report (`benchmarks/results/2026-10-10/fastapi-current-macos-native-stacks-20261010/README.md`)
adds 10 response-checked stack samples for fixed, large-response, chunked,
1 MiB upload, and Python-CPU FastAPI workloads on Uvicorn and uvicorn-rs under
uvloop. It shows Rust frames in the ASGI send/receive bridge, header extraction,
body-chunk queues, and Tokio notification paths. These are qualitative stack
samples, not function-level CPU shares; all sampled timings are invalid, and
the profile uses the dirty local source recorded in its report.

### Where the extra cost appears

The table uses the measured dirty source snapshot (`src/lib.rs` SHA-256
`1f222c06c5ecfa4f1c3b22299259ddb69f5d39822427e50c4a9f8b4eebf8f455`) and the
normal extension used by the matrix. At capture time, committed `HEAD`
`e8148e4e` had `src/lib.rs` SHA-256
`56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; the
working-tree hash above is different. These measurements therefore describe
the dirty candidate, not commit-level or release performance. The candidate
contains the 256 KiB / 1 ms request-body batching path and segmented-body
materialization. HTTP/1.1, WebSocket, and lifecycle use Uvicorn; HTTP/2 and
HTTP/3 use Hypercorn because Uvicorn has no HTTP/2 or HTTP/3 server. All
applications are ordinary FastAPI with its standard Starlette and Pydantic
stack.

| Workload | Matched measurement | What it identifies |
|---|---|---|
| HTTP/1 small fixed route, concurrency 64, asyncio | Uvicorn 25,189 vs uvicorn-rs 19,222 req/s; server CPU 39.6 vs 59.0 µs/request; p50 2.521 vs 3.375 ms | The Rust server adds about 19 µs of process CPU per request. Three clean asyncio CPU-profile pairs show Python-loop CPU near parity (38.9 vs 37.9 µs) and about 19 µs on Tokio-named threads. The separate uvloop profile has two clean pairs and the same shape (34.4 vs 28.3 µs on the Python loop; 16.9 µs Tokio). In the closed-loop client, the rate loss grows into an 854 µs p50 gap as requests queue. |
| HTTP/1 1 MiB upload | In a separate instrumented diagnostic, p50 time inside `receive()` was 21.334 vs 12.997 ms; Rust used 5.701 receive bridge futures and delivered about six Python `bytes` messages. Conversion took 73 µs/request, including allocation. | The latency gap follows request-body delivery and Rust/Python future scheduling. The app spent only 0.117 vs 0.061 ms outside awaited ASGI I/O. The expanded CPU diagnostic has three clean asyncio pairs (281.6 vs 608.6 µs total process CPU/op, including 418.5 µs on Tokio-named threads) and five uvloop pairs (275.5 vs 544.0 µs/op, including 373.2 µs on Tokio). This CPU capture is separate from rankable throughput/latency; the conversion timer is not pure memcpy CPU. |
| HTTP/1 256-chunk response | Uvicorn 1,391 vs uvicorn-rs 1,399 req/s; server CPU 717 vs 1,069 µs/request; p50 45.77 vs 46.57 ms | Throughput is at parity while Rust uses more CPU. A separate diagnostic counted 257 ASGI body messages, 15.77 full-queue waits, and 38.86 ms accumulated response-send wait per request. This points to per-message bridge work and bounded-queue backpressure. |
| WebSocket | Handshake rate was 2,965 vs 5,463/s. For 64 KiB echo, rates were 22,634 vs 22,934 messages/s under asyncio and 27,637 vs 29,160 under uvloop, with higher Rust CPU/message. A 32-byte text-echo attempt on the recorded source passed all 20 correctness checks, but all 20 timings failed the host-activity guard. | Handshake setup is faster in Rust; large echo rate is near parity but CPU is higher. Small-frame rate and per-frame CPU remain unqualified. |
| HTTP/2 and HTTP/3 | HTTP/2 small-chunk upload and HTTP/3 large/chunked responses beat Hypercorn on the qualifying workloads. HTTP/2 many-chunk responses were 1.21–1.54× faster but used more server CPU. The two qualifying HTTP/3 response comparisons ran at concurrency 1. | These are protocol-specific comparisons against Hypercorn, not Uvicorn. They show that the Rust implementation is not slower across the board; HTTP/2 response chunking still has a CPU cost even when its throughput is higher. |
| Lifespan | Startup medians were 151.5 ms for Uvicorn and 144.4 ms for Rust; idle SIGTERM exit was 199.2 vs 22.6 ms; active graceful exit was 2,190.6 vs 2,027.6 ms. | Lifecycle is not the source of the steady-state request slowdown in these measurements. |

An expanded exact-source per-thread profile captured 300 repetitions across
15 HTTP/1 FastAPI workloads, four server/loop variants, and five repetitions.
Every response check passed; 193 captures passed the host and identity guard.
The paired CPU splits cover fixed and validated routes, Python CPU, large and
chunked responses, uploads at multiple client write sizes, slow readers,
headers, and context variables. See the full thread-CPU report (`benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md`).
An earlier 228-row attempt had no timing rows pass the guard and remains in the
causal-profile archive (`benchmarks/results/2026-10-10/fastapi-causal-profiling-20261010/attempts.md`);
the later clean pairs supersede it for per-thread attribution. The complete
11-workload thread profile on source `6b164eb…` remains a separate source
snapshot and is not pooled with this matrix.

The focused text-echo attempt (`benchmarks/results/2026-10-10/fastapi-current-ws-text-echo-20261010/README.md`)
used 32-byte messages with asyncio and uvloop. All 20 rows passed payload
correctness; zero timing rows qualified because of unrelated host CPU activity.
The raw result and row artifacts are retained, but this attempt adds no
throughput, latency, or CPU claim.

A fresh identity-bound retry on the same dirty source first reran the complete
public parity gate: the first attempt had one infrastructure-only Uvicorn
TLS-WebSocket handshake timeout, while the preserved second attempt passed
243/243 cases. The normal-build H1 retry (`benchmarks/results/2026-10-10/fastapi-h1-targeted-rerun-20261010/analysis.md`)
then passed correctness on all 80 rows covering fixed requests, 1 MiB uploads
with 16 KiB client writes, and small chunked responses. The separate
WebSocket text retry (`benchmarks/results/2026-10-10/fastapi-ws-text-echo-rerun-20261010/analysis.md`)
passed all 20 message checks. A later focused fixed-route retry (`benchmarks/results/2026-10-10/fastapi-h1-fixed-retry-hostwindow-20261010/analysis.md`)
passed another 20 correctness rows. All 120 timing rows were rejected by the
existing host-activity guard because of unrelated CPU activity, including the
Android emulator; source, native, and client identities stayed stable. These
retries add correctness and rejection evidence only, with no throughput,
latency, or CPU claim.

A fresh identity-bound 1 MiB upload retry (`benchmarks/results/2026-10-10/fastapi-current-upload-host-retry-20261010/http1-upload/analysis.md`)
then passed its source-matched parity gate (243/243) and all 20 upload response
checks. The source and normal extension matched the matrix identities, but all
20 timing rows were rejected for unrelated host CPU activity. The full
parity receipt (`benchmarks/results/2026-10-10/fastapi-current-upload-host-retry-20261010/parity.json`),
raw rows, process logs, and identity are retained. This attempt adds no
throughput or latency result and is not pooled with earlier measurements.

The measured hot paths are ASGI bridge calls, scheduling, body materialization,
and bounded-queue waits. The sampled native stacks identify relevant functions
but do not provide exact function-level CPU shares. No SIMD bottleneck has been
identified.

The source-confirmed adapter-boundary copy ledger documents an asymmetric
boundary: immutable Python `bytes` sent in HTTP response bodies or WebSocket
binary messages are retained by PyO3's `Bytes` conversion without copying the
payload; network request bodies and inbound WebSocket frames still need to be
copied into Python-owned `bytes` objects. This does not count copies inside the
protocol, TLS, allocator, kernel, or framework paths. See the copy ledger (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/copy-time-runtime-diagnostics-retry2-20261010/README.md#confirmed-adapter-boundary-copy-ledger`).

The checkout was dirty and a Rust build overlapped the deeper eight-repeat
HTTP/1 retry. Consequently, 143/192 timings in that retry were host-invalid,
including the Python-CPU and request-upload pairs; they have no speed claim.
The report retains every excluded row, raw result, parity receipt, and exact
source/native identity. No release-performance claim follows from this local
run. A later short fixed-route concurrency sweep at 1, 8, 32, and 64 matched
both asyncio and uvloop against Uvicorn. Its host-valid rows show a stable
roughly 18–22 µs/request CPU premium under asyncio, with the latency gap growing
as concurrency increases. Same-source per-thread profiles put about 20
µs/request of fixed-route CPU on Tokio-named threads and about 419 µs/request
there for 1 MiB uploads; exact function-level upload attribution remains open.

A feature-gated follow-up on the matrix source measured 5.701 receive bridge
futures and about six ASGI body messages per 1 MiB upload, with 73 µs wall time
for the complete Rust-to-Python `bytes` materialization path. Diagnostic p50
`receive()` wait was 21.334 ms for uvicorn-rs and 12.997 ms for Uvicorn. For a
256-chunk response, Rust recorded 15.77 bounded-queue full waits and 38.86 ms
of accumulated send wait per request. These instrumented timings are not
normal-build rankings; the conversion timer includes allocation and is not a
pure copy or CPU-share measurement. See the bridge diagnostic receipt (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/copy-time-runtime-diagnostics-retry2-20261010/README.md`).

## Previous focused diagnosis on an earlier source snapshot

This page reports only upstream FastAPI on its normal Starlette and Pydantic
dependencies. No FastAPI-RS or Starlette-RS app or runtime was used. Results
are local, source-bound evidence from one Apple M3 Pro; they are not a
cross-platform release claim.

The 2026-10-10 focused diagnosis (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/README.md`)
uses the earlier `6b164eb…` source. Its qualified request-upload, response-
streaming, WebSocket echo, HTTP/2, lifecycle, H3 chunked-response, and
slow-reader measurements show near parity on the Python CPU route, extra Rust
CPU on small HTTP and WebSocket work, roughly 2× CPU for 1 MiB HTTP/1.1
uploads, and near-equal throttled slow-reader throughput. Its three-pair
per-thread profile covers all 11 H1 FastAPI workload types. These are
source-specific results and are not pooled with the `1f222c0…` matrix above.
See the full H1 CPU split (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/README.md#per-thread-cpu-across-all-http1-fastapi-workloads`).

A later same-source experiment changed only the request-body batch limit from
256 KiB to 1 MiB for a 1 MiB upload written in 16 KiB chunks. The 256 KiB
baseline reached three shared clean pairs; the candidate did not reach the
three-pair gate because unrelated host CPU activity invalidated most attempts.
Two isolated candidate pairs suggest modest CPU savings but higher sampled RSS
and worse tail latency, while throughput remained about one-third below
Uvicorn. The candidate was reverted. See the threshold A/B receipt (`benchmarks/results/2026-10-10/fastapi-upload-threshold-ab-20261010/README.md`)
for exact source/build hashes and every accepted and rejected run.

The recorded dirty working-tree source (`src/lib.rs` SHA-256
`6b164eb7333b9e20f30feaa94f23f32059d02ebd7852527318260d652e510a79`) passed
243/243 normal-build public parity cases. Its unified matrix passed 506/506
cases in three runs, with Coverage-MCP measuring 5,518/5,518 regions and
3,960/3,960 lines. The coverage report (`benchmarks/results/2026-10-10/unified-coverage-current-send-mode-20261010/coverage-report.json`)
is local evidence for this dirty source, not hosted candidate CI.

For the exact dirty `6b164eb…` source, three same-numbered fixed-route CPU
profile repetitions passed the host and identity guards on both servers. Their
matched medians were 34.1 µs/request for Uvicorn and 45.3 for uvicorn-rs. Four
same-numbered 1 MiB-upload repetitions passed on both servers, with matched
medians of 274.8 versus 547.5 µs/request. uvicorn-rs used less CPU on its
Python event-loop thread in both cases; the extra appeared on Tokio-named
threads. In the upload profiles, that split was 173.3 µs on Python plus 374.2
µs on Tokio-named threads. Details and the profiling-only ASGI timing captures are in the
focused diagnosis (`benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/README.md`).
The first all-H1 profile attempts overlapped an unrelated Rust build and were
rejected by the host guard. The final retry provides three clean matched CPU
profiles for every H1 workload; earlier rejected rows remain in the
causal-profile archive (`benchmarks/results/2026-10-10/fastapi-causal-profiling-20261010/attempts.md`).

## Full-category report (2026-10-10, earlier source snapshot)

The full report (`benchmarks/results/2026-10-10/fastapi-final-506/README.md`)
compares the same FastAPI app, Python version, dependencies, event-loop choices,
and host across uvicorn-rs, Uvicorn, and Hypercorn where the protocol matches.
It records Rust `src/lib.rs` SHA-256
`b5c1140587a5998e0ef835e7fa935a1177771b8dcbb9e0c0d4681a664f99fd22`. The
later focused report above uses the dirty working-tree source hash
`6b164eb7333b9e20f30feaa94f23f32059d02ebd7852527318260d652e510a79`; do not
combine their rows as one exact-source run. The Rust runtime uses one Tokio
async worker. Only host-clean matched repetitions count in the ratios below;
the raw report retains host-contended and otherwise invalid samples with their
exclusion reasons.

| Workload | Reference | Rust/reference throughput | p50 reference → Rust | Server CPU reference → Rust |
|---|---|---:|---:|---:|
| H1 fixed route / uvloop | Uvicorn | 0.835× | 2.167 → 2.663 ms | 34.2 → 46.5 µs/op |
| H1 validated FastAPI route / uvloop | Uvicorn | 0.941× | 3.846 → 4.169 ms | 60.4 → 70.9 µs/op |
| H1 Python CPU route / uvloop | Uvicorn | 1.007× | 57.257 → 60.341 ms | 913.3 → 922.8 µs/op |
| H1 1 MiB upload / asyncio | Uvicorn | 0.622× | 17.704 → 28.400 ms | 282.5 → 617.9 µs/op |
| H1 1 MiB upload / uvloop | Uvicorn | 0.684× | 16.959 → 25.784 ms | 275.4 → 547.6 µs/op |
| H2 1 MiB upload / asyncio | Hypercorn | 5.006× | 252.516 → 50.512 ms | 3,901.4 → 1,040.2 µs/op |
| H2 1 MiB response / uvloop | Hypercorn | 7.719× | 257.278 → 33.100 ms | 4,005.2 → 573.2 µs/op |
| H3 fixed response / asyncio, concurrency 1 | Hypercorn | 4.381× | 0.483 → 0.109 ms | 353.9 → 83.5 µs/op |
| H3 large response / uvloop, concurrency 1 | Hypercorn | 19.986× | 54.982 → 2.763 ms | 23,911.7 → 2,736.3 µs/op |
| H3 slow-reader backpressure / uvloop, concurrency 1 | Hypercorn | 0.997× | 251.6 → 251.9 ms | 29,748.6 → 9,097.4 µs/op |
| WebSocket text echo / asyncio | Uvicorn | 0.596× | 1.138 → 1.899 ms | 17.8 → 48.8 µs/op |
| WebSocket text echo / uvloop | Uvicorn | 0.728× | 0.972 → 1.346 ms | 15.2 → 32.4 µs/op |
| WebSocket 64 KiB binary echo / uvloop | Uvicorn | 1.068× | 2.333 → 2.265 ms | 36.5 → 46.4 µs/op |

For this `b5c1140` source snapshot, the full-category H3 attempt did not qualify
at concurrency 8 or 64 because Hypercorn timed out. A separate low-load retry
qualified seven H3 workload/loop pairs at concurrency 1; it found
large-response and chunked-response gains, while slow-reader throughput was
equal. Those H3 rows do not establish the later `6b164eb` working-tree source:
its focused report qualifies only the chunked-response workload at concurrency
1. H3 uploads and protocol-scope workloads remain unqualified. Lifecycle also
gained enough clean evidence in a
20-repetition follow-up: 14 matched asyncio repetitions and 9 uvloop
repetitions. Startup measured about 136–138 ms for Rust versus 154–156 ms for
Uvicorn; idle exit measured about 23 ms versus 195 ms, while held graceful exit
was about 2.03 s versus 2.20 s. These are local lifecycle boundaries, not
request throughput. The detailed report includes p50/p95/p99, RSS, all category
correctness and timing counts, raw receipts, stage diagnostics, and CPU
attribution limits. Results are per workload and must not be combined across
protocols into one speed ratio.

For the earlier `b5c1140…` source snapshot, the stage trace localized its H1
upload gap to request-body delivery and the Rust/Python receive bridge: that
version spent more time in `receive()` and more process CPU there, while the
handler and `send()` stages were not slower in the instrumented trace. Its
small WebSocket echo gap was consistent with fixed per-frame bridge/scheduling
cost. The separate 360-profile H1 CPU sweep and its 1.15–2.13× ratios also use
that `b5c1140…` source, as recorded by the profile README; they are historical
evidence and must not be merged with the dirty `6b164eb…` results. The full
HTTP/1 thread-CPU analysis (`benchmarks/results/2026-10-10/fastapi-final-506/current-source-diagnostics/all-http1-thread-cpu-20261010-aggregate.md`)
contains the accepted and excluded receipts for that older source.

For the 2026-10-10 benchmark source snapshot at dirty revision `6b164eb…`, the
profiling-only ASGI capture puts about 9.23 ms of the 1 MiB upload's p50 latency difference inside awaited
`receive()` calls, close to the 8.96 ms normal-build end-to-end p50 gap. The
same source's clean CPU profiles show about 374 µs/request on Tokio-named
threads, offset by about 102 µs less Python event-loop CPU than Uvicorn. Sampled
stacks include the PyO3 future bridge, Tokio `spawn_blocking` tasks,
`call_soon_threadsafe`, and memory movement, but stack samples are not
function-level CPU shares. No SIMD bottleneck was identified. The focused
report records exact profiles, source identity, and measurement limits.

## Previous five-category run (2026-10-09)

The full report (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/README.md`)
measured the same FastAPI 0.142.4 app on CPython 3.12.13, macOS 15.7.7 arm64,
with Rust 1.98.1 and one configured Tokio async worker. Uvicorn 0.54.0 with
httptools 0.8.0 is the H1, WebSocket, and lifespan reference. Hypercorn 0.18.0
is the H2 and H3 reference. Both asyncio and uvloop owned the Python ASGI app
loop. The run used five repetitions, five seconds per sample, one second of
warmup, and concurrency 64. Source and normal extension hashes stayed stable.

| Category | Reference | Correct rows | Qualified pairs | Result |
|---|---|---:|---:|---|
| HTTP/1.1 | Uvicorn | 300/300 | 12 | Mixed; common routes and large responses regress, Python CPU route is near parity |
| HTTP/2 | Hypercorn | 140/140 | 14 | Fixed and large responses are faster; small-chunk uploads regress |
| HTTP/3 | Hypercorn | 2/130 planned | 0 | The concurrency-64 reference timed out; no pair qualifies |
| WebSockets | Uvicorn | 60/60 | 5 | Handshakes are faster; text echo is slower |
| Lifespan/shutdown | Uvicorn | 20/20 | 1 | One workload/loop pair; insufficient for a category conclusion |

The four completed categories passed 520 correctness rows. The H3 failure was
64 response-header timeouts in the Hypercorn/uvloop reference during
`protocol-scope-consumed-request`; the two Rust rows are not a comparison.
An earlier run of the same Rust source and native extension measured H3 at
concurrency 1 against Hypercorn and qualified 10 workload/loop pairs. Its
per-workload analysis (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/http3-concurrency1/analysis.md`)
is separate evidence and does not establish high-concurrency H3 performance.

Representative matched results follow. Throughput is Rust/reference; latency
is the median of per-run p50 values; CPU is server process-tree microseconds
per operation. The complete analysis (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/analysis.md`)
contains every qualified workload's p50/p95/p99, server/client CPU, sampled
RSS, invalid rows, and comparison exclusions.

| Workload and loop | Throughput ratio | p50 reference → Rust | Server CPU reference → Rust |
|---|---:|---:|---:|
| H1 validated FastAPI route / asyncio | 0.908× | 4.381 → 4.928 ms | 68.5 → 83.2 µs/op |
| H1 large response / asyncio | 0.874× | 6.411 → 7.920 ms | 100.6 → 130.4 µs/op |
| H1 1 MiB upload, 1 KiB client writes / asyncio | 1.084× | 197.8 → 187.5 ms | 990.7 → 1,705.2 µs/op |
| H1 Python CPU route / asyncio | 1.043× | 59.708 → 60.416 ms | 955.9 → 934.8 µs/op |
| H2 fixed response / asyncio | 3.720× | 9.135 → 2.606 ms | 147.5 → 48.2 µs/op |
| H2 large response / asyncio | 8.077× | 264.3 → 32.572 ms | 4,122.3 → 574.1 µs/op |
| H2 small-chunk upload / asyncio | 0.548× | 53.090 → 100.8 ms | 860.6 → 2,613.3 µs/op |
| WebSocket handshake / asyncio | 2.151× | 0.420 → 0.189 ms | 281.1 → 152.3 µs/op |
| WebSocket text echo / asyncio | 0.591× | 1.108 → 1.863 ms | 17.3 → 48.1 µs/op |

These ratios are per workload and reference. Do not combine H1, H2, H3, or
WebSocket results into one overall speed number. The deliberate 1 KiB-write
upload above differs from the default 1 MiB upload workload: a separate
qualified same-source run measured that default case at 0.458× Uvicorn
throughput, with 2.33× p50 latency and 3.4× server CPU per operation. The
same-source diagnosis (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md`)
explains the upload workload difference and keeps its raw rows.

A new matched 1 MiB upload write-size sweep (`benchmarks/results/2026-10-09/fastapi-upload-granularity-current/README.md`)
tested 1 KiB through 1 MiB client writes on both servers with uvloop. For
16 KiB–1 MiB writes, uvicorn-rs stayed near 0.53× Uvicorn throughput and used
2.94–3.05× server CPU per request, regardless of client write size. The
diagnostic pass found 18 ASGI receive messages and 17.9 receive bridge futures
per Rust request versus five Uvicorn receive messages, with one payload's
worth of bytes copied into Python `bytes`. The 1 KiB-write run was limited by
the client and showed near-equal throughput despite higher Rust server CPU.

A receive-loop task-locals reuse experiment passed the 240-case public ASGI
matrix but did not show a material, repeatable upload gain; it was reverted.
The default 1 MiB upload measured 0.533× Uvicorn in five candidate pairs
versus 0.516× in an earlier three-pair baseline, with less than 1% lower Rust
CPU across separate measurement windows. See the
candidate report (`benchmarks/results/2026-10-09/fastapi-receive-locals-reuse-candidate/README.md`)
for latency, CPU, exclusions, and raw receipts.

## Where the additional time appears

This section is historical diagnostic evidence for committed source
`e8148e4` (`src/lib.rs` SHA-256
`56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`). It
predates the dirty `6b164eb…` source measured in the focused 2026-10-10 report;
do not combine the following stage counters, thread counts, or CPU values with
that report.

The FastAPI server cost breakdown (`benchmarks/results/2026-10-09/fastapi-stage-breakdown-current/README.md`)
combines the exact-source H1 counters, new HTTP/2 and WebSocket stage profiles,
repeated paired normal-build Python CPU-route samples, and signal-gated CPU
counters for the Python event-loop thread and whole process. It separates
normal-build results from instrumented-only timings and records why exact
Rust/PyO3 on-CPU function shares remain unmeasured on this Mac.

The normal matrix shows higher server CPU per request on several H1 workloads
and WebSocket echo. A Python CPU-bound route stays near parity in throughput
and server CPU, so that route's Python handler work does not explain the
broader H1 overhead. The upload measurements point to receive and bridge work.

Three alternating normal-build stack captures of the same Python CPU route
found a Rust Tokio worker in `PyGILState_Ensure` followed by a condition wait
in 80.7–83.6% of that worker's sampled wall-time ticks. This is a GIL wait
signal, not a CPU share. The repeated profiles and their limits are in the
stage report (`benchmarks/results/2026-10-09/fastapi-stage-breakdown-current/README.md`);
the matched CPU-route benchmark itself remains near parity.

The exact-source instrumented probe checked 48 runs of fixed route, validated
route, 1 MiB upload, and 256-chunk response workloads across Uvicorn and
uvicorn-rs with asyncio and uvloop. All responses were checked, but diagnostic
timings are excluded from performance ratios. Its counters locate two strong
cost signals:

1. **Request-body delivery crosses into Python repeatedly.** Rust produced
   about 18 `http.request` messages and 17.8 receive-bridge futures for a
   1 MiB request; Uvicorn produced five messages. Rust copied approximately
   one payload's worth into Python `bytes`, split across those messages. The
   extra cost is per-message PyO3 future completion, Python attachment, GIL
   acquisition, and event-loop scheduling—not 18 full-body copies.
2. **Chunked responses wait in the bounded Rust body queue.** At 256 chunks,
   the queue filled about 15.8 times per response and accumulated roughly
   40–48 ms of queue-send wait. TCP write-pending wait was negligible for a
   fast reader, so that observed wait is before socket writes. The deliberately
   slow-reader case exercises both queue and TCP backpressure.

The H2 profile narrows its small-upload regression to `receive()` awaits:
Rust took 108 ms at p50 versus Hypercorn's 56.5 ms with nearly equal counts of
body messages, and Rust created 62.8 receive bridge futures per request. Its
chunked response profile shows 242.5 ms of queue-send wait per response; Rust
still completed that normal workload faster than Hypercorn. The WebSocket
profile shows one Rust receive bridge future per small echo frame, while the
normal 32-byte echo workload used 2.8× the server CPU per message and delivered
0.591× the throughput of Uvicorn. A 64 KiB frame reached near-throughput parity.
Those cross-protocol details are in the stage report (`benchmarks/results/2026-10-09/fastapi-stage-breakdown-current/README.md`).

The new thread-level CPU attribution (`benchmarks/results/2026-10-09/fastapi-thread-cpu-attribution/README.md`)
measured four ordinary FastAPI H1 workloads with three short captures per
server and event loop. The synchronous Python CPU endpoint itself used about
810 µs/call on Uvicorn and 772–783 µs/call on uvicorn-rs; whole-process CPU
was near parity for that route. On the 1 MiB upload, Rust used less CPU on its
Python event-loop thread but about 582–741 µs/request more across the process.
That aligns with the receive/bridge evidence, although the process residual
includes all non-loop threads and does not identify a Rust function. The 48
responses passed checks, but only 12 passed the host/identity timing guard, so
these captures are diagnostic evidence rather than rankable benchmarks.

A Mach thread snapshot for the recorded source (`benchmarks/results/2026-10-09/fastapi-thread-cpu-mach-current-source-run2/README.md`)
then repeated the validated route and 1 MiB upload with Uvicorn and uvicorn-rs
both using uvloop. All 12 response checks passed and 11/12 captures passed the
host/identity guard. On the upload, the guard-clean medians were 276.6 µs of
process CPU per request for Uvicorn and 817.5 µs for uvicorn-rs, or 92.2% and
150.5% of one logical core during the measured intervals. Rust's Python
event-loop thread used 253.1 µs; Tokio-named threads used another 562.8 µs,
with 22–23 such threads visible. On the validated route the Rust event-loop
thread used less CPU, while the process still used about 9.6 µs more per
request. The Mach per-thread sum reconciled with process CPU within 0.002%.
These are CPU-attribution diagnostics, not throughput or latency rankings.

A repeat set of 12 Apple `sample` captures now includes validated routes,
1 MiB uploads, and 256-chunk responses under asyncio and uvloop. Every sample
passed exact response checks. The Rust app's inner FastAPI timing stayed near
the Uvicorn app timing on validated routes; upload `receive()` p50 was about
2.1–2.5× higher, while chunked-response `send()` p50 exposed bounded body-queue
wait. During upload profiles, the Rust process exposed 22–24 threads named
`tokio-rt-worker` despite one configured Tokio async worker. These are
diagnostic stack and wait measurements, not per-function CPU shares. See the
native stack attribution report (`benchmarks/results/2026-10-09/fastapi-native-stack-attribution-run2/README.md`)
for the per-loop measurements and interpretation.

The focused H1 diagnostic receipt (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio/README.md`)
and new H2/WebSocket diagnostic receipts contain raw Rust counters and ASGI
timings. Signal-gated thread counters add attribution at the event-loop-thread
and process levels, and the Mach snapshots add per-OS-thread CPU totals. They
still do not attribute on-CPU time to individual Rust or Python functions.
The available Apple `sample` profiles include waiting threads; exact function
shares and comparable total allocation counts remain unmeasured. No SIMD
hotspot has been identified. The one Tokio async worker is not a one-thread
process: Python owns a separate event loop, and the PyO3 completion path uses
Tokio's blocking pool.

The current host has only Apple Command Line Tools; `xcrun xctrace` is
unavailable, and DTrace cannot initialize with SIP and privilege restrictions.
The write-size sweep therefore closes the request-boundary and byte-counter
questions for H1 uploads, but native function-level on-CPU attribution still
requires a profiling-capable host.

## Evidence and limits

- The machine-readable category rows (`benchmarks/results/2026-10-09/fastapi-exact-f260-one-tokio-retry1/full-matrix-retry2/`)
  preserve matched repetitions and exclusions; the [methodology](benchmarks.md)
  describes the validity gates and resource accounting.
- The normal extension passed 239/239 public cases before the full-category
  run. The same extension hash subsequently passed the expanded 240/240
  normal-wheel parity matrix in the coverage evidence archive (`benchmarks/results/2026-10-09/asgi-unified-coverage-494/`).
- The checkout was dirty, host-contended rows were retained and excluded, and
  H3 did not finish at concurrency 64. The automated three-system benchmark
  also failed before producing a validated aggregate; see
  [latest run status](benchmark-status.md).
- Three valid matched repetitions are a descriptive gate, not a statistical
  significance test. The closed-loop, same-host load does not correct for
  coordinated omission. RSS is sampled process-tree RSS, not PSS or allocator
  peak.

The project has no broad performance-replacement claim. Continue performance
work only against a measured workload-specific bottleneck and require normal
parity plus repeatable end-to-end improvement before accepting an optimization.
