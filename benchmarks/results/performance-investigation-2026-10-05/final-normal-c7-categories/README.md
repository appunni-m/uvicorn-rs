# Final normal-build category run

Source `c7bd49…`, normal native `0e13bb…`, CPython 3.12.13; same apps and stock reference dependencies. The exact pre-captured 214-case public parity gate is in `run.json`. The driver planned 177 samples and retained 139 completed rows; H3 stopped after stock Hypercorn failed the additive consumed-request workload with 16 header timeouts. Four independent categories completed all response/lifecycle checks.

The analyzer qualifies WebSocket connection handshakes only: three matched valid repetitions, median same-repetition Rust/Uvicorn throughput ratio 1.590. Other timings are excluded or insufficient; the lone valid Rust H3 row cannot produce a comparison. This is frozen dirty local, same-host closed-loop evidence, not a release or general server speed claim.

All original reports, checkpoints, logs, process cleanup and identity records are copied unchanged. Source snapshots use lossless gzip to avoid introducing new source paths into the editable-dependency identity inventory. `archive-manifest.json` records copied and decompressed hashes. No row is removed for failure or host contention.
