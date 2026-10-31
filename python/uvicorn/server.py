# Copyright (c) 2026 Appunni M
# Public constructor shape follows Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Uvicorn-compatible programmatic server facade over the Rust engine."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import os
import random
import signal
import socket
import sys
import threading
import time
import warnings
from collections.abc import Awaitable, Callable, Generator
from email.utils import formatdate
from functools import cached_property
from types import FrameType
from typing import Any

from ._shutdown_trace import write_shutdown_trace
from .config import Config

HANDLED_SIGNALS = (signal.SIGINT, signal.SIGTERM)
if sys.platform == "win32":  # pragma: no cover - Windows-specific signal
    HANDLED_SIGNALS += (signal.SIGBREAK,)

logger = logging.getLogger("uvicorn.error")


def _ensure_windows_sockets_listening(
    sockets: list[socket.socket], backlog: int
) -> None:
    """Listen on bound Windows sockets once, before they are shared by workers."""
    if os.name != "nt":
        return
    for sock in sockets:
        if not sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
            sock.listen(backlog)


class ServerState:
    """Compatibility state container retained for Uvicorn integrations."""

    def __init__(self) -> None:
        self.total_requests = 0
        self.connections: set[Any] = set()
        self.tasks: set[asyncio.Task[None]] = set()
        self.default_headers: list[tuple[bytes, bytes]] = []
        self.app_state: dict[str, Any] = {}


def _track_server_state(app: Any, state: ServerState) -> Any:
    """Mirror request-task and completed-response state at the ASGI boundary."""

    async def tracked_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            async def tracked_lifespan_send(message: dict[str, Any]) -> None:
                if message.get("type") == "lifespan.startup.complete":
                    app_state = scope.get("state")
                    if isinstance(app_state, dict):
                        state.app_state = app_state
                await send(message)

            await app(scope, receive, tracked_lifespan_send)
            return
        if scope_type not in {"http", "websocket"}:
            await app(scope, receive, send)
            return

        task = asyncio.current_task()
        if task is not None:
            state.tasks.add(task)
        response_completed = False
        response_status: int | None = None

        async def tracked_send(message: dict[str, Any]) -> None:
            nonlocal response_completed, response_status
            final_http_body = (
                scope_type == "http"
                and not response_completed
                and message.get("type") == "http.response.body"
                and not message.get("more_body", False)
            )
            response_without_body = (
                scope.get("method") == "HEAD" or response_status in {204, 304}
            )
            if final_http_body and response_without_body:
                # The native HTTP stack may complete bodyless responses while
                # the ASGI app is still sending its required final body event.
                response_completed = True
                state.total_requests += 1
            await send(message)
            if final_http_body and not response_completed:
                response_completed = True
                state.total_requests += 1
            if scope_type == "http" and message.get("type") == "http.response.start":
                response_status = message.get("status")

        try:
            await app(scope, receive, tracked_send)
        finally:
            if task is not None:
                state.tasks.discard(task)

    return tracked_app


def _socket_address_key(address: Any) -> tuple[Any, Any] | None:
    if not isinstance(address, tuple) or len(address) < 2:
        return None
    return address[0], address[1]


