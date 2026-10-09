# Recorded benchmark analysis

Status: **partial_category_subset**. All metric cells use reference / Rust values from matching valid repetitions.

Scope: selected http3; omitted http1, http2, websocket, lifecycle. A selected subset is not a complete matrix.

| Category | Status | Rows / invalid | Qualified pairs | Evidence |
| --- | --- | ---: | ---: | --- |
| http1 | not_selected | 0 / 0 | 0 | not selected in this run |
| http2 | not_selected | 0 / 0 | 0 | not selected in this run |
| http3 | qualified_local_pairs | 130 / 24 | 10 | frozen dirty local evidence; not a release performance proof |
| websocket | not_selected | 0 / 0 | 0 | not selected in this run |
| lifecycle | not_selected | 0 / 0 | 0 | not selected in this run |

## Matched throughput and latency

HTTP rate is requests/s; WebSocket rate is completed messages/s or handshakes/s. Latency cells are p50 / p95 / p99 in ms, separately for each server.

| Category / workload / loop | Pairs | Rate ref / Rust | Latency ref | Latency Rust | Rust/ref rate |
| --- | ---: | ---: | --- | --- | ---: |
| http3 / protocol-scope-consumed-request / asyncio | 4 | 2,018.0 / 6,375.0 | 0.489 / 0.550 / 0.581 | 0.154 / 0.177 / 0.190 | 3.160 |
| http3 / protocol-scope-consumed-request / uvloop | 4 | 2,221.5 / 6,857.5 | 0.466 / 0.587 / 0.626 | 0.143 / 0.163 / 0.173 | 3.092 |
| http3 / protocol-scope / asyncio | 5 | 2,051.9 / 8,718.4 | 0.482 / 0.530 / 0.582 | 0.112 / 0.131 / 0.141 | 4.233 |
| http3 / protocol-scope / uvloop | 4 | 2,230.3 / 9,503.7 | 0.470 / 0.592 / 0.629 | 0.102 / 0.122 / 0.132 | 4.257 |
| http3 / fixed / asyncio | 5 | 2,056.1 / 8,817.3 | 0.481 / 0.531 / 0.583 | 0.111 / 0.129 / 0.140 | 4.275 |
| http3 / fixed / uvloop | 4 | 2,236.9 / 9,630.6 | 0.472 / 0.591 / 0.626 | 0.101 / 0.120 / 0.130 | 4.302 |
| http3 / large-response / asyncio | 4 | 37.388 / 360.7 | 14.721 / 52.705 / 55.988 | 2.789 / 2.858 / 2.897 | 9.659 |
| http3 / large-response / uvloop | 5 | 18.208 / 364.2 | 54.968 / 56.103 / 59.176 | 2.761 / 2.832 / 2.877 | 20.004 |
| http3 / many-response-chunks / asyncio | 4 | 19.593 / 328.7 | 50.240 / 54.736 / 83.626 | 3.026 / 3.230 / 3.329 | 16.666 |
| http3 / many-response-chunks / uvloop | 4 | 18.174 / 326.4 | 55.001 / 56.854 / 59.653 | 3.051 / 3.256 / 3.365 | 17.963 |

## Matched resource metrics

Server CPU is observed live process-tree CPU µs/op over its recorded boundary. Client CPU is complete reaped-child CPU µs/op only when explicitly marked. RSS cells are medians of sampled peak MiB.

