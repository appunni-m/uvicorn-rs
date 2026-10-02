# Full benchmark run notes

## HTTP/1.1 category

- 12 workloads, 4 server configurations, 3 repetitions: 144 rows.
- All 144 measured rows passed status/body correctness checks.
- The Python 3.12.13 environment includes Uvicorn 0.54.0, uvloop 0.23.0,
  httptools 0.8.0, Hypercorn 0.18.0, and the adjacent `starlette-rs` checkout
  at `de790c1314aaec9acb88aac8e70e2c7242506741`.
- **Performance status: provisional, not a clean acceptance run.** After the
  H1 runner completed, process inspection found an overlapping benchmark from
  the adjacent `pillow-rs` checkout (`scripts/run_transpose_throughput.py`,
  `python-gpu` child). It was consuming about 38% of one logical CPU in the
  first observation and about 95% in a later observation. It began during the
  H1 category; its exact start time relative to the H1 samples is unknown.
  Retain `http1.json` as correctness-gated exploratory evidence, but do not use
  it as the clean benchmark required for a performance claim.
- The runner's shuffled configs and per-sample server/client CPU and RSS fields
  remain available in `http1.json` for diagnosis. Rerun H1 after the competing
  benchmark ends before making a final performance decision.

## Instrumentation interpretation

The current Rust source extracts response `bytes` into `bytes::Bytes` through
PyO3's `PyBackedBytes` owner, which retains the Python allocation instead of
copying its payload. Therefore, the observed H1 response-stream slowdown is not
evidence that this conversion copies response bodies. The request receive path
does construct Python `bytes` from Rust-owned request buffers, which copies
into the object required by the ASGI `http.request` message.

Previous diagnostic runs on this code family recorded many full response-body
channel sends in the 256-chunk workload. Those instrumented results are
attribution evidence only and were built from a different source digest; they
are not a substitute for instrumenting this exact revision. The code path
creates a PyO3/Tokio future when the bounded body queue is full, in addition to
the per-request Python task scheduling bridge. Exact CPU attribution and the
large-response RSS cause still require a clean profile/allocation trace.

## Remaining categories and final gate state

- HTTP/2: all 84 rows passed their ALPN/status/body checks. Performance is
  provisional. A FastAPI-RS validation/indexing workload overlapped samples;
  process snapshots are `pre-http2-processes.txt` and
  `during-http2-processes.txt`.
- HTTP/3 cross-server attempt: aborted before writing a complete comparison
  file. Hypercorn uvloop failed the `protocol-scope` warm-up gate with four
  empty response bodies where 14 bytes were expected. The failed output is in
  `http3.log`; the failure is not a Rust-only H3 result.
- HTTP/3 Rust-only: all 36 rows passed. These are candidate data only, and
  performance is provisional. A Pillow migration/parity process and a Rust
  compile were active during this category; see
  `during-http3-failed-comparison-processes.txt` and
  `post-http3-processes.txt`.
- WebSockets: all 36 handshake/text/binary rows passed. Performance is
  provisional because a Pillow migration/parity run and parity input
  generation overlapped the category; see `during-websocket-processes.txt`.
- Lifespan/shutdown: all 20 rows passed, and every row recorded
  `active_asgi_task_cancelled: true`. Performance timings are provisional due
  to concurrent migration/parity work; see `pre-lifecycle-processes.txt`.
- The seven targeted probe scripts produced 17 `PASS` results; their complete
  output is in `live-probes.log`.

The standalone category validator confirmed 144 H1, 84 H2, 36 Rust-only H3,
36 WebSocket, and 20 lifecycle rows, all with zero runner-reported failures.
The full 66-row H3 cross-server requirement is still unmet because Hypercorn's
correctness gate aborted. No performance category in this attempt is a clean
acceptance result: unrelated CPU-heavy processes repeatedly appeared during
the long matrix. Keep every JSON file as correctness-gated exploratory data;
do not describe its rate, latency, CPU, or RSS as a repeatable server win.
