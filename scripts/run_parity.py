#!/usr/bin/env python3
"""Execute input-only black-box workflows against a reference and uvicorn-rs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import DataReceived, ResponseReceived, StreamEnded
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect as websocket_connect


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "parity"
MANIFEST_PATH = FIXTURES / "manifest.json"
APP = "tests.parity.app:app"
MANIFEST_SCHEMA = "uvicorn-rs-parity/manifest@2"
INPUT_SCHEMA = "uvicorn-rs-parity/input@2"
RESULT_SCHEMA = "uvicorn-rs-parity/result@2"


class ParityError(RuntimeError):
    """Invalid parity contract or failed adapter infrastructure."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def exact_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    actual = set(value)
    if actual != required:
        raise ParityError(
            f"{label} fields differ: missing={sorted(required - actual)}, "
            f"unknown={sorted(actual - required)}"
        )


def load_contract(
    manifest_path: Path = MANIFEST_PATH,
    fixture_root: Path = FIXTURES,
) -> tuple[dict[str, Any], dict[str, Any], list[Path]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exact_keys(
        manifest,
        {
            "schema", "scope", "oracles", "target", "profiles", "operations",
            "inputs", "result_schema", "normalization",
        },
        "manifest",
    )
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ParityError(f"unsupported manifest schema: {manifest['schema']!r}")
    if manifest["result_schema"] != RESULT_SCHEMA:
        raise ParityError("manifest result schema is unsupported")
    if not isinstance(manifest["inputs"], list) or not manifest["inputs"]:
        raise ParityError("manifest.inputs must be a non-empty path list")
    if any(not isinstance(item, str) or not item for item in manifest["inputs"]):
        raise ParityError("manifest.inputs must contain non-empty relative paths")
    if len(manifest["inputs"]) != len(set(manifest["inputs"])):
        raise ParityError("manifest.inputs contains duplicate paths")
    indexed_paths = []
    for relative in manifest["inputs"]:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not relative.startswith("inputs/"):
            raise ParityError(f"manifest input path must stay beneath inputs/: {relative!r}")
        indexed_paths.append(fixture_root / candidate)
    discovered_paths = sorted((fixture_root / "inputs").rglob("*.json"))
    if sorted(indexed_paths) != discovered_paths:
        missing = sorted(str(path.relative_to(fixture_root)) for path in set(discovered_paths) - set(indexed_paths))
        stale = sorted(str(path.relative_to(fixture_root)) for path in set(indexed_paths) - set(discovered_paths))
        raise ParityError(f"manifest input index differs from files: unindexed={missing}, missing={stale}")
    exact_keys(manifest["scope"], {"id", "mode", "authority", "description"}, "manifest.scope")
    exact_keys(manifest["target"], {"id", "name", "revision", "runtime", "protocols"}, "manifest.target")
    if manifest["target"]["id"] != "uvicorn-rs":
        raise ParityError("manifest target identity must be uvicorn-rs")
    oracle_ids: set[str] = set()
    for oracle in manifest["oracles"]:
        exact_keys(oracle, {"id", "name", "version", "runtime", "protocols", "components"}, "manifest oracle")
        if not isinstance(oracle["id"], str) or not oracle["id"] or oracle["id"] in oracle_ids:
            raise ParityError(f"missing or duplicate oracle ID: {oracle['id']!r}")
        oracle_ids.add(oracle["id"])
        if not isinstance(oracle["protocols"], list) or not oracle["protocols"]:
            raise ParityError(f"{oracle['id']}: protocols must be a non-empty array")
        component_ids = set()
        for component in oracle["components"]:
            exact_keys(component, {"id", "version"}, f"{oracle['id']} oracle component")
            if not isinstance(component["id"], str) or not component["id"] or component["id"] in component_ids:
                raise ParityError(f"{oracle['id']}: missing or duplicate component ID")
            if not isinstance(component["version"], str) or not component["version"]:
                raise ParityError(f"{oracle['id']}/{component['id']}: component version is required")
            component_ids.add(component["id"])
    for profile in manifest["profiles"]:
        exact_keys(profile, {"id", "oracle", "protocol", "oracle_config"}, "manifest profile")
    if len({profile["id"] for profile in manifest["profiles"]}) != len(manifest["profiles"]):
        raise ParityError("duplicate profile ID")
    observation_fields = {
        "status", "content_type", "body_bytes", "ordered_body_bytes", "early_body_bytes",
        "streamed_before_completion", "disconnect_event", "followup_response",
        "handshake_status", "subprotocol", "ordered_messages", "state_response",
        "process_terminated", "application_events",
    }
    for operation in manifest["operations"]:
        expected_operation_keys = {"id", "kind", "observe"}
        if "required_observations" in operation:
            expected_operation_keys.add("required_observations")
            if not set(operation["required_observations"]).issubset(observation_fields):
                raise ParityError(f"{operation.get('id')}: unknown required observation")
        exact_keys(operation, expected_operation_keys, "manifest operation")
        if (
            not isinstance(operation["observe"], list)
            or not operation["observe"]
            or len(operation["observe"]) != len(set(operation["observe"]))
            or not set(operation["observe"]).issubset(observation_fields)
        ):
            raise ParityError(f"{operation.get('id')}: unsupported observation field")
        required = operation.get("required_observations", {})
        if not isinstance(required, dict) or not set(required).issubset(operation["observe"]):
            raise ParityError(f"{operation.get('id')}: required observations must be declared in observe")

    profiles = {profile["id"]: profile for profile in manifest["profiles"]}
    operations = {operation["id"]: operation for operation in manifest["operations"]}
    if len(profiles) != len(manifest["profiles"]):
        raise ParityError("duplicate profile ID")
    if len(operations) != len(manifest["operations"]):
        raise ParityError("duplicate operation ID")
    if any(profile["oracle"] not in oracle_ids for profile in profiles.values()):
        raise ParityError("profile references an undeclared oracle")
    oracle_protocols = {oracle["id"]: set(oracle["protocols"]) for oracle in manifest["oracles"]}
    for profile in profiles.values():
        required_protocols = {part.strip() for part in profile["protocol"].split("+")}
        if not required_protocols.issubset(oracle_protocols[profile["oracle"]]):
            raise ParityError(f"{profile['id']}: oracle does not declare every profile protocol")
    if {path.stem for path in indexed_paths} != set(profiles):
        raise ParityError("the active input index must contain exactly one file per declared profile")

    case_ids: set[str] = set()
    operation_case_counts = {operation_id: 0 for operation_id in operations}
    profile_case_counts = {profile_id: 0 for profile_id in profiles}
    input_cases = []
    for input_path in indexed_paths:
        input_document = json.loads(input_path.read_text(encoding="utf-8"))
        exact_keys(input_document, {"schema", "cases"}, f"parity input {input_path.name}")
        if input_document["schema"] != INPUT_SCHEMA:
            raise ParityError(f"unsupported input schema in {input_path.name}: {input_document['schema']!r}")
        if not isinstance(input_document["cases"], list):
            raise ParityError(f"{input_path.name}: cases must be an array")
        if not input_document["cases"]:
            raise ParityError(f"{input_path.name}: active profile inputs must not be empty")
        if any(case.get("profile") != input_path.stem for case in input_document["cases"] if isinstance(case, dict)):
            raise ParityError(f"{input_path.name}: cases must belong to the file's declared profile")
        input_cases.extend(input_document["cases"])

    for case in input_cases:
        if not isinstance(case, dict):
            raise ParityError("every case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ParityError(f"missing, invalid, or duplicate case ID: {case_id!r}")
        case_ids.add(case_id)
        if case.get("profile") not in profiles:
            raise ParityError(f"{case_id}: undeclared profile {case.get('profile')!r}")
        profile_case_counts[case["profile"]] += 1
        operation = case.get("operation")
        if operation not in operations:
            raise ParityError(f"{case_id}: undeclared operation {operation!r}")
        operation_case_counts[operation] += 1
        if case.get("covers") != [operation]:
            raise ParityError(f"{case_id}: covers must identify its declared operation")
        for field in case:
            if field.startswith("expected") or field in {"oracle_output", "target_output"}:
                raise ParityError(f"{case_id}: parity inputs may not contain observed results")
        kind = case.get("profile")
        if kind in {"http1", "http2", "http3"} and "response_stream" in case:
            exact_keys(case, {"case_id", "profile", "operation", "covers", "response_stream"}, case_id)
            if kind == "http3":
                raise ParityError(f"{case_id}: no H3 observation client is declared for progressive reads")
            exact_keys(case["response_stream"], {"path"}, f"{case_id}.response_stream")
            if not case["response_stream"]["path"].startswith("/"):
                raise ParityError(f"{case_id}: response stream path must be origin-form")
        elif kind in {"http1", "http2", "http3"} and "disconnect" in case:
            exact_keys(case, {"case_id", "profile", "operation", "covers", "disconnect"}, case_id)
            if kind != "http1":
                raise ParityError(f"{case_id}: disconnect workflow is currently scoped to HTTP/1.1")
            exact_keys(case["disconnect"], {"path", "followup_path"}, f"{case_id}.disconnect")
        elif kind in {"http1", "http2", "http3"} and "request_stream" in case:
            exact_keys(case, {"case_id", "profile", "operation", "covers", "request_stream"}, case_id)
            if kind == "http3":
                raise ParityError(f"{case_id}: request streaming has no declared H3 reference workflow")
            stream = case["request_stream"]
            exact_keys(stream, {"method", "path", "headers", "chunks_base64"}, f"{case_id}.request_stream")
            if len(stream["chunks_base64"]) < 2:
                raise ParityError(f"{case_id}: request streaming requires at least two input chunks")
            try:
                for chunk in stream["chunks_base64"]:
                    base64.b64decode(chunk, validate=True)
            except (ValueError, TypeError) as error:
                raise ParityError(f"{case_id}: invalid request-stream base64") from error
        elif kind in {"http1", "http2", "http3"}:
            exact_keys(case, {"case_id", "profile", "operation", "covers", "request"}, case_id)
            request = case["request"]
            exact_keys(request, {"method", "path", "headers", "body_base64"}, f"{case_id}.request")
            try:
                base64.b64decode(request["body_base64"], validate=True)
            except (ValueError, TypeError) as error:
                raise ParityError(f"{case_id}: invalid request body base64") from error
            if not isinstance(request["path"], str) or not request["path"].startswith("/"):
                raise ParityError(f"{case_id}: request path must be origin-form")
            if kind == "http3" and (request["method"] != "GET" or request["body_base64"]):
                raise ParityError(f"{case_id}: current H3 client supports bodyless GET only")
            if not isinstance(request["headers"], list) or any(
                not isinstance(header, list)
                or len(header) != 2
                or not all(isinstance(part, str) for part in header)
                for header in request["headers"]
            ):
                raise ParityError(f"{case_id}: headers must be pairs of strings")
        elif kind == "websocket":
            exact_keys(case, {"case_id", "profile", "operation", "covers", "websocket"}, case_id)
            websocket = case["websocket"]
            exact_keys(websocket, {"path", "subprotocols", "messages"}, f"{case_id}.websocket")
            for message in websocket["messages"]:
                exact_keys(message, {"kind", "value"}, f"{case_id}.websocket message")
                if message["kind"] == "binary_base64":
                    base64.b64decode(message["value"], validate=True)
                elif message["kind"] != "text":
                    raise ParityError(f"{case_id}: unsupported WebSocket message kind")
        elif kind == "lifecycle":
            exact_keys(case, {"case_id", "profile", "operation", "covers", "lifecycle"}, case_id)
            exact_keys(
                case["lifecycle"],
                {"state_path", "hold_path", "graceful_timeout_seconds"},
                f"{case_id}.lifecycle",
            )
        elif kind == "http1-disconnect":
            raise ParityError("disconnect cases must use the http1 profile and disconnect input shape")

    missing_operations = sorted(operation for operation, count in operation_case_counts.items() if count == 0)
    missing_profiles = sorted(profile for profile, count in profile_case_counts.items() if count == 0)
    if missing_operations or missing_profiles:
        raise ParityError(f"unrepresented manifest entries: operations={missing_operations}, profiles={missing_profiles}")
    combined_inputs = {"schema": INPUT_SCHEMA, "cases": input_cases}
    return manifest, combined_inputs, indexed_paths


def runtime_identity(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    actual = {}
    for oracle in manifest["oracles"]:
        requirements = [(oracle["id"], oracle["version"])]
        requirements.extend((component["id"], component["version"]) for component in oracle["components"])
        for distribution, required in requirements:
            try:
                observed = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError as error:
                raise ParityError(f"required reference dependency is missing: {distribution}") from error
            if observed != required:
                raise ParityError(f"{distribution} version mismatch: expected {required}, found {observed}")
            actual[distribution] = observed
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
    rustc = subprocess.run(["rustc", "--version"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    native_extension = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
    try:
        native_extension_path = str(native_extension.relative_to(ROOT))
    except ValueError:
        native_extension_path = str(native_extension)
    return (
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "rustc": rustc,
            "dependencies": actual,
        },
        {
            "revision": revision,
            "dirty": dirty,
            "native_extension": {
                "path": native_extension_path,
                "sha256": sha256(native_extension),
            },
            "cargo_lock_sha256": sha256(ROOT / "Cargo.lock"),
        },
    )


def free_port(*, tcp_and_udp: bool = False) -> int:
    for _ in range(128):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            try:
                tcp.bind(("127.0.0.1", 0))
                port = tcp.getsockname()[1]
                if tcp_and_udp:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                        udp.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError("could not find an available test port")


def make_certificate(directory: Path) -> tuple[Path, Path]:
    certificate, key = directory / "server.pem", directory / "server-key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    return certificate, key


def build_h3_client() -> Path:
    subprocess.run(
        [
            "cargo", "build", "--quiet", "--release", "--manifest-path",
            "tools/http3-probe/Cargo.toml", "--bin", "parity-http3",
        ],
        cwd=ROOT,
        check=True,
        timeout=300,
    )
    return ROOT / "tools" / "http3-probe" / "target" / "release" / "parity-http3"


def start_server(
    server_id: str,
    profile: dict[str, Any],
    graceful_timeout_seconds: int,
    port: int,
    events_path: Path,
    certificate: Path | None,
    key: Path | None,
    config_path: Path,
) -> dict[str, Any]:
    profile_id = profile["id"]
    env = os.environ.copy()
    env["ASGI_PARITY_EVENTS"] = str(events_path)
    common = ["--host", "127.0.0.1", "--port", str(port)]
    if server_id == "uvicorn-rs":
        command = [sys.executable, "-m", "uvicorn_rs", APP, *common, "--loop", "uvloop"]
        if certificate and key:
            command.extend(["--certfile", str(certificate), "--keyfile", str(key)])
        command.extend(["--graceful-timeout", str(graceful_timeout_seconds)])
    elif server_id == "uvicorn":
        command = [
            sys.executable, "-m", "uvicorn", APP, *common, "--loop", "uvloop",
            "--http", "httptools", "--interface", "asgi3", "--ws", "websockets", "--lifespan", "on",
            "--log-level", "critical", "--no-server-header", "--timeout-graceful-shutdown",
            str(graceful_timeout_seconds),
        ]
    elif server_id == "hypercorn":
        command = [
            sys.executable, "-m", "hypercorn", f"asgi:{APP}", "--bind", f"127.0.0.1:{port}",
            "--worker-class", "uvloop", "--log-level", "critical", "--access-logfile", "/dev/null",
            "--certfile", str(certificate), "--keyfile", str(key), "--config", str(config_path),
        ]
        if profile_id == "http3":
            command.extend(["--quic-bind", f"127.0.0.1:{port}"])
    else:
        raise ParityError(f"unknown server adapter: {server_id}")

    log = tempfile.TemporaryFile(mode="w+t")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        text=True,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log.seek(0)
            output = log.read()[-6000:]
            log.close()
            raise ParityError(f"{server_id}/{profile_id} exited at startup ({process.returncode}):\n{output}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return {"id": server_id, "process": process, "port": port, "events": events_path, "log": log}
        except OSError:
            time.sleep(0.05)
    stop_server({"process": process, "log": log})
    raise ParityError(f"{server_id}/{profile_id} did not open its TCP listener")


def stop_server(server: dict[str, Any], *, graceful: bool = False) -> tuple[int | None, str]:
    process: subprocess.Popen = server["process"]
    log = server["log"]
    if log.closed:
        return process.returncode, ""
    if process.poll() is None:
        if graceful:
            process.terminate()
        else:
            process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    log.seek(0)
    text = log.read()
    log.close()
    return process.returncode, text[-6000:]


def read_events(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def response_observation(status: int, headers: list[tuple[str, str]], body: bytes) -> dict[str, Any]:
    content_type = next((value for name, value in headers if name.lower() == "content-type"), None)
    return {"status": status, "content_type": content_type, "body_base64": base64.b64encode(body).decode("ascii")}


def http1_request(port: int, request: dict[str, Any]) -> dict[str, Any]:
    body = base64.b64decode(request["body_base64"], validate=True)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(request["method"], request["path"], body=body, headers=dict(request["headers"]))
        response = connection.getresponse()
        payload = response.read()
        return response_observation(response.status, response.getheaders(), payload)
    finally:
        connection.close()


def read_http1_chunk(reader) -> bytes | None:
    line = reader.readline()
    if not line:
        raise ParityError("HTTP/1.1 server closed before completing chunked output")
    try:
        size = int(line.split(b";", maxsplit=1)[0].strip(), 16)
    except ValueError as error:
        raise ParityError(f"invalid chunked response-size line: {line!r}") from error
    if size == 0:
        while reader.readline() != b"\r\n":
            pass
        return None
    data = reader.read(size)
    if len(data) != size or reader.read(2) != b"\r\n":
        raise ParityError("truncated HTTP/1.1 response chunk")
    return data


def http1_streaming_request(port: int, specification: dict[str, Any]) -> dict[str, Any]:
    chunks = [base64.b64decode(item, validate=True) for item in specification["chunks_base64"]]
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.settimeout(10)
    reader = client.makefile("rb")
    try:
        headers = [
            f"{specification['method']} {specification['path']} HTTP/1.1\r\n",
            "Host: localhost\r\n",
            "Transfer-Encoding: chunked\r\n",
            "Connection: close\r\n",
        ]
        headers.extend(f"{name}: {value}\r\n" for name, value in specification["headers"])
        client.sendall(("".join(headers) + "\r\n").encode("ascii"))
        first_request_chunk = chunks[0]
        client.sendall(f"{len(first_request_chunk):x}\r\n".encode() + first_request_chunk + b"\r\n")

        status_line = reader.readline()
        if not status_line:
            raise ParityError("HTTP/1.1 server closed before starting its streaming response")
        status = int(status_line.split()[1])
        response_headers = []
        while True:
            line = reader.readline()
            if line == b"\r\n":
                break
            if not line:
                raise ParityError("HTTP/1.1 response ended before its headers were complete")
            name, value = line.decode("latin-1").split(":", maxsplit=1)
            response_headers.append((name.strip().lower(), value.strip()))

        early_body = read_http1_chunk(reader)
        if early_body is None:
            raise ParityError("response finished before the request upload was complete")
        for chunk in chunks[1:]:
            client.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
        client.sendall(b"0\r\n\r\n")
        response_chunks = [early_body]
        while (chunk := read_http1_chunk(reader)) is not None:
            response_chunks.append(chunk)
        result = response_observation(status, response_headers, b"".join(response_chunks))
        result["early_body_base64"] = base64.b64encode(early_body).decode("ascii")
        return result
    finally:
        reader.close()
        client.close()


def http1_response_streaming_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.settimeout(10)
    reader = client.makefile("rb")
    try:
        client.sendall(
            f"GET {specification['path']} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        status_line = reader.readline()
        if not status_line:
            raise ParityError("HTTP/1.1 server closed before starting its response stream")
        status = int(status_line.split()[1])
        response_headers = []
        while True:
            line = reader.readline()
            if line == b"\r\n":
                break
            if not line:
                raise ParityError("HTTP/1.1 response ended before its headers were complete")
            name, value = line.decode("latin-1").split(":", maxsplit=1)
            response_headers.append((name.strip().lower(), value.strip()))
        early_body = read_http1_chunk(reader)
        if early_body is None:
            raise ParityError("HTTP/1.1 response ended without a data chunk")
        streamed_before_completion = "response.finished" not in read_events(events_path)
        chunks = [early_body]
        while (chunk := read_http1_chunk(reader)) is not None:
            chunks.append(chunk)
        result = response_observation(status, response_headers, b"".join(chunks))
        result.update({
            "early_body_base64": base64.b64encode(early_body).decode("ascii"),
            "streamed_before_completion": streamed_before_completion,
        })
        return result
    finally:
        reader.close()
        client.close()


def http2_request(port: int, request: dict[str, Any]) -> dict[str, Any]:
    body = base64.b64decode(request["body_base64"], validate=True)
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    headers = [
        (":method", request["method"]),
        (":scheme", "https"),
        (":authority", f"localhost:{port}"),
        (":path", request["path"]),
    ]
    headers.extend((name.lower(), value) for name, value in request["headers"])
    if body:
        headers.append(("content-length", str(len(body))))
    connection.send_headers(stream_id, headers, end_stream=not body)
    if body:
        connection.send_data(stream_id, body, end_stream=True)
    tls_socket.sendall(connection.data_to_send())
    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    try:
        while True:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    pending = connection.data_to_send()
                    if pending:
                        tls_socket.sendall(pending)
                    return response_observation(status, response_headers, bytes(response_body))
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
    finally:
        tls_socket.close()


def http2_streaming_request(port: int, specification: dict[str, Any]) -> dict[str, Any]:
    chunks = [base64.b64decode(item, validate=True) for item in specification["chunks_base64"]]
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    headers = [
        (":method", specification["method"]),
        (":scheme", "https"),
        (":authority", f"localhost:{port}"),
        (":path", specification["path"]),
    ]
    headers.extend((name.lower(), value) for name, value in specification["headers"])
    connection.send_headers(stream_id, headers, end_stream=False)
    connection.send_data(stream_id, chunks[0], end_stream=False)
    tls_socket.sendall(connection.data_to_send())

    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    early_body = None
    ended = False
    try:
        while early_body is None:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    early_body = bytes(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
            if ended and early_body is None:
                raise ParityError("HTTP/2 response ended before request upload completed")

        for index, chunk in enumerate(chunks[1:]):
            connection.send_data(stream_id, chunk, end_stream=index == len(chunks[1:]) - 1)
        tls_socket.sendall(connection.data_to_send())
        while not ended:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        result = response_observation(status, response_headers, bytes(response_body))
        result["early_body_base64"] = base64.b64encode(early_body).decode("ascii")
        return result
    finally:
        tls_socket.close()


def http2_response_streaming_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    connection.send_headers(
        stream_id,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":authority", f"localhost:{port}"),
            (":path", specification["path"]),
        ],
        end_stream=True,
    )
    tls_socket.sendall(connection.data_to_send())
    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    early_body = None
    ended = False
    try:
        while early_body is None:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    early_body = bytes(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
            if ended and early_body is None:
                raise ParityError("HTTP/2 response ended without a data chunk")
        streamed_before_completion = "response.finished" not in read_events(events_path)

        while not ended:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        result = response_observation(status, response_headers, bytes(response_body))
        result.update({
            "early_body_base64": base64.b64encode(early_body).decode("ascii"),
            "streamed_before_completion": streamed_before_completion,
        })
        return result
    finally:
        tls_socket.close()


def http3_request(port: int, certificate: Path, request: dict[str, Any], client: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(client), f"127.0.0.1:{port}", str(certificate), request["path"]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip() or "no client diagnostic"
        raise ParityError(
            f"HTTP/3 probe client exited {result.returncode}: {diagnostic[-800:]}"
        )
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        diagnostic = result.stdout.strip() or result.stderr.strip() or "empty client output"
        raise ParityError(
            f"HTTP/3 probe client returned invalid JSON: {diagnostic[-800:]}"
        ) from error
    body = bytes.fromhex(response["body_hex"])
    return response_observation(response["status"], [("content-type", response["content_type"] or "")], body)


def websocket_observation(port: int, specification: dict[str, Any]) -> dict[str, Any]:
    uri = f"ws://127.0.0.1:{port}{specification['path']}"
    try:
        with websocket_connect(
            uri,
            subprotocols=specification["subprotocols"],
            open_timeout=10,
            close_timeout=2,
        ) as websocket:
            echoes = []
            for message in specification["messages"]:
                if message["kind"] == "text":
                    websocket.send(message["value"])
                    echoed = websocket.recv()
                    echoes.append({"kind": "text", "value": echoed})
                else:
                    sent = base64.b64decode(message["value"], validate=True)
                    websocket.send(sent)
                    echoed = websocket.recv()
                    if not isinstance(echoed, bytes):
                        raise ParityError("binary WebSocket message came back as text")
                    echoes.append({"kind": "binary_base64", "value": base64.b64encode(echoed).decode("ascii")})
            return {"handshake_status": 101, "subprotocol": websocket.subprotocol, "messages": echoes}
    except InvalidStatus as error:
        return {"handshake_status": error.response.status_code}


def project_observation(raw: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    source_fields = {
        "status": "status",
        "content_type": "content_type",
        "body_bytes": "body_base64",
        "ordered_body_bytes": "body_base64",
        "early_body_bytes": "early_body_base64",
        "streamed_before_completion": "streamed_before_completion",
        "disconnect_event": "disconnect_event",
        "followup_response": "followup",
        "handshake_status": "handshake_status",
        "subprotocol": "subprotocol",
        "ordered_messages": "messages",
        "state_response": "state_response",
        "process_terminated": "process_terminated",
        "application_events": "application_events",
    }
    projected = {}
    for field in operation["observe"]:
        source = source_fields[field]
        if source not in raw:
            raise ParityError(f"adapter omitted declared observation {field!r}")
        projected[field] = raw[source]
    return projected


def execute_case(
    case: dict[str, Any], server: dict[str, Any], profile: dict[str, Any],
    certificate: Path | None, h3_client: Path | None,
) -> dict[str, Any]:
    if "response_stream" in case:
        if profile["id"] == "http1":
            return http1_response_streaming_request(server["port"], case["response_stream"], server["events"])
        if profile["id"] == "http2":
            return http2_response_streaming_request(server["port"], case["response_stream"], server["events"])
    if "request_stream" in case:
        if profile["id"] == "http1":
            return http1_streaming_request(server["port"], case["request_stream"])
        if profile["id"] == "http2":
            return http2_streaming_request(server["port"], case["request_stream"])
    if "request" in case:
        profile_id = profile["id"]
        if profile_id in {"http1", "lifecycle"}:
            return http1_request(server["port"], case["request"])
        if profile_id == "http2":
            return http2_request(server["port"], case["request"])
        if profile_id == "http3":
            if certificate is None or h3_client is None:
                raise ParityError("HTTP/3 adapter is missing its certificate or client")
            return http3_request(server["port"], certificate, case["request"], h3_client)
    if "websocket" in case:
        return websocket_observation(server["port"], case["websocket"])
    if "disconnect" in case:
        disconnect = case["disconnect"]
        with socket.create_connection(("127.0.0.1", server["port"]), timeout=5) as client:
            client.sendall(
                f"POST {disconnect['path']} HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n".encode()
            )
        deadline = time.monotonic() + 3
        seen = False
        while time.monotonic() < deadline:
            seen = "http.disconnect" in read_events(server["events"])
            if seen:
                break
            time.sleep(0.02)
        followup = http1_request(server["port"], {
            "method": "GET", "path": disconnect["followup_path"], "headers": [], "body_base64": ""
        })
        return {"disconnect_event": seen, "followup": followup}
    if "lifecycle" in case:
        lifecycle = case["lifecycle"]
        state = http1_request(server["port"], {
            "method": "GET", "path": lifecycle["state_path"], "headers": [], "body_base64": ""
        })
        pending = socket.create_connection(("127.0.0.1", server["port"]), timeout=5)
        pending.sendall(
            f"GET {lifecycle['hold_path']} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and "request.hold" not in read_events(server["events"]):
                time.sleep(0.02)
            if "request.hold" not in read_events(server["events"]):
                raise ParityError(
                    "hold request did not enter the ASGI app before shutdown "
                    f"(events={read_events(server['events'])!r}, "
                    f"exit_code={server['process'].poll()!r}, state_response={state!r})"
                )
            exit_code, _ = stop_server(server, graceful=True)
            events = read_events(server["events"])
        finally:
            pending.close()
        return {
            "state_response": state,
            "process_terminated": exit_code is not None,
            "process_exit_code": exit_code,
            "application_events": events,
        }
    raise ParityError(f"no adapter for case {case['case_id']}")


def start_profile_servers(
    profile: dict[str, Any], tempdir: Path, cases: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], Path | None]:
    profile_id = profile["id"]
    tls = profile_id in {"http2", "http3"}
    certificate, key = make_certificate(tempdir) if tls else (None, None)
    config = tempdir / "hypercorn.toml"
    config.write_text("keep_alive_max_requests = 100000000\n", encoding="utf-8")
    graceful_timeout_seconds = next(
        (case["lifecycle"]["graceful_timeout_seconds"] for case in cases if "lifecycle" in case),
        1,
    )
    servers: dict[str, dict[str, Any]] = {}
    try:
        for server_id in (profile["oracle"], "uvicorn-rs"):
            port = free_port(tcp_and_udp=profile_id == "http3")
            events = tempdir / f"{server_id}-events.jsonl"
            servers[server_id] = start_server(
                server_id,
                profile,
                graceful_timeout_seconds,
                port,
                events,
                certificate,
                key,
                config,
            )
    except Exception:
        for server in servers.values():
            stop_server(server)
        raise
    return servers[profile["oracle"]], servers["uvicorn-rs"], certificate


def execute_profile(
    profile: dict[str, Any],
    cases: list[dict[str, Any]],
    h3_client: Path | None,
    operations: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outcomes = []
    infrastructure_errors = []
    with tempfile.TemporaryDirectory(prefix=f"uvicorn-rs-parity-{profile['id']}-") as temporary:
        tempdir = Path(temporary)
        try:
            oracle, target, certificate = start_profile_servers(profile, tempdir, cases)
        except Exception as error:
            infrastructure_errors.append({
                "profile": profile["id"],
                "server": None,
                "kind": "profile_startup_failure",
                "diagnostic": str(error)[-1000:],
            })
            for case in cases:
                outcomes.append({
                    "case_id": case["case_id"],
                    "profile": profile["id"],
                    "operation": case["operation"],
                    "requirements": case["covers"],
                    "status": "not_run",
                    "reason": "profile startup failed before this case could execute",
                })
            return outcomes, infrastructure_errors
        servers = {oracle["id"]: oracle, target["id"]: target}
        try:
            for case_index, case in enumerate(cases):
                try:
                    try:
                        oracle_raw = execute_case(case, oracle, profile, certificate, h3_client)
                    except Exception as error:
                        raise ParityError(f"oracle {oracle['id']} adapter failed: {error}") from error
                    try:
                        target_raw = execute_case(case, target, profile, certificate, h3_client)
                    except Exception as error:
                        raise ParityError(f"target uvicorn-rs adapter failed: {error}") from error
                    operation = operations[case["operation"]]
                    oracle_result = project_observation(oracle_raw, operation)
                    target_result = project_observation(target_raw, operation)
                    matches = oracle_result == target_result
                    required = operation.get("required_observations", {})
                    if any(
                        oracle_result.get(field) != value or target_result.get(field) != value
                        for field, value in required.items()
                    ):
                        matches = False
                    if not (oracle_result == target_result):
                        difference = "observed public fields differ exactly"
                    elif not matches:
                        difference = f"required observation did not match {required!r}"
                    else:
                        difference = None
                    outcomes.append({
                        "case_id": case["case_id"],
                        "profile": profile["id"],
                        "operation": case["operation"],
                        "requirements": case["covers"],
                        "status": "passed" if matches else "failed",
                        "oracle_observation": oracle_result,
                        "target_observation": target_result,
                        "server_exit_codes": {
                            "oracle": oracle["process"].returncode,
                            "target": target["process"].returncode,
                        },
                        "difference": difference,
                    })
                    print(f"{'PASS' if matches else 'FAIL'} {profile['id']}: {case['case_id']}", flush=True)
                except Exception as error:  # Preserve adapter failures in the generated result.
                    outcomes.append({
                        "case_id": case["case_id"],
                        "profile": profile["id"],
                        "operation": case["operation"],
                        "requirements": case["covers"],
                        "status": "infrastructure_failed",
                        "error": {"class": type(error).__name__, "message": str(error)[:1000]},
                    })
                    print(f"ERROR {profile['id']}: {case['case_id']}: {error}", flush=True)
                    for unrun_case in cases[case_index + 1:]:
                        outcomes.append({
                            "case_id": unrun_case["case_id"],
                            "profile": profile["id"],
                            "operation": unrun_case["operation"],
                            "requirements": unrun_case["covers"],
                            "status": "not_run",
                            "reason": f"an earlier {profile['id']} case failed to execute",
                        })
                    break
        finally:
            for server in servers.values():
                exit_code, logs = stop_server(server)
                if logs.strip():
                    print(f"--- {server['id']} server log ---\n{logs}", file=sys.stderr)
                normal_signal_exit = server["id"] == "uvicorn" and exit_code == -signal.SIGTERM
                if (exit_code != 0 and not normal_signal_exit) or "panicked at" in logs:
                    infrastructure_errors.append({
                        "profile": profile["id"],
                        "server": server["id"],
                        "kind": "server_shutdown_failure",
                        "exit_code": exit_code,
                        "diagnostic": logs[-1000:],
                    })
    return outcomes, infrastructure_errors


def validate_result_shape(
    result: dict[str, Any],
    selected_cases: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """Reject incomplete or internally inconsistent evidence before writing it."""

    exact_keys(result, {"schema", "run", "status", "summary", "cases", "infrastructure_errors"}, "result")
    if result["schema"] != RESULT_SCHEMA:
        raise ParityError(f"unsupported result schema: {result['schema']!r}")
    run = result["run"]
    exact_keys(
        run,
        {"run_id", "started_at", "finished_at", "manifest", "inputs", "environment", "target", "harness", "command"},
        "result.run",
    )
    if not isinstance(run["run_id"], str) or not run["run_id"]:
        raise ParityError("result.run.run_id must be non-empty")
    exact_keys(run["manifest"], {"path", "schema", "sha256"}, "result.run.manifest")
    if run["manifest"]["schema"] != manifest["schema"]:
        raise ParityError("result manifest schema differs from the active contract")
    expected_inputs = [str((FIXTURES / path).relative_to(ROOT)) for path in manifest["inputs"]]
    if not isinstance(run["inputs"], list) or [item.get("path") for item in run["inputs"]] != expected_inputs:
        raise ParityError("result input identities do not match the manifest index")
    for item in run["inputs"]:
        exact_keys(item, {"path", "schema", "sha256"}, "result.run.input")
        if item["schema"] != INPUT_SCHEMA:
            raise ParityError(f"result input schema is invalid: {item['schema']!r}")
    exact_keys(run["environment"], {"python", "platform", "machine", "rustc", "dependencies"}, "result.run.environment")
    dependencies = run["environment"]["dependencies"]
    if not isinstance(dependencies, dict):
        raise ParityError("result environment dependencies must be an object")
    for oracle in manifest["oracles"]:
        pinned = [(oracle["id"], oracle["version"])]
        pinned.extend((component["id"], component["version"]) for component in oracle["components"])
        for distribution, version in pinned:
            if dependencies.get(distribution) != version:
                raise ParityError(f"result identity does not match pinned {distribution} version {version}")
    exact_keys(
        run["target"],
        {"revision", "dirty", "native_extension", "cargo_lock_sha256"},
        "result.run.target",
    )
    exact_keys(run["target"]["native_extension"], {"path", "sha256"}, "result.run.target.native_extension")
    if not isinstance(run["target"]["dirty"], bool):
        raise ParityError("result target dirty flag must be boolean")
    exact_keys(
        run["harness"],
        {"runner", "runner_sha256", "fixture_app", "fixture_app_sha256", "http3_client"},
        "result.run.harness",
    )
    if run["harness"]["http3_client"] is not None:
        exact_keys(run["harness"]["http3_client"], {"path", "sha256"}, "result.run.harness.http3_client")
    for value, label in (
        (run["manifest"]["sha256"], "manifest"),
        (run["target"]["native_extension"]["sha256"], "native extension"),
        (run["target"]["cargo_lock_sha256"], "Cargo.lock"),
        (run["harness"]["runner_sha256"], "runner"),
        (run["harness"]["fixture_app_sha256"], "fixture app"),
        *((item["sha256"], "input") for item in run["inputs"]),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ParityError(f"result {label} identity must be a lowercase sha256 digest")
    if run["harness"]["http3_client"] is not None:
        value = run["harness"]["http3_client"]["sha256"]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ParityError("result HTTP/3 client identity must be a lowercase sha256 digest")
    if not isinstance(run["command"], list) or not run["command"] or not all(isinstance(part, str) for part in run["command"]):
        raise ParityError("result command must be a non-empty string array")
    expected = {case["case_id"]: case for case in selected_cases}
    recorded = result["cases"]
    if not isinstance(recorded, list):
        raise ParityError("result.cases must be an array")
    ids = [case.get("case_id") for case in recorded]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ParityError("result case IDs do not exactly match selected input case IDs")
    status_counts = {status: 0 for status in ("passed", "failed", "infrastructure_failed", "not_run")}
    operation_index = {
        operation["id"]: operation
        for operation in manifest["operations"]
    }
    for item in recorded:
        if item.get("status") not in status_counts:
            raise ParityError(f"result case {item.get('case_id')!r} has an invalid status")
        status_counts[item["status"]] += 1
        source_case = expected[item["case_id"]]
        if any(
            item.get(field) != source_case.get(source_field)
            for field, source_field in (
                ("profile", "profile"),
                ("operation", "operation"),
                ("requirements", "covers"),
            )
        ):
            raise ParityError(f"result metadata differs from selected input for {item['case_id']!r}")
        status = item["status"]
        common = {"case_id", "profile", "operation", "requirements", "status"}
        if status in {"passed", "failed"}:
            exact_keys(
                item,
                common | {"oracle_observation", "target_observation", "server_exit_codes", "difference"},
                f"result.cases[{item['case_id']}]",
            )
            observations = operation_index[item["operation"]]["observe"]
            for side in ("oracle_observation", "target_observation"):
                if set(item[side]) != set(observations):
                    raise ParityError(f"{item['case_id']}: {side} fields differ from the operation contract")
            exact_keys(item["server_exit_codes"], {"oracle", "target"}, f"{item['case_id']}.server_exit_codes")
            if status == "passed" and item["difference"] is not None:
                raise ParityError(f"{item['case_id']}: passing case cannot carry a difference")
            if status == "failed" and not isinstance(item["difference"], str):
                raise ParityError(f"{item['case_id']}: failed case must explain the difference")
        elif status == "infrastructure_failed":
            exact_keys(item, common | {"error"}, f"result.cases[{item['case_id']}]")
            exact_keys(item["error"], {"class", "message"}, f"{item['case_id']}.error")
        else:
            exact_keys(item, common | {"reason"}, f"result.cases[{item['case_id']}]")
            if not isinstance(item["reason"], str) or not item["reason"]:
                raise ParityError(f"{item['case_id']}: not-run reason must be non-empty")
    summary = result["summary"]
    exact_keys(summary, {"selected", "executed", "passed", "failed", "not_run", "infrastructure_failed"}, "result.summary")
    expected_counts = {
        "selected": len(selected_cases),
        "executed": len(selected_cases) - status_counts["not_run"],
        "passed": status_counts["passed"],
        "failed": status_counts["failed"],
        "not_run": status_counts["not_run"],
        "infrastructure_failed": status_counts["infrastructure_failed"] + len(result["infrastructure_errors"]),
    }
    if summary != expected_counts:
        raise ParityError(f"result summary does not match case evidence: expected {expected_counts}, found {summary}")
    if not isinstance(result["infrastructure_errors"], list):
        raise ParityError("result.infrastructure_errors must be an array")
    expected_status = "completed" if status_counts["passed"] == len(selected_cases) and not result["infrastructure_errors"] else "failed"
    if result["status"] != expected_status:
        raise ParityError(f"result status does not match case evidence: expected {expected_status!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "asgi-parity" / "result.json")
    args = parser.parse_args()

    manifest, inputs, input_paths = load_contract()
    environment, target_identity = runtime_identity(manifest)
    started = utc_now()
    h3_client = build_h3_client() if any(case["profile"] == "http3" for case in inputs["cases"]) else None
    case_results = []
    infrastructure_errors = []
    profile_map = {profile["id"]: profile for profile in manifest["profiles"]}
    operations = {operation["id"]: operation for operation in manifest["operations"]}
    for profile_id, profile in profile_map.items():
        selected = [case for case in inputs["cases"] if case["profile"] == profile_id]
        if selected:
            profile_results, profile_errors = execute_profile(profile, selected, h3_client, operations)
            case_results.extend(profile_results)
            infrastructure_errors.extend(profile_errors)
    counts = {
        "selected": len(inputs["cases"]),
        "executed": sum(result["status"] != "not_run" for result in case_results),
        "passed": sum(result["status"] == "passed" for result in case_results),
        "failed": sum(result["status"] == "failed" for result in case_results),
        "not_run": sum(result["status"] == "not_run" for result in case_results),
        "infrastructure_failed": sum(result["status"] == "infrastructure_failed" for result in case_results) + len(infrastructure_errors),
    }
    status = "completed" if counts["passed"] == counts["selected"] and counts["infrastructure_failed"] == 0 else "failed"
    result = {
        "schema": RESULT_SCHEMA,
        "run": {
            "run_id": uuid.uuid4().hex,
            "started_at": started,
            "finished_at": utc_now(),
            "manifest": {
                "path": str(MANIFEST_PATH.relative_to(ROOT)),
                "schema": manifest["schema"],
                "sha256": sha256(MANIFEST_PATH),
            },
            "inputs": [
                {
                    "path": str(path.relative_to(ROOT)),
                    "schema": INPUT_SCHEMA,
                    "sha256": sha256(path),
                }
                for path in input_paths
            ],
            "environment": environment,
            "target": target_identity,
            "harness": {
                "runner": str(Path(__file__).resolve().relative_to(ROOT)),
                "runner_sha256": sha256(Path(__file__).resolve()),
                "fixture_app": str((FIXTURES / "app.py").relative_to(ROOT)),
                "fixture_app_sha256": sha256(FIXTURES / "app.py"),
                "http3_client": (
                    {
                        "path": str(h3_client.relative_to(ROOT)),
                        "sha256": sha256(h3_client),
                    }
                    if h3_client is not None
                    else None
                ),
            },
            "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        },
        "status": status,
        "summary": counts,
        "cases": case_results,
        "infrastructure_errors": infrastructure_errors,
    }
    validate_result_shape(result, inputs["cases"], manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "summary": counts, "result": str(args.output)}, indent=2))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ParityError, subprocess.SubprocessError, OSError) as error:
        print(f"parity infrastructure failure: {error}", file=sys.stderr)
        raise SystemExit(2) from error
