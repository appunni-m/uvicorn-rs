"""Black-box WebSocket handshake, subprotocol, message, and denial checks."""

import asyncio
import contextlib
import socket
import subprocess
import sys
import time

import websockets


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_listening(port, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early with status {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("server did not start listening")


async def probe(port):
    uri = f"ws://127.0.0.1:{port}/echo"
    async with websockets.connect(uri, subprotocols=["chat"]) as websocket:
        if websocket.subprotocol != "chat":
            raise AssertionError(f"unexpected subprotocol: {websocket.subprotocol!r}")
        await websocket.send("hello")
        if await websocket.recv() != "hello":
            raise AssertionError("text WebSocket message did not round trip")
        await websocket.send(b"binary")
        if await websocket.recv() != b"binary":
            raise AssertionError("binary WebSocket message did not round trip")
    print("PASS: WebSocket handshake, subprotocol, and text/binary messages")

    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}/reject"):
            raise AssertionError("WebSocket close before accept was not denied")
    except websockets.exceptions.InvalidStatus as error:
        status = error.response.status_code
        if status != 403:
            raise AssertionError(f"expected HTTP 403 denial, got {status}") from error
    print("PASS: pre-accept websocket.close returned HTTP 403")


def main():
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn_rs",
            "examples.websocket_asgi:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_listening(port, process)
        try:
            asyncio.run(probe(port))
        except Exception as error:
            process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=3)
            if process.poll() is None:
                process.kill()
                process.wait()
            _, logs = process.communicate()
            raise RuntimeError(f"WebSocket probe failed; server log:\n{logs}") from error
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=3)
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stderr.close()


if __name__ == "__main__":
    main()
