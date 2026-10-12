# Benchmark and release-gate status

## Latest local benchmark preparation (2026-10-13)

The exact normal build passed **243/243** parity cases at commit
`957143ab5f810be861183bde0c239d558f78fefb`. The measured source
(`src/lib.rs` SHA-256
`ea149b5821a398f62c5a7762a83774040ae15ae0b268c28d921e4c61f3e54f47`),
normal extension (`8e7a060c5bdd9e1bd5d1c4d5bbcd5136de739208f7eccdbbd80963f235dcc64f`),
benchmark scripts, and lockfiles are unchanged in the current checkout. This
receipt applies to the same code inputs; it is not a clean commit-bound run of
the current documentation and ignore-rule commits.

The post-parity host preflight rejected three windows before timing began.
Unrelated CPU measured 128.7–245.2%, 238.9–268.8%, and 214.7–243.3% across
the three receipts. No timed rows were produced and no processes were stopped.
The receipts are in the local-only
`benchmarks/results/2026-10-13/kata-finish-20261013-1/` directory and are
excluded from Git.

The next benchmark work is limited to the underqualified matched pairs once a
host window passes preflight. The full parity suite does not need to be
repeated unless its code or input identity changes. This preparation
establishes no repeatable performance gain.

## Latest hosted ASGI matrix: run 38122909359

