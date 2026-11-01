# Copyright (c) 2026 Appunni M
# Derived from Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import logging
import os
import pickle
import signal
import threading
import time
from multiprocessing import Pipe
from socket import socket

from uvicorn._ansi import style
from uvicorn._shutdown_trace import write_shutdown_trace
from uvicorn._subprocess import get_subprocess, spawn
from uvicorn.config import STARTUP_FAILURE, Config
from uvicorn.server import Server

SIGNALS = {
    getattr(signal, f"SIG{x}"): x
    for x in "INT TERM BREAK HUP QUIT TTIN TTOU USR1 USR2 WINCH".split()
    if hasattr(signal, f"SIG{x}")
}

logger = logging.getLogger("uvicorn.error")

WINDOWS_SHUTDOWN_SIGNAL_ACK_TIMEOUT_SECONDS = 1.0
WINDOWS_SHUTDOWN_SIGNAL_MAX_ATTEMPTS = 2


class Process:
    def __init__(
        self,
        config: Config,
        sockets: list[socket],
    ) -> None:
        self.config = config
        self._server: Server | None = None
        self._windows_shutdown_signal_ack = (
            spawn.Event() if os.name == "nt" else None
        )

        self.parent_conn, self.child_conn = Pipe()
        self.process = get_subprocess(
            config,
            self.target,
            sockets,
            windows_process_group=os.name == "nt",
        )

    def _healthcheck(self, timeout: float) -> bool | None:
        """Receives a timeout and returns the worker's startup flag, or None if it does not answer in time."""
        try:
            self.parent_conn.send(b"ping")
            if self.parent_conn.poll(timeout):
                started: bool = self.parent_conn.recv()
                return started
            return None
        except (OSError, EOFError, pickle.UnpicklingError):
            return None

    def ping(self, timeout: float = 5) -> bool:
        """Receives a timeout and returns True if the worker answers a healthcheck in time."""
        return self._healthcheck(timeout) is not None

    def is_ready(self, timeout: float = 5) -> bool:
        """Receives a timeout and returns True if the worker answers and its server has finished startup."""
        return self._healthcheck(timeout) is True

    def pong(self) -> None:
        """Receives one healthcheck ping and replies with whether the server has finished startup."""
        self.child_conn.recv()
        self.child_conn.send(self.server.started)

    def always_pong(self) -> None:
        while True:
            self.pong()

    def target(self, sockets: list[socket] | None = None) -> None:  # pragma: no cover
        if os.name == "nt":  # pragma: py-not-win32
            # Windows doesn't support SIGTERM, so we use SIGBREAK instead.
            # And then we raise SIGTERM when SIGBREAK is received.
            # https://learn.microsoft.com/zh-cn/cpp/c-runtime-library/reference/signal?view=msvc-170
            def handle_sigbreak(sig: int, _frame) -> None:
                write_shutdown_trace(f"worker-sigbreak.received signal={sig}")
                if self._windows_shutdown_signal_ack is not None:
                    self._windows_shutdown_signal_ack.set()
                signal.raise_signal(signal.SIGTERM)

            signal.signal(  # type: ignore[attr-defined]
                signal.SIGBREAK, handle_sigbreak
            )
            write_shutdown_trace("worker-sigbreak.handler-installed")

        # Each spawned process runs the native server as an ordinary
        # single-worker instance. The parent owns worker supervision.
        self.config.workers = 1
        self.config._worker_mode = True
        threading.Thread(target=self.always_pong, daemon=True).start()
        self.server.run(sockets)
        write_shutdown_trace("worker.server-run.returned")

    def is_alive(self, timeout: float = 5) -> bool:
        if not self.process.is_alive():
            return False  # pragma: full coverage

        return self.ping(timeout)

    def wait_until_ready(self, timeout: float, should_exit: threading.Event | None = None) -> bool:
        """Receives a timeout and returns True if the worker starts serving, or False on exit, shutdown, or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if should_exit is not None and should_exit.is_set():
                return False
            if not self.process.is_alive():
                return False
            if self.is_ready(timeout=1):
                return True
            time.sleep(0.1)
        return False

    def start(self) -> None:
        self.process.start()

    def _begin_termination(self) -> bool:
        if self.process.exitcode is None:  # Process is still running
            assert self.process.pid is not None
            if os.name == "nt":  # pragma: py-not-win32
                signal_ack = self._windows_shutdown_signal_ack
                if signal_ack is not None:
                    signal_ack.clear()
                self._send_windows_shutdown_signal(attempt=1)
            else:
                os.kill(self.process.pid, signal.SIGTERM)
            return True
        return False

    def _send_windows_shutdown_signal(self, *, attempt: int) -> None:
        assert self.process.pid is not None
        write_shutdown_trace(
            f"worker-shutdown.signal-send pid={self.process.pid} attempt={attempt}"
        )
        os.kill(  # type: ignore[attr-defined]
            self.process.pid, signal.CTRL_BREAK_EVENT
        )

    def _wait_for_windows_shutdown_signal(self) -> None:
        signal_ack = self._windows_shutdown_signal_ack
        if os.name != "nt" or signal_ack is None:  # pragma: py-not-win32
            return

        for attempt in range(1, WINDOWS_SHUTDOWN_SIGNAL_MAX_ATTEMPTS + 1):
            if signal_ack.wait(WINDOWS_SHUTDOWN_SIGNAL_ACK_TIMEOUT_SECONDS):
                write_shutdown_trace(
                    f"worker-shutdown.signal-acknowledged "
                    f"pid={self.process.pid} attempt={attempt}"
                )
                return
            if not self.process.is_alive() or signal_ack.is_set():
                return
            write_shutdown_trace(
                f"worker-shutdown.signal-ack-timeout "
                f"pid={self.process.pid} attempt={attempt}"
            )
            if attempt < WINDOWS_SHUTDOWN_SIGNAL_MAX_ATTEMPTS:
                self._send_windows_shutdown_signal(attempt=attempt + 1)

    def _finish_termination(self) -> None:
        logger.info(f"Terminated child process [{self.process.pid}]")
        self.parent_conn.close()
        self.child_conn.close()

    def terminate(self) -> None:
        if self._begin_termination():
            self._wait_for_windows_shutdown_signal()
            self._finish_termination()


    def kill(self) -> None:
        # In Windows, the method will call `TerminateProcess` to kill the process.
        # In Unix, the method will send SIGKILL to the process.
        self.process.kill()
        self.parent_conn.close()
        self.child_conn.close()

    def join(self) -> None:
        logger.info(f"Waiting for child process [{self.process.pid}]")
        write_shutdown_trace(f"worker-join.wait pid={self.process.pid}")
        self.process.join()
        write_shutdown_trace(
            f"worker-join.complete pid={self.process.pid} exitcode={self.process.exitcode}"
        )

    @property
    def server(self) -> Server:
        if self._server is None:
            self._server = Server(config=self.config)
        return self._server

    @property
    def pid(self) -> int | None:
        return self.process.pid

    @property
    def exitcode(self) -> int | None:
        return self.process.exitcode


class Multiprocess:
    def __init__(
        self,
        config: Config,
        sockets: list[socket],
    ) -> None:
        self.config = config
        self.sockets = sockets

        self.processes_num = config.workers
        self.processes: list[Process] = []

        self.should_exit = threading.Event()

        self.signal_queue: list[int] = []
        for sig in SIGNALS:
            signal.signal(sig, lambda sig, frame: self.signal_queue.append(sig))

    def init_processes(self) -> None:
        for _ in range(self.processes_num):
            process = Process(self.config, self.sockets)
            process.start()
            self.processes.append(process)

    def terminate_all(self) -> None:
        write_shutdown_trace("supervisor-terminate-all.start")
        if os.name == "nt":  # pragma: py-not-win32
            pending: list[Process] = []
            # CTRL_BREAK delivery is asynchronous. Signal every process group
            # before waiting for any one worker so a delayed acknowledgement
            # cannot postpone delivery to the remaining workers.
            for process in self.processes:
                write_shutdown_trace(
                    f"supervisor-terminate-all.worker pid={process.pid} "
                    f"exitcode={process.exitcode}"
                )
                if process._begin_termination():
                    pending.append(process)
            for process in pending:
                process._wait_for_windows_shutdown_signal()
                process._finish_termination()
            return

        for process in self.processes:
            write_shutdown_trace(
                f"supervisor-terminate-all.worker pid={process.pid} exitcode={process.exitcode}"
            )
            process.terminate()

    def join_all(self) -> None:
        for process in self.processes:
            process.join()

    def restart_all(self) -> None:
        """Replaces each worker, bringing its replacement into service before retiring the old worker."""
        for idx, old_process in enumerate(self.processes):
            if self.should_exit.is_set():
                return

            new_process = Process(self.config, self.sockets)
            new_process.start()

            if not new_process.wait_until_ready(self.config.timeout_worker_healthcheck, self.should_exit):
                new_process.kill()
                new_process.join()
                if not self.should_exit.is_set():
                    logger.error(
                        f"New child process [{new_process.pid}] was not ready in time; "
                        f"keeping worker [{old_process.pid}] and aborting the restart."
                    )
                return

            old_process.terminate()
            old_process.join()
            self.processes[idx] = new_process

    def run(self) -> None:
        message = f"Started parent process [{os.getpid()}]"
        color_message = "Started parent process [{}]".format(style(str(os.getpid()), fg="cyan", bold=True))
        logger.info(message, extra={"color_message": color_message})

        self.init_processes()

        while not self.should_exit.wait(0.5):
            self.handle_signals()
            self.keep_subprocess_alive()

        self.terminate_all()
        self.join_all()

        message = f"Stopping parent process [{os.getpid()}]"
        color_message = "Stopping parent process [{}]".format(style(str(os.getpid()), fg="cyan", bold=True))
        logger.info(message, extra={"color_message": color_message})
        write_shutdown_trace("supervisor.run.returned")

    def keep_subprocess_alive(self) -> None:
        if self.should_exit.is_set():
            return  # parent process is exiting, no need to keep subprocess alive

        for idx, process in enumerate(self.processes):
            if process.is_alive(timeout=self.config.timeout_worker_healthcheck):
                continue

            process.kill()  # process is hung, kill it
            process.join()

            if process.exitcode == STARTUP_FAILURE:
                # The worker failed before it started serving, so the app, TLS or socket
                # bind is broken and would fail the same way on every restart.
                # See https://github.com/encode/uvicorn/discussions/2440.
                logger.error(f"Child process [{process.pid}] failed to start, stopping the parent process.")
                self.should_exit.set()
                return

            if self.should_exit.is_set():
                return  # pragma: full coverage

            logger.info(f"Child process [{process.pid}] died")
            process = Process(self.config, self.sockets)
            process.start()
            self.processes[idx] = process

    def handle_signals(self) -> None:
        for sig in tuple(self.signal_queue):
            self.signal_queue.remove(sig)
            sig_name = SIGNALS[sig]
            sig_handler = getattr(self, f"handle_{sig_name.lower()}", None)
            if sig_handler is not None:
                sig_handler()
            else:  # pragma: no cover
                logger.debug(f"Received signal {sig_name}, but no handler is defined for it.")

    def handle_int(self) -> None:
        write_shutdown_trace("supervisor-signal.handled signal=SIGINT")
        logger.info("Received SIGINT, exiting.")
        self.should_exit.set()

    def handle_term(self) -> None:
        logger.info("Received SIGTERM, exiting.")
        self.should_exit.set()

    def handle_break(self) -> None:  # pragma: py-not-win32
        write_shutdown_trace("supervisor-signal.handled signal=SIGBREAK")
        logger.info("Received SIGBREAK, exiting.")
        self.should_exit.set()

    def handle_hup(self) -> None:  # pragma: py-win32
        logger.info("Received SIGHUP, restarting processes.")
        self.restart_all()

    def handle_ttin(self) -> None:  # pragma: py-win32
        logger.info("Received SIGTTIN, increasing the number of processes.")
        self.processes_num += 1
        process = Process(self.config, self.sockets)
        process.start()
        self.processes.append(process)

    def handle_ttou(self) -> None:  # pragma: py-win32
        logger.info("Received SIGTTOU, decreasing number of processes.")
        if self.processes_num <= 1:
            logger.info("Already reached one process, cannot decrease the number of processes anymore.")
            return
        self.processes_num -= 1
        process = self.processes.pop()
        process.terminate()
        process.join()
