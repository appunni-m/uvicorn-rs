#!/usr/bin/env python3
"""Execute input-only black-box workflows against a reference and uvicorn-rs."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import http.client
import importlib
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path
import platform
import re
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

import psutil
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import DataReceived, ResponseReceived, StreamEnded, StreamReset
from h2.errors import ErrorCodes
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus
from websockets.sync.client import connect as websocket_connect


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "parity"
MANIFEST_PATH = FIXTURES / "manifest.json"
APP = "tests.parity.app:app"
MANIFEST_SCHEMA = "uvicorn-rs-parity/manifest@2"
INPUT_SCHEMA = "uvicorn-rs-parity/input@7"
RESULT_SCHEMA = "uvicorn-rs-parity/result@4"
# These messages authorize one deliberately injected panic per attempted
# coverage fault case. They never authorize ordinary target/reference panics
# or a failing process exit. The hook event, not a repeated JoinError log,
# supplies the evidence that the injected native task actually panicked.
COVERAGE_PANIC_MESSAGES = {
    "http.app-task.panic-before-response-start": "coverage-injected ASGI request task panic",
    "python.task-future.panic-after-completion": "coverage-injected ASGI app task panic after final response body",
    "websocket.handshake.mutex.poison": "coverage-injected WebSocket handshake mutex poison",
    "http3.connection-task.panic": "coverage-injected HTTP/3 connection task panic",
    "http3.connection-task.panic-during-shutdown": "coverage-injected HTTP/3 connection task panic during shutdown",
    "http3.request-task.panic": "coverage-injected HTTP/3 request task panic",
    "http3.request-task.panic-after-response": "coverage-injected HTTP/3 request task panic after response",
    "websocket.app-task.panic-before-handshake": "coverage-injected WebSocket application task panic",
    "server.websocket-task.shutdown-panic": "coverage-injected WebSocket session task panic during shutdown",
}
RUST_PANIC_HEADER = re.compile(
    r"^thread '[^'\n]*'(?: \([0-9]+\))? panicked at "
    r"(?P<source>.+):[0-9]+:[0-9]+:$"
)
FAULT_POINTS = {
    "python.task-future.defer-task-transfer",
    "python.task-cancel.cancel.getattr",
    "python.task-cancel.context.set-item",
    "python.task-cancel.schedule-call",
    "http.receive.disconnected-before-future-poll",
    "http.body-pump.send.connection-closed",
    "http.body-pump.first-poll-pause",
    "http.body-pump.final-send.connection-closed",
    "http.body-pump.after-final.connection-closed",
    "http.body-pump.drain.server-stop-wait",
    "http.body-pump.drain.terminal-frame",
    "http.body-pump.error.request-stop",
    "http.body-pump.reap.cancelled-task",
    "http.body-pump.shutdown.cancel-join",
    "http.body-pump.shutdown.hang",
    "http.body-pump.shutdown.complete-task-before-abort",
    "server.connection-io.eof-recheck.pause",
    "python.asgi-receive.borrow-conflict",
    "server.control.shutdown.borrow-conflict",
    "server.serve.control.borrow-conflict",
    "server.graceful-timeout.overflow",
    "server.python-locals.get-current",
    "python.task-completion.allocate",
    "http.request.empty-body.channel-closed",
    "websocket.app-task.panic-before-handshake",
    "server.quic-tls.config-error",
    "native.module.wrap-function.serve",
    "native.runtime.build.error",
    "server.websocket-task.shutdown-panic",
    "server.connection-task.shutdown-hang",
    "http3.request-task.panic",
    "http3.request-task.panic-after-response",
    "http3.connection.accept-finished",
    "http3.body-pump.send.connection-closed",
    "http3.body-pump.error.request-stop",

    "asgi.event-type.http-response-start.eq",
    "asgi.event-type.http-response-body.eq",
    "asgi.event-type.websocket-accept.eq",
    "asgi.event-type.websocket-close.eq",
    "asgi.event-type.websocket-send.eq",
    "asgi.event-type.lifespan-startup-complete.eq",
    "asgi.event-type.lifespan-startup-failed.eq",
    "asgi.event-type.lifespan-shutdown-complete.eq",
    "asgi.event-type.lifespan-shutdown-failed.eq",
    "asgi.event-type.extract",
    "http.asgi.send.type.get-item",
    "http.response.start.status.get-item",
    "http.response.start.status.extract",
    "http.response.start.headers.get-item",
    "http.response.start.headers.extract",
    "http.response.body.body.get-item",
    "http.response.body.body.extract",
    "http.response.body.more-body.get-item",
    "http.response.body.more-body.extract",
    "http.response.start.channel-closed",
    "http.response.body.channel-closed",
    "http.response.body-consumer.pause",
    "http.response.body-poll.receiver-pending.pause",
    "http.app-task.panic-before-response-start",
    "websocket.asgi.send.type.get-item",
    "websocket.accept.subprotocol.get-item",
    "websocket.accept.subprotocol.extract",
    "websocket.accept.headers.get-item",
    "websocket.accept.headers.extract",
    "websocket.close.code.get-item",
    "websocket.close.code.extract",
    "websocket.close.reason.get-item",
    "websocket.close.reason.extract",
    "websocket.send.text.get-item",
    "websocket.send.text.extract",
    "websocket.send.bytes.get-item",
    "websocket.send.bytes.extract",
    "lifespan.asgi.send.type.get-item",
    "lifespan.startup.failed.message.get-item",
    "lifespan.startup.failed.message.extract",
    "lifespan.shutdown.failed.message.get-item",
    "lifespan.shutdown.failed.message.extract",
    "lifespan.send.event-channel-closed",
    "native.module.add-class.asgi-io",
    "native.module.add-class.websocket-io",
    "native.module.add-class.lifespan-io",
    "native.module.add-class.server-control",
    "native.module.add-function.serve",
    "python.task-starter.import-asyncio",
    "python.task-starter.prelude-close-error",
    "python.task-starter.ensure-future",
    "python.task-starter.add-done-callback",
    "python.task-starter.inline-completion",
    "python.task-starter.inline-completion-registration-error",
    "python.task-starter.inline-completion.borrow-conflict",
    "python.task-starter.registration-error.borrow-conflict",
    "python.task-starter.registration-success.borrow-conflict",
    "python.task-starter.failure-cleanup.schedule-error",
    "python.task-starter.task-sender-missing",
    "python.task-future.task-receiver-closed",
    "python.task-future.starter-allocation",
    "python.task-future.context.set-item",
    "python.task-future.schedule-call",
    "python.task-future.panic-after-completion",
    "python.task-completion.result-receiver-closed",
    "scope.http.asgi.version.set-item",
    "scope.http.asgi.spec-version.set-item",
    "scope.http.type.set-item",
    "scope.http.asgi.set-item",
    "scope.http.http-version.set-item",
    "scope.http.method.set-item",
    "scope.http.scheme.set-item",
    "scope.http.path.set-item",
    "scope.http.raw-path.set-item",
    "scope.http.query-string.set-item",
    "scope.http.root-path.set-item",
    "scope.http.headers.append",
    "scope.http.headers.set-item",
    "scope.http.client.set-item",
    "scope.http.server.set-item",
    "scope.state.copy",
    "scope.state.set-item",
    "request.http.type.set-item",
    "request.http.body.set-item",
    "request.http.more-body.set-item",
    "request.http.disconnect.type.set-item",
    "http.receive.immediate-disconnect-message-error",
    "http.receive.lock-contention",
    "server.connection-task.service-error",
    "server.connection-task.join-error",
    "server.connection-task.service-await-error",
    "server.connection-task.join-await-error",
    "server.connection-task.service-select-result",
    "server.connection-task.join-select-result",
    "server.connection-task.service-error-during-shutdown",
    "server.connection-task.join-error-during-shutdown",
    "server.connection-io.poll-write-error",
    "http.asgi-io.allocate",
    "http.asgi.app-invoke",
    "server.listener.accept-error",
    "server.listener.local-addr-error",
    "server.http3-endpoint.bind-error",
    "server.http3-task.shutdown-hang",
    "server.websocket-task.shutdown-hang",
    "lifespan.io.allocate",
    "lifespan.app-invoke",
    "websocket.io.allocate",
    "websocket.app-invoke",
    "http3.connection-task.panic",
    "http3.endpoint.accept-closed",
    "http3.connection-task.panic-during-shutdown",
    "http3.connection-task.shutdown-hang",
    "http3.connection.create-error",
    "http3.connection.accept-error",
    "http3.peer-close.unexpected-error-kind",
    "http3.peer-close.close-reason-unavailable",
    "http3.request.resolve-error",
    "http3.response.builder-error",
    "http3.response.send-error",
    "http3.response.body-frame-error",
    "http3.response.non-data-frame",
    "http3.response.body-send-error",
    "http3.response.finish-error",
    "http3.body-pump.connection-closed",
    "http3.body-pump.connection-closed-select",
    "http3.body-pump.sender-closed-select",
    "http3.body-pump.final-message-connection-closed-select",
    "http3.body-pump.empty-data-frame",
    "http3.body-pump.send-error",
    "websocket.handshake.mutex.poison",
    "websocket.accept-key.header-value-error",
    "websocket.handshake.already-completed",
    "websocket.handshake.send-closed",
    "websocket.outgoing.channel-closed-on-send",
    "websocket.outgoing.queue-receiver-closed",
    "http.response.task-wins-start-select",
    "lifespan.scope.asgi.version.set-item",
    "lifespan.scope.asgi.spec-version.set-item",
    "lifespan.scope.type.set-item",
    "lifespan.scope.asgi.set-item",
    "lifespan.scope.state.set-item",
    "lifespan.receive.startup.type.set-item",
    "lifespan.receive.shutdown.type.set-item",
    "lifespan.shutdown.force-timeout",
    "lifespan.startup.event-channel-closed",
    "lifespan.startup.task-join-error",
    "lifespan.startup.send-closed",
    "lifespan.receive.channel-closed",
    "lifespan.shutdown.task-join-error",
    "lifespan.shutdown.task-join-after-complete",
    "scope.websocket.asgi.version.set-item",
    "scope.websocket.asgi.spec-version.set-item",
    "scope.websocket.type.set-item",
    "scope.websocket.asgi.set-item",
    "scope.websocket.http-version.set-item",
    "scope.websocket.method.set-item",
    "scope.websocket.scheme.set-item",
    "scope.websocket.path.set-item",
    "scope.websocket.raw-path.set-item",
    "scope.websocket.query-string.set-item",
    "scope.websocket.root-path.set-item",
    "scope.websocket.headers.append",
    "scope.websocket.headers.set-item",
    "scope.websocket.subprotocols.set-item",
    "scope.websocket.client.set-item",
    "scope.websocket.server.set-item",
    "websocket.receive.connect-type.set-item",
    "websocket.receive.text-type.set-item",
    "websocket.receive.text-value.set-item",
    "websocket.receive.binary-type.set-item",
    "websocket.receive.binary-value.set-item",
    "websocket.receive.disconnect-type.set-item",
    "websocket.receive.disconnect-code.set-item",
    "websocket.receive.disconnect-reason.set-item",
    "websocket.receive.closed-type.set-item",
    "websocket.receive.closed-code.set-item",
    "websocket.receive.closed-reason.set-item",
    "websocket.receive.channel-closed",
    "websocket.receive.connection-closed",
    "websocket.driver.connection-closed",
    "websocket.driver.peer-eof",
    "websocket.driver.app-task-aborted",
    "websocket.driver.incoming-text-receiver-closed",
    "websocket.driver.incoming-binary-receiver-closed",
    "websocket.driver.outgoing-channel-closed",
    "websocket.driver.send-error",
    "websocket.driver.drain-send-error",
}
PUBLIC_INPUT_CONTRACT_POINTS = {
    "public.http-response-header-capacity",
    "public.websocket-accept-header-capacity",
}
ASGI_SCOPE_SUPPORT_CONTRACT_POINTS = {"public.asgi-spec-version"}
# These selectors describe real protocol/application input. They are never
# native injection points and must not arm the coverage fault control.
HARNESS_FAULT_POINTS = (
    {"http3.client.abort-after-body"}
    | PUBLIC_INPUT_CONTRACT_POINTS
    | ASGI_SCOPE_SUPPORT_CONTRACT_POINTS
)
PYTHON_TASK_START_ERRORS = {
    "python.task-starter.import-asyncio": "MemoryError: coverage-only injected MemoryError at PythonTaskStarterImportAsyncio",
    "python.task-starter.ensure-future": "MemoryError: coverage-only injected MemoryError at PythonTaskStarterEnsureFuture",
    "python.task-completion.allocate": "MemoryError: coverage-only injected MemoryError at PythonTaskCompletionAllocate",
    "python.task-starter.prelude-close-error": "RuntimeError: coverage-injected task setup failure before bridge coroutine close",
}
PYTHON_TASK_START_CLEANUP_ERRORS = {
    "python.task-starter.prelude-close-error": "RuntimeError: coverage-injected bridge coroutine close failure",
}
EAGER_APPLICATION_CLEANUP_CONTRACTS = {
    "server-eager-application-registration-cleanup",
    "server-eager-application-registration-cleanup-normal-return",
}
EAGER_LIFESPAN_CLEANUP_CONTRACTS = {
    "server-eager-lifespan-registration-cleanup",
    "server-eager-lifespan-registration-cleanup-timeout",
}
EAGER_REGISTRATION_CLEANUP_CONTRACTS = (
    EAGER_APPLICATION_CLEANUP_CONTRACTS | EAGER_LIFESPAN_CLEANUP_CONTRACTS
)
FAULT_CONTRACTS = {
    "asgi-spec-version-2.5",
    "http-response-reset-cancels-deferred-task",
    "server-cancellation-schedule-error-bounded-shutdown",
    "http-read-eof-recheck-completes",
    "http-500-then-followup-200",
    "http-callback-error-followup-200",
    "http-original-task-start-error-followup-200",
    "http-callback-error-cleans-task-followup-200",
    "server-forced-task-completion-error-bounded-shutdown",
    "server-eager-lifespan-registration-cleanup",
    "server-eager-lifespan-registration-cleanup-timeout",
    "server-eager-application-registration-cleanup",
    "server-eager-application-registration-cleanup-normal-return",
    "http-reset-before-body-worker-disconnect-followup-200",
    "http-body-pump-drain-shutdown-joined",
    "http-body-pump-drain-terminal-frame",
    "http-body-pump-error-stop-disconnect-followup-200",
    "http-body-pump-reaps-cancelled-task",
    "http-body-pump-shutdown-cancelled-join",
    "http-body-pump-shutdown-aborts-hung-pump",
    "http-body-pump-shutdown-completes-task-before-abort",
    "http-response-header-capacity-recovery-followup-200",
    "websocket-header-capacity-error-followup-200",
    "http-start-error-close-followup-200",
    "http-response-body-error-followup-200",
    "http-response-backpressure-body-preserved-followup-200",
    "http-incomplete-body-preserves-emitted-chunk-after-consumer-pause",
    "http-response-body-queued-after-receiver-pending",
    "http3-500-error-body",
    "http3-connection-task-error-followup-200",
    "http3-connection-error-cancels-held-response-followup-200",
    "http3-peer-close-classification-defensive-error",
    "http3-stream-reset-on-runtime-error",
    "http3-request-task-error-before-peer-close-followup-200",
    "http3-body-pump-early-exit-500",
    "http3-upload-body-pump-preserves-data",
    "http3-upload-body-pump-send-error-disconnect",
    "http3-upload-body-pump-completes-final-message",
    "http3-connection-task-shutdown-error",
    "http3-connection-task-shutdown-hang-aborted",
    "http3-endpoint-accept-closes-http3",
    "http2-500-empty-body",
    "http3-client-abort-disconnect-followup",
    "http3-body-pump-error-stop-disconnect-followup-200",
    "http3-body-pump-reaps-cancelled-task",
    "http3-server-shutdown-force-abort",
    "http-final-body-preserved-after-app-task-panic",
    "http-task-panic-before-final-body-closes-stream",
    "http-start-and-final-body-preserved-after-task-wins-select",
    "http-connection-task-error-followup-200",
    "http-connection-task-write-error-followup-200",
    "http-concurrent-receive-after-lock-contention",
    "http-task-completion-error-followup-200",
    "http-start-response-preserved-followup-200",
    "http-disconnect-error-followup-200",
    "http-immediate-disconnect-message-error-followup-200",
    "server-startup-failure",
    "server-lifespan-startup-auto-fallback",
    "server-shutdown-failure",
    "server-lifespan-task-cancel",
    "server-connection-task-error-during-shutdown",
    "server-connection-task-shutdown-timeout-abort",
    "server-hyper-connection-error-during-shutdown",
    "websocket-server-shutdown-force-abort",
    "websocket-driver-send-error-followup-200",
    "websocket-driver-send-error-cancels-app",
    "websocket-handshake-error-followup-200",
    "websocket-teardown-and-followup-200",
}
WEBSOCKET_FAULT_POINTS = {
    "asgi.event-type.websocket-send.eq",
    "asgi.event-type.websocket-close.eq",
    "websocket.close.code.get-item",
    "websocket.close.code.extract",
    "websocket.close.reason.get-item",
    "websocket.close.reason.extract",
    "websocket.send.text.get-item",
    "websocket.send.text.extract",
    "websocket.send.bytes.get-item",
    "websocket.send.bytes.extract",
    "websocket.receive.channel-closed",
    "websocket.receive.connection-closed",
    "websocket.driver.connection-closed",
    "websocket.driver.peer-eof",
    "websocket.driver.app-task-aborted",
    "websocket.driver.incoming-text-receiver-closed",
    "websocket.driver.incoming-binary-receiver-closed",
    "websocket.driver.outgoing-channel-closed",
    "websocket.driver.send-error",
    "websocket.outgoing.channel-closed-on-send",
    "websocket.outgoing.queue-receiver-closed",
    "websocket.receive.text-type.set-item",
    "websocket.receive.text-value.set-item",
    "websocket.receive.binary-type.set-item",
    "websocket.receive.binary-value.set-item",
    "websocket.receive.disconnect-type.set-item",
    "websocket.receive.disconnect-code.set-item",
    "websocket.receive.disconnect-reason.set-item",
    "websocket.receive.closed-type.set-item",
    "websocket.receive.closed-code.set-item",
    "websocket.receive.closed-reason.set-item",
}
WEBSOCKET_HANDSHAKE_FAULT_POINTS = {
    "python.asgi-receive.borrow-conflict",
    "websocket.app-task.panic-before-handshake",
    "websocket.receive.connect-type.set-item",
    "asgi.event-type.websocket-accept.eq",
    "asgi.event-type.websocket-close.eq",
    "websocket.asgi.send.type.get-item",
    "websocket.accept.subprotocol.get-item",
    "websocket.accept.subprotocol.extract",
    "websocket.accept.headers.get-item",
    "websocket.accept.headers.extract",
    "websocket.handshake.mutex.poison",
    "websocket.handshake.already-completed",
    "websocket.handshake.send-closed",
    "websocket.io.allocate",
    "websocket.app-invoke",
    "websocket.accept-key.header-value-error",
}
LIFESPAN_STARTUP_AUTO_FALLBACK_FAULT_POINTS = {
    "lifespan.receive.channel-closed",
    "lifespan.startup.event-channel-closed",
    "lifespan.receive.startup.type.set-item",
    "asgi.event-type.lifespan-startup-complete.eq",
    "asgi.event-type.lifespan-startup-failed.eq",
    "lifespan.asgi.send.type.get-item",
    "lifespan.startup.failed.message.get-item",
    "lifespan.startup.failed.message.extract",
    "lifespan.send.event-channel-closed",
}
LIFESPAN_SHUTDOWN_FAILURE_FAULT_POINTS = {
    "lifespan.shutdown.task-join-error",
    "lifespan.shutdown.task-join-after-complete",
    "lifespan.receive.shutdown.type.set-item",
    "asgi.event-type.lifespan-shutdown-complete.eq",
    "asgi.event-type.lifespan-shutdown-failed.eq",
    "lifespan.asgi.send.type.get-item",
    "lifespan.shutdown.failed.message.get-item",
    "lifespan.shutdown.failed.message.extract",
}
LIFESPAN_TASK_CANCEL_FAULT_POINTS = {
    "lifespan.shutdown.force-timeout",
}
HTTP_RESPONSE_BODY_FAULT_POINTS = {
    "asgi.event-type.http-response-body.eq",
    "http.response.body.body.get-item",
    "http.response.body.body.extract",
    "http.response.body.more-body.get-item",
    "http.response.body.more-body.extract",
    "http.response.body.channel-closed",
}
HTTP_RESPONSE_BODY_BACKPRESSURE_FAULT_POINTS = {
    "http.response.body-consumer.pause",
}
HTTP_RESPONSE_START_ERROR_FAULT_POINTS = {
    "http.response.start.status.get-item",
    "http.response.start.status.extract",
    "http.response.start.headers.get-item",
    "http.response.start.headers.extract",
    "http.response.start.channel-closed",
}


class ParityError(RuntimeError):
    """Invalid parity contract or failed adapter infrastructure."""


class ProcessResourceSampler:
    """Sample one server process while a synchronized load case is active."""

    def __init__(self, pid: int) -> None:
        self.process = psutil.Process(pid)
        self.stop_event = threading.Event()
        self.samples: list[tuple[int, int]] = []
        self.thread = threading.Thread(
            target=self._sample_until_stopped,
            name="parity-resource-sampler",
            daemon=True,
        )

    def sample(self) -> tuple[int, int]:
        try:
            with self.process.oneshot():
                sample = (self.process.memory_info().rss, self.process.num_threads())
        except psutil.Error as error:
            raise ParityError(f"could not sample server resources: {error}") from error
        self.samples.append(sample)
        return sample

    def _sample_until_stopped(self) -> None:
        while not self.stop_event.wait(0.005):
            try:
                self.sample()
            except ParityError:
                return

    def start(self) -> None:
        self.sample()
        self.thread.start()

    def finish(self) -> dict[str, int]:
        self.stop_event.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive() or not self.samples:
            raise ParityError("server resource sampler did not stop cleanly")
        self.sample()
        return {
            "rss_before_bytes": self.samples[0][0],
            "rss_peak_bytes": max(sample[0] for sample in self.samples),
            "rss_after_bytes": self.samples[-1][0],
            "threads_peak": max(sample[1] for sample in self.samples),
            "sample_count": len(self.samples),
        }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def exact_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    actual = set(value)
    if actual != required:
        raise ParityError(
            f"{label} fields differ: missing={sorted(required - actual)}, "
            f"unknown={sorted(actual - required)}"
        )


def exact_case_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    """Allow versioned case-verification metadata in addition to one stimulus."""
    metadata = {"verification", "fault"} & set(value)
    exact_keys(value, required | metadata, label)


def validate_load_input(case: dict[str, Any], kind: str) -> None:
    load = case.get("load")
    if not isinstance(load, dict):
        raise ParityError(f"{case['case_id']}: load workflow requires a load object")
    if kind == "websocket":
        keys = {
            "key", "rounds", "concurrency", "pause_before_read_ms",
            "messages_per_session", "message_bytes",
        }
    else:
        keys = {
            "key", "rounds", "concurrency", "pause_before_read_ms",
            "chunks", "chunk_bytes",
        }
    exact_keys(load, keys, f"{case['case_id']}.load")
    if (
        not isinstance(load["key"], str)
        or not load["key"]
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in load["key"])
    ):
        raise ParityError(f"{case['case_id']}: load key must use ASCII letters, digits, '_' or '-'")
    if type(load["rounds"]) is not int or not 3 <= load["rounds"] <= 8:
        raise ParityError(f"{case['case_id']}: load rounds must be between 3 and 8")
    if type(load["concurrency"]) is not int or not 2 <= load["concurrency"] <= 64:
        raise ParityError(f"{case['case_id']}: load concurrency must be between 2 and 64")
    if (
        type(load["pause_before_read_ms"]) is not int
        or not 0 <= load["pause_before_read_ms"] <= 5000
    ):
        raise ParityError(f"{case['case_id']}: pause_before_read_ms must be between 0 and 5000")
    if kind == "websocket":
        if (
            type(load["messages_per_session"]) is not int
            or not 1 <= load["messages_per_session"] <= 32
            or type(load["message_bytes"]) is not int
            or not 1 <= load["message_bytes"] <= 4096
        ):
            raise ParityError(f"{case['case_id']}: WebSocket load message size/count is outside its bounds")
        if (
            case.get("profile") not in {"websocket", "websocket-tls"}
            or case.get("operation") != "websocket.concurrent-session-load"
        ):
            raise ParityError(f"{case['case_id']}: WebSocket load profile and operation do not match")
        return
    if (
        type(load["chunks"]) is not int
        or not 16 <= load["chunks"] <= 64
        or type(load["chunk_bytes"]) is not int
        or not 1024 <= load["chunk_bytes"] <= 4096
    ):
        raise ParityError(f"{case['case_id']}: HTTP load chunk size/count is outside its bounds")
    expected = {
        "http1": "http.concurrent-connections",
        "http2": "http.concurrent-stream-load",
        "http3": "http3.concurrent-stream-load",
    }
    if case.get("profile") not in expected or case.get("operation") != expected[case["profile"]]:
        raise ParityError(f"{case['case_id']}: HTTP load profile and operation do not match")


def load_contract(
    manifest_path: Path = MANIFEST_PATH,
    fixture_root: Path = FIXTURES,
) -> tuple[dict[str, Any], dict[str, Any], list[Path]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exact_keys(
        manifest,
        {
            "schema", "scope", "oracles", "target", "profiles", "operations",
            "inputs", "result_schema", "normalization",
        },
        "manifest",
    )
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ParityError(f"unsupported manifest schema: {manifest['schema']!r}")
    if manifest["result_schema"] != RESULT_SCHEMA:
        raise ParityError("manifest result schema is unsupported")
    if not isinstance(manifest["inputs"], list) or not manifest["inputs"]:
        raise ParityError("manifest.inputs must be a non-empty path list")
    if any(not isinstance(item, str) or not item for item in manifest["inputs"]):
        raise ParityError("manifest.inputs must contain non-empty relative paths")
    if len(manifest["inputs"]) != len(set(manifest["inputs"])):
        raise ParityError("manifest.inputs contains duplicate paths")
    indexed_paths = []
    for relative in manifest["inputs"]:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or not relative.startswith("inputs/"):
            raise ParityError(f"manifest input path must stay beneath inputs/: {relative!r}")
        indexed_paths.append(fixture_root / candidate)
    discovered_paths = sorted((fixture_root / "inputs").rglob("*.json"))
    if sorted(indexed_paths) != discovered_paths:
        missing = sorted(str(path.relative_to(fixture_root)) for path in set(discovered_paths) - set(indexed_paths))
        stale = sorted(str(path.relative_to(fixture_root)) for path in set(indexed_paths) - set(discovered_paths))
        raise ParityError(f"manifest input index differs from files: unindexed={missing}, missing={stale}")
    exact_keys(manifest["scope"], {"id", "mode", "authority", "description"}, "manifest.scope")
    exact_keys(manifest["target"], {"id", "name", "revision", "runtime", "protocols"}, "manifest.target")
    if manifest["target"]["id"] != "uvicorn-rs":
        raise ParityError("manifest target identity must be uvicorn-rs")
    oracle_ids: set[str] = set()
    for oracle in manifest["oracles"]:
        exact_keys(oracle, {"id", "name", "version", "runtime", "protocols", "components"}, "manifest oracle")
        if not isinstance(oracle["id"], str) or not oracle["id"] or oracle["id"] in oracle_ids:
            raise ParityError(f"missing or duplicate oracle ID: {oracle['id']!r}")
        oracle_ids.add(oracle["id"])
        if not isinstance(oracle["protocols"], list) or not oracle["protocols"]:
            raise ParityError(f"{oracle['id']}: protocols must be a non-empty array")
        component_ids = set()
        for component in oracle["components"]:
            exact_keys(component, {"id", "version"}, f"{oracle['id']} oracle component")
            if not isinstance(component["id"], str) or not component["id"] or component["id"] in component_ids:
                raise ParityError(f"{oracle['id']}: missing or duplicate component ID")
            if not isinstance(component["version"], str) or not component["version"]:
                raise ParityError(f"{oracle['id']}/{component['id']}: component version is required")
            component_ids.add(component["id"])
    for profile in manifest["profiles"]:
        exact_keys(profile, {"id", "oracle", "protocol", "oracle_config"}, "manifest profile")
    if len({profile["id"] for profile in manifest["profiles"]}) != len(manifest["profiles"]):
        raise ParityError("duplicate profile ID")
    observation_fields = {
        "status", "content_type", "body_bytes", "ordered_body_bytes", "early_body_bytes",
        "ordered_response_headers", "response_header_values_by_name",
        "streamed_before_completion", "disconnect_event", "followup_response",
        "handshake_status", "handshake_established", "subprotocol", "ordered_messages", "state_response",
        "ordered_message_payload_bytes", "last_ordered_message",
        "process_terminated", "process_exit_code", "application_events", "close_code", "close_reason",
        "connection_closed", "listener_closed_before_release", "idle_connection_closed",
        "startup_failed", "startup_error_observed", "responses", "pong_received",
        "resource_rounds", "resource_stable", "task_count_stable",
        "active_tasks_zero", "load_reached", "followup_healthy",
        "handshake_rejected", "client_aborted",
        "response_stream_started", "stream_reset", "application_cancelled",
        "active_streams_held", "application_cancellation_count",
        "application_completion_count", "shutdown_elapsed_ms",
        "response_complete_before_app_return",
        "background_work_completed",
        "application_cleanup_completed", "application_tasks_finished_before_probe_cleanup",
        "loop_alive_after_server_return", "lifespan_shutdown_completed", "shutdown_bounded",
        "lifespan_tasks_finished_before_probe_cleanup", "serve_cancellation_propagated",
        "server_error_observed",
        "request_task_failure_observed_before_peer_close",
        "response_incomplete", "peer_close_code", "trigger_request_sent", "fault_consumed",
        "request_task_cancellation_observed", "connection_error_observed", "diagnostics_ordered",
        "application_cleanup_before_followup", "server_log",
        "body_stream_error", "trigger_error",
    }
    for operation in manifest["operations"]:
        expected_operation_keys = {"id", "kind", "observe"}
        if "compare" in operation:
            expected_operation_keys.add("compare")
        if "required_observations" in operation:
            expected_operation_keys.add("required_observations")
            if not set(operation["required_observations"]).issubset(observation_fields):
                raise ParityError(f"{operation.get('id')}: unknown required observation")
        exact_keys(operation, expected_operation_keys, "manifest operation")
        if (
            not isinstance(operation["observe"], list)
            or not operation["observe"]
            or len(operation["observe"]) != len(set(operation["observe"]))
            or not set(operation["observe"]).issubset(observation_fields)
        ):
            raise ParityError(f"{operation.get('id')}: unsupported observation field")
        if "compare" in operation and (
            not isinstance(operation["compare"], list)
            or not operation["compare"]
            or len(operation["compare"]) != len(set(operation["compare"]))
            or not set(operation["compare"]).issubset(operation["observe"])
        ):
            raise ParityError(f"{operation.get('id')}: comparison fields must be observed")
        required = operation.get("required_observations", {})
        if not isinstance(required, dict) or not set(required).issubset(operation["observe"]):
            raise ParityError(f"{operation.get('id')}: required observations must be declared in observe")

    profiles = {profile["id"]: profile for profile in manifest["profiles"]}
    operations = {operation["id"]: operation for operation in manifest["operations"]}
    if len(profiles) != len(manifest["profiles"]):
        raise ParityError("duplicate profile ID")
    if len(operations) != len(manifest["operations"]):
        raise ParityError("duplicate operation ID")
    if any(profile["oracle"] not in oracle_ids for profile in profiles.values()):
        raise ParityError("profile references an undeclared oracle")
    oracle_protocols = {oracle["id"]: set(oracle["protocols"]) for oracle in manifest["oracles"]}
    for profile in profiles.values():
        required_protocols = {part.strip() for part in profile["protocol"].split("+")}
        if not required_protocols.issubset(oracle_protocols[profile["oracle"]]):
            raise ParityError(f"{profile['id']}: oracle does not declare every profile protocol")
    if {path.stem for path in indexed_paths} != set(profiles):
        raise ParityError("the active input index must contain exactly one file per declared profile")

    case_ids: set[str] = set()
    operation_case_counts = {operation_id: 0 for operation_id in operations}
    profile_case_counts = {profile_id: 0 for profile_id in profiles}
    input_cases = []
    for input_path in indexed_paths:
        input_document = json.loads(input_path.read_text(encoding="utf-8"))
        exact_keys(input_document, {"schema", "cases"}, f"parity input {input_path.name}")
        if input_document["schema"] != INPUT_SCHEMA:
            raise ParityError(f"unsupported input schema in {input_path.name}: {input_document['schema']!r}")
        if not isinstance(input_document["cases"], list):
            raise ParityError(f"{input_path.name}: cases must be an array")
        if not input_document["cases"]:
            raise ParityError(f"{input_path.name}: active profile inputs must not be empty")
        if any(case.get("profile") != input_path.stem for case in input_document["cases"] if isinstance(case, dict)):
            raise ParityError(f"{input_path.name}: cases must belong to the file's declared profile")
        input_cases.extend(input_document["cases"])

    for case in input_cases:
        if not isinstance(case, dict):
            raise ParityError("every case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ParityError(f"missing, invalid, or duplicate case ID: {case_id!r}")
        case_ids.add(case_id)
        if case.get("profile") not in profiles:
            raise ParityError(f"{case_id}: undeclared profile {case.get('profile')!r}")
        profile_case_counts[case["profile"]] += 1
        operation = case.get("operation")
        if operation not in operations:
            raise ParityError(f"{case_id}: undeclared operation {operation!r}")
        operation_case_counts[operation] += 1
        if case.get("covers") != [operation]:
            raise ParityError(f"{case_id}: covers must identify its declared operation")
        verification = case.get("verification", "oracle-parity")
        if verification == "oracle-parity":
            if "fault" in case:
                raise ParityError(f"{case_id}: oracle-parity cases may not activate a fault")
        elif verification == "fault-contract":
            fault = case.get("fault")
            if not isinstance(fault, dict):
                raise ParityError(f"{case_id}: fault-contract case requires a fault object")
            exact_keys(fault, {"point", "contract"}, f"{case_id}.fault")
            if not isinstance(fault["point"], str) or fault["point"] not in (FAULT_POINTS | HARNESS_FAULT_POINTS):
                raise ParityError(f"{case_id}: fault point is not allow-listed: {fault['point']!r}")
            if not isinstance(fault["contract"], str) or fault["contract"] not in FAULT_CONTRACTS:
                raise ParityError(f"{case_id}: unsupported fault contract: {fault['contract']!r}")
            if fault["contract"] == "http-response-header-capacity-recovery-followup-200":
                requests = case.get("request_sequence", [])
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] != "public.http-response-header-capacity"
                    or len(requests) != 2
                    or requests[0].get("path") != "/response-header-capacity?count=32769"
                    or requests[1].get("path") != "/scope"
                ):
                    raise ParityError(
                        f"{case_id}: public HTTP header capacity requires its finite response and recovery sequence"
                    )
            elif fault["contract"] == "asgi-spec-version-2.5":
                http_path = case.get("request", {}).get("path")
                websocket_path = case.get("websocket", {}).get("path")
                valid_http = (
                    case.get("profile") in {"http1", "http2", "http3"}
                    and case.get("operation") == "http.scope-and-body"
                    and http_path == "/scope-echo/asgi-version"
                )
                valid_websocket = (
                    case.get("profile") in {"websocket", "websocket-tls"}
                    and case.get("operation") == "websocket.scope-and-messages"
                    and websocket_path == "/ws-scope-echo/asgi-version"
                )
                if fault["point"] != "public.asgi-spec-version" or not (
                    valid_http or valid_websocket
                ):
                    raise ParityError(
                        f"{case_id}: the ASGI spec-version contract requires its declared public scope probe"
                    )
            elif fault["contract"] in {
                "http-500-then-followup-200", "http-callback-error-followup-200",
                "http-original-task-start-error-followup-200",
            }:
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or "request_sequence" not in case
                    or len(case["request_sequence"]) != 2
                ):
                    raise ParityError(
                        f"{case_id}: this fault contract requires exactly two HTTP/1.1 requests"
                    )
                if fault["contract"] == "http-callback-error-followup-200" and fault["point"] not in {
                    "python.task-starter.inline-completion",
                    "python.task-starter.inline-completion-registration-error",
                }:
                    raise ParityError(f"{case_id}: callback error contract requires an inline callback fault")
                if (
                    fault["contract"] == "http-original-task-start-error-followup-200"
                    and fault["point"] not in PYTHON_TASK_START_ERRORS
                ):
                    raise ParityError(f"{case_id}: original task-start error requires a supported prelude fault")
            elif fault["contract"] == "http-callback-error-cleans-task-followup-200":
                requests = case.get("request_sequence", [])
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in {
                        "python.task-starter.inline-completion.borrow-conflict",
                        "python.task-starter.registration-error.borrow-conflict",
                        "python.task-starter.registration-success.borrow-conflict",
                        "python.task-starter.failure-cleanup.schedule-error",
                    }
                    or len(requests) != 2
                    or requests[0].get("path") != "/task-cleanup-hold"
                    or requests[1].get("path") != "/task-cleanup-status"
                ):
                    raise ParityError(
                        f"{case_id}: callback errors require a held application and task-cleanup follow-up"
                    )
            elif fault["contract"] == "server-forced-task-completion-error-bounded-shutdown":
                if (
                    case.get("profile") != "lifecycle-owned-loop"
                    or case.get("operation") != "lifespan.post-response-application-shutdown"
                    or fault["point"] != "python.task-completion.result-receiver-closed"
                    or case.get("lifecycle", {}).get("background_path") != "/post-response-hold"
                ):
                    raise ParityError(
                        f"{case_id}: forced task-completion faults require the owned-loop background-task shutdown workflow"
                    )
            elif fault["contract"] in EAGER_REGISTRATION_CLEANUP_CONTRACTS:
                startup = fault["contract"] in EAGER_LIFESPAN_CLEANUP_CONTRACTS
                normal_return = fault["contract"].endswith("-normal-return")
                expected_point = (
                    "python.task-starter.inline-completion-registration-error"
                    if startup or normal_return else "python.task-starter.failure-cleanup.schedule-error"
                )
                callback_path = (
                    "/task-cleanup-suppress-cancel" if normal_return else "/task-cleanup-hold"
                )
                if (
                    case.get("profile") != "lifecycle-owned-loop-eager"
                    or case.get("operation") != "lifespan.eager-registration-failure-cleanup"
                    or fault["point"] != expected_point
                    or case.get("lifecycle", {}).get("state_path") != "/state"
                    or case.get("lifecycle", {}).get("graceful_timeout_seconds") != 1
                    or (not startup and case["lifecycle"].get("callback_path") != callback_path)
                    or (startup and "callback_path" in case["lifecycle"])
                    or case["lifecycle"].get("cleanup_delay_seconds")
                    != (5 if fault["contract"].endswith("-timeout") else 0.5)
                ):
                    raise ParityError(
                        f"{case_id}: eager registration cleanup requires its owning-loop role and callback workflow"
                    )
            elif fault["contract"] == "http3-500-error-body":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.application-error"
                    or fault["point"] != "http.app-task.panic-before-response-start"
                    or case.get("request", {}).get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 panic injection requires the pre-response application-failure workflow"
                    )
            elif fault["contract"] == "http3-connection-task-error-followup-200":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.handshake-recovery"
                    or fault["point"] != "http3.connection-task.panic"
                    or case.get("request", {}).get("invalid_alpn") is not True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 connection-task fault requires a rejected first connection and healthy follow-up"
                    )
            elif fault["contract"] == "http3-request-task-error-before-peer-close-followup-200":
                requests = case.get("request_sequence", [])
                if not isinstance(requests, list) or any(not isinstance(request, dict) for request in requests):
                    raise ParityError(f"{case_id}: request-task recovery requires an array of request objects")
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.request-task-recovery"
                    or fault["point"] != "http3.request-task.panic-after-response"
                    or len(requests) != 2
                    or requests[0] != requests[1]
                    or any("expect_response_error" in request for request in requests)
                ):
                    raise ParityError(
                        f"{case_id}: live request-task recovery requires two identical healthy same-connection requests"
                    )
            elif fault["contract"] == "http3-connection-error-cancels-held-response-followup-200":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.request-task-drain-on-accept-error"
                    or fault["point"] != "http3.connection.accept-error"
                    or case.get("response_reset", {}).get("path") != "/stream-cancel-until-reset"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 connection-error cleanup requires an active held response"
                    )
            elif fault["contract"] == "http3-stream-reset-on-runtime-error":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.injected-stream-error"
                    or fault["point"] not in {
                        "http3.request-task.panic",
                        "http3.connection.accept-finished",
                        "http3.connection.create-error",
                        "http3.connection.accept-error",
                        "http3.request.resolve-error",
                        "http3.response.builder-error",
                        "http3.response.send-error",
                        "http3.response.body-frame-error",
                        "http3.response.non-data-frame",
                        "http3.response.body-send-error",
                        "http3.response.finish-error",
                    }
                    or case.get("request", {}).get("expect_response_error") is not True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 stream-error faults require the reset-observation workflow"
                    )
            elif fault["contract"] == "http3-peer-close-classification-defensive-error":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.peer-close"
                    or fault["point"] not in {
                        "http3.peer-close.unexpected-error-kind",
                        "http3.peer-close.close-reason-unavailable",
                    }
                    or case.get("request", {}).get("close_error_code") != 33
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 peer-close classifier faults require the GREASE peer-close workflow"
                    )
            elif fault["contract"] == "http3-body-pump-early-exit-500":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.body-pump-early-exit"
                    or fault["point"] not in {
                        "http3.body-pump.send.connection-closed",
                        "http3.body-pump.connection-closed",
                        "http3.body-pump.connection-closed-select",
                        "http3.body-pump.sender-closed-select",
                    }
                    or case.get("request", {}).get("path") not in {"/return-before-response-start", "/h3-upload-disconnect"}
                    or not case.get("request", {}).get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 body-pump early exits require a nonempty POST request"
                    )
            elif fault["contract"] == "http3-upload-body-pump-preserves-data":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.request-upload"
                    or fault["point"] not in {
                        "http3.body-pump.empty-data-frame",
                    }
                    or case.get("request", {}).get("path") != "/read-first-upload"
                    or case.get("request", {}).get("method") != "POST"
                    or not case.get("request", {}).get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 body-pump upload faults require a nonempty POST read probe"
                    )
            elif fault["contract"] == "http3-upload-body-pump-completes-final-message":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.request-upload"
                    or fault["point"]
                    != "http3.body-pump.final-message-connection-closed-select"
                    or case.get("request", {}).get("path") != "/h3-upload-disconnect"
                    or case.get("request", {}).get("method") != "POST"
                    or not case.get("request", {}).get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 final-body upload fault requires a completed POST probe"
                    )
            elif fault["contract"] == "http3-upload-body-pump-send-error-disconnect":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.request-upload"
                    or fault["point"] != "http3.body-pump.send-error"
                    or case.get("request", {}).get("path") != "/read-first-upload"
                    or case.get("request", {}).get("method") != "POST"
                    or not case.get("request", {}).get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 upload send-error fault requires a nonempty POST read probe"
                    )
            elif fault["contract"] == "http3-connection-task-shutdown-error":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.connection-task-shutdown"
                    or fault["point"] != "http3.connection-task.panic-during-shutdown"
                    or case.get("request", {}).get("hold_open_for_shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 shutdown error requires the held-connection workflow"
                    )
            elif fault["contract"] == "http3-connection-task-shutdown-hang-aborted":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.connection-task-shutdown"
                    or fault["point"] != "http3.connection-task.shutdown-hang"
                    or case.get("request", {}).get("hold_open_for_shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 task-abort fault requires the held-connection workflow"
                    )
            elif fault["contract"] == "http3-endpoint-accept-closes-http3":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.endpoint-accept-fallback"
                    or fault["point"] != "http3.endpoint.accept-closed"
                    or case.get("startup_fallback", {}).get("followup_path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: endpoint accept closure requires startup plus an HTTP/1 follow-up"
                    )
            elif fault["contract"] == "http2-500-empty-body":
                if (
                    case.get("profile") != "http2"
                    or case.get("operation") != "http.application-error"
                    or fault["point"] != "http.app-task.panic-before-response-start"
                    or case.get("request", {}).get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/2 panic injection requires the pre-response application-failure workflow"
                    )
            elif fault["contract"] == "http3-client-abort-disconnect-followup":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.request-disconnect"
                    or fault["point"] != "http3.client.abort-after-body"
                    or case.get("request", {}).get("abort_after_body") is not True
                    or case.get("request", {}).get("path") != "/h3-upload-disconnect"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 client-abort contract requires the partial-body disconnect workflow"
                    )
            elif fault["contract"] == "http3-body-pump-error-stop-disconnect-followup-200":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.request-disconnect"
                    or fault["point"] != "http3.body-pump.error.request-stop"
                    or case.get("request", {}).get("abort_after_body") is not True
                    or case.get("request", {}).get("path") != "/h3-upload-disconnect"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 body-pump error stop requires a synchronized client abort"
                    )
            elif fault["contract"] == "http3-body-pump-reaps-cancelled-task":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.request-upload"
                    or fault["point"] != "http.body-pump.reap.cancelled-task"
                    or request.get("path") != "/read-first-upload"
                    or request.get("method") != "POST"
                    or not request.get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 task reaping requires a nonempty POST upload probe"
                    )
            elif fault["contract"] == "http3-server-shutdown-force-abort":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.graceful-shutdown"
                    or fault["point"] != "server.http3-task.shutdown-hang"
                    or case.get("request", {}).get("hold_open_for_shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 shutdown timeout faults require the held-connection shutdown workflow"
                    )
            elif fault["contract"] == "http-final-body-preserved-after-app-task-panic":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.application-error"
                    or fault["point"] != "python.task-future.panic-after-completion"
                    or case.get("request", {}).get("path") != "/complete-before-task-panic"
                ):
                    raise ParityError(
                        f"{case_id}: late task panic requires the final-body HTTP/1.1 workflow"
                    )
            elif fault["contract"] == "http-task-panic-before-final-body-closes-stream":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.response-body-fault"
                    or fault["point"] != "python.task-future.panic-after-completion"
                    or case.get("request", {}).get("path")
                    != "/invalid-asgi/incomplete-response-body"
                ):
                    raise ParityError(
                        f"{case_id}: incomplete-body task panic requires the HTTP/1.1 partial-body workflow"
                    )
            elif fault["contract"] == "http-incomplete-body-preserves-emitted-chunk-after-consumer-pause":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.response-body-fault"
                    or fault["point"] != "http.response.body-consumer.pause"
                    or case.get("request", {}).get("path")
                    != "/invalid-asgi/incomplete-response-body"
                ):
                    raise ParityError(
                        f"{case_id}: consumer-pause incomplete-body contract requires the HTTP/1.1 partial-body workflow"
                    )
            elif fault["contract"] == "http-start-and-final-body-preserved-after-task-wins-select":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.response-stream"
                    or fault["point"] != "http.response.task-wins-start-select"
                    or case.get("request", {}).get("path") != "/stream-yield-after-start"
                ):
                    raise ParityError(
                        f"{case_id}: queued-final-body selection requires the HTTP/1.1 stream workflow"
                    )
            elif fault["contract"] == "http-response-body-queued-after-receiver-pending":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.response-stream"
                    or fault["point"] != "http.response.body-poll.receiver-pending.pause"
                    or case.get("request", {}).get("path") not in {
                        "/stream-pending-then-complete", "/stream-pending-burst-then-complete",
                    }
                ):
                    raise ParityError(
                        f"{case_id}: queued-body recovery requires the HTTP/1.1 receiver-pending workflow"
                    )
            elif fault["contract"] == "http-response-reset-cancels-deferred-task":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.response-stream-reset"
                    or fault["point"] != "python.task-future.defer-task-transfer"
                    or case.get("response_reset", {}).get("path") != "/stream-cancel-until-reset"
                ):
                    raise ParityError(f"{case_id}: deferred task transfer requires the held response-reset workflow")
            elif fault["contract"] == "http-read-eof-recheck-completes":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http2"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] != "server.connection-io.eof-recheck.pause"
                    or "reset" in disconnect
                    or disconnect.get("wait_event") != "http.disconnect.waiting"
                ):
                    raise ParityError(f"{case_id}: EOF recheck requires a synchronized HTTP/2 connection disconnect")
            elif fault["contract"] == "server-cancellation-schedule-error-bounded-shutdown":
                if (
                    case.get("profile") != "lifecycle"
                    or case.get("operation") != "lifespan.shutdown-cancellation"
                    or fault["point"] not in {
                        "python.task-cancel.cancel.getattr", "python.task-cancel.context.set-item",
                        "python.task-cancel.schedule-call",
                    }
                    or case.get("lifecycle", {}).get("hold_path") != "/hold"
                ):
                    raise ParityError(f"{case_id}: cancellation errors require a held request and bounded shutdown")
            elif fault["contract"] == "http-connection-task-error-followup-200":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in {
                        "server.connection-task.service-error",
                        "server.connection-task.join-error",
                    }
                    or "request_sequence" not in case
                    or len(case["request_sequence"]) != 2
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in case["request_sequence"][0].get("headers", [])
                    )
                ):
                    raise ParityError(
                        f"{case_id}: connection-task faults require a close-delimited first request and HTTP follow-up"
                    )
            elif fault["contract"] == "http-connection-task-write-error-followup-200":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in {
                        "server.connection-task.service-await-error",
                        "server.connection-task.join-await-error",
                        "server.connection-task.service-select-result",
                        "server.connection-task.join-select-result",
                    }
                    or "request_sequence" not in case
                    or len(case["request_sequence"]) != 2
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in case["request_sequence"][0].get("headers", [])
                    )
                ):
                    raise ParityError(
                        f"{case_id}: connection-task write faults require a close-delimited first request and HTTP follow-up"
                    )
            elif fault["contract"] == "http-concurrent-receive-after-lock-contention":
                stream = case.get("request_stream", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] != "http.receive.lock-contention"
                    or stream.get("path") != "/concurrent-upload-receive"
                    or stream.get("wait_event") != "http.receive.concurrently-waiting"
                    or stream.get("send_all_before_read") is not True
                ):
                    raise ParityError(
                        f"{case_id}: receive contention requires the synchronized concurrent-upload workflow"
                    )
            elif fault["contract"] == "http-task-completion-error-followup-200":
                requests = case.get("request_sequence", [])
                first_headers = requests[0].get("headers", []) if requests else []
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] != "python.task-completion.result-receiver-closed"
                    or len(requests) != 2
                    or requests[0].get("path") != "/invalid-asgi/incomplete-response-body"
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in first_headers
                    )
                    or requests[1].get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: task completion channel faults require an incomplete response and health follow-up"
                    )
            elif fault["contract"] == "http-start-response-preserved-followup-200":
                requests = case.get("request_sequence", [])
                first_headers = requests[0].get("headers", []) if requests else []
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] != "http.response.task-wins-start-select"
                    or len(requests) != 2
                    or requests[0].get("path") != "/invalid-asgi/start-then-raise"
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in first_headers
                    )
                    or requests[1].get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: queued response-start faults require the start-then-raise request and health follow-up"
                    )
            elif fault["contract"] == "http-response-body-error-followup-200":
                requests = case.get("request_sequence", [])
                first_headers = requests[0].get("headers", []) if requests else []
                held_stream_fault = (
                    len(requests) == 2
                    and requests[0].get("path") == "/stream-progress-hold"
                    and requests[0].get("fault_after_response_headers") is True
                )
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in HTTP_RESPONSE_BODY_FAULT_POINTS
                    or len(requests) != 2
                    or (requests[0].get("path") != "/state" and not held_stream_fault)
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in first_headers
                    )
                    or requests[1].get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: response-body conversion faults require a close-delimited /state response and health follow-up"
                    )
            elif fault["contract"] == "http-response-backpressure-body-preserved-followup-200":
                requests = case.get("request_sequence", [])
                first_headers = requests[0].get("headers", []) if requests else []
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in HTTP_RESPONSE_BODY_BACKPRESSURE_FAULT_POINTS
                    or len(requests) != 2
                    or requests[0].get("path") != "/response-burst-large"
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in first_headers
                    )
                    or requests[1].get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: body backpressure faults require a large streamed response and a health follow-up"
                    )
            elif fault["contract"] == "http-start-error-close-followup-200":
                requests = case.get("request_sequence", [])
                first_headers = requests[0].get("headers", []) if requests else []
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in HTTP_RESPONSE_START_ERROR_FAULT_POINTS
                    or len(requests) != 2
                    or requests[0].get("path") != "/state"
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in first_headers
                    )
                    or requests[1].get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: invalid response-start field faults require close and a health follow-up"
                    )
            elif fault["contract"] == "http-reset-before-body-worker-disconnect-followup-200":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] != "http.body-pump.first-poll-pause"
                    or disconnect.get("path") != "/disconnect-read-twice"
                    or disconnect.get("followup_path") != "/disconnect-status"
                    or disconnect.get("wait_event") != "http.disconnect.waiting"
                    or disconnect.get("wait_event_after_disconnect")
                    != "http.disconnect.second:http.disconnect"
                    or disconnect.get("reset") is not True
                    or not isinstance(disconnect.get("content_length"), int)
                    or disconnect["content_length"] <= 0
                    or disconnect.get("partial_body_base64") != ""
                ):
                    raise ParityError(
                        f"{case_id}: delayed body-worker reset requires an incomplete upload and real disconnect follow-up"
                    )
            elif fault["contract"] == "http-body-pump-error-stop-disconnect-followup-200":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] != "http.body-pump.error.request-stop"
                    or disconnect.get("path") != "/disconnect-read-twice"
                    or disconnect.get("followup_path") != "/disconnect-status"
                    or disconnect.get("malformed_chunk") is not True
                    or disconnect.get("wait_event") != "http.disconnect.waiting"
                    or disconnect.get("wait_event_after_disconnect")
                    != "http.disconnect.second:http.disconnect"
                ):
                    raise ParityError(
                        f"{case_id}: malformed-body stop requires a synchronized ASGI disconnect and follow-up"
                    )
            elif fault["contract"] == "http-body-pump-drain-shutdown-joined":
                stream = case.get("request_stream", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] != "http.body-pump.drain.server-stop-wait"
                    or stream.get("path") != "/ignore-upload"
                    or stream.get("hold_until_shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: body-pump shutdown requires an open unread upload and synchronized shutdown"
                    )
            elif fault["contract"] == "http-body-pump-drain-terminal-frame":
                stream = case.get("request_stream", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] != "http.body-pump.drain.terminal-frame"
                    or stream.get("path") != "/ignore-upload"
                ):
                    raise ParityError(
                        f"{case_id}: drain termination requires an HTTP/1.1 early-response upload"
                    )
            elif fault["contract"] == "http-body-pump-reaps-cancelled-task":
                stream = case.get("request_stream", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] != "http.body-pump.reap.cancelled-task"
                    or stream.get("path") != "/read-first-upload"
                ):
                    raise ParityError(
                        f"{case_id}: task reaping requires an HTTP/1.1 streamed upload"
                    )
            elif fault["contract"] in {
                "http-body-pump-shutdown-cancelled-join",
                "http-body-pump-shutdown-aborts-hung-pump",
                "http-body-pump-shutdown-completes-task-before-abort",
            }:
                stream = case.get("request_stream", {})
                expected_point = (
                    "http.body-pump.shutdown.cancel-join"
                    if fault["contract"] == "http-body-pump-shutdown-cancelled-join"
                    else (
                        "http.body-pump.shutdown.hang"
                        if fault["contract"] == "http-body-pump-shutdown-aborts-hung-pump"
                        else "http.body-pump.shutdown.complete-task-before-abort"
                    )
                )
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] != expected_point
                    or stream.get("path") != "/ignore-upload"
                    or stream.get("hold_until_shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: request-body shutdown fault requires the synchronized unread-upload workflow"
                    )
            elif fault["contract"] == "http-disconnect-error-followup-200":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] != "request.http.disconnect.type.set-item"
                    or not disconnect.get("reset")
                    or "content_length" not in disconnect
                ):
                    raise ParityError(
                        f"{case_id}: disconnect-message faults require a reset during an incomplete request body"
                    )
            elif fault["contract"] == "http-immediate-disconnect-message-error-followup-200":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] != "http.receive.immediate-disconnect-message-error"
                    or disconnect.get("path") != "/disconnect-read-thrice"
                    or disconnect.get("wait_event") != "http.disconnect.waiting"
                    or disconnect.get("wait_event_after_disconnect")
                    != "http.disconnect.repeat-error:MemoryError"
                    or not disconnect.get("reset")
                    or "content_length" not in disconnect
                ):
                    raise ParityError(
                        f"{case_id}: immediate disconnect faults require the synchronized repeated-receive workflow"
                    )
            elif fault["contract"] == "server-startup-failure":
                if (
                    case.get("operation") != "lifespan.startup-failure"
                    or "startup_failure" not in case
                    or not (
                        fault["point"].startswith("lifespan.scope.")
                        or fault["point"] in {"lifespan.io.allocate", "lifespan.app-invoke"}
                        or fault["point"] in {
                            "python.asgi-receive.borrow-conflict",
                            "server.control.shutdown.borrow-conflict",
                            "server.serve.control.borrow-conflict",
                            "server.graceful-timeout.overflow",
                            "server.python-locals.get-current",
                        }
                        or fault["point"] in {"lifespan.startup.task-join-error", "lifespan.startup.send-closed"}
                        or fault["point"].startswith("native.module.")
                        or fault["point"] == "native.runtime.build.error"
                        or fault["point"] in {
                            "server.quic-tls.config-error",
                            "server.listener.accept-error",
                            "server.listener.local-addr-error",
                            "server.http3-endpoint.bind-error",
                        }
                    )
                ):
                    raise ParityError(
                        f"{case_id}: lifespan startup faults require the startup-failure workflow"
                    )
            elif fault["contract"] == "server-lifespan-startup-auto-fallback":
                if (
                    not (
                        case.get("profile") == "lifespan-fault-receive-startup"
                        or case.get("profile", "").startswith("lifespan-fault-asgi-startup-")
                        or case.get("profile") == "lifespan-fault-start-event-channel-closed"
                    )
                    or case.get("operation") != "lifespan.startup-auto-fallback"
                    or fault["point"] not in LIFESPAN_STARTUP_AUTO_FALLBACK_FAULT_POINTS
                    or "startup_fallback" not in case
                ):
                    raise ParityError(
                        f"{case_id}: lifespan startup faults require the auto-fallback workflow"
                    )
            elif fault["contract"] == "server-shutdown-failure":
                if (
                    not (
                        case.get("profile") == "lifespan-fault-shutdown-receive"
                        or case.get("profile", "").startswith("lifespan-fault-asgi-shutdown-")
                    )
                    or case.get("operation") != "server.shutdown-failure"
                    or fault["point"] not in LIFESPAN_SHUTDOWN_FAILURE_FAULT_POINTS
                    or "lifecycle" not in case
                ):
                    raise ParityError(
                        f"{case_id}: lifespan shutdown fault requires the shutdown-failure workflow"
                    )
            elif fault["contract"] == "server-lifespan-task-cancel":
                if (
                    case.get("profile") != "lifespan-fault-shutdown-cancel"
                    or case.get("operation") != "lifespan.shutdown-cancellation"
                    or fault["point"] not in LIFESPAN_TASK_CANCEL_FAULT_POINTS
                    or "lifecycle" not in case
                ):
                    raise ParityError(
                        f"{case_id}: lifespan task cancellation requires the shutdown-cancellation workflow"
                    )
            elif fault["contract"] == "server-connection-task-error-during-shutdown":
                if (
                    case.get("profile") != "lifecycle"
                    or case.get("operation") != "lifespan.shutdown-cancellation"
                    or fault["point"] not in {
                        "server.connection-task.service-error-during-shutdown",
                        "server.connection-task.join-error-during-shutdown",
                    }
                    or case.get("lifecycle", {}).get("hold_path") != "/hold"
                ):
                    raise ParityError(
                        f"{case_id}: connection-task shutdown faults require the held-request lifecycle workflow"
                    )
            elif fault["contract"] == "server-connection-task-shutdown-timeout-abort":
                if (
                    case.get("profile") != "lifecycle"
                    or case.get("operation") != "lifespan.shutdown-cancellation"
                    or fault["point"] != "server.connection-task.shutdown-hang"
                    or case.get("lifecycle", {}).get("state_path") != "/state"
                    or case.get("lifecycle", {}).get("hold_path") != "/hold"
                    or case.get("lifecycle", {}).get("graceful_timeout_seconds") != 1
                ):
                    raise ParityError(
                        f"{case_id}: connection-task timeout faults require the bounded held-request shutdown workflow"
                    )
            elif fault["contract"] == "server-hyper-connection-error-during-shutdown":
                if (
                    case.get("profile") not in {"lifecycle", "lifecycle-tls"}
                    or case.get("operation")
                    != "lifespan.hyper-connection-write-error-during-shutdown"
                    or fault["point"] != "server.connection-io.poll-write-error"
                    or case.get("lifecycle", {}).get("stream_path")
                    != "/stream-shutdown-hold"
                    or "reset_connection_after_shutdown" in case.get("lifecycle", {})
                ):
                    raise ParityError(
                        f"{case_id}: Hyper connection write faults require a held response during graceful shutdown"
                    )
            elif fault["contract"] == "websocket-server-shutdown-force-abort":
                if (
                    case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.shutdown-cancellation"
                    or fault["point"] not in {"server.websocket-task.shutdown-hang", "server.websocket-task.shutdown-panic"}
                    or case.get("websocket", {}).get("path") != "/ws-hold-on-shutdown"
                    or case.get("websocket", {}).get("shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: WebSocket shutdown timeout requires the held-session cancellation workflow"
                    )
            elif fault["contract"] in {
                "websocket-driver-send-error-followup-200",
                "websocket-driver-send-error-cancels-app",
            }:
                expected_path = (
                    "/ws-send-and-return"
                    if fault["contract"] == "websocket-driver-send-error-followup-200"
                    else "/ws-send-and-hold"
                )
                if (
                    case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.fault-contract"
                    or fault["point"] not in {
                        "websocket.driver.send-error",
                        "websocket.driver.drain-send-error",
                    }
                    or case.get("websocket", {}).get("path") != expected_path
                    or case.get("websocket", {}).get("expect_close") is not True
                ):
                    raise ParityError(
                        f"{case_id}: WebSocket send-error contracts require their matching outbound-send workflow"
                    )
            elif fault["contract"] == "websocket-header-capacity-error-followup-200":
                specification = case.get("websocket", {})
                if (
                    case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.fault-contract"
                    or fault["point"] != "public.websocket-accept-header-capacity"
                    or specification.get("path") != "/ws-header-capacity?count=32769"
                    or specification.get("followup_path") != "/scope"
                    or specification.get("messages") != []
                ):
                    raise ParityError(
                        f"{case_id}: public WebSocket header capacity requires its finite handshake and recovery workflow"
                    )
            elif fault["contract"] == "websocket-handshake-error-followup-200":
                if (
                    case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.fault-contract"
                    or fault["point"] not in WEBSOCKET_HANDSHAKE_FAULT_POINTS
                    or "websocket" not in case
                    or not case["websocket"].get("followup_path", "").startswith("/")
                ):
                    raise ParityError(
                        f"{case_id}: WebSocket receive-construction faults require a failed handshake and HTTP follow-up"
                    )
            elif (
                fault["contract"] != "websocket-teardown-and-followup-200"
                or case.get("profile") != "websocket"
                or case.get("operation") != "websocket.fault-contract"
                or fault["point"] not in WEBSOCKET_FAULT_POINTS
                or "websocket" not in case
                or not (
                    case["websocket"].get("expect_close") is True
                    or (
                        fault["point"] in {
                            "websocket.receive.disconnect-type.set-item",
                            "websocket.receive.disconnect-code.set-item",
                            "websocket.receive.disconnect-reason.set-item",
                        }
                        and "client_close" in case["websocket"]
                    )
                )
                or not case["websocket"].get("followup_path", "").startswith("/")
            ):
                raise ParityError(
                    f"{case_id}: WebSocket fault contracts require a closed receive channel and observed close"
                )
        else:
            raise ParityError(f"{case_id}: unsupported verification mode {verification!r}")
        for field in case:
            if field.startswith("expected") or field in {"oracle_output", "target_output"}:
                raise ParityError(f"{case_id}: parity inputs may not contain observed results")
        kind = case.get("profile")
        profile_protocols = {
            part.strip() for part in profiles[kind]["protocol"].split("+")
        }
        supports_http_request = bool(
            profile_protocols.intersection({"http/1.1", "http/2", "http/3"})
        )
        http_profile_ids = {"http1", "http1-tls", "http2", "http3"}
        if kind in http_profile_ids and "response_stream" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "response_stream"}, case_id)
            if kind == "http3":
                raise ParityError(f"{case_id}: no H3 observation client is declared for progressive reads")
            response_stream_keys = {"path"}
            if "app_return_event" in case["response_stream"]:
                response_stream_keys.add("app_return_event")
                if not isinstance(case["response_stream"]["app_return_event"], str) or not case["response_stream"]["app_return_event"]:
                    raise ParityError(f"{case_id}: app_return_event must be a nonempty event selector")
            if "pause_before_first_body_ms" in case["response_stream"]:
                response_stream_keys.add("pause_before_first_body_ms")
                if kind != "http1":
                    raise ParityError(
                        f"{case_id}: pausing the first body read is currently scoped to HTTP/1.1"
                    )
                pause_ms = case["response_stream"]["pause_before_first_body_ms"]
                if type(pause_ms) is not int or not 0 <= pause_ms <= 1000:
                    raise ParityError(
                        f"{case_id}: pause_before_first_body_ms must be an integer from 0 to 1000"
                    )
            exact_keys(case["response_stream"], response_stream_keys, f"{case_id}.response_stream")
            if not case["response_stream"]["path"].startswith("/"):
                raise ParityError(f"{case_id}: response stream path must be origin-form")
        elif kind in http_profile_ids and "response_reset" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "response_reset"}, case_id)
            reset_keys = {"path", "followup_path"}
            if kind == "http3":
                if case.get("fault", {}).get("contract") != "http3-connection-error-cancels-held-response-followup-200":
                    raise ParityError(f"{case_id}: HTTP/3 response reset requires the connection-error cleanup contract")
                reset_keys.add("trigger_path")
            elif kind not in {"http1", "http2"}:
                raise ParityError(f"{case_id}: response reset workflow supports HTTP/1.1, HTTP/2 and HTTP/3")
            exact_keys(case["response_reset"], reset_keys, f"{case_id}.response_reset")
            if not all(
                isinstance(case["response_reset"][key], str)
                and case["response_reset"][key].startswith("/")
                for key in reset_keys
            ):
                raise ParityError(f"{case_id}: response reset paths must be origin-form")
        elif kind in http_profile_ids and "disconnect" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "disconnect"}, case_id)
            if kind not in {"http1", "http2"}:
                raise ParityError(f"{case_id}: disconnect workflow supports HTTP/1.1 and HTTP/2")
            if kind == "http2":
                http2_disconnect_keys = {
                    "path", "followup_path", "wait_event", "wait_event_after_disconnect",
                }
                if case["disconnect"].get("empty_request") is True:
                    http2_disconnect_keys.add("empty_request")
                elif "complete_body_base64" in case["disconnect"]:
                    http2_disconnect_keys.update(
                        {"complete_body_base64", "wait_event_before_body"}
                    )
                else:
                    http2_disconnect_keys.update({"content_length", "partial_body_base64"})
                if "reset_stream" in case["disconnect"]:
                    http2_disconnect_keys.add("reset_stream")
                    if case["disconnect"]["reset_stream"] is not True:
                        raise ParityError(f"{case_id}: reset_stream must be true when present")
                exact_keys(case["disconnect"], http2_disconnect_keys, f"{case_id}.disconnect HTTP/2")
            disconnect_keys = {"path", "followup_path"}
            if "reset_stream" in case["disconnect"]:
                disconnect_keys.add("reset_stream")
                if kind != "http2" or case["disconnect"]["reset_stream"] is not True:
                    raise ParityError(f"{case_id}: reset_stream is supported only for HTTP/2 and must be true")
            if "empty_request" in case["disconnect"]:
                disconnect_keys.add("empty_request")
                if case["disconnect"]["empty_request"] is not True:
                    raise ParityError(f"{case_id}: empty_request must be true when present")
            if "malformed_chunk" in case["disconnect"]:
                disconnect_keys.add("malformed_chunk")
                if case["disconnect"]["malformed_chunk"] is not True:
                    raise ParityError(f"{case_id}: malformed_chunk must be true when present")
            if "complete_body_base64" in case["disconnect"]:
                disconnect_keys.update({"complete_body_base64", "wait_event_before_body"})
                if kind != "http2" or case["disconnect"].get("reset_stream") is not True:
                    raise ParityError(
                        f"{case_id}: complete-body resets are supported only for HTTP/2 stream resets"
                    )
                try:
                    complete_body = base64.b64decode(
                        case["disconnect"]["complete_body_base64"], validate=True
                    )
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid complete HTTP/2 body base64") from error
                if not complete_body:
                    raise ParityError(f"{case_id}: complete HTTP/2 body must be nonempty")
                if not isinstance(case["disconnect"]["wait_event_before_body"], str) or not case["disconnect"]["wait_event_before_body"]:
                    raise ParityError(f"{case_id}: wait_event_before_body must be nonempty text")
            if "wait_event" in case["disconnect"]:
                disconnect_keys.add("wait_event")
                if not isinstance(case["disconnect"]["wait_event"], str) or not case["disconnect"]["wait_event"]:
                    raise ParityError(f"{case_id}: wait_event must be non-empty text")
            if "wait_event_after_disconnect" in case["disconnect"]:
                disconnect_keys.add("wait_event_after_disconnect")
                if (
                    not isinstance(case["disconnect"]["wait_event_after_disconnect"], str)
                    or not case["disconnect"]["wait_event_after_disconnect"]
                ):
                    raise ParityError(
                        f"{case_id}: wait_event_after_disconnect must be non-empty text"
                    )
            if "reset" in case["disconnect"]:
                disconnect_keys.add("reset")
                if case["disconnect"]["reset"] is not True:
                    raise ParityError(f"{case_id}: reset must be true when present")
            if "content_length" in case["disconnect"] or "partial_body_base64" in case["disconnect"]:
                disconnect_keys.update({"content_length", "partial_body_base64"})
                if not isinstance(case["disconnect"]["content_length"], int) or case["disconnect"]["content_length"] <= 0:
                    raise ParityError(f"{case_id}: incomplete request content length must be positive")
                try:
                    partial_body = base64.b64decode(case["disconnect"]["partial_body_base64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid partial disconnect body base64") from error
                if len(partial_body) >= case["disconnect"]["content_length"]:
                    raise ParityError(f"{case_id}: disconnect body prefix must be shorter than content_length")
            if case["disconnect"].get("reset") and "content_length" not in case["disconnect"]:
                raise ParityError(f"{case_id}: reset disconnect requires an incomplete fixed-length body")
            if case["disconnect"].get("malformed_chunk") and (
                "content_length" in case["disconnect"] or "reset" in case["disconnect"]
            ):
                raise ParityError(f"{case_id}: malformed chunk framing cannot be combined with a fixed-length reset")
            if case["disconnect"].get("empty_request") and (
                "content_length" in case["disconnect"]
                or "partial_body_base64" in case["disconnect"]
                or "malformed_chunk" in case["disconnect"]
                or "reset" in case["disconnect"]
                or "wait_event" not in case["disconnect"]
            ):
                raise ParityError(
                    f"{case_id}: empty request disconnect requires a wait_event and no body mode"
                )
            exact_keys(case["disconnect"], disconnect_keys, f"{case_id}.disconnect")
        elif kind in http_profile_ids and "request_stream" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "request_stream"}, case_id)
            if kind == "http3":
                raise ParityError(f"{case_id}: request streaming has no declared H3 reference workflow")
            stream = case["request_stream"]
            stream_keys = {"method", "path", "headers", "chunks_base64"}
            if "trailers" in stream:
                stream_keys.add("trailers")
            if "send_all_before_read" in stream:
                stream_keys.add("send_all_before_read")
                if stream["send_all_before_read"] is not True:
                    raise ParityError(f"{case_id}: send_all_before_read must be true when present")
            if "send_remaining_after_response" in stream:
                stream_keys.add("send_remaining_after_response")
                if (
                    stream["send_remaining_after_response"] is not True
                    or kind != "http1"
                    or stream.get("send_all_before_read") is True
                ):
                    raise ParityError(
                        f"{case_id}: post-response request-body completion requires HTTP/1.1 streaming"
                    )
            if "keep_alive" in stream:
                stream_keys.add("keep_alive")
                if stream["keep_alive"] is not True or kind != "http1":
                    raise ParityError(f"{case_id}: keep_alive is supported only for HTTP/1.1 request streams")
            if "hold_until_shutdown" in stream:
                stream_keys.add("hold_until_shutdown")
                shutdown_contracts = {
                    "http-body-pump-drain-shutdown-joined",
                    "http-body-pump-shutdown-cancelled-join",
                    "http-body-pump-shutdown-aborts-hung-pump",
                    "http-body-pump-shutdown-completes-task-before-abort",
                }
                if (
                    stream["hold_until_shutdown"] is not True
                    or kind != "http1"
                    or case.get("verification") != "fault-contract"
                    or case.get("fault", {}).get("contract") not in shutdown_contracts
                ):
                    raise ParityError(
                        f"{case_id}: hold_until_shutdown is restricted to the target body-pump shutdown contract"
                    )
            if "wait_event" in stream:
                stream_keys.add("wait_event")
                if kind != "http1":
                    raise ParityError(f"{case_id}: request-stream event synchronization is HTTP/1.1 only")
                if not isinstance(stream["wait_event"], str) or not stream["wait_event"]:
                    raise ParityError(f"{case_id}: request-stream wait_event must be non-empty text")
            if "malformed_final_chunk" in stream:
                stream_keys.add("malformed_final_chunk")
                if stream["malformed_final_chunk"] is not True or kind != "http1":
                    raise ParityError(
                        f"{case_id}: malformed final chunk input is supported only for HTTP/1.1"
                    )
            exact_keys(stream, stream_keys, f"{case_id}.request_stream")
            if len(stream["chunks_base64"]) < 2:
                raise ParityError(f"{case_id}: request streaming requires at least two input chunks")
            try:
                for chunk in stream["chunks_base64"]:
                    base64.b64decode(chunk, validate=True)
            except (ValueError, TypeError) as error:
                raise ParityError(f"{case_id}: invalid request-stream base64") from error
            if "trailers" in stream and (
                not isinstance(stream["trailers"], list)
                or any(
                    not isinstance(header, list)
                    or len(header) != 2
                    or not all(isinstance(part, str) for part in header)
                    for header in stream["trailers"]
                )
            ):
                raise ParityError(f"{case_id}: request trailers must be pairs of strings")
        elif "request_sequence" in case and (
            kind in {"http1", "http2", "http3"}
            or (profile_protocols == {"http/1.1", "lifespan"} and not kind.endswith("-tls"))
        ):
            if kind == "http2" and case["operation"] not in {
                "http.concurrent-streams", "http.concurrent-stream-load"
            }:
                raise ParityError(f"{case_id}: HTTP/2 request sequences require the concurrent-streams operation")
            if kind == "http3" and case["operation"] not in {
                "http.keepalive-sequence", "http3.request-task-recovery",
                "http3.concurrent-stream-load",
            }:
                raise ParityError(f"{case_id}: HTTP/3 sequences require a declared sequence operation")
            sequence_keys = {"case_id", "profile", "operation", "covers", "request_sequence"}
            if "load" in case:
                sequence_keys.add("load")
                validate_load_input(case, "http")
                if case.get("verification", "oracle-parity") != "oracle-parity" or "fault" in case:
                    raise ParityError(f"{case_id}: load workflows require live oracle parity")
            elif case["operation"] in {
                "http.concurrent-connections", "http.concurrent-stream-load",
                "http3.concurrent-stream-load",
            }:
                raise ParityError(f"{case_id}: declared load operation requires a load input")
            if kind == "http3" and "h3_grease" in case:
                sequence_keys.add("h3_grease")
                if not isinstance(case["h3_grease"], bool):
                    raise ParityError(f"{case_id}: h3_grease must be a boolean")
            exact_case_keys(case, sequence_keys, case_id)
            requests = case["request_sequence"]
            if "load" in case:
                if (
                    not isinstance(requests, list)
                    or len(requests) != 1
                    or not isinstance(requests[0], dict)
                    or requests[0].get("method") != "GET"
                    or requests[0].get("path") != "/load/fan-in"
                    or requests[0].get("body_base64") != ""
                ):
                    raise ParityError(
                        f"{case_id}: load fan-in must declare one empty GET stimulus"
                    )
            elif (
                not isinstance(requests, list) or len(requests) < 2
                or any(not isinstance(request, dict) for request in requests)
            ):
                raise ParityError(f"{case_id}: request sequence requires at least two requests")
            if kind == "http3" and len(requests) > 128:
                raise ParityError(f"{case_id}: HTTP/3 sequences are bounded to 128 requests")
            if kind == "http3" and case["operation"] == "http.keepalive-sequence" and (
                case.get("verification", "oracle-parity") != "oracle-parity"
                or any("expect_response_error" in request for request in requests)
            ):
                raise ParityError(f"{case_id}: ordinary HTTP/3 sequences require live oracle parity without injected resets")
            if kind == "http3" and case["operation"] == "http3.request-task-recovery" and (
                case.get("verification") != "fault-contract"
                or case.get("fault", {}).get("contract")
                != "http3-request-task-error-before-peer-close-followup-200"
            ):
                raise ParityError(f"{case_id}: HTTP/3 request-task recovery requires its target-only live diagnostic contract")
            if case["operation"] == "http.application-task-cleanup-observer" and (
                kind != "http1"
                or case.get("verification", "oracle-parity") != "oracle-parity"
                or [request.get("path") for request in requests] != [
                    "/task-cleanup-hold?complete-response=1",
                    "/task-cleanup-status", "/task-cleanup-cancel", "/task-cleanup-status",
                ]
            ):
                raise ParityError(
                    f"{case_id}: task-cleanup observer requires its live hold, status, cancel, and status control"
                )
            if case["operation"] == "lifespan.state-shallow-copy" and (
                kind != "lifespan-state-copy-rehash"
                or case.get("verification", "oracle-parity") != "oracle-parity"
                or [request.get("path") for request in requests] != [
                    "/state-copy-arm", "/state-copy-observe", "/state-copy-observe",
                ]
            ):
                raise ParityError(
                    f"{case_id}: state shallow-copy parity requires its isolated key-rehash observation workflow"
                )
            for index, request in enumerate(requests):
                request_keys = {"method", "path", "headers", "body_base64"}
                if "fault_after_response_headers" in request:
                    request_keys.add("fault_after_response_headers")
                    if kind == "http3":
                        raise ParityError(f"{case_id}: HTTP/3 sequences do not support mid-response fault controls")
                exact_keys(request, request_keys, f"{case_id}.request_sequence[{index}]")
                if "fault_after_response_headers" in request and not isinstance(
                    request["fault_after_response_headers"], bool
                ):
                    raise ParityError(
                        f"{case_id}: fault_after_response_headers must be a boolean"
                    )
                try:
                    base64.b64decode(request["body_base64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid request-sequence body base64") from error
                if not isinstance(request["path"], str) or not request["path"].startswith("/"):
                    raise ParityError(f"{case_id}: request-sequence paths must be origin-form")
                if not isinstance(request["headers"], list) or any(
                    not isinstance(header, list)
                    or len(header) != 2
                    or not all(isinstance(part, str) for part in header)
                    for header in request["headers"]
                ):
                    raise ParityError(f"{case_id}: request-sequence headers must be pairs of strings")
        elif "request" in case and supports_http_request:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "request"}, case_id)
            request = case["request"]
            request_keys = {"method", "path", "headers", "body_base64"}
            if "http_version" in request:
                request_keys.add("http_version")
                if request["http_version"] not in {"1.0", "1.1"}:
                    raise ParityError(f"{case_id}: only HTTP/1.0 and HTTP/1.1 versions are valid inputs")
                if kind != "http1":
                    raise ParityError(f"{case_id}: explicit HTTP versions are currently scoped to HTTP/1.1 transport")
            if "omit_host" in request:
                request_keys.add("omit_host")
                if request["omit_host"] is not True:
                    raise ParityError(f"{case_id}: omit_host must be true when present")
                if kind != "http1" or request.get("http_version") != "1.0":
                    raise ParityError(f"{case_id}: omitting Host is currently scoped to HTTP/1.0")
            if "omit_authority" in request:
                request_keys.add("omit_authority")
                if request["omit_authority"] is not True or kind != "http2":
                    raise ParityError(f"{case_id}: omit_authority is currently scoped to HTTP/2")
                if not any(name.lower() == "host" for name, _ in request["headers"]):
                    raise ParityError(f"{case_id}: omitting :authority requires a Host header")
            if "authority" in request:
                request_keys.add("authority")
                authority = request["authority"]
                if (
                    kind not in {"http2", "http3"}
                    or not isinstance(authority, str)
                    or not authority
                    or any(character.isspace() for character in authority)
                    or any(character in authority for character in "/?#")
                ):
                    raise ParityError(
                        f"{case_id}: authority must be a nonempty HTTP/2 or HTTP/3 authority"
                    )
                if request.get("omit_authority"):
                    raise ParityError(f"{case_id}: authority cannot be combined with omit_authority")
            if "raw_headers" in request:
                request_keys.add("raw_headers")
                if request["raw_headers"] is not True or kind != "http1":
                    raise ParityError(f"{case_id}: raw_headers is currently scoped to HTTP/1.1")
                if request.get("http_version", "1.1") != "1.1":
                    raise ParityError(f"{case_id}: raw_headers requires HTTP/1.1")
                if any(name.lower() == "host" for name, _ in request["headers"]):
                    raise ParityError(f"{case_id}: raw_headers adapter supplies Host")
            if "absolute_target" in request:
                request_keys.add("absolute_target")
                if request["absolute_target"] is not True or kind != "http1":
                    raise ParityError(
                        f"{case_id}: absolute_target is currently scoped to HTTP/1.1"
                    )
                if any(name.lower() == "host" for name, _ in request["headers"]):
                    raise ParityError(
                        f"{case_id}: absolute_target requires the Host header to be omitted"
                    )
                if "http_version" in request or "omit_host" in request:
                    raise ParityError(
                        f"{case_id}: absolute_target cannot be combined with another HTTP version"
                    )
            if "hold_open_for_shutdown" in request:
                request_keys.add("hold_open_for_shutdown")
                if request["hold_open_for_shutdown"] is not True or kind != "http3":
                    raise ParityError(
                        f"{case_id}: holding a connection for shutdown is supported only for HTTP/3"
                    )
            if "hold_response_stream_for_shutdown" in request:
                request_keys.add("hold_response_stream_for_shutdown")
                if (
                    request["hold_response_stream_for_shutdown"] is not True
                    or kind != "http3"
                    or request.get("hold_open_for_shutdown") is not True
                    or request.get("path") != "/stream-shutdown-hold"
                ):
                    raise ParityError(
                        f"{case_id}: holding a response stream for shutdown requires the HTTP/3 held-response workflow"
                    )
            if "abort_response_after_headers" in request:
                request_keys.add("abort_response_after_headers")
                if request["abort_response_after_headers"] is not True or kind != "http3":
                    raise ParityError(
                        f"{case_id}: abort_response_after_headers is supported only for HTTP/3"
                    )
            if "expect_response_error" in request:
                request_keys.add("expect_response_error")
                if request["expect_response_error"] is not True or kind != "http3":
                    raise ParityError(
                        f"{case_id}: expect_response_error is supported only for HTTP/3 reset observations"
                    )
            if "leave_upload_open_until_response" in request:
                request_keys.add("leave_upload_open_until_response")
                if request["leave_upload_open_until_response"] is not True or kind != "http3":
                    raise ParityError(
                        f"{case_id}: leave_upload_open_until_response is supported only for HTTP/3"
                    )
                if request["method"] != "POST" or not request["body_base64"]:
                    raise ParityError(
                        f"{case_id}: an open HTTP/3 upload needs a nonempty POST body"
                    )
                content_lengths = [
                    value for name, value in request["headers"]
                    if name.lower() == "content-length"
                ]
                body_length = len(base64.b64decode(request["body_base64"], validate=True))
                if len(content_lengths) != 1 or not content_lengths[0].isdigit() or int(content_lengths[0]) <= body_length:
                    raise ParityError(
                        f"{case_id}: an open HTTP/3 upload needs a Content-Length larger than its body"
                    )
            if "empty_data_frame_before_body" in request:
                request_keys.add("empty_data_frame_before_body")
                if request["empty_data_frame_before_body"] is not True or kind != "http3":
                    raise ParityError(
                        f"{case_id}: empty_data_frame_before_body is supported only for HTTP/3"
                    )
                if request["method"] != "POST" or not request["body_base64"]:
                    raise ParityError(
                        f"{case_id}: an empty HTTP/3 DATA frame probe needs a nonempty POST body"
                    )
            if "abort_after_body" in request:
                request_keys.add("abort_after_body")
                if request["abort_after_body"] is not True or kind != "http3":
                    raise ParityError(f"{case_id}: abort_after_body is supported only for HTTP/3")
            if "invalid_alpn" in request:
                request_keys.add("invalid_alpn")
                if request["invalid_alpn"] is not True or kind != "http3":
                    raise ParityError(f"{case_id}: invalid_alpn is supported only for HTTP/3")
            if "close_error_code" in request:
                request_keys.add("close_error_code")
                code = request["close_error_code"]
                if kind != "http3" or type(code) is not int or not 0 <= code < 2**62:
                    raise ParityError(f"{case_id}: close_error_code must be an HTTP/3 u62 wire code")
                if set(request) - {
                    "method", "path", "headers", "body_base64", "close_error_code"
                }:
                    raise ParityError(f"{case_id}: peer closure requires a completed ordinary request")
            if operation in {"http3.peer-close", "http3.peer-close-registered"} and (
                kind != "http3" or "close_error_code" not in request
            ):
                raise ParityError(f"{case_id}: HTTP/3 peer-close requires an explicit close_error_code")
            exact_keys(request, request_keys, f"{case_id}.request")
            try:
                base64.b64decode(request["body_base64"], validate=True)
            except (ValueError, TypeError) as error:
                raise ParityError(f"{case_id}: invalid request body base64") from error
            if not isinstance(request["path"], str) or not request["path"].startswith("/"):
                raise ParityError(f"{case_id}: request path must be origin-form")
            if not isinstance(request["headers"], list) or any(
                not isinstance(header, list)
                or len(header) != 2
                or not all(isinstance(part, str) for part in header)
                for header in request["headers"]
            ):
                raise ParityError(f"{case_id}: headers must be pairs of strings")
        elif kind in {"websocket", "websocket-tls"}:
            case_keys = {"case_id", "profile", "operation", "covers", "websocket"}
            if "load" in case:
                case_keys.add("load")
                validate_load_input(case, "websocket")
                if case.get("verification", "oracle-parity") != "oracle-parity" or "fault" in case:
                    raise ParityError(f"{case_id}: WebSocket load workflows require live oracle parity")
            elif case["operation"] == "websocket.concurrent-session-load":
                raise ParityError(f"{case_id}: concurrent WebSocket sessions require a load input")
            exact_case_keys(case, case_keys, case_id)
            websocket = case["websocket"]
            websocket_keys = {"path", "subprotocols", "messages"}
            if case.get("operation") == "websocket.concurrent-session-load":
                if websocket.get("path") != "/ws/load" or websocket.get("messages") != []:
                    raise ParityError(
                        f"{case_id}: concurrent WebSocket sessions require the load echo workflow"
                    )
            if "shutdown" in websocket:
                websocket_keys.add("shutdown")
                if websocket["shutdown"] is not True:
                    raise ParityError(f"{case_id}: websocket shutdown workflow must be true")
            if "drop_during_upgrade" in websocket:
                websocket_keys.add("drop_during_upgrade")
                if websocket["drop_during_upgrade"] is not True or "shutdown" in websocket:
                    raise ParityError(f"{case_id}: drop_during_upgrade is a standalone reset workflow")
            if "shutdown_during_upgrade" in websocket:
                websocket_keys.add("shutdown_during_upgrade")
                if websocket["shutdown_during_upgrade"] is not True or websocket.get("shutdown") is not True:
                    raise ParityError(f"{case_id}: shutdown_during_upgrade requires shutdown=true")
            if "expect_close" in websocket:
                websocket_keys.add("expect_close")
                if websocket["expect_close"] is not True:
                    raise ParityError(f"{case_id}: expect_close must be true when present")
            if "send_only" in websocket:
                websocket_keys.add("send_only")
                if websocket["send_only"] is not True:
                    raise ParityError(f"{case_id}: send_only must be true when present")
            if "client_close" in websocket:
                websocket_keys.add("client_close")
                exact_keys(websocket["client_close"], {"code", "reason"}, f"{case_id}.websocket.client_close")
                if not isinstance(websocket["client_close"]["code"], int):
                    raise ParityError(f"{case_id}: client close code must be an integer")
                if not isinstance(websocket["client_close"]["reason"], str):
                    raise ParityError(f"{case_id}: client close reason must be text")
            if "abrupt_disconnect" in websocket:
                websocket_keys.add("abrupt_disconnect")
                if websocket["abrupt_disconnect"] is not True:
                    raise ParityError(f"{case_id}: abrupt_disconnect must be true when present")
            if "ping_payload" in websocket:
                websocket_keys.add("ping_payload")
                if not isinstance(websocket["ping_payload"], str):
                    raise ParityError(f"{case_id}: ping_payload must be text")
            if "headers" in websocket:
                websocket_keys.add("headers")
                if not isinstance(websocket["headers"], list) or any(
                    not isinstance(header, list)
                    or len(header) != 2
                    or not all(isinstance(part, str) for part in header)
                    for header in websocket["headers"]
                ):
                    raise ParityError(f"{case_id}: WebSocket headers must be pairs of strings")
            if "followup_path" in websocket:
                websocket_keys.add("followup_path")
                if not isinstance(websocket["followup_path"], str) or not websocket["followup_path"].startswith("/"):
                    raise ParityError(f"{case_id}: WebSocket followup_path must be origin-form")
            if "wait_for_app_event" in websocket:
                websocket_keys.add("wait_for_app_event")
                if (
                    not isinstance(websocket["wait_for_app_event"], str)
                    or not websocket["wait_for_app_event"]
                    or case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.final-frame-drain"
                    or websocket.get("expect_close") is not True
                    or websocket.get("messages") != []
                ):
                    raise ParityError(
                        f"{case_id}: deferred WebSocket reads require the final-frame drain workflow"
                    )
            if "receive_buffer_bytes" in websocket:
                websocket_keys.add("receive_buffer_bytes")
                if (
                    type(websocket["receive_buffer_bytes"]) is not int
                    or not 1 <= websocket["receive_buffer_bytes"] <= 65535
                    or "wait_for_app_event" not in websocket
                ):
                    raise ParityError(
                        f"{case_id}: receive_buffer_bytes requires a bounded deferred-read workflow"
                    )
            exact_keys(websocket, websocket_keys, f"{case_id}.websocket")
            for message in websocket["messages"]:
                exact_keys(message, {"kind", "value"}, f"{case_id}.websocket message")
                if message["kind"] == "binary_base64":
                    base64.b64decode(message["value"], validate=True)
                elif message["kind"] != "text":
                    raise ParityError(f"{case_id}: unsupported WebSocket message kind")
        elif "lifecycle" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "lifecycle"}, case_id)
            lifecycle_keys = {"graceful_timeout_seconds"}
            if "unfinished_tls_handshake" in case["lifecycle"]:
                lifecycle_keys.add("unfinished_tls_handshake")
                if (case["lifecycle"]["unfinished_tls_handshake"] is not True
                    or case["profile"] != "lifecycle-tls"
                    or case["operation"] != "lifespan.tls-handshake-graceful-shutdown"):
                    raise ParityError(f"{case_id}: unfinished TLS handshake requires its TLS lifecycle operation")
            if "state_path" in case["lifecycle"]:
                lifecycle_keys.add("state_path")
            if "hold_path" in case["lifecycle"]:
                lifecycle_keys.add("hold_path")
            if "background_path" in case["lifecycle"]:
                lifecycle_keys.add("background_path")
                if (
                    case["profile"] != "lifecycle-owned-loop"
                    or case["operation"] != "lifespan.post-response-application-shutdown"
                    or case["lifecycle"]["background_path"] != "/post-response-hold"
                    or set(case["lifecycle"])
                    != {"state_path", "background_path", "graceful_timeout_seconds"}
                    or case["lifecycle"]["state_path"] != "/state"
                    or case["lifecycle"]["graceful_timeout_seconds"] != 1
                ):
                    raise ParityError(
                        f"{case_id}: post-response shutdown requires the owned-loop public-API workflow"
                    )
            elif (
                case["profile"] == "lifecycle-owned-loop"
                or case["operation"] == "lifespan.post-response-application-shutdown"
            ):
                raise ParityError(f"{case_id}: owned-loop lifecycle requires a background request")
            if "callback_path" in case["lifecycle"]:
                lifecycle_keys.add("callback_path")
                if (
                    case["operation"] != "lifespan.eager-registration-failure-cleanup"
                    or case.get("fault", {}).get("contract")
                    not in EAGER_APPLICATION_CLEANUP_CONTRACTS
                ):
                    raise ParityError(f"{case_id}: callback lifecycle path requires eager application cleanup")
            if "cleanup_delay_seconds" in case["lifecycle"]:
                lifecycle_keys.add("cleanup_delay_seconds")
                if (
                    case["operation"] != "lifespan.eager-registration-failure-cleanup"
                    or case["profile"] != "lifecycle-owned-loop-eager"
                    or case["lifecycle"]["cleanup_delay_seconds"] not in {0.5, 5}
                    or case.get("verification") != "fault-contract"
                ):
                    raise ParityError(f"{case_id}: asynchronous cleanup delay requires the eager owning-loop fault workflow")
            if "stream_path" in case["lifecycle"]:
                lifecycle_keys.add("stream_path")
            if "stream_count" in case["lifecycle"]:
                lifecycle_keys.add("stream_count")
                if (
                    type(case["lifecycle"]["stream_count"]) is not int
                    or not 2 <= case["lifecycle"]["stream_count"] <= 32
                    or case["operation"] != "lifespan.concurrent-stream-zero-timeout-shutdown"
                ):
                    raise ParityError(
                        f"{case_id}: concurrent shutdown streams require 2..32 streams and the zero-timeout workflow"
                    )
            if "idle_transport_prefix_base64" in case["lifecycle"]:
                lifecycle_keys.add("idle_transport_prefix_base64")
                if (
                    case["profile"] not in {"lifecycle", "lifecycle-tls"}
                    or case["operation"] != "lifespan.active-stream-graceful-drain"
                ):
                    raise ParityError(
                        f"{case_id}: idle transport prefix requires the HTTP/1.1 or TLS graceful-drain workflow"
                    )
                try:
                    prefix = base64.b64decode(
                        case["lifecycle"]["idle_transport_prefix_base64"], validate=True
                    )
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid idle transport prefix base64") from error
                if not prefix:
                    raise ParityError(f"{case_id}: idle transport prefix must contain bytes")
            if "reset_connection_after_shutdown" in case["lifecycle"]:
                lifecycle_keys.add("reset_connection_after_shutdown")
                if case["lifecycle"]["reset_connection_after_shutdown"] is not True:
                    raise ParityError(f"{case_id}: reset_connection_after_shutdown must be true when present")
            if ("state_path" in case["lifecycle"]) == ("stream_path" in case["lifecycle"]):
                raise ParityError(f"{case_id}: lifecycle requires exactly one of state_path or stream_path")
            if "keep_alive_state_connection" in case["lifecycle"]:
                lifecycle_keys.add("keep_alive_state_connection")
                if case["lifecycle"]["keep_alive_state_connection"] is not True:
                    raise ParityError(f"{case_id}: keep_alive_state_connection must be true when present")
            if case["operation"] == "lifespan.idle-keepalive-graceful-shutdown":
                if (
                    case["profile"] != "lifecycle"
                    or case["lifecycle"].get("keep_alive_state_connection") is not True
                    or "hold_path" in case["lifecycle"]
                ):
                    raise ParityError(
                        f"{case_id}: idle keep-alive shutdown requires a persistent state connection without a held request"
                    )
            elif "keep_alive_state_connection" in case["lifecycle"]:
                raise ParityError(
                    f"{case_id}: keep_alive_state_connection is only supported by the idle keep-alive shutdown operation"
                )
            if case["operation"] == "lifespan.active-stream-graceful-drain":
                if (
                    case["profile"] not in {"lifecycle", "lifecycle-tls"}
                    or case["lifecycle"].get("stream_path") != "/stream-shutdown-hold"
                    or "hold_path" in case["lifecycle"]
                    or "keep_alive_state_connection" in case["lifecycle"]
                    or "reset_connection_after_shutdown" in case["lifecycle"]
                    or "idle_transport_prefix_base64" not in case["lifecycle"]
                ):
                    raise ParityError(
                        f"{case_id}: active-stream graceful drain requires the dedicated held-stream workflow"
                    )
            elif case["operation"] == "lifespan.concurrent-stream-zero-timeout-shutdown":
                if (
                    case["profile"] != "lifecycle"
                    or case["lifecycle"].get("stream_path") != "/stream-shutdown-hold"
                    or case["lifecycle"].get("stream_count") is None
                    or case["lifecycle"].get("graceful_timeout_seconds") != 0
                    or case["lifecycle"].get("reset_connection_after_shutdown") is not True
                    or "idle_transport_prefix_base64" in case["lifecycle"]
                    or "hold_path" in case["lifecycle"]
                ):
                    raise ParityError(
                        f"{case_id}: zero-timeout shutdown requires concurrent held HTTP/1.1 response streams"
                    )
            elif case["operation"] == "lifespan.active-stream-reset-during-shutdown":
                if (
                    case["profile"] not in {"lifecycle", "lifecycle-tls"}
                    or case["lifecycle"].get("stream_path")
                    not in {"/stream-shutdown-hold", "/stream-shutdown-reset-large"}
                    or case["lifecycle"].get("reset_connection_after_shutdown") is not True
                    or "hold_path" in case["lifecycle"]
                    or "keep_alive_state_connection" in case["lifecycle"]
                ):
                    raise ParityError(
                        f"{case_id}: reset during shutdown requires the dedicated held-stream workflow"
                    )
            elif case["operation"] == "lifespan.hyper-connection-write-error-during-shutdown":
                if (
                    case["profile"] not in {"lifecycle", "lifecycle-tls"}
                    or case["lifecycle"].get("stream_path") != "/stream-shutdown-hold"
                    or case.get("verification") != "fault-contract"
                    or case.get("fault", {}).get("contract")
                    != "server-hyper-connection-error-during-shutdown"
                ):
                    raise ParityError(
                        f"{case_id}: Hyper connection error requires a fault-contract held-stream workflow"
                    )
            elif "stream_path" in case["lifecycle"]:
                raise ParityError(
                    f"{case_id}: stream_path is only supported by a declared active-stream shutdown operation"
                )
            if (
                case["operation"] not in {
                    "lifespan.active-stream-reset-during-shutdown",
                    "lifespan.concurrent-stream-zero-timeout-shutdown",
                }
                and "reset_connection_after_shutdown" in case["lifecycle"]
            ):
                raise ParityError(
                    f"{case_id}: reset_connection_after_shutdown is only supported by the reset-during-shutdown operation"
                )
            exact_keys(case["lifecycle"], lifecycle_keys, f"{case_id}.lifecycle")
        elif "startup_failure" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "startup_failure"}, case_id)
            exact_keys(case["startup_failure"], {"expect_failed"}, f"{case_id}.startup_failure")
            if case["startup_failure"]["expect_failed"] is not True:
                raise ParityError(f"{case_id}: startup-failure workflow must expect failure")
        elif "startup_fallback" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "startup_fallback"}, case_id)
            exact_keys(case["startup_fallback"], {"followup_path"}, f"{case_id}.startup_fallback")
            if (
                not isinstance(case["startup_fallback"]["followup_path"], str)
                or not case["startup_fallback"]["followup_path"].startswith("/")
            ):
                raise ParityError(f"{case_id}: startup fallback follow-up path must be origin-form")
        elif kind == "http1-disconnect":
            raise ParityError("disconnect cases must use the http1 profile and disconnect input shape")
        else:
            raise ParityError(f"{case_id}: unsupported parity workflow shape")

    missing_operations = sorted(operation for operation, count in operation_case_counts.items() if count == 0)
    missing_profiles = sorted(profile for profile, count in profile_case_counts.items() if count == 0)
    if missing_operations or missing_profiles:
        raise ParityError(f"unrepresented manifest entries: operations={missing_operations}, profiles={missing_profiles}")
    combined_inputs = {"schema": INPUT_SCHEMA, "cases": input_cases}
    return manifest, combined_inputs, indexed_paths


def runtime_identity(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    actual = {}
    for oracle in manifest["oracles"]:
        requirements = [(oracle["id"], oracle["version"])]
        requirements.extend((component["id"], component["version"]) for component in oracle["components"])
        for distribution, required in requirements:
            try:
                observed = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError as error:
                raise ParityError(f"required reference dependency is missing: {distribution}") from error
            if observed != required:
                raise ParityError(f"{distribution} version mismatch: expected {required}, found {observed}")
            actual[distribution] = observed
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
    rustc = subprocess.run(["rustc", "--version"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    native_extension = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
    try:
        native_extension_path = str(native_extension.relative_to(ROOT))
    except ValueError:
        native_extension_path = str(native_extension)
    return (
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "rustc": rustc,
            "dependencies": actual,
        },
        {
            "revision": revision,
            "dirty": dirty,
            "native_extension": {
                "path": native_extension_path,
                "sha256": sha256(native_extension),
            },
            "cargo_lock_sha256": sha256(ROOT / "Cargo.lock"),
            "source_sha256": sha256(ROOT / "src/lib.rs"),
        },
    )


def free_port(*, tcp_and_udp: bool = False) -> int:
    for _ in range(128):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            try:
                tcp.bind(("127.0.0.1", 0))
                port = tcp.getsockname()[1]
                if tcp_and_udp:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                        udp.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError("could not find an available test port")


def make_certificate(directory: Path) -> tuple[Path, Path, Path]:
    leaf_certificate = directory / "server-leaf.pem"
    certificate = directory / "server-chain.pem"
    key = directory / "server-key.pem"
    ca_certificate = directory / "parity-ca.pem"
    ca_key = directory / "parity-ca-key.pem"
    csr = directory / "server.csr"
    extensions = directory / "server-extensions.cnf"
    extensions.write_text(
        "[server]\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-keyout", str(ca_key), "-out", str(ca_certificate),
            "-subj", "/CN=uvicorn-rs parity test CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            "-addext", "subjectKeyIdentifier=hash",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    subprocess.run(
        [
            "openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(csr), "-subj", "/CN=localhost",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    subprocess.run(
        [
            "openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_certificate),
            "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(leaf_certificate),
            "-days", "2", "-sha256", "-extfile", str(extensions), "-extensions", "server",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    certificate.write_bytes(leaf_certificate.read_bytes() + ca_certificate.read_bytes())
    return certificate, key, ca_certificate


def build_h3_client() -> Path:
    subprocess.run(
        [
            "cargo", "build", "--quiet", "--release", "--manifest-path",
            "tools/http3-probe/Cargo.toml", "--bin", "parity-http3",
        ],
        cwd=ROOT,
        check=True,
        timeout=300,
    )
    return ROOT / "tools" / "http3-probe" / "target" / "release" / "parity-http3"


def prebuilt_h3_client() -> Path:
    client = ROOT / "tools" / "http3-probe" / "target" / "release" / "parity-http3"
    if not client.is_file():
        raise ParityError(f"prebuild the HTTP/3 parity client before freezing identity: {client}")
    return client


def start_server(
    server_id: str,
    profile: dict[str, Any],
    graceful_timeout_seconds: int,
    port: int,
    events_path: Path,
    certificate: Path | None,
    key: Path | None,
    config_path: Path,
    expect_startup_failure: bool = False,
    coverage_profile_dir: Path | None = None,
    coverage_fault_control_path: Path | None = None,
    lifespan_mode_override: str | None = None,
    async_cleanup_delay_seconds: float = 0.5,
    observe_connection_errors: bool = False,
) -> dict[str, Any]:
    profile_id = profile["id"]
    env = os.environ.copy()
    # Shutdown workflows restart a profile in the same temporary directory.
    # Readiness and request checkpoints must belong to the new process.
    events_path.write_text("", encoding="utf-8")
    env["ASGI_PARITY_EVENTS"] = str(events_path)
    stream_release_path = events_path.with_suffix(".stream-release")
    stream_release_path.unlink(missing_ok=True)
    env["ASGI_PARITY_STREAM_RELEASE"] = str(stream_release_path)
    if profile_id == "websocket-tls":
        env["ASGI_PARITY_TRACE_WEBSOCKET_SCOPE"] = "1"
    if server_id == "uvicorn-rs" and coverage_profile_dir is not None:
        coverage_profile_dir.mkdir(parents=True, exist_ok=True)
        env["LLVM_PROFILE_FILE"] = str(coverage_profile_dir / "%p-%m.profraw")
    if server_id == "uvicorn-rs" and coverage_fault_control_path is not None:
        env["UVICORN_RS_COVERAGE_FAULT_FILE"] = str(coverage_fault_control_path)
    api_control_path = None
    api_snapshot_path = None
    lifespan_modes = {
        "lifespan-subclass-event-types": "subclass-event-types",
        "lifecycle-owned-loop-eager": "eager-owned-loop",
        "lifespan-state-copy-rehash": "state-copy-rehash",
        "lifespan-no-support": "unsupported",
        "lifespan-retained-send": "startup-return-retains-send",
        "lifespan-no-support-error": "unsupported-error",
        "lifespan-fault-start-event-channel-closed": "unsupported-error",
        "lifespan-no-support-error-retained": "unsupported-error-retains-send",
        "lifespan-receive-wrong-signature": "receive-wrong-signature",
        "lifespan-invalid-startup-event": "invalid-startup-event",
        "lifespan-missing-startup-event-type": "missing-startup-event-type",
        "lifespan-non-string-startup-event-type": "non-string-startup-event-type",
        "lifespan-startup-failed": "startup-failed",
        "lifespan-startup-failed-subclass": "startup-failed-subclass",
        "lifespan-startup-failed-empty": "startup-failed-empty",
        "lifespan-unexpected-startup-event": "unexpected-startup-event",
        "lifespan-shutdown-failed": "shutdown-failed",
        "lifespan-shutdown-failed-subclass": "shutdown-failed-subclass",
        "lifespan-shutdown-failed-empty": "shutdown-failed-empty",
        "lifespan-shutdown-returns": "shutdown-returns",
        "lifespan-shutdown-returns-retained": "shutdown-returns-retains-send",
        "lifespan-shutdown-raises": "shutdown-raises",
        "lifespan-shutdown-complete-then-raises": "shutdown-complete-then-raises",
        "lifespan-fault-asgi-shutdown-task-join-after-complete": "shutdown-complete-pending",
        "lifespan-shutdown-unexpected-event": "shutdown-unexpected-event",
        "lifespan-fault-shutdown-cancel": "shutdown-cancel-pending",
        "lifespan-startup-complete-then-returns": "startup-complete-then-return",
        "lifespan-fault-asgi-startup-failed": "startup-failed",
        "lifespan-fault-asgi-shutdown-failed": "shutdown-failed",
    }
    lifespan_mode = lifespan_modes.get(profile_id, "complete")
    if profile_id.startswith("lifespan-fault-asgi-startup-failed"):
        lifespan_mode = "startup-failed"
    elif profile_id.startswith("lifespan-fault-asgi-shutdown-failed"):
        lifespan_mode = "shutdown-failed"
    if profile_id == "lifespan-fault-asgi-shutdown-task-join-after-complete":
        lifespan_mode = "shutdown-complete-pending"
    env["ASGI_PARITY_LIFESPAN_MODE"] = lifespan_mode_override or lifespan_mode
    common = ["--host", "127.0.0.1", "--port", str(port)]
    startup_api_profiles = {
        "startup-partial-tls-api",
        "startup-missing-certificate",
        "startup-invalid-host",
        "startup-empty-certificate",
        "startup-invalid-certificate-pem",
        "startup-missing-private-key",
        "startup-empty-private-key",
        "startup-invalid-private-key-pem",
        "startup-mismatched-private-key",
    }
    if profile_id in startup_api_profiles:
        command = [
            sys.executable,
            str(ROOT / "tests/parity/startup_probe.py"),
            server_id,
            profile_id,
            str(certificate or ""),
            str(key or ""),
        ]
    elif profile_id in {"lifecycle-owned-loop", "lifecycle-owned-loop-eager"} or (
        server_id == "uvicorn-rs" and profile_id == "lifecycle-server-api"
    ):
        api_control_path = events_path.with_suffix(".shutdown")
        api_control_path.unlink(missing_ok=True)
        command = [
            sys.executable,
            str(ROOT / "tests/parity/server_api_probe.py"),
            str(port),
            str(graceful_timeout_seconds),
            str(api_control_path),
        ]
        if profile_id in {"lifecycle-owned-loop", "lifecycle-owned-loop-eager"}:
            api_snapshot_path = events_path.with_suffix(".server-api-snapshot.json")
            api_snapshot_path.unlink(missing_ok=True)
            command.extend(["--server", server_id, "--snapshot", str(api_snapshot_path)])
            if profile_id == "lifecycle-owned-loop-eager":
                command.extend(["--task-factory", "eager", "--cleanup-delay", str(async_cleanup_delay_seconds)])
    elif server_id == "uvicorn-rs":
        command = [sys.executable, "-m", "uvicorn_rs", APP, *common, "--loop", "uvloop"]
        if certificate and key:
            command.extend(["--certfile", str(certificate), "--keyfile", str(key)])
        command.extend(["--graceful-timeout", str(graceful_timeout_seconds)])
    elif server_id == "uvicorn":
        # Keep TLS WebSocket handshake progress in hosted diagnostics when the
        # reference adapter stalls before ASGI dispatch.
        websocket_tls_debug = (
            profile_id == "websocket-tls"
            and env.get("ASGI_PARITY_UVICORN_WEBSOCKET_DEBUG") == "1"
        )
        command = [
            sys.executable, "-m", "uvicorn", APP, *common, "--loop", "uvloop",
            # Follow Uvicorn's stock selector for the pinned reference version.
            # Since Uvicorn 0.50, `auto` selects its maintained SansIO adapter
            # when websockets is installed; forcing `websockets` uses the
            # deprecated legacy adapter and changes the reference behavior.
            "--http", "httptools", "--interface", "asgi3", "--ws", "auto",
            "--lifespan", "auto",
            "--log-level", "debug" if websocket_tls_debug else "error",
            "--no-server-header", "--timeout-graceful-shutdown",
            str(graceful_timeout_seconds),
        ]
        if certificate and key:
            command.extend(["--ssl-certfile", str(certificate), "--ssl-keyfile", str(key)])
    elif server_id == "hypercorn":
        command = [
            sys.executable, "-m", "hypercorn", f"asgi:{APP}", "--bind", f"127.0.0.1:{port}",
            "--worker-class", "uvloop", "--log-level",
            "error" if observe_connection_errors else "critical", "--access-logfile", "/dev/null",
            "--certfile", str(certificate), "--keyfile", str(key), "--config", str(config_path),
        ]
        if profile_id == "http3":
            command.extend(["--quic-bind", f"127.0.0.1:{port}"])
    else:
        raise ParityError(f"unknown server adapter: {server_id}")

    log = tempfile.TemporaryFile(mode="w+t")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        text=True,
    )
    if expect_startup_failure:
        # Startup failure probes launch Python in separate processes; allow
        # headroom for slower CI hosts before classifying a still-running
        # process as a server behavior mismatch.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.05)
        if process.poll() is not None:
            log.seek(0)
            captured_log = log.read()
            output = captured_log[-6000:]
            log.close()
            return {
                "id": server_id,
                "process": process,
                "port": port,
                "events": events_path,
                "log": log,
                "startup_failed": (
                    process.returncode != 0
                    and (
                        profile_id not in startup_api_profiles
                        or "ASGI_PARITY_SERVER_STARTUP_FAILURE" in output
                    )
                ),
                "startup_output": output,
                "captured_log": captured_log,
            }
        stopped_server = {"process": process, "log": log}
        stop_server(stopped_server)
        return {
            "id": server_id,
            "process": process,
            "port": port,
            "events": events_path,
            "log": log,
            "startup_failed": False,
            "startup_output": "server remained running after the startup-failure window",
            "captured_log": stopped_server["captured_log"],
        }
    deadline = time.monotonic() + 20
    lifespan_mode = env.get("ASGI_PARITY_LIFESPAN_MODE", "complete")
    startup_event_modes = {
        "complete",
        "subclass-event-types",
        "state-copy-rehash",
        "startup-complete-then-return",
        "shutdown-failed",
        "shutdown-failed-empty",
        "shutdown-failed-subclass",
        "shutdown-returns",
        "shutdown-returns-retains-send",
        "shutdown-raises",
        "shutdown-unexpected-event",
        "shutdown-cancel-pending",
    }
    wait_for_app_startup = (
        not expect_startup_failure
        and lifespan_mode in startup_event_modes
        and not (server_id == "uvicorn-rs" and profile_id == "lifespan-fault-receive-startup")
    )
    readiness_tls_context = None
    use_tls_readiness = profile_id in {"websocket-tls", "lifecycle-tls"} or (
        profile_id == "http3" and observe_connection_errors
    )
    if use_tls_readiness:
        readiness_tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        readiness_tls_context.check_hostname = False
        readiness_tls_context.verify_mode = ssl.CERT_NONE
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log.seek(0)
            output = log.read()[-6000:]
            log.close()
            raise ParityError(f"{server_id}/{profile_id} exited at startup ({process.returncode}):\n{output}")
        # For TLS profiles, avoid the raw TCP readiness probe until the ASGI
        # lifespan has completed. A probe that closes before sending TLS bytes
        # is an invalid handshake and can race the first real WebSocket client.
        if wait_for_app_startup and "lifespan.startup" not in read_events(events_path):
            time.sleep(0.05)
            continue
        if use_tls_readiness:
            # A bare TCP connect is not a valid readiness probe for this TLS
            # profile. Complete a harmless local HTTPS request before the
            # selected protocol operation begins.
            connection = http.client.HTTPSConnection(
                "127.0.0.1",
                port,
                timeout=1,
                context=readiness_tls_context,
            )
            try:
                connection.request("GET", "/__parity-readiness")
                response = connection.getresponse()
                response.read()
            except OSError:
                connection.close()
                time.sleep(0.05)
                continue
            connection.close()
            server = {
                "id": server_id,
                "process": process,
                "port": port,
                "events": events_path,
                "log": log,
                "startup_failed": False,
            }
            if api_control_path is not None:
                server["api_control_path"] = api_control_path
            if api_snapshot_path is not None:
                server["api_snapshot_path"] = api_snapshot_path
            if server_id == "uvicorn-rs" and coverage_fault_control_path is not None:
                server["coverage_fault_control_path"] = coverage_fault_control_path
            return server
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                server = {
                    "id": server_id,
                    "process": process,
                    "port": port,
                    "events": events_path,
                    "log": log,
                    "startup_failed": False,
                }
                if api_control_path is not None:
                    server["api_control_path"] = api_control_path
                if api_snapshot_path is not None:
                    server["api_snapshot_path"] = api_snapshot_path
                if server_id == "uvicorn-rs" and coverage_fault_control_path is not None:
                    server["coverage_fault_control_path"] = coverage_fault_control_path
                return server
        except OSError:
            time.sleep(0.05)
    stop_server({"process": process, "log": log})
    raise ParityError(f"{server_id}/{profile_id} did not open its TCP listener")


def stop_server(
    server: dict[str, Any], *, graceful: bool = False, signal_sent: bool = False
) -> tuple[int | None, str]:
    process: subprocess.Popen = server["process"]
    log = server["log"]
    if log.closed:
        return process.returncode, server.get("captured_log", "")[-6000:]
    if process.poll() is None:
        api_control_path = server.get("api_control_path")
        if api_control_path is not None:
            api_control_path.touch()
        elif not signal_sent:
            if graceful:
                process.terminate()
            else:
                process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    log.seek(0)
    text = log.read()
    log.close()
    # Lifecycle adapters can stop a process before profile finalization, and
    # profiles can restart several processes. Preserve the complete log so
    # validation cannot lose a panic when a handle is closed or a tail grows.
    server["captured_log"] = text
    return process.returncode, text[-6000:]


def rust_panic_issues(
    server: dict[str, Any], cases: list[dict[str, Any]], logs: str
) -> list[dict[str, Any]]:
    """Validate every Rust hook event against this process's coverage faults."""
    expected: Counter[str] = Counter()
    if server["id"] == "uvicorn-rs" and server.get("coverage_fault_control_path"):
        for case in cases:
            if case.get("verification") == "fault-contract":
                message = COVERAGE_PANIC_MESSAGES.get(case.get("fault", {}).get("point"))
                if message is not None:
                    expected[message] += 1

    observed: Counter[str] = Counter()
    issues = []
    lines = logs.splitlines()
    for index, line in enumerate(lines):
        if "panicked at" not in line:
            continue
        header = RUST_PANIC_HEADER.fullmatch(line)
        message = lines[index + 1] if index + 1 < len(lines) else None
        source = header.group("source") if header is not None else None
        # Source paths and hook messages must both match. In particular, a
        # known marker elsewhere in a log cannot excuse a separate panic.
        if (
            source is None
            or not (source == "src/lib.rs" or source.endswith("/src/lib.rs"))
            or message not in expected
        ):
            issues.append({
                "kind": "unexpected_rust_panic",
                "log_line": index + 1,
                "header": line,
                "message": message,
            })
            continue
        observed[message] += 1
    for message, count in expected.items():
        if observed[message] != count:
            issues.append({
                "kind": "coverage_panic_count_mismatch",
                "message": message,
                "expected": count,
                "observed": observed[message],
            })
    return issues


