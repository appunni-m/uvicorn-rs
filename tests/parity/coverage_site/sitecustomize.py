"""Keep coverage-only server shutdowns on normal process exit paths."""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import sys


if os.environ.get("ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN") == "1":
    from uvicorn.server import Server

    _original_handle_exit = Server.handle_exit

    def _handle_exit_without_signal_reraise(self, signum, frame):
        captured_signals = self._captured_signals
        captured_count = len(captured_signals)
        _original_handle_exit(self, signum, frame)
        del captured_signals[captured_count:]

    Server.handle_exit = _handle_exit_without_signal_reraise

    _runtime_marker_dir = os.environ.get("ASGI_PARITY_COVERAGE_RUNTIME_MARKER_DIR")
    if _runtime_marker_dir:
        def _record_runtime_import() -> None:
            marker_dir = Path(_runtime_marker_dir)
            marker_dir.mkdir(parents=True, exist_ok=True)
            marker = marker_dir / f"{os.getpid()}.json"
            temporary_marker = marker.with_suffix(".json.tmp")
            temporary_marker.write_text(
                json.dumps({
                    "pid": os.getpid(),
                    "rust_native_module_loaded": "uvicorn_rs._native" in sys.modules,
                }, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary_marker.replace(marker)

        atexit.register(_record_runtime_import)
