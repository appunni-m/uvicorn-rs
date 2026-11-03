# Windows: two-worker supervisor can hang after one Ctrl+C with a worker in socket.accept()

## Summary

Stock Uvicorn 0.54.0 intermittently fails to shut down on Windows after two
workers finish startup, one HTTP request completes, and one Ctrl+C is sent.
One worker finishes; the supervisor waits to join the remaining worker.

A post-timeout stack capture shows the supervisor in `BaseProcess.join()`
and the remaining worker in `socket.accept()` inside the asyncio selector
loop. Opening one additional TCP connection after the timeout lets that
worker shut down and the supervisor exit with code 0.

Everything needed to reproduce is included below. Use an empty directory;
no project checkout, external fixture, or CI artifact is required.

## Environment

- Windows Server 2022, build 20348, x86-64.
- CPython 3.12.13.
- Uvicorn 0.54.0 installed from PyPI, unmodified.
- click 8.5.0, h11 0.16.0, colorama 0.4.6.
- `WEB_CONCURRENCY=2`, `--loop asyncio --http h11 --ws none --lifespan on`.
- The app completes lifespan startup and shutdown immediately, and responds
  to HTTP with status 200 and body `ok`.

The failure is intermittent. One bounded three-launch batch had two clean
exits followed by a shutdown hang. A later stack-capture batch hung on launch
6; the controlled TCP-wakeup batch hung on launch 3. These observations do
not establish a failure rate or guarantee reproduction in three launches.

## Reproduction

Save the following two files in an empty directory. Run all commands from
that directory.

### 1. Application: `worker_terminate.py`

This file is only an ASGI application. It does not manage processes or signals.

```python
async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            await send({"type": event["type"] + ".complete"})
            if event["type"] == "lifespan.shutdown":
                return
    elif scope["type"] == "http":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
```

### 2. Automated controller: `cli_ctrl_c.py`

<details>
<summary>Complete standalone controller (Python standard library only)</summary>

The controller creates a private Windows console so that its console event
does not reach the caller's shell. It launches the ordinary Uvicorn CLI,
waits for both application startup messages, completes one HTTP request and
closes the client connection, then broadcasts exactly one `CTRL_C_EVENT`.

It records a failure if shutdown exceeds 12 seconds. Only after recording
that timeout does it optionally capture stacks and open a diagnostic TCP
connection. Recovery after that connection does not change the failed result.
It retains each attempt's complete log and stops on the first failure.

```python
"""Reproduce stock Uvicorn's two-worker Ctrl+C lifecycle without a parity runner."""

import argparse
import ctypes
import http.client
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import socket
import subprocess
import sys
import time


def attempt(directory, dump_exe=None):
    directory.mkdir(parents=True, exist_ok=True)
    # All processes in this private console receive the same Ctrl+C, as in an
    # interactive terminal. Enable delivery before spawning Uvicorn.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, ctypes.c_int]
    kernel32.SetConsoleCtrlHandler.restype = ctypes.c_int
    kernel32.GenerateConsoleCtrlEvent.argtypes = [ctypes.c_uint, ctypes.c_uint]
    kernel32.GenerateConsoleCtrlEvent.restype = ctypes.c_int
    if not kernel32.SetConsoleCtrlHandler(None, False):
        raise ctypes.WinError(ctypes.get_last_error())
    signal.signal(signal.SIGINT, lambda *_: None)
    signal.signal(signal.SIGBREAK, lambda *_: None)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    command = [sys.executable, "-m", "uvicorn", "worker_terminate:app",
               "--host", "127.0.0.1", "--port", str(port), "--loop", "asyncio",
               "--http", "h11", "--ws", "none", "--lifespan", "on", "--no-access-log"]
    environment = {**os.environ, "WEB_CONCURRENCY": "2", "PYTHONUNBUFFERED": "1"}
    result = {"command": command, "web_concurrency": 2,
              "python": platform.python_version(), "platform": platform.platform(),
              "uvicorn": importlib.metadata.version("uvicorn")}
    log_path = directory / "server.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and process.poll() is None:
                if log_path.read_bytes().count(b"Application startup complete.") >= 2:
                    break
                time.sleep(0.025)
            else:
                raise RuntimeError("two workers did not finish startup")
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request("GET", "/", headers={"Connection": "close"})
                response = connection.getresponse()
                result["http_status"] = response.status
                result["http_body"] = response.read().decode("ascii")
            finally:
                connection.close()
            if not kernel32.GenerateConsoleCtrlEvent(signal.CTRL_C_EVENT, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            result["ctrl_c_sent"] = True
            try:
                result["exit_code"] = process.wait(timeout=12)
                result["shutdown_timed_out"] = False
            except subprocess.TimeoutExpired:
                result["exit_code"] = None
                result["shutdown_timed_out"] = True
                # Read stacks only after the failure is already observed;
                # this does not instrument or alter the server's signal path.
                if dump_exe:
                    pids = dict.fromkeys(re.findall(
                        rb"Started (?:parent|server) process \[(\d+)\]", log_path.read_bytes()))
                    for pid in list(pids)[:8]:
                        dump = subprocess.run([str(dump_exe), "dump", "--pid", pid.decode()],
                                              capture_output=True, timeout=5, check=False)
                        (directory / f"stack-{pid.decode()}.txt").write_bytes(dump.stdout + dump.stderr)
                # Preserve the timeout, then test whether one TCP connection
                # releases the observed blocking accept and pending shutdown.
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        result["post_timeout_connection_opened"] = True
                    result["exit_code_after_connection"] = process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired) as error:
                    result["post_timeout_connection_result"] = type(error).__name__
        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=10, check=False)
                process.wait(timeout=5)
    result["server_log"] = log_path.read_text(encoding="utf-8", errors="replace")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("cli-ctrl-c"))
    parser.add_argument("--attempts", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--dump-exe", type=Path, help="optional py-spy executable; used only after a timeout")
    parser.add_argument("--in-console", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("requires Windows")
    if not args.in_console:
        for index in range(1, args.attempts + 1):
            directory = (args.output / str(index)).resolve()
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--in-console",
                 "--output", str(directory),
                 *(["--dump-exe", str(args.dump_exe.resolve())] if args.dump_exe else [])],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                timeout=60, check=False,
            )
            if completed.returncode:
                raise SystemExit(completed.returncode)
        raise SystemExit(0)
    result = attempt(args.output, args.dump_exe)
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    # A reproduced failure is diagnostic evidence, not a successful server run.
    raise SystemExit(1 if result.get("error") or result.get("shutdown_timed_out")
                     or result.get("exit_code") != 0 else 0)
```

