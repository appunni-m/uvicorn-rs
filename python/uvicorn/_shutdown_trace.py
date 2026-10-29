# Copyright (c) 2026 Appunni M
# SPDX-License-Identifier: BSD-3-Clause

"""Failure-only shutdown tracing shared by the server and worker supervisor."""

from __future__ import annotations

import os
import threading
import time


def write_shutdown_trace(event: str) -> None:
    """Write one process-stamped trace line when shutdown tracing is enabled."""
    if os.environ.get("UVICORN_RS_SHUTDOWN_TRACE") is None:
        return

    line = (
        "uvicorn-rs: shutdown-trace python"
        f" t_ns={time.monotonic_ns()} pid={os.getpid()}"
        f" thread={threading.current_thread().name} {event}\n"
    )
    try:
        os.write(2, line.encode("utf-8", "backslashreplace"))
    except OSError:
        pass
