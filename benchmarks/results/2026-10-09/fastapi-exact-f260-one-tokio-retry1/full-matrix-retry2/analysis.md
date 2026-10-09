# Recorded benchmark analysis

Status: **incomplete_categories**. All metric cells use reference / Rust values from matching valid repetitions.

Scope: selected http1, http2, http3, websocket, lifecycle; omitted none. A selected subset is not a complete matrix.

| Category | Status | Rows / invalid | Qualified pairs | Evidence |
| --- | --- | ---: | ---: | --- |
| http1 | qualified_local_pairs | 300 / 135 | 12 | frozen dirty local evidence; not a release performance proof |
| http2 | qualified_local_pairs | 140 / 5 | 14 | frozen dirty local evidence; not a release performance proof |
| http3 | incomplete_category | 2 / 0 | 0 | frozen dirty local evidence; not a release performance proof |
| websocket | qualified_local_pairs | 60 / 9 | 5 | frozen dirty local evidence; not a release performance proof |
| lifecycle | qualified_local_pairs | 20 / 7 | 1 | frozen dirty local evidence; not a release performance proof |

## Matched throughput and latency

HTTP rate is requests/s; WebSocket rate is completed messages/s or handshakes/s. Latency cells are p50 / p95 / p99 in ms, separately for each server.

