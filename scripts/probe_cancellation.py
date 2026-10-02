"""Black-box check that an HTTP client disconnect cancels its ASGI task."""

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
            "examples.cancellation_asgi:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--graceful-timeout",
            "1",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                _, stderr = process.communicate()
                raise RuntimeError(f"server exited early:\n{stderr}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise TimeoutError("server did not start listening")

        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            sock.sendall(
                b"GET /slow HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
                b"3\r\nabc\r\n"
            )
            time.sleep(0.1)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        connection.request("GET", "/cancelled")
        response = connection.getresponse()
        body = response.read()
        connection.close()
        if response.status != 200 or body != b"http.disconnect delivered":
            process.terminate()
            _, stderr = process.communicate(timeout=5)
            raise AssertionError(
                f"disconnect probe returned {response.status}: {body!r}\nserver log:\n{stderr}"
            )
        print("PASS: client disconnect delivered an ASGI http.disconnect event")

        with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
            sock.sendall(
                b"GET /send-after-disconnect HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
                b"3\r\nabc\r\n"
            )
            time.sleep(0.1)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        connection.request("GET", "/send-error")
        response = connection.getresponse()
        body = response.read()
        connection.close()
        if response.status != 200 or body != b"send raised OSError":
            raise AssertionError(f"send after disconnect returned {response.status}: {body!r}")
        print("PASS: ASGI send after disconnect raised OSError")

        pending = socket.create_connection(("127.0.0.1", port), timeout=2)
        pending.sendall(
            b"GET /hold HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
            b"3\r\nabc\r\n"
        )
        time.sleep(0.1)
        process.terminate()
        _, stderr = process.communicate(timeout=5)
        if process.returncode != 0:
            raise AssertionError(f"server exited with {process.returncode}:\n{stderr}")
        if "APP_CANCELLED_BY_SHUTDOWN" not in stderr:
            raise AssertionError(f"server did not cancel the Python task at shutdown:\n{stderr}")
        pending.close()
        print("PASS: graceful shutdown cancelled the remaining ASGI Python task")
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
