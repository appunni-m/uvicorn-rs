# October 5 investigation evidence

See [the investigation report](../../../docs/performance-investigation-2026-10-05.md)
for interpretation and scope.

## Four-arm HTTP/1 experiment

`original.json`, `vectored.json`, `interned-keys.json` and
`interned-keys-worker1.json` are unchanged runner reports. Their corresponding
JSONL checkpoints, metadata, logs and artifact directories preserve every
attempt. `run.json` records the variant order, build identities and restoration.
`analysis.json` summarizes the evidence; it does not replace the raw reports.

All 120 samples passed response checks. The contention guard rejected 105
timings, including every optimization timing. There is no accepted speedup.
The original large-response workload has three valid matched repetitions;
other workloads do not. These historical runs used reference logging at
`CRITICAL`, which could suppress reference error diagnostics. Later category
runners use `ERROR`; historical rows have not been rewritten.
The historical reference also used lifespan `off` while Rust used automatic
support detection. Revised H1/WebSocket runners use automatic lifespan on both.
The original sync-callable fixture is retained separately; its revised version
adds lifespan support and keeps the same HTTP response.

## Diagnostic profiles

`profiles/` contains profiler receipts, stack samples, checked client results,
server logs and frozen source inputs. The local build directory retains the
exact native executables identified in each receipt. Profiling is diagnostic
and deliberately excluded from timing comparisons. Stack counts describe
wall-time observations across threads, not CPU percentages or speed gains.

## Correctness receipts

`correctness/` preserves the failing H3 clean-close comparison before the fix,
passing defended cases, and 213-case public parity/Clippy receipts for the
`b642…` source. That source precedes the shared-buffer enum refactor; these
receipts are historical, not validation of a later compiled artifact.

`current-normal/` freezes source, build identity/logs, formatting/Clippy receipts
and 213-case live public parity for source `81c239…`, native `8f69af…`.
The borrowed scalar/vectored enum shares error handling without allocating or
copying payloads. This directory proves the named normal-build checks; fresh
complete coverage is documented separately in the coverage report.

## Initial synchronized category attempt

`categories-error-logs/` preserves the original reports, metadata, JSONL
checkpoints, server logs and recorded JSON/Markdown analysis. The intended
171-row matrix was incomplete: H1, H2, WebSocket and lifecycle completed 138
rows, and the unfinished H3 checkpoint contains one completed Rust row, for
139 recorded rows. Completed rows report zero failures. Stock Hypercorn's
first H3 protocol-scope warmup failed with 64 response-header timeouts; its
server log retains `ExceptionGroup` and `KeyError(4140)`. No final H3 report
or completed reference H3 performance row exists.

The analyzer reports zero qualified matching pairs. Contention-invalid timing,
missing repetitions and incomplete H3 evidence remain explicit; this attempt
establishes no speedup. `evidence-snapshot/` preserves the exact runner,
analyzer, measured sources, apps and client sources. Its manifest records
byte-identical raw copies and source hash checks; no binaries are archived.

`lifecycle-smoke-v2/` separately preserves two complete lifecycle correctness
rows and all four idle/active phase server logs. Both timing rows were invalid
because of unrelated host CPU activity. One repetition provides no qualified
paired performance comparison.

`http1-clean-retry/` preserves a separate 30-row attempt: all response checks
passed, 11 individual timing rows were valid, and 19 were invalid. Recorded
matching valid repetitions are fixed `[2, 3]`, large response `[1, 3]`, scope
with 32 headers `[1]`, and none for context variables or many response chunks.
No workload has the required three matching repetitions, so none qualifies
for a speedup. Its compact summary preserves the recorded pair metadata;
individual row counts are distinct from matching workload groups.

## HTTP/3 task retention and verification

`h3-task-reaping/` retains five before and five after normal-build diagnostics.
All responses and shutdown checks passed. Median sampled peak server RSS fell
from 614.3 MiB to 33.0 MiB. These runs describe local memory use: work counts
varied, before runs preceded after runs, and host contention prevented a
qualified speed comparison. The measurement identifies source `313fc3…` and
native `b11f16…`; it is not a measurement of the current saved normal binary.

`http3-task-reaping-coverage-attempt-1/` retains the later source `c7bd49…`
450-case attempt. Individual attribution passed, full repeats failed, and
two native regions remained missing. Its lossless report and logs preserve
the H3 receive-header failures and a separate Uvicorn TLS WebSocket timeout.
Historical passing 448-case results remain under `current-coverage/` and
apply only to source `81c239…`.

`http3-grease-interop/` retains a controlled client-setting replay. The
unchanged 128-request sequence failed with GREASE enabled and passed against
both servers with GREASE disabled; the peer-close case also passed in the
disabled arm. No reference source or deadline changed. This is selected
interoperability evidence on the instrumented native, not a benchmark.

`reproducible-runner/` retains the original runner proposal and later review
and framework-access receipts. Historical proposal text describes its own
creation time. Maintained commands now live in `scripts/`; the separate manual
CI workflow has been added but has not run on GitHub. The additive consumed-H3
request workload failed the concurrency-64 stock reference correctness gate;
it has no qualifying paired speed result.

`http3-task-reaping-coverage/` retains the successful current 451-case
attribution run and three full repeats: 4,778/4,778 native regions,
3,371/3,371 lines, and an unfiltered matching MCP check with zero gaps.
`current-normal-http3-task-reaping-final/` retains 214/214 public parity,
three passing exclusion cases and exact portable identity equality on the
normal `0e13bb…` binary. Its two invalid earlier identity attempts remain
separate.

`final-normal-c7-categories/` retains the fresh 177-sample plan and all 139
completed samples, including the lone Rust H3 row and reference timeout logs.
The qualified WebSocket connection-handshake comparison has three matched valid
repetitions and a median Rust/Uvicorn rate ratio of 1.590. HTTP timings and echo
comparisons lack sufficient clean matches. The driver preserved independent
categories after the H3 failure; no overall performance claim is accepted.

`sha256.json` inventories archived files except itself. No row was removed
because it failed a timing guard. The benchmark environment contains a
separately rebuilt, frozen `starlette-rs` wheel; the server does not depend on
that framework.