class _TLSContextProxy:
    """Terminate a user SSLContext and forward plaintext HTTP to Rust."""

    def __init__(self, context: Any, backlog: int, uds: str | None) -> None:
        self.context = context
        self.backlog = max(0, backlog)
        self.uds = uds
        self.backend_socket: socket.socket | None = None
        self.backend_address: tuple[str, int] | None = None
        self.servers: list[asyncio.Server] = []
        self.tasks: set[asyncio.Task[Any]] = set()
        self.writers: set[asyncio.StreamWriter] = set()
        self.scope_metadata: dict[
            tuple[Any, Any], tuple[Any, Any]
        ] = {}

    async def bind(
        self,
        host: str,
        port: int,
        sockets: list[socket.socket] | None,
    ) -> None:
        backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        backend.bind(("127.0.0.1", 0))
        backend.listen(self.backlog)
        backend.setblocking(False)
        self.backend_socket = backend
        self.backend_address = backend.getsockname()[:2]

        if sockets is not None:
            for sock in sockets:
                self.servers.append(
                    await asyncio.start_server(
                        self._accept,
                        sock=sock,
                        ssl=self.context,
                        backlog=self.backlog,
                        start_serving=False,
                    )
                )
        elif self.uds is not None:
            self.servers.append(
                await asyncio.start_unix_server(
                    self._accept,
                    path=self.uds,
                    ssl=self.context,
                    backlog=self.backlog,
                    start_serving=False,
                )
            )
        else:
            self.servers.append(
                await asyncio.start_server(
                    self._accept,
                    host=host,
                    port=port,
                    ssl=self.context,
                    backlog=self.backlog,
                    start_serving=False,
                )
            )

    def _accept(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.create_task(self._relay(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        backend_writer: asyncio.StreamWriter | None = None
        backend_key: tuple[Any, Any] | None = None
        self.writers.add(client_writer)
        try:
            if self.backend_address is None:
                return
            backend_reader, backend_writer = await asyncio.open_connection(
                *self.backend_address
            )
            self.writers.add(backend_writer)
            backend_key = _socket_address_key(
                backend_writer.get_extra_info("sockname")
            )
            if backend_key is not None:
                if self.uds is not None:
                    client_address = None
                    server_address = (self.uds, None)
                else:
                    client_address = client_writer.get_extra_info("peername")
                    server_address = client_writer.get_extra_info("sockname")
                self.scope_metadata[backend_key] = (
                    client_address,
                    server_address,
                )

            async def copy_stream(
                reader: asyncio.StreamReader,
                writer: asyncio.StreamWriter,
            ) -> None:
                try:
                    while data := await reader.read(64 * 1024):
                        writer.write(data)
                        await writer.drain()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
                if writer.can_write_eof():
                    with contextlib.suppress(OSError):
                        writer.write_eof()
                else:
                    writer.close()

            await asyncio.gather(
                copy_stream(client_reader, backend_writer),
                copy_stream(backend_reader, client_writer),
            )
        except (ConnectionError, OSError):
            pass
        finally:
            if backend_key is not None:
                self.scope_metadata.pop(backend_key, None)
            client_writer.close()
            if backend_writer is not None:
                backend_writer.close()
                self.writers.discard(backend_writer)
                with contextlib.suppress(BaseException):
                    await backend_writer.wait_closed()
            self.writers.discard(client_writer)
            with contextlib.suppress(BaseException):
                await client_writer.wait_closed()

    async def start_serving(self) -> None:
        for server in self.servers:
            await server.start_serving()

    def close_accepting(self) -> None:
        for server in self.servers:
            server.close()

    async def close(self) -> None:
        self.close_accepting()
        for writer in tuple(self.writers):
            writer.close()
        current = asyncio.current_task()
        tasks = [task for task in self.tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for server in self.servers:
            with contextlib.suppress(BaseException):
                await server.wait_closed()
        self.servers.clear()
        self.writers.clear()
        self.scope_metadata.clear()
        if self.backend_socket is not None:
            self.backend_socket.close()
            self.backend_socket = None

    def wrap_app(self, app: Any) -> Any:
        async def rewrite_scope(
            scope: dict[str, Any], receive: Any, send: Any
        ) -> None:
            if scope.get("type") in {"http", "websocket"}:
                backend_key = _socket_address_key(scope.get("client"))
                metadata = (
                    self.scope_metadata.get(backend_key)
                    if backend_key is not None
                    else None
                )
                if metadata is not None:
                    scope = dict(scope)
                    scope["scheme"] = "https"
                    scope["client"], scope["server"] = metadata
            await app(scope, receive, send)

        return rewrite_scope


class _CustomWebSocketProtocolProxy:
    """Keep native HTTP while handing WebSocket upgrades to Python extensions."""

    _MAX_PEEK_BYTES = 64 * 1024

    def __init__(
        self,
        config: Config,
        server_state: ServerState,
        ssl_context: Any,
    ) -> None:
        self.config = config
        self.server_state = server_state
        self.protocol_class = config.ws_protocol_class
        self.ssl_context = ssl_context
        self.backlog = max(0, config.backlog)
        self.uds = config.uds
        self.backend_socket: socket.socket | None = None
        self.backend_address: tuple[str, int] | None = None
        self.servers: list[asyncio.Server] = []
        self.connections: set[_CustomWebSocketDispatchProtocol] = set()
        self.websocket_protocols: set[Any] = set()
        self.websocket_connections: dict[Any, _CustomWebSocketDispatchProtocol] = {}
        self.tasks: set[asyncio.Task[Any]] = set()
        self.scope_metadata: dict[tuple[Any, Any], tuple[Any, Any]] = {}

    async def bind(
        self,
        host: str,
        port: int,
        sockets: list[socket.socket] | None,
    ) -> None:
        backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend.bind(("127.0.0.1", 0))
        backend.listen(self.backlog)
        backend.setblocking(False)
        self.backend_socket = backend
        self.backend_address = backend.getsockname()[:2]

        loop = asyncio.get_running_loop()
        factory = lambda: _CustomWebSocketDispatchProtocol(self)
        if sockets is not None:
            for sock in sockets:
                self.servers.append(
                    await loop.create_server(
                        factory,
                        sock=sock,
                        ssl=self.ssl_context,
                        backlog=self.backlog,
                        start_serving=False,
                    )
                )
        elif self.uds is not None:
            uds_perms = os.stat(self.uds).st_mode if os.path.exists(self.uds) else 0o666
            server = await loop.create_unix_server(
                factory,
                path=self.uds,
                ssl=self.ssl_context,
                backlog=self.backlog,
                start_serving=False,
            )
            os.chmod(self.uds, uds_perms)
            self.servers.append(server)
        else:
            self.servers.append(
                await loop.create_server(
                    factory,
                    host=host,
                    port=port,
                    ssl=self.ssl_context,
                    backlog=self.backlog,
                    start_serving=False,
                )
            )

    def _connect_backend(self, connection: _CustomWebSocketDispatchProtocol) -> None:
        if connection.connect_task is not None or connection.backend_transport is not None:
            return
        if self.backend_address is None:
            if connection.transport is not None:
                connection.transport.close()
            return
        task = asyncio.create_task(connection._open_backend(self.backend_address))
        connection.connect_task = task
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def register_backend(
        self,
        connection: _CustomWebSocketDispatchProtocol,
        transport: asyncio.Transport,
    ) -> None:
        key = _socket_address_key(transport.get_extra_info("sockname"))
        if key is None:
            return
        if self.uds is not None:
            client_address = None
            server_address = (self.uds, None)
        else:
            client_address = (
                connection.transport.get_extra_info("peername")
                if connection.transport is not None
                else None
            )
            server_address = (
                connection.transport.get_extra_info("sockname")
                if connection.transport is not None
                else None
            )
        self.scope_metadata[key] = (
            client_address,
            server_address,
        )
        connection.metadata_key = key

    def unregister(self, connection: _CustomWebSocketDispatchProtocol) -> None:
        self.connections.discard(connection)
        self.server_state.connections.discard(connection)
        if connection.metadata_key is not None:
            self.scope_metadata.pop(connection.metadata_key, None)
            connection.metadata_key = None

    async def start_serving(self) -> None:
        for server in self.servers:
            await server.start_serving()

    def close_accepting(self) -> None:
        for server in self.servers:
            server.close()

    def shutdown_websockets(self) -> None:
        for protocol in tuple(self.websocket_protocols):
            shutdown = getattr(protocol, "shutdown", None)
            if callable(shutdown):
                with contextlib.suppress(BaseException):
                    shutdown()

    async def wait_for_websockets(self) -> None:
        while self.websocket_protocols:
            await asyncio.sleep(0.05)

    def close_websockets(self) -> None:
        for connection in tuple(self.websocket_connections.values()):
            if connection.transport is not None:
                connection.transport.close()

    async def close(self) -> None:
        self.close_accepting()
        self.shutdown_websockets()
        for connection in tuple(self.connections):
            if connection.transport is not None:
                connection.transport.close()
            if connection.backend_transport is not None:
                connection.backend_transport.close()
        current = asyncio.current_task()
        tasks = [task for task in self.tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for server in self.servers:
            with contextlib.suppress(BaseException):
                await server.wait_closed()
        self.servers.clear()
        self.connections.clear()
        self.websocket_protocols.clear()
        self.websocket_connections.clear()
        self.scope_metadata.clear()
        if self.backend_socket is not None:
            self.backend_socket.close()
            self.backend_socket = None

    def close_now(self) -> None:
        self.close_accepting()
        self.shutdown_websockets()
        for connection in tuple(self.connections):
            if connection.transport is not None:
                connection.transport.close()
            if connection.backend_transport is not None:
                connection.backend_transport.close()
        for task in tuple(self.tasks):
            task.cancel()
        self.connections.clear()
        self.websocket_protocols.clear()
        self.websocket_connections.clear()
        self.scope_metadata.clear()
        if self.backend_socket is not None:
            self.backend_socket.close()
            self.backend_socket = None

    def wrap_app(self, app: Any) -> Any:
        async def rewrite_scope(
            scope: dict[str, Any], receive: Any, send: Any
        ) -> None:
            if scope.get("type") in {"http", "websocket"}:
                backend_key = _socket_address_key(scope.get("client"))
                metadata = (
                    self.scope_metadata.get(backend_key)
                    if backend_key is not None
                    else None
                )
                if metadata is not None:
                    scope = dict(scope)
                    scope["scheme"] = "https" if self.ssl_context is not None else "http"
                    scope["client"], scope["server"] = metadata
            await app(scope, receive, send)

        return rewrite_scope


class _CustomWebSocketDispatchProtocol(asyncio.Protocol):
    def __init__(self, proxy: _CustomWebSocketProtocolProxy) -> None:
        self.proxy = proxy
        self.transport: asyncio.Transport | None = None
        self.backend_transport: asyncio.Transport | None = None
        self.connect_task: asyncio.Task[Any] | None = None
        self.buffer = bytearray()
        self.metadata_key: tuple[Any, Any] | None = None
        self.handed_off = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self.proxy.connections.add(self)
        self.proxy.server_state.connections.add(self)

    def data_received(self, data: bytes) -> None:
        if self.backend_transport is not None:
            self.backend_transport.write(data)
            return
        self.buffer.extend(data)
        if self.proxy.protocol_class is not None:
            header_end = self.buffer.find(b"\r\n\r\n")
            if header_end >= 0:
                upgrade = _custom_websocket_request(bytes(self.buffer))
                if upgrade is not None:
                    request, trailing = upgrade
                    self.buffer.clear()
                    self._handoff_to_websocket(request, trailing)
                    return
                self.proxy._connect_backend(self)
                return
            if len(self.buffer) <= self.proxy._MAX_PEEK_BYTES:
                return
        self.proxy._connect_backend(self)

    def _handoff_to_websocket(self, request: bytes, trailing: bytes) -> None:
        transport = self.transport
        if transport is None:
            return
        protocol = self.proxy.protocol_class(
            config=self.proxy.config,
            server_state=self.proxy.server_state,
            app_state=self.proxy.server_state.app_state,
        )
        self.handed_off = True
        self.proxy.server_state.connections.discard(self)
        self.proxy.websocket_protocols.add(protocol)
        self.proxy.websocket_connections[protocol] = self
        adapter = _CustomWebSocketProtocolAdapter(self.proxy, self, protocol)
        try:
            protocol.connection_made(transport)
            transport.set_protocol(adapter)
            protocol.data_received(request)
            if trailing:
                protocol.data_received(trailing)
        except BaseException:
            self.proxy.websocket_protocols.discard(protocol)
            self.proxy.server_state.connections.discard(protocol)
            transport.close()

    async def _open_backend(self, address: tuple[str, int]) -> None:
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_connection(
                lambda: _CustomWebSocketBackendProtocol(self),
                host=address[0],
                port=address[1],
            )
        except (ConnectionError, OSError):
            if self.transport is not None:
                self.transport.close()
            return
        self.backend_transport = transport
        self.proxy.register_backend(self, transport)
        if self.buffer:
            transport.write(bytes(self.buffer))
            self.buffer.clear()

    def eof_received(self) -> bool | None:
        backend = self.backend_transport
        if backend is not None and backend.can_write_eof():
            with contextlib.suppress(OSError):
                backend.write_eof()
            return True
        if backend is not None:
            backend.close()
        return None

    def pause_writing(self) -> None:
        if self.backend_transport is not None:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                self.backend_transport.pause_reading()

    def resume_writing(self) -> None:
        if self.backend_transport is not None:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                self.backend_transport.resume_reading()

    def connection_lost(self, exc: Exception | None) -> None:
        self.proxy.unregister(self)
        if self.backend_transport is not None:
            self.backend_transport.close()
            self.backend_transport = None
        self.transport = None


class _CustomWebSocketBackendProtocol(asyncio.Protocol):
    def __init__(self, client: _CustomWebSocketDispatchProtocol) -> None:
        self.client = client
        self.transport: asyncio.Transport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def data_received(self, data: bytes) -> None:
        if self.client.transport is not None:
            self.client.transport.write(data)

    def eof_received(self) -> bool | None:
        client = self.client.transport
        if client is not None and client.can_write_eof():
            with contextlib.suppress(OSError):
                client.write_eof()
            return True
        if client is not None:
            client.close()
        return None

    def pause_writing(self) -> None:
        if self.client.transport is not None:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                self.client.transport.pause_reading()

    def resume_writing(self) -> None:
        if self.client.transport is not None:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                self.client.transport.resume_reading()

    def connection_lost(self, exc: Exception | None) -> None:
        if self.client.metadata_key is not None:
            self.client.proxy.scope_metadata.pop(self.client.metadata_key, None)
            self.client.metadata_key = None
        if self.client.transport is not None:
            self.client.transport.close()


class _CustomWebSocketProtocolAdapter(asyncio.Protocol):
    def __init__(
        self,
        proxy: _CustomWebSocketProtocolProxy,
        connection: _CustomWebSocketDispatchProtocol,
        protocol: asyncio.Protocol,
    ) -> None:
        self.proxy = proxy
        self.connection = connection
        self.protocol = protocol

    def data_received(self, data: bytes) -> None:
        self.protocol.data_received(data)

    def eof_received(self) -> bool | None:
        eof_received = getattr(self.protocol, "eof_received", None)
        return eof_received() if callable(eof_received) else None

    def pause_writing(self) -> None:
        callback = getattr(self.protocol, "pause_writing", None)
        if callable(callback):
            callback()

    def resume_writing(self) -> None:
        callback = getattr(self.protocol, "resume_writing", None)
        if callable(callback):
            callback()

    def connection_lost(self, exc: Exception | None) -> None:
        callback = getattr(self.protocol, "connection_lost", None)
        if callable(callback):
            callback(exc)
        self.proxy.websocket_protocols.discard(self.protocol)
        self.proxy.websocket_connections.pop(self.protocol, None)
        self.proxy.server_state.connections.discard(self.protocol)
        self.proxy.unregister(self.connection)


def _custom_websocket_request(data: bytes) -> tuple[bytes, bytes] | None:
    """Recreate Uvicorn's normalized request head before a protocol handoff."""
    header_end = data.find(b"\r\n\r\n")
    if header_end < 0:
        return None
    head = data[: header_end + 4]
    trailing = data[header_end + 4 :]
    lines = head[:-4].split(b"\r\n")
    if not lines:
        return None
    request_line = lines[0].split(b" ")
    if len(request_line) != 3:
        return None
    headers: list[tuple[bytes, bytes]] = []
    connection_tokens: list[bytes] = []
    upgrade_value: bytes | None = None
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or not name:
            return None
        name = name.lower()
        value = value.strip(b" \t")
        headers.append((name, value))
        if name == b"connection":
            connection_tokens = [token.lower().strip() for token in value.split(b",")]
        elif name == b"upgrade":
            upgrade_value = value.lower()
    if b"upgrade" not in connection_tokens or upgrade_value != b"websocket":
        return None
    method, target, _version = request_line
    normalized = bytearray(method + b" " + target + b" HTTP/1.1\r\n")
    for name, value in headers:
        normalized.extend(name + b": " + value + b"\r\n")
    normalized.extend(b"\r\n")
    return bytes(normalized), trailing


class _LifespanIO:
    """Queue-backed ASGI lifespan channels for Python protocol extensions."""

    def __init__(self, owner: _PythonLifespan) -> None:
        self.owner = owner
        self.requests: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def receive(self) -> dict[str, Any]:
        return await self.requests.get()

    async def send(self, message: dict[str, Any]) -> None:
        await self.owner.send(message)


class _PythonLifespan:
    """Run the ASGI lifespan needed by Uvicorn's user-supplied protocols."""

    def __init__(self, app: Any, mode: str, asgi_version: str) -> None:
        self.app = app
        self.mode = mode
        self.asgi_version = asgi_version
        self.state: dict[str, Any] = {}
        self.io = _LifespanIO(self)
        self.task: asyncio.Task[Any] | None = None
        self.startup_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()
        self.error_occurred = False
        self.startup_failed = False
        self.shutdown_failed = False
        self.should_exit = False

    async def startup(self) -> dict[str, Any]:
        if self.mode == "off":
            return self.state
        from uvicorn_rs._bridge import invoke

        scope = {
            "type": "lifespan",
            "asgi": {"version": self.asgi_version, "spec_version": "2.0"},
            "state": self.state,
        }
        self.task = asyncio.create_task(self._main(invoke, scope))
        await self.io.requests.put({"type": "lifespan.startup"})
        await self.startup_event.wait()
        if self.startup_failed or (self.error_occurred and self.mode == "on"):
            logger.error("Application startup failed. Exiting.")
            self.should_exit = True
            raise SystemExit(3)
        return self.state

    async def _main(self, invoke: Callable[..., Awaitable[Any]], scope: dict[str, Any]) -> None:
        try:
            await invoke(self.app, scope, self.io)
        except BaseException as error:
            self.error_occurred = True
            if self.startup_failed or self.shutdown_failed:
                return
            if self.mode == "auto":
                logger.info("ASGI 'lifespan' protocol appears unsupported.")
            else:
                logger.error("Exception in 'lifespan' protocol\n", exc_info=error)
        finally:
            self.startup_event.set()
            self.shutdown_event.set()

    async def send(self, message: dict[str, Any]) -> None:
        message_type = message["type"]
        assert message_type in {
            "lifespan.startup.complete",
            "lifespan.startup.failed",
            "lifespan.shutdown.complete",
            "lifespan.shutdown.failed",
        }
        if message_type == "lifespan.startup.complete":
            assert not self.startup_event.is_set()
            assert not self.shutdown_event.is_set()
            self.startup_event.set()
        elif message_type == "lifespan.startup.failed":
            assert not self.startup_event.is_set()
            assert not self.shutdown_event.is_set()
            self.startup_event.set()
            self.startup_failed = True
            if message.get("message"):
                logger.error(message["message"])
        elif message_type == "lifespan.shutdown.complete":
            assert self.startup_event.is_set()
            assert not self.shutdown_event.is_set()
            self.shutdown_event.set()
        else:
            assert self.startup_event.is_set()
            assert not self.shutdown_event.is_set()
            self.shutdown_event.set()
            self.shutdown_failed = True
            if message.get("message"):
                logger.error(message["message"])

    async def shutdown(self) -> None:
        if self.error_occurred:
            return
        if self.task is None:
            return
        await self.io.requests.put({"type": "lifespan.shutdown"})
        await self.shutdown_event.wait()
        if self.shutdown_failed or (self.error_occurred and self.mode == "on"):
            logger.error("Application shutdown failed. Exiting.")
            self.should_exit = True

    async def _stop_task(self) -> None:
        task = self.task
        if task is None:
            return
        if not task.done():
            task.cancel()
        with contextlib.suppress(BaseException):
            await task


class Server:
    """Run a :class:`Config` using the Rust network runtime."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.server_state = ServerState()
        self.started = False
        self._should_exit = False
        self.force_exit = False
        self._shutdown_logged = False
        self.last_notified = 0.0
        self._native_server: Any = None
        self._native_task: asyncio.Task[None] | None = None
        self._python_servers: list[asyncio.Server] = []
        self._python_lifespan: _PythonLifespan | None = None
        self._tls_context_proxy: _TLSContextProxy | None = None
        self._custom_websocket_proxy: _CustomWebSocketProtocolProxy | None = None
        self._inherited_socket: socket.socket | None = None
        self._captured_signals: list[int] = []

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self._should_exit = bool(value)
        if self._should_exit and self._native_server is not None:
            if self._tls_context_proxy is not None:
                self._tls_context_proxy.close_accepting()
            if self._custom_websocket_proxy is not None:
                self._custom_websocket_proxy.close_accepting()
            # Cancel the Rust accept loop before synchronous logging so a slow
            # log handler cannot postpone transport shutdown after a signal.
            write_shutdown_trace("server-native-shutdown.request")
            self._native_server.shutdown()
            write_shutdown_trace("server-native-shutdown.returned")
            self._log_shutdown_status()

    def _log_shutdown_status(self) -> None:
        """Report shutdown before native draining waits on ASGI tasks."""
        if self._shutdown_logged:
            return
        logger.info("Shutting down")
        if self.server_state.tasks:
            logger.info(
                "Waiting for background tasks to complete. (CTRL+C to force quit)"
            )
        self._shutdown_logged = True

    @cached_property
    def limit_max_requests(self) -> int | None:
        """Return the once-per-server request limit, including configured jitter."""
        if self.config.limit_max_requests is None:
            return None
        return self.config.limit_max_requests + random.randint(
            0, self.config.limit_max_requests_jitter
        )

    async def serve(self, sockets: list[socket.socket] | None = None) -> None:
        """Serve until shutdown, preserving caller event-loop ownership."""
        with self.capture_signals():
            await self._serve(sockets=sockets)

    async def _serve(self, sockets: list[socket.socket] | None = None) -> None:
        if not self.config.loaded:
            self.config.load()
        self.config._validate_native_runtime()

        process_id = os.getpid()
        logger.info("Started server process [%d]", process_id)
        cancelled = False
        try:
            await self.startup(sockets=sockets)
            await self.main_loop()
            if self.started:
                await self.shutdown(sockets=sockets)
                logger.info("Finished server process [%d]", process_id)
        except OSError as error:
            native_server = self._native_server
            if not self.started and native_server is not None and native_server.startup_failed:
                logger.error(error)
                raise SystemExit(3) from None
            raise
        except asyncio.CancelledError:
            if self.started:
                # Once startup is complete, Uvicorn leaves listener and server
                # state intact when the public serve task is cancelled.
                cancelled = True
            else:
                # Uvicorn binds only after lifespan startup. Let the native
                # server keep its lifespan task but skip listener startup if
                # this public serve task is cancelled first.
                native_server = self._native_server
                if native_server is not None:
                    native_server.cancel_startup()
                    cancelled = True
            raise
        finally:
            if not cancelled:
                self._cleanup_native_runtime()

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Start the Rust server and wait until its listener and lifespan are ready."""
        should_log_started_message = sockets is None
        if not self.config.loaded:
            self.config.load()
        self.config._validate_native_runtime()

        wsgi_auto_lifespan = (
            self.config.interface == "wsgi" and self.config.lifespan == "auto"
        )
        if wsgi_auto_lifespan:
            # Uvicorn's WSGI middleware rejects the lifespan scope. Its auto
            # lifespan handler logs this at INFO, treats startup as complete,
            # and skips lifespan shutdown. Keep that behavior in the Python
            # adapter while preventing the Rust lifecycle driver from logging
            # a fatal-looking unsupported-app diagnostic.
            logger.info("Waiting for application startup.")
            logger.info("ASGI 'lifespan' protocol appears unsupported.")
            logger.info("Application startup complete.")

        from uvicorn_rs import Server as NativeServer

        if sockets is None and self.config.uds is None and self.config.fd is not None:
            self._inherited_socket = socket.socket(fileno=os.dup(self.config.fd))
            sockets = [self._inherited_socket]

        if sockets is not None:
            # Listen before handing an inherited socket to the native server.
            # The supervisor also does this in its parent before spawning
            # Windows workers, so each child sees an already-listening handle.
            _ensure_windows_sockets_listening(sockets, self.config.backlog)

        if self.config._uses_custom_http_protocol:
            await self._startup_custom_http_protocol(sockets)
            return

        native_app = self.config.loaded_app
        native_host = self.config.host
        native_port = self.config.port
        native_uds = self.config.uds
        native_sockets = sockets
        tls_context_proxy = None
        custom_websocket_proxy = None
        if self.config._uses_custom_ws_protocol:
            custom_websocket_proxy = _CustomWebSocketProtocolProxy(
                self.config,
                self.server_state,
                self.config.ssl if self.config.is_ssl else None,
            )
            self._custom_websocket_proxy = custom_websocket_proxy
            try:
                await custom_websocket_proxy.bind(
                    self.config.host,
                    self.config.port,
                    sockets,
                )
            except BaseException:
                self._cleanup_native_runtime()
                raise
            if (
                custom_websocket_proxy.backend_socket is None
                or custom_websocket_proxy.backend_address is None
            ):
                self._cleanup_native_runtime()
                raise RuntimeError(
                    "custom WebSocket protocol proxy did not create its Rust listener"
                )
            native_app = custom_websocket_proxy.wrap_app(native_app)
            native_host = "127.0.0.1"
            native_port = custom_websocket_proxy.backend_address[1]
            native_uds = None
            native_sockets = [custom_websocket_proxy.backend_socket]
        elif self.config.ssl_context_factory is not None:
            tls_context_proxy = _TLSContextProxy(
                self.config.ssl,
                self.config.backlog,
                self.config.uds,
            )
            self._tls_context_proxy = tls_context_proxy
            try:
                await tls_context_proxy.bind(
                    self.config.host,
                    self.config.port,
                    sockets,
                )
            except BaseException:
                self._cleanup_native_runtime()
                raise
            if tls_context_proxy.backend_socket is None or tls_context_proxy.backend_address is None:
                self._cleanup_native_runtime()
                raise RuntimeError("TLS context proxy did not create its Rust listener")
            native_app = tls_context_proxy.wrap_app(native_app)
            native_host = "127.0.0.1"
            native_port = tls_context_proxy.backend_address[1]
            native_uds = None
            native_sockets = [tls_context_proxy.backend_socket]

        try:
            native_server = NativeServer(
                _track_server_state(native_app, self.server_state),
                host=native_host,
                port=native_port,
                uds=native_uds,
                backlog=self.config.backlog,
                timeout_keep_alive=self.config.timeout_keep_alive,
                certfile=(
                    None
                    if tls_context_proxy is not None
                    or custom_websocket_proxy is not None
                    else self.config.ssl_certfile
                ),
                keyfile=(
                    None
                    if tls_context_proxy is not None
                    or custom_websocket_proxy is not None
                    else self.config.ssl_keyfile
                ),
                ssl_keyfile_password=(
                    None
                    if tls_context_proxy is not None
                    or custom_websocket_proxy is not None
                    else self.config.ssl_keyfile_password
                ),
                ssl_ca_certs=(
                    os.fspath(self.config.ssl_ca_certs)
                    if tls_context_proxy is None
                    and custom_websocket_proxy is None
                    and self.config.ssl_ca_certs
                    else None
                ),
                ssl_cert_reqs=(
                    int(self.config.ssl_cert_reqs)
                    if tls_context_proxy is None and custom_websocket_proxy is None
                    else 0
                ),
                _tls12_only=(
                    self.config._native_tls12_only
                    if tls_context_proxy is None and custom_websocket_proxy is None
                    else False
                ),
                _tls_cipher_suites=(
                    self.config._native_tls_cipher_suites
                    if tls_context_proxy is None and custom_websocket_proxy is None
                    else None
                ),
                graceful_timeout=self.config.timeout_graceful_shutdown,
                lifespan="off" if wsgi_auto_lifespan else self.config.lifespan,
                root_path=self.config.root_path,
                default_headers=self.config.encoded_headers,
                date_header=self.config.date_header,
                http2=self.config.http2,
                ws_max_size=self.config.ws_max_size,
                ws_max_queue=(
                    self.config.ws_max_queue if self.config.ws == "websockets" else None
                ),
                websocket_enabled=self.config.ws != "none",
                ws_per_message_deflate=self.config.ws_per_message_deflate,
                ws_ping_interval=self.config.ws_ping_interval,
                ws_ping_timeout=self.config.ws_ping_timeout,
                _http1_max_buffer_size=(
                    # Hyper rejects an incomplete head when its buffer reaches
                    # this size; h11 permits the configured size and rejects
                    # only the next byte. Its default is 16 KiB.
                    (
                        self.config.h11_max_incomplete_event_size
                        if self.config.h11_max_incomplete_event_size is not None
                        else 16 * 1024
                    )
                    + 1
                    if self.config.http == "h11"
                    else None
                ),
                _http1_allow_authority_form=(
                    self.config.http != "httptools"
                    and (
                        self.config.http != "auto"
                        or importlib.util.find_spec("httptools") is None
                    )
                ),
                limit_concurrency=self.config.limit_concurrency,
                limit_max_requests=self.limit_max_requests,
                limit_max_requests_jitter=0,
                _reset_contextvars=self.config.reset_contextvars,
                _defer_startup_failure=True,
                _defer_startup_acceptance=True,
                sockets=native_sockets,
            )
        except BaseException:
            self._cleanup_native_runtime()
            raise
        self._native_server = native_server

        native_task = asyncio.create_task(native_server.serve())
        self._native_task = native_task
        try:
            # Readiness comes from Rust after bind and lifespan, never from the
            # scheduling yield.
            await asyncio.sleep(0)
            self.started = await native_server.wait_started()
            if self.started:
                try:
                    if tls_context_proxy is not None:
                        try:
                            await tls_context_proxy.start_serving()
                        except BaseException:
                            native_server.shutdown()
                            with contextlib.suppress(BaseException):
                                await asyncio.shield(native_task)
                            raise
                    if custom_websocket_proxy is not None:
                        try:
                            await custom_websocket_proxy.start_serving()
                        except BaseException:
                            native_server.shutdown()
                            with contextlib.suppress(BaseException):
                                await asyncio.shield(native_task)
                            raise
                    if should_log_started_message:
                        listeners = (
                            [sock for server in tls_context_proxy.servers for sock in (server.sockets or [])]
                            if tls_context_proxy is not None
                            else [
                                sock
                                for server in custom_websocket_proxy.servers
                                for sock in (server.sockets or [])
                            ]
                            if custom_websocket_proxy is not None
                            else sockets
                        )
                        self._log_started_message(listeners)
                finally:
                    native_server._acknowledge_startup()
        except OSError as error:
            if not self.started:
                with contextlib.suppress(BaseException):
                    await asyncio.shield(native_task)
                if native_server.startup_failed:
                    logger.error(error)
                    self._cleanup_native_runtime()
                    raise SystemExit(3) from None
            self._cleanup_native_runtime()
            raise
        except asyncio.CancelledError:
            raise
        except BaseException:
            native_server.shutdown()
            with contextlib.suppress(BaseException):
                await asyncio.shield(native_task)
            self._cleanup_native_runtime()
            raise

        if not self.started and not self._should_exit:
            try:
                await native_task
            except OSError as error:
                self._cleanup_native_runtime()
                if native_server.startup_failed:
                    logger.error(error)
                    raise SystemExit(3) from None
                raise
            except BaseException:
                self._cleanup_native_runtime()
                raise
            if native_server.startup_failed:
                self._cleanup_native_runtime()
                raise SystemExit(3)

    async def _startup_custom_http_protocol(
        self, sockets: list[socket.socket] | None
    ) -> None:
        """Honor Uvicorn's explicit asyncio.Protocol extension boundary."""
        protocol_class = self.config.http_protocol_class
        if protocol_class is None:
            raise RuntimeError("custom HTTP protocol was not resolved by Config.load()")

        lifespan = _PythonLifespan(
            self.config.loaded_app, self.config.lifespan, self.config.asgi_version
        )
        self._python_lifespan = lifespan
        await lifespan.startup()
        loop = asyncio.get_running_loop()

        def create_protocol(
            _loop: asyncio.AbstractEventLoop | None = None,
        ) -> asyncio.Protocol:
            return protocol_class(
                config=self.config,
                server_state=self.server_state,
                app_state=lifespan.state,
                _loop=_loop,
            )

        if sockets is not None:
            self._python_servers = []
            for sock in sockets:
                server = await loop.create_server(
                    create_protocol,
                    sock=sock,
                    ssl=self.config.ssl,
                    backlog=self.config.backlog,
                )
                self._python_servers.append(server)
        elif self.config.uds is not None:
            uds_perms = (
                os.stat(self.config.uds).st_mode
                if os.path.exists(self.config.uds)
                else 0o666
            )
            server = await loop.create_unix_server(
                create_protocol,
                path=self.config.uds,
                ssl=self.config.ssl,
                backlog=self.config.backlog,
            )
            os.chmod(self.config.uds, uds_perms)
            self._python_servers = [server]
        else:
            try:
                server = await loop.create_server(
                    create_protocol,
                    host=self.config.host,
                    port=self.config.port,
                    ssl=self.config.ssl,
                    backlog=self.config.backlog,
                )
            except OSError as error:
                logger.error(error)
                await lifespan.shutdown()
                self._python_lifespan = None
                raise SystemExit(3) from None
            self._python_servers = [server]

        if sockets is None:
            listeners = [
                sock
                for server in self._python_servers
                for sock in (server.sockets or [])
            ]
            self._log_started_message(listeners)
        self.started = True

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        """Stop the Rust server and wait for active connections and lifespan cleanup."""
        self._log_shutdown_status()

        if self._python_servers:
            servers = self._python_servers
            for server in servers:
                server.close()
            for sock in sockets or []:
                sock.close()

            for connection in list(self.server_state.connections):
                connection.shutdown()
            await asyncio.sleep(0.1)

            try:
                await asyncio.wait_for(
                    self._wait_for_python_tasks_to_complete(servers),
                    timeout=self.config.timeout_graceful_shutdown,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Cancel %s running task(s), timeout graceful shutdown exceeded",
                    len(self.server_state.tasks),
                )
                for task in self.server_state.tasks:
                    task.cancel(msg="Task cancelled, timeout graceful shutdown exceeded")

            if not self.force_exit and self._python_lifespan is not None:
                lifespan = self._python_lifespan
                await lifespan.shutdown()
            self._python_servers = []
            self._cleanup_native_runtime()
            return

        native_server = self._native_server
        native_task = self._native_task
        tls_context_proxy = self._tls_context_proxy
        custom_websocket_proxy = self._custom_websocket_proxy
        if tls_context_proxy is not None:
            tls_context_proxy.close_accepting()
        if custom_websocket_proxy is not None:
            custom_websocket_proxy.close_accepting()
            custom_websocket_proxy.shutdown_websockets()
            if self.force_exit:
                custom_websocket_proxy.close_websockets()
            else:
                try:
                    await asyncio.wait_for(
                        custom_websocket_proxy.wait_for_websockets(),
                        timeout=self.config.timeout_graceful_shutdown,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "Cancel %s running task(s), timeout graceful shutdown exceeded",
                        len(self.server_state.tasks),
                    )
                    custom_websocket_proxy.close_websockets()
                    for task in self.server_state.tasks:
                        task.cancel(
                            msg="Task cancelled, timeout graceful shutdown exceeded"
                        )
        try:
            if native_server is not None:
                write_shutdown_trace("server-shutdown.request")
                native_server.shutdown()
            if native_task is not None:
                await native_task
                write_shutdown_trace("server-native-task.finished")
        finally:
            for sock in sockets or []:
                sock.close()
            if tls_context_proxy is not None:
                await tls_context_proxy.close()
            if custom_websocket_proxy is not None:
                await custom_websocket_proxy.close()
            self._cleanup_native_runtime()

    async def _wait_for_python_tasks_to_complete(
        self, servers: list[asyncio.Server]
    ) -> None:
        if self.server_state.connections and not self.force_exit:
            logger.info("Waiting for connections to close. (CTRL+C to force quit)")
            while self.server_state.connections and not self.force_exit:
                await asyncio.sleep(0.1)
        if self.server_state.tasks and not self.force_exit:
            logger.info("Waiting for background tasks to complete. (CTRL+C to force quit)")
            while self.server_state.tasks and not self.force_exit:
                await asyncio.sleep(0.1)
        for server in servers:
            await server.wait_closed()

    def _cleanup_native_runtime(self) -> None:
        """Release runtime references, listeners, and inherited duplicates."""
        self._native_server = None
        self._native_task = None
        for server in self._python_servers:
            server.close()
        self._python_servers = []
        if self._python_lifespan is not None:
            task = self._python_lifespan.task
            if task is not None and not task.done():
                task.cancel()
        self._python_lifespan = None
        tls_context_proxy = self._tls_context_proxy
        self._tls_context_proxy = None
        if tls_context_proxy is not None:
            tls_context_proxy.close_accepting()
            for writer in tuple(tls_context_proxy.writers):
                writer.close()
            for task in tuple(tls_context_proxy.tasks):
                task.cancel()
            tls_context_proxy.scope_metadata.clear()
            if tls_context_proxy.backend_socket is not None:
                tls_context_proxy.backend_socket.close()
                tls_context_proxy.backend_socket = None
        custom_websocket_proxy = self._custom_websocket_proxy
        self._custom_websocket_proxy = None
        if custom_websocket_proxy is not None:
            custom_websocket_proxy.close_now()
        inherited_socket = self._inherited_socket
        self._inherited_socket = None
        if inherited_socket is not None:
            inherited_socket.close()

    async def main_loop(self) -> None:
        """Wait for serving to stop while running Uvicorn worker tick hooks."""
        native_server = self._native_server
        native_task = self._native_task
        if native_server is not None and native_task is not None:
            await self._wait_for_native_server(native_task, native_server)
            return

        counter = 0
        while not await self.on_tick(counter):
            counter = (counter + 1) % 864000
            await asyncio.sleep(0.1)

    async def _wait_for_native_server(self, native_task, native_server) -> None:
        """Wait for Rust serving while delivering optional Uvicorn worker heartbeats."""
        counter = 0
        while not native_task.done():
            try:
                should_exit = await self.on_tick(counter)
            except BaseException:
                native_server.shutdown()
                with contextlib.suppress(BaseException):
                    await native_task
                raise

            if should_exit:
                write_shutdown_trace("server-main-loop.exit-observed")
                if self._tls_context_proxy is not None:
                    self._tls_context_proxy.close_accepting()
                if self._custom_websocket_proxy is not None:
                    self._custom_websocket_proxy.close_accepting()
                native_server.shutdown()

            if native_task.done():
                break
            counter = (counter + 1) % 864000
            await asyncio.wait((native_task,), timeout=0.1)

        await native_task

    async def on_tick(self, counter: int) -> bool:
        """Update worker state and report whether Uvicorn should stop serving."""
        if counter % 10 == 0:
            current_time = time.time()
            date_header = (
                [(b"date", formatdate(current_time, usegmt=True).encode())]
                if self.config.date_header
                else []
            )
            self.server_state.default_headers = date_header + self.config.encoded_headers

            callback = self.config.callback_notify
            if callback is not None and current_time - self.last_notified > self.config.timeout_notify:
                self.last_notified = current_time
                await callback()

        if self.should_exit:
            return True

        max_requests = self.limit_max_requests
        if max_requests is not None and self.server_state.total_requests >= max_requests:
            logger.info(
                "Maximum request limit of %d exceeded. Terminating process.",
                max_requests,
            )
            return True

        return False

    def _log_started_message(self, sockets: list[socket.socket] | None = None) -> None:
        """Log the selected listener URL after native startup completes."""
        if self.config.fd is not None and sockets:
            logger.info(
                "Uvicorn running on socket %s (Press CTRL+C to quit)",
                sockets[0].getsockname(),
            )
            return
        if self.config.uds is not None:
            logger.info(
                "Uvicorn running on unix socket %s (Press CTRL+C to quit)",
                self.config.uds,
            )
            return
        host = self.config.host or "0.0.0.0"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        scheme = "https" if self.config.is_ssl else "http"
        logger.info(
            "Uvicorn running on %s://%s:%d (Press CTRL+C to quit)",
            scheme,
            host,
            self.config.port,
        )

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        """Gracefully stop on signals, then restore their normal process effect."""
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        original_handlers = {
            signum: signal.signal(signum, self.handle_exit)
            for signum in HANDLED_SIGNALS
        }
        try:
            yield
        finally:
            for signum, handler in original_handlers.items():
                signal.signal(signum, handler)

        # Fault-contract runs keep the coverage-instrumented process exit
        # normal so LLVM can flush its profile. Public signal behavior is
        # exercised by the ordinary parity cases.
        if os.environ.get("UVICORN_RS_COVERAGE_FAULT_FILE"):
            return

        for signum in reversed(self._captured_signals):
            signal.raise_signal(signum)

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        """Record a signal and request graceful shutdown from the native server."""
        write_shutdown_trace(
            "server-signal.received "
            f"signal={sig} native_server={self._native_server is not None}"
        )
        self._captured_signals.append(sig)
        if self._should_exit and sig == signal.SIGINT:
            self.force_exit = True
            if self._native_server is not None:
                self._native_server.force_shutdown()
        else:
            self.should_exit = True

    def run(self, sockets: list[socket.socket] | None = None) -> None:
        """Run :meth:`serve` in a new loop and handle process signals."""
        # Match Uvicorn's evaluation order: it creates the serve coroutine
        # before resolving the loop factory. If loop selection fails, Python
        # consequently reports the same unawaited-coroutine warning.
        serve_coroutine = self.serve(sockets=sockets)
        try:
            loop_factory = self.config.get_loop_factory()
        except BaseException:
            # The Rust adapter resolves the loop before handing the coroutine
            # to asyncio.Runner. Emit the warning Uvicorn gets from dropping
            # that coroutine during argument evaluation, then close it so the
            # adapter does not emit a second warning during cleanup.
            try:
                warnings.warn(
                    f"coroutine '{serve_coroutine.__qualname__}' was never awaited",
                    RuntimeWarning,
                    stacklevel=2,
                    source=serve_coroutine,
                )
            finally:
                serve_coroutine.close()
            raise

        if sys.version_info >= (3, 11):
            with asyncio.Runner(loop_factory=loop_factory) as runner:
                runner.run(serve_coroutine)
        elif loop_factory is None:
            asyncio.run(serve_coroutine)
        else:
            loop = loop_factory()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(serve_coroutine)
            finally:
                asyncio.set_event_loop(None)
                loop.close()
        write_shutdown_trace("server.run.returned")
