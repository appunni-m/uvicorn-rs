# Copyright (c) 2026 Appunni M
# Adapted from Uvicorn 0.54.0's deprecated Gunicorn worker integration.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Deprecated Gunicorn workers that run the Rust-native Uvicorn server."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import warnings
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from gunicorn.arbiter import Arbiter
from gunicorn.workers.base import Worker

from uvicorn.config import Config
from uvicorn.server import Server

warnings.warn(
    "The `uvicorn.workers` module is deprecated. Please use `uvicorn-worker` package instead.\n"
    "For more details, see https://github.com/Kludex/uvicorn-worker.",
    DeprecationWarning,
)

_T = TypeVar("_T")


def _cancel_all_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel pending tasks and report failures before closing a legacy loop."""
    pending = asyncio.all_tasks(loop)
    if not pending:
        return

    for task in pending:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

    for task in pending:
        if task.cancelled():
            continue
        exception = task.exception()
        if exception is not None:
            loop.call_exception_handler(
                {
                    "message": "unhandled exception during asyncio.run() shutdown",
                    "exception": exception,
                    "task": task,
                }
            )


def _legacy_asyncio_run(
    main: Coroutine[Any, Any, _T],
    *,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None,
) -> _T:
    """Run a worker coroutine with the Python 3.9/3.10 Uvicorn loop cleanup."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("asyncio.run() cannot be called from a running event loop")

    if not asyncio.iscoroutine(main):
        raise ValueError(f"a coroutine was expected, got {main!r}")

    loop = asyncio.new_event_loop() if loop_factory is None else loop_factory()
    try:
        if loop_factory is None:
            asyncio.set_event_loop(loop)
        loop.set_debug(False)
        return loop.run_until_complete(main)
    finally:
        try:
            _cancel_all_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            if loop_factory is None:
                asyncio.set_event_loop(None)
            loop.close()


class UvicornWorker(Worker):
    """Gunicorn worker for an ASGI application served by Uvicorn-RS."""

    CONFIG_KWARGS: dict[str, Any] = {"loop": "auto", "http": "auto"}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        logger = logging.getLogger("uvicorn.error")
        logger.handlers = self.log.error_log.handlers
        logger.setLevel(self.log.error_log.level)
        logger.propagate = False

        logger = logging.getLogger("uvicorn.access")
        logger.handlers = self.log.access_log.handlers
        logger.setLevel(self.log.access_log.level)
        logger.propagate = False

        config_kwargs: dict[str, Any] = {
            "app": None,
            "log_config": None,
            "timeout_keep_alive": self.cfg.keepalive,
            "timeout_notify": self.timeout,
            "callback_notify": self.callback_notify,
            "limit_max_requests": self.max_requests,
            "forwarded_allow_ips": self.cfg.forwarded_allow_ips,
        }

        if self.cfg.is_ssl:
            config_kwargs.update(
                {
                    "ssl_keyfile": self.cfg.ssl_options.get("keyfile"),
                    "ssl_certfile": self.cfg.ssl_options.get("certfile"),
                    "ssl_keyfile_password": self.cfg.ssl_options.get("password"),
                    "ssl_version": self.cfg.ssl_options.get("ssl_version"),
                    "ssl_cert_reqs": self.cfg.ssl_options.get("cert_reqs"),
                    "ssl_ca_certs": self.cfg.ssl_options.get("ca_certs"),
                    "ssl_ciphers": self.cfg.ssl_options.get("ciphers"),
                }
            )

        backlog = self.cfg.settings["backlog"].value
        if backlog:
            config_kwargs["backlog"] = backlog

        config_kwargs.update(self.CONFIG_KWARGS)
        self.config = Config(**config_kwargs)

    def init_signals(self) -> None:
        """Leave Gunicorn's supervisor signals available to the worker loop."""
        for signum in self.SIGNALS:
            signal.signal(signum, signal.SIG_DFL)
        signal.signal(signal.SIGUSR1, self.handle_usr1)
        signal.siginterrupt(signal.SIGUSR1, False)

    def _install_sigquit_handler(self) -> None:
        """Route SIGQUIT through the worker's asyncio loop."""
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGQUIT, self.handle_exit, signal.SIGQUIT, None)

    async def _serve(self) -> None:
        self.config.app = self.wsgi
        server = Server(config=self.config)
        self._install_sigquit_handler()
        await server.serve(sockets=self.sockets)
        if not server.started:
            sys.exit(Arbiter.WORKER_BOOT_ERROR)

    def run(self) -> None:
        """Run the server with the event-loop policy selected by Config."""
        loop_factory = self.config.get_loop_factory()
        if sys.version_info >= (3, 12):
            asyncio.run(self._serve(), loop_factory=loop_factory)
        elif sys.version_info >= (3, 11):
            with asyncio.Runner(debug=False, loop_factory=loop_factory) as runner:
                runner.run(self._serve())
        else:
            _legacy_asyncio_run(self._serve(), loop_factory=loop_factory)

    async def callback_notify(self) -> None:
        """Tell Gunicorn's arbiter that this worker is responsive."""
        self.notify()


class UvicornH11Worker(UvicornWorker):
    """Gunicorn worker using the H11 compatibility selector."""

    CONFIG_KWARGS = {"loop": "asyncio", "http": "h11"}
