# Benchmark and release-gate status

## Local matched benchmark

The latest local five-category run is documented in the
[FastAPI benchmark results](benchmark-results.md). It used stock FastAPI and
one configured Tokio async worker. H1, H2, WebSocket, and lifecycle passed
520 correctness rows and produced 32 qualified workload/loop comparisons.
H3 stopped at the correctness gate when Hypercorn/uvloop timed out on the
concurrency-64 reference case. These are one-host, dirty-checkout measurements;
they do not establish a cross-platform performance claim.

The [494-case ASGI evidence archive](../benchmarks/results/2026-10-09/asgi-unified-coverage-494/)
records 240 oracle cases, 254 fault contracts, three complete repeats,
5,298/5,298 native regions, 3,753/3,753 lines, and 240/240 normal-wheel
parity. This is local macOS arm64 evidence on the dirty `f260d78` source and
does not replace hosted verification of the exact commit.

## Latest hosted benchmark workflow

The latest automated three-system run is
[37885559188](https://github.com/appunni-m/uvicorn-rs/actions/runs/37885559188)
on `f260d78`. It completed with failure on Linux x86_64, Linux arm64, and
macOS arm64. Linux x86_64 and macOS arm64 failed the exact-wheel parity gate;
Linux arm64 passed parity and then failed during the sequential category
benchmark. Per-system artifacts were uploaded, but this session cannot
download the logs or artifacts without an authenticated GitHub session. The
failure causes and arm64 timing rows therefore remain unknown. There is no
validated three-system aggregate.

## Latest hosted correctness and release CI

The latest CI run is
[37885559203](https://github.com/appunni-m/uvicorn-rs/actions/runs/37885559203)
on `f260d78`. Rust quality and the minimum-Rust-version job passed. Installed
wheel parity and unified coverage failed; package preparation and Python-floor
jobs were skipped. Anonymous job-log access does not expose the failing cases,
so the local 494-case pass cannot be presented as hosted verification.

No candidate bundle for this exact source has passed the release gates. No
tag, GitHub Release, crates.io publication, or PyPI package was created. The
candidate process is documented in [release status](releases.md).

## Reproduction

Use the maintained setup and commands in the
[benchmark guide](benchmarks.md). Keep the exact source, native extension,
FastAPI app, Python and dependency versions fixed; run the full parity gate
before timing; retain every rejected row; and report each protocol/reference
separately. A failed reference workload is an incomplete comparison, not a
performance result.
