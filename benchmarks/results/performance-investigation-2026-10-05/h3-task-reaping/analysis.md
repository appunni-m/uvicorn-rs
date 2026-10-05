# HTTP/3 request-task reaping memory diagnostic

**Memory observation only; speed improvement is not proven.** This compares two Rust builds, without a stock reference.

| Arm | Correct runs | Timing-valid runs | Sampled peak RSS median (MiB) | Sampled peak RSS range (MiB) | Completed request range |
| --- | ---: | ---: | ---: | ---: | ---: |
| before | 5/5 | 2/5 | 614.328 | 467.281–657.906 | 112,855–151,838 |
| after | 5/5 | 0/5 | 33.016 | 30.938–37.219 | 110,204–155,671 |

RSS summaries use all ten correct runs, including eight timing-invalid rows. The matching valid speed-pair count is zero. No throughput, latency or CPU medians/ratios are derived.

## Raw per-run observations

| Arm / repetition | Completed requests | Sampled peak RSS (MiB) | Timing valid | Raw invalid reason |
| --- | ---: | ---: | --- | --- |
| before / 1 | 150,605 | 630.906 | false | unrelated_host_cpu_activity |
| before / 2 | 151,838 | 657.906 | true | — |
| before / 3 | 149,848 | 614.328 | true | — |
| before / 4 | 112,855 | 467.281 | false | unrelated_host_cpu_activity |
| before / 5 | 134,655 | 543.891 | false | unrelated_host_cpu_activity |
| after / 1 | 110,204 | 37.219 | false | unrelated_host_cpu_activity |
| after / 2 | 129,505 | 33.016 | false | unrelated_host_cpu_activity |
| after / 3 | 126,709 | 33.594 | false | unrelated_host_cpu_activity |
| after / 4 | 143,723 | 32.750 | false | unrelated_host_cpu_activity |
| after / 5 | 155,671 | 30.938 | false | unrelated_host_cpu_activity |

## Matched configuration and mechanism

Both arms used the identical `examples.bench_matrix_asgi:app` protocol-scope workload, Python 3.12.13, uvloop 0.23.0, Rust 1.98.1, normal release mode, the same QUIC client binary, concurrency 64 over four multiplexed connections, one-second warmup and five-second load windows on an Apple M3 Pro. Every response status and byte passed validation; all server exits were clean without unexpected native errors or panics. Measured source records differ only at `src/lib.rs`; complete snapshots and identities are retained.

The prior connection-level `JoinSet` accumulated request tasks and joined them after acceptance ended. The change joins completed request tasks during acceptance and keeps cancellation priority, final draining and shared JoinError reporting. This source-level ownership change is consistent with the lower observed RSS. RSS alone does not identify heap allocations, allocator retention or a Python payload leak.

All before repetitions ran before all after repetitions. Closed-loop windows completed different amounts of work; no fixed-request-count, interleaved or equal-offered-rate comparison was run.

## Interpretation limits

- Target-only before/after memory diagnostic; no stock-reference performance comparison is present.
- All before runs preceded all after runs; arms were not interleaved or randomized.
- Fixed elapsed closed-loop windows completed differing request counts; this is not equal-work or fixed-offered-rate evidence.
- RSS summaries include every correct run, including timing-invalid rows; host contention remains explicitly recorded.
- RSS is sampled process-tree resident memory, not allocator live/peak bytes, PSS, private memory, or proof of a Python payload leak.
- The source-level JoinSet ownership mechanism explains task-allocation retention, while the RSS measurements do not isolate allocator arenas or Python/native heap contributions.
- No qualified throughput, latency, CPU gain, overall speedup, or statistical-significance claim is made.
- Both arms are frozen dirty local normal-release builds, not release or published-package performance proof.
- Clients, server and observer share the host; no open-loop test or coordinated-omission correction is available.
