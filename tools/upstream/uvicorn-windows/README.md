# Stock Uvicorn Windows worker reproducer

Copy this directory anywhere outside the uvicorn-rs checkout. These scripts use
only the Python standard library and an installed stock Uvicorn. They do not
import uvicorn-rs, FastAPI, or the parity runner, and do not patch Uvicorn.

## Run on Windows

Use CPython 3.12.13, the interpreter from the failing CI environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install uvicorn==0.54.0 click==8.5.0 h11==0.16.0 colorama==0.4.6
.\.venv\Scripts\python cli_ctrl_c.py --attempts 3
```

The `py -3.12` command selects your installed Python 3.12 interpreter; check
`python --version` if reproducing the exact patch version matters. On the hosted
runner, `uv` installs and selects 3.12.13 explicitly.

The controller opens a private console, launches `python -m uvicorn` with
`WEB_CONCURRENCY=2`, waits for both application startup messages, completes one
HTTP request, and generates one console Ctrl+C event. It waits 12 seconds for
the supervisor to exit and retains every attempt's JSON and complete server log.
After a timeout it opens one diagnostic TCP connection and waits up to three
seconds to see whether that wakes the stalled worker, then cleans up any
remaining process tree. The original timeout remains a failed result. It stops on the first failure
or after three attempts. Exit status 1 means that the failure reproduced or
the probe encountered an error; inspect `result.json` to distinguish them.

The ASGI app is the `app` function in `worker_terminate.py`. To try the same
input manually in a fresh Windows terminal:

```powershell
$env:WEB_CONCURRENCY = "2"
.\.venv\Scripts\python -m uvicorn worker_terminate:app --host 127.0.0.1 --port 8000 --loop asyncio --http h11 --ws none --lifespan on --no-access-log
```

Wait for both workers' startup messages, request `http://127.0.0.1:8000/` from
another terminal, then press Ctrl+C once. Manual terminal reproduction has
not yet been independently verified; the automated console-event result below
is the verified reproduction.

## Verified observation

[CI #632](https://github.com/appunni-m/uvicorn-rs/actions/runs/41586707341/job/125753785308)
ran the standalone scripts on Windows Server 2022, build 20348, with CPython
3.12.13 and stock Uvicorn 0.54.0. Attempts 1 and 2 exited with code 0. Attempt 3
served HTTP 200 with body `ok`, then remained alive past the 12-second shutdown
deadline. The log ends at `Waiting for child process [6224]`; that worker had
reported startup complete but never reported `Shutting down`.

The retained artifact is `uvicorn-stock-windows-worker-diagnostic`, ID
`13208510909`, archive SHA-256
`1abc517a9d5668d9f255b02f7aca57d2bb25483a0eff309b66f29147fd00e666`.
This is an observed 1/3 failure in a bounded batch, not an estimated failure
rate and not evidence of a deterministic failure on every launch.

`worker_terminate.py` separately starts one ready stock `Process` and calls its
unmodified `terminate()` operation. That probe exited within five seconds
(exit code 3 after logging application shutdown complete), so it did **not**
reproduce the two-worker join hang by itself.

This shutdown failure is separate from the earlier `socket.listen()`
`WinError(10022)` startup crash. The standalone three-attempt batch did not
reproduce the startup crash. Do not combine them into a single proven cause.

## Confirmed stall and wakeup

[CI #634](https://github.com/appunni-m/uvicorn-rs/actions/runs/41587452848/job/125756162041)
reproduced the hang on attempt 6. External `py-spy dump` snapshots taken after
the timeout show the supervisor in `BaseProcess.join()` and the remaining
worker's main thread in `socket.accept()`, called by
`BaseSelectorEventLoop._accept_connection()`. That worker was not waiting for
an ASGI lifespan handler or an application task. The exited worker could no
longer be inspected, as expected. See the retained [supervisor stack](evidence/ci634-supervisor-stack.txt)
and [worker stack](evidence/ci634-worker-stack.txt).

[CI #635](https://github.com/appunni-m/uvicorn-rs/actions/runs/41587817744/job/125757313584)
reproduced the same stack on attempt 3. After the timeout and stack snapshots,
the controller opened one additional TCP connection. The stalled worker then
logged graceful shutdown and the supervisor exited with code 0 within the
three-second wakeup window. The result still records `shutdown_timed_out=true`.
See the [wakeup result](evidence/ci635-failure-and-wakeup.json).

This confirms the location of the stall and a network event that releases it.
It does not yet establish which shared-listener operation causes `accept()` to
block, or validate a production patch. [PR guidance](PR-GUIDANCE.md) gives the
focused acceptance criteria for a fix.

## Further diagnosis

`cli_ctrl_c.py --dump-exe <path-to-py-spy.exe>` optionally captures the supervisor
and workers' Python stacks only after a shutdown timeout has already occurred.
It does not install hooks in Uvicorn or change signal delivery. The plain
reproducer above needs no profiler.

The first stack-capture batch, [CI #633](https://github.com/appunni-m/uvicorn-rs/actions/runs/41587051987),
completed three clean CLI attempts and therefore produced no failure stacks.
The diagnostic workflow bounds a capture batch at ten launches and
stops at the first failure; this is a search for failure evidence, not a retry
until a passing release receipt appears. The standalone script still defaults
to three attempts.

The initial signal-delivery lead was that the stock supervisor uses
`os.kill(worker_pid, CTRL_BREAK_EVENT)` in
[`Process.terminate()`](https://github.com/Kludex/uvicorn/blob/0.54.0/uvicorn/supervisors/multiprocess.py).
CPython's Windows multiprocessing spawn uses creation flags zero. Microsoft's
[console API contract](https://learn.microsoft.com/en-us/windows/console/generateconsolectrlevent)
defines a nonzero target as a process group created with
`CREATE_NEW_PROCESS_GROUP`. This is a separate mismatch to investigate; the
captured failure is blocked in `accept()`. These facts do not prove a lost
console signal caused that blocked call. Related prior
reports are [Uvicorn discussion #2292](https://github.com/Kludex/uvicorn/discussions/2292)
and [Microsoft terminal issue #335](https://github.com/microsoft/terminal/issues/335).

Keep the unmodified failing baseline. Before proposing a fix upstream, require
a causal change and a matched focused regression check. uvicorn-rs must retain
correct startup and shutdown behavior; it must not reproduce this reference
hang. A source-bound candidate correctness check can establish an improvement
while the failed reference comparison remains visible. Upstream repair is not
a prerequisite for that decision. Coverage, independent review, benchmark and
artifact release requirements remain required.
