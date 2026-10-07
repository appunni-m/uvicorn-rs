"""Shared black-box integration app for Starlette and starlette-rs.

The HTTP application uses APIs available in both packages. WebSocket handling
uses a small plain ASGI endpoint because starlette-rs has not implemented
Starlette's WebSocketRoute API at the pinned revision used by this project.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route


def _write_marker(environment_key: str, value: str, *, append: bool = False) -> None:
    destination = os.environ.get(environment_key)
    if destination is None:
        raise RuntimeError(f"missing {environment_key}")
    with Path(destination).open("a" if append else "w", encoding="utf-8") as marker:
        marker.write(value + "\n")


@asynccontextmanager
async def lifespan(_app):
    _write_marker("UVICORN_RS_LIFESPAN_MARKER", "startup", append=True)
    try:
        yield {"token": "integration-lifespan-token"}
    finally:
        _write_marker("UVICORN_RS_LIFESPAN_MARKER", "shutdown", append=True)


async def state(request: Request) -> PlainTextResponse:
    return PlainTextResponse("state:" + request.state.token)


async def stream(_request: Request) -> StreamingResponse:
    async def content():
        for part in (b"alpha", b"beta", b"gamma"):
            yield part
            await asyncio.sleep(0.02)

    return StreamingResponse(content(), media_type="application/octet-stream")


async def upload(request: Request) -> PlainTextResponse:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
    return PlainTextResponse("upload:" + body.decode("ascii"))


def _background_marker() -> None:
    _write_marker("UVICORN_RS_BACKGROUND_MARKER", "complete")


async def background(_request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        "background:accepted",
        background=BackgroundTask(_background_marker),
    )


async def application_error(_request: Request) -> PlainTextResponse:
    raise RuntimeError("intentional starlette integration error")


_starlette_app = Starlette(
    routes=[
        Route("/state", state),
        Route("/stream", stream),
        Route("/upload", upload, methods=["POST"]),
        Route("/background", background),
        Route("/error", application_error),
    ],
    lifespan=lifespan,
)


async def _websocket(scope, receive, send) -> None:
    message = await receive()
    if message["type"] != "websocket.connect":
        return
    await send({"type": "websocket.accept", "subprotocol": "integration"})
    while True:
        message = await receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("text") is not None:
            await send({"type": "websocket.send", "text": "echo:" + message["text"]})
        elif message.get("bytes") is not None:
            await send({"type": "websocket.send", "bytes": b"echo:" + message["bytes"]})


async def app(scope, receive, send) -> None:
    if scope["type"] == "websocket":
        await _websocket(scope, receive, send)
    else:
        await _starlette_app(scope, receive, send)
