"""Public server API backed by the Rust network runtime."""

import asyncio
import os
import tempfile
import sys

from . import _bridge, _native


class Server:
    """Serve one ASGI 3 application over HTTP/1.1, HTTP/2, and HTTP/3.

    The application executes on the Python event loop that calls :meth:`serve`;
    Rust owns the network listeners and protocol data plane.
    """

    def __init__(
        self,
        app,
        host="127.0.0.1",
        port=8000,
        uds=None,
        backlog=2048,
        timeout_keep_alive=5,
        certfile=None,
        keyfile=None,
        graceful_timeout=10,
        lifespan=True,
        root_path="",
        default_headers=None,
        date_header=True,
        ws_max_size=16 * 1024 * 1024,
        limit_concurrency=None,
        ws_ping_interval=20.0,
        ws_ping_timeout=20.0,
        limit_max_requests=None,
        _defer_startup_failure=False,
        sockets=None,
        limit_max_requests_jitter=0,
        http2=True,
        _reset_contextvars=False,
    ):
        """Store the application and listener options for a server run.

        Args:
            app: ASGI 3 application callable.
            host: TCP bind host and, when TLS is enabled, QUIC bind host.
            port: TCP and QUIC port in the range supported by the OS.
            uds: Optional Unix domain socket path. When set, the Rust runtime
                binds this stream socket and does not create a QUIC listener.
            sockets: Optional non-empty list of pre-bound IPv4 or IPv6 TCP
                listeners. Their descriptors are transferred to Rust during
                startup.
            backlog: Maximum pending TCP connections; negative values are
                clamped to zero as in Uvicorn's socket-listen path.
            timeout_keep_alive: Idle timeout for persistent HTTP/1 connections
                in seconds. HTTP/2 and HTTP/3 connections are not affected.
            certfile: Optional PEM certificate chain. Pair with ``keyfile`` to
                enable HTTPS and HTTP/3.
            keyfile: Optional PEM private key paired with ``certfile``.
            graceful_timeout: Non-negative shutdown grace period in seconds;
                ``None`` waits for shutdown to finish without a deadline.
            lifespan: A boolean enabling automatic lifespan detection, or one
                of ``"auto"``, ``"on"``, or ``"off"``. Strict ``"on"`` mode
                propagates startup failure with Uvicorn's exit status 3.
            root_path: Prefix used for the ASGI ``root_path`` and ``path``
                scope values. ``raw_path`` always preserves the request path
                bytes received from the client.
            default_headers: Encoded response headers inserted before the
                application's response headers. ``None`` uses Uvicorn's
                default ``server: uvicorn`` header.
            date_header: Whether to add the standard HTTP ``Date`` header.
            http2: Whether TCP listeners accept HTTP/2 and prior-knowledge h2c.
            ws_ping_interval: Seconds between server-initiated WebSocket pings;
                ``None`` or a non-positive value disables keepalive pings.
            ws_ping_timeout: Seconds to wait for the matching pong before
                closing with code 1011; ``None`` disables the pong deadline.
            limit_concurrency: Maximum active connections or request tasks
                before the Rust runtime returns HTTP 503.
            limit_max_requests: Maximum number of completed HTTP responses
                before graceful server shutdown. Non-positive values stop
                after startup, matching Uvicorn's request counter semantics.
            limit_max_requests_jitter: Random non-negative addition to the
                completed-response threshold, selected once at startup.

        Configuration errors are reported when :meth:`serve` starts the native
        runtime.
        """
        self.app = app
        self.host = host
        self.port = port
        self.uds = uds
        self.sockets = sockets
        self.backlog = backlog
        self.timeout_keep_alive = timeout_keep_alive
        self.certfile = certfile
        self.keyfile = keyfile
        self.graceful_timeout = graceful_timeout
        self.lifespan = lifespan
        self.root_path = root_path
        self.default_headers = (
            [(b"server", b"uvicorn")] if default_headers is None else default_headers
        )
        self.date_header = date_header
        self.http2 = http2
        self.ws_max_size = ws_max_size
        self.limit_concurrency = limit_concurrency
        self.ws_ping_interval = ws_ping_interval
        self.ws_ping_timeout = ws_ping_timeout
        self.limit_max_requests = limit_max_requests
        self.limit_max_requests_jitter = limit_max_requests_jitter
        self._defer_startup_failure = _defer_startup_failure
        self._reset_contextvars = _reset_contextvars
        self.startup_failed = False
        self._control = None

    def shutdown(self):
        """Request graceful native shutdown without cancelling the Python task.

        The request is ignored before :meth:`serve` starts or after it exits.
        """
        control = self._control
        if control is not None:
            control.shutdown()

    async def wait_started(self):
        """Wait until bind and lifespan startup finish, or startup terminates."""
        control = self._control
        if control is None:
            return False
        return await control.wait_started()

    async def wait_startup_failed(self):
        """Wait for startup to finish and report a fatal lifespan failure."""
        control = self._control
        if control is None:
            return self.startup_failed
        return await control.wait_startup_failed()

    async def serve(self):
        """Run the server until shutdown or task cancellation.

        Cancellation requests graceful native shutdown, waits for cleanup, and
        then propagates ``asyncio.CancelledError``. Startup, bind, application,
        and lifespan failures propagate to the caller.
        """
        if self.sockets is not None and self.uds is not None:
            raise ValueError("pre-bound sockets cannot be combined with uds")
        if self.sockets is not None and not self.sockets:
            raise ValueError("at least one pre-bound TCP listener is required")
        transfer_directory = None
        transfer_path = None
        if self.sockets is not None:
            transfer_directory = tempfile.TemporaryDirectory(
                prefix="uvrs-", dir="/tmp" if os.path.isdir("/tmp") else None
            )
            transfer_path = os.path.join(transfer_directory.name, "listener.sock")
        control = _native.ServerControl()
        self._control = control
        limit_concurrency = self.limit_concurrency
        if limit_concurrency is not None:
            limit_concurrency = min(max(limit_concurrency, 0), sys.maxsize)
        limit_max_requests = self.limit_max_requests
        if limit_max_requests is not None:
            limit_max_requests = min(max(limit_max_requests, 0), sys.maxsize)
        if self.limit_max_requests_jitter < 0:
            raise ValueError("limit_max_requests_jitter must be non-negative")
        limit_max_requests_jitter = min(
            self.limit_max_requests_jitter, sys.maxsize
        )
        native_task = None
        app_invoker = (
            _bridge.invoke_with_reset_contextvars
            if self._reset_contextvars
            else _bridge.invoke
        )
        try:
            native_task = asyncio.ensure_future(
                _native.serve(
                    self.app,
                    app_invoker,
                    self.host,
                    self.port,
                    self.uds,
                    transfer_path,
                    self.backlog,
                    self.timeout_keep_alive,
                    self.certfile,
                    self.keyfile,
                    self.graceful_timeout,
                    self.lifespan,
                    self.root_path,
                    self.default_headers,
                    self.date_header,
                    self.http2,
                    self.ws_max_size,
                    self.ws_ping_interval,
                    self.ws_ping_timeout,
                    limit_concurrency,
                    limit_max_requests,
                    limit_max_requests_jitter,
                    control,
                    _bridge.log_concurrency_limit_rejection,
                )
            )
            if transfer_path is not None:
                await asyncio.to_thread(
                    _bridge.send_listener_fds, transfer_path, self.sockets
                )
            await asyncio.shield(native_task)
        except asyncio.CancelledError:
            control.shutdown()
            if native_task is not None:
                await asyncio.shield(native_task)
            raise
        except BaseException:
            if native_task is not None:
                native_task.cancel()
                await asyncio.gather(native_task, return_exceptions=True)
            raise
        finally:
            if transfer_directory is not None:
                transfer_directory.cleanup()
            if native_task is not None:
                self.startup_failed = await control.wait_startup_failed()
            if self._control is control:
                self._control = None
        if self.startup_failed and not self._defer_startup_failure:
            raise SystemExit(3)
