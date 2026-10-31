# Copyright (c) 2026 Appunni M
# Derived from CPython's multiprocessing.popen_spawn_win32 implementation.
# Copyright (c) 2001-2023 Python Software Foundation.
# SPDX-License-Identifier: PSF-2.0
#
# Summary of changes from CPython: create each Uvicorn worker in its own
# Windows process group so CTRL_BREAK_EVENT can reach that worker by PID.

"""Windows multiprocessing support for individually signalable Uvicorn workers."""

from __future__ import annotations

import os
import sys
from multiprocessing.context import SpawnProcess
from multiprocessing import popen_spawn_win32

if os.name != "nt":  # pragma: no cover - imported only by the Windows adapter
    raise ImportError("uvicorn._windows_spawn is only available on Windows")

_winapi = popen_spawn_win32._winapi


class _WorkerPopen(popen_spawn_win32.Popen):
    """Spawn a worker with a process group for its graceful Ctrl+Break stop."""

    def __init__(self, process_obj: SpawnProcess) -> None:
        prep_data = popen_spawn_win32.spawn.get_preparation_data(process_obj._name)
        read_handle, write_handle = _winapi.CreatePipe(None, 0)
        write_fd = popen_spawn_win32.msvcrt.open_osfhandle(write_handle, 0)
        command = popen_spawn_win32.spawn.get_command_line(
            parent_pid=os.getpid(), pipe_handle=read_handle
        )
        python_exe = popen_spawn_win32.spawn.get_executable()

        if popen_spawn_win32.WINENV and popen_spawn_win32._path_eq(
            python_exe, sys.executable
        ):
            python_exe = sys._base_executable
            command[0] = python_exe
            environment = os.environ.copy()
            environment["__PYVENV_LAUNCHER__"] = sys.executable
        else:
            environment = None

        command_line = " ".join(f'"{argument}"' for argument in command)
        if sys.version_info >= (3, 13):
            from subprocess import STARTF_FORCEOFFFEEDBACK, STARTUPINFO

            startup_info = STARTUPINFO(dwFlags=STARTF_FORCEOFFFEEDBACK)
        else:
            startup_info = None

        with open(write_fd, "wb", closefd=True) as child_pipe:
            try:
                process_handle, thread_handle, pid, _thread_id = _winapi.CreateProcess(
                    python_exe,
                    command_line,
                    None,
                    None,
                    False,
                    _winapi.CREATE_NEW_PROCESS_GROUP,
                    environment,
                    None,
                    startup_info,
                )
                _winapi.CloseHandle(thread_handle)
            except BaseException:
                _winapi.CloseHandle(read_handle)
                raise

            self.pid = pid
            self.returncode = None
            self._handle = process_handle
            self.sentinel = int(process_handle)
            self.finalizer = popen_spawn_win32.util.Finalize(
                self,
                popen_spawn_win32._close_handles,
                (self.sentinel, int(read_handle)),
            )

            popen_spawn_win32.set_spawning_popen(self)
            try:
                popen_spawn_win32.reduction.dump(prep_data, child_pipe)
                popen_spawn_win32.reduction.dump(process_obj, child_pipe)
            finally:
                popen_spawn_win32.set_spawning_popen(None)


class WindowsSpawnProcess(SpawnProcess):
    """Multiprocessing spawn process whose PID is also its Ctrl+Break group ID."""

    @staticmethod
    def _Popen(process_obj: SpawnProcess) -> _WorkerPopen:
        return _WorkerPopen(process_obj)
