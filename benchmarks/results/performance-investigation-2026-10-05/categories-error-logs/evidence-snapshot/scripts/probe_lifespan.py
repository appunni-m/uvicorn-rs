"""Black-box checks for lifespan state, SIGTERM, and graceful shutdown."""

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
            "examples.lifespan_asgi:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--graceful-timeout",
            "3",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        bodies = []
        last_error = None
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError(f"server exited early with status {process.returncode}")
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", "/state")
                response = connection.getresponse()
                bodies.append(response.read())
                connection.close()
                if len(bodies) == 2:
                    break
            except OSError as error:
                last_error = error
                time.sleep(0.05)
        else:
            raise RuntimeError(f"server did not serve both requests: {last_error}")

        if bodies != [b"startup-token:0", b"startup-token:1"]:
            raise AssertionError(f"unexpected lifespan state copies: {bodies!r}")
        process.terminate()
        _, stderr = process.communicate(timeout=5)
        if process.returncode != 0:
            raise AssertionError(f"server exited with {process.returncode}:\n{stderr}")
        if "LIFESPAN_SHUTDOWN_COMPLETE" not in stderr:
            raise AssertionError(f"server did not finish lifespan shutdown:\n{stderr}")
        print("PASS: startup state, per-request shallow copies, and SIGTERM shutdown")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()


if __name__ == "__main__":
    main()
