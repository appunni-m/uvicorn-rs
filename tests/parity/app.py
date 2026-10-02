"""Deterministic ASGI service shared by parity source and target processes."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path


_disconnect_seen = False


def _record(event: str) -> None:
    path = os.environ.get("ASGI_PARITY_EVENTS")
    if path:
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")


async def _respond(send, body: bytes, *, status: int = 200, content_type: bytes = b"application/octet-stream") -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type)],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


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
    global _disconnect_seen

    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                scope["state"]["parity-token"] = "ready"
                _record("lifespan.startup")
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                _record("lifespan.shutdown")
                await send({"type": "lifespan.shutdown.complete"})
                return
        return

    if scope["type"] == "websocket":
        await receive()
        if scope["path"] == "/ws-deny":
            await send({"type": "websocket.close", "code": 1008, "reason": "denied"})
            return
        offered = scope.get("subprotocols", [])
        protocol = "parity" if "parity" in offered else None
        await send({"type": "websocket.accept", "subprotocol": protocol})
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

    if path in {"/stream", "/stream-progress"}:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"first/", "more_body": True})
        if path == "/stream-progress":
            _record("response.first.sent")
            await asyncio.sleep(0.1)
        for chunk in (b"second/", b"last"):
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        if path == "/stream-progress":
            _record("response.finished")
        return

    if path == "/raise":
        raise RuntimeError("parity exception sentinel")

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

    if path == "/disconnect-watch":
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                _disconnect_seen = True
                _record("http.disconnect")
                return

    if path == "/disconnect-status":
        body = b"seen" if _disconnect_seen else b"missing"
        await _respond(send, body, content_type=b"text/plain; charset=utf-8")
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

    return _app_impl(scope, receive, send)
