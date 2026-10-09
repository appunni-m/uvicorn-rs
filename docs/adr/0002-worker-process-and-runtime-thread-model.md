# ADR 0002: Single-process runtime and worker scope

- **Status:** Accepted. Process workers and their supervisor are outside the current project scope.
- **Date:** 2026-10-09
- **Related:** [ADR 0001](0001-runtime-and-asyncio-bridge.md), KATA issue `sjc2`.

## Context

The current server runs in one process. That process owns one Python event loop
for ASGI callbacks and one Tokio core worker thread for Rust networking. Python
application code stays on the loop that loaded and serves the app; Tokio does
not execute FastAPI handlers. PyO3 bridge work may also use Tokio's blocking
pool, so “one Tokio worker” does not mean the process has only one thread.

Processes cannot share Tokio threads. A Uvicorn-style worker feature would
therefore require separate processes, each with its own interpreter, GIL,
Python loop, app instance, lifespan, and Tokio runtime, plus listener sharing,
supervision, failure propagation, cancellation, and child reaping. HTTP/3 would
add a QUIC connection-affinity requirement. The original MVP scope excludes
worker/process supervision, and the current one-process benchmark does not
prove a benefit from adding it.

## Decision

Keep one server process and one Tokio core worker per process for the current
CLI. Keep ASGI callable execution, task creation, `contextvars`, and exception
behavior on the Python-owned event loop. Do not add a `--workers` option or
claim multi-core Python execution in this scope.

Any future worker proposal requires a separate scope decision. It must first
compare matched Uvicorn and `uvicorn-rs` runs at 1, 2, and 4 processes for both
I/O-bound and deterministic Python CPU-bound FastAPI workloads, then specify
listener sharing and prove startup, lifespan isolation, worker failure,
cancellation, signal shutdown, and child cleanup. Tokio thread-count changes
must be measured separately from process-count changes.

## Consequences

- The supported CLI remains single-process; worker supervision is not part of
  the support matrix.
- Python CPU-bound callbacks remain subject to the interpreter's GIL. Tokio
  worker count does not change that behavior.
- The current single-process FastAPI results cannot be used to predict
  multi-worker scaling.
- Worker design and benchmarks are deferred; the current implementation keeps
  the simpler ASGI and lifecycle model required by the MVP.