| Category / workload / loop | Pairs | Rate ref / Rust | Latency ref | Latency Rust | Rust/ref rate |
| --- | ---: | ---: | --- | --- | ---: |
| http1 / fastapi-validated-route / asyncio | 4 | 14,579.1 / 13,242.0 | 4.381 / 4.461 / 4.537 | 4.928 / 7.030 / 7.861 | 0.908 |
| http1 / fastapi-validated-route / uvloop | 4 | 16,062.1 / 15,420.9 | 3.970 / 4.043 / 7.886 | 4.245 / 6.067 / 6.780 | 0.959 |
| http1 / fastapi-large-response / asyncio | 4 | 9,920.3 / 8,662.4 | 6.411 / 6.657 / 7.082 | 7.920 / 8.231 / 8.843 | 0.874 |
| http1 / fastapi-many-response-chunks / asyncio | 3 | 1,461.6 / 1,382.3 | 43.517 / 49.471 / 50.036 | 47.029 / 48.911 / 50.731 | 0.955 |
| http1 / fastapi-many-response-chunks / uvloop | 4 | 1,345.0 / 1,699.0 | 46.970 / 53.587 / 54.402 | 37.797 / 40.042 / 41.889 | 1.265 |
| http1 / fastapi-upload-1m-write-1k / asyncio | 3 | 324.4 / 351.7 | 197.8 / 299.8 / 356.1 | 187.5 / 259.4 / 339.0 | 1.084 |
| http1 / fastapi-scope-32-headers / asyncio | 5 | 18,224.2 / 14,824.2 | 3.506 / 3.548 / 3.593 | 4.471 / 6.278 / 7.079 | 0.811 |
| http1 / fastapi-scope-32-headers / uvloop | 5 | 20,075.2 / 17,064.8 | 3.145 / 3.184 / 6.281 | 3.873 / 5.395 / 6.085 | 0.851 |
| http1 / fastapi-contextvars / asyncio | 5 | 17,940.7 / 15,646.8 | 3.565 / 3.618 / 3.677 | 4.165 / 5.913 / 6.709 | 0.876 |
| http1 / fastapi-contextvars / uvloop | 5 | 19,278.4 / 18,862.4 | 3.264 / 3.307 / 6.575 | 3.451 / 4.865 / 5.546 | 0.987 |
| http1 / fastapi-python-cpu / asyncio | 5 | 1,062.3 / 1,114.8 | 59.708 / 68.499 / 72.274 | 60.416 / 84.851 / 87.586 | 1.043 |
| http1 / fastapi-python-cpu / uvloop | 5 | 1,102.0 / 1,128.2 | 57.353 / 69.344 / 76.315 | 60.334 / 84.830 / 87.720 | 1.023 |
| http2 / protocol-scope / asyncio | 5 | 6,713.6 / 24,878.4 | 9.211 / 14.191 / 14.866 | 2.648 / 3.649 / 4.273 | 3.706 |
| http2 / protocol-scope / uvloop | 5 | 6,819.7 / 28,759.9 | 9.050 / 14.236 / 15.071 | 2.275 / 3.184 / 3.699 | 4.233 |
| http2 / fixed / asyncio | 3 | 6,768.8 / 25,181.1 | 9.135 / 14.142 / 14.917 | 2.606 / 3.617 / 4.198 | 3.720 |
| http2 / fixed / uvloop | 4 | 6,880.3 / 29,456.4 | 8.971 / 14.353 / 15.130 | 2.226 / 3.100 / 3.659 | 4.270 |
| http2 / large-response / asyncio | 4 | 242.0 / 1,954.9 | 264.3 / 287.0 / 293.9 | 32.572 / 37.014 / 39.188 | 8.077 |
| http2 / large-response / uvloop | 5 | 252.2 / 1,963.6 | 253.7 / 274.5 / 283.1 | 32.384 / 36.933 / 39.021 | 7.791 |
| http2 / many-response-chunks / asyncio | 5 | 186.9 / 224.4 | 341.4 / 381.7 / 396.4 | 286.0 / 307.0 / 314.6 | 1.201 |
| http2 / many-response-chunks / uvloop | 5 | 200.4 / 307.4 | 320.2 / 346.0 / 353.5 | 209.0 / 225.2 / 231.4 | 1.533 |
| http2 / request-upload / asyncio | 5 | 248.1 / 501.8 | 256.4 / 336.1 / 359.8 | 126.9 / 136.7 / 142.8 | 2.017 |
| http2 / request-upload / uvloop | 5 | 315.6 / 675.8 | 200.5 / 226.9 / 282.7 | 93.993 / 101.2 / 104.8 | 2.142 |
| http2 / request-upload-small-chunks / asyncio | 5 | 1,156.3 / 636.6 | 53.090 / 67.723 / 71.698 | 100.8 / 105.4 / 106.9 | 0.548 |
| http2 / request-upload-small-chunks / uvloop | 5 | 1,195.3 / 943.4 | 53.548 / 54.517 / 55.137 | 68.032 / 70.560 / 72.152 | 0.789 |
| http2 / slow-reader-backpressure / asyncio | 4 | 7.874 / 7.939 | 253.3 / 255.4 / 264.5 | 251.6 / 253.1 / 253.5 | 1.008 |
| http2 / slow-reader-backpressure / uvloop | 5 | 7.890 / 7.943 | 253.1 / 255.4 / 255.5 | 251.5 / 252.8 / 253.2 | 1.006 |
| websocket / connection-handshake / asyncio | 5 | 2,252.7 / 4,855.0 | 0.420 / 0.505 / 0.594 | 0.189 / 0.274 / 0.351 | 2.151 |
| websocket / connection-handshake / uvloop | 5 | 3,018.3 / 5,503.0 | 0.302 / 0.400 / 0.486 | 0.158 / 0.254 / 0.330 | 1.849 |
| websocket / text-echo / asyncio | 4 | 57,790.6 / 34,158.0 | 1.108 / 1.130 / 1.150 | 1.863 / 2.841 / 3.217 | 0.591 |
| websocket / text-echo / uvloop | 4 | 67,170.9 / 47,970.1 | 0.952 / 0.971 / 0.987 | 1.353 / 1.949 / 2.212 | 0.715 |
| websocket / binary-64k-echo / uvloop | 3 | 28,033.5 / 29,369.3 | 2.271 / 2.433 / 2.553 | 2.248 / 3.038 / 3.201 | 1.044 |

## Matched resource metrics

Server CPU is observed live process-tree CPU µs/op over its recorded boundary. Client CPU is complete reaped-child CPU µs/op only when explicitly marked. RSS cells are medians of sampled peak MiB.

