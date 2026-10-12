# ASGI inventory 485 evidence

This archive records the 2026-10-07 live ASGI input matrix and its normal-wheel
verification. The matrix contains 485 cases across 70 input files and 66
operations: 233 live oracle comparisons and 252 target-only contracts. One
attribution pass and three full repeats passed all 485 cases with no failures,
infrastructure errors, retries, or skipped cases.

The instrumented default-feature `src/lib.rs` build measured 5,106/5,106 LLVM
regions and 3,606/3,606 lines. Coverage MCP matched the report receipt and
returned zero region gaps. These figures cover Rust source regions only; they
do not measure Python code or establish full ASGI conformance.

The separately installed macOS ARM64 abi3 wheel passed its package-consumer
probe and all 233 public oracle comparisons. Its normal-build exclusion audit
passed 16 checks over three selected public workflows and found all 221
registered fault points absent from the imported wheel.

## Evidence files

- [`evidence-index.json`](evidence-index.json) records the run identities,
  environment, counts, and SHA-256 values.
- The generated report (`coverage-report-isolated.json.gz`), context sidecar,
  full Coverage-MCP response, and structured receipt remain local-only and are
  not committed.
- Generated full-matrix artifact bundle (`full-matrix-artifacts-isolated.tar.gz`)
  contains per-case logs and profiles; it remains local-only and is not committed.
- [`normal-parity-isolated.json.gz`](normal-parity-isolated.json.gz) preserves
  the 233-case normal-wheel result.
- [`wheel-consumer-isolated.json`](wheel-consumer-isolated.json) records the
  installed wheel hash and HTTP, asyncio context, cancellation, TLS, and
  shutdown checks.
- The generated normal-exclusion audit bundle is local-only because it contains
  logs. The tracked [`normal-exclusion-receipt-final.json`](normal-exclusion-receipt-final.json)
  records the final 16-check audit, repeated after aligning the offline evidence
  checker with the manifest's comparison fields.
- [`offline-validation.json`](offline-validation.json) records successful
  CI evidence checks run after restoring the local compressed matrix artifacts.
- The generated `run-isolated.log` remains local-only and is not committed. The
  focused
  [`TLS WebSocket diagnostic`](tls-websocket-isolation-diagnostics.json)
  records the observed profile-reuse handshake flake and the isolated runs.

The [`preliminary-retry-tolerant/`](preliminary-retry-tolerant/) folder keeps
the earlier diagnostic report separate. It is not the final no-retry evidence.
The final matrix isolates the TLS WebSocket close case with a fresh server
lifetime, avoiding profile-level listener reuse at the boundary that showed
intermittent timeouts. No artificial delay was added.

The response-header probe records exact wire order for H1/H2, but its parity
comparison compares repeated values per header name. Cross-name response order
is a known H1/H2 ASGI deviation; the H3 client does not expose raw wire order.
See the [support matrix](../../../../docs/support-matrix.md)
and [case inventory](../../../../docs/asgi-case-inventory.md). Passing this
archive does not establish full ASGI conformance, complete HTTP security
coverage, or a performance improvement.
