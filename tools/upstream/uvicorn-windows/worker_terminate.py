"""Stock-Uvicorn-only Windows worker shutdown probe; no runtime patches.

Install uvicorn==0.54.0, then run this file in an otherwise empty directory.
A private console prevents console events from reaching the caller's shell.
"""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys


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


def probe():
    from uvicorn import Config
    from uvicorn.supervisors.multiprocess import Process

    # The controller shares the worker's console, but must survive a stray
    # broadcast. The worker installs Uvicorn's own SIGBREAK handler at startup.
    signal.signal(signal.SIGBREAK, lambda *_: None)
    config = Config("worker_terminate:app", host="127.0.0.1", port=0,
                    loop="asyncio", http="h11", ws="none", lifespan="on")
    listener = config.bind_socket()
    worker = Process(config, [listener])
    worker.start()
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "uvicorn": importlib.metadata.version("uvicorn"), "pid": worker.pid}
    try:
        result["ready"] = worker.wait_until_ready(10)
        if not result["ready"]:
            raise RuntimeError("worker failed to become ready")
        worker.terminate()  # Exactly the stock supervisor's shutdown operation.
        worker.process.join(timeout=5)  # Bound the otherwise unbounded join().
        result["alive_after_terminate"] = worker.process.is_alive()
        result["exit_code_before_cleanup"] = worker.exitcode
    finally:
        if worker.process.is_alive():
            worker.kill()
            worker.process.join(timeout=5)
        listener.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("worker-terminate.json"))
    parser.add_argument("--in-console", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("requires Windows console signal semantics")
    if not args.in_console:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.with_suffix(".log").open("wb") as log:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--in-console",
                 "--output", str(args.output.resolve())], stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=40, check=False,
            )
        raise SystemExit(completed.returncode)
    try:
        result = probe()
    except Exception as error:
        result = {"error": f"{type(error).__name__}: {error}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    raise SystemExit(1 if result.get("error") else 0)
