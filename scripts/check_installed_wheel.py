#!/usr/bin/env python3
"""Check a real installed wheel through its CLI and public ASGI server API.

This is a package-consumer smoke check, not the full live oracle parity matrix.
It uses only the standard library so the declared Python floor can run it.
"""

import argparse
import asyncio
import contextvars
import hashlib
import importlib.metadata
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import zipfile


async def consume_wheel():
    from uvicorn_rs import Server

    loop = asyncio.get_running_loop()
    thread = threading.get_ident()
    context = contextvars.ContextVar("wheel-consumer-context", default=None)
    context.set("wheel-caller")
    events = []

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    events.append("startup")
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    events.append("shutdown")
                    return
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if not event.get("more_body", False):
                break
        if (asyncio.get_running_loop() is not loop
                or threading.get_ident() != thread or context.get() != "wheel-caller"):
            raise RuntimeError("wheel ASGI invocation lost caller loop/thread/context")
        response = b"wheel:" + bytes(body)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-length", str(len(response)).encode())]})
        await send({"type": "http.response.body", "body": response})
        events.append("http.complete")

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    task = asyncio.create_task(Server(app, port=port, graceful_timeout=2).serve())
    cancellation_propagated = False
    writer = None
    try:
        deadline = loop.time() + 10
        while True:
            if task.done():
                await task
                raise RuntimeError("wheel server exited before serving a request")
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                break
            except OSError:
                if loop.time() >= deadline:
                    raise TimeoutError("wheel server did not start within ten seconds")
                await asyncio.sleep(0.02)
        payload = b"\x00\x01package-consumer"
        writer.write(b"POST /wheel HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
                     + str(len(payload)).encode() + b"\r\nConnection: close\r\n\r\n" + payload)
        await writer.drain()
        headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        body = await asyncio.wait_for(reader.readexactly(len(b"wheel:" + payload)), 5)
        if not headers.startswith(b"HTTP/1.1 200 ") or body != b"wheel:" + payload:
            raise RuntimeError("installed wheel returned the wrong HTTP status or body")
    finally:
        try:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
        finally:
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), 10)
            except asyncio.CancelledError:
                cancellation_propagated = True
    if (not cancellation_propagated or events != ["startup", "http.complete", "shutdown"]
            or not loop.is_running()):
        raise RuntimeError("installed wheel did not complete owned lifespan and cancellation")
    return {"status": "passed", "events": events,
            "caller_loop_thread_context_preserved": True,
            "server_cancellation_propagated": True, "caller_loop_alive": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import uvicorn_rs
    from uvicorn_rs import _native

    native = Path(_native.__file__).resolve()
    package = Path(uvicorn_rs.__file__).resolve()
    checkout_python = Path(__file__).resolve().parents[1] / "python"
    if checkout_python in native.parents or checkout_python in package.parents:
        raise RuntimeError("consumer check imported the editable checkout instead of the installed wheel")
    data = native.read_bytes()
    with zipfile.ZipFile(args.wheel) as archive:
        modules = [name for name in archive.namelist()
                   if name.startswith("uvicorn_rs/_native.") and name.endswith((".so", ".pyd"))]
        if len(modules) != 1 or data != archive.read(modules[0]):
            raise RuntimeError("imported native module does not match the exact supplied wheel")
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-wheel-consumer-") as directory:
        cli = subprocess.run([sys.executable, "-m", "uvicorn_rs", "--help"], cwd=directory,
                             capture_output=True, text=True, timeout=20, check=True)
    if "module:app" not in cli.stdout:
        raise RuntimeError("installed wheel CLI help does not describe module:app")
    evidence = {"schema": "uvicorn-rs-installed-wheel-consumer@1", "python": sys.version,
                "version": importlib.metadata.version("uvicorn-rs"),
                "wheel": str(args.wheel.resolve()),
                "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
                "native_path": str(native), "native_sha256": hashlib.sha256(data).hexdigest(),
                "package_path": str(package), "cli_help": "passed",
                "live_asgi": asyncio.run(consume_wheel()),
                "scope": "actual package-consumer HTTP/lifespan/context/cancellation smoke; not full oracle parity"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"status": "passed", "receipt": str(args.output)}))


if __name__ == "__main__":
    main()
