# Windows: two-worker supervisor can hang joining a worker after one Ctrl+C

## Environment

- Stock Uvicorn 0.54.0, installed from PyPI; no source or runtime patches.
- CPython 3.12.13 on Windows Server 2022, build 20348.
- Minimal dependencies: click 8.5.0, h11 0.16.0, colorama 0.4.6.
- `WEB_CONCURRENCY=2`, asyncio loop, h11 HTTP, WebSockets disabled.
- Tiny ASGI app with immediate lifespan startup/shutdown completion and an
  HTTP response of `200 ok`. No FastAPI, Rust extension, or custom protocol.

## Reproduction

Copy `cli_ctrl_c.py` and `worker_terminate.py` from
[this standalone reproduction directory](https://github.com/appunni-m/uvicorn-rs/tree/a0936005288b7627759caf31f5d67c92f9988747/tools/upstream/uvicorn-windows)
into an empty directory, then use an isolated environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install uvicorn==0.54.0 click==8.5.0 h11==0.16.0 colorama==0.4.6
.\.venv\Scripts\python cli_ctrl_c.py --attempts 3
```

The controller creates a private Windows console, starts the ordinary Uvicorn
CLI, waits for both workers' application startup messages, sends and completes
one HTTP request, then broadcasts exactly one `CTRL_C_EVENT` to that console.
It retains the complete logs and bounds the shutdown wait at 12 seconds.

Expected: the supervisor and both ready workers exit after graceful shutdown.

Actual: the first two attempts exited with code 0; the third served HTTP 200,
one worker finished, and the supervisor remained blocked joining the other
worker until the controller cleaned up the process tree after the deadline.

## Failing log

```text
INFO:     Started parent process [6788]
INFO:     Started server process [3504]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Started server process [6224]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [3504]
INFO:     Received SIGINT, exiting.
INFO:     Terminated child process [6224]
INFO:     Waiting for child process [3504]
INFO:     Waiting for child process [6224]
```

[Complete independent stock-only run and artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/41586707341/job/125753785308).
The artifact includes all three attempts, including both successful controls.

## Scope and investigation

This establishes a shutdown hang with a small standalone app. It does not
establish that every Windows launch fails or that the separate historical
`WinError(10022)` startup crash has the same cause. A single-worker probe of
the stock `Process.terminate()` path did not hang.

One lead is the worker-directed `CTRL_BREAK_EVENT`: stock Uvicorn targets a
spawned worker PID, while the documented Windows API expects a process-group
ID for targeted delivery. Related history:
[Uvicorn #2292](https://github.com/Kludex/uvicorn/discussions/2292) and
[microsoft/terminal #335](https://github.com/microsoft/terminal/issues/335).
This is an investigation lead, not yet a confirmed causal explanation.

No upstream issue or pull request has been submitted from this draft.
