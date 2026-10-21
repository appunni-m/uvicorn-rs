# Copyright (c) 2026 Appunni M
# Derived from Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Efficient file-system notifications through the optional watchfiles extra."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from socket import socket

from watchfiles import watch

from uvicorn.config import Config

from .basereload import BaseReload


class FileFilter:
    """Apply Uvicorn's include and exclude patterns to changed paths."""

    def __init__(self, config: Config) -> None:
        default_includes = ["*.py"]
        self.includes = [
            pattern for pattern in default_includes if pattern not in config.reload_excludes
        ]
        self.includes.extend(config.reload_includes)
        self.includes = list(set(self.includes))

        default_excludes = [".*", ".py[cod]", ".sw.*", "~*"]
        self.excludes = [
            pattern for pattern in default_excludes if pattern not in config.reload_includes
        ]
        self.exclude_dirs: list[Path] = []
        for pattern in config.reload_excludes:
            path = Path(pattern)
            try:
                is_directory = path.is_dir()
            except OSError:
                is_directory = False
            if is_directory:
                self.exclude_dirs.append(path)
            else:
                self.excludes.append(pattern)
        self.excludes = list(set(self.excludes))

    def __call__(self, path: Path) -> bool:
        for include_pattern in self.includes:
            if path.match(include_pattern):
                if str(path).endswith(include_pattern):
                    return True
                if any(directory in path.parents for directory in self.exclude_dirs):
                    return False
                if any(path.match(pattern) for pattern in self.excludes):
                    return False
                return True
        return False


class WatchFilesReload(BaseReload):
    """Watch configured roots and restart after included file changes."""

    def __init__(
        self,
        config: Config,
        target: Callable[[list[socket] | None], None],
        sockets: list[socket],
    ) -> None:
        super().__init__(config, target, sockets)
        self.reloader_name = "WatchFiles"
        self.watch_filter = FileFilter(config)
        self.watcher = watch(
            *config.reload_dirs,
            watch_filter=None,
            stop_event=self.should_exit,
            yield_on_timeout=True,
            ignore_permission_denied=True,
        )

    def should_restart(self) -> list[Path] | None:
        self.pause()
        changes = next(self.watcher)
        if changes:
            unique_paths = {Path(change[1]) for change in changes}
            return [path for path in unique_paths if self.watch_filter(path)]
        return None
