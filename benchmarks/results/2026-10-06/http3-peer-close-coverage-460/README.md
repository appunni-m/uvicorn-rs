# HTTP/3 peer-close correctness evidence

This archive records the October 6, 2026 verification of unknown HTTP/3
application close-code handling.

## Results

- Unified matrix: 460/460 cases, with three complete 460/460 repeats.
- Matrix composition: 221 live oracle comparisons and 239 target-only
  contracts, across 70 input files and 64 operations.
- Native coverage: 4,810/4,810 regions and 3,395/3,395 lines.
- Coverage MCP: exact report measured; source matches receipt; tests passed;
  zero missing regions and zero gap groups.
- Normal wheel: 221/221 public parity cases; 16/16 exclusion checks and 3/3
  selected public cases.

The 460-case report SHA-256 is
`c45f978fc76174636ecb7d4062d23e68c4084e2fc7355d090aff99823f606d53`. The
normal parity result SHA-256 is
`eea7e61ff11934b1c0107cfd38d01cc792ff0fe260fed73dcedf6eb92e3551a7`. The
[evidence index](evidence-index.json) lists the source, manifest, build, and
retained-file hashes.

## Reproduce

From the recorded checkout, run the complete unified attribution and repeat
gate:

```sh
PATH="target/release-tool-env-2026-10-05/bin:$PATH" \
  .venv/bin/python scripts/run_unified_coverage.py \
  --output build/kata-migration-2026-10-06/h3-close/coverage-final-460.json \
  --artifacts-dir build/kata-migration-2026-10-06/h3-close/coverage-final-460-artifacts \
  --matrix-repeats 3 --case-infra-retries 0 --matrix-infra-retries 0
```

Query Coverage MCP for regions on that exact report. The saved
`coverage-mcp-full-response.json` contains the structured response and report
hash. Then validate the retained gate offline:

```sh
.venv/bin/python scripts/check_ci_evidence.py --offline coverage \
  build/kata-migration-2026-10-06/h3-close/coverage-final-460.json
.venv/bin/python scripts/check_ci_evidence.py --offline parity \
  build/kata-migration-2026-10-06/h3-close/normal-parity-221.json
```

The normal parity report records the imported wheel extension SHA-256 and all
fixture, runner, dependency, and environment identities. The exclusion bundle
retains native inspection outputs, logs, the selected workflow result, and its
receipt; the normal wheel's identity is recorded by SHA-256.

## Scope

This is local dirty-checkout evidence from macOS 15.7.7 ARM64, CPython 3.12.13,
and Rust 1.98.1. Its measured revision is
`fce9706c8d7eb21c999989c729b01242b9421731`. It is not a clean release
baseline, a complete official ASGI conformance result, or performance evidence
for the October 6 source. QUIC transport `CONNECTION_CLOSE` behavior is outside
the tested application-close cases.
