# Benchmark preflight rejected: 2026-10-04

No correctness probe or benchmark category was started in this directory. The
initial environment snapshot was captured at 2026-10-04T16:46:44Z, but a later
preflight found unrelated work on the shared host, including concurrent Rust
compilation (peaking above eight logical CPUs), Python parity/API-surface
validation in other project checkouts, and an Android emulator. These workloads
violate the documented quiet-host gate. This directory contains setup metadata
only and is not performance evidence.

The adjacent `starlette-rs` checkout was clean when inspected at revision
`cc2f2795e9bbbbfb95a7bdf1271db13fa37c1aa4`; a neighboring benchmark updated
only `docs/BENCHMARKS.md` afterward. The editable install is present in this
repository's benchmark virtual environment and does not add a runtime
`starlette-rs` dependency to `uvicorn-rs`.

Start a new run with a new UTC directory after the shared host's build and
validation jobs are quiet. Recapture the environment and process snapshots
immediately before the correctness probes and each benchmark category.
