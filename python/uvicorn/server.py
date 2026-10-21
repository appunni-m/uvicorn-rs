# Copyright (c) 2026 Appunni M
# Public constructor shape follows Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Uvicorn-compatible programmatic server facade over the Rust engine."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
import threading
from collections.abc import Generator
from types import FrameType
from typing import Any

from .config import Config

HANDLED_SIGNALS = (signal.SIGINT, signal.SIGTERM)
if sys.platform == "win32":  # pragma: no cover - Windows-specific signal
    HANDLED_SIGNALS += (signal.SIGBREAK,)

logger = logging.getLogger("uvicorn.error")


class Server:
    """Run a :class:`Config` using the Rust network runtime."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.started = False
        self._should_exit = False
        self.force_exit = False
        self._native_server: Any = None
        self._captured_signals: list[int] = []

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        was_exiting = self._should_exit
        self._should_exit = bool(value)
        if self._should_exit and not was_exiting:
            logger.info("Shutting down")
        if self._should_exit and self._native_server is not None:
            self._native_server.shutdown()

    async def serve(self, sockets: list[socket.socket] | None = None) -> None:
        """Serve until shutdown, preserving caller event-loop ownership."""
        with self.capture_signals():
            await self._serve(sockets=sockets)

    async def _serve(self, sockets: list[socket.socket] | None = None) -> None:
        self.config.validate_native_runtime()
        if not self.config.loaded:
            self.config.load()

        process_id = os.getpid()
        logger.info("Started server process [%d]", process_id)

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

        inherited_socket = None
        if sockets is None and self.config.uds is None and self.config.fd is not None:
            inherited_socket = socket.fromfd(
                self.config.fd, socket.AF_INET, socket.SOCK_STREAM
            )
            sockets = [inherited_socket]
        try:
            native_server = NativeServer(
                self.config.loaded_app,
                host=self.config.host,
                port=self.config.port,
                uds=self.config.uds,
                backlog=self.config.backlog,
                timeout_keep_alive=self.config.timeout_keep_alive,
                certfile=self.config.ssl_certfile,
                keyfile=self.config.ssl_keyfile,
                graceful_timeout=self.config.timeout_graceful_shutdown,
                lifespan="off" if wsgi_auto_lifespan else self.config.lifespan,
                root_path=self.config.root_path,
                default_headers=self.config.encoded_headers,
                date_header=self.config.date_header,
                ws_max_size=self.config.ws_max_size,
                ws_ping_interval=self.config.ws_ping_interval,
                ws_ping_timeout=self.config.ws_ping_timeout,
                limit_concurrency=self.config.limit_concurrency,
                limit_max_requests=self.config.limit_max_requests,
                _defer_startup_failure=True,
                sockets=sockets,
            )
            self._native_server = native_server
            if self._should_exit:
                native_server.shutdown()

            native_task = asyncio.create_task(native_server.serve())
            try:
                # Readiness comes from Rust after bind and lifespan, never from
                # the scheduling yield.
                await asyncio.sleep(0)
                self.started = await native_server.wait_started()
                if self.started:
                    self._log_started_message(sockets)
                await native_task
                if self.started:
                    logger.info("Finished server process [%d]", process_id)
                if native_server.startup_failed:
                    raise SystemExit(3)
            finally:
                self._native_server = None
        finally:
            if inherited_socket is not None:
                inherited_socket.close()

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
        scheme = "https" if self.config.ssl_certfile is not None else "http"
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

        for signum in reversed(self._captured_signals):
            signal.raise_signal(signum)

    def handle_exit(self, signum: int, frame: FrameType | None) -> None:
        """Record a signal and request graceful shutdown from the native server."""
        self._captured_signals.append(signum)
        if self._should_exit and signum == signal.SIGINT:
            self.force_exit = True
        else:
            self.should_exit = True

    def run(self, sockets: list[socket.socket] | None = None) -> None:
        """Run :meth:`serve` in a new loop and handle process signals."""
        loop_factory = self.config.get_loop_factory()

        if sys.version_info >= (3, 11):
            with asyncio.Runner(loop_factory=loop_factory) as runner:
                runner.run(self.serve(sockets=sockets))
        elif loop_factory is None:
            asyncio.run(self.serve(sockets=sockets))
        else:
            loop = loop_factory()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.serve(sockets=sockets))
            finally:
                asyncio.set_event_loop(None)
                loop.close()
