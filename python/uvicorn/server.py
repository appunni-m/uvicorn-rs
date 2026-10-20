# Copyright (c) 2026 Appunni M
# Public constructor shape follows Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Uvicorn-compatible programmatic server facade over the Rust engine."""

from __future__ import annotations

import asyncio
import signal
import socket
import sys
from typing import Any

from .config import Config


class Server:
    """Run a :class:`Config` using the Rust network runtime."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.started = False
        self._should_exit = False
        self.force_exit = False
        self._native_server: Any = None

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self._should_exit = bool(value)
        if self._should_exit and self._native_server is not None:
            self._native_server.shutdown()

    async def serve(self, sockets: list[socket.socket] | None = None) -> None:
        """Serve until shutdown, preserving caller event-loop ownership."""
        if sockets is not None:
            raise NotImplementedError("uvicorn-rs does not support pre-bound sockets yet")
        self.config.validate_native_runtime()
        if not self.config.loaded:
            self.config.load()

        from uvicorn_rs import Server as NativeServer

        native_server = NativeServer(
            self.config.loaded_app,
            host=self.config.host,
            port=self.config.port,
            certfile=self.config.ssl_certfile,
            keyfile=self.config.ssl_keyfile,
            graceful_timeout=(
                10
                if self.config.timeout_graceful_shutdown is None
                else self.config.timeout_graceful_shutdown
            ),
            lifespan=self.config.lifespan != "off",
            root_path=self.config.root_path,
            default_headers=self.config.encoded_headers,
            date_header=self.config.date_header,
        )
        self._native_server = native_server
        if self._should_exit:
            native_server.shutdown()

        native_task = asyncio.create_task(native_server.serve())
        try:
            # Let the native serve coroutine install its startup control. The
            # value of ``started`` comes from Rust after bind and lifespan,
            # never from this scheduling yield.
            await asyncio.sleep(0)
            if native_task.done():
                await native_task
            self.started = await native_server.wait_started()
            await native_task
        finally:
            self._native_server = None

    def run(self, sockets: list[socket.socket] | None = None) -> None:
        """Run :meth:`serve` in a new loop and handle process signals."""
        loop_factory = self.config.get_loop_factory()

        async def run_server() -> None:
            loop = asyncio.get_running_loop()
            installed_handlers = []
            for signum in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(signum, setattr, self, "should_exit", True)
                except (AttributeError, NotImplementedError, RuntimeError, ValueError):
                    continue
                installed_handlers.append(signum)
            try:
                await self.serve(sockets=sockets)
            finally:
                for signum in installed_handlers:
                    try:
                        loop.remove_signal_handler(signum)
                    except (AttributeError, NotImplementedError, RuntimeError, ValueError):
                        pass

        if sys.version_info >= (3, 11):
            with asyncio.Runner(loop_factory=loop_factory) as runner:
                runner.run(run_server())
        elif loop_factory is None:
            asyncio.run(run_server())
        else:
            loop = loop_factory()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_server())
            finally:
                asyncio.set_event_loop(None)
                loop.close()
