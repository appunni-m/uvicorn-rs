"""FastAPI workloads for comparing identical Python framework code on ASGI servers."""

from functools import lru_cache
from contextvars import ContextVar
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Query, Request, WebSocket
from pydantic import BaseModel
from starlette.responses import PlainTextResponse, Response, StreamingResponse


app = FastAPI()
REQUEST_CONTEXT: ContextVar[str] = ContextVar("fastapi_benchmark_context", default="missing")


class ItemResponse(BaseModel):
    item_id: int
    name: str
    active: bool
    labels: list[str]


class CpuResponse(BaseModel):
    iterations: int
    checksum: int


@lru_cache(maxsize=8)
def _body(size: int) -> bytes:
    return b"x" * size


async def _body_chunks(count: int, size: int) -> AsyncIterator[bytes]:
    chunk = _body(size)
    for _ in range(count):
        yield chunk


@app.get("/fixed")
async def fixed_response() -> PlainTextResponse:
    """Measure the smallest ordinary FastAPI request and response path."""
    return PlainTextResponse("Hello World!")


@app.get("/protocol")
async def protocol_scope(request: Request) -> PlainTextResponse:
    """Expose the negotiated protocol version through the FastAPI request scope."""
    return PlainTextResponse(f"http_version={request.scope['http_version']}")


@app.api_route("/protocol-consumed", methods=["GET", "POST"])
async def protocol_consumed(request: Request) -> PlainTextResponse:
    """Consume a request body and report its size with the negotiated protocol."""
    body = await request.body()
    return PlainTextResponse(
        f"http_version={request.scope['http_version']};bytes={len(body)}"
    )


@app.get("/large/{size}")
async def large_response(size: int) -> Response:
    """Send one cached immutable body to isolate large response transport."""
    return Response(_body(size), media_type="application/octet-stream")


@app.get("/chunks/{count}/{size}")
async def chunked_response(count: int, size: int) -> StreamingResponse:
    """Stream fixed-size chunks through FastAPI's normal response machinery."""
    return StreamingResponse(
        _body_chunks(count, size), media_type="application/octet-stream"
    )


@app.post("/upload/{expected_size}")
async def request_upload(expected_size: int, request: Request) -> PlainTextResponse:
    """Consume the complete request body using FastAPI's Request interface."""
    body = await request.body()
    return PlainTextResponse(f"bytes={len(body)}")


@app.get("/scope")
async def scope_headers(request: Request) -> PlainTextResponse:
    """Exercise a wider HTTP scope while checking all supplied benchmark headers."""
    present = {name for name, _ in request.scope["headers"]}
    expected = {f"x-bench-{index}".encode() for index in range(32)}
    return PlainTextResponse("scope-ok" if expected <= present else "scope-error")


async def _request_context() -> AsyncIterator[str]:
    token = REQUEST_CONTEXT.set("request-context")
    try:
        yield REQUEST_CONTEXT.get()
    finally:
        REQUEST_CONTEXT.reset(token)


@app.get("/context")
async def contextvars_response(
    value: str = Depends(_request_context),
) -> PlainTextResponse:
    """Exercise a request-scoped async dependency and ContextVar propagation."""
    return PlainTextResponse(value)


@app.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int, repeat: int = Query(default=1, ge=1, le=5)
) -> ItemResponse:
    """Exercise route matching, parameter validation, and response serialization."""
    return ItemResponse(
        item_id=item_id * repeat,
        name=f"item-{item_id}",
        active=True,
        labels=["python", "asgi"],
    )


@app.get("/cpu/{iterations}", response_model=CpuResponse)
def python_cpu(iterations: int) -> CpuResponse:
    """Exercise a deterministic Python-heavy sync route and response validation."""
    checksum = 0
    for index in range(iterations):
        checksum = (checksum + (index * 17) % 251) % 1_000_003
    return CpuResponse(iterations=iterations, checksum=checksum)


@app.websocket("/echo")
async def websocket_echo(websocket: WebSocket) -> None:
    """Accept and echo the same text and binary frames on both server stacks."""
    await websocket.accept(subprotocol="bench")
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") is not None:
            await websocket.send_bytes(message["bytes"])
        elif message.get("text") is not None:
            await websocket.send_text(message["text"])
