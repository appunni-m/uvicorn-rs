# Copyright (c) 2026 Appunni M
# Derived from Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Portable polling fallback for Python module reloads."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from socket import socket

from uvicorn.config import Config

from .basereload import BaseReload

logger = logging.getLogger("uvicorn.error")


class StatReload(BaseReload):
    """Detect Python source changes by checking modification times."""

    def __init__(
        self,
        config: Config,
        target: Callable[[list[socket] | None], None],
        sockets: list[socket],
    ) -> None:
        super().__init__(config, target, sockets)
        self.reloader_name = "StatReload"
        self.mtimes: dict[Path, float] = {}
        if config.reload_excludes or config.reload_includes:
            logger.warning(
                "--reload-include and --reload-exclude have no effect unless "
                "watchfiles is installed."
            )

    def should_restart(self) -> list[Path] | None:
        self.pause()
        for file in self.iter_py_files():
            try:
                mtime = file.stat().st_mtime
            except OSError:
                continue
            old_time = self.mtimes.get(file)
            if old_time is None:
                self.mtimes[file] = mtime
            elif mtime > old_time:
                return [file]
        return None

    def restart(self) -> None:
        self.mtimes = {}
        super().restart()

    def iter_py_files(self) -> Iterator[Path]:
        for reload_dir in self.config.reload_dirs:
            yield from (path.resolve() for path in reload_dir.rglob("*.py"))
