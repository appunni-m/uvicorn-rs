# 491-case unified coverage after the EOF recheck contract assertion

Measured on 2026-10-08 from the working tree at revision `1a72c9b3ab18e01389b1e19efbc76bf569e98730`. The archive preserves the exact unified LLVM report and context, the paginated Coverage-MCP response, each full repeat result, and the focused H2 EOF-recheck case result.

## Result

Per-case attribution passed **491/491** cases: **239/239** live oracle comparisons and **252/252** target-only fault contracts. Each of the three complete repeats passed **491/491**, with zero behavior failures, infrastructure failures, retries, or cases not run. Attribution matches the aggregate profile union.

Native coverage is **5121/5121 regions** and **3624/3624 lines (100%)**. Coverage-MCP measured the exact report with `source: matches_receipt`, `tests: passed`, and zero gap groups.

The `fault.http2.connection-disconnect-completes-eof-recheck` contract now requires the test harness to observe consumption of the injected EOF-recheck pause before sending its follow-up request. The focused case passed with a 200 follow-up. The previous implementation could report success without proving that the injected pause ran. A fresh instrumented build was used; an earlier `--skip-build` attempt had no target profile and was discarded.

## Source and build identity

The worktree was dirty at revision `1a72c9b3ab18e01389b1e19efbc76bf569e98730`. `src/lib.rs` SHA-256: `1a0c90dbdd08e7f6172a1a6d6f6928f021bd473d74836ee7eeb853e1fb4d55a4`. `scripts/run_parity.py` SHA-256: `a61d16ea5d1432ece5bac31aebbee7c99124a57877e60c4e781ded55909b9ee7`. Aggregate source/input SHA-256: `9c52350403f9bee48166ede3230e87d083f845bf134da0f70297120e7feede84`. Input manifest SHA-256: `35abb756dda4bc53e6e62e616f08722b9e53de1094317cc77972f668f8dc3972`. Instrumented extension SHA-256: `2fcd0eeb88f38d7c07801335e37416837761fd0d4a340d86aab57ba8638dc2d5`. Coverage-MCP build ID: `93a183b2b3a8330d6ad74e170416c68c456b658d884be7f3a96dc637b0d337dc`. Report SHA-256 before compression: `bc49875bbdbdc0486465de314101b5124a552476a650296871171e9fe79129e1`.

Environment: CPython 3.12.13, rustc rustc 1.98.1 (48a229cea 2026-09-01), cargo-llvm-cov cargo-llvm-cov 0.8.7, macOS-15.7.7-arm64-arm-64bit.

This is local working-tree evidence. It is not a clean hosted release baseline, a performance benchmark, or a claim of full Uvicorn/ASGI compatibility. The separate installed-wheel parity and hosted coverage jobs are tracked in [coverage.md](../../../../docs/coverage.md).

## Reproduction

```sh
uv run --python 3.12 --locked --group benchmark python scripts/run_unified_coverage.py \
  --output target/asgi-coverage/local-eof-fault-consumed-2026-10-08/coverage-report.json \
  --artifacts-dir target/asgi-coverage/local-eof-fault-consumed-2026-10-08/artifacts
uv run --python 3.12 --locked --group benchmark python scripts/attach_coverage_mcp.py \
  --report target/asgi-coverage/local-eof-fault-consumed-2026-10-08/coverage-report.json \
  --receipt target/asgi-coverage/local-eof-fault-consumed-2026-10-08/coverage-mcp-pages.json
```

## Files

- `coverage-report.json.gz`: full per-case results and region attribution, with Coverage-MCP evidence attached.
- `coverage-report.json.context.json`: report digest and source/build/test receipt.
- `coverage-mcp-pages.json`: exact structured Coverage-MCP response.
- `matrix-repeat-results.tar.gz`: result JSON files from all three complete repeats.
- `eof-recheck-case/`: focused fault-contract result and logs.
- `evidence-index.json`: checksums, environment, identities, and case/repeat totals.