| Category / workload / loop | Server CPU µs/op ref / Rust | Server RSS ref / Rust | Client CPU µs/op ref / Rust | Client RSS ref / Rust |
| --- | ---: | ---: | ---: | ---: |
| http3 / protocol-scope-consumed-request / asyncio | 362.3 / 117.4 | 104.9 / 44.367 | 74.661 / 28.443 | 4.141 / 4.219 |
| http3 / protocol-scope-consumed-request / uvloop | 310.5 / 102.2 | 106.6 / 45.719 | 62.387 / 27.378 | 4.250 / 4.211 |
| http3 / protocol-scope / asyncio | 353.1 / 87.500 | 105.1 / 44.406 | 72.692 / 27.818 | 4.266 / 4.297 |
| http3 / protocol-scope / uvloop | 306.0 / 75.314 | 106.2 / 45.719 | 61.301 / 27.175 | 4.094 / 4.344 |
| http3 / fixed / asyncio | 353.2 / 86.110 | 105.7 / 44.438 | 73.039 / 27.726 | 4.250 / 4.297 |
| http3 / fixed / uvloop | 304.7 / 74.349 | 106.8 / 45.586 | 60.641 / 27.139 | 4.078 / 4.305 |
| http3 / large-response / asyncio | 14,580.4 / 2,764.8 | 127.0 / 52.523 | 5,058.6 / 3,146.0 | 5.219 / 5.703 |
| http3 / large-response / uvloop | 23,899.6 / 2,732.9 | 126.7 / 53.844 | 7,268.1 / 3,119.8 | 5.078 / 5.562 |
| http3 / many-response-chunks / asyncio | 36,198.3 / 3,578.6 | 105.7 / 51.219 | 7,173.5 / 3,446.3 | 5.156 / 5.578 |
| http3 / many-response-chunks / uvloop | 25,400.7 / 3,466.1 | 123.5 / 52.531 | 7,415.9 / 3,478.8 | 5.078 / 5.703 |

## Lifecycle

Startup is a preparation-to-observed-response upper bound. CPU is complete reaped-server lifetime seconds, with idle and active phases kept separate.

| Loop | Pairs | Startup ms ref / Rust | Idle exit ms ref / Rust | Held exit ms ref / Rust | Idle CPU s ref / Rust | Active CPU s ref / Rust | Idle RSS MiB ref / Rust | Active RSS MiB ref / Rust |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No qualified matching lifecycle pairs | — | — | — | — | — | — | — | — |

## Exclusions and incomplete inputs

- http3 invalid row reasons: timing_valid_false_or_missing=24; unrelated_host_cpu_activity=24.
- http3 target-only exclusions: {'target_only_no_live_reference_pair': 10}.
- http3/request-upload/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_missing_or_duplicate; target_only_no_live_reference_pair.
- http3/request-upload/uvloop: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_missing_or_duplicate; target_only_no_live_reference_pair.
- http3/slow-reader-backpressure/asyncio: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http3/slow-reader-backpressure/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.

## Interpretation limits

- Three valid matching repetitions are a descriptive gate, not evidence of statistical significance.
- Medians of per-run latency percentiles are not pooled request latency percentiles.
- Throughput ratios use matching repetitions only; no overall winner or cross-protocol ranking is produced.
- Recorded H1, H2, H3, and WebSocket client clocks/setup/drain boundaries differ and cannot be compared across protocols.
- Closed-loop same-host load has no coordinated-omission correction or open-loop offered-rate evidence.
- Sustained server CPU is observed live process-tree cpu_times deltas over the recorded load/monitor boundary; complete reaped-child accounting is not inferred.
- Client CPU is complete reaped-child RUSAGE_CHILDREN accounting across setup/load/drain/report only when each row explicitly asserts client_cpu_complete.
- RSS is sampled process-tree RSS; the reported value is a median of matched runs' sampled peaks, not allocator peak, PSS, or private memory.
- Lifecycle complete CPU covers the spawned and reaped server process lifetime (startup/readiness/shutdown); the separate elapsed and cold-start boundaries additionally include observer/free-port/environment preparation, and differ from sustained request CPU.
- Lifecycle startup is preparation-to-observed-valid-response, an upper bound affected by polling and observer work; no sub-poll precision is claimed.
- Exception diagnostic policies differ and exception-to-500 timing remains unrankable; H3 uploads have no live qualifying Hypercorn performance pair.
- The analyzer checks recorded identities and gates; it does not independently attest compilation or reconstruct the measured processes.
