# Benchmark and release-gate status

## Local FastAPI results

The latest exact-source [FastAPI category matrix](../benchmarks/results/2026-10-10/fastapi-current-matched-matrix-20261010/README.md)
uses stock FastAPI on CPython 3.12.13, one Tokio async worker, and source
`1f222c0…` with normal extension `bf3cb99…`. It has 390/390 complete-matrix
correctness rows, 420 focused retry rows, and 192 deeper H1 rows. H1 fixed
requests regress against Uvicorn as concurrency rises; H1 upload diagnostics
locate latency in `receive()` delivery and the Rust/Python future bridge.
HTTP/1 streaming has near-parity rate with higher Rust CPU, while WebSocket
handshake and qualifying HTTP/2/3 workloads favor Rust. The per-workload table
and current-source interpretation are in the report; there is no single
cross-protocol speed ratio.

Follow-up diagnostics now cover all 15 HTTP/1 workload variants with thread
CPU counters and add 320 response-checked stage rows for HTTP/2, HTTP/3, and
WebSockets. See the [per-thread report](../benchmarks/results/2026-10-10/fastapi-current-all-h1-thread-cpu-retry-20261010/README.md)
and [protocol-stage report](../benchmarks/results/2026-10-10/fastapi-current-protocol-stages-20261010/README.md).
The stage timings are diagnostic-only; the ordinary matched matrix remains
the throughput, latency, process CPU, and RSS evidence.

A current-source 32-byte WebSocket text-echo attempt passed 20/20 payload
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
cross-platform performance claim. The current dirty-source thread and stack
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
the current dirty candidate. The hosted cause remains unconfirmed; details and
receipts are in the [TLS-drain probe follow-up](../benchmarks/results/2026-10-10/ci54-tls-drain-probe-followup/README.md).

## Latest hosted multi-system benchmark

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
change in `b2ea48bc`; they do not validate the current dirty Rust candidate.

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
passed the failing case 10/10 times with matching oracle and target
observations, so it does not explain the hosted mismatch. The job annotation
still omits those observations. Benchmark #12 is terminal without validated
timing data: all three system jobs and aggregation failed, with the Linux
x86-64 parity gate stopping before timing.

## Release candidate

No release-candidate bundle is ready. CI #56 passed its full hosted gates on
clean commit `72dfa51`, but that commit contains only the benchmark diagnostic
workflow change and does not include the dirty Rust candidate. Benchmark #13
has one macOS ARM64 parity failure and its two Linux jobs are still measuring
categories; it has not produced a validated three-system aggregate. Benchmark
#12 ended without validated timing data. No tag, GitHub Release, crates.io
publication, or PyPI package was created. See [release status](releases.md).

## Reproduction

Use the maintained setup and commands in the [benchmark guide](benchmarks.md).
Freeze the source, native extension, FastAPI app, clients, Python and
dependencies; pass the complete parity gate before timing; retain rejected
attempts; and report each protocol/reference separately. A failed reference
workload is incomplete evidence, not a performance result.
