"""Public server API backed by the Rust network runtime."""

import asyncio

from . import _bridge, _native


class Server:
    """Serve one ASGI 3 application over HTTP/1.1, HTTP/2, and HTTP/3."""

    def __init__(
        self,
        app,
        host="127.0.0.1",
        port=8000,
        certfile=None,
        keyfile=None,
        graceful_timeout=10,
    ):
        self.app = app
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile
        self.graceful_timeout = graceful_timeout

    async def serve(self):
        """Run the server until its task is cancelled or the process exits."""
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
