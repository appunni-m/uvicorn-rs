# Recorded benchmark analysis

Status: **incomplete_categories**. All metric cells use reference / Rust values from matching valid repetitions.

| Category | Status | Rows / invalid | Qualified pairs | Evidence |
| --- | --- | ---: | ---: | --- |
| http1 | no_qualified_pairs | 72 / 58 | 0 | frozen dirty local evidence; not a release performance proof |
| http2 | no_qualified_pairs | 42 / 39 | 0 | frozen dirty local evidence; not a release performance proof |
| http3 | incomplete_category | 1 / 0 | 0 | frozen dirty local evidence; not a release performance proof |
| websocket | qualified_local_pairs | 18 / 8 | 1 | frozen dirty local evidence; not a release performance proof |
| lifecycle | no_qualified_pairs | 6 / 6 | 0 | frozen dirty local evidence; not a release performance proof |

## Matched throughput and latency

HTTP rate is requests/s; WebSocket rate is completed messages/s or handshakes/s. Latency cells are p50 / p95 / p99 in ms, separately for each server.

| Category / workload | Pairs | Rate ref / Rust | Latency ref | Latency Rust | Rust/ref rate |
| --- | ---: | ---: | --- | --- | ---: |
| websocket / connection-handshake | 3 | 3,771.4 / 5,997.3 | 0.245 / 0.381 / 0.474 | 0.146 / 0.281 / 0.312 | 1.590 |

## Matched resource metrics

Server CPU is observed live process-tree CPU µs/op over its recorded boundary. Client CPU is complete reaped-child CPU µs/op only when explicitly marked. RSS cells are medians of sampled peak MiB.

| Category / workload | Server CPU µs/op ref / Rust | Server RSS ref / Rust | Client CPU µs/op ref / Rust | Client RSS ref / Rust |
| --- | ---: | ---: | ---: | ---: |
| websocket / connection-handshake | 188.9 / 112.4 | 32.047 / 26.500 | 57.842 / 58.396 | 2.672 / 2.672 |

## Lifecycle

Startup is a preparation-to-observed-response upper bound. CPU is complete reaped-server lifetime seconds, with idle and active phases kept separate.

| Pairs | Startup ms ref / Rust | Idle exit ms ref / Rust | Held exit ms ref / Rust | Idle CPU s ref / Rust | Active CPU s ref / Rust | Idle RSS MiB ref / Rust | Active RSS MiB ref / Rust |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No qualified matching lifecycle pairs | — | — | — | — | — | — | — |

## Exclusions and incomplete inputs

- http1 invalid row reasons: timing_valid_false_or_missing=58; unequal_exception_diagnostic_policy=6; unrelated_host_cpu_activity=58.
- http1/fixed: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/large-response: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/many-response-chunks: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/small-response-chunks: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/request-upload: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/request-upload-small-chunks: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/slow-reader-backpressure: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/scope-32-headers: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/contextvars: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/sync-callable-awaitable: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/exception-to-500: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available; unequal_exception_diagnostic_policy.
- http1/starlette-rs-route: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2 invalid row reasons: timing_valid_false_or_missing=39; unrelated_host_cpu_activity=39.
- http2/protocol-scope: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2/fixed: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2/large-response: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2/many-response-chunks: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2/request-upload: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2/request-upload-small-chunks: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2/slow-reader-backpressure: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http3/protocol-scope-consumed-request: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/protocol-scope: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/fixed: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/large-response: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/many-response-chunks: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/request-upload: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing; target_only_no_live_reference_pair.
- http3/slow-reader-backpressure: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- websocket invalid row reasons: timing_valid_false_or_missing=8; unrelated_host_cpu_activity=8.
- websocket/text-echo: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- websocket/binary-64k-echo: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- lifecycle invalid row reasons: active_phase_gate_failed_or_missing=6; idle_phase_gate_failed_or_missing=5; timing_valid_false_or_missing=6; unrelated_host_cpu_activity=6.
- lifecycle/lifecycle: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.

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
