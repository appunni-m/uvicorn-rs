# 491-case ASGI parity and Rust coverage

Measured on 2026-10-07 from the local macOS ARM64 checkout. This archive
records the full indexed matrix after adding parity for an empty WebSocket
subprotocol token.

## Result

The manifest ran 491 cases: 239 live oracle comparisons and 252 target-only
contracts. All 491 cases passed attribution and each of three full repeats;
there were no failures, infrastructure failures, transient retries, or cases
not run. Normal non-instrumented parity passed 239/239.

LLVM coverage is 5,123/5,123 regions and 3,628/3,628 lines in `src/lib.rs`.
Coverage-MCP queried this exact report and found zero gap groups with
`source: matches_receipt` and `tests: passed`. Case attribution matches the
union of per-case profiles.

The new case, `websocket.empty-subprotocol-token-handshake-rejected`, sends an
empty `Sec-WebSocket-Protocol` value. Before the fix, uvicorn-rs accepted the
upgrade and invoked the app while Uvicorn rejected the handshake with HTTP
400. The Rust server now rejects the empty comma-list token before ASGI scope
construction; both live servers return HTTP 400. The scope-side empty-token
filter was removed because this malformed header is rejected before dispatch.

## Identity and scope

The checkout was dirty at revision
`d66548a5f0be8b51bc85245255d07741a60317ba`. The Rust source SHA-256 is
`e8d8510f49992ccb6dc39e529d478ec2f06861674e0678044863ca4aa12d4dbd`; the
source/input aggregate SHA-256 is
`0fb80c4486587dae82da9c28fa1b321924cf4533b05ea8477d15cff83fbf6949`.
The instrumented extension SHA-256 is
`391929f43630a4b4e13feb6570a1d4e522dcf8a8bc24e984f8f30ab52f0aca2c`.

The run used CPython 3.12.13, Rust 1.98.1, cargo-llvm-cov 0.8.7, and macOS
15.7.7 ARM64. Coverage measures default-feature `src/lib.rs` with
`cfg(coverage)`. It excludes Python code, dependencies, optional diagnostic
features, other platforms, the official full ASGI suite, and performance.
The results are local working-tree evidence, not a clean release build or a
hosted Linux result.

The uploaded hosted log available during this run showed expected lifecycle
fault-case tracebacks followed by `PASS` lines, then an older 238-case summary
with one infrastructure failure and one case not run. It did not identify the
failing case or include `coverage-report.json`; that hosted failure remains
unresolved by this local measurement.

## Reproduction

```sh
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
uv run --group benchmark python scripts/run_parity.py \
  --output target/asgi-coverage/normal-parity.json
uv run --group benchmark python scripts/run_unified_coverage.py \
  --output target/asgi-coverage/unified/coverage-report.json \
  --artifacts-dir target/asgi-coverage/unified/artifacts \
  --case-infra-retries 0 --matrix-infra-retries 0 --matrix-repeats 3
```

Query Coverage-MCP `coverage_gaps` against the exact report with
`metric=regions`, preserve the structured page array, then attach it:

```sh
uv run --group benchmark python scripts/attach_coverage_mcp.py \
  --report target/asgi-coverage/unified/coverage-report.json \
  --receipt target/asgi-coverage/unified/coverage-mcp-pages.json
```

## Files

- `coverage-report.json.gz`: full unified LLVM report with case-to-region
  attribution and attached Coverage-MCP receipt.
- `coverage-report.json.context.json`: report, source, build, and test receipt.
- `coverage-mcp-pages.json`: exact structured Coverage-MCP response.
- `matrix-repeat-results.tar.gz`: three complete repeat results and identities.
- `normal-parity-239.json`: complete normal-build live oracle result.
- `evidence-index.json`: artifact hashes, source/build identities, and totals.
