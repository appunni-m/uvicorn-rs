# 491-case ASGI parity and Rust coverage after the HTTP receive coverage fix

Measured locally on 2026-10-07 from the working tree at revision `dc8cf3f58623b761d7187153d5e96636bbdd77be`. This archive preserves the complete unified LLVM report, its Coverage-MCP receipt, all three verification repeats, and a separate normal-build parity result.

## Result

All 491 indexed cases passed attribution: 239 live oracle comparisons and 252 target-only fault contracts. Three complete 491/491 repeats passed. There were zero behavior failures, infrastructure failures, transient retries, or cases not run. A single infrastructure-only retry was permitted for attribution but was not used.

Native coverage for default-feature `src/lib.rs` is **5,121/5,121 regions** and **3,624/3,624 lines (100%)**. Coverage-MCP measured this exact report with `source: matches_receipt`, `tests: passed`, and zero gap groups. Per-case attribution matches the aggregate profile union.

The rebuilt normal, non-instrumented extension passed all 239 live oracle comparisons. The change measured here only removes a conditional around a `cfg(coverage)` diagnostic inside the HTTP receive lock-contention path; it does not alter production builds.

## Identity and scope

The checkout was dirty at revision `dc8cf3f58623b761d7187153d5e96636bbdd77be`. The `src/lib.rs` SHA-256 is `1a0c90dbdd08e7f6172a1a6d6f6928f021bd473d74836ee7eeb853e1fb4d55a4`; the aggregate source/input SHA-256 is `dba61473dae213fa5336d8d9c29e03ffd8a9ae6476fcd9fa0ac9c37061c20830`. The instrumented extension SHA-256 is `2fcd0eeb88f38d7c07801335e37416837761fd0d4a340d86aab57ba8638dc2d5` and the normal extension SHA-256 is `0e75d893144bb2a87819904e7356a532ca844eaef7b35d16d97b54e6cffb1485`. The report SHA-256 before compression is `4478d365b091dc9094462c13903c3e49d2450ff9f90f5dd8f4cf89a8f2e3bf8e`; the Coverage-MCP build ID is `93a183b2b3a8330d6ad74e170416c68c456b658d884be7f3a96dc637b0d337dc`.

The instrumented run used CPython 3.12.13, rustc 1.98.1 (48a229cea 2026-09-01), cargo-llvm-cov 0.8.7, and macOS-15.7.7-arm64-arm-64bit. The denominator is default-feature `src/lib.rs` built with `cfg(coverage)`. Python code, dependencies, optional diagnostic features, other platforms, the official full ASGI conformance suite, and performance are outside this coverage claim.

The attached older hosted run [37603449348](https://github.com/appunni-m/uvicorn-rs/actions/runs/37603449348) was on commit `6b28666` with 490 cases. It recorded an H3 infrastructure failure (`http3.asgi-event-type-string-subclass`), one infrastructure failure plus one not-run case in each repeat, and 5,106/5,108 regions. That report predates this local source measurement and does not contradict it. Hosted verification of this exact source change is still pending.

## Reproduction

```sh
uv run --python 3.12 --locked --group benchmark python scripts/run_unified_coverage.py \
  --output target/asgi-coverage/local-coverage-region-fix-retry-2026-10-07/coverage-report.json \
  --artifacts-dir target/asgi-coverage/local-coverage-region-fix-retry-2026-10-07/artifacts \
  --case-infra-retries 1 --matrix-infra-retries 0
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
uv run --python 3.12 --locked --group benchmark python scripts/run_parity.py \
  --output target/asgi-coverage/local-coverage-region-fix-retry-2026-10-07/normal-parity-239.json
uv run --python 3.12 --locked --group benchmark python scripts/attach_coverage_mcp.py \
  --report target/asgi-coverage/local-coverage-region-fix-retry-2026-10-07/coverage-report.json \
  --receipt target/asgi-coverage/local-coverage-region-fix-retry-2026-10-07/coverage-mcp-receipt.json
```

Coverage-MCP was queried with `coverage_gaps` for the exact report, `metric: regions`, `limit: 15`; its structured page is preserved as `coverage-mcp-pages.json` and attached with `scripts/attach_coverage_mcp.py`.

## Additional checks

The repository's Rust formatting check, Clippy checks for the main crate and
HTTP/3 probe with `-D warnings`, `git diff --check`, and offline
`scripts/check_ci_evidence.py coverage ... --offline` all passed. The offline
evidence check validated the retained report and context without importing the
currently installed extension.

## Files

- `coverage-report.json.gz`: unified report with per-case results, region attribution, and attached Coverage-MCP evidence.
- `coverage-report.json.context.json`: report hash, source, build, and test receipt.
- `coverage-mcp-pages.json`: exact structured Coverage-MCP response.
- `matrix-repeat-results.tar.gz`: raw result JSON for each of the three complete repeats.
- `normal-parity-239.json`: full normal-build oracle result.
- `evidence-index.json`: checksums, environment, source/build identities, and summary totals.
