# ADR 0002: ASGI worker processes and Tokio thread model

- **Status:** Accepted architecture direction; worker implementation is gated on correctness and benchmark evidence.
- **Date:** 2026-10-08
- **Related:** [ADR 0001](0001-runtime-and-asyncio-bridge.md), KATA issue `sjc2`.

## Context

One `uvicorn-rs` process owns one Python event loop for ASGI callbacks and the
current experiment configures one Tokio worker thread for Rust networking and
protocol work. Tokio's threads can run Rust tasks on multiple cores. They do
not execute FastAPI or other Python application callbacks: those are scheduled
onto the caller's one Python event loop and run under that interpreter's GIL.

An operating-system process cannot share its threads with another process.
Trying to route ASGI calls from several Python processes through one Tokio
runtime would require an IPC protocol for scopes, events, streamed bodies,
responses, WebSockets, cancellation, and backpressure. That adds a second
transport boundary and changes the ordinary in-process ASGI execution model.

Uvicorn's worker option is a process model: it starts independent workers with
`spawn`, and each worker loads and serves the application. Its documentation
also describes process supervision and notes that workers are mutually
exclusive with reload. This is the relevant compatibility model, not a shared
thread pool ([Uvicorn deployment](https://www.uvicorn.org/deployment/)).

## Decisions

### 1. Keep Tokio as the Rust network runtime and start with one worker thread

Do not replace Tokio based on language-level assumptions. It already supports
the server's async sockets and protocol tasks. Consider another runtime only
if a clean, workload-matched profile shows that Tokio's scheduler or I/O driver
is a material bottleneck after the Python bridge and protocol work are
accounted for. The current default is one Tokio worker thread, as an explicit
measurement choice. SIMD and additional Tokio threads cannot parallelize
pure-Python FastAPI callback execution on one interpreter.

### 2. Model optional ASGI workers as independent spawned processes

If worker benchmarks show a useful benefit, `--workers N` will mean N
independent server processes. Each process owns:

- one Python interpreter and GIL;
- one asyncio loop (or one uvloop when explicitly selected);
- one imported ASGI app instance and one lifespan startup/shutdown;
- one Rust server instance and one Tokio runtime.

The default remains one process. Worker count and Tokio thread count are
separate controls and must be measured independently. Increasing Tokio threads
must not be described as Python application parallelism. A worker process is
the compatible way to run CPU-bound Python callbacks on more than one core,
subject to the app's own thread/process behavior.

This preserves normal FastAPI expectations: each worker has process-local
globals, app state, lifespan resources, and caches. A deployment with multiple
workers does not share those Python objects between processes, just as with
Uvicorn workers. The server will not wrap application calls in an executor or
move them onto Tokio workers.

### 3. Keep listener sharing and protocol support explicit

The worker manager must use a documented listener-sharing strategy and must
not add unsafe Rust. A same-port `SO_REUSEPORT` design is a candidate where the
OS supports it, but it is not assumed to have identical support or connection
distribution across platforms. TCP, TLS, UDP/QUIC, and HTTP/3 affinity need
separate live checks; in particular, a worker mode that cannot reliably route
QUIC packets to the owning connection must reject HTTP/3 rather than silently
misroute it. Worker support will be listed separately in the support matrix.

Each child must report readiness only after its listener and ASGI lifespan
startup succeed. The supervisor must fail the whole startup if a child fails,
forward shutdown signals, wait for graceful cleanup, escalate only after a
bounded deadline, and reap every child. Automatic restarts, reload, dynamic
worker-count signals, and process hot upgrades are outside the first worker
milestone unless separately specified and tested.

### 4. Require worker-specific evidence before claiming a speedup

Compare the same app, interpreter, dependencies, loop choice, client, request
mix, hardware, and repetition schedule for Uvicorn and `uvicorn-rs` at 1, 2,
and 4 workers. Include both an I/O-bound workload and deterministic pure-Python
CPU-bound work; include an actual FastAPI route as well as a direct ASGI case
to separate framework overhead from server bridge overhead. Report throughput,
p50/p95/p99 latency, server process-tree CPU, and aggregate RSS. Keep invalid
or contended observations visible and out of performance ratios.

Keep the Tokio thread count fixed at one while measuring the FastAPI workloads
and the broader protocol matrix. A later 1/2/4-thread comparison can change
only that setting on the same workload and host. Do not vary process and Tokio
thread counts in the same comparison, since that would obscure which layer
changed. Keep one Tokio thread unless a clean paired run shows a repeatable
benefit from changing it without correctness regressions.

## Consequences

- A multi-worker server will use more memory because each process has its own
  interpreter, app, runtime, and imported modules.
- A CPU-bound Python route can scale across process GILs; an async I/O-bound
  route may already use one event loop efficiently, so extra workers can add
  overhead without improving latency or throughput.
- Rust networking currently uses one Tokio worker thread per process.
  Worker processes may help Python callback saturation, but their extra
  runtimes and threads need separate measurement.
- There is no cross-process sharing of Tokio threads or Python app state.
- Worker mode is not part of the current CLI support matrix until listener
  sharing, startup, failure, cancellation, and shutdown cases pass the public
  black-box matrix and the worker benchmark qualifies.
