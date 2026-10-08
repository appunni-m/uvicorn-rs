# Multi-system benchmark results

No completed result from the automated three-system benchmark matrix has been
archived yet. The first complete run will replace this page through the
benchmark documentation update PR.

The automated matrix is configured for Ubuntu 24.04 x86_64, Ubuntu 24.04 arm64,
and macOS 15 arm64. It runs the public parity gate before measuring HTTP/1.1,
HTTP/2, HTTP/3, WebSockets, and lifespan/shutdown. Each system is reported
separately. A performance row requires at least three matching valid
repetitions; invalid rows are retained and excluded from comparisons.

Historical runs remain in the [performance feasibility report](feasibility.md)
and their source-specific archives. They are not results for the current source
revision. See the [benchmark methodology](benchmarks.md) for workloads, runner
identity, resource accounting, and interpretation limits.