</details>

### 3. Install and run

With CPython 3.12.13 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install uvicorn==0.54.0 click==8.5.0 h11==0.16.0 colorama==0.4.6
.\.venv\Scripts\python --version
.\.venv\Scripts\python cli_ctrl_c.py --attempts 3
```

Check that the version output is `Python 3.12.13`; `py -3.12` alone selects
whichever Python 3.12 patch is installed.

Exit status 0 means all requested attempts exited cleanly. Exit status 1
means a timeout/nonzero exit or probe error; inspect
`cli-ctrl-c/<attempt>/result.json` and `server.log` to distinguish them.
The controller permits a bounded `--attempts 10` batch if the initial
three launches do not reproduce the intermittent hang, and still stops at
the first failure.

For optional external stacks, install the profiler and run a new batch:

```powershell
.\.venv\Scripts\python -m pip install py-spy==0.4.3
.\.venv\Scripts\python cli_ctrl_c.py --attempts 10 --output with-stacks --dump-exe .\.venv\Scripts\py-spy.exe
```

The plain reproduction does not need py-spy. The optional profiler only
attaches after a timeout has already occurred; the server is not patched
or instrumented during startup, traffic or signal delivery.

## Expected behavior

After both workers are ready and the request has completed, one Ctrl+C
shuts down both workers and the supervisor cleanly, without requiring
another connection or another signal.

The 12-second limit is a bound in this reproduction. There is no intentionally
long-running request, delayed lifespan handler, or active client connection
that should require draining.

## Actual behavior

The request returns HTTP 200 with body `ok`. One worker exits, but the other
does not reach its shutdown log, and the parent waits beyond 12 seconds.

A representative failing attempt logged:

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

## Post-timeout stacks and controlled wakeup

A subsequent attempt captured the same shutdown hang. These excerpts are from
external `py-spy dump` snapshots after the timeout and before opening the
diagnostic connection.

Supervisor, PID 7132:

```text
Thread 7384 (idle): "MainThread"
    Popen.wait (multiprocessing\popen_spawn_win32.py:112)
    BaseProcess.join (multiprocessing\process.py:149)
    Process.join (uvicorn\supervisors\multiprocess.py:124)
    Multiprocess.join_all (uvicorn\supervisors\multiprocess.py:171)
    Multiprocess.run (uvicorn\supervisors\multiprocess.py:208)
```

Remaining worker, PID 2460:

```text
Thread 1640 (idle): "MainThread"
    socket.accept (socket.py:295)
    BaseSelectorEventLoop._accept_connection (asyncio\selector_events.py:178)
    Handle._run (asyncio\events.py:88)
    BaseEventLoop._run_once (asyncio\base_events.py:1999)
    BaseEventLoop.run_forever (asyncio\base_events.py:645)
    BaseEventLoop.run_until_complete (asyncio\base_events.py:678)
    Runner.run (asyncio\runners.py:118)
    run (asyncio\runners.py:195)
    Server.run (uvicorn\server.py:86)
    Process.target (uvicorn\supervisors\multiprocess.py:77)
    subprocess_started (uvicorn\_subprocess.py:80)
```

After these snapshots, opening one TCP connection to the same listener
(without sending another shutdown signal) was followed by:

```text
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [2460]
INFO:     Stopping parent process [7132]
```

The supervisor exited with code 0 within the three-second connection-wakeup
window. Relevant fields from that attempt:

```json
{
  "http_status": 200,
  "http_body": "ok",
  "ctrl_c_sent": true,
  "exit_code": null,
  "shutdown_timed_out": true,
  "post_timeout_connection_opened": true,
  "exit_code_after_connection": 0
}
```

## What is established, and what remains unknown

- The ordinary two-worker CLI can hang during shutdown with this small app.
- The captured worker is in the listener's accept callback, rather than an
  application lifespan handler; the parent is waiting to join it.
- An additional connection released the observed stall in the controlled
  wakeup attempt. This is diagnostic evidence, not a proposed workaround.
- The exact operation that makes the shared listener block is not established.
  Windows socket-sharing and nonblocking-mode transitions are investigation
  leads, not a confirmed cause.
- The verified reproduction uses a generated console Ctrl+C in a private
  console. A manual keyboard Ctrl+C reproduction has not been independently
  verified.
- This report covers the shutdown hang only. No production fix is included.
