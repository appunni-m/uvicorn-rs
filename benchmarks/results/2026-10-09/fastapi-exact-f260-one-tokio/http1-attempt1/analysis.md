# Recorded benchmark analysis

Status: **partial_category_subset**. All metric cells use reference / Rust values from matching valid repetitions.

Scope: selected http1; omitted http2, http3, websocket, lifecycle. A selected subset is not a complete matrix.

| Category | Status | Rows / invalid | Qualified pairs | Evidence |
| --- | --- | ---: | ---: | --- |
| http1 | qualified_local_pairs | 300 / 144 | 9 | frozen dirty local evidence; not a release performance proof |
| http2 | not_selected | 0 / 0 | 0 | not selected in this run |
| http3 | not_selected | 0 / 0 | 0 | not selected in this run |
| websocket | not_selected | 0 / 0 | 0 | not selected in this run |
| lifecycle | not_selected | 0 / 0 | 0 | not selected in this run |

## Matched throughput and latency

HTTP rate is requests/s; WebSocket rate is completed messages/s or handshakes/s. Latency cells are p50 / p95 / p99 in ms, separately for each server.

| Category / workload / loop | Pairs | Rate ref / Rust | Latency ref | Latency Rust | Rust/ref rate |
| --- | ---: | ---: | --- | --- | ---: |
| http1 / fastapi-validated-route / uvloop | 3 | 15,952.1 / 14,915.5 | 3.948 / 4.139 / 7.833 | 4.350 / 6.245 / 7.032 | 0.935 |
| http1 / fastapi-fixed / asyncio | 3 | 24,895.5 / 18,220.2 | 2.547 / 2.697 / 2.792 | 3.587 / 5.140 / 5.898 | 0.731 |
| http1 / fastapi-small-response-chunks / asyncio | 4 | 2,647.8 / 2,491.7 | 23.723 / 30.109 / 31.079 | 25.556 / 28.839 / 31.200 | 0.941 |
| http1 / fastapi-request-upload / asyncio | 3 | 3,123.3 / 1,428.7 | 19.248 / 25.143 / 28.162 | 44.933 / 47.000 / 50.601 | 0.458 |
| http1 / fastapi-request-upload / uvloop | 4 | 3,230.1 / 1,819.2 | 19.599 / 24.730 / 27.672 | 35.152 / 37.120 / 39.927 | 0.563 |
| http1 / fastapi-upload-1m-write-1m / uvloop | 4 | 3,208.7 / 1,806.0 | 19.594 / 24.840 / 27.959 | 35.425 / 37.374 / 40.556 | 0.561 |
| http1 / fastapi-contextvars / uvloop | 3 | 18,882.8 / 17,396.1 | 3.318 / 3.460 / 6.722 | 3.741 / 5.335 / 6.103 | 0.921 |
| http1 / fastapi-python-cpu / asyncio | 3 | 1,026.2 / 1,072.2 | 61.941 / 70.512 / 74.821 | 63.897 / 88.313 / 91.287 | 1.045 |
| http1 / fastapi-python-cpu / uvloop | 3 | 1,076.5 / 1,076.3 | 58.238 / 70.063 / 79.489 | 63.515 / 89.019 / 92.696 | 1.001 |

## Matched resource metrics

Server CPU is observed live process-tree CPU µs/op over its recorded boundary. Client CPU is complete reaped-child CPU µs/op only when explicitly marked. RSS cells are medians of sampled peak MiB.

| Category / workload / loop | Server CPU µs/op ref / Rust | Server RSS ref / Rust | Client CPU µs/op ref / Rust | Client RSS ref / Rust |
| --- | ---: | ---: | ---: | ---: |
| http1 / fastapi-validated-route / uvloop | 62.573 / 74.250 | 50.016 / 51.391 | 16.081 / 55.152 | 8.172 / 8.391 |
| http1 / fastapi-fixed / asyncio | 40.097 / 62.436 | 47.109 / 48.938 | 20.195 / 57.576 | 8.641 / 8.438 |
| http1 / fastapi-small-response-chunks / asyncio | 376.7 / 581.2 | 50.078 / 49.859 | 177.1 / 111.2 | 7.812 / 9.766 |
| http1 / fastapi-request-upload / asyncio | 319.5 / 1,088.6 | 383.0 / 211.2 | 218.9 / 231.7 | 15.125 / 14.641 |
| http1 / fastapi-request-upload / uvloop | 308.8 / 855.3 | 408.2 / 212.7 | 261.1 / 228.4 | 14.734 / 14.625 |
| http1 / fastapi-upload-1m-write-1m / uvloop | 310.8 / 860.6 | 410.5 / 215.5 | 258.8 / 229.2 | 14.758 / 14.609 |
| http1 / fastapi-contextvars / uvloop | 52.798 / 64.178 | 49.219 / 51.172 | 15.594 / 51.993 | 8.266 / 8.406 |
| http1 / fastapi-python-cpu / asyncio | 990.3 / 973.3 | 50.656 / 51.297 | 37.018 / 27.639 | 7.750 / 7.500 |
| http1 / fastapi-python-cpu / uvloop | 938.6 / 954.3 | 52.734 / 52.938 | 27.400 / 27.295 | 7.312 / 7.469 |

## Lifecycle

Startup is a preparation-to-observed-response upper bound. CPU is complete reaped-server lifetime seconds, with idle and active phases kept separate.

| Loop | Pairs | Startup ms ref / Rust | Idle exit ms ref / Rust | Held exit ms ref / Rust | Idle CPU s ref / Rust | Active CPU s ref / Rust | Idle RSS MiB ref / Rust | Active RSS MiB ref / Rust |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No qualified matching lifecycle pairs | — | — | — | — | — | — | — | — |

## Exclusions and incomplete inputs

- http1 invalid row reasons: timing_valid_false_or_missing=144; unrelated_host_cpu_activity=144.
- http1/fastapi-validated-route/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-fixed/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-large-response/asyncio: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-large-response/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-many-response-chunks/asyncio: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-many-response-chunks/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-small-response-chunks/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-1k/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-1k/uvloop: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-16k/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-16k/uvloop: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-256k/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-256k/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-1m/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-request-upload-small-chunks/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-request-upload-small-chunks/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-slow-reader-backpressure/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-slow-reader-backpressure/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-scope-32-headers/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-scope-32-headers/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-contextvars/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.

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
