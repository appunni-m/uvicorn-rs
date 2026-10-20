"""Public server API backed by the Rust network runtime."""

import asyncio
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
        certfile=None,
        keyfile=None,
        graceful_timeout=10,
        lifespan=True,
        root_path="",
        default_headers=None,
        date_header=True,
        ws_max_size=16 * 1024 * 1024,
        limit_concurrency=None,
        _defer_startup_failure=False,
    ):
        """Store the application and listener options for a server run.

        Args:
            app: ASGI 3 application callable.
            host: TCP bind host and, when TLS is enabled, QUIC bind host.
            port: TCP and QUIC port in the range supported by the OS.
            certfile: Optional PEM certificate chain. Pair with ``keyfile`` to
                enable HTTPS and HTTP/3.
            keyfile: Optional PEM private key paired with ``certfile``.
            graceful_timeout: Non-negative shutdown grace period in seconds.
            lifespan: A boolean enabling automatic lifespan detection, or one
                of ``"auto"``, ``"on"``, or ``"off"``. Strict ``"on"`` mode
                propagates startup failure with Uvicorn's exit status 3.
            root_path: Prefix used for the ASGI ``root_path``, ``path``, and
                ``raw_path`` scope values.
            default_headers: Encoded response headers inserted before the
                application's response headers. ``None`` uses Uvicorn's
                default ``server: uvicorn`` header.
            date_header: Whether to add the standard HTTP ``Date`` header.
            limit_concurrency: Maximum active connections or request tasks
                before the Rust runtime returns HTTP 503.

        Configuration errors are reported when :meth:`serve` starts the native
        runtime.
        """
        self.app = app
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.graceful_timeout = graceful_timeout
        self.lifespan = lifespan
        self.root_path = root_path
        self.default_headers = (
            [(b"server", b"uvicorn")] if default_headers is None else default_headers
        )
        self.date_header = date_header
        self.ws_max_size = ws_max_size
        self.limit_concurrency = limit_concurrency
        self._defer_startup_failure = _defer_startup_failure
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
        control = _native.ServerControl()
        self._control = control
        limit_concurrency = self.limit_concurrency
        if limit_concurrency is not None:
            limit_concurrency = min(max(limit_concurrency, 0), sys.maxsize)
        native_task = asyncio.ensure_future(
            _native.serve(
                self.app,
                _bridge.invoke,
                self.host,
                self.port,
                self.certfile,
                self.keyfile,
                self.graceful_timeout,
                self.lifespan,
                self.root_path,
                self.default_headers,
                self.date_header,
                self.ws_max_size,
                limit_concurrency,
                control,
            )
        )
        try:
            await asyncio.shield(native_task)
        except asyncio.CancelledError:
            control.shutdown()
            await asyncio.shield(native_task)
            raise
        finally:
            self.startup_failed = await control.wait_startup_failed()
            if self._control is control:
                self._control = None
        if self.startup_failed and not self._defer_startup_failure:
            raise SystemExit(3)
