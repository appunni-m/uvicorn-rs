# HTTP/1 clean retry

A separate attempt using the same frozen source and normal native extension. All 30 completed rows report zero failures. Eleven individual timing rows were valid and 19 were invalid.

| Workload | Valid matching repetitions | Required | Qualified |
| --- | --- | ---: | --- |
| contextvars | None | 3 | No |
| fixed | 2, 3 | 3 | No |
| large-response | 1, 3 | 3 | No |
| many-response-chunks | None | 3 | No |
| scope-32-headers | 1 | 3 | No |

The five matched repetitions across three workload groups correspond to ten paired rows; one additional valid individual row has no matching valid partner. Counts from different workloads cannot be combined to satisfy the three-repetition gate. No workload qualifies for a speedup or ratio, and performance_evidence_status remains not_proven.

Original JSON, JSONL, metadata, runner log and all server artifacts are byte-identical copies. Their original paths are retained. summary.json copies the recorded pair metadata without recomputing or promoting its outcomes. Declared source hashes match the sibling categories-error-logs/evidence-snapshot; no binaries are copied.
