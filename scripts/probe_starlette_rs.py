"""Check an installed starlette-rs app through the independent ASGI server."""

import http.client
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn_rs",
            "examples.starlette_rs_asgi:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        last_error = None
        for _ in range(100):
            if process.poll() is not None:
                _, stderr = process.communicate()
                raise RuntimeError(f"server exited early:\n{stderr}")
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", "/")
                response = connection.getresponse()
                body = response.read()
                connection.close()
                break
            except OSError as error:
                last_error = error
                time.sleep(0.05)
        else:
            raise RuntimeError(f"server did not accept a connection: {last_error}")
        if response.status != 200 or body != b"starlette-rs ASGI app":
            raise AssertionError(f"unexpected response: {response.status} {body!r}")
        print("PASS: starlette-rs app served without a server runtime dependency")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()


if __name__ == "__main__":
    main()
