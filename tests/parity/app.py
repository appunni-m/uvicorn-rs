"""Deterministic ASGI service shared by parity source and target processes."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from urllib.parse import parse_qs


_disconnect_seen = False
_disconnect_sequence = []
_retained_lifespan_send = None
_concurrent_arrivals = 0
_concurrent_barrier = None
_load_groups = {}
_task_cleanup_tasks = []
_state_copy_key = None
_state_copy_source = None
_state_copy_shared = None


def _header_capacity_headers(query_string):
    """Build a finite, input-selected list of distinct valid ASGI headers."""
    parameter, separator, value = query_string.partition(b"=")
    if parameter != b"count" or not separator or not value.isdigit():
        raise ValueError("header-capacity fixture requires a decimal count")
    count = int(value)
    if not 1 <= count <= 32769:
        raise ValueError("header-capacity fixture count is outside its bounded range")
    return [(f"x-capacity-{index:x}".encode("ascii"), b"x") for index in range(count)]


def _scope_address(scope, key):
    address = scope.get(key)
    if address is None:
        return None
    host, port = address
    return [host, "<port>" if port is not None else None]


def _scope_headers(scope, *, excluded=frozenset()):
    headers = []
    http_version = scope.get("http_version")
    http2_or_3_cookie_values = []
    for name, value in scope.get("headers", []):
        lowered_name = name.lower()
        if lowered_name in excluded:
            continue
        if lowered_name == b"cookie" and http_version in {"2", "3"}:
            # ASGI permits HTTP/2 and HTTP/3 Cookie fields either split or
            # joined with the cookie delimiter. Compare their ordered value
            # bytes after applying that permitted representation change.
            http2_or_3_cookie_values.append(value)
            continue
        # Normalize listener-selected ports while retaining authority presence.
        if lowered_name == b"host" and b":" in value:
            host, separator, port = value.rpartition(b":")
            if separator and port.isdigit():
                value = host + b":<port>"
        headers.append(
            [base64.b64encode(name).decode("ascii"), base64.b64encode(value).decode("ascii")]
        )
    if http2_or_3_cookie_values:
        headers.append([
            base64.b64encode(b"cookie").decode("ascii"),
            base64.b64encode(b"; ".join(http2_or_3_cookie_values)).decode("ascii"),
        ])
    # Header-name order is not significant, but same-name values retain order.
    return sorted(headers, key=lambda header: header[0])


class _StateCopyKey(str):
    """Detect rehashing of a key while a server copies lifespan state."""

    def __new__(cls, value, source):
        key = str.__new__(cls, value)
        key.source = source
        key.armed = False
        key.hash_calls = 0
        return key

    def __hash__(self):
        self.hash_calls += 1
        if self.armed:
            self.source["copy-source-mutated"] = True
        return str.__hash__(self)


class _ASGIEventType(str):
    """Exercise the ASGI string-subclass path used by the Python bridge."""


def _record(event: str) -> None:
    path = os.environ.get("ASGI_PARITY_EVENTS")
    if path:
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")


def _load_parameters(scope, kind):
    query = parse_qs(scope.get("query_string", b"").decode("ascii"))
    key = query.get("key", [""])[0]
    count = query.get("count", [""])[0]
    if not key or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in key):
        raise ValueError("load fixture requires a safe key")
    if not count.isdigit() or not 2 <= int(count) <= 64:
        raise ValueError("load fixture count must be between 2 and 64")
    parameters = {"key": key, "count": int(count)}
    if kind == "http":
        chunks = query.get("chunks", [""])[0]
        chunk_bytes = query.get("chunk_bytes", [""])[0]
        if not chunks.isdigit() or not 16 <= int(chunks) <= 64:
            raise ValueError("HTTP load fixture chunk count must be between 16 and 64")
        if not chunk_bytes.isdigit() or not 1024 <= int(chunk_bytes) <= 4096:
            raise ValueError("HTTP load fixture chunk size must be between 1024 and 4096")
        parameters.update({"chunks": int(chunks), "chunk_bytes": int(chunk_bytes)})
    elif kind == "websocket":
        messages = query.get("messages", [""])[0]
        message_bytes = query.get("message_bytes", [""])[0]
        if not messages.isdigit() or not 1 <= int(messages) <= 32:
            raise ValueError("WebSocket load fixture message count must be between 1 and 32")
        if not message_bytes.isdigit() or not 1 <= int(message_bytes) <= 4096:
            raise ValueError("WebSocket load fixture message size must be between 1 and 4096")
        parameters.update({"messages": int(messages), "message_bytes": int(message_bytes)})
    return parameters


def _load_enter(scope, kind):
    parameters = _load_parameters(scope, kind)
    identity = (kind, parameters["key"])
    state = _load_groups.get(identity)
    if state is None:
        state = {
            "expected": parameters["count"],
            "arrived": 0,
            "active": 0,
            "peak_active": 0,
            "peak_python_tasks": 0,
            "barrier": asyncio.Event(),
        }
        _load_groups[identity] = state
    elif state["expected"] != parameters["count"]:
        raise ValueError("load fixture count changed while the barrier was active")
    state["arrived"] += 1
    state["active"] += 1
    state["peak_active"] = max(state["peak_active"], state["active"])
    state["peak_python_tasks"] = max(state["peak_python_tasks"], len(asyncio.all_tasks()))
    if state["arrived"] >= state["expected"]:
        state["barrier"].set()
    return parameters, state, identity


def _load_exit(state):
    state["active"] -= 1


def _load_snapshot(kind, key):
    identity = (kind, key)
    state = _load_groups.get(identity)
    if state is None:
        return None
    result = {
        "arrived": state["arrived"],
        "active": state["active"],
        "expected": state["expected"],
        "peak_active": state["peak_active"],
        "peak_python_tasks": state["peak_python_tasks"],
        "idle_python_tasks": len(asyncio.all_tasks()),
    }
    if state["active"] == 0:
        _load_groups.pop(identity, None)
    return result


async def _respond(
    send,
    body: bytes,
    *,
    status: int = 200,
    content_type: bytes = b"application/octet-stream",
    event_type=str,
) -> None:
    await send(
        {
            "type": event_type("http.response.start"),
            "status": status,
            "headers": [(b"content-type", content_type)],
        }
    )
    await send({"type": event_type("http.response.body"), "body": body, "more_body": False})


async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _app_impl(scope, receive, send):
    global _disconnect_seen, _disconnect_sequence, _retained_lifespan_send
    global _concurrent_arrivals, _concurrent_barrier
    global _state_copy_key, _state_copy_source, _state_copy_shared

    if scope["type"] == "lifespan":
        lifespan_mode = os.environ.get("ASGI_PARITY_LIFESPAN_MODE", "complete")
        if lifespan_mode == "receive-wrong-signature":
            await receive(None)
        if lifespan_mode == "shutdown-cancel-pending":
            startup = await receive()
            if startup["type"] != "lifespan.startup":
                return
            scope["state"]["parity-token"] = "ready"
            _record("lifespan.startup")
            await send({"type": "lifespan.startup.complete"})
            try:
                shutdown = await receive()
                if shutdown["type"] == "lifespan.shutdown":
                    _record("lifespan.shutdown")
                    _record("lifespan.shutdown.hold")
                    await asyncio.Event().wait()
                    await send({"type": "lifespan.shutdown.complete"})
            except asyncio.CancelledError:
                _record("lifespan.task-cancelled")
                raise
            return
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                if lifespan_mode == "unsupported":
                    return
                if lifespan_mode == "startup-return-retains-send":
                    # Keep the Rust LifespanIo sender alive after the ASGI
                    # callable returns. This distinguishes app-task
                    # completion from event-channel closure in LifespanRuntime.
                    _retained_lifespan_send = send
                    _record("lifespan.app-returned-before-startup-event")
                    return
                if lifespan_mode == "unsupported-error-retains-send":
                    # Keep the send channel alive after the app fails. An ASGI
                    # application can retain the callable beyond its return.
                    _retained_lifespan_send = send
                    raise RuntimeError("parity lifespan unsupported sentinel")
                if lifespan_mode == "unsupported-error":
                    raise RuntimeError("parity lifespan unsupported sentinel")
                invalid_startup_events = {
                    "invalid-startup-event": {"type": "http.response.start"},
                    "missing-startup-event-type": {},
                    "non-string-startup-event-type": {"type": 42},
                }
                if lifespan_mode in invalid_startup_events:
                    await send(invalid_startup_events[lifespan_mode])
                    return
                if lifespan_mode in {
                    "startup-failed", "startup-failed-empty", "startup-failed-subclass"
                }:
                    _record("lifespan.startup.failed")
                    failure_type = (
                        _ASGIEventType("lifespan.startup.failed")
                        if lifespan_mode == "startup-failed-subclass"
                        else "lifespan.startup.failed"
                    )
                    failure = {"type": failure_type}
                    if lifespan_mode == "startup-failed":
                        failure["message"] = "parity startup failure"
                    elif lifespan_mode == "startup-failed-subclass":
                        failure["message"] = "parity startup subclass failure"
                    await send(failure)
                    return
                if lifespan_mode == "startup-complete-then-return":
                    scope["state"]["parity-token"] = "ready"
                    _record("lifespan.startup")
                    await send({"type": "lifespan.startup.complete"})
                    _record("lifespan.app-returned-after-startup")
                    return
                if lifespan_mode == "subclass-event-types":
                    scope["state"]["parity-token"] = "ready"
                    _record("lifespan.startup")
                    await send({"type": _ASGIEventType("lifespan.startup.complete")})
                    continue
                if lifespan_mode == "unexpected-startup-event":
                    _record("lifespan.unexpected-startup-event")
                    await send({"type": "lifespan.shutdown.complete"})
                    return
                scope["state"]["parity-token"] = "ready"
                if lifespan_mode == "state-copy-rehash":
                    _state_copy_source = scope["state"]
                    _state_copy_shared = {"value": "shared"}
                    _state_copy_key = _StateCopyKey("copy-key", _state_copy_source)
                    _state_copy_source[_state_copy_key] = _state_copy_shared
                _record("lifespan.startup")
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if lifespan_mode in {
                    "shutdown-failed", "shutdown-failed-empty", "shutdown-failed-subclass"
                }:
                    _record("lifespan.shutdown.failed")
                    failure_type = (
                        _ASGIEventType("lifespan.shutdown.failed")
                        if lifespan_mode == "shutdown-failed-subclass"
                        else "lifespan.shutdown.failed"
                    )
                    failure = {"type": failure_type}
                    if lifespan_mode == "shutdown-failed":
                        failure["message"] = "parity shutdown failure"
                    elif lifespan_mode == "shutdown-failed-subclass":
                        failure["message"] = "parity shutdown subclass failure"
                    await send(failure)
                    return
                if lifespan_mode == "shutdown-returns":
                    _record("lifespan.shutdown-returned-without-event")
                    return
                if lifespan_mode == "shutdown-returns-retains-send":
                    _retained_lifespan_send = send
                    _record("lifespan.shutdown-returned-without-event")
                    return
                if lifespan_mode == "shutdown-raises":
                    _record("lifespan.shutdown-raised")
                    raise RuntimeError("parity lifespan shutdown exception sentinel")
                if lifespan_mode == "shutdown-unexpected-event":
                    _record("lifespan.shutdown-unexpected-event")
                    await send({"type": "lifespan.startup.complete"})
                    return
                _record("lifespan.shutdown")
                shutdown_type = (
                    _ASGIEventType("lifespan.shutdown.complete")
                    if lifespan_mode == "subclass-event-types"
                    else "lifespan.shutdown.complete"
                )
                await send({"type": shutdown_type})
                if lifespan_mode == "shutdown-complete-then-raises":
                    _record("lifespan.shutdown-raised-after-complete")
                    raise RuntimeError("parity exception after shutdown.complete sentinel")
                if lifespan_mode == "shutdown-complete-pending":
                    try:
                        await asyncio.Future()
                    finally:
                        _record("lifespan.task-cancelled-after-complete")
                return
        return

    if scope["type"] == "websocket":
        if os.environ.get("ASGI_PARITY_TRACE_WEBSOCKET_SCOPE") == "1":
            _record(f"websocket.scope:{scope['path']}")
        if scope["path"].startswith("/ws-scope-echo/"):
            await receive()
            offered = scope.get("subprotocols", [])
            observed = {
                "type": scope["type"],
                "asgi_version": scope.get("asgi", {}).get("version"),
                "http_version": scope.get("http_version"),
                "scheme": scope.get("scheme"),
                "path": scope.get("path"),
                "raw_path_base64": (
                    base64.b64encode(scope["raw_path"]).decode("ascii")
                    if scope.get("raw_path") is not None
                    else None
                ),
                "query_string_base64": base64.b64encode(
                    scope.get("query_string", b"") or b""
                ).decode("ascii"),
                "root_path": scope.get("root_path", ""),
                "headers_base64": _scope_headers(
                    scope, excluded={b"sec-websocket-key"}
                ),
                "client": _scope_address(scope, "client"),
                "server": _scope_address(scope, "server"),
                "subprotocols": offered,
                "state": scope.get("state", {}),
            }
            if scope["path"] == "/ws-scope-echo/asgi-version":
                observed["asgi_spec_version"] = scope.get("asgi", {}).get("spec_version")
            await send({
                "type": "websocket.accept",
                "subprotocol": "parity" if "parity" in offered else None,
            })
            await send({
                "type": "websocket.send",
                "text": json.dumps(observed, separators=(",", ":")),
            })
            await send({"type": "websocket.close", "code": 1000, "reason": "scope complete"})
            return
        if scope["path"] == "/ws-header-capacity":
            try:
                await send({
                    "type": "websocket.accept",
                    "headers": _header_capacity_headers(scope["query_string"]),
                })
                _record("websocket.header-capacity.accept-sent")
                await receive()
            finally:
                _record("websocket.header-capacity.cleanup-completed")
            return
        await receive()
        if scope["path"] in {
            "/ws-wrong-context-http-response-start",
            "/ws-wrong-context-http-response-body",
        }:
            event_type = (
                "http.response.start"
                if scope["path"].endswith("start")
                else "http.response.body"
            )
            await send({"type": event_type})
            return
        if scope["path"] == "/ws-receive-wrong-signature":
            await send({"type": "websocket.accept"})
            await receive(None)
            return
        if scope["path"] in {"/ws-upgrade-client-drop", "/ws-upgrade-server-shutdown"}:
            _record("websocket.upgrade.waiting")
            await asyncio.sleep(0.2)
            await send({"type": "websocket.accept"})
            _record("websocket.upgrade.accepted")
            await receive()
            return
        if scope["path"] == "/ws-deny":
            await send({"type": "websocket.close", "code": 1008, "reason": "denied"})
            return
        if scope["path"] == "/ws-deny-default":
            await send({"type": "websocket.close"})
            return
        if scope["path"] == "/ws-missing-event-type":
            await send({"text": "missing event type"})
            return
        if scope["path"] == "/ws-unknown-event-type":
            await send({"type": "websocket.ping"})
            return
        if scope["path"] == "/ws-return-before-handshake":
            return
        if scope["path"] == "/ws-raise-before-handshake":
            raise RuntimeError("WebSocket pre-handshake sentinel")
        if scope["path"] == "/ws-send-before-accept":
            await send({"type": "websocket.send", "text": "too early"})
            return
        if scope["path"] == "/ws-raise-after-accept":
            await send({"type": "websocket.accept"})
            raise RuntimeError("WebSocket post-accept sentinel")
        if scope["path"] == "/ws-send-after-client-disconnect":
            await send({"type": "websocket.accept"})
            message = await receive()
            if message["type"] == "websocket.disconnect":
                _record(f"websocket.disconnect:{message.get('code')}:{message.get('reason', '')}")
                await send({"type": "websocket.send", "text": "too late"})
            return
        if scope["path"] == "/ws-read-after-client-disconnect":
            await send({"type": "websocket.accept"})
            message = await receive()
            if message["type"] == "websocket.disconnect":
                second_message = await receive()
                _record(f"websocket.disconnect.second:{second_message['type']}")
            return
        if scope["path"] == "/ws-abrupt-disconnect":
            await send({"type": "websocket.accept"})
            message = await receive()
            if message["type"] == "websocket.disconnect":
                _record("websocket.disconnected-abrupt")
            return
        if scope["path"] == "/ws-wait-for-disconnect":
            await send({"type": "websocket.accept"})
            message = await receive()
            if message["type"] == "websocket.disconnect":
                _record(f"websocket.disconnect:{message['code']}:{message['reason']}")
            return
        if scope["path"] == "/ws-custom-accept-header":
            offered = scope.get("subprotocols", [])
            await send({
                "type": "websocket.accept",
                "subprotocol": "parity" if "parity" in offered else None,
                "headers": [(b"x-asgi-parity", b"accepted")],
            })
            await receive()
            return
        if scope["path"] == "/ws-invalid-accept-header-value":
            await send({"type": "websocket.accept", "headers": [(b"x-parity", b"invalid\nvalue")]})
            return
        if scope["path"] == "/ws-reserved-accept-header":
            await send({"type": "websocket.accept", "headers": [(b"sec-websocket-accept", b"invalid")]})
            return
        if scope["path"] == "/ws-invalid-subprotocol-value":
            await send({"type": "websocket.accept", "subprotocol": "invalid\nprotocol"})
            return
        if scope["path"] == "/ws-invalid-accept-header":
            await send({
                "type": "websocket.accept",
                "headers": [(b"invalid header name", b"value")],
            })
            return
        if scope["path"] == "/ws-invalid-accept-headers-container":
            await send({"type": "websocket.accept", "headers": 42})
            return
        if scope["path"] == "/ws-invalid-subprotocol-type":
            await send({"type": "websocket.accept", "subprotocol": 42})
            return
        if scope["path"] == "/ws-invalid-close-code-type":
            await send({"type": "websocket.close", "code": "1000"})
            return
        if scope["path"] == "/ws-close-default-after-accept":
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.close"})
            await receive()
            return
        if scope["path"] == "/ws-close-twice":
            await send({"type": "websocket.accept"})
            await send({"type": "websocket.close", "code": 1000})
            await send({"type": "websocket.close", "code": 1001})
            return
        if scope["path"] == "/ws/load":
            parameters, state, _identity = _load_enter(scope, "websocket")
            try:
                await state["barrier"].wait()
                await send({"type": "websocket.accept"})
                for _ in range(parameters["messages"]):
                    message = await receive()
                    if message["type"] == "websocket.disconnect":
                        return
                    if message["type"] != "websocket.receive":
                        raise RuntimeError("WebSocket load fixture received an unexpected event")
                    if "text" in message:
                        await send({"type": "websocket.send", "text": message["text"]})
                    else:
                        await send({"type": "websocket.send", "bytes": message["bytes"]})
                await send({"type": "websocket.close", "code": 1000})
            finally:
                _load_exit(state)
            return
        if scope["path"] == "/ws-client-close":
            await send({"type": "websocket.accept"})
            message = await receive()
            if message["type"] == "websocket.disconnect":
                _record(f"websocket.disconnect:{message.get('code')}:{message.get('reason', '')}")
            return
        if scope["path"] == "/ws-hold":
            await send({"type": "websocket.accept"})
            _record("websocket.hold")
            message = await receive()
            if message["type"] == "websocket.disconnect":
                _record(f"websocket.disconnect:{message.get('code')}:{message.get('reason', '')}")
            return
        if scope["path"] == "/ws-hold-on-shutdown":
            await send({"type": "websocket.accept"})
            _record("websocket.hold")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                _record("websocket.app-cancelled")
                raise
            return
        offered = scope.get("subprotocols", [])
        protocol = "parity" if "parity" in offered else None
        accept_type = (
            _ASGIEventType("websocket.accept")
            if scope["path"] == "/ws-send-subclass-events"
            else "websocket.accept"
        )
        await send({"type": accept_type, "subprotocol": protocol})
        if scope["path"] == "/ws-outbound-queue-closed":
            try:
                await send({"type": "websocket.send", "text": "queue fault"})
            except OSError:
                _record("websocket.outgoing.queue-closed")
                raise
            return
        if scope["path"] == "/ws-duplicate-accept":
            await send({"type": "websocket.accept"})
            return
        if scope["path"] == "/ws-invalid-send-payload":
            await send({"type": "websocket.send"})
            return
        if scope["path"] == "/ws-invalid-send-both-payloads":
            await send({"type": "websocket.send", "text": "text", "bytes": b"bytes"})
            return
        if scope["path"] == "/ws-server-finish":
            await send({"type": "websocket.send", "text": "server finished"})
            await asyncio.sleep(0.05)
            return
        if scope["path"] == "/ws-send-and-return":
            await send({"type": "websocket.send", "text": "queued final frame"})
            return
        if scope["path"] == "/ws-send-and-hold":
            await send({"type": "websocket.send", "text": "send before hold"})
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                _record("websocket.app-cancelled-after-send-error")
                raise
        if scope["path"] == "/ws-send-subclass-events":
            await send({"type": _ASGIEventType("websocket.send"), "text": "subclass"})
            await send({"type": _ASGIEventType("websocket.close"), "code": 1000, "reason": "subclass"})
            await receive()
            return
        if scope["path"] == "/ws-outbound-burst":
            for index in range(32):
                await send({"type": "websocket.send", "text": f"burst-{index:02}"})
            await send({"type": "websocket.close", "code": 1000, "reason": "burst complete"})
            await receive()
            return
        if scope["path"] == "/ws-close-after-message":
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            await send({"type": "websocket.send", "text": "closing"})
            await send({"type": "websocket.close", "code": 1001, "reason": "server draining"})
            await receive()
            return
        while True:
            message = await receive()
            if message["type"] == "websocket.disconnect":
                return
            if message.get("text") is not None:
                await send({"type": "websocket.send", "text": message["text"]})
            else:
                await send({"type": "websocket.send", "bytes": message.get("bytes", b"")})

    if scope["type"] != "http":
        raise RuntimeError(f"unsupported ASGI scope type: {scope['type']}")

    path = scope["path"]
    if path == "/response-headers-order":
        await send({
            "type": "http.response.start",
            "status": 201,
            "headers": [
                (b"x-asgi-order", b"first"),
                (b"x-asgi-duplicate", b"second"),
                (b"x-asgi-order", b"last"),
                (b"x-asgi-duplicate", b"first"),
                (b"content-type", b"text/plain"),
            ],
        })
        await send({"type": "http.response.body", "body": b"ordered-headers"})
        return
    if path.startswith("/scope-echo/"):
        observed = {
            "type": scope["type"],
            "asgi_version": scope.get("asgi", {}).get("version"),
            "method": scope["method"],
            "scheme": scope["scheme"],
            "http_version": scope["http_version"],
            "path": scope["path"],
            "raw_path_base64": base64.b64encode(scope["raw_path"]).decode("ascii"),
            "query_string_base64": base64.b64encode(scope["query_string"]).decode("ascii"),
            "root_path": scope.get("root_path", ""),
            "headers_base64": _scope_headers(scope),
            "client": _scope_address(scope, "client"),
            "server": _scope_address(scope, "server"),
            "state": scope.get("state", {}),
        }
        if path == "/scope-echo/asgi-version":
            observed["asgi_spec_version"] = scope.get("asgi", {}).get("spec_version")
        await _respond(send, json.dumps(observed, separators=(",", ":")).encode(), content_type=b"application/json")
        return

    if path == "/response-header-capacity":
        try:
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": _header_capacity_headers(scope["query_string"]),
            })
        except RuntimeError as error:
            _record(f"http.header-capacity.error:{type(error).__name__}:{error}")
            await _respond(send, b"header capacity rejected", status=500)
            _record("http.header-capacity.recovered")
            return
        await send({"type": "http.response.body", "body": b"headers accepted"})
        return

    if path == "/scope":
        body = b"" if scope["method"] == "GET" else await _read_body(receive)
        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        observed = {
            "http_version": scope["http_version"],
            "method": scope["method"],
            "scheme": scope["scheme"],
            "path": path,
            "query_string_base64": base64.b64encode(scope["query_string"]).decode("ascii"),
            "x-parity": headers.get(b"x-parity", b"").decode("latin-1"),
            "body_base64": base64.b64encode(body).decode("ascii"),
        }
        await _respond(send, json.dumps(observed, separators=(",", ":")).encode(), content_type=b"application/json")
        return

    if path == "/event-type-subclass":
        await _respond(
            send,
            b"string-subclass",
            content_type=b"text/plain; charset=utf-8",
            event_type=_ASGIEventType,
        )
        return

    if path == "/invalid-asgi/missing-type":
        await send({"status": 200})
        return

    if path == "/invalid-asgi/unknown-type":
        await send({"type": "http.response.trailers"})
        return

    if path == "/final-body-before-app-return":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for data, more_body in [(b"first/", True), (b"second/", True), (b"last", False)]:
            await send({"type": "http.response.body", "body": data, "more_body": more_body})
        _record("response.final.sent")
        await asyncio.sleep(0.25)
        _record("response.final.app-returned")
        return

    if path.startswith("/concurrent-request/"):
        if _concurrent_barrier is None:
            _concurrent_barrier = asyncio.Event()
        _concurrent_arrivals += 1
        if _concurrent_arrivals == 2:
            _concurrent_barrier.set()
        await _concurrent_barrier.wait()
        await _respond(send, path.encode(), content_type=b"text/plain; charset=utf-8")
        return

    if path == "/load/fan-in":
        parameters, state, _identity = _load_enter(scope, "http")
        try:
            await state["barrier"].wait()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/octet-stream")],
                }
            )
            for index in range(parameters["chunks"]):
                chunk = bytes([index % 256]) * parameters["chunk_bytes"]
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            _load_exit(state)
        return

    if path == "/load/status":
        query = parse_qs(scope.get("query_string", b"").decode("ascii"))
        key = query.get("key", [""])[0]
        kind = query.get("kind", [""])[0]
        if kind not in {"http", "websocket"}:
            await _respond(send, b"invalid load kind", status=400, content_type=b"text/plain")
            return
        snapshot = _load_snapshot(kind, key)
        if snapshot is None:
            await _respond(send, b"load group not found", status=404, content_type=b"text/plain")
            return
        await _respond(
            send,
            json.dumps(snapshot, sort_keys=True).encode("ascii"),
            content_type=b"application/json",
        )
        return

    if path == "/return-before-response-start":
        return

    if path == "/h3-early-response-open-upload":
        await _respond(
            send,
            b"response-before-upload-complete",
            content_type=b"text/plain; charset=utf-8",
        )
        return

    if path == "/invalid-asgi/non-string-type":
        await send({"type": 42})
        return

    wrong_context_events = {
        "websocket-accept": "websocket.accept",
        "websocket-close": "websocket.close",
        "websocket-send": "websocket.send",
        "lifespan-startup-complete": "lifespan.startup.complete",
        "lifespan-startup-failed": "lifespan.startup.failed",
        "lifespan-shutdown-complete": "lifespan.shutdown.complete",
        "lifespan-shutdown-failed": "lifespan.shutdown.failed",
    }
    if path.startswith("/invalid-asgi/wrong-context/"):
        event_name = path.rsplit("/", 1)[-1]
        await send({"type": wrong_context_events[event_name]})
        return

    if path == "/invalid-asgi/invalid-status":
        await send({"type": "http.response.start", "status": 99, "headers": []})
        return

    if path == "/invalid-asgi/status-not-integer":
        await send({"type": "http.response.start", "status": "200", "headers": []})
        return

    if path == "/invalid-asgi/headers-not-iterable":
        await send({"type": "http.response.start", "status": 200, "headers": 42})
        return

    if path == "/invalid-asgi/duplicate-start":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.start", "status": 201, "headers": []})
        return

    if path == "/invalid-asgi/start-then-raise":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("parity response-start exception sentinel")

    if path == "/invalid-asgi/incomplete-response-body":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"incomplete/", "more_body": True})
        return

    if path == "/invalid-asgi/body-not-bytes":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": "not-bytes", "more_body": False})
        return

    if path == "/invalid-asgi/final-body-then-raise":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"final/", "more_body": False})
        raise RuntimeError("parity final-body exception sentinel")

    if path == "/invalid-asgi/missing-status":
        await send({"type": "http.response.start", "headers": []})
        return

    if path == "/invalid-asgi/body-before-start":
        await send({"type": "http.response.body", "body": b"before-start"})
        return

    if path == "/response-empty-body-field":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body"})
        return

    if path == "/no-content":
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return

    if path == "/invalid-asgi/header-name":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"invalid header name", b"value")],
            }
        )
        await send({"type": "http.response.body", "body": b"invalid"})
        return

    if path == "/invalid-asgi/header-value":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-invalid", b"value\r\ninjected: yes")],
            }
        )
        await send({"type": "http.response.body", "body": b"invalid"})
        return

    if path == "/response-burst":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/octet-stream")],
            }
        )
        for index in range(64):
            await send({"type": "http.response.body", "body": bytes([index]) * 1024, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return

    if path == "/response-burst-large":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/octet-stream")],
            }
        )
        for index in range(256):
            await send({"type": "http.response.body", "body": bytes([index]) * 4096, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return

    if path == "/ignore-upload":
        await _respond(send, b"upload-ignored", content_type=b"text/plain; charset=utf-8")
        _record("http.body-pump.app-response-finished")
        return

    if path == "/read-first-upload":
        # Consume exactly one ASGI request event, then stop reading. The body
        # returned by the server may combine wire chunks differently, so the
        # observation is deliberately independent of the chunk boundary.
        await receive()
        await _respond(
            send,
            b"read-once",
            content_type=b"application/octet-stream",
        )
        return

    if path == "/upload-pump-disconnect":
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                _record("http.disconnect")
                return

    if path == "/concurrent-upload-receive":
        first_receive = asyncio.create_task(receive())
        # The client withholds the upload until the checkpoint below. Give
        # the first receive bridge time to acquire the Rust request mutex so
        # the second concurrent receive exercises the try_lock fallback.
        await asyncio.sleep(0.02)
        second_receive = asyncio.create_task(receive())
        await asyncio.sleep(0.02)
        _record("http.receive.concurrently-waiting")
        messages = await asyncio.gather(first_receive, second_receive)
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.request"
        )
        await _respond(send, body, content_type=b"application/octet-stream")
        return

    if path == "/concurrent-upload-receive-completion":
        first_receive = asyncio.create_task(receive())
        await asyncio.sleep(0)
        second_receive = asyncio.create_task(receive())
        await asyncio.sleep(0.02)
        _record("http.receive.concurrently-waiting")
        await asyncio.gather(first_receive, second_receive)
        await _respond(send, b"concurrent-receives-completed", content_type=b"text/plain; charset=utf-8")
        return

    if path == "/h3-upload-disconnect":
        _record("http3.upload.started")
        received_body = False
        while True:
            receive_task = asyncio.ensure_future(receive())
            if received_body:
                await asyncio.sleep(0)
                _record("http3.upload.waiting-after-body")
            message = await receive_task
            if message["type"] == "http.disconnect":
                _record("http3.upload.disconnected")
                return
            _record("http3.upload.body")
            _record(
                f"http3.upload.body.more:{message.get('more_body')}:{len(message.get('body', b''))}"
            )
            if not message.get("more_body", False):
                _record("http3.upload.body.complete")
                break
            received_body = True
        await _respond(send, b"upload-disconnect-observed", content_type=b"text/plain; charset=utf-8")
        return

    if path == "/stream-yield-after-start":
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        # Give the server a scheduling turn to begin polling the response body
        # before the final ASGI body event is queued.
        await asyncio.sleep(0)
        await send(
            {
                "type": "http.response.body",
                "body": b"yielded-after-start",
                "more_body": False,
            }
        )
        return

    if path in {"/stream-pending-then-complete", "/stream-pending-burst-then-complete"}:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        # Leave the body channel empty long enough for the transport to poll
        # it once before the ASGI task queues its only (final) body frame.
        await asyncio.sleep(0.02)
        if path == "/stream-pending-burst-then-complete":
            await send({"type": "http.response.body", "body": b"queued-", "more_body": True})
            await send({"type": "http.response.body", "body": b"after-pending", "more_body": False})
            return
        await send(
            {
                "type": "http.response.body",
                "body": b"queued-after-pending",
                "more_body": False,
            }
        )
        return

    if path in {"/stream", "/stream-progress", "/stream-progress-hold"}:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"first/", "more_body": True})
        if path in {"/stream-progress", "/stream-progress-hold"}:
            _record("response.first.sent")
            if path == "/stream-progress-hold":
                _record("response.reset.hold")
                release_path = Path(os.environ["ASGI_PARITY_STREAM_RELEASE"])
                deadline = asyncio.get_running_loop().time() + 5
                while (
                    not release_path.exists()
                    and asyncio.get_running_loop().time() < deadline
                ):
                    await asyncio.sleep(0.005)
            else:
                await asyncio.sleep(0.1)
        for chunk in (b"second/", b"last"):
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        if path == "/stream-progress-hold":
            _record("response.reset.finished")
        elif path == "/stream-progress":
            _record("response.finished")
        return

    if path in {"/stream-shutdown-hold", "/stream-shutdown-reset-large"}:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"first/", "more_body": True})
        _record("response.shutdown.hold")
        release_path = Path(os.environ["ASGI_PARITY_STREAM_RELEASE"])
        try:
            deadline = asyncio.get_running_loop().time() + 5
            while not release_path.exists() and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.005)
        except asyncio.CancelledError:
            _record("response.shutdown.cancelled")
            raise
        if path == "/stream-shutdown-reset-large":
            chunk = b"x" * (256 * 1024)
            for _ in range(32):
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        else:
            for chunk in (b"second/", b"last"):
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        _record("response.shutdown.finished")
        return

    if path == "/stream-cancel-until-reset":
        # Let the Rust-side PythonTaskFuture observe the newly scheduled
        # asyncio.Task before this reset probe starts its response. Without
        # this scheduling point the client can reset on the first body chunk
        # before the task handle has been transferred to the Rust future.
        await asyncio.sleep(0.05)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"first/", "more_body": True})
        _record("response.reset.hold")
        try:
            await asyncio.Event().wait()
        finally:
            _record("response.reset.app-cancelled")
        return

    if path == "/raise":
        raise RuntimeError("parity exception sentinel")

    if path == "/receive-wrong-signature":
        await receive(None)
        return

    if path == "/complete-before-task-panic":
        await _respond(
            send,
            b"complete-before-task-panic",
            content_type=b"text/plain; charset=utf-8",
        )
        # Let the HTTP body driver consume the final frame before the coverage
        # build injects a panic as the Python task reports its completion.
        await asyncio.sleep(0.1)
        return

    if path == "/state-copy-arm":
        _state_copy_key.armed = True
        _state_copy_key.hash_calls = 0
        await _respond(send, b"armed", content_type=b"text/plain; charset=utf-8")
        return

    if path == "/state-copy-observe":
        request_state = scope["state"]
        request_state["copy-local-only"] = True
        # Plain string lookups do not invoke the stored subclass key's hash.
        # Observe the copy's namespace and shallow value ownership publicly.
        observed = {
            "source_mutated": "copy-source-mutated" in _state_copy_source,
            "rehash_calls": _state_copy_key.hash_calls,
            "separate_namespace": request_state is not _state_copy_source,
            "shared_value": request_state.get("copy-key") is _state_copy_shared,
            "local_write_changed_source": "copy-local-only" in _state_copy_source,
        }
        await _respond(
            send,
            json.dumps(observed, sort_keys=True, separators=(",", ":")).encode(),
            content_type=b"application/json",
        )
        return

    if path == "/state":
        token = scope.get("state", {}).get("parity-token", "missing")
        await _respond(send, token.encode(), content_type=b"text/plain; charset=utf-8")
        return

    if path == "/upload-stream":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if chunk:
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            if not message.get("more_body", False):
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

    if path == "/disconnect-send-body":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        _record("http.disconnect.body.waiting")
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                _disconnect_seen = True
                _record("http.disconnect")
                try:
                    await send({"type": "http.response.body", "body": b"late", "more_body": False})
                except OSError:
                    _record("http.disconnect.body-send-error")
                return

    if path in {
        "/disconnect-watch",
        "/disconnect-send",
        "/disconnect-read-once",
        "/disconnect-read-twice",
        "/disconnect-read-thrice",
    }:
        if path in {"/disconnect-read-once", "/disconnect-read-twice", "/disconnect-read-thrice"}:
            _record("http.disconnect.waiting")
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                _disconnect_seen = True
                _record("http.disconnect")
                if path == "/disconnect-read-twice":
                    second_message = await receive()
                    _record(f"http.disconnect.second:{second_message['type']}")
                if path == "/disconnect-read-thrice":
                    try:
                        second_message = await receive()
                    except MemoryError:
                        _record("http.disconnect.repeat-error:MemoryError")
                        return
                    _record(f"http.disconnect.second:{second_message['type']}")
                    third_message = await receive()
                    _record(f"http.disconnect.third:{third_message['type']}")
                if path == "/disconnect-send":
                    try:
                        await send({"type": "http.response.start", "status": 200, "headers": []})
                    except OSError:
                        _record("http.disconnect.send-error")
                return

    if path == "/disconnect-after-complete-request":
        message = await receive()
        if message["type"] != "http.request" or message.get("more_body", False):
            raise AssertionError("empty request did not produce its final ASGI request event")
        _record("http.disconnect.waiting-after-complete-request")
        message = await receive()
        _record(f"http.disconnect.after-complete-request:{message['type']}")
        if message["type"] == "http.disconnect":
            _disconnect_seen = True
        return

    if path == "/disconnect-after-complete-upload":
        _record("http.disconnect.waiting-before-complete-upload")
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                _disconnect_seen = True
                _record("http.disconnect.before-complete-upload:" + message["type"])
                return
            if not message.get("more_body", False):
                _record("http.disconnect.waiting-after-complete-upload")
                message = await receive()
                _record("http.disconnect.after-complete-upload:" + message["type"])
                if message["type"] == "http.disconnect":
                    _disconnect_seen = True
                    _record("http.disconnect")
                return

    if path == "/disconnect-after-close-before-receive":
        _record("http.disconnect.before-first-receive")
        # The synchronized client closes while no receive future is pending.
        # Waiting here lets the connection-close signal reach the Rust side
        # before the app asks for its first request event.
        await asyncio.sleep(0.05)
        message = await receive()
        _disconnect_sequence = [message["type"]]
        _record(f"http.disconnect.first:{message['type']}")
        while message["type"] == "http.request":
            message = await receive()
            _disconnect_sequence.append(message["type"])
        if message["type"] == "http.disconnect":
            _disconnect_seen = True
            _record("http.disconnect")
        return

    if path == "/disconnect-status":
        body = b"seen" if _disconnect_seen else b"missing"
        await _respond(send, body, content_type=b"text/plain; charset=utf-8")
        return

    if path == "/disconnect-after-close-status":
        body = ",".join(_disconnect_sequence or ["missing"]).encode()
        await _respond(send, body, content_type=b"text/plain; charset=utf-8")
        return

    if path in {"/task-cleanup-hold", "/task-cleanup-suppress-cancel"}:
        # Register through the fixture and public asyncio Task API. A failed
        # callback registration can schedule this app before reporting an
        # error; the following request must detect any task it leaves live.
        _task_cleanup_tasks.append(asyncio.current_task())
        _record("application.task-cleanup.hold")
        try:
            if scope["query_string"] == b"complete-response=1":
                await _respond(send, b"held")
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if path == "/task-cleanup-suppress-cancel":
                _record("application.task-cleanup.cancel-suppressed")
                return
            _record("application.task-cleanup.cancelled")
            raise
        finally:
            _record("application.task-cleanup.finished")
        return

    if path == "/task-cleanup-status":
        # Give previously scheduled application tasks an owning-loop turn to
        # register before observing them. Before-start cancellation correctly
        # leaves no fixture task to observe.
        await asyncio.sleep(0)
        pending = sum(not task.done() for task in _task_cleanup_tasks)
        body = json.dumps(
            {"pending_application_tasks": pending}, separators=(",", ":")
        ).encode()
        await _respond(send, body, content_type=b"application/json")
        return

    if path == "/task-cleanup-cancel":
        pending = [task for task in _task_cleanup_tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        body = json.dumps(
            {"cancelled_application_tasks": len(pending)}, separators=(",", ":")
        ).encode()
        await _respond(send, body, content_type=b"application/json")
        return

    if path == "/post-response-hold":
        try:
            await _respond(send, b"complete")
            _record("response.background.hold")
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            _record("response.background.cancelled")
            raise
        finally:
            _record("response.background.cleanup-completed")
        return

    if path == "/hold":
        _record("request.hold")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            _record("request.cancelled")
            raise

    if path == "/not-found":
        await _respond(send, b"not found", status=404, content_type=b"text/plain; charset=utf-8")
        return

    if path == "/sync-callable":
        await _respond(send, b"sync-callable-awaitable", content_type=b"text/plain; charset=utf-8")
        return

    await _respond(send, b"ok", content_type=b"text/plain; charset=utf-8")


def app(scope, receive, send):
    """Synchronous ASGI callable that returns the coroutine doing the work."""

    if scope["type"] == "http" and scope["path"] == "/sync-callable-raises":
        raise RuntimeError("parity synchronous HTTP callable sentinel")
    if scope["type"] == "websocket" and scope["path"] == "/ws-sync-callable-raises":
        raise RuntimeError("parity synchronous WebSocket callable sentinel")
    return _app_impl(scope, receive, send)
