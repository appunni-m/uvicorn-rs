# Latest automated benchmark attempt

- Run: [37718341537 (attempt 1)](https://github.com/appunni-m/uvicorn-rs/actions/runs/37718341537)
- Commit: [`faf533910909d75dd9a3671a48add79e066ee711`](https://github.com/appunni-m/uvicorn-rs/commit/faf533910909d75dd9a3671a48add79e066ee711)
- Recorded: 2026-10-08
- Status: all three hosted jobs failed in the server wheel setup step, before parity or timed benchmark results were produced.

The run exposed a malformed wheel-discovery command in the workflow. The prior
attempt, [run 37718066529](https://github.com/appunni-m/uvicorn-rs/actions/runs/37718066529),
also stopped during setup because macOS Bash 3.2 does not provide `mapfile`; that
portability issue was fixed in commit `faf5339`.

See the [latest complete results](benchmark-results.md) for the last archived
measurements, and the [benchmark guide](benchmarks.md) for the methodology.
