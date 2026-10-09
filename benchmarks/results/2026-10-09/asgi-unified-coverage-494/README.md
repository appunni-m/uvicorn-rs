# Unified ASGI coverage evidence (494 cases)

This is the current local full-matrix coverage receipt for the dirty working tree based on `f260d78c71e9266c2b3301ab3915f74de5511fc2`. It includes 240 live oracle-parity cases and 254 target-only fault contracts, all three complete repeats, and the final real-backpressure WebSocket frame-drain parity case.

| Gate | Result |
|---|---:|
| Per-case attribution | 494/494 passed |
| Full repeat 1 | 494/494 passed |
| Full repeat 2 | 494/494 passed |
| Full repeat 3 | 494/494 passed |
| Oracle cases | 240/240 passed |
| Fault contracts | 254/254 passed |
| Rust regions | 5,298/5,298 (100%) |
| Rust lines | 3,753/3,753 (100%) |
| Coverage-MCP gaps | 0 region groups; 0 line groups |
| Normal-wheel public parity | 240/240 passed |

Coverage-MCP reports `source: matches_receipt` and `tests: passed`, build ID `78576a3a519fb09c8d8a54b03166afe77e645d745f98eb7e73bd1974c8822a8c`. The source file `src/lib.rs` SHA-256 is `56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; the normal extension SHA-256 is `94c677f0e37a52bd80d81571997443a60d69379c16bb2acdcf9831bddb0499b0`. This measures default-feature coverage of the declared Rust source scope on macOS arm64. It does not prove full ASGI conformance, every feature/platform, clean-commit hosted verification, or performance.

## Evidence files

- [Compressed unified report](coverage-report.json.gz) and [context receipt](coverage-report.json.context.json)
- [Coverage-MCP region and line receipt](coverage-mcp-all-metrics.json)
- [Normal non-instrumented 240-case public parity result](normal-public-parity-240.json.gz)
- [Source/build manifest](source-manifest.json) and [three repeat outcomes](verification-runs.json)

The report was generated on CPython 3.12.13, Rust 1.98.1, macOS 15.7.7 arm64. The executable normal-wheel parity used the exact extension hash listed above.
