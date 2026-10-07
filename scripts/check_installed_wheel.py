"""Check a real installed wheel through its CLI and public ASGI server API.

This is a package-consumer smoke check, not the full live oracle parity matrix.
Its Python code uses only the standard library; the POSIX TLS probe requires
the openssl executable.
"""

import argparse
import asyncio
import contextvars
import hashlib
import http.client
import importlib.metadata
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path


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
        if (
            asyncio.get_running_loop() is not loop
            or threading.get_ident() != thread
            or context.get() != "wheel-caller"
        ):
            raise RuntimeError("wheel ASGI invocation lost caller loop/thread/context")
        response = b"wheel:" + bytes(body)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", str(len(response)).encode())],
            }
        )
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
        writer.write(
            b"POST /wheel HTTP/1.1\r\nHost: localhost\r\nContent-Length: "
            + str(len(payload)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + payload
        )
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
    if (
        not cancellation_propagated
        or events != ["startup", "http.complete", "shutdown"]
        or not loop.is_running()
    ):
        raise RuntimeError(
            "installed wheel did not complete owned lifespan and cancellation"
        )
    return {
        "status": "passed",
        "events": events,
        "caller_loop_thread_context_preserved": True,
        "server_cancellation_propagated": True,
        "caller_loop_alive": True,
    }


def probe_installed_cli_tls_and_shutdown():
    """Exercise module:app, TLS, and bounded POSIX SIGTERM on the installed wheel."""
    if os.name == "nt":
        return {
            "status": "not_run",
            "reason": "the direct SIGTERM/TLS process probe is POSIX-only",
        }
    openssl = shutil.which("openssl")
    if openssl is None:
        raise RuntimeError(
            "openssl is required to create the installed-wheel TLS probe certificate"
        )

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    checkout = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-installed-cli-") as directory:
        workdir = Path(directory)
        certificate = workdir / "cert.pem"
        private_key = workdir / "key.pem"
        subprocess.run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        log_path = workdir / "server.log"
        command = [
            sys.executable,
            "-m",
            "uvicorn_rs",
            "examples.lifespan_asgi:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--certfile",
            str(certificate),
            "--keyfile",
            str(private_key),
            "--graceful-timeout",
            "2",
        ]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(checkout)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(["http/1.1"])
        with log_path.open("w", encoding="utf-8") as logs:
            process = subprocess.Popen(
                command,
                cwd=workdir,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=logs,
            )
            held_connection = None
            try:
                deadline = time.monotonic() + 10
                response_body = None
                selected_alpn = None
                response_status = None
                tls_version = None
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        logs.flush()
                        raise RuntimeError(
                            "installed CLI exited during startup "
                            f"({process.returncode}):\n{log_path.read_text(encoding='utf-8')}"
                        )
                    connection = http.client.HTTPSConnection(
                        "127.0.0.1", port, timeout=2, context=context
                    )
                    try:
                        connection.request("GET", "/state")
                        response = connection.getresponse()
                        response_status = response.status
                        response_body = response.read()
                        if connection.sock is not None:
                            selected_alpn = connection.sock.selected_alpn_protocol()
                            tls_version = connection.sock.version()
                        break
                    except (OSError, ssl.SSLError, http.client.HTTPException):
                        time.sleep(0.05)
                    finally:
                        connection.close()
                if (
                    response_status != 200
                    or response_body != b"startup-token:0"
                    or selected_alpn != "http/1.1"
                ):
                    raise RuntimeError(
                        "installed module:app TLS request failed or negotiated the wrong ALPN "
                        f"(status={response_status!r}, body={response_body!r}, "
                        f"alpn={selected_alpn!r})"
                    )

                raw = socket.create_connection(("127.0.0.1", port), timeout=3)
                held_connection = context.wrap_socket(raw, server_hostname="localhost")
                held_connection.settimeout(3)
                held_connection.sendall(
                    b"GET /hold HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n"
                )
                hold_deadline = time.monotonic() + 3
                while time.monotonic() < hold_deadline:
                    logs.flush()
                    if "APP_HOLD_STARTED" in log_path.read_text(encoding="utf-8"):
                        break
                    if process.poll() is not None:
                        raise RuntimeError(
                            "installed CLI exited before entering the held request"
                        )
                    time.sleep(0.02)
                else:
                    raise TimeoutError("installed CLI did not enter the held request")

                shutdown_started = time.monotonic()
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired as error:
                    raise TimeoutError(
                        "installed CLI did not stop within five seconds after SIGTERM"
                    ) from error
                shutdown_elapsed = time.monotonic() - shutdown_started
                logs.flush()
                log_text = log_path.read_text(encoding="utf-8")
                if process.returncode != 0:
                    raise RuntimeError(
                        f"installed CLI exited {process.returncode} after SIGTERM:\n{log_text}"
                    )
                if "APP_CANCELLED_BY_SHUTDOWN" not in log_text:
                    raise RuntimeError("SIGTERM did not cancel the held ASGI request")
                if "LIFESPAN_SHUTDOWN_COMPLETE" not in log_text:
                    raise RuntimeError(
                        "SIGTERM did not complete ASGI lifespan shutdown"
                    )
                if shutdown_elapsed > 5:
                    raise RuntimeError(
                        "installed CLI exceeded the five-second shutdown bound"
                    )
                return {
                    "status": "passed",
                    "command": "python -m uvicorn_rs module:app --certfile ... --keyfile ...",
                    "http_status": response_status,
                    "http_body": response_body.decode(),
                    "tls_version": tls_version,
                    "alpn": selected_alpn,
                    "held_request_cancelled": True,
                    "lifespan_shutdown_completed": True,
                    "signal": "SIGTERM",
                    "shutdown_elapsed_seconds": round(shutdown_elapsed, 6),
                    "shutdown_bound_seconds": 5,
                    "exit_code": process.returncode,
                }
            finally:
                if held_connection is not None:
                    held_connection.close()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)


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
        raise RuntimeError(
            "consumer check imported the editable checkout instead of the installed wheel"
        )
    data = native.read_bytes()
    with zipfile.ZipFile(args.wheel) as archive:
        modules = [
            name
            for name in archive.namelist()
            if name.startswith("uvicorn_rs/_native.") and name.endswith((".so", ".pyd"))
        ]
        if len(modules) != 1 or data != archive.read(modules[0]):
            raise RuntimeError(
                "imported native module does not match the exact supplied wheel"
            )
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-wheel-consumer-") as directory:
        cli = subprocess.run(
            [sys.executable, "-m", "uvicorn_rs", "--help"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    if "module:app" not in cli.stdout:
        raise RuntimeError("installed wheel CLI help does not describe module:app")
    evidence = {
        "schema": "uvicorn-rs-installed-wheel-consumer@1",
        "python": sys.version,
        "platform": sys.platform,
        "consumer_probe_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "version": importlib.metadata.version("uvicorn-rs"),
        "wheel": str(args.wheel.resolve()),
        "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
        "native_path": str(native),
        "native_sha256": hashlib.sha256(data).hexdigest(),
        "package_path": str(package),
        "cli_help": "passed",
        "cli_tls_and_shutdown": probe_installed_cli_tls_and_shutdown(),
        "live_asgi": asyncio.run(consume_wheel()),
        "scope": "actual package-consumer HTTP/lifespan/context/cancellation and POSIX CLI/TLS/shutdown smoke; not full oracle parity",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"status": "passed", "receipt": str(args.output)}))


if __name__ == "__main__":
    main()
