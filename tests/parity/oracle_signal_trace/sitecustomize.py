"""Windows oracle shims for worker signal routing and optional signal tracing."""

from __future__ import annotations

import os
import signal
import sys
import time


if os.name == "nt" and os.environ.get("ASGI_PARITY_WINDOWS_WORKER_GROUPS") == "1":
    helper_dir = os.environ.get("ASGI_PARITY_WINDOWS_SPAWN_HELPER_DIR")
    if not helper_dir:
        raise RuntimeError("Windows oracle worker-group shim has no helper directory")
    sys.path.insert(0, helper_dir)
    try:
        import _windows_spawn
        import multiprocessing

        multiprocessing.get_context("spawn").Process = (
            _windows_spawn.WindowsSpawnProcess
        )
    finally:
        sys.path.remove(helper_dir)


if (
    os.name == "nt"
    and os.environ.get("ASGI_PARITY_TRACE_ORACLE_SIGNAL_ACTIVE") == "1"
):
    _prefix = "uvicorn-rs: shutdown-trace"
    _watched = {
        int(value)
        for value in (
            getattr(signal, "SIGINT", None),
            getattr(signal, "SIGBREAK", None),
            getattr(signal, "SIGTERM", None),
        )
        if value is not None
    }
    _control_events = {
        int(getattr(signal, name)): name
        for name in ("CTRL_C_EVENT", "CTRL_BREAK_EVENT")
        if getattr(signal, name, None) is not None
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

    if os.environ.get("ASGI_PARITY_WINDOWS_WORKER_GROUPS") == "1":
        _windows_spawn = sys.modules["_windows_spawn"]
        _original_spawn_popen = _windows_spawn.WindowsSpawnProcess._Popen

        def _trace_spawn(process_obj):
            popen = _original_spawn_popen(process_obj)
            group_flag = int(_windows_spawn._winapi.CREATE_NEW_PROCESS_GROUP)
            _write(
                "worker-spawn",
                getattr(signal, "SIGBREAK", None),
                f"child_pid={popen.pid} group_id={popen.pid} "
                f"creation_flag={group_flag}",
            )
            return popen

        _windows_spawn.WindowsSpawnProcess._Popen = staticmethod(_trace_spawn)

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
        number = _number(signum)
        control_event = _control_events.get(number)
        should_trace = number in _watched or control_event is not None
        detail = f"target_pid={pid}"
        if control_event is not None:
            detail += f" control_event={control_event}"
        if should_trace:
            _write("kill-request", signum, detail)
        try:
            result = _original_kill(pid, signum)
        except BaseException as error:
            if should_trace:
                _write(
                    "kill-error",
                    signum,
                    f"{detail} error={type(error).__name__}:{error}",
                )
            raise
        if should_trace:
            _write("kill-return", signum, detail)
        return result

    def _console_process_snapshot() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_console_process_list = kernel32.GetConsoleProcessList
            get_console_process_list.argtypes = [
                ctypes.POINTER(wintypes.DWORD),
                wintypes.DWORD,
            ]
            get_console_process_list.restype = wintypes.DWORD
            process_ids = (wintypes.DWORD * 128)()
            count = int(get_console_process_list(process_ids, len(process_ids)))
            if count == 0:
                _write(
                    "console-snapshot",
                    signal.SIGINT,
                    f"probe_pid={os.environ.get('ASGI_PARITY_TRACE_PROBE_PID', '?')} "
                    f"winerror={ctypes.get_last_error()}",
                )
                return
            attached_ids = [
                int(process_ids[index]) for index in range(min(count, 128))
            ]
            probe_pid = os.environ.get("ASGI_PARITY_TRACE_PROBE_PID", "?")
            probe_attached = (
                str(probe_pid).isdigit() and int(probe_pid) in attached_ids
            )
            _write(
                "console-snapshot",
                signal.SIGINT,
                f"probe_pid={probe_pid} attached_pids={attached_ids!r} "
                f"probe_attached={probe_attached}",
            )
        except Exception as error:
            _write(
                "console-snapshot-error",
                signal.SIGINT,
                f"error={type(error).__name__}:{error}",
            )

    _console_process_snapshot()

    signal.signal = _trace_signal
    if _original_raise_signal is not None:
        signal.raise_signal = _trace_raise_signal
    os.kill = _trace_kill
