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
