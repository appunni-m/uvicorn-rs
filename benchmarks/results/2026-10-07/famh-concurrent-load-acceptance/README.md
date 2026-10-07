# Concurrent load and zero-grace shutdown acceptance

Measured 2026-10-07 on the local macOS ARM64 checkout. This archive records bounded correctness and resource-stability workflows; it is not a throughput or latency benchmark.

## Workloads

| Case | Stimulus |
|---|---|
| `http1.concurrent-connections-slow-readers-resource-bound` | 32 concurrent connections; 32 response chunks × 2 KiB; 100 ms before reads; four rounds. |
| `http2.concurrent-stream-load-slow-reader-resource-bound` | 32 concurrent streams; 32 response chunks × 2 KiB; 100 ms before reads; four rounds. |
| `http3.concurrent-stream-load-slow-reader-resource-bound` | 16 concurrent streams; 64 response chunks × 4 KiB; 100 ms before reads; three rounds. |
| `websocket.concurrent-sessions-slow-reader-resource-bound` | 16 sessions; 16 echoed messages × 4 KiB; 100 ms before reads; four rounds. |
| `lifespan.zero-timeout-shutdown-cancels-16-active-streams` | Hold 16 HTTP/1.1 responses, send SIGTERM with timeout 0, reset clients, require all ASGI tasks to observe cancellation and lifespan shutdown to finish. |

The four load inputs compare response or message byte lengths and SHA-256 fingerprints against the live reference. They sample process RSS and OS threads every 5 ms, require the configured concurrency to be reached, no net idle Python-task growth from the first to final round, zero active application work, healthy follow-up requests, and at most 16 MiB spread across late-round RSS samples. The RSS threshold measures stability for these fixed inputs; it is not an absolute process-memory cap. The zero-timeout case requires 16 cancellations, zero completed responses, completed lifespan shutdown, and process exit within three seconds. Recorded shutdown milliseconds are diagnostic only.

## Results

The manifest contained 490 cases across 70 input files and 71 operations: 238 live oracle comparisons and 252 target-only contracts. Per-case attribution and three full matrix repeats each passed 490/490 with zero failures, infrastructure failures, retries, or cases not run. LLVM coverage was 5,108/5,108 regions and 3,608/3,608 lines. Coverage MCP reports a matching source receipt, passed test status, and zero region-gap groups. A normal non-instrumented local build passed all 238 oracle comparisons. The five focused cases passed in that run as well.

The measured source was dirty at revision `cf3ce35764707edc07b90e7aeb8e05fe1e1210f3`; `src/lib.rs` SHA-256 was `b598c8e9b2d33db5b0c5bcdfdc8a49ec281918393eb8cfe60ff9185a62957121`. Environment: CPython 3.12.13, Rust 1.98.1, macOS 15.7.7 ARM64, Uvicorn 0.54.0, Hypercorn 0.18.0, and aioquic 1.3.0. The source/build receipt is local evidence, not a clean release baseline.

## Reproduction

From the repository root, sync the pinned benchmark dependencies and run the normal live-oracle set:

```sh
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
uv run --group benchmark python scripts/run_parity.py --output target/parity-normal.json
```

Then run attribution and three full instrumented repeats with retries disabled:

```sh
uv run --group benchmark python scripts/run_unified_coverage.py \
  --output build/asgi-coverage/current/coverage-report.json \
  --artifacts-dir build/asgi-coverage/current/artifacts \
  --matrix-repeats 3 --matrix-infra-retries 0 --case-infra-retries 0
```

Query Coverage MCP for `coverage_gaps` using that report, `metric=regions`, and no filter. Preserve every returned structured page in an array, then attach and validate it with:

```sh
uv run --group benchmark python scripts/attach_coverage_mcp.py \
  --report build/asgi-coverage/current/coverage-report.json \
  --receipt build/asgi-coverage/current/coverage-mcp-pages.json
```

## Limits

These fixed loads establish parity, task cleanup, and bounded RSS spread for the named cases. They do not establish throughput or latency gains, high-scale capacity, absolute memory limits, packet-loss recovery, or security-corpus behavior. Only HTTP/1.1 has concurrent zero-grace shutdown coverage; shutdown under concurrent HTTP/2, HTTP/3, and WebSocket load remains unverified. Request-queue capacities remain item-count bounds, not global byte limits. The Python ASGI application still runs in Python and each ASGI event crosses the bridge.

No new body-size, byte-queue, or global connection cap is introduced by this acceptance. The measured inputs do not establish a safe general-purpose byte limit, and adding one would change which requests the server accepts. Retain current behavior here; evaluate any additional byte-based limit through a separate compatibility decision and parity cases.

## Files

- `normal-parity-238.json`: complete normal-build oracle result.
- `selected-load-cases.json`: compact five-case load and shutdown result.
- `coverage-report.json.gz` and `coverage-report.json.context.json`: unified report and source/build receipt.
- `coverage-mcp-pages.json`: exact structured Coverage MCP response.
- `matrix-repeat-results.tar.gz`: raw result JSON for each of the three complete matrix repeats.
- `evidence-index.json`: source, build, run, and artifact hashes.
