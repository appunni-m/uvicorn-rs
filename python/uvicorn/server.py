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
from collections.abc import Generator
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


def _track_server_state(app: Any, state: ServerState) -> Any:
    """Mirror request-task and completed-response state at the ASGI boundary."""

    async def tracked_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope.get("type")
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
        self._inherited_socket: socket.socket | None = None
        self._captured_signals: list[int] = []

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self._should_exit = bool(value)
        if self._should_exit and self._native_server is not None:
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
        self.config._validate_native_runtime()
        if not self.config.loaded:
            self.config.load()

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
        self.config._validate_native_runtime()
        if not self.config.loaded:
            self.config.load()

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

        try:
            native_server = NativeServer(
                _track_server_state(self.config.loaded_app, self.server_state),
                host=self.config.host,
                port=self.config.port,
                uds=self.config.uds,
                backlog=self.config.backlog,
                timeout_keep_alive=self.config.timeout_keep_alive,
                certfile=self.config.ssl_certfile,
                keyfile=self.config.ssl_keyfile,
                ssl_keyfile_password=self.config.ssl_keyfile_password,
                ssl_ca_certs=(
                    os.fspath(self.config.ssl_ca_certs)
                    if self.config.ssl_ca_certs
                    else None
                ),
                ssl_cert_reqs=int(self.config.ssl_cert_reqs),
                _tls12_only=self.config._native_tls12_only,
                _tls_cipher_suites=self.config._native_tls_cipher_suites,
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
                sockets=sockets,
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
                    if should_log_started_message:
                        self._log_started_message(sockets)
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

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        """Stop the Rust server and wait for active connections and lifespan cleanup."""
        self._log_shutdown_status()

        native_server = self._native_server
        native_task = self._native_task
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
            self._cleanup_native_runtime()

    def _cleanup_native_runtime(self) -> None:
        """Release adapter-owned references and inherited listener duplicates."""
        self._native_server = None
        self._native_task = None
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