The hosted matrix ran on clean commit
[`9b2d8aaf`](https://github.com/appunni-m/uvicorn-rs/commit/9b2d8aaf321666eb365b1fa69d39029233d0ece0).
The aggregate job validated a **partial** matrix; each platform job stopped in
the sequential category step, so this run does not establish a complete
three-system performance result. Its FastAPI validated-route throughput was
below Uvicorn on all three systems: 0.676×/0.700× on Linux x86-64,
0.769×/0.936× on Linux ARM64, and 0.671×/0.683× on macOS ARM64 (asyncio /
uvloop). The [per-system report, archived raw evidence, and verified artifact
digests](../benchmarks/results/hosted/38122909359-attempt-1/README.md) record
the incomplete categories and failure receipts.

The docs updater pushed commit [`94f68885`](https://github.com/appunni-m/uvicorn-rs/commit/94f68885d3455383a806c606b53781fe7be7b7a2)
to `automation/benchmark-results`, then failed in the final “Propose the
updated results documentation” step (job
[`114433266672`](https://github.com/appunni-m/uvicorn-rs/actions/runs/38122909359/job/114433266672#step:5:76)).
The public run page requires sign-in to expose that step's log, so the exact
pull-request creation error remains unknown. The aggregate result and docs
step are separate outcomes.

The separately attached `asgi-category-benchmarks-macos-arm64 (1).zip` has
SHA-256 `92e2cd68d8afb38a367b6e789fc5143e6ff054b7cf7b3ab3298466692ee7091a`,
identical to the archived macOS artifact above. It adds no new benchmark
samples. Its HTTP/1 category stopped after 120/300 rows when a 1 KiB upload
case failed in the libcurl client; FastAPI then observed a client disconnect.
The analyzer withholds all H1 ratios because the category is incomplete. The
other categories produced 14 HTTP/2, 12 HTTP/3, 6 WebSocket, and 2 lifecycle
matched descriptive pairs. The [archive review and current H1 experiment
status](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/current-run-status.md)
records the failure boundary and the limits on interpreting these measurements.

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
and it is not a hosted rerun. See the [archived-row review and repeat
evidence](../benchmarks/results/2026-10-12/http1-disconnect-before-first-receive-repro/README.md).

The Tokio blocking-pool experiment passed 243/243 public parity cases with the
default, 1-thread, and 4-thread settings. Its first timing slice has one
qualified descriptive pair: default pool, stock FastAPI, 1 MiB request body,
64 KiB client callback cap, three host-valid repetitions per server. Uvicorn
handled 4,149 requests/s and Rust 3,840 (0.925×); Rust p50/p95/p99 and observed
server CPU were higher. The setting comparison is incomplete: cap 1 had no
qualified pairs, and cap 4 has not been timed. See the [full experiment
report](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/README.md).

Twelve earlier consecutive host preflights (receipts 5–16) rejected before
benchmark startup. The latest of those samples found
`mediaanalysisd` at 66.2–100.9% of one core, `qemu-system-aarch64-headless`
reached 28.7% in one interval, and aggregate unrelated CPU ranged from 94.8%
to 140.1%, with consecutive samples over the aggregate threshold. No process
was stopped. Subsequent short windows accepted for the default and cap-1 runs,
but the per-row guard still rejected noisy rows. Ten later cap-4 preflights
rejected; the [first](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-4-host-preflight.json)
and [latest](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-4-host-preflight-retry-9.json)
receipts show the aggregate and sustained-process guards. Three subsequent
focused cap-1 preflights rejected under the same guards; see the [latest
receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/cap-1-focused-preflight-retry-2.json).
Eighteen resumed preflights also rejected before timing: `mediaanalysisd` used
29.3–101.5% of one core, `qemu-system-aarch64-headless` reached 78.7%, and
aggregate unrelated CPU ranged from 56.2% to 279.6%. The latest sample found
`mediaanalysisd` at 29.3–96.1% and aggregate unrelated CPU at 56.2–115.2%.
No process was stopped.
See the [first](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-1.json)
and [latest](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/blocking-pool/resume-host-preflight-18.json)
receipts.
See the [current experiment
status](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/current-run-status.md).
The latest goal-continuation preflight also rejected before timing: unrelated
aggregate CPU ranged from 115.1% to 178.8%, a `python3.12` process used
94.6–100.6% of one core throughout all eight intervals, and
`qemu-system-aarch64-headless` reached 79.6% in one interval. The receipt
records process names and PIDs only; no benchmark started and no process was
stopped. See the [latest receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-goal-continuation-20261012.json).
The intended comparison isolates stock FastAPI 1 MiB uploads with 64 KiB and
256 KiB client writes against Uvicorn on the same asyncio loop. No performance
claim about pool-cap effects follows from this partial timing evidence.

A fresh standalone host preflight after the profile review rejected as well:
the process named `python3.12` used 85.3–104.3% of one core in all eight
intervals, and unrelated aggregate CPU ranged from 100.4% to 151.4%. The
receipt captures names and PIDs, not the process command. No timed benchmark
started in that rejected window and no process was stopped. Later short windows
accepted for default and cap 1, but the cap comparison remains incomplete. See
the [preflight receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-post-doc-audit.json).

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
[raw report and server logs](../benchmarks/results/2026-10-12/http2-client-shutdown-20261012/README.md)
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
[archived hosted evidence](../benchmarks/results/hosted/38122909359-attempt-1/README.md) records
the matrix boundary and artifact digest.

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
draw a performance conclusion. See the [attempt ledger and raw evidence](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/README.md).

### H1 benchmark-source route and fixed-response batch (2026-10-12)

A separate complete 40-row selected-subset run passed all response checks; 30
rows passed the timing guard and three workload/loop pairs qualified. The
validated FastAPI route measured 0.900× Uvicorn throughput under asyncio and
0.966× under uvloop. The fixed response measured 0.750× under asyncio; its
uvloop pair had only two valid repetitions. The qualified pairs used 9.0–20.1
µs more aggregate server-process CPU per operation. This does not isolate the
CPU between the Python event loop, PyO3 bridge, and Rust networking. The
[source-bound report and raw rows](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-route-fixed/README.md)
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
not attribute that CPU to a particular Python or Rust function. The [report
and raw evidence](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-response-workloads/README.md)
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
did not have enough matching valid repetitions. The [report and raw evidence](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-workloads/README.md)
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
the cause. See the [profile report](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/h1-upload-profile/README.md),
[preflight receipts](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-h1-rest.json),
and [retry](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-profile-next-2.json).
The latest host check also rejected before timing: `mediaanalysisd` remained at
63.2–87.9% of one core in all eight intervals, with unrelated aggregate CPU
peaking at 115.9%. A retry 30 seconds later also rejected, with aggregate
unrelated CPU peaking at 290.0% and `mediaanalysisd` remaining at 65.5–87.2% in
all intervals. See the [first receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-20261012.json)
and [retry](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry1-20261012.json).
A second retry rejected too: `mediaanalysisd` remained at 56.6–85.9% in all
intervals, and aggregate unrelated CPU peaked at 136.4%. See the [second retry
receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry2-20261012.json).
A third retry rejected as well: unrelated aggregate CPU peaked at 214.2%,
`mediaanalysisd` used 55.1–87.8%, and a `python3.12` process used 86.0–100.5%
in all intervals. No benchmark started and no process was stopped. See the
[third receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry3-20261012.json).
A fourth retry rejected 45 seconds later: `mediaanalysisd` remained at
51.6–98.4%, `rustc` at 94.0–103.5%, and aggregate unrelated CPU peaked at
220.1%. No benchmark started. See the [fourth receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry4-20261012.json).
A fifth preflight 60 seconds later rejected as well: `mediaanalysisd` used
70.8–75.5%, `rustc` used 94.3–101.5% in all intervals, and aggregate CPU
peaked at 211.9%. See the [fifth receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-after-archive-retry5-20261012.json).
A fresh preflight on continuation also rejected, with aggregate CPU peaking at
200.3%, `mediaanalysisd` at 50.6–80.4% in all intervals, and a `python3.12`
process at 95.8–97.1% in three intervals. No timing began. See the
[receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-1.json).
A second continuation preflight rejected too: aggregate CPU peaked at 227.1%,
`mediaanalysisd` used 46.8–73.5% in all intervals, `git` used 27.5–32.0% in
seven, and `rustc` briefly used 101.1%. See the [receipt](../benchmarks/results/2026-10-12/wh9k-focused-h1-20261012-1/host-preflight-continuation-20261012-2.json).

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

The [five-category analysis](../benchmarks/results/2026-10-11/fastapi-current-full-category-20261011-retry1/analysis.md)
and its raw rows keep each category and each host-rejected sample separate.
HTTP/1 completed all 300 planned rows with zero response failures, but only 20
passed the timing guard and **no H1 workload/loop pair qualified**. HTTP/2
stopped after 68/140 rows when uvicorn-rs could not bind its HTTP/3 endpoint
(`Address already in use`); all 68 collected rows had zero response failures.
HTTP/3 completed 130/130 rows (112 timing-valid, 10 qualified pairs), WebSocket
completed 60/60 (57 timing-valid, 6 pairs), and lifecycle completed 20/20 (14
timing-valid, 1 pair).

An [isolated HTTP/2 retry](../benchmarks/results/2026-10-11/fastapi-current-full-category-20261011-http2-retry1/analysis.md)
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
that no benchmark started: [first](../benchmarks/results/2026-10-11/fastapi-current-h1-focused-retry-20261011/host-preflight.json)
and [second](../benchmarks/results/2026-10-11/fastapi-current-h1-focused-retry-20261011-2/host-preflight.json).

The 2026-10-10 exact-source [FastAPI category matrix](../benchmarks/results/2026-10-10/fastapi-current-matched-matrix-20261010/README.md)
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
The [corrected-input smoke run](../benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/analysis.md)
passed 24/24 response checks. Its 0.2-second duration is exploratory; although
the analyzer formed one matched H3 uvloop pair, the fresh host preflight had
rejected and the run is not a performance result. Older rows that sent a
one-byte GET body are a different input identity. See the [HTTP/3 request-shape
details](benchmark-results.md#http3-request-shape-correction-2026-10-11).
Thirteen subsequent preflights rejected timed work for aggregate unrelated CPU
above 100% of one core and a process above the per-process threshold in
consecutive intervals. The [latest receipt](../benchmarks/results/2026-10-11/wh9k-after-native-core-20261011-1.json)
records no benchmark start. In preflight 13, unrelated CPU ranged from
49.4–122.2% of one core and `mediaanalysisd` used 28.1–102.7% across eight
intervals. Preflight 12 recorded 119.0–172.3% aggregate activity, with a Codex
renderer peaking at 39.0% and a Chrome helper at 63.0%. Earlier rejected
receipts remain available beside the benchmark results.

Follow-up diagnostics now cover all 15 HTTP/1 workload variants with thread
CPU counters and add 320 response-checked stage rows for HTTP/2, HTTP/3, and
WebSockets. See the [per-thread report](../benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md)
and [protocol-stage report](../benchmarks/results/2026-10-10/fastapi-current-protocol-stages-20261010/README.md).
The stage timings are diagnostic-only; the ordinary matched matrix remains
the throughput, latency, process CPU, and RSS evidence.

A 32-byte WebSocket text-echo attempt on the recorded benchmark source passed 20/20 payload
checks, but all 20 timing rows failed the host-activity guard. Its
[receipt](../benchmarks/results/2026-10-10/fastapi-current-ws-text-echo-20261010/README.md)
records the attempt without making a small-frame speed claim.

The exact-source per-thread CPU retry covers 15 HTTP/1 workloads, four
server/loop variants, and five repetitions: 300 response checks passed and
193 timing captures passed the host and identity guard. Its paired CPU split
shows the Python loop near or below Uvicorn on most routes, with additional
work on Tokio-named threads for fixed requests, uploads, and chunked output.
The [per-workload report](../benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md)
keeps lower-count pairs and host-rejected captures visible. An earlier 228-row
attempt had no timing captures pass the guard; it remains in the
[attempt receipts](../benchmarks/results/2026-10-10/fastapi-causal-profiling-20261010/attempts.md).

The [earlier focused diagnosis on source `6b164eb…`](../benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/README.md)
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

The [full five-category report](../benchmarks/results/2026-10-10/fastapi-final-506/README.md)
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
allocation/copy ledger remains open; see the [bridge and copy report](../benchmarks/results/2026-10-10/fastapi-current-one-tokio-20261010/copy-time-runtime-diagnostics-retry2-20261010/README.md).

A same-source request-body batch-threshold experiment compared the current
256 KiB default with a temporary 1 MiB threshold on FastAPI's 1 MiB upload.
The baseline reached three shared clean pairs; host contention left the
candidate below the three-pair gate. Its two isolated clean pairs suggest
small CPU savings alongside higher RSS and worse tail latency, but are not
enough to justify changing the default. The 256 KiB source and matching native
build are restored. See the [threshold experiment receipt](../benchmarks/results/2026-10-10/fastapi-upload-threshold-ab-20261010/README.md).

The dirty `6b164eb…` working tree passed 243/243 normal-build public parity
cases. The unified matrix passed 506/506 cases across three complete runs;
Coverage-MCP measured 5,518/5,518 regions and 3,960/3,960 lines. This does not
replace hosted exact-commit CI: run #50 on `e8148e4` has a WSS oracle timeout,
and the package and Python-floor jobs were skipped.

Two fresh local host preflights were rejected before timing. The latest
eight-interval sample found unrelated `rustc` at 96.9–100.8% and
`mediaanalysisd` at 74.8–95.8% of one core in every interval; aggregate
unrelated CPU was 187.1–214.1%. No benchmark process was started. The
[first receipt](../benchmarks/results/2026-10-10/fastapi-current-host-preflight-20261010/README.md)
and [follow-up receipt](../benchmarks/results/2026-10-10/fastapi-current-host-preflight-retry2-20261010/README.md)
retain the measurements and guard policy.

A third eight-interval sample at 14:35 UTC also rejected timing. Unrelated
aggregate CPU ranged from 116.6% to 251.4% of one core; `mediaanalysisd` was
over 25% in every interval, while `rustc` and the Codex renderer also exceeded
the guard in consecutive intervals. No benchmark process was started. See the
[third preflight receipt](../benchmarks/results/2026-10-10/fastapi-current-host-preflight-retry3-20261010/README.md).

The earlier 2026-10-09 full-category run used stock FastAPI, Starlette, and
Pydantic, with one configured Tokio worker. H1, H2, WebSocket, and lifecycle
completed 520 correctness rows and produced 32 workload/loop pairs with at
least three valid matched repetitions. H3 at concurrency 64 stopped on
Hypercorn reference timeouts and produced no valid pair. The newer low-load H3
follow-up is separate evidence and does not establish high-concurrency H3
performance.

The report [fastapi-thread-cpu-attribution](../benchmarks/results/2026-10-09/fastapi-thread-cpu-attribution/README.md)
adds 48 signal-gated CPU captures across four FastAPI H1 workloads, two event
loops, and both servers. Every response passed; 12/48 captures passed the
host/identity timing guard, so all CPU captures are diagnostic-only. A separate
direct timer measured the synchronous FastAPI CPU handler in 12 captures, all
with the guard passing. It found the Python handler near parity and the
largest extra process CPU on request-body receive paths. Exact native
function-level CPU shares and a complete allocation/copy ledger remain open.

The [committed `e8148e4` per-thread CPU run](../benchmarks/results/2026-10-09/fastapi-thread-cpu-mach-current-source-run2/README.md)
passed all 12 response checks and 11/12 host/identity guards. Its clean
1 MiB-upload rows attribute about 563 µs/request of uvicorn-rs CPU to
Tokio-named threads, with 22–23 runtime-named threads observed despite one
configured async worker. The Rust Python loop itself used slightly less CPU
than Uvicorn's. These measurements are for the committed source before the
later dirty `6b164eb…` capture and must not be merged with its 374 µs/thread
result. They remain diagnostic-only and do not identify hot functions.

The [committed `e8148e4` upload write-size sweep](../benchmarks/results/2026-10-09/fastapi-upload-granularity-current/README.md)
passed response checks and obtained three to five valid pairs per workload.
For 16 KiB–1 MiB client writes, uvicorn-rs delivered about half Uvicorn's
throughput and used about three times its server CPU. Separate receive-stage
counters showed 18 Rust ASGI body messages and 17.9 bridge futures per request
versus five Uvicorn receives, while Python-bytes copy volume stayed at one
payload. This strengthens the receive-bridge diagnosis; function-level CPU
shares remain open.

The [latest native stack captures](../benchmarks/results/2026-10-09/fastapi-native-stack-attribution-run2/README.md)
add 12 correctness-passing profiles of the same FastAPI routes across asyncio
and uvloop. They show upload time concentrated in `receive()` awaits, chunked
response time in bounded Rust `send()` waits, and multiple Tokio-named runtime
threads under load despite one async worker. These are diagnostic wall-time
samples, not CPU shares or rankable benchmark rows.

The local [494-case ASGI evidence archive](../benchmarks/results/2026-10-09/asgi-unified-coverage-494/)
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
[here](../benchmarks/results/2026-10-09/current-full-parity-recheck-240.json)
and [here](../benchmarks/results/2026-10-09/wss-oracle-exact-e8148e4-retry3/).

A separate 2026-10-10 follow-up repeated that WSS input eight times on the
current working tree: seven passed and one was classified as an oracle
infrastructure timeout. The failure occurred while a preflight sample showed
unrelated `mediaanalysisd` and `rustc` using about one CPU core each; three
later standard attempts and three debug attempts passed. This supports a
load-sensitive timeout as a possibility, not a proven root cause, and the
follow-up is not an exact source/build or hosted CI gate. See the
[WSS follow-up receipt](../benchmarks/results/2026-10-10/ci50-wss-oracle-followup-local-20261010/README.md).

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
receipts are in the [TLS-drain probe follow-up](../benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md).

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
are recorded in the [TLS-drain probe follow-up](../benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md).

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
[reproduction receipt](../benchmarks/results/2026-10-10/ci55-body-pump-fault-repro-a93-20261010/README.md).

Commit [`72dfa51`](https://github.com/appunni-m/uvicorn-rs/commit/72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f)
adds bounded case-specific annotations to the benchmark parity step and is
now pushed to `main`. CI #56 completed successfully on this exact commit: the
installed-wheel parity, unified coverage, package, Python-floor, Rust quality,
and MSRV gates passed. ASGI performance matrix #13 is still running on the same
commit. Its macOS ARM64 job failed exact parity at
`http1.disconnect-before-first-asgi-receive` before timing; its Linux x86-64 and
Linux ARM64 jobs passed parity and the FastAPI control, then entered sequential
category measurements. No three-system benchmark aggregate is available yet.
The [exact-commit local reproduction](../benchmarks/results/2026-10-10/ci13-disconnect-exact72-repro/README.md)
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
Its [analysis and raw evidence](../benchmarks/results/2026-10-11/fastapi-exact-443c5cc-local-evidence/README.md)
show 570/650 timing rows rejected for unrelated host CPU activity; only three
matched H1 pairs qualified. The 1 MiB upload measured 0.453× Uvicorn throughput
under asyncio and 0.544× under uvloop, while HTTP/2, HTTP/3, WebSocket, and
lifecycle had no qualified pairs. This local result confirms that host load
can prevent timing qualification but does not diagnose the hosted run #16
failure.

The latest local preflight, run 7, again rejected timing before starting a
benchmark: unrelated host CPU ranged from 101.0% to 156.7% of one core, and
`mediaanalysisd` used 74.4% to 100.5% in all eight intervals. See the
[preflight receipt](../benchmarks/results/2026-10-11/kata-continuation-host-preflight-7/host-preflight.json).

A fresh preflight after the HTTP/3 input correction also rejected timing before
starting a benchmark. Unrelated CPU reached 298.1% of one core; `homed` used
58.7% to 126.4% and `cloudd` used up to 76.4% across the rejected intervals.
The host guard rejected both aggregate and sustained per-process activity. See
the [preflight receipt](../benchmarks/results/2026-10-11/h3-corrected-current-host-preflight-20261011-1.json).

The earlier 78-row full H3 report is not validation of the corrected request
framing: its recorded source hashes for the H3 script and client were
`d3f11375` and `8e798372`, and its client binary hash was
`a6947902`. The current H3 script and client source hashes are `26567768` and
`34d464c5`, and the current binary hash is `c0ae1fce`. Exclude the earlier
report's zero-failure count from evidence for the correction; its [raw rows](../benchmarks/results/2026-10-11/fastapi-kata-continuation-http3-20261011/http3.json)
remain available for its original run identity.

The focused 24-row report matches the current H3 script, client source, and
binary identities. It covers `protocol-scope` and
`protocol-scope-consumed-request`, with zero request failures and 16/24
timing-valid rows. See its [raw report](../benchmarks/results/2026-10-11/fastapi-http-spec-correctness-20261011/http3.json).

The complete corrected H3 matrix subsequently finished with 130/130 planned
rows and zero request failures. Source, native-extension, and probe-binary
identities were stable before and after the run. The host guard accepted 69
timing rows and rejected 61 for unrelated host CPU activity. At least three
matched valid repetitions exist for `protocol-scope` and `fixed` under both
loops, `large-response` under both loops, and `protocol-scope-consumed-request`
under uvloop. The [run analysis](../benchmarks/results/2026-10-11/h3-rfc-input-corrected-repeat-20261011-1.artifacts/README.md)
reports their same-repetition throughput, latency, server CPU, and RSS ratios.
These are one local Mac run against Hypercorn, not a multi-system or repeated
release performance result. The chunked-response and slow-reader workloads
have no qualified pairs; H3 upload has no Hypercorn reference rows and no valid
Rust timing rows. The [raw report](../benchmarks/results/2026-10-11/h3-rfc-input-corrected-repeat-20261011-1.json),
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
sustained `mediaanalysisd` activity. See preflight [1](../benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-1.json),
[2](../benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-2.json),
[3](../benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-3.json),
and [4](../benchmarks/results/2026-10-11/after-h3-rfc-host-preflight-20261011-4.json).
No process was stopped and no benchmark measurement began during these
preflights.

## Release candidate

No release-candidate bundle is ready. CI run `38087300590` passed its eight
hosted gates on clean commit `16ed349`. The newer ASGI benchmark matrix
`38122909359` stopped in the sequential category step on all three systems, so
it produced no validated multi-system performance result. Its docs-update job
also failed in the final pull-request step; the required sign-in prevents
inspection of the step log, so the exact error remains unknown. No tag, GitHub
Release, crates.io publication, or PyPI package was created. See
[release status](releases.md).

## Reproduction

Use the maintained setup and commands in the [benchmark guide](benchmarks.md).
Freeze the source, native extension, FastAPI app, clients, Python and
dependencies; pass the complete parity gate before timing; retain rejected
attempts; and report each protocol/reference separately. A failed reference
workload is incomplete evidence, not a performance result.
