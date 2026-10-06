# Request-body pump ownership evidence (2026-10-06)

This archive binds one dirty-checkout source snapshot to a complete unified
instrumented run, the exact Coverage-MCP query response, and a normal installed
wheel run. It records local macOS ARM64 evidence; it is not a clean release
baseline.

The unified manifest contains 473 workflows: 225 live oracle comparisons and
248 target-only contracts. Per-case attribution and each of three complete
repeats pass without failures, infrastructure errors, retries or omissions.
Native `src/lib.rs` coverage is 5,106/5,106 regions and 3,606/3,606 lines.
Coverage-MCP identifies the same source receipt and reports zero missing
regions and zero gap groups.

The release-mode abi3 wheel passed the same 225 public oracle cases. The normal
binary exclusion audit passed all 16 checks and its three selected workflows
(one oracle case and two public capacity contracts). The full coverage report
is compressed losslessly; its context sidecar, normal parity result and audit
receipt accompany it. The audit bundle retains inspection outputs.

`evidence-index.json` records SHA-256 identities, Python/Rust versions,
platform, manifest, native binaries, case counts and repeat summaries. Historical
coverage and performance records remain in the project docs; this archive
contains no benchmark claim and does not establish official full ASGI
conformance.
