"""Launch the CLI and verify one live HTTP request/response through ASGI."""

import http.client
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def choose_port():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def probe(app, expected_status, expected_body, expected_log=None, loop="asyncio"):
    port = choose_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn_rs",
            app,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--loop",
            loop,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        response = None
        last_error = None
        for _ in range(100):
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise RuntimeError(
                    f"server exited early ({process.returncode})\nstdout:\n{stdout}\nstderr:\n{stderr}"
                )
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("POST", "/probe?q=1", body=b"payload")
                response = connection.getresponse()
                body = response.read()
                connection.close()
                break
            except OSError as error:
                last_error = error
                time.sleep(0.05)
        else:
            raise RuntimeError(f"server did not accept a connection: {last_error}")

        if response.status != expected_status or body != expected_body:
            raise AssertionError(
                f"{app}: expected HTTP {expected_status} and {expected_body!r}, "
                f"got {response.status} and {body!r}"
            )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        stdout, stderr = process.communicate()

    if expected_log is not None and expected_log not in stderr:
        raise AssertionError(f"{app}: expected {expected_log!r} in server stderr:\n{stderr}")
    print(f"PASS: {app} on {loop} returned HTTP {response.status} {body.decode(errors='replace')}")


def main():
    probe(
        "examples.hello_asgi:app",
        200,
        b"POST /probe 1.1 payload",
    )
    probe(
        "examples.bridge_contract_asgi:app",
        200,
        b"call_thread=True;loop=True;context=caller-context;request=payload",
        loop="uvloop",
    )
    probe(
        "examples.raising_asgi:app",
        500,
        b"Internal Server Error",
        expected_log="bridge exception sentinel",
    )


if __name__ == "__main__":
    main()
