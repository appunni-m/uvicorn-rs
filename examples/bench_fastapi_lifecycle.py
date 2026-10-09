"""FastAPI lifecycle workload shared by the maintained server benchmarks."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import sys
from typing import AsyncIterator

from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.benchmark_state = {
        "token": "startup-token",
        "nested": {"count": 0},
    }
    try:
        yield
    finally:
        print("LIFESPAN_SHUTDOWN_COMPLETE", file=sys.stderr, flush=True)


app = FastAPI(lifespan=lifespan)


@app.get("/state")
async def state(request: Request) -> PlainTextResponse:
    """Confirm startup state, then mutate state as the existing probe does."""
    state = request.app.state.benchmark_state
    observed = f"{state['token']}:{state['nested']['count']}"
    state["token"] = "request-token"
    state["nested"]["count"] += 1
    return PlainTextResponse(observed)


@app.get("/hold")
async def hold() -> None:
    """Hold one request until graceful shutdown cancels its ASGI task."""
    print("APP_HOLD_STARTED", file=sys.stderr, flush=True)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        print("APP_CANCELLED_BY_SHUTDOWN", file=sys.stderr, flush=True)
        raise
