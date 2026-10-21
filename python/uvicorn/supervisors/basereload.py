# Copyright (c) 2026 Appunni M
# Derived from Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Parent-process lifecycle shared by file reload strategies."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from socket import socket
from types import FrameType

from uvicorn._ansi import style
from uvicorn._subprocess import get_subprocess
from uvicorn.config import Config

HANDLED_SIGNALS = (signal.SIGINT, signal.SIGTERM)
logger = logging.getLogger("uvicorn.error")


class BaseReload:
    """Run one server child and replace it when the watcher finds changes."""

    def __init__(
        self,
        config: Config,
        target: Callable[[list[socket] | None], None],
        sockets: list[socket],
    ) -> None:
        self.config = config
        self.target = target
        self.sockets = sockets
        self.should_exit = threading.Event()
        self.pid = os.getpid()
        self.is_restarting = False
        self.reloader_name: str | None = None

    def signal_handler(self, sig: int, frame: FrameType | None) -> None:
        """Stop the supervisor when the parent receives a termination signal."""
        del sig, frame
        if sys.platform == "win32" and self.is_restarting:
            self.is_restarting = False
        else:
            self.should_exit.set()

    def run(self) -> None:
        """Start the server child, handle changes, and shut down cleanly."""
        self.startup()
        try:
            for changes in self:
                if changes:
                    logger.warning(
                        "%s detected changes in %s. Reloading...",
                        self.reloader_name,
                        ", ".join(map(_display_path, changes)),
                    )
                    self.restart()
        finally:
            self.shutdown()

    def pause(self) -> None:
        """Wait for the configured reload interval or stop request."""
        if self.should_exit.wait(self.config.reload_delay):
            raise StopIteration

    def __iter__(self) -> Iterator[list[Path] | None]:
        return self

    def __next__(self) -> list[Path] | None:
        return self.should_restart()

    def startup(self) -> None:
        """Install parent signal handlers and start the first server child."""
        message = f"Started reloader process [{self.pid}] using {self.reloader_name}"
        color_message = "Started reloader process [{}] using {}".format(
            style(str(self.pid), fg="cyan", bold=True),
            style(str(self.reloader_name), fg="cyan", bold=True),
        )
        logger.info(message, extra={"color_message": color_message})
        for sig in HANDLED_SIGNALS:
            signal.signal(sig, self.signal_handler)
        self.process = get_subprocess(
            config=self.config, target=self.target, sockets=self.sockets
        )
        self.process.start()

    def restart(self) -> None:
        """Replace the serving child while keeping the parent listener open."""
        if sys.platform == "win32":
            self.is_restarting = True
            assert self.process.pid is not None
            os.kill(self.process.pid, signal.CTRL_C_EVENT)
            sys.stdout.write(" ")
            sys.stdout.flush()
        else:
            self.process.terminate()
        self.process.join()
        self.process = get_subprocess(
            config=self.config, target=self.target, sockets=self.sockets
        )
        self.process.start()

    def shutdown(self) -> None:
        """Stop the active child and close the listener owned by the parent."""
        process = getattr(self, "process", None)
        if sys.platform == "win32":
            self.should_exit.set()
        elif process is not None:
            process.terminate()
        if process is not None:
            process.join()
        for sock in self.sockets:
            sock.close()
        color_message = "Stopping reloader process [{}]".format(
            style(str(self.pid), fg="cyan", bold=True)
        )
        logger.info(
            "Stopping reloader process [%s]", self.pid,
            extra={"color_message": color_message},
        )

    def should_restart(self) -> list[Path] | None:
        """Return changed paths; subclasses provide the watch strategy."""
        raise NotImplementedError("Reload strategies must implement should_restart()")


def _display_path(path: Path) -> str:
    try:
        return f"'{path.relative_to(Path.cwd())}'"
    except ValueError:
        return f"'{path}'"
