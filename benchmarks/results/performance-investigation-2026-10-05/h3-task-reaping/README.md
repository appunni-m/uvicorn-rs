# HTTP/3 request-task reaping evidence

`before/` and `after/` retain every original report, JSONL row, provenance
sidecar, runner log and individual server log as byte-identical copies, with
original paths preserved in `archive-manifest.json`. Each arm additionally has
a source snapshot checked against every measured source-file SHA. Binaries are
identified by SHA but are not stored here. The original files remain unchanged.

Read [analysis.md](analysis.md) for descriptive sampled-RSS observations and
[analysis.json](analysis.json) for exact values, request counts, raw timing flags,
identities and limitations. All ten Rust runs passed response and graceful exit
checks. The two before timing-valid rows and zero after timing-valid rows yield
zero qualified matching speed pairs. The RSS medians include timing-invalid
runs explicitly; they are not throughput, latency or CPU evidence.

This is a target-only memory diagnostic. Before ran entirely before after and
the fixed-duration closed-loop windows completed different request counts. The
source mechanism is completed `JoinSet` task allocations retained until joining;
the change reaps them during acceptance. RSS is not a heap allocation profile,
an allocator-peak measurement, or proof of a Python-payload leak.

The before normal release identity is in `../current-normal/`; the changed
normal release identity/source/build/fmt/Clippy logs are in
`../current-normal-h3-reaping/`. Public parity for that changed binary is pending
in this archive until its owner appends the completed exact-binary gate. The
separate `../h3-diagnostics/` preserves stock Hypercorn failures and a low-load
functional observation without converting them into benchmark rankings.

`archive-h3-reaping.py` is the original stdlib-only archive/derivation command,
retained for inspection. It copies and hashes existing artifacts only and was
not used to execute an application, benchmark, build or probe.
