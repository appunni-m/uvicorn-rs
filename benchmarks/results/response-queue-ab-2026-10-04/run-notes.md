# Response queue depth experiment

**Status:** focused evidence supports a larger response-message queue for this
streaming workload. It does not establish an overall server performance win.

## Method

The benchmark used the same locked environment and command parameters for each
run: CPython 3.12.13, macOS 15.7.7 on an Apple M3 Pro (12 logical CPUs),
concurrency 64, three 2-second repetitions, a 250 ms warmup, and seed
`20261004`. The workload returns a 1 MiB body as 256 ordered 4 KiB ASGI body
messages. The libcurl client used persistent HTTP/1.1 connections and checked
every complete response body. The recorded benchmark metadata pins the server
and dependency versions and source digest.

`queue4.json` is retained as an exploratory run, but its host was busy and its
timings are excluded from the comparison. `queue4-repeat.json` is the fresh
four-message control. `queue16.json` and `queue16-repeat.json` are two
queue-sixteen campaigns. Every one of the 12 rows in each campaign had zero
failures and passed full-body checking.

## Rust plus uvloop results

Values are medians across the three repetitions in each campaign.

| Queue messages | Campaign | Requests/s | p50 ms | p95 ms | p99 ms | Server CPU | Peak RSS |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | Fresh control | 778 | 81.87 | 106.89 | 113.63 | 193.6% | 35.28 MiB |
| 16 | First candidate run | 2,480 | 25.13 | 39.09 | 61.53 | 205.0% | 36.09 MiB |
| 16 | Repeat candidate run | 2,469 | 26.29 | 38.22 | 42.50 | 204.0% | 36.05 MiB |

The repeat queue-sixteen run delivered 3.17 times the fresh queue-four
throughput. Its median p50, p95, and p99 were respectively 67.9%, 64.2%, and
62.6% lower. Server CPU rose by 10.5 percentage points (about 5.4% relative),
and peak RSS rose by 0.77 MiB. The two queue-sixteen throughput medians differ
by less than 1%.

In the repeat campaign, Rust plus uvloop reached 2,469 requests/s versus 1,793
for Uvicorn plus uvloop and httptools. Rust's p50 was lower (26.29 vs 33.83
ms), while p95 was slightly higher (38.22 vs 36.88 ms). The Uvicorn p99 was
high and variable across these short runs, so it is not evidence of a stable
tail-latency advantage.

Rust used about 2.04 CPU cores at its median throughput, compared with about
0.98 for Uvicorn. Normalized by those sampled CPU shares, this is roughly
1,210 requests/s per core for Rust and 1,828 for Uvicorn. This workload
therefore shows a throughput win from using more CPU, not better per-core
efficiency. The result is not evidence that Rust is faster overall or that
SIMD is relevant to this path.

## Interpretation and limits

The implementation calls `try_send` for each ASGI response-body message. When
the bounded Tokio channel is full, it returns a Python awaitable whose send
waits for queue capacity. Raising the count gives the application more room to
produce a burst before that wait applies. The measurements are consistent with
fewer full-queue stalls; the benchmark did not enable runtime diagnostics, so
it did not directly count those stalls for these campaigns. This tuning does
not remove per-message Python calls or the Python/Rust boundary.

The host was not fully isolated for the queue-sixteen repeat: its saved
pre-run sample ranged from roughly 64% to 81% CPU idle, while the queue-four
pre-run sample ranged from roughly 90% to 95%. The matching Uvicorn
uvloop/httptools controls were 1,850 and 1,793 requests/s, which stayed close,
but longer interleaved queue-four/queue-sixteen campaigns on an idle host are
still needed before publishing a general performance claim. See the adjacent
`*-host.txt` files for the snapshots.

The queue is bounded by message count, not bytes; individual ASGI chunks can
be arbitrarily large. Peak RSS here reflects 4 KiB chunks and does not prove a
safe memory ceiling for arbitrary applications or high connection counts. A
byte-budgeted backpressure policy and large-chunk/many-connection memory cases
remain follow-up work before treating this as a production default.

The queue-sixteen candidate also passed the response-burst parity case on
HTTP/1.1, HTTP/2, and HTTP/3. The live results are in
`queue16-streaming-protocol-parity.json`. This is targeted protocol evidence,
not a pass of the complete ASGI support matrix. The repository changelog was
not modified.
