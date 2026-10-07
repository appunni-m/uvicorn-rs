"""Compare one shared Starlette-compatible ASGI app through Uvicorn and uvicorn-rs.

Run this only in an isolated environment containing an installed uvicorn-rs
wheel, Uvicorn, and exactly one of upstream Starlette or starlette-rs-py.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import importlib.metadata
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = "examples.starlette_compat_asgi:app"
STREAM_BODY = (b"alpha", b"beta", b"gamma")
UPLOAD_BODY = (b"first|", b"second")
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _free_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _identity(framework: str, server_wheel: Path, framework_wheel) -> dict[str, object]:
    import starlette

    server_wheel = server_wheel.resolve()
    server_wheel_sha256 = hashlib.sha256(server_wheel.read_bytes()).hexdigest()
    if framework == "starlette":
        if _version("starlette-rs-py") is not None:
            raise RuntimeError(
                "upstream Starlette and starlette-rs-py share the starlette namespace"
            )
        version = _version("starlette")
        if version is None:
            raise RuntimeError("the upstream starlette distribution is not installed")
        framework_files = [Path(starlette.__file__).resolve()]
        framework_version = version
        framework_distribution = "starlette"
        native_hash = None
        framework_wheel_sha256 = None
    else:
        version = _version("starlette-rs-py")
        if version is None:
            raise RuntimeError(
                "the separately built starlette-rs-py distribution is not installed"
            )
        if _version("starlette") is not None:
            raise RuntimeError(
                "upstream Starlette and starlette-rs-py must use separate environments"
            )
        native = importlib.import_module("starlette_rs_py._core")
        framework_files = [
            Path(starlette.__file__).resolve(),
            Path(native.__file__).resolve(),
        ]
        framework_version = version
        framework_distribution = "starlette-rs-py"
        native_bytes = Path(native.__file__).read_bytes()
        native_hash = hashlib.sha256(native_bytes).hexdigest()
        if framework_wheel is None:
            raise RuntimeError("starlette-rs integration requires --framework-wheel")
        framework_wheel = framework_wheel.resolve()
        with zipfile.ZipFile(framework_wheel) as archive:
            modules = [
                name
                for name in archive.namelist()
                if name.startswith("starlette_rs_py/_core.")
                and name.endswith((".so", ".pyd"))
            ]
            if len(modules) != 1 or native_bytes != archive.read(modules[0]):
                raise RuntimeError(
                    "imported starlette-rs extension does not match its wheel"
                )
        framework_wheel_sha256 = hashlib.sha256(
            framework_wheel.read_bytes()
        ).hexdigest()

    package = importlib.import_module("uvicorn_rs")
    native_server = importlib.import_module("uvicorn_rs._native")
    package_path = Path(package.__file__).resolve()
    native_path = Path(native_server.__file__).resolve()
    if package_path.is_relative_to(ROOT / "python") or native_path.is_relative_to(
        ROOT / "python"
    ):
        raise RuntimeError(
            "uvicorn-rs must be installed from a wheel; the editable checkout is not accepted"
        )
    native_bytes = native_path.read_bytes()
    with zipfile.ZipFile(server_wheel) as archive:
        modules = [
            name
            for name in archive.namelist()
            if name.startswith("uvicorn_rs/_native.") and name.endswith((".so", ".pyd"))
        ]
        if len(modules) != 1 or native_bytes != archive.read(modules[0]):
            raise RuntimeError(
                "imported uvicorn-rs extension does not match --server-wheel"
            )

    server_distribution = importlib.metadata.distribution("uvicorn-rs")
    requirements = list(server_distribution.requires or [])
    if any("starlette" in requirement.lower() for requirement in requirements):
        raise RuntimeError("uvicorn-rs declares a Starlette runtime dependency")
    installed_files = [str(path) for path in (server_distribution.files or [])]
    if any(
        path.startswith(("starlette/", "starlette_rs_py/")) for path in installed_files
    ):
        raise RuntimeError("the uvicorn-rs distribution bundles a Starlette package")

    return {
        "python": sys.version,
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": sys.platform,
        "framework": framework,
        "framework_distribution": framework_distribution,
        "framework_version": framework_version,
        "framework_files": [str(path) for path in framework_files],
        "starlette_rs_native_sha256": native_hash,
        "server_wheel": str(server_wheel),
        "server_wheel_sha256": server_wheel_sha256,
        "framework_wheel": str(framework_wheel.resolve()) if framework_wheel else None,
        "framework_wheel_sha256": framework_wheel_sha256,
        "integration_app_sha256": hashlib.sha256(
            (ROOT / "examples/starlette_compat_asgi.py").read_bytes()
        ).hexdigest(),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "uvicorn_version": importlib.metadata.version("uvicorn"),
        "uvicorn_rs_version": server_distribution.version,
        "uvicorn_rs_package": str(package_path),
        "uvicorn_rs_native": str(native_path),
        "uvicorn_rs_native_sha256": hashlib.sha256(native_bytes).hexdigest(),
        "uvicorn_rs_runtime_requirements": requirements,
        "uvicorn_rs_bundle_has_framework": False,
    }


def _wait_listening(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _, stderr = process.communicate()
            raise RuntimeError(
                f"server exited during startup ({process.returncode}):\n{stderr}"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError as error:
            last_error = error
            time.sleep(0.03)
    raise TimeoutError(f"server did not listen within ten seconds: {last_error}")


def _start_server(server: str, port: int, marker_dir: Path) -> subprocess.Popen[str]:
    module = "uvicorn" if server == "uvicorn" else "uvicorn_rs"
    command = [
        sys.executable,
        "-m",
        module,
        APP,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if server == "uvicorn-rs":
        command.extend(["--graceful-timeout", "2"])
    environment = os.environ.copy()
    paths = [str(ROOT)]
    if environment.get("PYTHONPATH"):
        paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    environment["UVICORN_RS_LIFESPAN_MARKER"] = str(marker_dir / "lifespan.txt")
    environment["UVICORN_RS_BACKGROUND_MARKER"] = str(marker_dir / "background.txt")
    process = subprocess.Popen(
        command,
        cwd=marker_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_listening(port, process)
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stderr:
            process.stderr.close()
        raise
    return process


def _http_request(
    port: int, method: str, path: str, chunks: tuple[bytes, ...] | None = None
) -> tuple[int, bytes]:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.settimeout(5)
        request = client.makefile("rwb", buffering=0)
        if chunks is None:
            request.write(
                f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
            )
        else:
            request.write(
                f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
                "Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n".encode()
            )
            for chunk in chunks:
                request.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                time.sleep(0.01)
            request.write(b"0\r\n\r\n")
        status_line = request.readline().decode("latin-1").rstrip("\r\n")
        fields = status_line.split(" ", 2)
        if len(fields) < 2 or not fields[0].startswith("HTTP/1."):
            raise RuntimeError(f"invalid HTTP status line: {status_line!r}")
        status = int(fields[1])
        headers: dict[str, str] = {}
        while True:
            line = request.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            name, separator, value = line.decode("latin-1").partition(":")
            if not separator:
                raise RuntimeError(f"invalid HTTP response header: {line!r}")
            headers[name.strip().lower()] = value.strip()
        if headers.get("transfer-encoding", "").lower() == "chunked":
            body_parts: list[bytes] = []
            while True:
                size_line = request.readline().split(b";", 1)[0].strip()
                size = int(size_line, 16)
                if size == 0:
                    while request.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    break
                body_parts.append(request.read(size))
                if request.read(2) != b"\r\n":
                    raise RuntimeError("malformed chunked response terminator")
            body = b"".join(body_parts)
        elif "content-length" in headers:
            body = request.read(int(headers["content-length"]))
        else:
            body = request.read()
        return status, body


def _stream_response(port: int) -> dict[str, object]:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.settimeout(5)
        stream = client.makefile("rwb", buffering=0)
        stream.write(
            b"GET /stream HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n"
        )
        status_line = stream.readline().decode("latin-1").rstrip("\r\n")
        fields = status_line.split(" ", 2)
        if len(fields) < 2:
            raise RuntimeError(f"invalid streaming status line: {status_line!r}")
        status = int(fields[1])
        headers: dict[str, str] = {}
        while True:
            line = stream.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            name, separator, value = line.decode("latin-1").partition(":")
            if not separator:
                raise RuntimeError(f"invalid streaming response header: {line!r}")
            headers[name.strip().lower()] = value.strip()
        if headers.get("transfer-encoding", "").lower() != "chunked":
            raise RuntimeError(
                "StreamingResponse did not use HTTP/1.1 chunked transfer encoding"
            )
        chunks: list[bytes] = []
        while True:
            size_line = stream.readline().split(b";", 1)[0].strip()
            size = int(size_line, 16)
            if size == 0:
                while stream.readline() not in (b"\r\n", b"\n", b""):
                    pass
                break
            chunks.append(stream.read(size))
            if stream.read(2) != b"\r\n":
                raise RuntimeError("malformed streaming response chunk")
        return {
            "status": status,
            "chunks": [chunk.decode("ascii") for chunk in chunks],
            "body": b"".join(chunks).decode("ascii"),
            "transfer_encoding": headers["transfer-encoding"],
        }


def _masked_frame(opcode: int, payload: bytes) -> bytes:
    mask = os.urandom(4)
    size = len(payload)
    if size < 126:
        header = bytes((0x80 | opcode, 0x80 | size))
    elif size <= 0xFFFF:
        header = bytes((0x80 | opcode, 0x80 | 126)) + size.to_bytes(2, "big")
    else:
        header = bytes((0x80 | opcode, 0x80 | 127)) + size.to_bytes(8, "big")
    return (
        header
        + mask
        + bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    )


def _read_frame(stream) -> tuple[int, bytes]:
    first, second = stream.read(2)
    opcode = first & 0x0F
    size = second & 0x7F
    if size == 126:
        size = int.from_bytes(stream.read(2), "big")
    elif size == 127:
        size = int.from_bytes(stream.read(8), "big")
    masked = bool(second & 0x80)
    mask = stream.read(4) if masked else b""
    payload = stream.read(size)
    if len(payload) != size:
        raise RuntimeError("truncated WebSocket frame")
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return opcode, payload


def _websocket_probe(port: int) -> dict[str, object]:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
        client.settimeout(5)
        stream = client.makefile("rwb", buffering=0)
        stream.write(
            (
                "GET /ws HTTP/1.1\r\n"
                "Host: localhost\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Protocol: integration\r\n\r\n"
            ).encode("ascii")
        )
        status_line = stream.readline().decode("latin-1").rstrip("\r\n")
        fields = status_line.split(" ", 2)
        if len(fields) < 2:
            raise RuntimeError(f"invalid WebSocket status line: {status_line!r}")
        status = int(fields[1])
        headers: dict[str, str] = {}
        while True:
            line = stream.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            name, separator, value = line.decode("latin-1").partition(":")
            if not separator:
                raise RuntimeError(f"invalid WebSocket response header: {line!r}")
            headers[name.strip().lower()] = value.strip()
        expected_accept = base64.b64encode(
            hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if headers.get("sec-websocket-accept") != expected_accept:
            raise RuntimeError("WebSocket handshake returned the wrong accept digest")
        if headers.get("sec-websocket-protocol") != "integration":
            raise RuntimeError(
                "WebSocket server did not select the offered subprotocol"
            )
        stream.write(_masked_frame(0x1, b"hello"))
        opcode, payload = _read_frame(stream)
        if opcode != 0x1:
            raise RuntimeError(f"expected a WebSocket text frame, got opcode {opcode}")
        text = payload.decode("utf-8")
        stream.write(_masked_frame(0x8, (1000).to_bytes(2, "big")))
        return {
            "status": status,
            "subprotocol": headers["sec-websocket-protocol"],
            "echo": text,
        }


def _run_server(server: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"uvicorn-rs-{server}-") as temp:
        marker_dir = Path(temp)
        port = _free_port()
        process = _start_server(server, port, marker_dir)
        observations: dict[str, object] = {}
        try:
            status, body = _http_request(port, "GET", "/state")
            if status != 200 or body != b"state:integration-lifespan-token":
                raise RuntimeError(
                    f"{server} lifespan-backed route failed: {status} {body!r}"
                )
            observations["lifespan_state"] = {"status": status, "body": body.decode()}

            streamed = _stream_response(port)
            if (
                streamed["status"] != 200
                or streamed["chunks"] != [chunk.decode() for chunk in STREAM_BODY]
                or streamed["body"] != b"".join(STREAM_BODY).decode()
            ):
                raise RuntimeError(
                    f"{server} response streaming differed: {streamed!r}"
                )
            observations["response_stream"] = streamed

            status, body = _http_request(port, "POST", "/upload", UPLOAD_BODY)
            expected_upload = b"upload:" + b"".join(UPLOAD_BODY)
            if status != 200 or body != expected_upload:
                raise RuntimeError(
                    f"{server} request streaming failed: {status} {body!r}"
                )
            observations["request_stream"] = {"status": status, "body": body.decode()}

            status, body = _http_request(port, "GET", "/background")
            background_marker = marker_dir / "background.txt"
            deadline = time.monotonic() + 2
            while not background_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if (
                status != 200
                or body != b"background:accepted"
                or not background_marker.exists()
                or background_marker.read_text(encoding="utf-8") != "complete\n"
            ):
                raise RuntimeError(
                    "Starlette background task did not finish after the response"
                )
            observations["background_task"] = {
                "status": status,
                "body": body.decode(),
                "completed": True,
            }

            websocket = _websocket_probe(port)
            if websocket != {
                "status": 101,
                "subprotocol": "integration",
                "echo": "echo:hello",
            }:
                raise RuntimeError(
                    f"{server} WebSocket behavior differed: {websocket!r}"
                )
            observations["websocket"] = websocket

            status, body = _http_request(port, "GET", "/error")
            if status != 500 or body != b"Internal Server Error":
                raise RuntimeError(
                    f"{server} exception response differed: {status} {body!r}"
                )
            observations["application_error"] = {
                "status": status,
                "body": body.decode(),
            }

            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    f"{server} did not stop within five seconds after SIGTERM"
                ) from error
            elapsed = time.monotonic() - started
            _, stderr = process.communicate()
            accepted_exit_codes = (
                (0,) if server == "uvicorn-rs" else (0, -signal.SIGTERM)
            )
            if process.returncode not in accepted_exit_codes:
                raise RuntimeError(
                    f"{server} shutdown exited {process.returncode}:\n{stderr}"
                )
            if elapsed > 5:
                raise RuntimeError(f"{server} exceeded the five-second shutdown bound")
            lifespan_marker = marker_dir / "lifespan.txt"
            if not lifespan_marker.exists() or lifespan_marker.read_text(
                encoding="utf-8"
            ) != ("startup\nshutdown\n"):
                raise RuntimeError(
                    f"{server} did not complete Starlette lifespan shutdown:\n{stderr}"
                )
            observations["lifespan_shutdown"] = True
            return {
                "observations": observations,
                "shutdown": {
                    "signal": "SIGTERM",
                    "exit_code": process.returncode,
                    "elapsed_seconds": round(elapsed, 6),
                    "bounded_seconds": 5,
                },
            }
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if process.stderr:
                process.stderr.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--framework",
        choices=("starlette", "starlette-rs"),
        required=True,
        help="which mutually exclusive starlette namespace is installed",
    )
    parser.add_argument("--server-wheel", type=Path, required=True)
    parser.add_argument("--framework-wheel", type=Path)
    parser.add_argument(
        "--output", type=Path, help="write the full JSON receipt to this path"
    )
    args = parser.parse_args()
    identity = _identity(args.framework, args.server_wheel, args.framework_wheel)
    reference = _run_server("uvicorn")
    candidate = _run_server("uvicorn-rs")
    if reference["observations"] != candidate["observations"]:
        raise RuntimeError(
            "Uvicorn and uvicorn-rs returned different application observations:\n"
            + json.dumps(
                {
                    "uvicorn": reference["observations"],
                    "uvicorn-rs": candidate["observations"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    result = {
        "schema": "uvicorn-rs-starlette-integration@1",
        "status": "passed",
        "identity": identity,
        "app": APP,
        "same_app_for_both_servers": True,
        "parity": "all observed HTTP, streaming, WebSocket, background, error, and lifespan values match",
        "servers": {"uvicorn": reference, "uvicorn-rs": candidate},
        "scope_note": (
            "The shared HTTP routes use the common Starlette API subset. WebSocket transport is "
            "exercised by a plain ASGI branch because the pinned starlette-rs revision does not "
            "yet expose Starlette WebSocketRoute."
        ),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"PASS: {args.framework} parity; receipt={args.output}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
