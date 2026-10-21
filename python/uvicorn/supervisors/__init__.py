# Copyright (c) 2026 Appunni M
# Part of the Uvicorn-compatible Python process supervisor.
# SPDX-License-Identifier: BSD-3-Clause

"""Process supervision used by the Uvicorn-compatible entry points."""

from typing import TYPE_CHECKING

from .basereload import BaseReload
from .multiprocess import Multiprocess

if TYPE_CHECKING:
    ChangeReload: type[BaseReload]
else:
    try:
        from .watchfilesreload import WatchFilesReload as ChangeReload
    except ImportError:
        from .statreload import StatReload as ChangeReload

__all__ = ["ChangeReload", "Multiprocess"]
