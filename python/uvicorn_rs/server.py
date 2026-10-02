"""Public server API backed by the Rust network runtime."""

import asyncio

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

        Configuration errors are reported when :meth:`serve` starts the native
        runtime.
        """
        self.app = app
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.graceful_timeout = graceful_timeout

    async def serve(self):
        """Run the server until shutdown or task cancellation.

        Cancellation requests graceful native shutdown, waits for cleanup, and
        then propagates ``asyncio.CancelledError``. Startup, bind, application,
        and lifespan failures propagate to the caller.
        """
        control = _native.ServerControl()
        native_task = asyncio.ensure_future(
            _native.serve(
                self.app,
                _bridge.invoke,
                self.host,
                self.port,
                self.certfile,
                self.keyfile,
                self.graceful_timeout,
                control,
            )
        )
        try:
            await asyncio.shield(native_task)
        except asyncio.CancelledError:
            control.shutdown()
            await asyncio.shield(native_task)
            raise