def read_events(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def wait_for_listener_closed(server: dict[str, Any], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server["process"].poll() is not None:
            return False
        try:
            probe = socket.create_connection(("127.0.0.1", server["port"]), timeout=0.05)
        except ConnectionRefusedError:
            return True
        except (socket.timeout, ConnectionResetError):
            # A stopped accept loop can fill the backlog while its listener
            # remains open. A close racing with connect can also reset the
            # probe. Retry until refusal; neither outcome proves closure.
            pass
        except OSError as error:
            raise ParityError(f"could not verify listener closure: {error}") from error
        else:
            probe.close()
        time.sleep(0.01)
    return False


def read_server_log(server: dict[str, Any]) -> str:
    """Read captured server output without disturbing later shutdown reporting."""
    log = server["log"]
    if log.closed:
        return server.get("captured_log", "")
    # Popen's inherited descriptor shares its write offset with this handle.
    # Seeking and restoring that offset can overwrite diagnostics emitted
    # during a live read; pread leaves the child's append position intact.
    log.flush()
    size = os.fstat(log.fileno()).st_size
    return os.pread(log.fileno(), size, 0).decode("utf-8", errors="replace")


def server_process_diagnostic(server: dict[str, Any]) -> dict[str, Any]:
    """Return bounded process state when a live adapter fails."""
    process: subprocess.Popen = server["process"]
    exit_code = process.poll()
    return {
        "pid": process.pid,
        "alive": exit_code is None,
        "exit_code": exit_code,
        "attempted_cases": [
            case["case_id"] for case in server.get("attempted_cases", [])[-8:]
        ],
    }


def read_server_api_snapshot(server: dict[str, Any]) -> dict[str, Any]:
    """Read the owning-loop observation recorded before any probe cleanup."""
    path = server.get("api_snapshot_path")
    if path is None or not path.exists():
        raise ParityError("public server API did not record a snapshot before probe cleanup")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    exact_keys(snapshot, {
        "server_task_finished", "serve_cancellation_propagated",
        "application_tasks_finished_before_probe_cleanup",
        "lifespan_tasks_finished_before_probe_cleanup", "loop_alive_after_server_return",
        "shutdown_elapsed_seconds", "lifespan_shutdown_completed", "application_events",
    }, "public server API snapshot")
    return snapshot


def response_observation(status: int, headers: list[tuple[str, str]], body: bytes) -> dict[str, Any]:
    content_type = next((value for name, value in headers if name.lower() == "content-type"), None)
    ordered_response_headers = [
        [name.lower(), value]
        for name, value in headers
        if name.lower().startswith("x-asgi-")
    ]
    response_header_values_by_name: dict[str, list[str]] = {}
    for name, value in ordered_response_headers:
        response_header_values_by_name.setdefault(name, []).append(value)
    return {
        "status": status,
        "content_type": content_type,
        "body_base64": base64.b64encode(body).decode("ascii"),
        "ordered_response_headers": ordered_response_headers,
        "response_header_values_by_name": [
            [name, values] for name, values in sorted(response_header_values_by_name.items())
        ],
        "connection_closed": False,
    }


def http1_request(
    port: int, request: dict[str, Any], *, ssl_context: ssl.SSLContext | None = None
) -> dict[str, Any]:
    body = base64.b64decode(request["body_base64"], validate=True)
    if request.get("absolute_target"):
        if ssl_context is not None:
            raise ParityError("the absolute-target adapter does not support TLS")
        return http1_absolute_request(port, request)
    if request.get("raw_headers"):
        return http1_raw_header_request(port, request, body, ssl_context=ssl_context)
    if request.get("omit_host", False):
        if ssl_context is not None:
            raise ParityError("the omit_host adapter does not support TLS")
        connection = socket.create_connection(("127.0.0.1", port), timeout=10)
        connection.settimeout(10)
        try:
            headers = list(request["headers"])
            if body and not any(name.lower() == "content-length" for name, _ in headers):
                headers.append(("Content-Length", str(len(body))))
            request_bytes = [
                f"{request['method']} {request['path']} HTTP/1.0\r\n",
                *(f"{name}: {value}\r\n" for name, value in headers),
                "\r\n",
            ]
            connection.sendall("".join(request_bytes).encode("ascii") + body)
            response = http.client.HTTPResponse(connection)
            response.begin()
            payload = response.read()
            return response_observation(response.status, response.getheaders(), payload)
        finally:
            connection.close()

    if ssl_context is None:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    else:
        connection = http.client.HTTPSConnection(
            "127.0.0.1", port, timeout=10, context=ssl_context
        )
    if request.get("http_version") == "1.0":
        connection._http_vsn = 10
        connection._http_vsn_str = "HTTP/1.0"
    try:
        connection.request(request["method"], request["path"], body=body, headers=dict(request["headers"]))
        try:
            response = connection.getresponse()
        except http.client.RemoteDisconnected:
            return {
                "status": None,
                "content_type": None,
                "body_base64": "",
                "connection_closed": True,
            }
        try:
            payload = response.read()
        except http.client.IncompleteRead as error:
            observation = response_observation(
                response.status,
                response.getheaders(),
                error.partial,
            )
            observation["connection_closed"] = True
            return observation
        return response_observation(response.status, response.getheaders(), payload)
    finally:
        connection.close()


def http1_raw_header_request(
    port: int,
    request: dict[str, Any],
    body: bytes,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    """Send ordered HTTP/1.1 header pairs without a mapping that folds duplicates."""
    connection = socket.create_connection(("127.0.0.1", port), timeout=10)
    connection.settimeout(10)
    if ssl_context is not None:
        connection = ssl_context.wrap_socket(connection, server_hostname="localhost")
    try:
        headers = list(request["headers"])
        headers.insert(0, ("Host", f"localhost:{port}"))
        if body and not any(name.lower() == "content-length" for name, _ in headers):
            headers.append(("Content-Length", str(len(body))))
        request_bytes = [f"{request['method']} {request['path']} HTTP/1.1\r\n"]
        request_bytes.extend(f"{name}: {value}\r\n" for name, value in headers)
        request_bytes.append("\r\n")
        connection.sendall("".join(request_bytes).encode("latin-1") + body)
        response = http.client.HTTPResponse(connection)
        try:
            response.begin()
        except http.client.RemoteDisconnected:
            return {
                "status": None,
                "content_type": None,
                "body_base64": "",
                "connection_closed": True,
            }
        try:
            payload = response.read()
        except http.client.IncompleteRead as error:
            observation = response_observation(
                response.status,
                response.getheaders(),
                error.partial,
            )
            observation["connection_closed"] = True
            return observation
        return response_observation(response.status, response.getheaders(), payload)
    finally:
        connection.close()


def http1_absolute_request(port: int, request: dict[str, Any]) -> dict[str, Any]:
    body = base64.b64decode(request["body_base64"], validate=True)
    target = f"http://127.0.0.1:{port}{request['path']}"
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    sock.settimeout(10)
    try:
        lines = [f"{request['method']} {target} HTTP/1.1\r\n"]
        for name, value in request["headers"]:
            if name.lower() == "host":
                raise ParityError("absolute-target adapter requires the Host header to be omitted")
            lines.append(f"{name}: {value}\r\n")
        if body:
            lines.append(f"Content-Length: {len(body)}\r\n")
        lines.append("\r\n")
        sock.sendall("".join(lines).encode("ascii") + body)
        response = http.client.HTTPResponse(sock)
        response.begin()
        return response_observation(response.status, response.getheaders(), response.read())
    finally:
        sock.close()


def http1_request_sequence(
    port: int,
    requests: list[dict[str, Any]],
    *,
    fault_control_path: Path | None = None,
    fault_point: str | None = None,
    events_path: Path | None = None,
) -> dict[str, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    responses = []
    try:
        for index, request in enumerate(requests):
            arm_fault_after_headers = request.get("fault_after_response_headers", False)
            events_before = len(read_events(events_path)) if events_path is not None else 0
            release_path = (
                events_path.with_suffix(".stream-release")
                if arm_fault_after_headers and events_path is not None
                else None
            )
            if release_path is not None:
                release_path.unlink(missing_ok=True)
            if fault_control_path is not None:
                selected_point = fault_point if index == 0 and not arm_fault_after_headers else ""
                fault_control_path.write_text(selected_point or "", encoding="utf-8")
            body = base64.b64decode(request["body_base64"], validate=True)
            connection.request(
                request["method"],
                request["path"],
                body=body,
                headers=dict(request["headers"]),
            )
            try:
                response = connection.getresponse()
            except http.client.RemoteDisconnected:
                responses.append({
                    "status": None,
                    "content_type": None,
                    "body_base64": "",
                    "connection_closed": True,
                })
                connection.close()
                continue
            if arm_fault_after_headers:
                if fault_control_path is None or not fault_point or release_path is None:
                    raise ParityError(
                        "delayed response fault requires fault control and application events"
                    )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if "response.first.sent" in read_events(events_path)[events_before:]:
                        break
                    time.sleep(0.005)
                else:
                    raise ParityError(
                        "stream fixture did not send its first response chunk before the fault"
                    )
                fault_control_path.write_text(fault_point, encoding="utf-8")
                release_path.touch()
            response_headers = response.getheaders()
            content_type = next(
                (value for name, value in response_headers if name.lower() == "content-type"),
                None,
            )
            try:
                response_body = response.read()
            except http.client.IncompleteRead as error:
                responses.append({
                    "status": response.status,
                    "content_type": content_type,
                    "body_base64": base64.b64encode(error.partial).decode("ascii"),
                    "connection_closed": True,
                })
                connection.close()
                continue
            responses.append({
                "status": response.status,
                "content_type": content_type,
                "body_base64": base64.b64encode(response_body).decode("ascii"),
            })
            if (
                index == 0
                and fault_control_path is not None
                and fault_point in {
                    "python.task-starter.inline-completion.borrow-conflict",
                    "python.task-starter.registration-error.borrow-conflict",
                    "python.task-starter.registration-success.borrow-conflict",
                    "python.task-starter.failure-cleanup.schedule-error",
                }
                and fault_control_path.read_text(encoding="utf-8").strip() == fault_point
            ):
                raise ParityError("callback cleanup fault was not consumed by the target")
        return {"responses": responses}
    finally:
        if fault_control_path is not None:
            fault_control_path.write_text("", encoding="utf-8")
        connection.close()


def http1_concurrent_requests(
    port: int,
    requests: list[dict[str, Any]],
    *,
    pause_before_read_ms: int,
) -> list[dict[str, Any]]:
    """Send one request per connection, then release all response readers together."""
    barrier = threading.Barrier(len(requests))

    def request_one(request: dict[str, Any]) -> dict[str, Any]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        body = base64.b64decode(request["body_base64"], validate=True)
        try:
            connection.connect()
            connection.putrequest(request["method"], request["path"])
            headers = list(request["headers"])
            if body and not any(name.lower() == "content-length" for name, _ in headers):
                headers.append(("Content-Length", str(len(body))))
            if not any(name.lower() == "connection" for name, _ in headers):
                headers.append(("Connection", "close"))
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders(body if body else None)
            barrier.wait(timeout=10)
            if pause_before_read_ms:
                time.sleep(pause_before_read_ms / 1000)
            response = connection.getresponse()
            return response_observation(response.status, response.getheaders(), response.read())
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(requests), thread_name_prefix="parity-http-load") as pool:
        futures = [pool.submit(request_one, request) for request in requests]
        return [future.result(timeout=30) for future in futures]


def read_http1_chunk(reader) -> bytes | None:
    line = reader.readline()
    if not line:
        raise ParityError("HTTP/1.1 server closed before completing chunked output")
    try:
        size = int(line.split(b";", maxsplit=1)[0].strip(), 16)
    except ValueError as error:
        raise ParityError(f"invalid chunked response-size line: {line!r}") from error
    if size == 0:
        while reader.readline() != b"\r\n":
            pass
        return None
    data = reader.read(size)
    if len(data) != size or reader.read(2) != b"\r\n":
        raise ParityError("truncated HTTP/1.1 response chunk")
    return data


def http1_body_pump_shutdown_workflow(
    server: dict[str, Any], specification: dict[str, Any], fault: dict[str, Any]
) -> dict[str, Any]:
    """Hold an unread request upload in the body-pump drain until shutdown."""
    fault_control_path = server.get("coverage_fault_control_path")
    if fault_control_path is None:
        raise ParityError("body-pump shutdown workflow requires the instrumented target")
    chunks = [base64.b64decode(item, validate=True) for item in specification["chunks_base64"]]
    if not chunks:
        raise ParityError("body-pump shutdown workflow requires a nonempty first chunk")

    client = socket.create_connection(("127.0.0.1", server["port"]), timeout=10)
    client.settimeout(10)
    fault_control_path.write_text(fault["point"], encoding="utf-8")
    try:
        headers = [
            f"{specification['method']} {specification['path']} HTTP/1.1\r\n",
            "Host: localhost\r\n",
            "Transfer-Encoding: chunked\r\n",
        ]
        headers.extend(f"{name}: {value}\r\n" for name, value in specification["headers"])
        client.sendall(("".join(headers) + "\r\n").encode("ascii"))
        first_chunk = chunks[0]
        client.sendall(f"{len(first_chunk):x}\r\n".encode() + first_chunk + b"\r\n")

        response = http.client.HTTPResponse(client)
        response.begin()
        payload = response.read()
        observation = response_observation(response.status, response.getheaders(), payload)
        observation["early_body_base64"] = observation["body_base64"]

        if fault["contract"] == "http-body-pump-shutdown-completes-task-before-abort":
            shutdown_hold_marker = "uvicorn-rs: request-body pump entered shutdown-hold fault"
            deadline = time.monotonic() + 5
            while shutdown_hold_marker not in read_server_log(server) and time.monotonic() < deadline:
                time.sleep(0.005)
            if shutdown_hold_marker not in read_server_log(server):
                raise ParityError("request-body pump did not enter the synchronized shutdown hold")
            drain_pause_consumed = False
        elif fault["contract"] == "http-body-pump-shutdown-cancelled-join":
            deadline = time.monotonic() + 5
            while (
                "http.body-pump.app-response-finished" not in read_events(server["events"])
                and time.monotonic() < deadline
            ):
                time.sleep(0.005)
            if "http.body-pump.app-response-finished" not in read_events(server["events"]):
                raise ParityError("ASGI app did not finish its response before body-pump shutdown")
            drain_pause_consumed = False
        else:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if fault_control_path.read_text(encoding="utf-8").strip() != fault["point"]:
                    break
                time.sleep(0.005)
            else:
                raise ParityError("request-body pump did not enter the synchronized unread-body drain")
            drain_pause_consumed = True

        shutdown_started = time.monotonic()
        exit_code, server_log = stop_server(server, graceful=True)
        shutdown_elapsed = time.monotonic() - shutdown_started
        shutdown_fault_consumed = (
            fault_control_path.read_text(encoding="utf-8").strip() != fault["point"]
        )
        observation.update({
            "process_terminated": exit_code is not None,
            "process_exit_code": exit_code,
            "shutdown_bounded": shutdown_elapsed <= 5,
            "shutdown_elapsed_seconds": shutdown_elapsed,
            "drain_pause_consumed": drain_pause_consumed,
            "shutdown_fault_consumed": shutdown_fault_consumed,
            "body_pump_joined": bool(re.search(
                r"^uvicorn-rs: request-body pumps joined: [1-9]\d*$",
                server_log,
                re.MULTILINE,
            )),
            "server_log": server_log,
        })
        return observation
    finally:
        fault_control_path.write_text("", encoding="utf-8")
        client.close()


def http1_streaming_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    chunks = [base64.b64decode(item, validate=True) for item in specification["chunks_base64"]]
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.settimeout(10)
    reader = client.makefile("rb")
    try:
        headers = [
            f"{specification['method']} {specification['path']} HTTP/1.1\r\n",
            "Host: localhost\r\n",
            "Transfer-Encoding: chunked\r\n",
        ]
        if not specification.get("keep_alive", False):
            headers.append("Connection: close\r\n")
        headers.extend(f"{name}: {value}\r\n" for name, value in specification["headers"])
        client.sendall(("".join(headers) + "\r\n").encode("ascii"))
        wait_event = specification.get("wait_event")
        if wait_event is not None:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and wait_event not in read_events(events_path):
                time.sleep(0.005)
            if wait_event not in read_events(events_path):
                raise ParityError(f"ASGI app did not reach request-stream checkpoint {wait_event!r}")
        first_request_chunk = chunks[0]
        connection_closed = False
        client.sendall(f"{len(first_request_chunk):x}\r\n".encode() + first_request_chunk + b"\r\n")

        if specification.get("send_all_before_read", False):
            for chunk in chunks[1:]:
                try:
                    client.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True
                    break
            if not connection_closed:
                try:
                    if specification.get("malformed_final_chunk", False):
                        client.sendall(b"not-a-size\r\n")
                    else:
                        trailer_lines = "".join(
                            f"{name}: {value}\r\n"
                            for name, value in specification.get("trailers", [])
                        )
                        client.sendall(("0\r\n" + trailer_lines + "\r\n").encode("ascii"))
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True

        try:
            status_line = reader.readline()
        except ConnectionResetError:
            status_line = b""
        if not status_line:
            result = response_observation(None, [], b"")
            result.update({"early_body_base64": "", "connection_closed": True})
            return result
        status = int(status_line.split()[1])
        response_headers = []
        while True:
            line = reader.readline()
            if line == b"\r\n":
                break
            if not line:
                raise ParityError("HTTP/1.1 response ended before its headers were complete")
            name, value = line.decode("latin-1").split(":", maxsplit=1)
            response_headers.append((name.strip().lower(), value.strip()))

        early_body = read_http1_chunk(reader)
        if early_body is None:
            raise ParityError("response finished before the request upload was complete")
        if (
            not specification.get("send_all_before_read", False)
            and not specification.get("send_remaining_after_response", False)
            and not connection_closed
        ):
            for chunk in chunks[1:]:
                try:
                    client.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True
                    break
            if not connection_closed:
                try:
                    if specification.get("malformed_final_chunk", False):
                        client.sendall(b"not-a-size\r\n")
                    else:
                        trailer_lines = "".join(
                            f"{name}: {value}\r\n"
                            for name, value in specification.get("trailers", [])
                        )
                        client.sendall(("0\r\n" + trailer_lines + "\r\n").encode("ascii"))
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True
        response_chunks = [early_body]
        try:
            while (chunk := read_http1_chunk(reader)) is not None:
                response_chunks.append(chunk)
        except (BrokenPipeError, ConnectionResetError, ParityError):
            connection_closed = True
        if specification.get("send_remaining_after_response", False) and not connection_closed:
            for chunk in chunks[1:]:
                try:
                    client.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True
                    break
            if not connection_closed:
                try:
                    client.sendall(b"0\r\n\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True
        result = response_observation(status, response_headers, b"".join(response_chunks))
        result["early_body_base64"] = base64.b64encode(early_body).decode("ascii")
        result["connection_closed"] = connection_closed
        return result
    finally:
        reader.close()
        client.close()


def http1_response_streaming_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    events_before = len(read_events(events_path))
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.settimeout(10)
    reader = client.makefile("rb")
    try:
        client.sendall(
            f"GET {specification['path']} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        status_line = reader.readline()
        if not status_line:
            raise ParityError("HTTP/1.1 server closed before starting its response stream")
        status = int(status_line.split()[1])
        response_headers = []
        while True:
            line = reader.readline()
            if line == b"\r\n":
                break
            if not line:
                raise ParityError("HTTP/1.1 response ended before its headers were complete")
            name, value = line.decode("latin-1").split(":", maxsplit=1)
            response_headers.append((name.strip().lower(), value.strip()))
        pause_ms = specification.get("pause_before_first_body_ms", 0)
        if pause_ms:
            time.sleep(pause_ms / 1000)
        early_body = read_http1_chunk(reader)
        if early_body is None:
            raise ParityError("HTTP/1.1 response ended without a data chunk")
        streamed_before_completion = "response.finished" not in read_events(events_path)[events_before:]
        chunks = [early_body]
        while (chunk := read_http1_chunk(reader)) is not None:
            chunks.append(chunk)
        result = response_observation(status, response_headers, b"".join(chunks))
        result.update({
            "early_body_base64": base64.b64encode(early_body).decode("ascii"),
            "streamed_before_completion": streamed_before_completion,
        })
        return result
    finally:
        reader.close()
        client.close()


def http1_response_reset_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    events_before = len(read_events(events_path))
    stream_release_path = events_path.with_suffix(".stream-release")
    stream_release_path.unlink(missing_ok=True)
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.settimeout(10)
    reader = client.makefile("rb")
    try:
        client.sendall(
            f"GET {specification['path']} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        status_line = reader.readline()
        if not status_line:
            raise ParityError("HTTP/1.1 server closed before starting its response stream")
        status = int(status_line.split()[1])
        response_headers = []
        while True:
            line = reader.readline()
            if line == b"\r\n":
                break
            if not line:
                raise ParityError("HTTP/1.1 response ended before its headers were complete")
            name, value = line.decode("latin-1").split(":", maxsplit=1)
            response_headers.append((name.strip().lower(), value.strip()))
        first_chunk = read_http1_chunk(reader)
        if first_chunk is None:
            raise ParityError("HTTP/1.1 response ended before its first streamed chunk")
        hold_deadline = time.monotonic() + 1
        current_events = read_events(events_path)[events_before:]
        while "response.reset.hold" not in current_events and time.monotonic() < hold_deadline:
            time.sleep(0.005)
            current_events = read_events(events_path)[events_before:]
        if "response.reset.hold" not in current_events:
            raise ParityError("stream-reset app did not enter its per-case response hold")
        streamed_before_completion = "response.reset.finished" not in current_events
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    finally:
        reader.close()
        client.close()

    # Hold the application after its first chunk so the reset is sent while the
    # response is still active; then release the finite hold and prove keep-serving.
    time.sleep(0.15)
    stream_release_path.touch()
    followup = http1_request(port, {
        "method": "GET",
        "path": specification["followup_path"],
        "headers": [],
        "body_base64": "",
    })
    return {
        "status": status,
        "content_type": next((value for name, value in response_headers if name == "content-type"), None),
        "early_body_base64": base64.b64encode(first_chunk).decode("ascii"),
        "streamed_before_completion": streamed_before_completion,
        "connection_closed": True,
        "followup": followup,
    }


def http2_disconnect_request(
    port: int,
    specification: dict[str, Any],
    events_path: Path,
    fault_control_path: Path | None = None,
    fault_point: str | None = None,
) -> dict[str, Any]:
    events_before = len(read_events(events_path))
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=5)
    client = context.wrap_socket(raw_socket, server_hostname="localhost")
    try:
        if client.selected_alpn_protocol() != "h2":
            raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
        connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
        connection.initiate_connection()
        stream_id = connection.get_next_available_stream_id()
        headers = [
            (":method", "POST"), (":scheme", "https"),
            (":authority", f"localhost:{port}"), (":path", specification["path"]),
        ]
        empty_request = specification.get("empty_request") is True
        complete_body = specification.get("complete_body_base64")
        if not empty_request:
            content_length = (
                len(base64.b64decode(complete_body, validate=True))
                if complete_body is not None
                else specification["content_length"]
            )
            headers.append(("content-length", str(content_length)))
        connection.send_headers(stream_id, headers, end_stream=empty_request)
        if complete_body is not None:
            client.sendall(connection.data_to_send())
            before_body_event = specification["wait_event_before_body"]
            deadline = time.monotonic() + 3
            while (
                before_body_event not in read_events(events_path)[events_before:]
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            if before_body_event not in read_events(events_path)[events_before:]:
                raise ParityError(
                    "HTTP/2 app did not enter its pre-upload receive checkpoint"
                )
            connection.send_data(
                stream_id,
                base64.b64decode(complete_body, validate=True),
                end_stream=True,
            )
        elif not empty_request:
            connection.send_data(
                stream_id,
                base64.b64decode(specification["partial_body_base64"], validate=True),
            )
        client.sendall(connection.data_to_send())
        deadline = time.monotonic() + 3
        while (
            specification["wait_event"] not in read_events(events_path)[events_before:]
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if specification["wait_event"] not in read_events(events_path)[events_before:]:
            raise ParityError("HTTP/2 app did not reach its receive checkpoint before connection close")
        if specification.get("reset_stream") is True:
            connection.reset_stream(stream_id, error_code=ErrorCodes.CANCEL)
            client.sendall(connection.data_to_send())
            event = specification["wait_event_after_disconnect"]
            deadline = time.monotonic() + 3
            while event not in read_events(events_path)[events_before:] and time.monotonic() < deadline:
                time.sleep(0.01)
            events = read_events(events_path)[events_before:]
            if event not in events:
                raise ParityError(
                    "HTTP/2 app did not receive disconnect after its stream reset "
                    f"(events={events!r})"
                )
            followup = http2_request_on_connection(client, connection, port, {
                "method": "GET", "path": specification["followup_path"],
                "headers": [], "body_base64": "",
            })
            return {
                "disconnect_event": "http.disconnect" in events,
                "followup": followup,
                "application_events": events,
                "same_connection": True,
            }
    finally:
        client.close()
    event = specification["wait_event_after_disconnect"]
    deadline = time.monotonic() + 3
    while event not in read_events(events_path)[events_before:] and time.monotonic() < deadline:
        time.sleep(0.01)
    events = read_events(events_path)[events_before:]
    if event not in events:
        raise ParityError("HTTP/2 app did not finish its disconnect receives")
    fault_consumed = False
    if fault_control_path is not None:
        if fault_point is None:
            raise ParityError("HTTP/2 EOF recheck fault observation requires its point selector")
        deadline = time.monotonic() + 3
        while (
            fault_control_path.read_text(encoding="utf-8").strip()
            == fault_point
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        if fault_control_path.read_text(encoding="utf-8").strip() == fault_point:
            raise ParityError(
                "HTTP/2 EOF recheck pause was not consumed while the disconnected request was held"
            )
        fault_consumed = True
    followup = http2_request(port, {
        "method": "GET", "path": specification["followup_path"], "headers": [], "body_base64": "",
    })
    observation = {
        "disconnect_event": "http.disconnect" in events,
        "followup": followup,
        "application_events": events,
    }
    if fault_control_path is not None:
        observation["fault_consumed"] = fault_consumed
    return observation


def http2_request_on_connection(
    client: ssl.SSLSocket, connection: H2Connection, port: int, request: dict[str, Any]
) -> dict[str, Any]:
    body = base64.b64decode(request["body_base64"], validate=True)
    stream_id = connection.get_next_available_stream_id()
    headers = [
        (":method", request["method"]),
        (":scheme", "https"),
        (":authority", f"localhost:{port}"),
        (":path", request["path"]),
    ]
    headers.extend((name.lower(), value) for name, value in request["headers"])
    if body:
        headers.append(("content-length", str(len(body))))
    connection.send_headers(stream_id, headers, end_stream=not body)
    if body:
        connection.send_data(stream_id, body, end_stream=True)
    client.sendall(connection.data_to_send())

    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    while True:
        received = client.recv(65536)
        if not received:
            raise ParityError("HTTP/2 connection closed before the sibling request completed")
        for event in connection.receive_data(received):
            if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                for name, value in event.headers:
                    if name == ":status":
                        status = int(value)
                    else:
                        response_headers.append((name, value))
            elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                response_body.extend(event.data)
                connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
            elif isinstance(event, StreamReset) and event.stream_id == stream_id:
                raise ParityError("HTTP/2 sibling request was reset after the upload stream reset")
            elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                pending = connection.data_to_send()
                if pending:
                    client.sendall(pending)
                observation = response_observation(status, response_headers, bytes(response_body))
                observation["same_connection"] = True
                return observation
        pending = connection.data_to_send()
        if pending:
            client.sendall(pending)


def http2_concurrent_requests(
    port: int,
    requests: list[dict[str, Any]],
    *,
    pause_before_read_ms: int = 0,
) -> dict[str, Any]:
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=5)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    try:
        if tls_socket.selected_alpn_protocol() != "h2":
            raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
        tls_socket.settimeout(5)
        connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
        connection.initiate_connection()
        responses = {}
        for request in requests:
            stream_id = connection.get_next_available_stream_id()
            headers = [(":method", request["method"]), (":scheme", "https"),
                       (":authority", f"localhost:{port}"), (":path", request["path"])]
            headers.extend((name.lower(), value) for name, value in request["headers"])
            body = base64.b64decode(request["body_base64"], validate=True)
            connection.send_headers(stream_id, headers, end_stream=not body)
            if body:
                connection.send_data(stream_id, body, end_stream=True)
            responses[stream_id] = {"status": None, "headers": [], "body": bytearray()}
        tls_socket.sendall(connection.data_to_send())
        if pause_before_read_ms:
            time.sleep(pause_before_read_ms / 1000)
        ended = set()
        while len(ended) < len(responses):
            received = tls_socket.recv(65536)
            if not received:
                raise ParityError("HTTP/2 connection closed before all concurrent streams completed")
            for event in connection.receive_data(received):
                stream_id = getattr(event, "stream_id", None)
                if stream_id not in responses:
                    continue
                response = responses[stream_id]
                if isinstance(event, ResponseReceived):
                    for name, value in event.headers:
                        if name == ":status":
                            response["status"] = int(value)
                        else:
                            response["headers"].append((name, value))
                elif isinstance(event, DataReceived):
                    response["body"].extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded):
                    ended.add(stream_id)
                elif isinstance(event, StreamReset):
                    raise ParityError(f"concurrent HTTP/2 stream {stream_id} was reset")
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        close_error = close_http2_connection(connection, tls_socket)
        if close_error is not None:
            raise ParityError(f"HTTP/2 load client teardown failed: {close_error}")
        return {"responses": [response_observation(r["status"], r["headers"], bytes(r["body"]))
                              for r in responses.values()]}
    finally:
        tls_socket.close()


def close_http2_connection(
    connection: H2Connection, tls_socket: ssl.SSLSocket
) -> str | None:
    """Send GOAWAY, then complete TLS close-notify with the server."""
    try:
        # Drain control frames that were already in flight before starting TLS
        # shutdown. Otherwise a valid SETTINGS ACK or GOAWAY can race with the
        # TLS close-notify and look like illegal post-close application data.
        tls_socket.settimeout(0.05)
        quiet_since = time.monotonic()
        drain_deadline = quiet_since + 0.5
        while time.monotonic() < drain_deadline:
            try:
                received = tls_socket.recv(65536)
            except TimeoutError:
                if time.monotonic() - quiet_since >= 0.05:
                    break
                continue
            if not received:
                return None
            quiet_since = time.monotonic()
            for event in connection.receive_data(received):
                if isinstance(event, DataReceived):
                    connection.acknowledge_received_data(
                        event.flow_controlled_length, event.stream_id
                    )
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        connection.close_connection(error_code=ErrorCodes.NO_ERROR)
        pending = connection.data_to_send()
        if pending:
            tls_socket.sendall(pending)
        tls_socket.settimeout(0.25)
        raw_socket = tls_socket.unwrap()
    except (ssl.SSLZeroReturnError, ssl.SSLEOFError):
        # Rustls closes the transport after receiving close-notify without
        # necessarily sending a reciprocal TLS alert. EOF still proves that
        # the peer observed the close and released this connection.
        return None
    except TimeoutError:
        # The client close-notify has been sent. A server that waits for TCP
        # EOF instead of returning its own TLS alert will observe the socket
        # close in the caller's finally block.
        return None
    except ssl.SSLError as error:
        if error.reason == "APPLICATION_DATA_AFTER_CLOSE_NOTIFY":
            return None
        return f"{type(error).__name__}: {error}"
    except OSError as error:
        return f"{type(error).__name__}: {error}"
    else:
        raw_socket.close()
        return None


def http2_request(port: int, request: dict[str, Any]) -> dict[str, Any]:
    body = base64.b64decode(request["body_base64"], validate=True)
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    headers = [
        (":method", request["method"]),
        (":scheme", "https"),
    ]
    if not request.get("omit_authority"):
        headers.append((":authority", request.get("authority", f"localhost:{port}")))
    headers.append((":path", request["path"]))
    headers.extend((name.lower(), value) for name, value in request["headers"])
    if body:
        headers.append(("content-length", str(len(body))))
    connection.send_headers(stream_id, headers, end_stream=not body)
    if body:
        connection.send_data(stream_id, body, end_stream=True)
    tls_socket.sendall(connection.data_to_send())
    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    try:
        while True:
            try:
                received = tls_socket.recv(65536)
            except TimeoutError:
                observation = response_observation(status, response_headers, bytes(response_body))
                observation["connection_closed"] = True
                return observation
            if not received:
                observation = response_observation(status, response_headers, bytes(response_body))
                observation["connection_closed"] = True
                return observation
            events = connection.receive_data(received)
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamReset) and event.stream_id == stream_id:
                    observation = response_observation(status, response_headers, bytes(response_body))
                    observation["connection_closed"] = True
                    return observation
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    pending = connection.data_to_send()
                    if pending:
                        tls_socket.sendall(pending)
                    return response_observation(status, response_headers, bytes(response_body))
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
    finally:
        # A TLS close-notify lets the server finish its connection task before
        # load probes sample the Python task baseline.
        close_http2_connection(connection, tls_socket)
        tls_socket.close()


def http2_response_reset_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    events_before = len(read_events(events_path))
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    tls_socket.settimeout(5)
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    connection.send_headers(
        stream_id,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":authority", f"localhost:{port}"),
            (":path", specification["path"]),
        ],
        end_stream=True,
    )
    tls_socket.sendall(connection.data_to_send())

    status = 0
    response_headers: list[tuple[str, str]] = []
    response_stream_started = False
    try:
        deadline = time.monotonic() + 5
        while not response_stream_started and time.monotonic() < deadline:
            received = tls_socket.recv(65536)
            if not received:
                raise ParityError("HTTP/2 server closed before streaming response data")
            for event in connection.receive_data(received):
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_stream_started = bool(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        if not response_stream_started:
            raise ParityError("HTTP/2 response did not stream data before the deadline")

        hold_deadline = time.monotonic() + 2
        current_events = read_events(events_path)[events_before:]
        while "response.reset.hold" not in current_events and time.monotonic() < hold_deadline:
            time.sleep(0.005)
            current_events = read_events(events_path)[events_before:]
        if "response.reset.hold" not in current_events:
            raise ParityError("HTTP/2 reset app did not enter its per-case response hold")
        connection.reset_stream(stream_id, error_code=ErrorCodes.CANCEL)
        tls_socket.sendall(connection.data_to_send())
    finally:
        tls_socket.close()

    followup = http2_request(port, {
        "method": "GET",
        "path": specification["followup_path"],
        "headers": [],
        "body_base64": "",
    })
    return {
        "status": status,
        "content_type": next((value for name, value in response_headers if name == "content-type"), None),
        "response_stream_started": response_stream_started,
        "stream_reset": True,
        "followup": followup,
    }


def http2_streaming_request(port: int, specification: dict[str, Any]) -> dict[str, Any]:
    chunks = [base64.b64decode(item, validate=True) for item in specification["chunks_base64"]]
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    headers = [
        (":method", specification["method"]),
        (":scheme", "https"),
        (":authority", f"localhost:{port}"),
        (":path", specification["path"]),
    ]
    headers.extend((name.lower(), value) for name, value in specification["headers"])
    connection.send_headers(stream_id, headers, end_stream=False)
    connection.send_data(stream_id, chunks[0], end_stream=False)
    tls_socket.sendall(connection.data_to_send())

    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    early_body = None
    ended = False
    try:
        while early_body is None:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    early_body = bytes(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
            if ended and early_body is None:
                raise ParityError("HTTP/2 response ended before request upload completed")

        trailers = specification.get("trailers", [])
        for index, chunk in enumerate(chunks[1:]):
            final_chunk = index == len(chunks[1:]) - 1
            connection.send_data(stream_id, chunk, end_stream=final_chunk and not trailers)
        if trailers:
            connection.send_headers(
                stream_id,
                [(name.lower(), value) for name, value in trailers],
                end_stream=True,
            )
        tls_socket.sendall(connection.data_to_send())
        while not ended:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        result = response_observation(status, response_headers, bytes(response_body))
        result["early_body_base64"] = base64.b64encode(early_body).decode("ascii")
        return result
    finally:
        tls_socket.close()


def http2_response_streaming_request(
    port: int, specification: dict[str, Any], events_path: Path
) -> dict[str, Any]:
    events_before = len(read_events(events_path))
    context = ssl._create_unverified_context()
    context.set_alpn_protocols(["h2"])
    raw_socket = socket.create_connection(("127.0.0.1", port), timeout=10)
    tls_socket = context.wrap_socket(raw_socket, server_hostname="localhost")
    if tls_socket.selected_alpn_protocol() != "h2":
        tls_socket.close()
        raise ParityError("TLS did not negotiate HTTP/2 through ALPN")
    connection = H2Connection(config=H2Configuration(client_side=True, header_encoding="utf-8"))
    connection.initiate_connection()
    tls_socket.sendall(connection.data_to_send())
    stream_id = connection.get_next_available_stream_id()
    connection.send_headers(
        stream_id,
        [
            (":method", "GET"),
            (":scheme", "https"),
            (":authority", f"localhost:{port}"),
            (":path", specification["path"]),
        ],
        end_stream=True,
    )
    tls_socket.sendall(connection.data_to_send())
    status = 0
    response_headers: list[tuple[str, str]] = []
    response_body = bytearray()
    early_body = None
    ended = False
    try:
        while early_body is None:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    early_body = bytes(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
            if ended and early_body is None:
                raise ParityError("HTTP/2 response ended without a data chunk")
        streamed_before_completion = "response.finished" not in read_events(events_path)[events_before:]

        while not ended:
            events = connection.receive_data(tls_socket.recv(65536))
            for event in events:
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    ended = True
            pending = connection.data_to_send()
            if pending:
                tls_socket.sendall(pending)
        result = response_observation(status, response_headers, bytes(response_body))
        result.update({
            "early_body_base64": base64.b64encode(early_body).decode("ascii"),
            "streamed_before_completion": streamed_before_completion,
        })
        return result
    finally:
        tls_socket.close()


def http3_request(
    port: int,
    trust_anchor: Path,
    request: dict[str, Any],
    client: Path,
    *,
    events_path: Path | None = None,
    events_before: int = 0,
) -> dict[str, Any]:
    specification = {
        "method": request["method"],
        "path": request["path"],
        "headers": request["headers"],
        "body_hex": base64.b64decode(request["body_base64"], validate=True).hex(),
        "abort_after_body": request.get("abort_after_body", False),
        "abort_response_after_headers": request.get("abort_response_after_headers", False),
        "expect_response_error": request.get("expect_response_error", False),
        "leave_upload_open_until_response": request.get("leave_upload_open_until_response", False),
        "empty_data_frame_before_body": request.get("empty_data_frame_before_body", False),
        "invalid_alpn": request.get("invalid_alpn", False),
    }
    if "authority" in request:
        specification["authority"] = request["authority"]
    if "close_error_code" in request:
        specification["close_error_code"] = request["close_error_code"]
    command = [str(client), f"127.0.0.1:{port}", str(trust_anchor)]
    input_data = json.dumps(specification)
    if request.get("abort_after_body") and events_path is not None:
        release_path = events_path.with_suffix(".http3-abort-release")
        release_path.unlink(missing_ok=True)
        specification["abort_release_file"] = str(release_path)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdin is not None
        process.stdin.write(json.dumps(specification))
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 5
        while (
            time.monotonic() < deadline
            and not {
                "http3.upload.started",
                "http3.upload.body",
                "http3.upload.waiting-after-body",
            }.issubset(set(read_events(events_path)[events_before:]))
            and process.poll() is None
        ):
            time.sleep(0.01)
        observed_events = set(read_events(events_path)[events_before:])
        if not {
            "http3.upload.started",
            "http3.upload.body",
            "http3.upload.waiting-after-body",
        }.issubset(observed_events):
            process.kill()
            stdout, stderr = process.communicate()
            diagnostic = (
                stderr or stdout
            ).strip() or f"ASGI upload checkpoints were not reached: {sorted(observed_events)}"
            raise ParityError(
                f"HTTP/3 abort client did not reach the ASGI body checkpoint: {diagnostic[-800:]}"
            )
        release_path.touch()
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate()
            raise ParityError(
                "HTTP/3 abort client did not exit after the release checkpoint"
            ) from error
        returncode = process.returncode
    else:
        result = subprocess.run(
            command,
            cwd=ROOT,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=20,
        )
        returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
    if returncode != 0:
        diagnostic = (stderr or stdout).strip() or "no client diagnostic"
        raise ParityError(
            f"HTTP/3 probe client exited {returncode}: {diagnostic[-800:]}"
        )
    try:
        response = json.loads(stdout)
    except json.JSONDecodeError as error:
        diagnostic = stdout.strip() or stderr.strip() or "empty client output"
        raise ParityError(
            f"HTTP/3 probe client returned invalid JSON: {diagnostic[-800:]}"
        ) from error
    if response.get("response_timeout") is True:
        return {
            "status": None,
            "connection_closed": False,
            "stream_reset": False,
        }
    if response.get("stream_reset") is True:
        return {"stream_reset": True, "connection_closed": True, "status": None}
    if request.get("abort_after_body"):
        if response.get("aborted") is not True:
            raise ParityError(
                "HTTP/3 probe did not report the requested client-side abort"
            )
        return {"aborted": True}
    if request.get("abort_response_after_headers"):
        if response.get("client_aborted") is not True:
            raise ParityError(
                "HTTP/3 probe did not report the response-side client cancellation"
            )
        return {"status": response["status"], "client_aborted": True}
    body = bytes.fromhex(response["body_hex"])
    observation = response_observation(
        response["status"], [("content-type", response["content_type"] or "")], body
    )
    observation["ordered_response_headers"] = response.get("ordered_response_headers", [])
    response_header_values_by_name: dict[str, list[str]] = {}
    for name, value in observation["ordered_response_headers"]:
        response_header_values_by_name.setdefault(name, []).append(value)
    observation["response_header_values_by_name"] = [
        [name, values] for name, values in sorted(response_header_values_by_name.items())
    ]
    observation["connection_closed"] = response["body_stream_error"]
    observation["stream_reset"] = response["body_stream_error"]
    return observation


def http3_connection_error_with_held_response(
    server: dict[str, Any],
    trust_anchor: Path,
    specification: dict[str, Any],
    client: Path,
    fault: dict[str, str],
) -> dict[str, Any]:
    """Arm an accept failure after a real response chunk, retaining both streams."""
    control_path = server.get("coverage_fault_control_path")
    if control_path is None:
        raise ParityError("HTTP/3 held-response cleanup requires the coverage-only fault control")
    control_path.write_text("", encoding="utf-8")
    result_path = server["events"].with_suffix(".http3-held-response-result")
    release_path = server["events"].with_suffix(".http3-held-response-release")
    result_path.unlink(missing_ok=True)
    release_path.unlink(missing_ok=True)
    log_offset = len(read_server_log(server))
    events_offset = len(read_events(server["events"]))
    wire_request = {
        "method": "GET", "path": specification["path"], "headers": [], "body_hex": "",
        "hold_result_file": str(result_path), "hold_release_file": str(release_path),
        "request_after_first_response_chunk": {
            "method": "GET", "path": specification["trigger_path"], "headers": [], "body_hex": "",
        },
    }
    process = subprocess.Popen(
        [str(client), f"127.0.0.1:{server['port']}", str(trust_anchor)],
        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(json.dumps(wire_request))
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 10
        while (
            not result_path.exists() and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if not result_path.exists():
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate()
            raise ParityError(
                "HTTP/3 held response did not reach its first-chunk barrier: "
                f"{(stderr or stdout).strip()[-800:]}"
            )
        first_chunk = json.loads(result_path.read_text(encoding="utf-8"))
        exact_keys(first_chunk, {
            "status", "content_type", "body_hex", "body_stream_error", "stream_reset",
            "connection_closed", "first_body_chunk_received",
        }, "HTTP/3 first-chunk barrier")
        if first_chunk["first_body_chunk_received"] is not True or not bytes.fromhex(first_chunk["body_hex"]):
            raise ParityError("HTTP/3 held-response barrier did not observe a real body chunk")
        deadline = time.monotonic() + 3
        while (
            "response.reset.hold" not in read_events(server["events"])[events_offset:]
            and process.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if (
            process.poll() is not None
            or "response.reset.hold" not in read_events(server["events"])[events_offset:]
        ):
            raise ParityError("HTTP/3 response did not remain held at the first-chunk barrier")
        # Acceptance is already waiting without an armed fault. A second
        # same-connection request advances it before the next accept checks
        # the newly armed point and cancels the owned held request.
        control_path.write_text(fault["point"], encoding="utf-8")
        release_path.touch()
        stdout, stderr = process.communicate(timeout=5)
        if process.returncode != 0:
            raise ParityError(f"HTTP/3 held-response client failed: {(stderr or stdout)[-800:]}")
        wire_observation = json.loads(stdout)
        exact_keys(wire_observation, {
            "status", "content_type", "body_hex", "body_stream_error", "stream_reset",
            "connection_closed", "first_body_chunk_received", "response_incomplete",
            "peer_close_code", "trigger_request_sent", "trigger_error",
        }, "HTTP/3 held-response result")
        cancellation_pattern = r"uvicorn-rs: HTTP/3 request task failed: task [0-9]+ was cancelled"
        connection_pattern = (
            r"uvicorn-rs: HTTP/3 connection from .+ failed: "
            r"coverage-injected runtime error at Http3ConnectionAcceptError"
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            case_log = read_server_log(server)[log_offset:]
            lines = case_log.splitlines()
            cancellation_lines = [index for index, line in enumerate(lines) if re.fullmatch(cancellation_pattern, line)]
            connection_lines = [index for index, line in enumerate(lines) if re.fullmatch(connection_pattern, line)]
            case_events = read_events(server["events"])[events_offset:]
            cleanup_observed = "response.reset.app-cancelled" in case_events
            if cancellation_lines and len(connection_lines) == 1 and cleanup_observed:
                break
            time.sleep(0.01)
        fault_consumed = control_path.read_text(encoding="utf-8") == ""
        followup = http3_request(
            server["port"], trust_anchor,
            {"method": "GET", "path": specification["followup_path"], "headers": [], "body_base64": ""},
            client,
        )
        observation = response_observation(
            wire_observation["status"],
            [("content-type", wire_observation["content_type"] or "")],
            bytes.fromhex(wire_observation["body_hex"]),
        )
        observation.update({
            "early_body_base64": base64.b64encode(bytes.fromhex(first_chunk["body_hex"])).decode("ascii"),
            "response_stream_started": wire_observation["first_body_chunk_received"],
            "stream_reset": wire_observation["stream_reset"],
            "connection_closed": wire_observation["connection_closed"],
            "response_incomplete": wire_observation["response_incomplete"],
            "peer_close_code": wire_observation["peer_close_code"],
            "trigger_request_sent": wire_observation["trigger_request_sent"],
            "body_stream_error": wire_observation["body_stream_error"],
            "trigger_error": wire_observation["trigger_error"],
            "fault_consumed": fault_consumed,
            "request_task_cancellation_observed": bool(cancellation_lines),
            "connection_error_observed": len(connection_lines) == 1,
            "diagnostics_ordered": bool(cancellation_lines) and len(connection_lines) == 1
            and max(cancellation_lines) < connection_lines[0],
            "application_cleanup_before_followup": cleanup_observed,
            "application_events": case_events,
            "server_log": case_log,
            "followup": followup,
        })
        return observation
    finally:
        release_path.touch()
        if process.poll() is None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        control_path.write_text("", encoding="utf-8")


def http3_request_sequence(
    server: dict[str, Any],
    trust_anchor: Path,
    requests: list[dict[str, Any]],
    client: Path,
    fault: dict[str, str] | None = None,
    h3_grease: bool = True,
    *,
    concurrent: bool = False,
    pause_before_read_ms: int = 0,
) -> dict[str, Any]:
    """Observe sequential streams and optional task diagnostics before peer close."""
    result_path = server["events"].with_suffix(".http3-sequence-result")
    release_path = server["events"].with_suffix(".http3-sequence-release")
    result_path.unlink(missing_ok=True)
    release_path.unlink(missing_ok=True)
    wire_requests = []
    for request in requests:
        wire = {
            "method": request["method"], "path": request["path"],
            "headers": request["headers"],
            "body_hex": base64.b64decode(request["body_base64"], validate=True).hex(),
        }
        wire_requests.append(wire)
    hold_after_response = 1 if fault else len(requests)
    specification = {
        **wire_requests[0], "request_sequence": wire_requests,
        "hold_result_file": str(result_path), "hold_release_file": str(release_path),
        "hold_after_response": hold_after_response,
        "h3_grease": h3_grease,
        "concurrent": concurrent,
        "pause_before_read_ms": pause_before_read_ms,
    }
    log_offset = len(read_server_log(server))
    control_path = server.get("coverage_fault_control_path") if fault else None
    if fault is not None and control_path is None:
        raise ParityError("HTTP/3 request-task recovery requires the coverage-only fault control")
    if control_path is not None:
        control_path.write_text(fault["point"], encoding="utf-8")
    process = None
    try:
        process = subprocess.Popen(
            [str(client), f"127.0.0.1:{server['port']}", str(trust_anchor)],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )
        assert process.stdin is not None
        process.stdin.write(json.dumps(specification))
        process.stdin.close()
        process.stdin = None
        deadline = time.monotonic() + 10
        while (
            not result_path.exists() and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if not result_path.exists():
            if process.poll() is None:
                process.kill()
            stdout, stderr = process.communicate()
            raise ParityError(
                "HTTP/3 sequence did not reach its live-connection result barrier: "
                f"{(stderr or stdout).strip()[-800:]}"
            )
        wire_observation = json.loads(result_path.read_text(encoding="utf-8"))
        wire_prefix = wire_observation.get("responses")
        if not isinstance(wire_prefix, list) or len(wire_prefix) != hold_after_response:
            raise ParityError("HTTP/3 sequence omitted its declared response-barrier prefix")
        task_failure_observed = False
        if fault is not None:
            # A Rust panic-hook message is not proof that the parent reaped
            # its task. Observe the parent's original error diagnostic while
            # this exact client connection remains alive at the barrier.
            prefix = "uvicorn-rs: HTTP/3 request task failed:"
            message = COVERAGE_PANIC_MESSAGES[fault["point"]]
            deadline = time.monotonic() + 3
            while process.poll() is None and time.monotonic() < deadline:
                case_log = read_server_log(server)[log_offset:]
                diagnostics = [line for line in case_log.splitlines() if line.startswith(prefix)]
                task_failure_observed = len(diagnostics) == 1 and message in diagnostics[0]
                if task_failure_observed:
                    break
                time.sleep(0.01)
        if process.poll() is not None:
            raise ParityError("HTTP/3 client exited before the live-connection release")
        release_path.touch()
        stdout, stderr = process.communicate(timeout=5)
        if process.returncode != 0:
            raise ParityError(f"HTTP/3 sequence client failed after release: {(stderr or stdout)[-800:]}")
        final_observation = json.loads(stdout)
        wire_responses = final_observation.get("responses")
        if not isinstance(wire_responses, list) or len(wire_responses) != len(requests):
            raise ParityError("HTTP/3 sequence omitted a declared request observation")
        if wire_responses[:hold_after_response] != wire_prefix:
            raise ParityError("HTTP/3 completed response prefix changed across its release barrier")
        responses = []
        for wire_response in wire_responses:
            if not isinstance(wire_response, dict):
                raise ParityError("HTTP/3 sequence response must be an object")
            response = response_observation(
                wire_response["status"],
                [("content-type", wire_response["content_type"] or "")],
                bytes.fromhex(wire_response["body_hex"]),
            )
            response["stream_reset"] = wire_response["stream_reset"]
            if (
                response["status"] != 200 or response["stream_reset"]
                or wire_response["body_stream_error"]
            ):
                raise ParityError("HTTP/3 sequence did not complete every healthy response")
            responses.append(response)
        observation = {"responses": responses}
        if fault is not None:
            observation.update({
                "followup": responses[-1],
                "request_task_failure_observed_before_peer_close": task_failure_observed,
            })
        return observation
    finally:
        release_path.touch()
        if process is not None:
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        if control_path is not None:
            control_path.write_text("", encoding="utf-8")


def load_status_request(
    server: dict[str, Any],
    profile_id: str,
    key: str,
    trust_anchor: Path | None,
    h3_client: Path | None,
    *,
    kind: str = "http",
) -> dict[str, Any]:
    request = {
        "method": "GET",
        "path": f"/load/status?kind={kind}&key={key}",
        "headers": [],
        "body_base64": "",
    }
    if profile_id == "http2":
        return http2_request(server["port"], request)
    if profile_id == "http3":
        if trust_anchor is None or h3_client is None:
            raise ParityError("HTTP/3 load status is missing its certificate or client")
        return http3_request(server["port"], trust_anchor, request, h3_client)
    ssl_context = None
    if profile_id == "websocket-tls":
        if trust_anchor is None:
            raise ParityError("TLS WebSocket load status is missing its trust anchor")
        ssl_context = ssl.create_default_context(cafile=str(trust_anchor))
    return http1_request(server["port"], request, ssl_context=ssl_context)


def _load_resource_result(
    responses_by_round: list[Any],
    resource_rounds: list[dict[str, int]],
    concurrency: int,
    rounds: int,
) -> dict[str, Any]:
    quiescent = all(result["active"] == 0 for result in resource_rounds)
    load_reached = all(
        result["arrived"] == concurrency
        and result["expected"] == concurrency
        and result["peak_active"] == concurrency
        and result["peak_python_tasks"] >= concurrency
        for result in resource_rounds
    )
    settled_rss = [result["rss_after_bytes"] for result in resource_rounds[-3:]]
    rss_stable = (
        len(settled_rss) == 3
        and max(settled_rss) - min(settled_rss) <= 16 * 1024 * 1024
    )
    task_counts = [result["idle_python_tasks"] for result in resource_rounds]
    tasks_stable = (
        len(task_counts) == rounds
        and task_counts[-1] <= task_counts[0]
    )
    return {
        "responses": responses_by_round,
        "resource_rounds": resource_rounds,
        "active_tasks_zero": quiescent,
        "load_reached": load_reached,
        "resource_stable": rss_stable,
        "task_count_stable": tasks_stable,
        "followup_healthy": len(resource_rounds) == rounds,
    }


def _load_response_fingerprint(response: dict[str, Any]) -> dict[str, Any]:
    """Keep exact response parity evidence compact for repeated load rounds."""
    if "body_base64" in response:
        body = base64.b64decode(response["body_base64"], validate=True)
        return {
            "status": response["status"],
            "content_type": response["content_type"],
            "body_bytes": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "ordered_response_headers": response["ordered_response_headers"],
        }
    if "messages" in response:
        messages = [message.encode("utf-8") for message in response["messages"]]
        return {
            "messages": [
                {"bytes": len(message), "sha256": hashlib.sha256(message).hexdigest()}
                for message in messages
            ],
            "close_code": response["close_code"],
            "close_reason": response["close_reason"],
        }
    raise ParityError("load response has no byte or message payload to fingerprint")


def run_http_load_case(
    server: dict[str, Any],
    profile: dict[str, Any],
    case: dict[str, Any],
    trust_anchor: Path | None,
    h3_client: Path | None,
) -> dict[str, Any]:
    load = case["load"]
    requests = case["request_sequence"]
    if len(requests) != 1:
        raise ParityError("HTTP load input must use one reusable request stimulus")
    request_stimulus = requests[0]
    key = load["key"]
    request_path = (
        f"/load/fan-in?key={key}&count={load['concurrency']}"
        f"&chunks={load['chunks']}&chunk_bytes={load['chunk_bytes']}"
    )
    expanded_requests = [
        dict(request_stimulus, path=request_path)
        for _ in range(load["concurrency"])
    ]
    responses_by_round = []
    resource_rounds = []

    for _round_index in range(load["rounds"]):
        sampler = ProcessResourceSampler(server["process"].pid)
        sampler.start()
        if profile["id"] == "http1":
            responses = http1_concurrent_requests(
                server["port"],
                expanded_requests,
                pause_before_read_ms=load["pause_before_read_ms"],
            )
        elif profile["id"] == "http2":
            response_group = http2_concurrent_requests(
                server["port"],
                expanded_requests,
                pause_before_read_ms=load["pause_before_read_ms"],
            )
            responses = response_group["responses"]
        elif profile["id"] == "http3":
            if trust_anchor is None or h3_client is None:
                raise ParityError("HTTP/3 load request is missing its certificate or client")
            response_group = http3_request_sequence(
                server,
                trust_anchor,
                expanded_requests,
                h3_client,
                h3_grease=False,
                concurrent=True,
                pause_before_read_ms=load["pause_before_read_ms"],
            )
            responses = response_group["responses"]
        else:
            raise ParityError(f"unsupported HTTP load profile: {profile['id']}")

        time.sleep(0.05)
        status_response = load_status_request(
            server, profile["id"], key, trust_anchor, h3_client
        )
        time.sleep(0.05)
        resource = sampler.finish()
        if status_response["status"] != 200:
            raise ParityError(f"load follow-up returned HTTP {status_response['status']}")
        try:
            app_status = json.loads(
                base64.b64decode(status_response["body_base64"], validate=True)
            )
        except (ValueError, json.JSONDecodeError) as error:
            raise ParityError("load follow-up returned invalid application state") from error
        responses_by_round.append(
            [_load_response_fingerprint(response) for response in responses]
        )
        resource_rounds.append({**app_status, **resource})

    return _load_resource_result(
        responses_by_round,
        resource_rounds,
        load["concurrency"],
        load["rounds"],
    )


def websocket_client_subprotocols(specification: dict[str, Any]) -> list[str] | None:
    """Map no ASGI offers to no wire header for the pinned websockets client."""
    # websockets 17 sends Sec-WebSocket-Protocol for [] (an invalid empty
    # header); ASGI's empty list means the client offered no subprotocols.
    return specification["subprotocols"] or None


def websocket_concurrent_sessions(
    server: dict[str, Any],
    specification: dict[str, Any],
    load: dict[str, Any],
    trust_anchor: Path | None,
) -> list[dict[str, Any]]:
    scheme = "wss" if trust_anchor is not None else "ws"
    ssl_context = (
        ssl.create_default_context(cafile=str(trust_anchor))
        if trust_anchor is not None
        else None
    )
    path = (
        f"{specification['path']}?key={load['key']}&count={load['concurrency']}"
        f"&messages={load['messages_per_session']}&message_bytes={load['message_bytes']}"
    )
    subprotocols = websocket_client_subprotocols(specification)
    barrier = threading.Barrier(load["concurrency"])

    def session(session_index: int) -> dict[str, Any]:
        uri = f"{scheme}://127.0.0.1:{server['port']}{path}"
        with websocket_connect(
            uri,
            subprotocols=subprotocols,
            ssl=ssl_context,
            proxy=None,
            open_timeout=20,
            close_timeout=3,
            compression=None,
            max_size=1024 * 1024,
        ) as websocket:
            barrier.wait(timeout=15)
            payload = chr(65 + session_index % 26) + ("x" * (load["message_bytes"] - 1))
            for _ in range(load["messages_per_session"]):
                websocket.send(payload)
            if load["pause_before_read_ms"]:
                time.sleep(load["pause_before_read_ms"] / 1000)
            echoes = [websocket.recv() for _ in range(load["messages_per_session"])]
            try:
                unexpected = websocket.recv()
            except ConnectionClosed:
                pass
            else:
                raise ParityError(
                    f"WebSocket load session received an unexpected message: {unexpected!r}"
                )
            if echoes != [payload] * load["messages_per_session"]:
                raise ParityError("WebSocket load session received a mismatched echo")
            return {
                "messages": echoes,
                "close_code": websocket.close_code,
                "close_reason": websocket.close_reason,
            }

    with ThreadPoolExecutor(
        max_workers=load["concurrency"], thread_name_prefix="parity-websocket-load"
    ) as pool:
        futures = [pool.submit(session, index) for index in range(load["concurrency"])]
        return [future.result(timeout=45) for future in futures]


def run_websocket_load_case(
    server: dict[str, Any],
    profile: dict[str, Any],
    case: dict[str, Any],
    trust_anchor: Path | None,
    h3_client: Path | None,
) -> dict[str, Any]:
    load = case["load"]
    responses_by_round = []
    resource_rounds = []
    for _round_index in range(load["rounds"]):
        sampler = ProcessResourceSampler(server["process"].pid)
        sampler.start()
        responses = websocket_concurrent_sessions(
            server, case["websocket"], load, trust_anchor
        )
        time.sleep(0.05)
        status_response = load_status_request(
            server,
            profile["id"],
            load["key"],
            trust_anchor,
            h3_client,
            kind="websocket",
        )
        time.sleep(0.05)
        resource = sampler.finish()
        if status_response["status"] != 200:
            raise ParityError(
                f"WebSocket load follow-up returned HTTP {status_response['status']}"
            )
        try:
            app_status = json.loads(
                base64.b64decode(status_response["body_base64"], validate=True)
            )
        except (ValueError, json.JSONDecodeError) as error:
            raise ParityError("WebSocket load follow-up returned invalid application state") from error
        responses_by_round.append(
            [_load_response_fingerprint(response) for response in responses]
        )
        resource_rounds.append({**app_status, **resource})
    return _load_resource_result(
        responses_by_round,
        resource_rounds,
        load["concurrency"],
        load["rounds"],
    )


def http3_peer_close_request(
    server: dict[str, Any],
    trust_anchor: Path,
    request: dict[str, Any],
    client: Path,
) -> dict[str, Any]:
    """Observe a complete response, explicit peer closure, and a fresh connection.

    Each client invocation creates its own QUIC connection. Inspect diagnostics
    only after graceful teardown has joined the server's connection tasks, so
    an arbitrary delay cannot conceal late failure logs.
    """
    log_offset = len(read_server_log(server))
    observation = http3_request(server["port"], trust_anchor, request, client)
    observation["followup"] = http3_request(
        server["port"], trust_anchor, request, client
    )
    exit_code, _ = stop_server(server, graceful=True)
    case_log = read_server_log(server)[log_offset:]
    observation["process_terminated"] = exit_code is not None
    observation["process_exit_code"] = exit_code
    # The public reference logs errors at ERROR; native diagnostic messages
    # have the uvicorn-rs prefix. Preserve raw logs in the run's stderr while
    # comparing their presence, rather than runtime-specific text or addresses.
    # The coverage-only request-body join count is routine lifecycle accounting.
    case_log = re.sub(
        r"^uvicorn-rs: request-body pumps joined: [1-9]\d*$",
        "",
        case_log,
        flags=re.MULTILINE,
    )
    observation["server_error_observed"] = bool(re.search(
        r"^uvicorn-rs:|\[(?:ERROR|CRITICAL)\]|^Traceback \(most recent call last\):|panicked at",
        case_log,
        re.MULTILINE,
    ))
    return observation


def http3_shutdown_request(
    server: dict[str, Any],
    trust_anchor: Path,
    request: dict[str, Any],
    client: Path,
) -> dict[str, Any]:
    """Keep an HTTP/3 connection or response stream open during shutdown."""
    events_path = server["events"]
    result_path = events_path.with_suffix(".http3-shutdown-result")
    release_path = events_path.with_suffix(".http3-shutdown-release")
    result_path.unlink(missing_ok=True)
    release_path.unlink(missing_ok=True)
    specification = {
        "method": request["method"],
        "path": request["path"],
        "headers": request["headers"],
        "body_hex": base64.b64decode(request["body_base64"], validate=True).hex(),
        "hold_result_file": str(result_path),
        "hold_release_file": str(release_path),
        "hold_response_stream_for_shutdown": request.get(
            "hold_response_stream_for_shutdown", False
        ),
    }
    process = subprocess.Popen(
        [str(client), f"127.0.0.1:{server['port']}", str(trust_anchor)],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    process.stdin.write(json.dumps(specification))
    process.stdin.close()
    process.stdin = None
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not result_path.exists() and process.poll() is None:
        time.sleep(0.01)
    if not result_path.exists():
        process.kill()
        stdout, stderr = process.communicate()
        diagnostic = (stderr or stdout).strip() or "HTTP/3 probe did not publish its response"
        raise ParityError(f"HTTP/3 shutdown probe failed before server drain: {diagnostic[-800:]}")
    response = json.loads(result_path.read_text(encoding="utf-8"))
    exit_code, server_log = stop_server(server, graceful=True)
    release_path.touch()
    try:
        stdout, stderr = process.communicate(timeout=8)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise ParityError("HTTP/3 probe did not exit after the server shutdown") from error
    if process.returncode != 0:
        diagnostic = (stderr or stdout).strip() or "no client diagnostic"
        raise ParityError(f"HTTP/3 shutdown probe exited {process.returncode}: {diagnostic[-800:]}")
    observation = response_observation(
        response["status"],
        [("content-type", response["content_type"] or "")],
        bytes.fromhex(response["body_hex"]),
    )
    observation["process_terminated"] = exit_code is not None
    observation["server_log"] = server_log
    return observation


def websocket_observation(
    server: dict[str, Any],
    specification: dict[str, Any],
    trust_anchor: Path | None,
    *,
    fault_control_path: Path | None = None,
    fault_point: str | None = None,
) -> dict[str, Any]:
    scheme = "wss" if trust_anchor is not None else "ws"
    uri = f"{scheme}://127.0.0.1:{server['port']}{specification['path']}"
    subprotocols = websocket_client_subprotocols(specification)
    ssl_context = None
    if trust_anchor is not None:
        ssl_context = ssl.create_default_context(cafile=str(trust_anchor))
    client_trace = None
    client_logger = None
    client_handler = None
    if (
        trust_anchor is not None
        and os.environ.get("ASGI_PARITY_UVICORN_WEBSOCKET_DEBUG") == "1"
        and not specification.get("drop_during_upgrade")
        and not specification.get("shutdown_during_upgrade")
        and not specification.get("shutdown")
    ):
        client_trace = io.StringIO()
        client_logger = logging.Logger(
            f"asgi-parity-websocket-client-{uuid.uuid4().hex}", level=logging.DEBUG
        )
        client_logger.propagate = False
        client_handler = logging.StreamHandler(client_trace)
        client_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        client_logger.addHandler(client_handler)
    events_path = server["events"]
    events_before = len(read_events(events_path))
    if fault_control_path is not None:
        if fault_point is None:
            raise ParityError("fault-controlled WebSocket adapter requires an allow-listed point")
        fault_control_path.write_text(fault_point, encoding="utf-8")

    if specification.get("drop_during_upgrade") or specification.get("shutdown_during_upgrade"):
        client = socket.create_connection(("127.0.0.1", server["port"]), timeout=10)
        client.settimeout(10)
        raw_request = (
            f"GET {specification['path']} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server['port']}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        client.sendall(raw_request)
        deadline = time.monotonic() + 3
        while (
            time.monotonic() < deadline
            and "websocket.upgrade.waiting" not in read_events(events_path)[events_before:]
        ):
            if server["process"].poll() is not None:
                client.close()
                raise ParityError("WebSocket app exited before the pending upgrade was observed")
            time.sleep(0.01)
        if "websocket.upgrade.waiting" not in read_events(events_path)[events_before:]:
            client.close()
            raise ParityError("WebSocket app did not enter the pending-upgrade checkpoint")
        if specification.get("shutdown_during_upgrade"):
            exit_code, _ = stop_server(server, graceful=True)
            client.close()
            return {"process_terminated": exit_code is not None}
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        client.close()
        time.sleep(0.3)
        followup = http1_request(server["port"], {
            "method": "GET",
            "path": specification["followup_path"],
            "headers": [],
            "body_base64": "",
        })
        return {"status": followup["status"]}

    def add_fault_followup(
        observation: dict[str, Any], *, wait_for_events: bool = True
    ) -> dict[str, Any]:
        public_contract = fault_point in PUBLIC_INPUT_CONTRACT_POINTS
        if fault_control_path is None and not public_contract:
            return observation
        if (
            fault_point == "websocket.accept-key.header-value-error"
            and fault_control_path.read_text(encoding="utf-8").strip() == fault_point
        ):
            raise ParityError("WebSocket accept-header conversion fault was not consumed by the target")
        if fault_control_path is not None:
            fault_control_path.write_text("", encoding="utf-8")
        application_events = read_events(events_path)[events_before:]
        if wait_for_events or public_contract:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and (
                "websocket.header-capacity.cleanup-completed" not in application_events
                if public_contract else not application_events
            ):
                time.sleep(0.01)
                application_events = read_events(events_path)[events_before:]
        observation["application_events"] = application_events
        followup = {
            "method": "GET",
            "path": specification["followup_path"],
            "headers": [],
            "body_base64": "",
        }
        observation["followup"] = http1_request(server["port"], followup)
        return observation
    if specification.get("shutdown", False):
        ready = threading.Event()
        client_result: dict[str, Any] = {"close_code": None, "close_reason": None}
        client_error: list[Exception] = []

        def hold_connection() -> None:
            try:
                with websocket_connect(
                    uri,
                    subprotocols=subprotocols,
                    ssl=ssl_context,
                    proxy=None,
                    open_timeout=20,
                    close_timeout=2,
                    logger=client_logger,
                ) as websocket:
                    ready.set()
                    try:
                        websocket.recv()
                    except ConnectionClosed as error:
                        close = error.rcvd
                        client_result["close_code"] = close.code if close is not None else None
                        client_result["close_reason"] = close.reason if close is not None else None
            except Exception as error:
                client_error.append(error)
                ready.set()

        client = threading.Thread(target=hold_connection, name="parity-websocket-shutdown", daemon=True)
        client.start()
        if not ready.wait(20):
            raise ParityError("WebSocket shutdown client did not complete its handshake")
        if client_error:
            raise ParityError(f"WebSocket shutdown client failed: {client_error[0]}")
        deadline = time.monotonic() + 3
        application_events = read_events(events_path)[events_before:]
        while time.monotonic() < deadline and "websocket.hold" not in application_events:
            time.sleep(0.02)
            application_events = read_events(events_path)[events_before:]
        if "websocket.hold" not in application_events:
            raise ParityError("WebSocket app did not enter its held receive before shutdown")
        exit_code, _ = stop_server(server, graceful=True)
        client.join(3)
        deadline = time.monotonic() + 2
        application_events = read_events(events_path)[events_before:]
        while time.monotonic() < deadline and not any(
            event.startswith("websocket.disconnect:") for event in application_events
        ):
            time.sleep(0.02)
            application_events = read_events(events_path)[events_before:]
        return {
            "process_terminated": exit_code is not None,
            "application_events": application_events,
            "close_code": client_result["close_code"],
            "close_reason": client_result["close_reason"],
        }
    client_socket: socket.socket | None = None
    try:
        receive_buffer_bytes = specification.get("receive_buffer_bytes")
        if receive_buffer_bytes is not None:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer_bytes)
            client_socket.connect(("127.0.0.1", server["port"]))
        with websocket_connect(
            uri,
            sock=client_socket,
            subprotocols=subprotocols,
            additional_headers=specification.get("headers", []),
            ssl=ssl_context,
            proxy=None,
            open_timeout=20,
            close_timeout=2,
            max_queue=1 if "wait_for_app_event" in specification else 16,
            max_size=16 * 1024 * 1024 if "wait_for_app_event" in specification else 1024 * 1024,
            logger=client_logger,
        ) as websocket:
            if specification.get("abrupt_disconnect", False):
                websocket.close_socket()
                deadline = time.monotonic() + 3
                application_events = []
                while time.monotonic() < deadline:
                    application_events = read_events(events_path)[events_before:]
                    if "websocket.disconnected-abrupt" in application_events:
                        break
                    time.sleep(0.01)
                return {
                    "disconnect_event": "websocket.disconnected-abrupt" in application_events,
                }
            echoes = []
            pong_received = None
            if "ping_payload" in specification:
                pong_received = websocket.ping(specification["ping_payload"]).wait(timeout=3)
            for message in specification["messages"]:
                if message["kind"] == "text":
                    websocket.send(message["value"])
                    if specification.get("send_only", False):
                        continue
                    echoed = websocket.recv()
                    echoes.append({"kind": "text", "value": echoed})
                else:
                    sent = base64.b64decode(message["value"], validate=True)
                    websocket.send(sent)
                    if specification.get("send_only", False):
                        continue
                    echoed = websocket.recv()
                    if not isinstance(echoed, bytes):
                        raise ParityError("binary WebSocket message came back as text")
                    echoes.append({"kind": "binary_base64", "value": base64.b64encode(echoed).decode("ascii")})
            wait_for_app_event = specification.get("wait_for_app_event")
            if wait_for_app_event is not None:
                deadline = time.monotonic() + 10
                application_events = read_events(events_path)[events_before:]
                while wait_for_app_event not in application_events and time.monotonic() < deadline:
                    time.sleep(0.01)
                    application_events = read_events(events_path)[events_before:]
                if wait_for_app_event not in application_events:
                    raise ParityError(
                        f"WebSocket app did not reach deferred-read event {wait_for_app_event!r}"
                    )
            observation = {"handshake_status": 101, "subprotocol": websocket.subprotocol, "messages": echoes}
            if pong_received is not None:
                observation["pong_received"] = pong_received
            if specification.get("expect_close", False):
                try:
                    while True:
                        received = websocket.recv()
                        if isinstance(received, bytes):
                            echoes.append({
                                "kind": "binary_base64",
                                "value": base64.b64encode(received).decode("ascii"),
                            })
                        else:
                            echoes.append({"kind": "text", "value": received})
                except ConnectionClosed as error:
                    close = error.rcvd
                    observation["close_code"] = close.code if close is not None else None
                    observation["close_reason"] = close.reason if close is not None else None
            if "client_close" in specification:
                websocket.close(
                    code=specification["client_close"]["code"],
                    reason=specification["client_close"]["reason"],
                )
                application_events = []
                deadline = time.monotonic() + (0 if fault_control_path is not None else 2)
                while time.monotonic() < deadline:
                    application_events = read_events(events_path)[events_before:]
                    if application_events:
                        break
                    time.sleep(0.01)
                observation["application_events"] = application_events
            observation["message_payload_bytes"] = [
                len(
                    message["value"].encode("utf-8")
                    if message["kind"] == "text"
                    else base64.b64decode(message["value"], validate=True)
                )
                for message in echoes
            ]
            observation["last_message"] = echoes[-1] if echoes else None
            return add_fault_followup(
                observation,
                wait_for_events=fault_point not in {
                    "websocket.receive.text-type.set-item",
                    "websocket.receive.text-value.set-item",
                    "websocket.receive.binary-type.set-item",
                    "websocket.receive.binary-value.set-item",
                    "websocket.receive.disconnect-type.set-item",
                    "websocket.receive.disconnect-code.set-item",
                    "websocket.receive.disconnect-reason.set-item",
                    "websocket.receive.closed-type.set-item",
                    "websocket.receive.closed-code.set-item",
                    "websocket.receive.closed-reason.set-item",
                },
            )
    except TimeoutError as error:
        if client_trace is None:
            raise
        trace = client_trace.getvalue()[-3000:] or "<no WebSocket protocol log emitted>"
        raise ParityError(f"WebSocket client timed out; client_trace={trace}") from error
    except ConnectionClosed as error:
        if fault_control_path is None:
            raise
        close = error.rcvd
        return add_fault_followup(
            {
                "handshake_status": 101,
                "close_code": close.code if close is not None else None,
                "close_reason": close.reason if close is not None else None,
            },
            wait_for_events=False,
        )
    except InvalidStatus as error:
        observation = {"handshake_established": False, "handshake_status": error.response.status_code}
        return add_fault_followup(observation, wait_for_events=False)
    except InvalidHandshake:
        # Malformed application handshake headers have no stable response
        # status across ASGI servers; parity here asks only whether the
        # WebSocket handshake was established.
        return add_fault_followup(
            {"handshake_established": False, "handshake_status": None},
            wait_for_events=False,
        )
    finally:
        if client_logger is not None and client_handler is not None:
            trace = client_trace.getvalue()[-3000:]
            if trace:
                sys.stderr.write(
                    f"--- {server['id']} WebSocket client trace ---\n{trace}\n"
                )
            client_logger.removeHandler(client_handler)
            client_handler.close()
        if fault_control_path is not None:
            fault_control_path.write_text("", encoding="utf-8")
        if client_socket is not None:
            client_socket.close()


def project_observation(raw: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    source_fields = {
        "status": "status",
        "content_type": "content_type",
        "body_bytes": "body_base64",
        "ordered_body_bytes": "body_base64",
        "ordered_response_headers": "ordered_response_headers",
        "response_header_values_by_name": "response_header_values_by_name",
        "early_body_bytes": "early_body_base64",
        "streamed_before_completion": "streamed_before_completion",
        "disconnect_event": "disconnect_event",
        "followup_response": "followup",
        "client_aborted": "client_aborted",
        "response_stream_started": "response_stream_started",
        "active_streams_held": "active_streams_held",
        "application_cancellation_count": "application_cancellation_count",
        "application_completion_count": "application_completion_count",
        "shutdown_elapsed_ms": "shutdown_elapsed_ms",
        "stream_reset": "stream_reset",
        "application_cancelled": "application_cancelled",
        "handshake_status": "handshake_status",
        "handshake_established": "handshake_established",
        "handshake_rejected": "handshake_rejected",
        "pong_received": "pong_received",
        "subprotocol": "subprotocol",
        "ordered_messages": "messages",
        "ordered_message_payload_bytes": "message_payload_bytes",
        "last_ordered_message": "last_message",
        "close_code": "close_code",
        "close_reason": "close_reason",
        "state_response": "state_response",
        "process_terminated": "process_terminated",
        "process_exit_code": "process_exit_code",
        "application_events": "application_events",
        "connection_closed": "connection_closed",
        "listener_closed_before_release": "listener_closed_before_release",
        "idle_connection_closed": "idle_connection_closed",
        "startup_failed": "startup_failed",
        "startup_error_observed": "startup_error_observed",
        "responses": "responses",
        "resource_rounds": "resource_rounds",
        "resource_stable": "resource_stable",
        "task_count_stable": "task_count_stable",
        "active_tasks_zero": "active_tasks_zero",
        "load_reached": "load_reached",
        "followup_healthy": "followup_healthy",
        "response_complete_before_app_return": "response_complete_before_app_return",
        "background_work_completed": "background_work_completed",
        "application_cleanup_completed": "application_cleanup_completed",
        "application_tasks_finished_before_probe_cleanup": "application_tasks_finished_before_probe_cleanup",
        "loop_alive_after_server_return": "loop_alive_after_server_return",
        "lifespan_shutdown_completed": "lifespan_shutdown_completed",
        "shutdown_bounded": "shutdown_bounded",
        "lifespan_tasks_finished_before_probe_cleanup": "lifespan_tasks_finished_before_probe_cleanup",
        "serve_cancellation_propagated": "serve_cancellation_propagated",
        "server_error_observed": "server_error_observed",
        "request_task_failure_observed_before_peer_close": "request_task_failure_observed_before_peer_close",
        "response_incomplete": "response_incomplete",
        "peer_close_code": "peer_close_code",
        "trigger_request_sent": "trigger_request_sent",
        "fault_consumed": "fault_consumed",
        "request_task_cancellation_observed": "request_task_cancellation_observed",
        "connection_error_observed": "connection_error_observed",
        "diagnostics_ordered": "diagnostics_ordered",
        "application_cleanup_before_followup": "application_cleanup_before_followup",
        "server_log": "server_log",
        "body_stream_error": "body_stream_error",
        "trigger_error": "trigger_error",
    }
    projected = {}
    for field in operation["observe"]:
        source = source_fields[field]
        if source not in raw:
            raise ParityError(f"adapter omitted declared observation {field!r}")
        projected[field] = raw[source]
    return projected


def run_zero_timeout_concurrent_stream_shutdown(
    server: dict[str, Any],
    profile: dict[str, Any],
    lifecycle: dict[str, Any],
    trust_anchor: Path | None,
) -> dict[str, Any]:
    """Hold concurrent HTTP/1.1 responses, then reset clients during zero-grace shutdown."""
    count = lifecycle["stream_count"]
    events_path = server["events"]
    events_before = len(read_events(events_path))
    release_path = events_path.with_suffix(".stream-release")
    release_path.unlink(missing_ok=True)
    ssl_context = None
    if profile["id"] == "lifecycle-tls":
        ssl_context = ssl._create_unverified_context()
    connections: list[http.client.HTTPConnection] = []

    def open_stream(
        _index: int,
    ) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse, socket.socket]:
        if ssl_context is None:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server["port"], timeout=8
            )
        else:
            connection = http.client.HTTPSConnection(
                "127.0.0.1", server["port"], timeout=8, context=ssl_context
            )
        try:
            connection.request(
                "GET", lifecycle["stream_path"], headers={"Connection": "close"}
            )
            client_socket = connection.sock
            if client_socket is None:
                raise ParityError("concurrent shutdown request did not retain its client socket")
            response = connection.getresponse()
            if response.status != 200 or response.read(6) != b"first/":
                raise ParityError("concurrent shutdown stream did not emit its first body chunk")
            return connection, response, client_socket
        except BaseException:
            connection.close()
            raise

    try:
        with ThreadPoolExecutor(
            max_workers=count, thread_name_prefix="parity-shutdown-stream"
        ) as pool:
            futures = [pool.submit(open_stream, index) for index in range(count)]
            streams = [future.result(timeout=12) for future in futures]
        connections = [connection for connection, _response, _sock in streams]

        deadline = time.monotonic() + 5
        events = read_events(events_path)[events_before:]
        while events.count("response.shutdown.hold") < count and time.monotonic() < deadline:
            time.sleep(0.01)
            events = read_events(events_path)[events_before:]
        if events.count("response.shutdown.hold") != count:
            raise ParityError(
                "not every concurrent response reached its hold before shutdown: "
                f"{events.count('response.shutdown.hold')}/{count}"
            )

        shutdown_started = time.monotonic()
        server["process"].terminate()
        aborted = 0
        for _connection, _response, client_socket in streams:
            client_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
            )
            client_socket.close()
            aborted += 1
        exit_code, server_log = stop_server(server, graceful=True, signal_sent=True)
        shutdown_elapsed = time.monotonic() - shutdown_started
        # Release any app task if a server failed to cancel it before process
        # teardown; the recorded cancellation count remains the acceptance signal.
        release_path.touch()
        events = read_events(events_path)[events_before:]
        return {
            "process_terminated": exit_code is not None,
            "client_aborted": aborted == count,
            "response_stream_started": len(streams) == count,
            "active_streams_held": events.count("response.shutdown.hold"),
            "application_cancellation_count": events.count("response.shutdown.cancelled"),
            "application_completion_count": events.count("response.shutdown.finished"),
            "application_events": events,
            "shutdown_bounded": shutdown_elapsed <= lifecycle["graceful_timeout_seconds"] + 3,
            "shutdown_elapsed_ms": round(shutdown_elapsed * 1000, 3),
            "server_log": server_log,
        }
    finally:
        release_path.touch()
        for connection in connections:
            connection.close()
        if server["process"].poll() is None:
            stop_server(server, graceful=True)


def execute_case(
    case: dict[str, Any], server: dict[str, Any], profile: dict[str, Any],
    trust_anchor: Path | None, h3_client: Path | None,
) -> dict[str, Any]:
    if "response_reset" in case:
        if profile["id"] == "http1":
            fault = case.get("fault")
            fault_control_path = server.get("coverage_fault_control_path") if fault else None
            if fault_control_path is not None:
                fault_control_path.write_text(fault["point"], encoding="utf-8")
            try:
                observation = http1_response_reset_request(server["port"], case["response_reset"], server["events"])
                if fault is not None:
                    deadline = time.monotonic() + 3
                    while (
                        "response.reset.app-cancelled" not in read_events(server["events"])
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    observation["application_events"] = read_events(server["events"])
                return observation
            finally:
                if fault_control_path is not None:
                    fault_control_path.write_text("", encoding="utf-8")
        if profile["id"] == "http2":
            return http2_response_reset_request(server["port"], case["response_reset"], server["events"])
        if profile["id"] == "http3":
            if trust_anchor is None or h3_client is None:
                raise ParityError("HTTP/3 held-response cleanup is missing its certificate or client")
            return http3_connection_error_with_held_response(
                server, trust_anchor, case["response_reset"], h3_client, case["fault"],
            )
        raise ParityError(f"{case['case_id']}: response reset workflow supports HTTP/1.1, HTTP/2 and HTTP/3")
    if "response_stream" in case:
        events_before = len(read_events(server["events"]))
        if profile["id"] == "http1":
            observation = http1_response_streaming_request(server["port"], case["response_stream"], server["events"])
        elif profile["id"] == "http2":
            observation = http2_response_streaming_request(server["port"], case["response_stream"], server["events"])
        else:
            raise ParityError(f"{case['case_id']}: no progressive response client for this protocol")
        event = case["response_stream"].get("app_return_event")
        if event is not None:
            observation["response_complete_before_app_return"] = event not in read_events(server["events"])[events_before:]
            deadline = time.monotonic() + 2
            while event not in read_events(server["events"])[events_before:] and time.monotonic() < deadline:
                time.sleep(0.005)
            observation["background_work_completed"] = event in read_events(server["events"])[events_before:]
        return observation
    if "request_stream" in case:
        fault = case.get("fault")
        if (
            fault is not None
            and fault["contract"] in {
                "http-body-pump-drain-shutdown-joined",
                "http-body-pump-shutdown-cancelled-join",
                "http-body-pump-shutdown-aborts-hung-pump",
                "http-body-pump-shutdown-completes-task-before-abort",
            }
        ):
            if profile["id"] != "http1":
                raise ParityError("body-pump shutdown workflow is HTTP/1.1 only")
            return http1_body_pump_shutdown_workflow(server, case["request_stream"], fault)
        if profile["id"] == "http1":
            fault_control_path = server.get("coverage_fault_control_path") if fault else None
            if fault_control_path is not None:
                fault_control_path.write_text(fault["point"], encoding="utf-8")
            try:
                observation = http1_streaming_request(
                    server["port"], case["request_stream"], server["events"]
                )
                if (
                    fault is not None
                    and fault["contract"] in {
                        "http-body-pump-reaps-cancelled-task",
                        "http-body-pump-drain-terminal-frame",
                    }
                ):
                    deadline = time.monotonic() + 3
                    while (
                        fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.005)
                    if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                        raise ParityError("request-body test fault was not consumed")
                    observation["fault_consumed"] = True
                return observation
            finally:
                if fault_control_path is not None:
                    fault_control_path.write_text("", encoding="utf-8")
        if profile["id"] == "http2":
            return http2_streaming_request(server["port"], case["request_stream"])
    if "load" in case and "request_sequence" in case:
        return run_http_load_case(server, profile, case, trust_anchor, h3_client)
    if "request_sequence" in case:
        if profile["id"] == "http3":
            if trust_anchor is None or h3_client is None:
                raise ParityError("HTTP/3 sequence is missing its certificate or client")
            return http3_request_sequence(
                server, trust_anchor, case["request_sequence"], h3_client, case.get("fault"),
                h3_grease=case.get("h3_grease", True),
            )
        if profile["id"] == "http2":
            return http2_concurrent_requests(server["port"], case["request_sequence"])
        profile_protocols = {part.strip() for part in profile["protocol"].split("+")}
        if (
            profile["id"] != "http1"
            and not (
                profile_protocols == {"http/1.1", "lifespan"}
                and not profile["id"].endswith("-tls")
            )
        ):
            raise ParityError(f"{case['case_id']}: no request-sequence adapter for this protocol")
        fault = case.get("fault")
        log_offset = len(read_server_log(server))
        events_before = len(read_events(server["events"]))
        observation = http1_request_sequence(
            server["port"],
            case["request_sequence"],
            fault_control_path=(
                server.get("coverage_fault_control_path")
                if fault and fault["point"] in FAULT_POINTS else None
            ),
            fault_point=fault.get("point") if fault else None,
            events_path=server["events"],
        )
        observation["server_log"] = read_server_log(server)[log_offset:]
        observation["application_events"] = read_events(server["events"])[events_before:]
        return observation
    if "request" in case:
        profile_id = profile["id"]
        fault = case.get("fault")
        fault_control_path = server.get("coverage_fault_control_path") if fault else None
        if fault_control_path is not None:
            control_point = fault["point"] if fault["point"] in FAULT_POINTS else ""
            fault_control_path.write_text(control_point, encoding="utf-8")
        if profile["protocol"].startswith("http/1.1"):
            ssl_context = None
            if profile_id == "http1-tls":
                if trust_anchor is None:
                    raise ParityError("HTTPS profile is missing its generated trust anchor")
                ssl_context = ssl.create_default_context(cafile=str(trust_anchor))
            return http1_request(server["port"], case["request"], ssl_context=ssl_context)
        if profile_id == "http2":
            return http2_request(server["port"], case["request"])
        if profile_id == "http3":
            if trust_anchor is None or h3_client is None:
                raise ParityError("HTTP/3 adapter is missing its certificate or client")
            request = case["request"]
            if case["operation"] in {"http3.peer-close", "http3.peer-close-registered"}:
                return http3_peer_close_request(server, trust_anchor, request, h3_client)
            if request.get("hold_open_for_shutdown"):
                return http3_shutdown_request(server, trust_anchor, request, h3_client)
            if request.get("invalid_alpn"):
                try:
                    http3_request(server["port"], trust_anchor, request, h3_client)
                    handshake_rejected = False
                except ParityError:
                    handshake_rejected = True
                followup = http3_request(
                    server["port"], trust_anchor, {
                        "method": "GET",
                        "path": "/state",
                        "headers": [],
                        "body_base64": "",
                    }, h3_client,
                )
                return {
                    "handshake_rejected": handshake_rejected,
                    "followup": followup,
                }
            events_before = len(read_events(server["events"]))
            observation = http3_request(
                server["port"],
                trust_anchor,
                request,
                h3_client,
                events_path=server["events"],
                events_before=events_before,
            )
            if request.get("abort_after_body"):
                deadline = time.monotonic() + 3
                while (
                    time.monotonic() < deadline
                    and "http3.upload.disconnected" not in read_events(server["events"])[events_before:]
                ):
                    time.sleep(0.01)
                followup = http3_request(
                    server["port"], trust_anchor, {
                        "method": "GET",
                        "path": "/state",
                        "headers": [],
                        "body_base64": "",
                    }, h3_client,
                )
                if (
                    fault is not None
                    and fault["contract"]
                    == "http3-body-pump-error-stop-disconnect-followup-200"
                    and fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                ):
                    raise ParityError("HTTP/3 body-pump error-stop fault was not consumed")
                result = {
                    "disconnect_event": "http3.upload.disconnected" in read_events(server["events"])[events_before:],
                    "followup": followup,
                }
                if fault is not None and fault["contract"] == "http3-body-pump-error-stop-disconnect-followup-200":
                    result["fault_consumed"] = True
                return result
            if request.get("abort_response_after_headers"):
                followup = http3_request(
                    server["port"], trust_anchor, {
                        "method": "GET",
                        "path": "/state",
                        "headers": [],
                        "body_base64": "",
                    }, h3_client,
                )
                return {
                    **observation,
                    "followup": followup,
                }
            if (
                fault is not None
                and fault["contract"] == "http3-body-pump-reaps-cancelled-task"
            ):
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("HTTP/3 request-body reaper fault was not consumed")
                observation["fault_consumed"] = True
            return observation
    if "websocket" in case:
        if case.get("operation") == "websocket.concurrent-session-load":
            return run_websocket_load_case(
                server, profile, case, trust_anchor, h3_client
            )
        fault = case.get("fault")
        log_offset = len(read_server_log(server))
        observation = websocket_observation(
            server,
            case["websocket"],
            trust_anchor,
            fault_control_path=(
                server.get("coverage_fault_control_path")
                if fault and fault["point"] in FAULT_POINTS else None
            ),
            fault_point=fault.get("point") if fault else None,
        )
        observation["server_log"] = read_server_log(server)[log_offset:]
        return observation
    if "startup_failure" in case:
        return {
            "startup_failed": server["startup_failed"],
            "application_events": read_events(server["events"]),
        }
    if "startup_fallback" in case:
        deadline = time.monotonic() + 8
        followup = None
        ssl_context = (
            ssl.create_default_context(cafile=str(trust_anchor))
            if trust_anchor is not None
            else None
        )
        while time.monotonic() < deadline:
            try:
                followup = http1_request(server["port"], {
                    "method": "GET",
                    "path": case["startup_fallback"]["followup_path"],
                    "headers": [],
                    "body_base64": "",
                }, ssl_context=ssl_context)
                if followup["status"] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.05)
        return {
            "startup_error_observed": (
                "coverage-only injected MemoryError at " in read_server_log(server)
                or "uvicorn-rs: ASGI app does not support lifespan" in read_server_log(server)
            ),
            "followup": followup,
        }
    if "disconnect" in case:
        disconnect = case["disconnect"]
        fault = case.get("fault")
        fault_control_path = server.get("coverage_fault_control_path") if fault else None
        events_before = len(read_events(server["events"]))

        def application_events() -> list[str]:
            return read_events(server["events"])[events_before:]

        if fault_control_path is not None:
            fault_control_path.write_text(fault["point"], encoding="utf-8")
        if profile["id"] == "http2":
            eof_recheck_control = (
                fault_control_path
                if fault and fault["contract"] == "http-read-eof-recheck-completes"
                else None
            )
            try:
                return http2_disconnect_request(
                    server["port"], disconnect, server["events"], eof_recheck_control,
                    fault["point"] if eof_recheck_control is not None else None,
                )
            finally:
                if fault_control_path is not None:
                    fault_control_path.write_text("", encoding="utf-8")
        client = socket.create_connection(("127.0.0.1", server["port"]), timeout=5)
        disconnect_started = time.monotonic()
        reset_elapsed_seconds = None
        try:
            if disconnect.get("malformed_chunk"):
                client.sendall(
                    f"POST {disconnect['path']} HTTP/1.1\r\nHost: localhost\r\n"
                    "Transfer-Encoding: chunked\r\n\r\nnot-a-size\r\nabc\r\n0\r\n\r\n".encode()
                )
                deadline = time.monotonic() + 3
                while (
                    time.monotonic() < deadline
                    and "http.disconnect" not in read_events(server["events"])
                ):
                    time.sleep(0.01)
                if "http.disconnect" not in read_events(server["events"]):
                    raise ParityError("malformed chunk body did not reach ASGI as a disconnect")
            elif disconnect.get("empty_request"):
                client.sendall(
                    f"GET {disconnect['path']} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode()
                )
                waiting_event = disconnect["wait_event"]
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and waiting_event not in application_events():
                    time.sleep(0.01)
                if waiting_event not in application_events():
                    raise ParityError(
                        f"ASGI app did not reach disconnect checkpoint {waiting_event!r}"
                    )
            elif "content_length" in disconnect:
                prefix = base64.b64decode(disconnect["partial_body_base64"], validate=True)
                client.sendall(
                    f"POST {disconnect['path']} HTTP/1.1\r\nHost: localhost\r\n"
                    f"Content-Length: {disconnect['content_length']}\r\n\r\n".encode() + prefix
                )
                if "wait_event" in disconnect and not disconnect.get("reset"):
                    waiting_event = disconnect["wait_event"]
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline and waiting_event not in application_events():
                        time.sleep(0.01)
                    if waiting_event not in application_events():
                        raise ParityError(
                            f"ASGI app did not reach disconnect checkpoint {waiting_event!r}"
                        )
                if disconnect.get("reset"):
                    waiting_event = disconnect.get("wait_event", "http.disconnect.waiting")
                    deadline = time.monotonic() + 3
                    while (
                        time.monotonic() < deadline
                        and waiting_event not in application_events()
                    ):
                        time.sleep(0.01)
                    if waiting_event not in application_events():
                        raise ParityError("ASGI app did not begin receiving before the client reset")
                    if (
                        fault
                        and fault["contract"] == "http-reset-before-body-worker-disconnect-followup-200"
                    ):
                        # The coverage-only pause clears its control before
                        # yielding. Synchronize the real TCP reset with that
                        # admission checkpoint without fabricating close state.
                        deadline = time.monotonic() + 3
                        while (
                            fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                            and time.monotonic() < deadline
                        ):
                            time.sleep(0.001)
                        if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                            raise ParityError("body-worker pause was not consumed before the client reset")
                    client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            else:
                client.sendall(
                    f"POST {disconnect['path']} HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n".encode()
                )
                if "wait_event" in disconnect:
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline and disconnect["wait_event"] not in application_events():
                        time.sleep(0.01)
                    if disconnect["wait_event"] not in application_events():
                        raise ParityError(
                            f"ASGI app did not reach disconnect checkpoint {disconnect['wait_event']!r}"
                        )
        finally:
            client.close()
            if disconnect.get("reset"):
                reset_elapsed_seconds = time.monotonic() - disconnect_started
        after_disconnect_event = disconnect.get("wait_event_after_disconnect")
        deadline = time.monotonic() + (0 if fault and not after_disconnect_event else 3)
        seen = False
        while time.monotonic() < deadline:
            seen = "http.disconnect" in application_events()
            if seen:
                break
            time.sleep(0.02)
        if after_disconnect_event:
            deadline = time.monotonic() + 3
            while (
                time.monotonic() < deadline
                and after_disconnect_event not in application_events()
            ):
                time.sleep(0.01)
            if after_disconnect_event not in application_events():
                raise ParityError(
                    "ASGI app did not reach post-disconnect checkpoint "
                    f"{after_disconnect_event!r}"
                )
        if (
            fault is not None
            and fault["contract"] == "http-body-pump-error-stop-disconnect-followup-200"
            and fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
        ):
            raise ParityError("malformed-body pump stop fault was not consumed")
        if fault_control_path is not None:
            fault_control_path.write_text("", encoding="utf-8")
        followup = http1_request(server["port"], {
            "method": "GET", "path": disconnect["followup_path"], "headers": [], "body_base64": ""
        })
        return {
            "disconnect_event": seen,
            "followup": followup,
            "application_events": application_events(),
            "reset_elapsed_seconds": reset_elapsed_seconds,
            "disconnect_workflow_seconds": time.monotonic() - disconnect_started,
        }
    if "lifecycle" in case:
        lifecycle = case["lifecycle"]
        if case["operation"] == "lifespan.concurrent-stream-zero-timeout-shutdown":
            return run_zero_timeout_concurrent_stream_shutdown(
                server, profile, lifecycle, trust_anchor
            )
        if case["operation"] == "lifespan.eager-registration-failure-cleanup":
            fault = case["fault"]
            fault_control_path = server["coverage_fault_control_path"]
            startup = fault["contract"] in EAGER_LIFESPAN_CLEANUP_CONTRACTS
            if startup and fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                raise ParityError("eager lifespan registration fault was not consumed during startup")
            state = http1_request(server["port"], {
                "method": "GET", "path": lifecycle["state_path"], "headers": [], "body_base64": "",
            })
            failure_response = None
            followup = None
            if "callback_path" in lifecycle:
                fault_control_path.write_text(fault["point"], encoding="utf-8")
                failure_response = http1_request(server["port"], {
                    "method": "GET", "path": lifecycle["callback_path"], "headers": [], "body_base64": "",
                })
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("eager application registration fault was not consumed")
                fault_control_path.write_text("", encoding="utf-8")
                followup = http1_request(server["port"], {
                    "method": "GET", "path": lifecycle["state_path"], "headers": [], "body_base64": "",
                })
            exit_code, server_log = stop_server(server, graceful=True)
            snapshot = read_server_api_snapshot(server)
            return {
                "state_response": state,
                "process_terminated": exit_code is not None and snapshot["server_task_finished"],
                "process_exit_code": exit_code,
                "application_tasks_finished_before_probe_cleanup": snapshot["application_tasks_finished_before_probe_cleanup"],
                "lifespan_tasks_finished_before_probe_cleanup": snapshot["lifespan_tasks_finished_before_probe_cleanup"],
                "loop_alive_after_server_return": snapshot["loop_alive_after_server_return"],
                "serve_cancellation_propagated": snapshot["serve_cancellation_propagated"],
                "shutdown_bounded": snapshot["shutdown_elapsed_seconds"] <= lifecycle["graceful_timeout_seconds"] + 3,
                "application_events": snapshot["application_events"],
                "server_log": server_log,
                "lifespan_shutdown_completed": snapshot["lifespan_shutdown_completed"],
                "failure_response": failure_response,
                "followup": followup,
            }
        if case["operation"] == "lifespan.post-response-application-shutdown":
            state = http1_request(server["port"], {
                "method": "GET", "path": lifecycle["state_path"], "headers": [], "body_base64": ""
            })
            response = http1_request(server["port"], {
                "method": "GET", "path": lifecycle["background_path"],
                "headers": [["Connection", "close"]], "body_base64": "",
            })
            deadline = time.monotonic() + 3
            events = read_events(server["events"])
            while "response.background.hold" not in events and time.monotonic() < deadline:
                time.sleep(0.01)
                events = read_events(server["events"])
            if "response.background.hold" not in events:
                raise ParityError("post-response application work did not reach its hold before shutdown")
            response_complete_before_app_return = (
                "response.background.cleanup-completed" not in events
            )
            fault = case.get("fault")
            fault_control_path = server.get("coverage_fault_control_path") if fault else None
            if fault_control_path is not None:
                # The completion-channel fault belongs to the held app, not
                # the readiness request or its already completed response.
                fault_control_path.write_text(fault["point"], encoding="utf-8")
            exit_code, server_log = stop_server(server, graceful=True)
            if (
                fault_control_path is not None
                and fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
            ):
                raise ParityError("forced task-completion fault was not consumed by the target")
            snapshot = read_server_api_snapshot(server)
            # Read the snapshot's events, not the file after process exit:
            # explicit probe cleanup and asyncio.run could otherwise conceal
            # a server that returned while an ASGI application was still live.
            snapshot_events = snapshot["application_events"]
            return {
                "state_response": state,
                "status": response["status"],
                "body_base64": response["body_base64"],
                "response_complete_before_app_return": response_complete_before_app_return,
                "process_terminated": exit_code is not None and snapshot["server_task_finished"],
                "process_exit_code": exit_code,
                "application_cancelled": "response.background.cancelled" in snapshot_events,
                "application_cleanup_completed": (
                    "response.background.cleanup-completed" in snapshot_events
                ),
                "application_tasks_finished_before_probe_cleanup": (
                    snapshot["application_tasks_finished_before_probe_cleanup"]
                ),
                "loop_alive_after_server_return": snapshot["loop_alive_after_server_return"],
                "lifespan_shutdown_completed": snapshot["lifespan_shutdown_completed"],
                "shutdown_bounded": (
                    snapshot["shutdown_elapsed_seconds"] <= lifecycle["graceful_timeout_seconds"] + 3
                ),
                "server_log": server_log,
            }
        if "stream_path" in lifecycle:
            tls_context = None
            if profile["id"] == "lifecycle-tls":
                tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                tls_context.check_hostname = False
                tls_context.verify_mode = ssl.CERT_NONE
                connection = http.client.HTTPSConnection(
                    "127.0.0.1", server["port"], timeout=5, context=tls_context
                )
            else:
                connection = http.client.HTTPConnection("127.0.0.1", server["port"], timeout=5)
            idle_connection = None
            try:
                if "idle_transport_prefix_base64" in lifecycle:
                    # Admit a real connection before the active stream. Its
                    # incomplete input remains open while the later request
                    # proves the server can still accept and execute work.
                    idle_connection = socket.create_connection(
                        ("127.0.0.1", server["port"]), timeout=5
                    )
                    if tls_context is not None:
                        idle_connection = tls_context.wrap_socket(
                            idle_connection, server_hostname="localhost"
                        )
                    idle_connection.sendall(base64.b64decode(
                        lifecycle["idle_transport_prefix_base64"], validate=True
                    ))
                    idle_connection.settimeout(2)
                connection.request(
                    "GET",
                    lifecycle["stream_path"],
                    headers=(
                        {}
                        if lifecycle.get("reset_connection_after_shutdown") is True
                        else {"Connection": "close"}
                    ),
                )
                response = connection.getresponse()
                first_chunk = response.read(6)
                if first_chunk != b"first/":
                    raise ParityError(
                        f"active stream did not deliver its first chunk before shutdown: {first_chunk!r}"
                    )
                deadline = time.monotonic() + 3
                while (
                    time.monotonic() < deadline
                    and "response.shutdown.hold" not in read_events(server["events"])
                ):
                    time.sleep(0.01)
                if "response.shutdown.hold" not in read_events(server["events"]):
                    raise ParityError("active response stream did not enter its shutdown hold")

                release_path = server["events"].with_suffix(".stream-release")
                fault = case.get("fault")
                if (
                    fault is not None
                    and fault["contract"] == "server-hyper-connection-error-during-shutdown"
                ):
                    fault_control_path = server.get("coverage_fault_control_path")
                    if fault_control_path is None:
                        raise ParityError("instrumented target has no connection-write fault control")
                    server["process"].terminate()
                    if not wait_for_listener_closed(server, timeout=3):
                        raise ParityError("server listener remained open after graceful shutdown began")
                    fault_control_path.write_text(fault["point"], encoding="utf-8")
                    time.sleep(0.1)
                    release_path.touch()
                    exit_code, server_log = stop_server(
                        server, graceful=True, signal_sent=True
                    )
                    if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                        raise ParityError("connection-write fault was not consumed by the target")
                    connection_closed = False
                    try:
                        if connection.sock is not None:
                            connection.sock.settimeout(2)
                        response.read()
                    except socket.timeout:
                        connection_closed = False
                    except (http.client.HTTPException, OSError):
                        connection_closed = True
                    else:
                        if connection.sock is None:
                            connection_closed = True
                        else:
                            try:
                                connection_closed = connection.sock.recv(1) == b""
                            except ConnectionResetError:
                                connection_closed = True
                            except socket.timeout:
                                connection_closed = False
                    return {
                        "process_terminated": exit_code is not None,
                        "application_events": read_events(server["events"]),
                        "connection_closed": connection_closed,
                        "response_stream_started": bool(first_chunk),
                        "server_log": server_log,
                    }
                if lifecycle.get("reset_connection_after_shutdown") is True:
                    client_socket = connection.sock
                    if client_socket is None:
                        raise ParityError("active stream socket was not retained before shutdown")

                    reset_result: dict[str, object] = {"completed": False, "error": None}

                    def reset_client_and_release_stream() -> None:
                        time.sleep(0.25)
                        try:
                            client_socket.setsockopt(
                                socket.SOL_SOCKET,
                                socket.SO_LINGER,
                                struct.pack("ii", 1, 0),
                            )
                            client_socket.close()
                            # Give the server time to observe the RST before
                            # the held ASGI response resumes writing.
                            time.sleep(0.1)
                            reset_result["completed"] = True
                        except OSError as error:
                            reset_result["error"] = error
                        finally:
                            release_path.touch()

                    reset_thread = threading.Thread(
                        target=reset_client_and_release_stream,
                        name="parity-reset-during-shutdown",
                        daemon=True,
                    )
                    reset_thread.start()
                    exit_code, server_log = stop_server(server, graceful=True)
                    reset_thread.join(timeout=2)
                    events = read_events(server["events"])
                    if reset_thread.is_alive():
                        raise ParityError("client reset/release trigger did not finish")
                    if reset_result["error"] is not None:
                        raise ParityError(
                            f"client reset failed during shutdown: {reset_result['error']}"
                        )
                    if reset_result["completed"] is not True:
                        raise ParityError("client reset did not complete during shutdown")
                    if "response.shutdown.hold" not in events:
                        raise ParityError("active response stream left its hold before client reset")
                    return {
                        "process_terminated": exit_code is not None,
                        "application_events": events,
                        "client_aborted": True,
                        "response_stream_started": bool(first_chunk),
                        "server_log": server_log,
                    }

                server["process"].terminate()
                # Leave the held stream enough of its three-second grace to
                # complete even when admission closure is the failed behavior.
                listener_closed_before_release = wait_for_listener_closed(server, timeout=1)
                if server["process"].poll() is not None:
                    raise ParityError("server exited before the held response stream was released")
                if "response.shutdown.finished" in read_events(server["events"]):
                    raise ParityError("response stream finished before its shutdown release")
                release_path.touch()
                exit_code, server_log = stop_server(server, graceful=True, signal_sent=True)
                stream_body = first_chunk + response.read()
                state = response_observation(
                    response.status, response.getheaders(), stream_body
                )
                closed = False
                if connection.sock is None:
                    closed = True
                else:
                    try:
                        connection.sock.settimeout(2)
                        closed = connection.sock.recv(1) == b""
                    except (ConnectionResetError, socket.timeout):
                        closed = False
                events = read_events(server["events"])
                if stream_body != b"first/second/last":
                    raise ParityError(f"active response stream was not fully drained: {stream_body!r}")
                if "response.shutdown.finished" not in events:
                    raise ParityError("ASGI app did not finish its response stream during shutdown")
                if not closed:
                    raise ParityError("server did not close the drained HTTP/1.1 connection")
                idle_connection_closed = False
                if idle_connection is not None:
                    try:
                        idle_connection_closed = idle_connection.recv(1) == b""
                    except OSError:
                        idle_connection_closed = False
                if (
                    server["id"] == "uvicorn-rs"
                    and "uvicorn-rs: connection task failed during shutdown:" in server_log
                ):
                    raise ParityError(
                        "Rust connection task reported an error while draining the completed response: "
                        f"{server_log.strip()}"
                    )
                return {
                    "state_response": state,
                    "process_terminated": exit_code is not None,
                    "process_exit_code": exit_code,
                    "application_events": events,
                    "connection_closed": closed,
                    "listener_closed_before_release": listener_closed_before_release,
                    "idle_connection_closed": idle_connection_closed,
                    "server_log": server_log,
                }
            finally:
                connection.close()
                if idle_connection is not None:
                    idle_connection.close()
        keep_alive_connection = None
        if lifecycle.get("keep_alive_state_connection") is True:
            keep_alive_connection = http.client.HTTPConnection("127.0.0.1", server["port"], timeout=5)
            keep_alive_connection.request("GET", lifecycle["state_path"], headers={"Connection": "keep-alive"})
            state_response = keep_alive_connection.getresponse()
            state = response_observation(
                state_response.status,
                state_response.getheaders(),
                state_response.read(),
            )
            if keep_alive_connection.sock is None:
                keep_alive_connection.close()
                raise ParityError("server closed the state connection before graceful shutdown")
        else:
            state = http1_request(server["port"], {
                "method": "GET", "path": lifecycle["state_path"], "headers": [], "body_base64": ""
            }, ssl_context=(ssl.create_default_context(cafile=str(trust_anchor))
                            if profile["id"] == "lifecycle-tls" else None))
        fault = case.get("fault")
        fault_control_path = server.get("coverage_fault_control_path") if fault else None
        if fault_control_path is not None:
            fault_control_path.write_text(fault["point"], encoding="utf-8")
        if (
            fault is not None
            and fault["contract"] == "server-connection-task-shutdown-timeout-abort"
        ):
            # Complete one connection while the injected select is armed, then
            # hold a second connection until shutdown exercises its timeout arm.
            probe = http1_request(server["port"], {
                "method": "GET",
                "path": lifecycle["state_path"],
                "headers": [],
                "body_base64": "",
            })
            if probe.get("status") != 200 or probe.get("body_base64") != "cmVhZHk=":
                raise ParityError(
                    "shutdown-timeout fault probe did not complete with the expected state response"
                )
        if lifecycle.get("unfinished_tls_handshake") is True:
            pending_tls = socket.create_connection(("127.0.0.1", server["port"]), timeout=3)
            try:
                # Let the connection reach its TLS read, while deliberately
                # withholding ClientHello bytes from this ordinary peer.
                time.sleep(0.05)
                exit_code, server_log = stop_server(server, graceful=True)
                pending_tls.settimeout(2)
                try:
                    connection_closed = pending_tls.recv(1) == b""
                except ConnectionResetError:
                    connection_closed = True
                except socket.timeout:
                    connection_closed = False
                return {"state_response": state, "process_terminated": exit_code is not None,
                        "process_exit_code": exit_code, "connection_closed": connection_closed,
                        "application_events": read_events(server["events"]), "server_log": server_log}
            finally:
                pending_tls.close()
        if "hold_path" not in lifecycle:
            exit_code, server_log = stop_server(server, graceful=True)
            connection_closed = None
            if keep_alive_connection is not None:
                try:
                    assert keep_alive_connection.sock is not None
                    keep_alive_connection.sock.settimeout(2)
                    connection_closed = keep_alive_connection.sock.recv(1) == b""
                except (ConnectionResetError, socket.timeout):
                    connection_closed = False
                finally:
                    keep_alive_connection.close()
            if fault_control_path is not None:
                fault_control_path.write_text("", encoding="utf-8")
            observation = {
                "state_response": state,
                "process_terminated": exit_code is not None,
                "process_exit_code": exit_code,
                "application_events": read_events(server["events"]),
                "server_log": server_log,
            }
            if lifecycle.get("keep_alive_state_connection") is True:
                observation["connection_closed"] = connection_closed
            return observation
        pending = socket.create_connection(("127.0.0.1", server["port"]), timeout=5)
        if profile["id"] == "lifecycle-tls":
            tls_context = ssl.create_default_context(cafile=str(trust_anchor))
            pending = tls_context.wrap_socket(pending, server_hostname="localhost")
        pending.sendall(
            f"GET {lifecycle['hold_path']} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and "request.hold" not in read_events(server["events"]):
                time.sleep(0.02)
            if "request.hold" not in read_events(server["events"]):
                raise ParityError(
                    "hold request did not enter the ASGI app before shutdown "
                    f"(events={read_events(server['events'])!r}, "
                    f"exit_code={server['process'].poll()!r}, state_response={state!r})"
                )
            exit_code, server_log = stop_server(server, graceful=True)
            events = read_events(server["events"])
        finally:
            pending.close()
        return {
            "state_response": state,
            "process_terminated": exit_code is not None,
            "process_exit_code": exit_code,
            "application_events": events,
            "server_log": server_log,
        }
    raise ParityError(f"no adapter for case {case['case_id']}")


def fault_contract_matches(fault: dict[str, Any], observation: dict[str, Any]) -> bool:
    if fault["contract"] == "asgi-spec-version-2.5":
        payload = None
        body = observation.get("body_bytes")
        if isinstance(body, str):
            try:
                payload = json.loads(base64.b64decode(body, validate=True))
            except (ValueError, json.JSONDecodeError):
                return False
        if payload is None:
            messages = observation.get("ordered_messages", [])
            for message in messages:
                if message.get("kind") == "text":
                    try:
                        payload = json.loads(message["value"])
                    except (KeyError, TypeError, json.JSONDecodeError):
                        return False
                    break
        return (
            isinstance(payload, dict)
            and payload.get("asgi_spec_version") == "2.5"
        )
    if fault["contract"] == "http-body-pump-drain-shutdown-joined":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"upload-ignored").decode("ascii")
            and observation.get("drain_pause_consumed") is True
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("shutdown_bounded") is True
            and observation.get("body_pump_joined") is True
            and "request-body pumps exceeded the graceful timeout"
            not in observation.get("server_log", "")
        )
    if fault["contract"] == "http-body-pump-drain-terminal-frame":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"upload-ignored").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http-body-pump-shutdown-cancelled-join":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"upload-ignored").decode("ascii")
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("shutdown_bounded") is True
            and observation.get("shutdown_fault_consumed") is True
            and "request-body pump failed or was cancelled during shutdown"
            in observation.get("server_log", "")
            and "request-body pumps exceeded the graceful timeout"
            not in observation.get("server_log", "")
        )
    if fault["contract"] == "http-body-pump-shutdown-aborts-hung-pump":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"upload-ignored").decode("ascii")
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("shutdown_bounded") is True
            and observation.get("shutdown_fault_consumed") is True
            and "request-body pumps exceeded the graceful timeout"
            in observation.get("server_log", "")
            and "request-body pump joined after forced abort"
            in observation.get("server_log", "")
            and "panicked" not in observation.get("server_log", "")
        )
    if fault["contract"] == "http-body-pump-shutdown-completes-task-before-abort":
        log = observation.get("server_log", "")
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"upload-ignored").decode("ascii")
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("shutdown_bounded") is True
            and observation.get("shutdown_fault_consumed") is True
            and "request-body pump entered shutdown-hold fault" in log
            and "request-body pumps exceeded the graceful timeout" in log
            and "request-body pump completed during forced-abort join" in log
            and "request-body pump joined after forced abort" in log
            and "panicked" not in log
        )
    if fault["contract"] in {
        "http-body-pump-reaps-cancelled-task",
        "http3-body-pump-reaps-cancelled-task",
    }:
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"read-once").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http-response-header-capacity-recovery-followup-200":
        responses = observation.get("responses", [])
        events = observation.get("application_events", [])
        return (
            isinstance(responses, list) and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") == 500
            and responses[0].get("body_base64")
            == base64.b64encode(b"header capacity rejected").decode("ascii")
            and responses[1].get("status") == 200
            and "http.header-capacity.error:RuntimeError:HTTP response headers: max size reached" in events
            and "http.header-capacity.recovered" in events
        )
    if fault["contract"] == "websocket-header-capacity-error-followup-200":
        followup = observation.get("followup_response")
        events = observation.get("application_events", [])
        return (
            observation.get("handshake_status") == 500
            and isinstance(followup, dict) and followup.get("status") == 200
            and "websocket.header-capacity.accept-sent" in events
            and "websocket.header-capacity.cleanup-completed" in events
            and "uvicorn-rs: WebSocket request failed: max size reached"
            in observation.get("server_log", "").splitlines()
        )
    if fault["contract"] in EAGER_REGISTRATION_CLEANUP_CONTRACTS:
        startup = fault["contract"] in EAGER_LIFESPAN_CLEANUP_CONTRACTS
        events = observation.get("application_events", [])
        log = observation.get("server_log", "")
        common = (
            observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("application_tasks_finished_before_probe_cleanup") is True
            and observation.get("loop_alive_after_server_return") is True
            and observation.get("serve_cancellation_propagated") is True
            and observation.get("shutdown_bounded") is True
        )
        if startup:
            return (
                common
                and "lifespan.async-finally.started" in events
                and "RuntimeError: coverage-injected callback registration failure after inline completion" in log
                and (
                    (
                        observation.get("lifespan_tasks_finished_before_probe_cleanup") is False
                        and "lifespan.async-finally.finished" not in events
                        and "uvicorn-rs: Python ASGI lifespan cancellation cleanup exceeded the graceful timeout" in log
                    ) if fault["contract"].endswith("-timeout") else (
                        observation.get("lifespan_tasks_finished_before_probe_cleanup") is True
                        and "lifespan.async-finally.finished" in events
                    )
                )
            )
        failure = observation.get("failure_response")
        followup = observation.get("followup")
        if fault["contract"].endswith("-normal-return"):
            return (
                common
                and observation.get("lifespan_tasks_finished_before_probe_cleanup") is True
                and isinstance(failure, dict) and failure.get("status") == 500
                and isinstance(followup, dict) and followup.get("status") == 200
                and observation.get("lifespan_shutdown_completed") is True
                and "application.task-cleanup.hold" in events
                and "application.task-cleanup.cancel-suppressed" in events
                and "application.task-cleanup.finished" in events
                and "application.async-finally.started" not in events
                and "RuntimeError: coverage-injected callback registration failure after inline completion"
                in log.splitlines()
                and not any(message in log for message in (
                    "Exception in callback",
                    "Python event loop stopped before the ASGI task started",
                    "Python event loop stopped before the ASGI task completed",
                ))
            )
        return (
            common
            and observation.get("lifespan_tasks_finished_before_probe_cleanup") is True
            and isinstance(failure, dict) and failure.get("status") == 500
            and isinstance(followup, dict) and followup.get("status") == 200
            and observation.get("lifespan_shutdown_completed") is True
            and "application.task-cleanup.cancelled" in events
            and "application.async-finally.started" in events
            and "application.async-finally.finished" in events
            and "RuntimeError: coverage-injected callback registration failure before cancellation cleanup scheduling" in log
            and "coverage-injected cancellation cleanup scheduling failure" in log
        )
    if fault["contract"] == "http-response-reset-cancels-deferred-task":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and "response.reset.app-cancelled" in observation.get("application_events", [])
            and isinstance(followup, dict) and followup.get("status") == 200
        )
    if fault["contract"] == "http-read-eof-recheck-completes":
        followup = observation.get("followup_response")
        return (
            observation.get("disconnect_event") is True
            and observation.get("fault_consumed") is True
            and isinstance(followup, dict) and followup.get("status") == 200
        )
    if fault["contract"] == "server-cancellation-schedule-error-bounded-shutdown":
        events = observation.get("application_events", [])
        log = observation.get("server_log", "")
        return (
            observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and "lifespan.shutdown" in events
            and "MemoryError" in log
            and "cancelled Python ASGI tasks exceeded the graceful timeout" in log
        )
    if fault["contract"] == "server-forced-task-completion-error-bounded-shutdown":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes") == base64.b64encode(b"complete").decode("ascii")
            and observation.get("response_complete_before_app_return") is True
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("application_cancelled") is True
            and observation.get("application_cleanup_completed") is True
            and observation.get("application_tasks_finished_before_probe_cleanup") is True
            and observation.get("loop_alive_after_server_return") is True
            and observation.get("lifespan_shutdown_completed") is True
            and observation.get("shutdown_bounded") is True
            and "Python event loop stopped before the cancelled ASGI task completed"
            in observation.get("server_log", "")
        )
    if fault["contract"] == "http-callback-error-cleans-task-followup-200":
        responses = observation.get("responses")
        log = observation.get("server_log", "")
        borrow_errors = (
            "RuntimeError: Already borrowed", "RuntimeError: Already mutably borrowed",
        )
        if fault["point"] == "python.task-starter.registration-error.borrow-conflict":
            original_error = (
                "RuntimeError: coverage-injected callback registration failure before completion-state borrow"
            )
            error_preserved = original_error in log and not any(error in log for error in borrow_errors)
        elif fault["point"] == "python.task-starter.failure-cleanup.schedule-error":
            error_preserved = (
                "RuntimeError: coverage-injected callback registration failure before cancellation cleanup scheduling"
                in log
                and "coverage-injected cancellation cleanup scheduling failure" in log
                and not any(error in log for error in borrow_errors)
            )
        else:
            error_preserved = any(error in log for error in borrow_errors)
        return (
            error_preserved
            and isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") == 500
            and responses[1].get("status") == 200
            and responses[1].get("body_base64")
            == base64.b64encode(b'{"pending_application_tasks":0}').decode("ascii")
        )
    if fault["contract"] in {
        "http-500-then-followup-200", "http-callback-error-followup-200",
        "http-original-task-start-error-followup-200",
    }:
        responses = observation.get("responses")
        if fault["contract"] == "http-original-task-start-error-followup-200":
            log = observation.get("server_log", "")
            cleanup_error = PYTHON_TASK_START_CLEANUP_ERRORS.get(fault["point"])
            if (
                PYTHON_TASK_START_ERRORS[fault["point"]] not in log.splitlines()
                or (cleanup_error is not None and cleanup_error not in log.splitlines())
                or (cleanup_error is not None and "coroutine 'invoke' was never awaited" in log)
                or any(message in log for message in (
                    "Python event loop stopped before the ASGI task started",
                    "Python event loop stopped before the ASGI task completed",
                    "Exception in callback",
                ))
            ):
                return False
        if fault["contract"] == "http-callback-error-followup-200":
            expected_error = (
                "RuntimeError: coverage-injected callback registration failure after inline completion"
                if fault["point"] == "python.task-starter.inline-completion-registration-error"
                else "asyncio.exceptions.InvalidStateError:"
            )
            if expected_error not in observation.get("server_log", ""):
                return False
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") == 500
            and responses[1].get("status") == 200
        )
    if fault["contract"] == "http3-500-error-body":
        return (
            observation.get("status") == 500
            and observation.get("body_bytes") == "SW50ZXJuYWwgU2VydmVyIEVycm9y"
        )
    if fault["contract"] == "http3-connection-task-error-followup-200":
        followup = observation.get("followup_response")
        return (
            observation.get("handshake_rejected") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "http3-connection-error-cancels-held-response-followup-200":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and observation.get("early_body_bytes") == base64.b64encode(b"first/").decode("ascii")
            and observation.get("body_bytes") == base64.b64encode(b"first/").decode("ascii")
            and observation.get("response_stream_started") is True
            and observation.get("response_incomplete") is True
            and observation.get("body_stream_error") is True
            and observation.get("stream_reset") is True
            and observation.get("connection_closed") is True
            and type(observation.get("peer_close_code")) is int
            and observation.get("peer_close_code") == 0x102
            and observation.get("trigger_request_sent") is True
            and observation.get("fault_consumed") is True
            and observation.get("request_task_cancellation_observed") is True
            and observation.get("connection_error_observed") is True
            and observation.get("diagnostics_ordered") is True
            and observation.get("application_cleanup_before_followup") is True
            and observation.get("application_events", []).count("response.reset.app-cancelled") == 1
            and "panicked" not in observation.get("server_log", "")
            and isinstance(followup, dict) and followup.get("status") == 200
            and followup.get("stream_reset") is False
        )
    if fault["contract"] == "http3-stream-reset-on-runtime-error":
        return (
            observation.get("stream_reset") is True
            or observation.get("connection_closed") is True
        )
    if fault["contract"] == "http3-peer-close-classification-defensive-error":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("server_error_observed") is True
        )
    if fault["contract"] == "http3-request-task-error-before-peer-close-followup-200":
        responses = observation.get("responses")
        followup = observation.get("followup_response")
        return (
            observation.get("request_task_failure_observed_before_peer_close") is True
            and isinstance(responses, list) and len(responses) == 2
            and all(
                isinstance(response, dict) and response.get("status") == 200
                and response.get("stream_reset") is False
                for response in responses
            )
            and responses[0] == responses[1]
            and isinstance(followup, dict) and followup.get("status") == 200
            and followup.get("stream_reset") is False
            and followup == responses[-1]
        )
    if fault["contract"] == "http3-body-pump-early-exit-500":
        return (
            observation.get("status") == 500
            and observation.get("body_bytes") == ""
        )
    if fault["contract"] == "http3-upload-body-pump-preserves-data":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"read-once").decode("ascii")
        )
    if fault["contract"] == "http3-upload-body-pump-send-error-disconnect":
        return observation.get("status") == 500 and observation.get("ordered_body_bytes") == ""
    if fault["contract"] == "http3-upload-body-pump-completes-final-message":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"upload-disconnect-observed").decode("ascii")
        )
    if fault["contract"] == "http3-connection-task-shutdown-error":
        return (
            observation.get("process_terminated") is True
            and "HTTP/3 connection task failed during shutdown" in observation.get("server_log", "")
        )
    if fault["contract"] == "http3-connection-task-shutdown-hang-aborted":
        return (
            observation.get("process_terminated") is True
            and "HTTP/3 connection tasks exceeded grace period" in observation.get("server_log", "")
        )
    if fault["contract"] == "http3-endpoint-accept-closes-http3":
        followup = observation.get("followup_response")
        return (
            observation.get("startup_error_observed") is False
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "http2-500-empty-body":
        return (
            observation.get("status") == 500
            and observation.get("body_bytes") == ""
        )
    if fault["contract"] == "http3-client-abort-disconnect-followup":
        followup = observation.get("followup_response")
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "http3-body-pump-error-stop-disconnect-followup-200":
        followup = observation.get("followup")
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-server-shutdown-force-abort":
        return (
            observation.get("status") == 200
            and observation.get("process_terminated") is True
            and "HTTP/3 shutdown exceeded grace period" in observation.get("server_log", "")
        )
    if fault["contract"] == "http-final-body-preserved-after-app-task-panic":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes") == "Y29tcGxldGUtYmVmb3JlLXRhc2stcGFuaWM="
            and "ASGI app task failed after the response body completed" in observation.get("server_log", "")
            and "coverage-injected ASGI app task panic after final response body" in observation.get("server_log", "")
        )
    if fault["contract"] == "http-task-panic-before-final-body-closes-stream":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes") == "aW5jb21wbGV0ZS8="
            and observation.get("connection_closed") is True
        )
    if fault["contract"] == "http-incomplete-body-preserves-emitted-chunk-after-consumer-pause":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes") == "aW5jb21wbGV0ZS8="
            and observation.get("connection_closed") is True
        )
    if fault["contract"] == "http-start-and-final-body-preserved-after-task-wins-select":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes") == "eWllbGRlZC1hZnRlci1zdGFydA=="
            and observation.get("connection_closed") is False
        )
    if fault["contract"] == "http-response-body-queued-after-receiver-pending":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes") == "cXVldWVkLWFmdGVyLXBlbmRpbmc="
            and observation.get("connection_closed") is False
        )
    if fault["contract"] == "http-start-error-close-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") is None
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
        )
    if fault["contract"] == "http-response-body-error-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") == 200
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
        )
    if fault["contract"] == "http-response-backpressure-body-preserved-followup-200":
        responses = observation.get("responses")
        expected_body = b"".join(bytes([index]) * 4096 for index in range(256))
        if not isinstance(responses, list) or len(responses) != 2:
            return False
        first, followup = responses
        if not isinstance(first, dict) or not isinstance(followup, dict):
            return False
        try:
            first_body = base64.b64decode(first.get("body_base64", ""), validate=True)
        except (binascii.Error, ValueError):
            return False
        return (
            first.get("status") == 200
            and first.get("content_type") == "application/octet-stream"
            and first_body == expected_body
            and followup.get("status") == 200
        )
    if fault["contract"] == "http-connection-task-error-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") == 200
            and responses[1].get("status") == 200
            and "connection task failed:" in observation.get("server_log", "")
        )
    if fault["contract"] == "http-connection-task-write-error-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") is None
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
            and "connection task failed:" in observation.get("server_log", "")
        )
    if fault["contract"] == "http-concurrent-receive-after-lock-contention":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"first-second").decode("ascii")
            and "coverage observed concurrent HTTP receive lock contention"
            in observation.get("server_log", "")
        )
    if fault["contract"] == "http-task-completion-error-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and isinstance(responses[0], dict)
            and isinstance(responses[1], dict)
            and responses[0].get("status") == 200
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
            and "Python event loop stopped before the ASGI task completed"
            in observation.get("server_log", "")
        )
    if fault["contract"] == "http-start-response-preserved-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") == 200
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
        )
    if fault["contract"] == "http-reset-before-body-worker-disconnect-followup-200":
        followup = observation.get("followup_response")
        workflow_elapsed = observation.get("disconnect_workflow_seconds")
        events = observation.get("application_events", [])
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("body_base64") == base64.b64encode(b"seen").decode("ascii")
            and "http.disconnect.waiting" in events
            and "http.disconnect" in events
            and "http.disconnect.second:http.disconnect" in events
            and isinstance(workflow_elapsed, (int, float))
            and 0 <= workflow_elapsed < 8
        )
    if fault["contract"] == "http-body-pump-error-stop-disconnect-followup-200":
        followup = observation.get("followup_response")
        events = observation.get("application_events", [])
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("body_base64") == base64.b64encode(b"seen").decode("ascii")
            and "http.disconnect.waiting" in events
            and "http.disconnect" in events
            and "http.disconnect.second:http.disconnect" in events
        )
    if fault["contract"] == "http-disconnect-error-followup-200":
        followup = observation.get("followup_response")
        return isinstance(followup, dict) and followup.get("status") == 200
    if fault["contract"] == "http-immediate-disconnect-message-error-followup-200":
        followup = observation.get("followup_response")
        events = observation.get("application_events")
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and isinstance(events, list)
            and "http.disconnect" in events
            and "http.disconnect.repeat-error:MemoryError" in events
        )
    if fault["contract"] == "server-startup-failure":
        if fault["point"] in {
            "server.graceful-timeout.overflow", "server.serve.control.borrow-conflict",
            "native.runtime.build.error",
        }:
            message = {
                "server.graceful-timeout.overflow": "ValueError: graceful_timeout exceeds the supported monotonic deadline range",
                "server.serve.control.borrow-conflict": "RuntimeError: Already mutably borrowed",
                "native.runtime.build.error": "OSError: could not initialize Tokio runtime: coverage-injected native runtime build error",
            }[fault["point"]]
            log = observation.get("server_log", "")
            return (
                observation.get("startup_failed") is True
                and message in log.splitlines()
                and "lifespan.startup" not in observation.get("application_events", [])
                and "Exception in callback" not in log
                and "Python event loop stopped before the ASGI task started" not in log
                and "Python event loop stopped before the ASGI task completed" not in log
            )
        if fault["point"] == "server.listener.accept-error":
            events = observation.get("application_events")
            return (
                observation.get("startup_failed") is True
                and isinstance(events, list)
                and "lifespan.startup" in events
                and "lifespan.shutdown" in events
            )
        return observation.get("startup_failed") is True
    if fault["contract"] == "server-lifespan-startup-auto-fallback":
        followup = observation.get("followup_response")
        return (
            observation.get("startup_error_observed") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "server-shutdown-failure":
        return (
            observation.get("process_terminated") is True
            and isinstance(observation.get("process_exit_code"), int)
            and observation["process_exit_code"] != 0
        )
    if fault["contract"] == "server-lifespan-task-cancel":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and "lifespan.shutdown.hold" in events
            and "lifespan.task-cancelled" in events
        )
    if fault["contract"] == "server-connection-task-error-during-shutdown":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and "request.cancelled" in events
            and "lifespan.shutdown" in events
            and "connection task failed during shutdown" in observation.get("server_log", "")
        )
    if fault["contract"] == "server-connection-task-shutdown-timeout-abort":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and "request.cancelled" in events
            and "lifespan.shutdown" in events
            and "panicked" not in observation.get("server_log", "")
        )
    if fault["contract"] == "server-hyper-connection-error-during-shutdown":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and observation.get("connection_closed") is True
            and observation.get("response_stream_started") is True
            and "lifespan.shutdown" in events
            and "connection task failed during shutdown:" in observation.get("server_log", "")
        )
    if fault["contract"] == "websocket-server-shutdown-force-abort":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and "websocket.hold" in events
            and "websocket.app-cancelled" in events
        )
    if fault["contract"] == "websocket-driver-send-error-followup-200":
        followup = observation.get("followup_response")
        return (
            observation.get("handshake_status") == 101
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "websocket-driver-send-error-cancels-app":
        events = observation.get("application_events", [])
        followup = observation.get("followup_response")
        return (
            observation.get("handshake_status") == 101
            and "websocket.app-cancelled-after-send-error" in events
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "websocket-handshake-error-followup-200":
        followup = observation.get("followup_response")
        return (
            (
                observation.get("handshake_status") == 500
                if fault["point"] == "websocket.accept-key.header-value-error"
                else observation.get("handshake_status") != 101
            )
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and (
                fault["point"] != "websocket.accept-key.header-value-error"
                or "uvicorn-rs: WebSocket request failed: failed to parse header value"
                in observation.get("server_log", "")
            )
        )
    if fault["contract"] == "websocket-teardown-and-followup-200":
        events = observation.get("application_events")
        followup = observation.get("followup_response")
        healthy_followup = (
            observation.get("handshake_status") == 101
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
        expected_disconnect = {
            "websocket.receive.channel-closed": "websocket.disconnect:1005:",
            "websocket.receive.connection-closed": "websocket.disconnect:1005:",
            "websocket.driver.connection-closed": "websocket.disconnect:1006:",
            "websocket.driver.peer-eof": "websocket.disconnect:1006:",
            "websocket.outgoing.queue-receiver-closed": "websocket.outgoing.queue-closed",
        }.get(fault["point"])
        if expected_disconnect is None:
            return healthy_followup
        return (
            healthy_followup
            and isinstance(events, list)
            and any(event.startswith(expected_disconnect) for event in events)
        )
    return False


def add_verification_metadata(
    outcomes: list[dict[str, Any]], cases: list[dict[str, Any]]
) -> None:
    cases_by_id = {case["case_id"]: case for case in cases}
    for outcome in outcomes:
        case = cases_by_id[outcome["case_id"]]
        outcome["verification"] = case.get("verification", "oracle-parity")
        outcome["fault"] = case.get("fault")


def start_profile_servers(
    profile: dict[str, Any],
    tempdir: Path,
    cases: list[dict[str, Any]],
    coverage_profile_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any], Path | None]:
    profile_id = profile["id"]
    tls = profile_id in {
        "http2",
        "http3",
        "http1-tls",
        "lifecycle-tls",
        "websocket-tls",
        "startup-missing-private-key",
        "startup-empty-private-key",
        "startup-invalid-private-key-pem",
        "startup-mismatched-private-key",
    }
    if tls:
        certificate, key, trust_anchor = make_certificate(tempdir)
    else:
        certificate, key, trust_anchor = None, None, None
    config = tempdir / "hypercorn.toml"
    config.write_text("keep_alive_max_requests = 100000000\n", encoding="utf-8")
    graceful_timeout_seconds = next(
        (case["lifecycle"]["graceful_timeout_seconds"] for case in cases if "lifecycle" in case),
        1,
    )
    expect_startup_failure = any(
        "startup_failure" in case and case["startup_failure"]["expect_failed"]
        for case in cases
    )
    coverage_fault_control_path = None
    has_fault_contract = any(case.get("verification") == "fault-contract" for case in cases)
    needs_native_fault_control = any(
        case.get("verification") == "fault-contract"
        and case["fault"]["point"] in FAULT_POINTS
        for case in cases
    )
    if needs_native_fault_control:
        coverage_fault_control_path = tempdir / "coverage-fault.txt"
    if has_fault_contract and coverage_fault_control_path is not None:
        startup_fault_point = next(
            (
                case["fault"]["point"]
                for case in cases
                if case.get("verification") == "fault-contract"
                and (
                    "startup_failure" in case or "startup_fallback" in case
                    or case.get("fault", {}).get("contract") in {
                        "server-eager-lifespan-registration-cleanup",
                        "server-eager-lifespan-registration-cleanup-timeout",
                    }
                )
            ),
            "",
        )
        coverage_fault_control_path.write_text(startup_fault_point, encoding="utf-8")
    servers: dict[str, dict[str, Any]] = {}
    # Fault contracts execute only the instrumented target. Starting an
    # unused reference can introduce unrelated startup/shutdown failures,
    # particularly for fixtures that deliberately hold lifespan completion.
    server_ids = ["uvicorn-rs"]
    if any(case.get("verification", "oracle-parity") == "oracle-parity" for case in cases):
        server_ids.insert(0, profile["oracle"])
    try:
        for server_id in server_ids:
            port = free_port(tcp_and_udp=profile_id == "http3")
            events = tempdir / f"{server_id}-events.jsonl"
            servers[server_id] = start_server(
                server_id,
                profile,
                graceful_timeout_seconds,
                port,
                events,
                certificate,
                key,
                config,
                expect_startup_failure=(
                    expect_startup_failure
                    and not (
                        server_id == profile["oracle"]
                        and any(
                            case.get("verification") == "fault-contract"
                            and "startup_failure" in case
                            for case in cases
                        )
                    )
                ),
                coverage_profile_dir=(
                    coverage_profile_dir / "target"
                    if server_id == "uvicorn-rs" and coverage_profile_dir is not None
                    else None
                ),
                coverage_fault_control_path=(
                    coverage_fault_control_path
                    if server_id == "uvicorn-rs" and coverage_fault_control_path is not None
                    else None
                ),
                lifespan_mode_override=(
                    "complete"
                    if server_id == profile["oracle"]
                    and (
                        profile_id.startswith("lifespan-fault-asgi-startup-failed")
                        or profile_id.startswith("lifespan-fault-asgi-shutdown-failed")
                    )
                    else None
                ),
                async_cleanup_delay_seconds=next(
                    (case["lifecycle"].get("cleanup_delay_seconds", 0.5)
                     for case in cases if "lifecycle" in case), 0.5
                ),
                observe_connection_errors=any(
                    case["operation"] in {"http3.peer-close", "http3.peer-close-registered"}
                    for case in cases
                ),
            )
    except Exception:
        for server in servers.values():
            stop_server(server)
        raise
    return servers.get(profile["oracle"]), servers["uvicorn-rs"], trust_anchor


def execute_profile(
    profile: dict[str, Any],
    cases: list[dict[str, Any]],
    h3_client: Path | None,
    operations: dict[str, dict[str, Any]],
    coverage_profile_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    startup_cases = [
        case for case in cases
        if "startup_failure" in case or "startup_fallback" in case
        or case.get("fault", {}).get("contract") in {
            "server-eager-lifespan-registration-cleanup",
            "server-eager-lifespan-registration-cleanup-timeout",
        }
    ]
    if startup_cases and (len(cases) != 1 or len(startup_cases) != 1):
        # Startup faults are loaded before the target process starts. Isolate
        # each such case so its process-wide fault cannot disable the other
        # cases grouped under the same protocol profile.
        startup_case_ids = {case["case_id"] for case in startup_cases}
        case_groups = [
            [case for case in cases if case["case_id"] not in startup_case_ids],
            *([case] for case in startup_cases),
        ]
        grouped_outcomes: dict[str, dict[str, Any]] = {}
        infrastructure_errors = []
        for case_group in case_groups:
            if not case_group:
                continue
            group_outcomes, group_errors = execute_profile(
                profile,
                case_group,
                h3_client,
                operations,
                coverage_profile_dir,
            )
            grouped_outcomes.update(
                (outcome["case_id"], outcome) for outcome in group_outcomes
            )
            infrastructure_errors.extend(group_errors)
        return [grouped_outcomes[case["case_id"]] for case in cases], infrastructure_errors

    outcomes = []
    infrastructure_errors = []
    with tempfile.TemporaryDirectory(prefix=f"uvicorn-rs-parity-{profile['id']}-") as temporary:
        tempdir = Path(temporary)
        try:
            oracle, target, trust_anchor = start_profile_servers(
                profile, tempdir, cases, coverage_profile_dir
            )
        except Exception as error:
            infrastructure_errors.append({
                "profile": profile["id"],
                "server": None,
                "kind": "profile_startup_failure",
                "diagnostic": str(error)[-1000:],
            })
            for case in cases:
                outcomes.append({
                    "case_id": case["case_id"],
                    "profile": profile["id"],
                    "operation": case["operation"],
                    "requirements": case["covers"],
                    "status": "not_run",
                    "reason": "profile startup failed before this case could execute",
                })
            add_verification_metadata(outcomes, cases)
            return outcomes, infrastructure_errors
        servers = {server["id"]: server for server in (oracle, target) if server is not None}
        server_history = list(servers.values())
        for server in server_history:
            server["attempted_cases"] = []
        # A graceful-shutdown workflow stops the target server by design, so
        # execute it after cases that still need the shared profile process.
        # Closing an HTTP/1.1 WebSocket upgrade also terminates the server, so
        # it belongs at the end of the shared-process profile for the same
        # reason as the held-session shutdown workflow.
        def stops_server(case: dict[str, Any]) -> bool:
            return bool(
                "lifecycle" in case
                or case["operation"] in {"http3.peer-close", "http3.peer-close-registered"}
                or case.get("request", {}).get("hold_open_for_shutdown", False)
                or case.get("request_stream", {}).get("hold_until_shutdown", False)
                or case.get("websocket", {}).get("shutdown", False)
                or case.get("websocket", {}).get("shutdown_during_upgrade", False)
                # Keep the TLS scope-close probe independent from the next
                # WSS workflow. Both servers close this WebSocket normally,
                # but their TLS transports can still be draining when the
                # next case starts on the shared profile listener.
                or case["case_id"] == "websocket-tls.scope-headers-path-query-and-subprotocols"
            )

        def needs_fresh_server(case: dict[str, Any]) -> bool:
            return case["case_id"] == "websocket-tls.scope-headers-path-query-and-subprotocols"

        execution_cases = sorted(cases, key=stops_server)
        try:
            for case_index, case in enumerate(execution_cases):
                if case_index:
                    previous_case = execution_cases[case_index - 1]
                    if stops_server(previous_case) or needs_fresh_server(case) or case["operation"] in {
                        "http3.peer-close", "http3.peer-close-registered",
                        "http3.request-task-recovery",
                        "http3.request-task-drain-on-accept-error",
                    }:
                        # These workflows intentionally terminate each shared
                        # profile server. Start fresh processes before the next
                        # shutdown case so both workflows receive a live server.
                        # A diagnostic peer-close workflow also needs fresh
                        # processes before it starts: earlier connection tasks
                        # could otherwise emit failure logs after its offset.
                        for server in servers.values():
                            stop_server(server)
                        oracle, target, trust_anchor = start_profile_servers(
                            profile,
                            tempdir,
                            execution_cases[case_index:],
                            coverage_profile_dir,
                        )
                        servers = {
                            server["id"]: server for server in (oracle, target) if server is not None
                        }
                        for server in servers.values():
                            server["attempted_cases"] = []
                            server_history.append(server)
                try:
                    try:
                        target["attempted_cases"].append(case)
                        fault_control_path = target.get("coverage_fault_control_path")
                        if (
                            fault_control_path is not None
                            and (
                                case.get("verification", "oracle-parity") != "fault-contract"
                                or case.get("fault", {}).get("point") not in FAULT_POINTS
                            )
                        ):
                            # A fault is armed through a file and remains there
                            # until replaced. Clear it before each ordinary
                            # target case so it cannot leak into later requests.
                            fault_control_path.write_text("", encoding="utf-8")
                        target_raw = execute_case(case, target, profile, trust_anchor, h3_client)
                    except Exception as error:
                        raise ParityError(f"target uvicorn-rs adapter failed: {error}") from error
                    operation = operations[case["operation"]]
                    target_result = project_observation(target_raw, operation)
                    if case.get("verification", "oracle-parity") == "fault-contract":
                        oracle_result = None
                        fault_observation = target_result
                        if case["fault"]["contract"] in {
                            "http-callback-error-followup-200",
                            "http-original-task-start-error-followup-200",
                            "http-callback-error-cleans-task-followup-200",
                        }:
                            fault_observation = {**target_result, "server_log": target_raw["server_log"]}
                        elif case["fault"]["contract"] == "http-response-header-capacity-recovery-followup-200":
                            fault_observation = {
                                **target_result,
                                "application_events": target_raw["application_events"],
                            }
                        elif case["fault"]["contract"] == "websocket-header-capacity-error-followup-200":
                            fault_observation = {**target_result, "server_log": target_raw["server_log"]}
                        elif case["fault"]["contract"] == "server-forced-task-completion-error-bounded-shutdown":
                            fault_observation = {**target_result, "server_log": target_raw["server_log"]}
                        elif case["fault"]["contract"] == "server-startup-failure":
                            fault_observation = {**target_result, "server_log": read_server_log(target)}
                        elif case["fault"]["contract"] == "websocket-handshake-error-followup-200":
                            fault_observation = {**target_result, "server_log": target_raw["server_log"]}
                        elif case["fault"]["contract"] in EAGER_REGISTRATION_CLEANUP_CONTRACTS:
                            fault_observation = {**target_result, "server_log": target_raw["server_log"],
                                                 "failure_response": target_raw["failure_response"],
                                                 "followup": target_raw["followup"],
                                                 "lifespan_shutdown_completed": target_raw["lifespan_shutdown_completed"]}
                        elif case["fault"]["contract"] == "http-response-reset-cancels-deferred-task":
                            fault_observation = {**target_result, "application_events": target_raw["application_events"]}
                        elif case["fault"]["contract"] == "http-read-eof-recheck-completes":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] == "http-reset-before-body-worker-disconnect-followup-200":
                            fault_observation = {
                                **target_result,
                                "application_events": target_raw["application_events"],
                                "reset_elapsed_seconds": target_raw["reset_elapsed_seconds"],
                                "disconnect_workflow_seconds": target_raw["disconnect_workflow_seconds"],
                            }
                        elif case["fault"]["contract"] == "http-body-pump-drain-shutdown-joined":
                            fault_observation = {**target_result, **target_raw}
                        elif case["fault"]["contract"] in {
                            "http-body-pump-error-stop-disconnect-followup-200",
                            "http-body-pump-drain-terminal-frame",
                            "http-body-pump-reaps-cancelled-task",
                            "http-body-pump-shutdown-cancelled-join",
                            "http-body-pump-shutdown-aborts-hung-pump",
                            "http-body-pump-shutdown-completes-task-before-abort",
                            "http3-body-pump-error-stop-disconnect-followup-200",
                            "http3-body-pump-reaps-cancelled-task",
                        }:
                            fault_observation = {**target_result, **target_raw}
                        elif case["fault"]["contract"] == "server-cancellation-schedule-error-bounded-shutdown":
                            fault_observation = {**target_result, "server_log": target_raw["server_log"],
                                                 "process_exit_code": target_raw["process_exit_code"]}
                        elif case["fault"]["contract"] == "http-task-completion-error-followup-200":
                            fault_observation = {
                                **target_result,
                                "server_log": read_server_log(target),
                            }
                        elif (
                            case["fault"]["contract"]
                            == "http-immediate-disconnect-message-error-followup-200"
                        ):
                            fault_observation = {
                                **target_result,
                                "application_events": target_raw["application_events"],
                            }
                        elif case["fault"]["contract"] in {
                            "http-connection-task-error-followup-200",
                            "http-connection-task-write-error-followup-200",
                        }:
                            deadline = time.monotonic() + 2
                            server_log = read_server_log(target)
                            while (
                                "connection task failed:" not in server_log
                                and time.monotonic() < deadline
                            ):
                                time.sleep(0.01)
                                server_log = read_server_log(target)
                            fault_observation = {
                                **target_result,
                                "server_log": server_log,
                            }
                        elif case["fault"]["contract"] == "http-concurrent-receive-after-lock-contention":
                            fault_observation = {
                                **target_result,
                                "server_log": read_server_log(target),
                            }
                        elif case["fault"]["contract"] == "http-final-body-preserved-after-app-task-panic":
                            deadline = time.monotonic() + 2
                            server_log = read_server_log(target)
                            while (
                                "ASGI app task failed after the response body completed" not in server_log
                                and time.monotonic() < deadline
                            ):
                                time.sleep(0.01)
                                server_log = read_server_log(target)
                            fault_observation = {
                                **target_result,
                                "server_log": server_log,
                            }
                        elif case["fault"]["contract"] == "server-connection-task-error-during-shutdown":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                            }
                        elif case["fault"]["contract"] == "server-connection-task-shutdown-timeout-abort":
                            fault_observation = {
                                **target_result,
                                "process_exit_code": target_raw["process_exit_code"],
                                "server_log": target_raw["server_log"],
                            }
                        elif case["fault"]["contract"] == "server-hyper-connection-error-during-shutdown":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                            }
                        elif case["fault"]["contract"] == "http3-server-shutdown-force-abort":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                            }
                        elif case["fault"]["contract"] in {
                            "http3-connection-task-shutdown-error",
                            "http3-connection-task-shutdown-hang-aborted",
                        }:
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                            }
                        matches = fault_contract_matches(case["fault"], fault_observation)
                        difference = (
                            None if matches else
                            f"fault contract {case['fault']['contract']!r} did not hold"
                        )
                        if not matches:
                            # Keep the evidence evaluated by the predicate in
                            # failures, including bounded process diagnostics.
                            difference += ": " + json.dumps(
                                fault_observation, sort_keys=True
                            )
                    else:
                        if oracle is None:
                            raise ParityError("oracle-parity workflow has no live reference server")
                        try:
                            oracle["attempted_cases"].append(case)
                            oracle_raw = execute_case(case, oracle, profile, trust_anchor, h3_client)
                        except Exception as error:
                            diagnostic = {
                                "case_id": case["case_id"],
                                "profile": profile["id"],
                                "events": read_events(oracle["events"]),
                                "server_log": read_server_log(oracle)[-2000:],
                                "oracle_process": server_process_diagnostic(oracle),
                                "target_process": server_process_diagnostic(target),
                                "target_server_log": read_server_log(target)[-2000:],
                            }
                            raise ParityError(
                                f"oracle {oracle['id']} adapter failed: {error}; "
                                f"diagnostic={json.dumps(diagnostic, sort_keys=True)}"
                            ) from error
                        oracle_result = project_observation(oracle_raw, operation)
                        comparison_fields = operation.get("compare", operation["observe"])
                        oracle_comparison = {
                            field: oracle_result[field] for field in comparison_fields
                        }
                        target_comparison = {
                            field: target_result[field] for field in comparison_fields
                        }
                        matches = oracle_comparison == target_comparison
                        required = operation.get("required_observations", {})
                        if any(
                            oracle_result.get(field) != value or target_result.get(field) != value
                            for field, value in required.items()
                        ):
                            matches = False
                        if oracle_comparison != target_comparison:
                            difference = "observed public fields differ exactly"
                        elif not matches:
                            difference = f"required observation did not match {required!r}"
                        else:
                            difference = None
                    outcomes.append({
                        "case_id": case["case_id"],
                        "profile": profile["id"],
                        "operation": case["operation"],
                        "requirements": case["covers"],
                        "status": "passed" if matches else "failed",
                        "oracle_observation": oracle_result,
                        "target_observation": target_result,
                        "server_exit_codes": {
                            "oracle": oracle["process"].returncode if oracle is not None else None,
                            "target": target["process"].returncode,
                        },
                        "difference": difference,
                    })
                    print(f"{'PASS' if matches else 'FAIL'} {profile['id']}: {case['case_id']}", flush=True)
                except Exception as error:  # Preserve adapter failures in the generated result.
                    outcomes.append({
                        "case_id": case["case_id"],
                        "profile": profile["id"],
                        "operation": case["operation"],
                        "requirements": case["covers"],
                        "status": "infrastructure_failed",
                        "error": {"class": type(error).__name__, "message": str(error)[:5000]},
                    })
                    print(f"ERROR {profile['id']}: {case['case_id']}: {error}", flush=True)
                    for unrun_case in execution_cases[case_index + 1:]:
                        outcomes.append({
                            "case_id": unrun_case["case_id"],
                            "profile": profile["id"],
                            "operation": unrun_case["operation"],
                            "requirements": unrun_case["covers"],
                            "status": "not_run",
                            "reason": f"an earlier {profile['id']} case failed to execute",
                    })
                    break
        finally:
            for server in server_history:
                exit_code, logs = stop_server(server)
                captured_log = server.get("captured_log", logs)
                if captured_log.strip():
                    print(f"--- {server['id']} server log ---\n{captured_log}", file=sys.stderr)
                normal_signal_exit = server["id"] == "uvicorn" and exit_code == -signal.SIGTERM
                expected_startup_error = server.get("startup_failed", False)
                expected_lifespan_shutdown_error = (
                    profile["id"].startswith("lifespan-shutdown-")
                    or profile["id"] == "lifespan-startup-complete-then-returns"
                    or any(
                        case.get("fault", {}).get("contract")
                        in {"server-shutdown-failure", "server-lifespan-task-cancel"}
                        for case in server["attempted_cases"]
                    )
                )
                panic_issues = rust_panic_issues(
                    server, server["attempted_cases"], captured_log
                )
                if panic_issues:
                    infrastructure_errors.append({
                        "profile": profile["id"],
                        "server": server["id"],
                        "pid": server["process"].pid,
                        "kind": "server_panic_failure",
                        "exit_code": exit_code,
                        "panic_issues": panic_issues,
                        "diagnostic": logs[-1000:],
                    })
                if (
                    (exit_code != 0 and not normal_signal_exit and not expected_startup_error
                     and not expected_lifespan_shutdown_error)
                ):
                    infrastructure_errors.append({
                        "profile": profile["id"],
                        "server": server["id"],
                        "kind": "server_shutdown_failure",
                        "exit_code": exit_code,
                        "diagnostic": logs[-1000:],
                    })
    add_verification_metadata(outcomes, cases)
    return outcomes, infrastructure_errors


