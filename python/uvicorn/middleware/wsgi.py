# Copyright (c) 2026 Appunni M
# WSGI adapter behavior is adapted from Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Adapt a WSGI application to the ASGI interface used by the server."""

from __future__ import annotations

import asyncio
import concurrent.futures
import io
import sys
import warnings
from collections import deque
from collections.abc import Iterable
from types import TracebackType
from typing import Any, Callable

_Scope = dict[str, Any]
_Message = dict[str, Any]
_Receive = Callable[[], Any]
_Send = Callable[[_Message], Any]
_Environ = dict[str, Any]
_ExcInfo = tuple[type[BaseException], BaseException, TracebackType]
_StartResponse = Callable[[str, Iterable[tuple[str, str]], _ExcInfo | None], Any]
_WSGIApp = Callable[[_Environ, _StartResponse], Iterable[bytes]]


def build_environ(scope: _Scope, message: _Message, body: io.BytesIO) -> _Environ:
    """Build the WSGI environment from an ASGI scope and request event."""
    script_name = scope.get("root_path", "").encode("utf8").decode("latin1")
    path_info = scope["path"].encode("utf8").decode("latin1")
    path_info = path_info.removeprefix(script_name)
    environ: _Environ = {
        "REQUEST_METHOD": scope["method"],
        "SCRIPT_NAME": script_name,
        "PATH_INFO": path_info,
        "QUERY_STRING": scope["query_string"].decode("ascii"),
        "SERVER_PROTOCOL": f"HTTP/{scope['http_version']}",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": scope.get("scheme", "http"),
        "wsgi.input": body,
        "wsgi.errors": sys.stdout,
        "wsgi.multithread": True,
        "wsgi.multiprocess": True,
        "wsgi.run_once": False,
    }

    server = scope.get("server")
    if server is None:
        server = ("localhost", 80)
    environ["SERVER_NAME"] = server[0]
    environ["SERVER_PORT"] = server[1]

    client = scope.get("client")
    if client is not None:
        environ["REMOTE_ADDR"] = client[0]

    for name, value in scope.get("headers", []):
        name_str = name.decode("latin1")
        if name_str == "content-length":
            corrected_name = "CONTENT_LENGTH"
        elif name_str == "content-type":
            corrected_name = "CONTENT_TYPE"
        else:
            corrected_name = f"HTTP_{name_str.upper().replace('-', '_')}"
        value_str = value.decode("latin1")
        if corrected_name in environ:
            existing_value = environ[corrected_name]
            assert isinstance(existing_value, str)
            value_str = existing_value + "," + value_str
        environ[corrected_name] = value_str
    return environ


class _WSGIMiddleware:
    def __init__(self, app: _WSGIApp, workers: int = 10) -> None:
        warnings.warn(
            "Uvicorn's native WSGI implementation is deprecated, you should switch to a2wsgi (`pip install a2wsgi`).",
            DeprecationWarning,
        )
        self.app = app
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        assert scope["type"] == "http"
        responder = WSGIResponder(self.app, self.executor, scope)
        await responder(receive, send)


class WSGIResponder:
    def __init__(
        self,
        app: _WSGIApp,
        executor: concurrent.futures.ThreadPoolExecutor,
        scope: _Scope,
    ) -> None:
        self.app = app
        self.executor = executor
        self.scope = scope
        self.send_event = asyncio.Event()
        self.send_queue: deque[_Message | None] = deque()
        self.loop = asyncio.get_event_loop()
        self.response_started = False
        self.exc_info: _ExcInfo | None = None

    async def __call__(self, receive: _Receive, send: _Send) -> None:
        message = await receive()
        body = io.BytesIO(message.get("body", b""))
        more_body = message.get("more_body", False)
        if more_body:
            body.seek(0, io.SEEK_END)
            while more_body:
                body_message = await receive()
                body.write(body_message.get("body", b""))
                more_body = body_message.get("more_body", False)
            body.seek(0)

        environ = build_environ(self.scope, message, body)
        wsgi_future = self.loop.run_in_executor(
            self.executor, self.wsgi, environ, self.start_response
        )
        sender = self.loop.create_task(self.sender(send))
        try:
            await asyncio.wait_for(wsgi_future, None)
        finally:
            self.send_queue.append(None)
            self.send_event.set()
            await asyncio.wait_for(sender, None)
        if self.exc_info is not None:
            raise self.exc_info[0].with_traceback(self.exc_info[1], self.exc_info[2])

    async def sender(self, send: _Send) -> None:
        while True:
            if self.send_queue:
                message = self.send_queue.popleft()
                if message is None:
                    return
                await send(message)
            else:
                await self.send_event.wait()
                self.send_event.clear()

    def start_response(
        self,
        status: str,
        response_headers: Iterable[tuple[str, str]],
        exc_info: _ExcInfo | None = None,
    ) -> None:
        self.exc_info = exc_info
        if not self.response_started:
            self.response_started = True
            status_code_str, _ = status.split(" ", 1)
            status_code = int(status_code_str)
            headers = [
                (name.encode("ascii"), value.encode("ascii"))
                for name, value in response_headers
            ]
            self.send_queue.append(
                {"type": "http.response.start", "status": status_code, "headers": headers}
            )
            self.loop.call_soon_threadsafe(self.send_event.set)

    def wsgi(self, environ: _Environ, start_response: _StartResponse) -> None:
        for chunk in self.app(environ, start_response):
            self.send_queue.append(
                {"type": "http.response.body", "body": chunk, "more_body": True}
            )
            self.loop.call_soon_threadsafe(self.send_event.set)
        self.send_queue.append(
            {"type": "http.response.body", "body": b"", "more_body": False}
        )
        self.loop.call_soon_threadsafe(self.send_event.set)


class WSGILifespanAdapter:
    """Match Uvicorn's auto-mode fallback for WSGI applications."""

    def __init__(self, app: Any, lifespan: str) -> None:
        self.app = app
        self.lifespan = lifespan

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope["type"] == "lifespan" and self.lifespan == "auto":
            return
        await self.app(scope, receive, send)


try:
    from a2wsgi import WSGIMiddleware
except ModuleNotFoundError:
    WSGIMiddleware = _WSGIMiddleware