| Category / workload / loop | Server CPU µs/op ref / Rust | Server RSS ref / Rust | Client CPU µs/op ref / Rust | Client RSS ref / Rust |
| --- | ---: | ---: | ---: | ---: |
| http1 / fastapi-validated-route / asyncio | 68.491 / 83.210 | 46.742 / 49.844 | 21.191 / 58.122 | 8.250 / 8.094 |
| http1 / fastapi-validated-route / uvloop | 62.146 / 71.480 | 48.938 / 50.852 | 15.425 / 55.113 | 8.141 / 8.242 |
| http1 / fastapi-large-response / asyncio | 100.6 / 130.4 | 47.750 / 50.609 | 148.1 / 170.4 | 9.445 / 9.789 |
| http1 / fastapi-many-response-chunks / asyncio | 682.9 / 1,081.5 | 53.359 / 49.656 | 444.0 / 465.6 | 8.547 / 10.656 |
| http1 / fastapi-many-response-chunks / uvloop | 742.1 / 868.3 | 53.117 / 50.977 | 563.7 / 422.0 | 8.508 / 10.672 |
| http1 / fastapi-upload-1m-write-1k / asyncio | 990.7 / 1,705.2 | 416.4 / 300.4 | 33,273.3 / 26,658.3 | 14.000 / 13.875 |
| http1 / fastapi-scope-32-headers / asyncio | 54.805 / 76.985 | 47.031 / 48.453 | 25.483 / 63.752 | 8.047 / 8.312 |
| http1 / fastapi-scope-32-headers / uvloop | 49.742 / 67.293 | 49.281 / 50.375 | 20.363 / 63.470 | 8.484 / 8.266 |
| http1 / fastapi-contextvars / asyncio | 55.664 / 71.379 | 46.406 / 49.078 | 20.593 / 58.300 | 8.453 / 8.359 |
| http1 / fastapi-contextvars / uvloop | 51.794 / 58.565 | 48.844 / 51.281 | 14.957 / 56.939 | 8.344 / 8.281 |
| http1 / fastapi-python-cpu / asyncio | 955.9 / 934.8 | 50.625 / 51.312 | 35.590 / 25.908 | 7.688 / 7.484 |
| http1 / fastapi-python-cpu / uvloop | 915.6 / 909.9 | 52.109 / 52.938 | 25.882 / 25.941 | 7.328 / 7.531 |
| http2 / protocol-scope / asyncio | 148.7 / 48.659 | 98.719 / 47.766 | 42.352 / 9.958 | 4.297 / 5.250 |
| http2 / protocol-scope / uvloop | 146.4 / 41.935 | 99.656 / 48.375 | 42.275 / 10.003 | 4.281 / 6.344 |
| http2 / fixed / asyncio | 147.5 / 48.208 | 99.547 / 47.578 | 42.852 / 9.927 | 4.328 / 5.234 |
| http2 / fixed / uvloop | 145.1 / 41.011 | 100.3 / 48.570 | 42.470 / 9.939 | 4.438 / 6.414 |
| http2 / large-response / asyncio | 4,122.3 / 574.1 | 425.1 / 47.320 | 1,597.8 / 1,118.0 | 6.734 / 7.547 |
| http2 / large-response / uvloop | 3,959.3 / 561.7 | 508.1 / 48.719 | 1,570.8 / 1,118.3 | 6.750 / 7.688 |
| http2 / many-response-chunks / asyncio | 5,339.3 / 7,535.4 | 341.3 / 48.375 | 1,615.2 / 2,646.9 | 6.750 / 5.781 |
| http2 / many-response-chunks / uvloop | 4,981.3 / 5,654.5 | 391.9 / 49.547 | 1,578.9 / 2,566.0 | 6.656 / 5.766 |
| http2 / request-upload / asyncio | 4,025.7 / 3,224.4 | 409.8 / 143.5 | 1,044.3 / 860.3 | 6.359 / 13.547 |
| http2 / request-upload / uvloop | 3,164.0 / 2,414.5 | 389.2 / 162.5 | 1,038.4 / 835.6 | 6.406 / 13.797 |
| http2 / request-upload-small-chunks / asyncio | 860.6 / 2,613.3 | 112.1 / 64.203 | 213.8 / 184.3 | 5.109 / 8.250 |
| http2 / request-upload-small-chunks / uvloop | 835.4 / 1,936.7 | 114.0 / 65.969 | 215.2 / 179.9 | 4.688 / 8.531 |
| http2 / slow-reader-backpressure / asyncio | 16,000.4 / 24,544.9 | 122.4 / 44.711 | 6,295.0 / 18,071.1 | 6.688 / 7.031 |
| http2 / slow-reader-backpressure / uvloop | 13,797.1 / 18,971.4 | 126.3 / 46.031 | 6,302.9 / 18,555.4 | 6.750 / 6.938 |
| websocket / connection-handshake / asyncio | 281.1 / 152.3 | 46.359 / 44.984 | 65.246 / 56.220 | 2.516 / 2.672 |
| websocket / connection-handshake / uvloop | 230.3 / 125.3 | 47.734 / 46.172 | 61.086 / 55.466 | 2.484 / 2.562 |
| websocket / text-echo / asyncio | 17.316 / 48.117 | 49.711 / 59.938 | 11.080 / 10.209 | 16.727 / 13.383 |
| websocket / text-echo / uvloop | 14.894 / 31.846 | 50.758 / 64.930 | 10.642 / 9.822 | 16.680 / 13.461 |
| websocket / binary-64k-echo / uvloop | 35.699 / 46.067 | 115.5 / 95.609 | 22.393 / 23.835 | 30.078 / 28.703 |

