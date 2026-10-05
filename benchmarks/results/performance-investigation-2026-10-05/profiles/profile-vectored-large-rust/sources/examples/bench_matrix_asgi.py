"""ASGI workloads shared by the category benchmark clients."""

from __future__ import annotations

import contextvars


_cached_bodies: dict[int, bytes] = {}
_benchmark_context = contextvars.ContextVar("benchmark_context", default="unset")


def _body(size: int) -> bytes:
    value = _cached_bodies.get(size)
    if value is None:
        value = b"x" * size
        _cached_bodies[size] = value
    return value


async def _receive_request(receive) -> int | None:
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        size += len(message.get("body", b""))
        if not message.get("more_body", False):
            return size


async def _http(scope, receive, send) -> None:
    path = scope["path"].split("?")[0]

    if path == "/protocol":
        await receive()
        body = f"http_version={scope['http_version']}".encode("ascii")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    if path.startswith("/upload/"):
        size = await _receive_request(receive)
        if size is None:
            return
        body = f"bytes={size}".encode("ascii")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    await receive()

    if path == "/fixed":
        body = b"Hello World!"
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", b"12")],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    if path.startswith("/large/"):
        size = int(path.rsplit("/", 1)[1])
        body = _body(size)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", str(size).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    if path.startswith("/chunks/"):
        _, _, count_text, chunk_text = path.split("/")
        count = int(count_text)
        chunk_size = int(chunk_text)
        chunk = _body(chunk_size)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for index in range(count):
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": index + 1 < count,
                }
            )
        return

    if path == "/scope":
        headers = dict(scope["headers"])
        valid = all(headers.get(f"x-bench-{index}".encode()) == b"value" for index in range(32))
        body = b"scope-ok" if valid else b"scope-invalid"
        status = 200 if valid else 400
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    if path == "/context":
        token = _benchmark_context.set("request-context")
        body = _benchmark_context.get().encode("ascii")
        _benchmark_context.reset(token)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", str(len(body)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
        return

    if path == "/exception":
        raise RuntimeError("benchmark exception path")

    body = b"not found"
    await send({"type": "http.response.start", "status": 404, "headers": []})
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def _websocket(scope, receive, send) -> None:
    message = await receive()
    if message["type"] == "websocket.disconnect":
        return
    await send({"type": "websocket.accept", "subprotocol": "bench"})
    while True:
        message = await receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") is not None:
            await send({"type": "websocket.send", "bytes": message["bytes"]})
        elif message.get("text") is not None:
            await send({"type": "websocket.send", "text": message["text"]})


async def _lifespan(receive, send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def app(scope, receive, send):
    if scope["type"] == "http":
        await _http(scope, receive, send)
    elif scope["type"] == "websocket":
        await _websocket(scope, receive, send)
    elif scope["type"] == "lifespan":
        await _lifespan(receive, send)
