"""Internal callable aliases used by the Uvicorn compatibility facade."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, Union


ASGIScope = dict[str, Any]
ASGIReceiveCallable = Callable[[], Awaitable[dict[str, Any]]]
ASGISendCallable = Callable[[dict[str, Any]], Awaitable[None]]


class ASGI2Protocol(Protocol):
    def __init__(self, scope: ASGIScope) -> None: ...

    async def __call__(
        self, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None: ...


ASGI2Application = type[ASGI2Protocol]
ASGI3Application = Callable[
    [ASGIScope, ASGIReceiveCallable, ASGISendCallable], Awaitable[None]
]
ASGIApplication = Union[ASGI2Application, ASGI3Application]