## Lifecycle

Startup is a preparation-to-observed-response upper bound. CPU is complete reaped-server lifetime seconds, with idle and active phases kept separate.

| Loop | Pairs | Startup ms ref / Rust | Idle exit ms ref / Rust | Held exit ms ref / Rust | Idle CPU s ref / Rust | Active CPU s ref / Rust | Idle RSS MiB ref / Rust | Active RSS MiB ref / Rust |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| asyncio | 3 | 153.9 / 132.7 | 195.0 / 22.609 | 2,206.2 / 2,036.5 | 0.143 / 0.140 | 0.149 / 0.149 | 42.609 / 40.812 | 42.688 / 40.938 |

## Exclusions and incomplete inputs

- http1 invalid row reasons: timing_valid_false_or_missing=135; unrelated_host_cpu_activity=135.
- http1/fastapi-fixed/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-fixed/uvloop: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-large-response/uvloop: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-small-response-chunks/asyncio: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-small-response-chunks/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-request-upload/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-request-upload/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-1k/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-16k/asyncio: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-16k/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-256k/asyncio: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-256k/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-1m/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-upload-1m-write-1m/uvloop: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-request-upload-small-chunks/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-request-upload-small-chunks/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-slow-reader-backpressure/asyncio: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http1/fastapi-slow-reader-backpressure/uvloop: 1 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- http2 invalid row reasons: timing_valid_false_or_missing=5; unrelated_host_cpu_activity=5.
- http3/protocol-scope-consumed-request/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/protocol-scope-consumed-request/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/protocol-scope/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/protocol-scope/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/fixed/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/fixed/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/large-response/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/large-response/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/many-response-chunks/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/many-response-chunks/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/request-upload/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing; target_only_no_live_reference_pair.
- http3/request-upload/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing; target_only_no_live_reference_pair.
- http3/slow-reader-backpressure/asyncio: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- http3/slow-reader-backpressure/uvloop: 0 matching valid repetitions; category_completion_metadata_missing; category_incomplete; driver_category_clean_owned_process_exit_missing_or_failed; driver_category_correctness_gate_missing_or_failed; driver_category_exit_not_successful; driver_category_plan_or_identity_gate_missing_or_failed; driver_category_report_hash_differs_or_missing; driver_category_row_count_differs_or_missing; fewer_than_required_matching_valid_repetitions; recorded_dependency_identities_differ_or_missing; recorded_identity_not_stable_or_missing; recorded_pair_gate_missing_or_duplicate; recorded_source_native_client_identities_differ_or_missing.
- websocket invalid row reasons: timing_valid_false_or_missing=9; unrelated_host_cpu_activity=9.
- websocket/binary-64k-echo/asyncio: 2 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.
- lifecycle invalid row reasons: timing_valid_false_or_missing=7; unrelated_host_cpu_activity=7.
- lifecycle/lifecycle/uvloop: 0 matching valid repetitions; fewer_than_required_matching_valid_repetitions; recorded_pair_gate_not_available.

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
