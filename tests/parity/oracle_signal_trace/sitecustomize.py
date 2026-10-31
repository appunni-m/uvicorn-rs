"""Opt-in signal receipt tracing for the pinned Windows Uvicorn oracle."""

from __future__ import annotations

import os
import signal
import time


if (
    os.name == "nt"
    and os.environ.get("ASGI_PARITY_TRACE_ORACLE_SIGNAL_ACTIVE") == "1"
):
    _prefix = "uvicorn-rs: shutdown-trace"
    _watched = {
        int(value)
        for value in (
            getattr(signal, "SIGBREAK", None),
            getattr(signal, "SIGTERM", None),
        )
        if value is not None
    }
    _original_signal = signal.signal
    _original_raise_signal = getattr(signal, "raise_signal", None)
    _original_kill = os.kill
    _wrapped_handlers = {}

    def _number(signum: object) -> int | None:
        try:
            return int(signum)
        except (TypeError, ValueError):
            return None

    def _handler_name(handler: object) -> str:
        module = getattr(handler, "__module__", "?")
        name = getattr(
            handler,
            "__qualname__",
            getattr(handler, "__name__", "callable"),
        )
        return f"{module}.{name}"

    def _write(event: str, signum: object, detail: str = "") -> None:
        try:
            number = _number(signum)
            line = (
                f"{_prefix} pid={os.getpid()} t_ns={time.monotonic_ns()} "
                f"ppid={os.getppid()} oracle=1 event={event} signal={number}"
            )
            if detail:
                line += f" {detail}"
            os.write(2, (line + "\n").encode("ascii", errors="backslashreplace"))
        except Exception:
            pass

    def _trace_signal(signum, handler):
        number = _number(signum)
        if number not in _watched or not callable(handler):
            return _original_signal(signum, handler)
        if _wrapped_handlers.get(id(handler)) is handler:
            return _original_signal(signum, handler)

        def traced_handler(received_signal, frame):
            _write(
                "handler-enter",
                received_signal,
                f"handler={_handler_name(handler)}",
            )
            try:
                return handler(received_signal, frame)
            finally:
                _write(
                    "handler-exit",
                    received_signal,
                    f"handler={_handler_name(handler)}",
                )

        _wrapped_handlers[id(traced_handler)] = traced_handler
        _write("handler-install", signum, f"handler={_handler_name(handler)}")
        return _original_signal(signum, traced_handler)

    def _trace_raise_signal(signum):
        if _number(signum) in _watched:
            _write("raise-signal", signum)
        if _original_raise_signal is None:
            raise AttributeError("signal.raise_signal is unavailable")
        return _original_raise_signal(signum)

    def _trace_kill(pid, signum):
        if _number(signum) in _watched:
            _write("kill", signum, f"target_pid={pid}")
        return _original_kill(pid, signum)

    signal.signal = _trace_signal
    if _original_raise_signal is not None:
        signal.raise_signal = _trace_raise_signal
    os.kill = _trace_kill
