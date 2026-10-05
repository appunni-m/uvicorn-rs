# Initial synchronized category attempt

This archive preserves the completed initial attempt and its unfinished H3 checkpoint. The intended 171-row matrix was not fully executed. Four complete categories contain 138 rows (H1 72, H2 42, WebSocket 18, lifecycle 6), and the H3 checkpoint contains one completed Rust row: 139 recorded rows in total. All completed rows report zero response/lifecycle failures.

The stock Hypercorn H3 protocol-scope warmup failed in repetition 1 with 64 response-header timeouts. Its server log retains the ExceptionGroup and KeyError(4140). No completed Hypercorn H3 performance row or final H3 report exists. The raw log and checkpoint are preserved unchanged.

The recorded analyzer reports incomplete_categories and zero qualified matching pairs. Contention, missing repetitions, incomplete H3 evidence and unequal exception diagnostic policies remain explicit exclusions; this archive establishes no speedup. The experiment used a frozen dirty local checkout, normal native SHA 8f69afda0be9d121d304c674d5638f470da6939fbed58ce809457284df6585b6 and src/lib.rs SHA 81c239b5f596cf4be18cc71bc3b537c02224c0f1e1ab35174e6386f5203510cd.

Original reports, metadata, JSONL checkpoints, logs, artifacts and analysis files are byte-identical copies. Absolute paths in those files retain their original locations. evidence-snapshot/ preserves the measured sources plus the exact task-local runner and analyzer; its framework build receipt describes the separately installed normal fixture wheel. No binaries are copied. archive-manifest.json records original paths, sizes and SHA-256 values.