def validate_result_shape(
    result: dict[str, Any],
    selected_cases: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """Reject incomplete or internally inconsistent evidence before writing it."""

    exact_keys(result, {"schema", "run", "status", "summary", "cases", "infrastructure_errors"}, "result")
    if result["schema"] != RESULT_SCHEMA:
        raise ParityError(f"unsupported result schema: {result['schema']!r}")
    run = result["run"]
    exact_keys(
        run,
        {"run_id", "started_at", "finished_at", "manifest", "inputs", "environment", "target", "harness", "command"},
        "result.run",
    )
    if not isinstance(run["run_id"], str) or not run["run_id"]:
        raise ParityError("result.run.run_id must be non-empty")
    exact_keys(run["manifest"], {"path", "schema", "sha256"}, "result.run.manifest")
    if run["manifest"]["schema"] != manifest["schema"]:
        raise ParityError("result manifest schema differs from the active contract")
    expected_inputs = [str((FIXTURES / path).relative_to(ROOT)) for path in manifest["inputs"]]
    if not isinstance(run["inputs"], list) or [item.get("path") for item in run["inputs"]] != expected_inputs:
        raise ParityError("result input identities do not match the manifest index")
    for item in run["inputs"]:
        exact_keys(item, {"path", "schema", "sha256"}, "result.run.input")
        if item["schema"] != INPUT_SCHEMA:
            raise ParityError(f"result input schema is invalid: {item['schema']!r}")
    exact_keys(run["environment"], {"python", "platform", "machine", "rustc", "dependencies"}, "result.run.environment")
    dependencies = run["environment"]["dependencies"]
    if not isinstance(dependencies, dict):
        raise ParityError("result environment dependencies must be an object")
    for oracle in manifest["oracles"]:
        pinned = [(oracle["id"], oracle["version"])]
        pinned.extend((component["id"], component["version"]) for component in oracle["components"])
        for distribution, version in pinned:
            if dependencies.get(distribution) != version:
                raise ParityError(f"result identity does not match pinned {distribution} version {version}")
    exact_keys(
        run["target"],
        {"revision", "dirty", "native_extension", "cargo_lock_sha256", "source_sha256"},
        "result.run.target",
    )
    exact_keys(run["target"]["native_extension"], {"path", "sha256"}, "result.run.target.native_extension")
    if not isinstance(run["target"]["dirty"], bool):
        raise ParityError("result target dirty flag must be boolean")
    exact_keys(
        run["harness"],
        {"runner", "runner_sha256", "fixture_app", "fixture_app_sha256", "http3_client"},
        "result.run.harness",
    )
    if run["harness"]["http3_client"] is not None:
        exact_keys(run["harness"]["http3_client"], {"path", "sha256"}, "result.run.harness.http3_client")
    for value, label in (
        (run["manifest"]["sha256"], "manifest"),
        (run["target"]["native_extension"]["sha256"], "native extension"),
        (run["target"]["cargo_lock_sha256"], "Cargo.lock"),
        (run["target"]["source_sha256"], "Rust source"),
        (run["harness"]["runner_sha256"], "runner"),
        (run["harness"]["fixture_app_sha256"], "fixture app"),
        *((item["sha256"], "input") for item in run["inputs"]),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ParityError(f"result {label} identity must be a lowercase sha256 digest")
    if run["harness"]["http3_client"] is not None:
        value = run["harness"]["http3_client"]["sha256"]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ParityError("result HTTP/3 client identity must be a lowercase sha256 digest")
    if not isinstance(run["command"], list) or not run["command"] or not all(isinstance(part, str) for part in run["command"]):
        raise ParityError("result command must be a non-empty string array")
    expected = {case["case_id"]: case for case in selected_cases}
    recorded = result["cases"]
    if not isinstance(recorded, list):
        raise ParityError("result.cases must be an array")
    ids = [case.get("case_id") for case in recorded]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ParityError("result case IDs do not exactly match selected input case IDs")
    status_counts = {status: 0 for status in ("passed", "failed", "infrastructure_failed", "not_run")}
    operation_index = {
        operation["id"]: operation
        for operation in manifest["operations"]
    }
    for item in recorded:
        if item.get("status") not in status_counts:
            raise ParityError(f"result case {item.get('case_id')!r} has an invalid status")
        status_counts[item["status"]] += 1
        source_case = expected[item["case_id"]]
        if any(
            item.get(field) != source_case.get(source_field)
            for field, source_field in (
                ("profile", "profile"),
                ("operation", "operation"),
                ("requirements", "covers"),
                ("fault", "fault"),
            )
        ):
            raise ParityError(f"result metadata differs from selected input for {item['case_id']!r}")
        verification = source_case.get("verification", "oracle-parity")
        if item.get("verification") != verification:
            raise ParityError(f"result verification policy differs for {item['case_id']!r}")
        status = item["status"]
        common = {"case_id", "profile", "operation", "requirements", "verification", "fault", "status"}
        if status in {"passed", "failed"}:
            exact_keys(
                item,
                common | {"oracle_observation", "target_observation", "server_exit_codes", "difference"},
                f"result.cases[{item['case_id']}]",
            )
            observations = operation_index[item["operation"]]["observe"]
            for side in ("oracle_observation", "target_observation"):
                if verification == "fault-contract" and side == "oracle_observation":
                    if item[side] is not None:
                        raise ParityError(f"{item['case_id']}: fault-contract oracle must be not-applicable")
                    continue
                if not isinstance(item[side], dict) or set(item[side]) != set(observations):
                    raise ParityError(f"{item['case_id']}: {side} fields differ from the operation contract")
            exact_keys(item["server_exit_codes"], {"oracle", "target"}, f"{item['case_id']}.server_exit_codes")
            if status == "passed" and item["difference"] is not None:
                raise ParityError(f"{item['case_id']}: passing case cannot carry a difference")
            if status == "failed" and not isinstance(item["difference"], str):
                raise ParityError(f"{item['case_id']}: failed case must explain the difference")
        elif status == "infrastructure_failed":
            exact_keys(item, common | {"error"}, f"result.cases[{item['case_id']}]")
            exact_keys(item["error"], {"class", "message"}, f"{item['case_id']}.error")
        else:
            exact_keys(item, common | {"reason"}, f"result.cases[{item['case_id']}]")
            if not isinstance(item["reason"], str) or not item["reason"]:
                raise ParityError(f"{item['case_id']}: not-run reason must be non-empty")
    summary = result["summary"]
    exact_keys(summary, {"selected", "executed", "passed", "failed", "not_run", "infrastructure_failed"}, "result.summary")
    expected_counts = {
        "selected": len(selected_cases),
        "executed": len(selected_cases) - status_counts["not_run"],
        "passed": status_counts["passed"],
        "failed": status_counts["failed"],
        "not_run": status_counts["not_run"],
        "infrastructure_failed": status_counts["infrastructure_failed"] + len(result["infrastructure_errors"]),
    }
    if summary != expected_counts:
        raise ParityError(f"result summary does not match case evidence: expected {expected_counts}, found {summary}")
    if not isinstance(result["infrastructure_errors"], list):
        raise ParityError("result.infrastructure_errors must be an array")
    expected_status = "completed" if status_counts["passed"] == len(selected_cases) and not result["infrastructure_errors"] else "failed"
    if result["status"] != expected_status:
        raise ParityError(f"result status does not match case evidence: expected {expected_status!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "asgi-parity" / "result.json")
    parser.add_argument(
        "--case-id",
        action="append",
        help="run only the named input case; repeat to select a batch",
    )
    parser.add_argument(
        "--coverage-profile-dir",
        type=Path,
        help="write this case's target LLVM profile beneath the directory (requires exactly one --case-id)",
    )
    parser.add_argument(
        "--fault-contracts",
        action="store_true",
        help="include coverage-build-only fault-contract cases in addition to oracle parity",
    )
    parser.add_argument(
        "--prebuilt-http3-client",
        action="store_true",
        help="use the prebuilt HTTP/3 client without invoking Cargo; required for frozen benchmark identity",
    )
    args = parser.parse_args()

    manifest, inputs, input_paths = load_contract()
    if args.case_id:
        requested = set(args.case_id)
        known = {case["case_id"] for case in inputs["cases"]}
        unknown = sorted(requested - known)
        if unknown:
            parser.error(f"unknown case ID(s): {', '.join(unknown)}")
        selected_cases = [case for case in inputs["cases"] if case["case_id"] in requested]
    else:
        selected_cases = list(inputs["cases"])
    fault_cases = [case for case in selected_cases if case.get("verification") == "fault-contract"]
    if fault_cases and not args.fault_contracts:
        if args.case_id:
            parser.error("selected fault-contract case requires --fault-contracts and an instrumented coverage build")
        selected_cases = [case for case in selected_cases if case.get("verification", "oracle-parity") != "fault-contract"]
    coverage_profile_dir = args.coverage_profile_dir.resolve() if args.coverage_profile_dir else None
    if coverage_profile_dir is not None:
        if len(selected_cases) != 1 or not args.case_id:
            parser.error("--coverage-profile-dir requires exactly one selected --case-id")
        (coverage_profile_dir / "runner").mkdir(parents=True, exist_ok=True)
        os.environ["LLVM_PROFILE_FILE"] = str(
            coverage_profile_dir / "runner" / "%p-%m.profraw"
        )
    environment, target_identity = runtime_identity(manifest)
    started = utc_now()
    needs_h3_client = any(case["profile"] == "http3" for case in selected_cases)
    h3_client = (
        (prebuilt_h3_client() if args.prebuilt_http3_client else build_h3_client())
        if needs_h3_client else None
    )
    h3_client_sha256 = sha256(h3_client) if h3_client is not None else None
    case_results = []
    infrastructure_errors = []
    profile_map = {profile["id"]: profile for profile in manifest["profiles"]}
    operations = {operation["id"]: operation for operation in manifest["operations"]}
    for profile_id, profile in profile_map.items():
        selected = [case for case in selected_cases if case["profile"] == profile_id]
        if selected:
            profile_results, profile_errors = execute_profile(
                profile,
                selected,
                h3_client,
                operations,
                coverage_profile_dir,
            )
            case_results.extend(profile_results)
            infrastructure_errors.extend(profile_errors)
    counts = {
        "selected": len(selected_cases),
        "executed": sum(result["status"] != "not_run" for result in case_results),
        "passed": sum(result["status"] == "passed" for result in case_results),
        "failed": sum(result["status"] == "failed" for result in case_results),
        "not_run": sum(result["status"] == "not_run" for result in case_results),
        "infrastructure_failed": sum(result["status"] == "infrastructure_failed" for result in case_results) + len(infrastructure_errors),
    }
    status = "completed" if counts["passed"] == counts["selected"] and counts["infrastructure_failed"] == 0 else "failed"
    result = {
        "schema": RESULT_SCHEMA,
        "run": {
            "run_id": uuid.uuid4().hex,
            "started_at": started,
            "finished_at": utc_now(),
            "manifest": {
                "path": str(MANIFEST_PATH.relative_to(ROOT)),
                "schema": manifest["schema"],
                "sha256": sha256(MANIFEST_PATH),
            },
            "inputs": [
                {
                    "path": str(path.relative_to(ROOT)),
                    "schema": INPUT_SCHEMA,
                    "sha256": sha256(path),
                }
                for path in input_paths
            ],
            "environment": environment,
            "target": target_identity,
            "harness": {
                "runner": str(Path(__file__).resolve().relative_to(ROOT)),
                "runner_sha256": sha256(Path(__file__).resolve()),
                "fixture_app": str((FIXTURES / "app.py").relative_to(ROOT)),
                "fixture_app_sha256": sha256(FIXTURES / "app.py"),
                "http3_client": (
                    {
                        "path": str(h3_client.relative_to(ROOT)),
                        "sha256": h3_client_sha256,
                    }
                    if h3_client is not None
                    else None
                ),
            },
            "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        },
        "status": status,
        "summary": counts,
        "cases": case_results,
        "infrastructure_errors": infrastructure_errors,
    }
    validate_result_shape(result, selected_cases, manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "summary": counts, "result": str(args.output)}, indent=2))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ParityError, subprocess.SubprocessError, OSError) as error:
        print(f"parity infrastructure failure: {error}", file=sys.stderr)
        raise SystemExit(2) from error
