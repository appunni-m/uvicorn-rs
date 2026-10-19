# ADR 0002: Single-process prototype and worker migration

- **Status:** The current prototype is single-process. Excluding workers from the release target is superseded by [ADR 0005](0005-uvicorn-public-compatibility-contract.md).
- **Date:** 2026-10-09
- **Related:** [ADR 0001](0001-runtime-and-asyncio-bridge.md), Kata issue sjc2.

## Context

The current server runs in one process. It owns one Python event loop for ASGI callbacks and one Tokio core worker thread for Rust networking. Python application code stays on the loop that loaded and serves the app; Tokio does not execute FastAPI handlers. PyO3 bridge work may also use Tokio's blocking pool, so one Tokio core worker does not mean the process has only one thread.

Processes cannot share a Tokio runtime. A Uvicorn-style worker feature requires separate processes, each with its own interpreter, GIL, Python loop, app instance, lifespan, and Tokio runtime, plus listener sharing, supervision, failure propagation, cancellation, and child reaping. HTTP/3 also requires a QUIC connection-affinity design.

## Current prototype

The current Python command starts one server process and one Tokio core worker. It does not implement worker supervision. Python callable execution, task creation, context variables, and exception behavior stay on the Python-owned event loop. Python callbacks remain subject to the interpreter's GIL.

## Compatibility target

[ADR 0005](0005-uvicorn-public-compatibility-contract.md) makes the Uvicorn worker and process-control contract part of the planned drop-in surface. The implementation must map worker count, process supervision, health checks, signals, restart behavior, listener sharing, shutdown, and cleanup to explicit parity cases. Each Python worker process owns its interpreter, event loop, application lifespan, and Tokio runtime; Tokio threads are not shared across processes.

Compare matching Uvicorn and uvicorn-rs runs at 1, 2, and 4 processes for I/O-bound and deterministic Python CPU-bound FastAPI workloads. Measure Tokio thread-count changes separately from process-count changes. Performance measurements do not replace lifecycle, isolation, failure, and cleanup parity.

## Consequences

- Documentation distinguishes the single-process prototype from the future worker-compatible release.
- One Python process does not gain parallel Python callback execution merely because Tokio has additional threads.
- Worker support, reload, and process supervision remain open release work until their versioned compatibility inputs pass.
- The current single-process benchmark cannot predict multi-worker scaling.
