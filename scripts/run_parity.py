#!/usr/bin/env python3
"""Execute input-only black-box workflows against a reference and uvicorn-rs."""

from __future__ import annotations

import argparse
import base64
import binascii
import errno
import hashlib
import http.client
import importlib
import ipaddress
import io
import json
import logging
import math
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
import traceback
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from urllib.parse import parse_qs, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import psutil
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    DataReceived,
    InformationalResponseReceived,
    ResponseReceived,
    StreamEnded,
    StreamReset,
    TrailersReceived,
)
from h2.errors import ErrorCodes
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus
from websockets.sync.client import connect as websocket_connect
from parity_identity import runtime_source_digest, runtime_source_hashes


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "parity"
MANIFEST_PATH = FIXTURES / "manifest.json"
APP = "tests.parity.app:app"
MANIFEST_SCHEMA = "uvicorn-rs-parity/manifest@2"
INPUT_SCHEMA = "uvicorn-rs-parity/input@46"
RESULT_SCHEMA = "uvicorn-rs-parity/result@5"
ORACLE_PYTHON = Path(sys.executable)
# Normal-wheel parity must exercise the installed wheel built for this run.
# Source-tree parity leaves this disabled so its Python adapter is loaded from
# the checkout beside the instrumented native extension.
INSTALLED_CANDIDATE_MODE = False
TRACE_HYPERCORN_H3_EVENTS = False
# These messages authorize one deliberately injected panic per attempted
# coverage fault case. They never authorize ordinary target/reference panics
# or a failing process exit. The hook event, not a repeated JoinError log,
# supplies the evidence that the injected native task actually panicked.
COVERAGE_PANIC_MESSAGES = {
    "http.app-task.panic-before-response-start": "coverage-injected ASGI request task panic",
    "http3.native-app-task.panic-before-response-start": "coverage-injected ASGI request task panic",
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
    "http.connection-lifetime.wait-complete",
    "http.connection.peer-read-failed.wait-complete",
    "http.body-pump.batch-limit.one-byte",
    "http.body-pump.batch-threshold.send-connection-closed",
    "http.body-pump.oversized.send-connection-closed",
    "http.body-pump.error.stop-wait",
    "http.body-pump.error.buffered-send-connection-closed",
    "http.body-pump.error.buffered-send-continues",
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
    "http.request.body-segment.length-overflow",
    "http.request.body-segment.out-of-bounds",
    "python.asgi-receive.borrow-conflict",
    "server.control.shutdown.borrow-conflict",
    "server.serve.control.borrow-conflict",
    "server.graceful-timeout.overflow",
    "server.connection.invalid-default-header.source-chain",
    "server.default-header.response-finalization",
    "server.python-locals.get-current",
    "python.task-completion.allocate",
    "http.request.empty-body.channel-closed",
    "websocket.app-task.panic-before-handshake",
    "websocket.native-upgrade.extension-removed-after-dispatch",
    "server.quic-tls.config-error",
    "python.ssl.ca-verifier.import",
    "python.ssl.ca-verifier.protocol",
    "python.ssl.ca-verifier.context",
    "python.ssl.ca-verifier.create-context",
    "python.ssl.ca-verifier.verify-mode",
    "python.ssl.ca-verifier.create-verify-mode",
    "python.ssl.ca-verifier.set-verify-mode",
    "python.ssl.ca-verifier.rust-parse-error",
    "python.ssl.keyfile-error.import",
    "python.ssl.keyfile-error.protocol",
    "python.ssl.keyfile-error.context",
    "python.ssl.keyfile-error.create-context",
    "python.ssl.keyfile.rust-decrypt-error",
    "python.pkcs12.reader.outer-too-long",
    "python.pkcs12.reader.outer-sequence-decode",
    "python.pkcs12.reader.outer-finish",
    "python.pkcs12.reader.encrypted-info-too-long",
    "python.pkcs12.reader.algorithm-too-long",
    "python.pkcs12.reader.parameters-too-long",
    "native.module.wrap-function.serve",
    "native.runtime.build.error",
    "server.websocket-task.shutdown-panic",
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
    "http.response.start.trailers.get-item",
    "http.response.start.trailers.extract",
    "http.response.start.headers.get-item",
    "http.response.start.headers.extract",
    "http.response.date-header.invalid-value",
    "http.response.body.body.get-item",
    "http.response.body.body.extract",
    "http.response.body.more-body.get-item",
    "http.response.body.more-body.extract",
    "http.response.start.channel-closed",
    "http.response.body.channel-closed",
    "http.response.early-hint.disconnected",
    "http.response.early-hint.channel-closed",
    "http.response.trailers.disconnected",
    "http.response.trailers.channel-closed",
    "http.response.trailers.channel-full",
    "http.response.trailers.full-send-closed",
    "http.response.body-consumer.pause",
    "http.response.body-poll.receiver-pending.pause",
    "http.app-task.panic-before-response-start",
    "http3.native-app-task.panic-before-response-start",
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
    "scope.http2.extensions.early-hint.set-item",
    "scope.http2.extensions.response-trailers.set-item",
    "scope.http2.extensions.set-item",
    "scope.state.copy",
    "scope.state.set-item",
    "request.http.type.set-item",
    "request.http.body.set-item",
    "request.http.more-body.set-item",
    "request.http.disconnect.type.set-item",
    "http.receive.immediate-disconnect-message-error",
    "http.receive.lock-contention",
    "server.connection-task.service-error",
    "server.connection-info.missing",
    "server.connection-lifetime.missing",
    "server.peer-read-half-closed.missing",
    "server.peer-read-failed.missing",
    "server.connection-io.poll-write-error",
    "server.tcp-nodelay.set-error",
    "http.asgi-io.allocate",
    "http.asgi.app-invoke",
    "server.listener.accept-error",
    "server.listener.local-addr-error",
    "server.unix-listener.set-permissions-error",
    "server.prebound-transfer.bind-error",
    "server.prebound-transfer.accept-error",
    "server.prebound-transfer.read-error",
    "server.prebound-transfer.recv-error",
    "server.prebound-transfer.missing-marker",
    "server.prebound-transfer.unexpected-ancillary",
    "server.prebound-transfer.control-truncated",
    "server.prebound-transfer.get-descriptor-flags-error",
    "server.prebound-transfer.set-descriptor-flags-error",
    "server.prebound-transfer.listen-error",
    "server.prebound-transfer.nonblocking-error",
    "server.prebound-transfer.tcp-listener-conversion-error",
    "server.prebound-transfer.no-listener",
    "server.prebound-transfer.listener-marker-invalid-count",
    "server.prebound-transfer.end-marker-has-descriptor",
    "server.prebound-transfer.invalid-marker",
    "server.tcp-address-lookup.empty",
    "server.tcp-socket.create-error",
    "server.tcp-socket.reuseaddr-error",
    "server.tcp-socket.bind-error",
    "server.tcp-socket.listen-error",
    "server.http3-endpoint.bind-error",
    "server.http3-task.shutdown-hang",
    "server.websocket-task.shutdown-hang",
    "lifespan.io.allocate",
    "lifespan.app-invoke",
    "lifespan.log-info.import-logging",
    "lifespan.log-info.get-logger",
    "lifespan.log-info.call-get-logger",
    "lifespan.log-info.call-info",
    "websocket.io.allocate",
    "websocket.app-invoke",
    "websocket.native-upgrade.missing",
    "websocket.native-upgrade.register-closed",
    "http3.connection-task.panic",
    "http3.endpoint.accept-closed",
    "http3.connection-task.panic-during-shutdown",
    "http3.connection-task.shutdown-hang",
    "http3.connection.create-error",
    "http3.connection.accept-error",
    "http3.connection-info.missing",
    "http3.connection-lifetime.missing",
    "http3.native-body-pump.stop-wait",
    "http3.native-body-pump.disconnect-send-stop-wait",
    "http3.native-body-pump.final-message-stop-wait",
    "http3.native-body-pump.final-message-send-error",
    "http3.native-body-pump.send-stop-wait",
    "http3.native-body-pump.error-stop-wait",
    "http3.native-body-pump.cancel-before-first-poll",
    "http3.native-body-pump.sender-closed",
    "http3.legacy-path.selection",
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
    "http3.body-pump.final-message-send-error",
    "http3.body-pump.empty-data-frame",
    "http3.native-body-pump.empty-data-frame",
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
    "websocket.yawc.unexpected-continuation-frame",
    "websocket.yawc.invalid-text-frame",
    "websocket.yawc.invalid-close-reason",
    "websocket.yawc.close-reply-flush-error",
    "websocket.yawc.close-reply-flush-unexpected-frame",
    "websocket.driver.connection-closed",
    "websocket.peer-read-failed.wait-complete",
    "websocket.peer-read-failed.unavailable",
    "websocket.peer-read-failed.watch-fallback",
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
    {
        "http3.client.abort-after-body",
        "http3.client.peer-stop-before-response-headers",
        "http3.client.peer-stop-after-request-body-complete",
        "http3.client.peer-stop-while-upload-open",
        "http3.client.finish-upload-after-response",
        "public.http3-request-trailers",
    }
    | PUBLIC_INPUT_CONTRACT_POINTS
    | ASGI_SCOPE_SUPPORT_CONTRACT_POINTS
)
# These fault contracts exercise the legacy HTTP/3 server implementation,
# which is selected at process startup when its fault point is armed. Keep
# their target processes isolated so the input can arm the fault before the
# server chooses between the legacy and native HTTP/3 paths.
LEGACY_HTTP3_FAULT_POINTS = {
    "http3.request-task.panic",
    "http3.request-task.panic-after-response",
    "http3.connection.accept-finished",
    "http3.connection-task.panic",
    "http3.endpoint.accept-closed",
    "http3.connection-task.panic-during-shutdown",
    "http3.connection-task.shutdown-hang",
    "http3.connection.create-error",
    "http3.connection.accept-error",
    "http3.legacy-path.selection",
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
    "http3.body-pump.final-message-send-error",
    "http3.body-pump.empty-data-frame",
    "http3.body-pump.send-error",
    "http3.body-pump.send.connection-closed",
    "http3.body-pump.error.request-stop",
    "server.http3-task.shutdown-hang",
    "http.app-task.panic-before-response-start",
}
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
    "server-connection-invalid-default-header-source-chain",
    "server-default-header-finalization-error-closes-connection",
    "http2-response-event-fault-consumed-and-status-observed",
    "python-ssl-ca-verifier-error-propagates",
    "python-ssl-ca-verifier-success-fallback-propagates",
    "python-ssl-keyfile-error-propagates",
    "python-ssl-keyfile-rust-decrypt-error-propagates",
    "python-pkcs12-reader-error-propagates",
    "http3-request-trailers-drained-as-body-only",
    "http-response-reset-cancels-deferred-task",
    "server-cancellation-schedule-error-bounded-shutdown",
    "server-startup-cancellation-shutdown-error-propagates",
    "server-startup-bind-shutdown-error-logged",
    "http-500-then-followup-200",
    "http-response-build-error-closes-connection-followup-200",
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
    "http-body-pump-send-stopped-without-response",
    "http-body-pump-oversized-frame-echo",
    "http-body-pump-reaps-cancelled-task",
    "http-body-pump-shutdown-cancelled-join",
    "http-body-pump-shutdown-aborts-hung-pump",
    "http-body-pump-shutdown-completes-task-before-abort",
    "http-request-body-conversion-error-caught",
    "http-response-header-capacity-recovery-followup-200",
    "websocket-header-capacity-error-followup-200",
    "http-start-error-close-followup-200",
    "http-response-body-error-followup-200",
    "http-response-backpressure-body-preserved-followup-200",
    "http-incomplete-body-preserves-emitted-chunk-after-consumer-pause",
    "http-response-body-queued-after-receiver-pending",
    "http3-500-error-body",
    "http3-connection-task-error-followup-200",
    "http3-legacy-handshake-recovery",
    "http3-connection-error-cancels-held-response-followup-200",
    "http3-peer-close-classification-defensive-error",
    "http3-legacy-peer-close-no-error",
    "http3-legacy-peer-close-unknown-code-ignored",
    "http3-legacy-peer-close-classification-error",
    "http3-stream-reset-on-runtime-error",
    "http3-legacy-default-header-error-resets-stream",
    "http3-request-task-error-before-peer-close-followup-200",
    "http3-body-pump-early-exit-500",
    "http3-upload-body-pump-preserves-data",
    "http3-native-body-pump-pre-poll-cancel-preserves-response",
    "http3-native-body-pump-sender-closed-preserves-response",
    "http3-native-body-pump-send-stop-preserves-response",
    "http3-native-body-pump-final-message-stop-preserves-response",
    "http3-native-body-pump-final-message-send-error-preserves-response",
    "http3-upload-body-pump-send-error-disconnect",
    "http3-upload-body-pump-completes-final-message",
    "http3-connection-task-shutdown-error",
    "http3-legacy-connection-task-shutdown-completes",
    "http3-connection-task-shutdown-hang-aborted",
    "http3-endpoint-accept-closes-http3",
    "http2-500-generic-error-body",
    "http3-client-abort-disconnect-followup",
    "http3-peer-stop-cancels-held-app-followup-200",
    "http3-peer-stop-after-body-complete-disconnect-followup-200",
    "http3-peer-stop-open-upload-disconnect-followup-200",
    "http3-open-upload-app-return-retires-body-pump",
    "http3-peer-stop-cancelled-send-disconnect-followup-200",
    "http3-body-pump-error-stop-disconnect-followup-200",
    "http3-legacy-body-pump-delivers-disconnect-followup-200",
    "http3-body-pump-reaps-cancelled-task",
    "http3-server-shutdown-force-abort",
    "http-final-body-preserved-after-app-task-panic",
    "http-task-panic-before-final-body-closes-stream",
    "http-start-and-final-body-preserved-after-task-wins-select",
    "http-native-service-error-close-followup-200",
    "http-native-connection-write-error-followup-200",
    "http-concurrent-receive-after-lock-contention",
    "http-task-completion-error-followup-200",
    "http-start-response-preserved-followup-200",
    "http-disconnect-error-followup-200",
    "http-connection-lifetime-closed-disconnect-followup-200",
    "http-immediate-disconnect-message-error-followup-200",
    "server-startup-failure",
    "server-unix-listener-permission-error-startup-propagates",
    "server-lifespan-startup-auto-fallback",
    "server-lifespan-startup-auto-fallback-logger-failure-ignored",
    "server-shutdown-failure",
    "server-lifespan-task-cancel",
    "server-native-connection-error-during-shutdown",
    "websocket-server-shutdown-force-abort",
    "websocket-driver-send-error-followup-200",
    "websocket-driver-send-error-cancels-app",
    "websocket-registration-failure-cancels-app-followup-200",
    "websocket-handshake-error-followup-200",
    "websocket-teardown-and-followup-200",
}
PYTHON_SSL_CA_VERIFIER_FAULT_POINTS = {
    "python.ssl.ca-verifier.import",
    "python.ssl.ca-verifier.protocol",
    "python.ssl.ca-verifier.context",
    "python.ssl.ca-verifier.create-context",
    "python.ssl.ca-verifier.verify-mode",
    "python.ssl.ca-verifier.create-verify-mode",
    "python.ssl.ca-verifier.set-verify-mode",
}
PYTHON_SSL_CA_VERIFIER_RUST_PARSE_FAULT_POINT = (
    "python.ssl.ca-verifier.rust-parse-error"
)
PYTHON_SSL_KEYFILE_ERROR_FAULT_POINTS = {
    "python.ssl.keyfile-error.import",
    "python.ssl.keyfile-error.protocol",
    "python.ssl.keyfile-error.context",
    "python.ssl.keyfile-error.create-context",
}
PYTHON_SSL_KEYFILE_RUST_DECRYPT_FAULT_POINT = "python.ssl.keyfile.rust-decrypt-error"
PKCS12_PARSER_FAULT_POINTS = {
    "python.pkcs12.reader.outer-too-long",
    "python.pkcs12.reader.outer-sequence-decode",
    "python.pkcs12.reader.outer-finish",
    "python.pkcs12.reader.encrypted-info-too-long",
    "python.pkcs12.reader.algorithm-too-long",
    "python.pkcs12.reader.parameters-too-long",
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
    "websocket.yawc.unexpected-continuation-frame",
    "websocket.yawc.invalid-text-frame",
    "websocket.yawc.invalid-close-reason",
    "websocket.yawc.close-reply-flush-error",
    "websocket.yawc.close-reply-flush-unexpected-frame",
    "websocket.driver.connection-closed",
    "websocket.peer-read-failed.unavailable",
    "websocket.peer-read-failed.watch-fallback",
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
    "websocket.native-upgrade.missing",
    "websocket.native-upgrade.extension-removed-after-dispatch",
    "websocket.native-upgrade.register-closed",
    "websocket.accept-key.header-value-error",
    "websocket.peer-read-failed.wait-complete",
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
LIFESPAN_INFO_LOG_FAILURE_FAULT_POINTS = {
    "lifespan.log-info.import-logging",
    "lifespan.log-info.get-logger",
    "lifespan.log-info.call-get-logger",
    "lifespan.log-info.call-info",
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
    "http.response.start.trailers.get-item",
    "http.response.start.trailers.extract",
    "http.response.start.headers.get-item",
    "http.response.start.headers.extract",
    "http.response.start.channel-closed",
}
HTTP2_SCOPE_FAULT_POINTS = {
    "scope.http2.extensions.early-hint.set-item",
    "scope.http2.extensions.response-trailers.set-item",
    "scope.http2.extensions.set-item",
}


class ParityError(RuntimeError):
    """Invalid parity contract or failed adapter infrastructure."""


class ProcessResourceSampler:
    """Sample the live server process tree during a synchronized load case."""

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
            processes = [self.process, *self.process.children(recursive=True)]
        except psutil.Error as error:
            raise ParityError(f"could not enumerate server processes: {error}") from error
        rss_bytes = 0
        thread_count = 0
        root_sampled = False
        for process in processes:
            try:
                with process.oneshot():
                    rss_bytes += process.memory_info().rss
                    thread_count += process.num_threads()
                root_sampled |= process.pid == self.process.pid
            except psutil.NoSuchProcess:
                if process.pid == self.process.pid:
                    raise ParityError("server process exited during resource sampling")
                # A child can exit after children() returns and before its
                # sample; the next interval will observe the remaining tree.
                continue
            except psutil.Error as error:
                raise ParityError(f"could not sample server resources: {error}") from error
        if not root_sampled:
            raise ParityError("server process was absent from its resource sample")
        sample = (rss_bytes, thread_count)
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
            component_keys = {"id", "version"}
            if "platforms" in component:
                component_keys.add("platforms")
            exact_keys(component, component_keys, f"{oracle['id']} oracle component")
            if not isinstance(component["id"], str) or not component["id"] or component["id"] in component_ids:
                raise ParityError(f"{oracle['id']}: missing or duplicate component ID")
            if not isinstance(component["version"], str) or not component["version"]:
                raise ParityError(f"{oracle['id']}/{component['id']}: component version is required")
            if "platforms" in component:
                platforms = component["platforms"]
                if (
                    not isinstance(platforms, list)
                    or not platforms
                    or any(not isinstance(platform_id, str) for platform_id in platforms)
                    or len(platforms) != len(set(platforms))
                    or any(platform_id not in {"linux", "macos", "windows"} for platform_id in platforms)
                ):
                    raise ParityError(
                        f"{oracle['id']}/{component['id']}: platforms must be unique supported platform IDs"
                    )
            component_ids.add(component["id"])
    for profile in manifest["profiles"]:
        exact_keys(profile, {"id", "oracle", "protocol", "oracle_config"}, "manifest profile")
    if len({profile["id"] for profile in manifest["profiles"]}) != len(manifest["profiles"]):
        raise ParityError("duplicate profile ID")
    observation_fields = {
        "status", "content_type", "body_bytes", "ordered_body_bytes", "early_body_bytes",
        "early_hints", "early_hint_before_final_start", "response_trailers",
        "message_received",
        "ordered_response_headers", "response_header_values_by_name",
        "server_header_values", "date_header_present",
        "streamed_before_completion", "disconnect_event", "followup_response",
        "handshake_status", "handshake_established", "handshake_accept_valid", "frame_sent",
        "disconnect_code", "followup_status", "subprotocol", "ordered_messages", "state_response",
        "ordered_message_payload_bytes", "last_ordered_message",
        "process_terminated", "process_exit_code", "application_events", "close_code", "close_reason",
        "connection_closed", "listener_closed_before_release", "idle_connection_closed",
        "startup_failed", "startup_error_observed", "responses", "pong_received",
        "bind_error_logged",
        "first_server_ping_received", "first_server_ping_payload_length", "pong_sent",
        "unsolicited_pong_sent",
        "second_server_ping_received", "second_server_ping_payload_length",
        "second_pong_sent", "second_pong_payload_matches_ping",
        "timeout_close_received", "timeout_close_code", "timeout_close_reason",
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
        "body_stream_error", "trigger_error", "shutdown_clean",
        "exit_code", "stdout_base64", "stderr_base64",
        "response_received", "response_status", "response_content_type",
        "response_body_base64", "listener_responses", "shutdown_signal_sent", "shutdown_signals_sent", "process_timed_out",
        "raw_connection_open_after_timeout",
        "graceful_shutdown_cancellation_observed",
        "server_log_events", "worker_replacement_observed", "request_limit_response_count",
        "request_limit_range_satisfied",
        "server_started_before_shutdown", "serve_task_finished_before_shutdown",
        "server_started",
        "startup_failure_wait_result", "dropped_control_wait_result",
        "serve_raised", "serve_timed_out", "server_exit_code",
        "serve_exception_class", "serve_exception_message",
        "client_certificate_rejected", "negotiated_tls_version", "negotiated_tls_cipher",
        "process_stderr_has_unhandled_task_warning",
        "first_response_body_base64", "second_response_body_base64", "reload_observed",
        "process_stdout_base64", "process_stderr_base64",
        "workers_ignored_warning", "excluded_change_reloaded",
        "included_change_reloaded", "scope_observation", "compression_negotiated",
        "server_ping_observed",
        "lifespan_startup_entered_before_cancel", "server_started_before_cancel",
        "serve_cancelled", "serve_task_finished",
        "listener_accepting_after_cancel", "listener_transfer_blocked",
    }
    for operation in manifest["operations"]:
        expected_operation_keys = {"id", "kind", "observe"}
        if "compare" in operation:
            expected_operation_keys.add("compare")
        if "comparison_normalization" in operation:
            expected_operation_keys.add("comparison_normalization")
            normalizations = operation["comparison_normalization"]
            if not isinstance(normalizations, dict):
                raise ParityError(
                    f"{operation.get('id')}: comparison_normalization must be an object"
                )
            exact_keys(
                normalizations,
                {"stderr_base64"},
                f"{operation.get('id')}.comparison_normalization",
            )
            if (
                operation.get("id") != "cli.process"
                or normalizations["stderr_base64"]
                != "python-process-diagnostics"
            ):
                raise ParityError(
                    f"{operation.get('id')}: unsupported comparison normalization"
                )
        if "required_observations" in operation:
            expected_operation_keys.add("required_observations")
            if not set(operation["required_observations"]).issubset(observation_fields):
                raise ParityError(f"{operation.get('id')}: unknown required observation")
        if "target_requirements" in operation:
            expected_operation_keys.add("target_requirements")
            if (
                not isinstance(operation["target_requirements"], dict)
                or not set(operation["target_requirements"]).issubset(observation_fields)
            ):
                raise ParityError(f"{operation.get('id')}: unknown target requirement")
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
        if "comparison_normalization" in operation and not set(
            operation["comparison_normalization"]
        ).issubset(operation.get("compare", operation["observe"])):
            raise ParityError(
                f"{operation.get('id')}: normalized fields must be compared"
            )
        required = operation.get("required_observations", {})
        if not isinstance(required, dict) or not set(required).issubset(operation["observe"]):
            raise ParityError(f"{operation.get('id')}: required observations must be declared in observe")
        target_requirements = operation.get("target_requirements", {})
        if (
            not isinstance(target_requirements, dict)
            or not set(target_requirements).issubset(operation["observe"])
        ):
            raise ParityError(
                f"{operation.get('id')}: target requirements must be declared in observe"
            )

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
            elif fault["contract"] == "http3-request-trailers-drained-as-body-only":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.scope-and-body"
                    or fault["point"] != "public.http3-request-trailers"
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-request-trailers"
                    or not request.get("body_base64")
                    or not request.get("trailers")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 request-trailer conformance requires a body upload with trailing headers"
                    )
            elif fault["contract"] in {
                "http-500-then-followup-200", "http-callback-error-followup-200",
                "http-original-task-start-error-followup-200",
                "http-response-build-error-closes-connection-followup-200",
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
                    or fault["point"]
                    not in {
                        "http.app-task.panic-before-response-start",
                        "http3.native-app-task.panic-before-response-start",
                    }
                    or case.get("request", {}).get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 500-body contract requires a pre-response task failure on /state"
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
            elif fault["contract"] == "http3-legacy-handshake-recovery":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.handshake-recovery"
                    or fault["point"] != "http3.legacy-path.selection"
                    or case.get("request", {}).get("invalid_alpn") is not True
                ):
                    raise ParityError(
                        f"{case_id}: legacy HTTP/3 handshake recovery requires a rejected ALPN handshake and healthy follow-up"
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
                        "http3.connection-info.missing",
                        "http3.connection-lifetime.missing",
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
            elif fault["contract"] == "http3-legacy-default-header-error-resets-stream":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.injected-stream-error"
                    or fault["point"] != "http3.legacy-path.selection"
                    or case.get("server_options", {}).get("headers") != ["invalid name: value"]
                    or case.get("request", {}).get("path") != "/state"
                    or case.get("request", {}).get("expect_response_error") is not True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 legacy default-header failure requires the invalid-header stream-reset workflow"
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
            elif fault["contract"] == "http3-legacy-peer-close-no-error":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.peer-close"
                    or fault["point"] != "http3.legacy-path.selection"
                    or case.get("request", {}).get("close_error_code") != 256
                ):
                    raise ParityError(
                        f"{case_id}: legacy HTTP/3 no-error classification requires a real H3_NO_ERROR peer close"
                    )
            elif fault["contract"] == "http3-legacy-peer-close-unknown-code-ignored":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.peer-close"
                    or fault["point"] != "http3.legacy-path.selection"
                    or case.get("request", {}).get("close_error_code") != 515
                ):
                    raise ParityError(
                        f"{case_id}: legacy HTTP/3 unknown-code classification requires a real 0x203 peer close"
                    )
            elif fault["contract"] == "http3-legacy-peer-close-classification-error":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.peer-close-registered"
                    or fault["point"] != "http3.legacy-path.selection"
                    or case.get("request", {}).get("close_error_code") != 512
                ):
                    raise ParityError(
                        f"{case_id}: legacy HTTP/3 error classification requires a real QPACK_DECOMPRESSION_FAILED peer close"
                    )
            elif fault["contract"] == "http3-body-pump-early-exit-500":
                request = case.get("request", {})
                final_message_send_error = (
                    fault["point"] == "http3.body-pump.final-message-send-error"
                )
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.body-pump-early-exit"
                    or fault["point"] not in {
                        "http3.body-pump.send.connection-closed",
                        "http3.body-pump.connection-closed",
                        "http3.body-pump.connection-closed-select",
                        "http3.body-pump.sender-closed-select",
                        "http3.body-pump.final-message-send-error",
                    }
                    or request.get("path") not in {"/return-before-response-start", "/h3-upload-disconnect"}
                    or request.get("method") != "POST"
                    or (final_message_send_error and (
                        request.get("path") != "/h3-upload-disconnect"
                        or request.get("body_base64") != ""
                    ))
                    or (not final_message_send_error and not request.get("body_base64"))
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 body-pump early exits require a supported POST probe"
                    )
            elif fault["contract"] == "http3-legacy-body-pump-delivers-disconnect-followup-200":
                request = case.get("request", {})
                content_lengths = [
                    value for name, value in request.get("headers", [])
                    if name.lower() == "content-length"
                ]
                try:
                    body_length = len(
                        base64.b64decode(request.get("body_base64", ""), validate=True)
                    )
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid HTTP/3 disconnect body base64") from error
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.request-disconnect"
                    or fault["point"] != "http3.legacy-path.selection"
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-upload-disconnect"
                    or request.get("abort_after_body") is not True
                    or not request.get("body_base64")
                    or len(content_lengths) != 1
                    or not content_lengths[0].isdigit()
                    or int(content_lengths[0]) <= body_length
                ):
                    raise ParityError(
                        f"{case_id}: legacy HTTP/3 disconnect delivery requires a partial POST upload and peer reset"
                    )
            elif fault["contract"] == "http3-upload-body-pump-preserves-data":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.request-upload"
                    or fault["point"] not in {
                        "http3.body-pump.empty-data-frame",
                        "http3.native-body-pump.empty-data-frame",
                    }
                    or case.get("request", {}).get("path") != "/read-first-upload"
                    or case.get("request", {}).get("method") != "POST"
                    or not case.get("request", {}).get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 body-pump upload faults require a nonempty POST read probe"
                    )
            elif fault["contract"] == "http3-native-body-pump-pre-poll-cancel-preserves-response":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.application-status"
                    or fault["point"] != "http3.native-body-pump.cancel-before-first-poll"
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-early-response-open-upload"
                    or request.get("leave_upload_open_until_response") is not True
                    or not request.get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: native HTTP/3 pre-poll cancellation requires the open-upload early-response workflow"
                    )
            elif fault["contract"] == "http3-native-body-pump-sender-closed-preserves-response":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.application-status"
                    or fault["point"] != "http3.native-body-pump.sender-closed"
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-early-response-open-upload"
                    or request.get("leave_upload_open_until_response") is not True
                    or not request.get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: native HTTP/3 sender-close observation requires the open-upload early-response workflow"
                    )
            elif fault["contract"] == "http3-native-body-pump-send-stop-preserves-response":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.application-status"
                    or fault["point"] != "http3.native-body-pump.send-stop-wait"
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-early-response-open-upload"
                    or request.get("leave_upload_open_until_response") is not True
                    or not request.get("body_base64")
                ):
                    raise ParityError(
                        f"{case_id}: native HTTP/3 send-stop observation requires the open-upload early-response workflow"
                    )
            elif fault["contract"] == "http3-native-body-pump-final-message-stop-preserves-response":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.application-status"
                    or fault["point"] != "http3.native-body-pump.final-message-stop-wait"
                    or request.get("method") != "GET"
                    or request.get("path") != "/h3-early-response-open-upload"
                    or request.get("body_base64") != ""
                ):
                    raise ParityError(
                        f"{case_id}: final-message stop requires a bodyless GET response probe"
                    )
            elif fault["contract"] == (
                "http3-native-body-pump-final-message-send-error-preserves-response"
            ):
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http.application-status"
                    or fault["point"] != "http3.native-body-pump.final-message-send-error"
                    or request.get("method") != "GET"
                    or request.get("path") != "/h3-early-response-open-upload"
                    or request.get("body_base64") != ""
                ):
                    raise ParityError(
                        f"{case_id}: final-message send-error requires the bodyless GET probe"
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
            elif fault["contract"] == "http3-legacy-connection-task-shutdown-completes":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.connection-task-shutdown"
                    or fault["point"] != "http3.legacy-path.selection"
                    or case.get("request", {}).get("hold_open_for_shutdown") is not True
                ):
                    raise ParityError(
                        f"{case_id}: legacy HTTP/3 shutdown requires the held-connection workflow"
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
            elif fault["contract"] == "http2-500-generic-error-body":
                is_application_panic = (
                    fault["point"] == "http.app-task.panic-before-response-start"
                    and case.get("operation") == "http.application-error"
                )
                is_scope_construction_error = (
                    fault["point"] in HTTP2_SCOPE_FAULT_POINTS
                    and case.get("operation") == "http.application-status"
                )
                if (
                    case.get("profile") != "http2"
                    or not (is_application_panic or is_scope_construction_error)
                    or case.get("request", {}).get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/2 pre-response failures require a generic-error request to /state"
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
            elif fault["contract"] == "http3-peer-stop-cancels-held-app-followup-200":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.peer-stop-cancels-held-request"
                    or fault["point"] != "http3.client.peer-stop-before-response-headers"
                    or request.get("peer_stop_before_response_headers") is not True
                    or request.get("path") != "/hold"
                    or request.get("same_connection_followup_path") != "/sync-callable"
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 peer-stop contract requires the held-app and same-connection recovery workflow"
                    )
            elif fault["contract"] == "http3-peer-stop-open-upload-disconnect-followup-200":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.peer-stop-disconnects-open-request-body"
                    or fault["point"] != "http3.client.peer-stop-while-upload-open"
                    or request.get("peer_stop_while_upload_open") is not True
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-open-upload-peer-stop"
                    or request.get("same_connection_followup_path") != "/sync-callable"
                ):
                    raise ParityError(
                        f"{case_id}: open-upload peer-stop contract requires the partial-body and same-connection recovery workflow"
                    )
            elif fault["contract"] == "http3-open-upload-app-return-retires-body-pump":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.open-upload-retires-body-pump"
                    or fault["point"] != "http3.client.finish-upload-after-response"
                    or request.get("complete_upload_after_response") is not True
                    or request.get("method") != "POST"
                    or request.get("path") != "/h3-open-upload-app-return"
                    or request.get("same_connection_followup_path")
                    != "/h3-open-upload-followup"
                ):
                    raise ParityError(
                        f"{case_id}: app-return body-pump contract requires the partial upload and same-connection follow-up workflow"
                    )
            elif fault["contract"] == "http3-peer-stop-after-body-complete-disconnect-followup-200":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.disconnect-after-request-body-complete"
                    or fault["point"] != "http3.client.peer-stop-after-request-body-complete"
                    or request.get("peer_stop_after_body_complete") is not True
                    or request.get("path") != "/h3-disconnect-after-body"
                    or request.get("same_connection_followup_path") != "/sync-callable"
                ):
                    raise ParityError(
                        f"{case_id}: post-body peer-stop contract requires the complete-body and same-connection recovery workflow"
                    )
            elif fault["contract"] == "http3-peer-stop-cancelled-send-disconnect-followup-200":
                request = case.get("request", {})
                if (
                    case.get("profile") != "http3"
                    or case.get("operation")
                    != "http3.disconnect-after-request-body-complete-cancelled-send"
                    or fault["point"]
                    != "http3.native-body-pump.disconnect-send-stop-wait"
                    or request.get("peer_stop_after_body_complete") is not True
                    or request.get("path") != "/h3-disconnect-after-body"
                    or request.get("same_connection_followup_path") != "/sync-callable"
                ):
                    raise ParityError(
                        f"{case_id}: cancelled disconnect-send contract requires the post-body peer-stop and same-connection recovery workflow"
                    )
            elif fault["contract"] == "http3-body-pump-error-stop-disconnect-followup-200":
                if (
                    case.get("profile") != "http3"
                    or case.get("operation") != "http3.request-disconnect"
                    or fault["point"] not in {
                        "http3.body-pump.error.request-stop",
                        "http3.native-body-pump.stop-wait",
                        "http3.native-body-pump.error-stop-wait",
                    }
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
            elif fault["contract"] == "http-native-service-error-close-followup-200":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] not in {
                        "server.connection-task.service-error",
                        "server.connection-info.missing",
                        "server.connection-lifetime.missing",
                        "server.peer-read-half-closed.missing",
                        "server.peer-read-failed.missing",
                        "server.tcp-nodelay.set-error",
                    }
                    or "request_sequence" not in case
                    or len(case["request_sequence"]) != 2
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in case["request_sequence"][0].get("headers", [])
                    )
                ):
                    raise ParityError(
                        f"{case_id}: native service errors require a close-delimited request and HTTP follow-up"
                    )
            elif fault["contract"] == "http-native-connection-write-error-followup-200":
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.keepalive-sequence"
                    or fault["point"] != "server.connection-io.poll-write-error"
                    or "request_sequence" not in case
                    or len(case["request_sequence"]) != 2
                    or not any(
                        name.lower() == "connection" and value.lower() == "close"
                        for name, value in case["request_sequence"][0].get("headers", [])
                    )
                ):
                    raise ParityError(
                        f"{case_id}: native connection-write faults require a close-delimited request and HTTP follow-up"
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
            elif fault["contract"] == "http-request-body-conversion-error-caught":
                stream = case.get("request_stream", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] not in {
                        "http.request.body-segment.length-overflow",
                        "http.request.body-segment.out-of-bounds",
                    }
                    or stream.get("path") != "/request-body-error-probe"
                    or stream.get("send_all_before_read") is not True
                    or len(stream.get("chunks_base64", [])) < 2
                ):
                    raise ParityError(
                        f"{case_id}: request-body conversion errors require the segmented-body ASGI probe"
                    )
            elif fault["contract"] == "http-body-pump-error-stop-disconnect-followup-200":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] not in {
                        "http.body-pump.error.request-stop",
                        "http.body-pump.error.stop-wait",
                        "http.body-pump.error.buffered-send-connection-closed",
                        "http.body-pump.error.buffered-send-continues",
                    }
                    or disconnect.get("path") != "/disconnect-read-twice"
                    or disconnect.get("followup_path") != "/disconnect-status"
                    or not (
                        disconnect.get("malformed_chunk") is True
                        or (
                            fault["point"]
                            == "http.body-pump.error.buffered-send-connection-closed"
                            and disconnect.get("reset") is True
                        )
                    )
                    or disconnect.get("wait_event") != "http.disconnect.waiting"
                    or disconnect.get("wait_event_after_disconnect")
                    != "http.disconnect.second:http.disconnect"
                    or (
                        fault["point"] in {
                            "http.body-pump.error.buffered-send-connection-closed",
                            "http.body-pump.error.buffered-send-continues",
                        }
                        and not isinstance(disconnect.get("partial_body_base64"), str)
                    )
                    or (
                        fault["point"] in {
                            "http.body-pump.error.buffered-send-connection-closed",
                            "http.body-pump.error.buffered-send-continues",
                        }
                        and disconnect.get("reset") is True
                        and "content_length" not in disconnect
                    )
                    or (
                        fault["point"] == "http.body-pump.error.stop-wait"
                        and "partial_body_base64" in disconnect
                    )
                    or (
                        fault["point"] == "http.body-pump.error.request-stop"
                        and not isinstance(disconnect.get("partial_body_base64"), str)
                    )
                ):
                    raise ParityError(
                        f"{case_id}: malformed-body stop requires buffered body data, a synchronized ASGI disconnect, and follow-up"
                    )
            elif fault["contract"] == "http-body-pump-send-stopped-without-response":
                stream = case.get("request_stream", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] not in {
                        "http.body-pump.send.connection-closed",
                        "http.body-pump.batch-threshold.send-connection-closed",
                        "http.body-pump.oversized.send-connection-closed",
                    }
                    or stream.get("path") != "/upload-pump-disconnect"
                    or stream.get("followup_path") != "/state?coverage-fault=followup"
                    or not (
                        len(stream.get("chunks_base64", [])) >= 1
                        or len(stream.get("generated_chunks", [])) >= 1
                    )
                ):
                    raise ParityError(
                        f"{case_id}: body-pump send stop requires a streamed /upload-pump-disconnect request"
                    )
            elif fault["contract"] == "http-body-pump-oversized-frame-echo":
                stream = case.get("request_stream", {})
                generated_chunks = stream.get("generated_chunks", [])
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.request-streaming"
                    or fault["point"] != "http.body-pump.batch-limit.one-byte"
                    or stream.get("path") != "/upload-stream"
                    or stream.get("send_all_before_read") is not True
                    or len(generated_chunks) != 2
                    or any(chunk.get("size_bytes") != 2 for chunk in generated_chunks)
                ):
                    raise ParityError(
                        f"{case_id}: oversized-frame probe requires two small echoed frames under the injected one-byte limit"
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
                    or stream.get("path") != "/read-first-upload"
                    or stream.get("send_first_chunk_before_wait_event") is not True
                    or not stream.get("expected_response_body_base64")
                    or stream.get("wait_event") != "http.body-pump.app-response-finished"
                    or stream.get("send_remaining_after_response") is not True
                    or stream.get("keep_alive") is not True
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
            elif fault["contract"] == "http-connection-lifetime-closed-disconnect-followup-200":
                disconnect = case.get("disconnect", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.client-disconnect"
                    or fault["point"] not in {
                        "http.connection-lifetime.wait-complete",
                        "http.connection.peer-read-failed.wait-complete",
                    }
                    or disconnect.get("path") != "/disconnect-after-complete-request"
                    or disconnect.get("followup_path") != "/disconnect-status"
                    or disconnect.get("empty_request") is not True
                    or disconnect.get("wait_event")
                    != "http.disconnect.waiting-after-complete-request"
                    or disconnect.get("wait_event_after_disconnect")
                    != "http.disconnect.after-complete-request:http.disconnect"
                ):
                    raise ParityError(
                        f"{case_id}: connection-lifetime completion requires the synchronized complete-request disconnect workflow"
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
                        or fault["point"].startswith("server.prebound-transfer.")
                        or fault["point"] in {
                            "server.quic-tls.config-error",
                            "server.listener.accept-error",
                            "server.listener.local-addr-error",
                            "server.tcp-address-lookup.empty",
                            "server.tcp-socket.create-error",
                            "server.tcp-socket.reuseaddr-error",
                            "server.tcp-socket.bind-error",
                            "server.tcp-socket.listen-error",
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
            elif fault["contract"] == "server-lifespan-startup-auto-fallback-logger-failure-ignored":
                if (
                    case.get("profile") not in {
                        "lifespan-fault-receive-startup",
                        "lifespan-no-support-error",
                    }
                    or case.get("operation") != "lifespan.startup-auto-fallback"
                    or fault["point"] not in LIFESPAN_INFO_LOG_FAILURE_FAULT_POINTS
                    or case.get("startup_fallback", {}).get("followup_path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: logger failures require the startup auto-fallback follow-up workflow"
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
            elif fault["contract"] == "server-startup-cancellation-shutdown-error-propagates":
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation")
                    != "python.api.server-startup-cancel-shutdown-error"
                    or fault["point"] != "lifespan.shutdown.task-join-error"
                    or case.get("api", {}).get(
                        "server_startup_cancel_before_listener"
                    )
                    is not True
                ):
                    raise ParityError(
                        f"{case_id}: shutdown join fault requires startup cancellation before listener bind"
                    )
            elif fault["contract"] == "server-startup-bind-shutdown-error-logged":
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation")
                    != "python.api.server-startup-bind-shutdown-error-log"
                    or fault["point"] != "lifespan.shutdown.task-join-error"
                    or case.get("api", {}).get(
                        "server_startup_bind_failure_lifespan_cleanup"
                    )
                    is not True
                ):
                    raise ParityError(
                        f"{case_id}: shutdown join fault requires the listener-bind-failure workflow"
                    )
            elif fault["contract"] == "server-unix-listener-permission-error-startup-propagates":
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation")
                    != "python.api.server-startup-uds-socket-replacement-lifespan-cleanup"
                    or fault["point"] != "server.unix-listener.set-permissions-error"
                    or case.get("api", {}).get(
                        "server_startup_uds_socket_replacement_lifespan_cleanup"
                    )
                    is not True
                ):
                    raise ParityError(
                        f"{case_id}: Unix socket permission failures require the UDS startup and lifespan workflow"
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
            elif fault["contract"] == "server-native-connection-error-during-shutdown":
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
                        f"{case_id}: native connection write faults require a held response during graceful shutdown"
                    )
            elif fault["contract"] == "python-ssl-ca-verifier-error-propagates":
                run_http = case.get("api", {}).get("run_http", {})
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation") != "python.api.run-http"
                    or fault["point"] not in PYTHON_SSL_CA_VERIFIER_FAULT_POINTS
                    or run_http.get("invocation") != "config-server"
                    or run_http.get("tls") is not True
                    or run_http.get("ssl_ca_certs") != "malformed-ca"
                    or run_http.get("ssl_cert_reqs") != 2
                ):
                    raise ParityError(
                        f"{case_id}: Python SSL CA helper faults require malformed-CA Config/Server startup"
                    )
            elif fault["contract"] == "python-ssl-ca-verifier-success-fallback-propagates":
                run_http = case.get("api", {}).get("run_http", {})
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation") != "python.api.run-http"
                    or fault["point"]
                    != PYTHON_SSL_CA_VERIFIER_RUST_PARSE_FAULT_POINT
                    or run_http.get("invocation") != "config-server"
                    or run_http.get("tls") is not True
                    or run_http.get("ssl_ca_certs") != "generated-ca"
                    or run_http.get("ssl_cert_reqs") != 2
                ):
                    raise ParityError(
                        f"{case_id}: Rust CA parser faults require a generated-CA Config/Server startup case"
                    )
            elif fault["contract"] == "python-ssl-keyfile-error-propagates":
                run_http = case.get("api", {}).get("run_http", {})
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation") != "python.api.run-http"
                    or fault["point"] not in PYTHON_SSL_KEYFILE_ERROR_FAULT_POINTS
                    or run_http.get("invocation") != "config-server"
                    or run_http.get("tls") is not True
                    or run_http.get("ssl_keyfile_format")
                    != "pkcs12-pbe-sha1-3des-invalid-decrypted-key"
                    or not run_http.get("ssl_keyfile_password")
                    or run_http.get("ssl_cert_reqs") != 2
                ):
                    raise ParityError(
                        f"{case_id}: Python SSL keyfile helper faults require the invalid-decrypted-key Config/Server case"
                    )
            elif fault["contract"] == "python-ssl-keyfile-rust-decrypt-error-propagates":
                run_http = case.get("api", {}).get("run_http", {})
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation") != "python.api.run-http"
                    or fault["point"] != PYTHON_SSL_KEYFILE_RUST_DECRYPT_FAULT_POINT
                    or run_http.get("invocation") != "config-server"
                    or run_http.get("tls") is not True
                    or run_http.get("ssl_keyfile_format") != "traditional-rsa-des-ede3"
                    or not run_http.get("ssl_keyfile_password")
                    or run_http.get("ssl_cert_reqs") != 2
                ):
                    raise ParityError(
                        f"{case_id}: Rust keyfile decryption fault requires a valid encrypted RSA key"
                    )
            elif fault["contract"] == "python-pkcs12-reader-error-propagates":
                run_http = case.get("api", {}).get("run_http", {})
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation") != "python.api.run-http"
                    or fault["point"] not in PKCS12_PARSER_FAULT_POINTS
                    or run_http.get("invocation") != "config-server"
                    or run_http.get("tls") is not True
                    or run_http.get("ssl_keyfile_format") != "pkcs12-pbe-sha1-3des"
                    or not run_http.get("ssl_keyfile_password")
                ):
                    raise ParityError(
                        f"{case_id}: PKCS#12 reader faults require password-protected PKCS#12 Config/Server startup"
                    )
            elif fault["contract"] == "server-connection-invalid-default-header-source-chain":
                run_http = case.get("api", {}).get("run_http", {})
                if (
                    case.get("profile") != "python-api"
                    or case.get("operation") != "python.api.run-http"
                    or fault["point"]
                    != "server.connection.invalid-default-header.source-chain"
                    or run_http.get("invocation") != "api"
                    or run_http.get("headers") != [["Invalid Header", "value"]]
                ):
                    raise ParityError(
                        f"{case_id}: source-chain filtering requires an invalid default-header API request"
                    )
            elif fault["contract"] == "server-default-header-finalization-error-closes-connection":
                headers = case.get("server_options", {}).get("headers", [])
                request = case.get("request", {})
                if (
                    case.get("profile") != "http1"
                    or case.get("operation") != "http.invalid-response-header"
                    or fault["point"] != "server.default-header.response-finalization"
                    or len(headers) != 1
                    or not (
                        headers[0].startswith("Invalid Header:")
                        or (
                            headers[0].startswith("X-Invalid: bad")
                            and any(ord(character) < 32 for character in headers[0])
                        )
                    )
                    or request.get("method") != "GET"
                    or request.get("path") != "/state"
                ):
                    raise ParityError(
                        f"{case_id}: default-header finalization faults require one invalid configured header and a /state request"
                    )
            elif fault["contract"] == "http2-response-event-fault-consumed-and-status-observed":
                point = fault["point"]
                request = case.get("request", {})
                early_hint_fault = point in {
                    "http.response.early-hint.disconnected",
                    "http.response.early-hint.channel-closed",
                }
                trailer_fault = point in {
                    "http.response.trailers.disconnected",
                    "http.response.trailers.channel-closed",
                    "http.response.trailers.channel-full",
                    "http.response.trailers.full-send-closed",
                }
                has_trailer_negotiation = any(
                    name.lower() == "te" and value.lower() == "trailers"
                    for name, value in request.get("headers", [])
                )
                if (
                    case.get("profile") != "http2"
                    or case.get("operation") != "http.invalid-asgi-message-status"
                    or request.get("method") != "GET"
                    or request.get("body_base64") != ""
                    or not (
                        early_hint_fault
                        and request.get("path") == "/response-early-hints"
                        or trailer_fault
                        and request.get("path") == "/response-trailers"
                        and has_trailer_negotiation
                    )
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/2 response-event faults require their declared early-hint or negotiated-trailer route"
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
                websocket = case.get("websocket", {})
                server_options = case.get("server_options", {})
                if type(server_options) is not dict:
                    server_options = {}
                ping_interval = server_options.get("ws_ping_interval")
                ping_timeout = server_options.get("ws_ping_timeout")
                ping_send_error = (
                    fault["contract"] == "websocket-driver-send-error-followup-200"
                    and fault["point"] == "websocket.driver.send-error"
                    and websocket.get("path") == "/ws"
                    and websocket.get("messages") == []
                    and type(ping_interval) in {int, float}
                    and math.isfinite(ping_interval)
                    and ping_interval > 0
                    and type(ping_timeout) in {int, float}
                    and math.isfinite(ping_timeout)
                    and ping_timeout > 0
                )
                if (
                    case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.fault-contract"
                    or fault["point"] not in {
                        "websocket.driver.send-error",
                        "websocket.driver.drain-send-error",
                    }
                    or (
                        websocket.get("path") != expected_path
                        and not ping_send_error
                    )
                    or websocket.get("expect_close") is not True
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
            elif fault["contract"] == "websocket-registration-failure-cancels-app-followup-200":
                specification = case.get("websocket", {})
                if (
                    case.get("profile") != "websocket"
                    or case.get("operation") != "websocket.registration-failure-cleanup"
                    or fault["point"] != "websocket.native-upgrade.register-closed"
                    or specification.get("path") != "/ws-registration-failure-hold"
                    or specification.get("messages") != []
                    or specification.get("followup_path") != "/state"
                    or specification.get("wait_for_app_event")
                    != "websocket.registration-failure.cancelled"
                ):
                    raise ParityError(
                        f"{case_id}: native WebSocket registration failure requires the held-app cancellation and follow-up workflow"
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
                            "websocket.yawc.close-reply-flush-error",
                            "websocket.yawc.close-reply-flush-unexpected-frame",
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
        http_profile_ids = {
            "http1", "http1-header-policy", "http1-tls", "http2", "http3"
        }
        if kind == "cli" and "process" in case:
            exact_case_keys(case, {"case_id", "profile", "operation", "covers", "process"}, case_id)
            if case["operation"] != "cli.process":
                raise ParityError(f"{case_id}: CLI process input requires cli.process")
            process = case["process"]
            exact_keys(
                process,
                {"invocation", "arguments", "environment", "working_directory", "timeout_seconds"},
                f"{case_id}.process",
            )
            if process["invocation"] not in {"module", "console"}:
                raise ParityError(f"{case_id}: unsupported CLI invocation mode")
            arguments = process["arguments"]
            if (
                not isinstance(arguments, list)
                or any(not isinstance(argument, str) or "\x00" in argument for argument in arguments)
            ):
                raise ParityError(f"{case_id}: process arguments must be a list of NUL-free strings")
            environment = process["environment"]
            if not isinstance(environment, dict):
                raise ParityError(f"{case_id}: process environment must be an object")
            for name, value in environment.items():
                if (
                    not isinstance(name, str)
                    or not name
                    or "=" in name
                    or "\x00" in name
                    or (value is not None and (not isinstance(value, str) or "\x00" in value))
                ):
                    raise ParityError(f"{case_id}: process environment entries must be valid strings or null")
            if process["working_directory"] not in {"project", "temporary"}:
                raise ParityError(f"{case_id}: unsupported process working directory")
            timeout_seconds = process["timeout_seconds"]
            if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
                raise ParityError(f"{case_id}: process timeout must be between 1 and 60 seconds")
        elif kind == "python-api" and "api" in case:
            python_api_case_keys = {
                "case_id", "profile", "operation", "covers", "api"
            }
            if "required_observations" in case:
                python_api_case_keys.add("required_observations")
            if case.get("verification") == "fault-contract":
                python_api_case_keys.update({"verification", "fault"})
            exact_case_keys(case, python_api_case_keys, case_id)
            if "required_observations" in case:
                required_observations = case["required_observations"]
                observed_fields = operations[case["operation"]]["observe"]
                if (
                    type(required_observations) is not dict
                    or not set(required_observations).issubset(observed_fields)
                ):
                    raise ParityError(
                        f"{case_id}.required_observations must use declared observation fields"
                    )
            if case.get("verification") == "fault-contract":
                fault = case["fault"]
                run_http = case.get("api", {}).get("run_http", {})
                helper_error_case = (
                    fault["contract"] == "python-ssl-ca-verifier-error-propagates"
                    and fault["point"] in PYTHON_SSL_CA_VERIFIER_FAULT_POINTS
                    and run_http.get("ssl_ca_certs") == "malformed-ca"
                )
                fallback_error_case = (
                    fault["contract"]
                    == "python-ssl-ca-verifier-success-fallback-propagates"
                    and fault["point"]
                    == PYTHON_SSL_CA_VERIFIER_RUST_PARSE_FAULT_POINT
                    and run_http.get("ssl_ca_certs") == "generated-ca"
                )
                pkcs12_parser_error_case = (
                    fault["contract"] == "python-pkcs12-reader-error-propagates"
                    and fault["point"] in PKCS12_PARSER_FAULT_POINTS
                    and run_http.get("ssl_keyfile_format") == "pkcs12-pbe-sha1-3des"
                )
                keyfile_error_case = (
                    fault["contract"] == "python-ssl-keyfile-error-propagates"
                    and fault["point"] in PYTHON_SSL_KEYFILE_ERROR_FAULT_POINTS
                    and run_http.get("ssl_keyfile_format")
                    == "pkcs12-pbe-sha1-3des-invalid-decrypted-key"
                )
                keyfile_rust_decrypt_error_case = (
                    fault["contract"] == "python-ssl-keyfile-rust-decrypt-error-propagates"
                    and fault["point"] == PYTHON_SSL_KEYFILE_RUST_DECRYPT_FAULT_POINT
                    and run_http.get("ssl_keyfile_format") == "traditional-rsa-des-ede3"
                )
                default_header_source_chain_case = (
                    fault["contract"]
                    == "server-connection-invalid-default-header-source-chain"
                    and fault["point"]
                    == "server.connection.invalid-default-header.source-chain"
                    and run_http.get("headers") == [["Invalid Header", "value"]]
                )
                startup_shutdown_error_case = (
                    fault["contract"]
                    == "server-startup-cancellation-shutdown-error-propagates"
                    and fault["point"] == "lifespan.shutdown.task-join-error"
                    and case["operation"]
                    == "python.api.server-startup-cancel-shutdown-error"
                    and case.get("api", {}).get(
                        "server_startup_cancel_before_listener"
                    )
                    is True
                )
                startup_bind_shutdown_error_case = (
                    fault["contract"] == "server-startup-bind-shutdown-error-logged"
                    and fault["point"] == "lifespan.shutdown.task-join-error"
                    and case["operation"]
                    == "python.api.server-startup-bind-shutdown-error-log"
                    and case.get("api", {}).get(
                        "server_startup_bind_failure_lifespan_cleanup"
                    )
                    is True
                )
                uds_permission_error_case = (
                    fault["contract"]
                    == "server-unix-listener-permission-error-startup-propagates"
                    and fault["point"] == "server.unix-listener.set-permissions-error"
                    and case["operation"]
                    == "python.api.server-startup-uds-socket-replacement-lifespan-cleanup"
                    and case.get("api", {}).get(
                        "server_startup_uds_socket_replacement_lifespan_cleanup"
                    )
                    is True
                )
                if (
                    not startup_shutdown_error_case
                    and not startup_bind_shutdown_error_case
                    and not uds_permission_error_case
                    and (
                        case["operation"] != "python.api.run-http"
                        or not (
                            helper_error_case
                            or fallback_error_case
                            or keyfile_error_case
                            or keyfile_rust_decrypt_error_case
                            or default_header_source_chain_case
                            or pkcs12_parser_error_case
                        )
                        or (
                            not (
                                default_header_source_chain_case
                                or pkcs12_parser_error_case
                            )
                            and (
                                run_http.get("invocation") != "config-server"
                                or run_http.get("tls") is not True
                                or run_http.get("ssl_cert_reqs") != 2
                            )
                        )
                    )
                ):
                    raise ParityError(
                        f"{case_id}: Python adapter fault requires its declared public workflow"
                    )
            readiness_operations = {
                "python.api.server-readiness": "server_readiness",
                "python.api.server-callback-notify": "server_callback_notify",
                "python.api.server-startup-failure-state": "server_startup_failure",
                "python.api.server-startup-bind-failure-lifespan-cleanup": "server_startup_bind_failure_lifespan_cleanup",
                "python.api.server-startup-uds-socket-replacement-lifespan-cleanup": "server_startup_uds_socket_replacement_lifespan_cleanup",
                "python.api.server-startup-failure-waiter": "server_startup_failure_waiter",
                "python.api.server-startup-cancel-before-listener": "server_startup_cancel_before_listener",
                "python.api.server-startup-cancel-shutdown-error": "server_startup_cancel_before_listener",
                "python.api.server-startup-cancel-without-lifespan": "server_startup_cancel_without_lifespan",
                "python.api.server-startup-cancel-during-prebound-transfer": "server_startup_cancel_during_prebound_transfer",
                "python.api.server-startup-cancel-during-prebound-transfer-without-lifespan": "server_startup_cancel_during_prebound_transfer_without_lifespan",
                "python.api.server-startup-bind-shutdown-error-log": "server_startup_bind_failure_lifespan_cleanup",
            }
            if case["operation"] in {
                "python.api.run-http-reload",
                "python.api.run-http-reload-filters",
            }:
                exact_keys(case["api"], {"run_http_reload"}, f"{case_id}.api")
                reload_request = case["api"]["run_http_reload"]
                reload_request_keys = {"timeout_seconds", "reload_delay", "workers"}
                if case["operation"] == "python.api.run-http-reload-filters":
                    reload_request_keys.update({"reload_include", "reload_exclude"})
                    if "environment" in reload_request:
                        reload_request_keys.add("environment")
                exact_keys(
                    reload_request,
                    reload_request_keys,
                    f"{case_id}.api.run_http_reload",
                )
                timeout_seconds = reload_request["timeout_seconds"]
                reload_delay = reload_request["reload_delay"]
                workers = reload_request["workers"]
                if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 60:
                    raise ParityError(
                        f"{case_id}.api.run_http_reload.timeout_seconds must be from 5 through 60"
                    )
                if (
                    isinstance(reload_delay, bool)
                    or not isinstance(reload_delay, (int, float))
                    or not 0 < reload_delay <= 2
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http_reload.reload_delay must be greater than 0 and at most 2 seconds"
                    )
                if type(workers) is not int or not 1 <= workers <= 16:
                    raise ParityError(
                        f"{case_id}.api.run_http_reload.workers must be from 1 through 16"
                    )
                if case["operation"] == "python.api.run-http-reload-filters":
                    environment = reload_request.get("environment", {})
                    if not isinstance(environment, dict):
                        raise ParityError(
                            f"{case_id}.api.run_http_reload.environment must be an object"
                        )
                    allowed_environment = {
                        "UVICORN_RELOAD_INCLUDES",
                        "UVICORN_RELOAD_EXCLUDES",
                    }
                    if set(environment) - allowed_environment or any(
                        not isinstance(value, str) or "\x00" in value
                        for value in environment.values()
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http_reload.environment supports only string reload include/exclude values"
                        )
                    for field in ("reload_include", "reload_exclude"):
                        patterns = reload_request[field]
                        environment_name = {
                            "reload_include": "UVICORN_RELOAD_INCLUDES",
                            "reload_exclude": "UVICORN_RELOAD_EXCLUDES",
                        }[field]
                        if (
                            not isinstance(patterns, list)
                            or len(patterns) > 16
                            or (not patterns and environment_name not in environment)
                            or any(
                                not isinstance(pattern, str)
                                or not pattern
                                or len(pattern) > 512
                                or "\x00" in pattern
                                for pattern in patterns
                            )
                        ):
                            raise ParityError(
                                f"{case_id}.api.run_http_reload.{field} must be a non-empty array of bounded glob strings"
                            )
            elif case["operation"] in {
                "python.api.run-http",
                "python.api.run-http-incomplete-header",
                "python.api.run-http-signal-sequence",
                "python.api.run-http-graceful-timeout",
                "python.api.run-http-request-limit",
                "python.api.run-http-asgi-scope-contract",
                "python.api.run-http-concurrency",
                "python.api.run-http-bind-conflict",
                "python.api.run-http-uds-bind-conflict",
            }:
                exact_keys(case["api"], {"run_http"}, f"{case_id}.api")
                run_http = case["api"]["run_http"]
                optional_run_http_keys = {
                    "headers",
                    "observe_headers",
                    "interface",
                    "application_interface",
                    "environment",
                    "request_headers",
                    "request_body_base64",
                    "request_body_chunks_base64",
                    "http_version",
                    "http_backend",
                    "observe_scope",
                    "proxy_headers",
                    "forwarded_allow_ips",
                    "limit_concurrency",
                    "loop",
                    "observe_loop",
                    "log_level",
                    "log_config",
                    "emit_level_logs",
                    "access_log",
                    "server_header",
                    "date_header",
                    "use_colors",
                    "factory",
                    "callable_instance",
                    "implicit_factory",
                    "backlog",
                    "timeout_keep_alive",
                    "timeout_graceful_shutdown",
                    "root_path_from_environment",
                    "host_from_environment",
                    "port_from_environment",
                    "keep_alive_probe_delay_seconds",
                    "workers",
                    "timeout_worker_healthcheck",
                    "uds",
                    "tls",
                    "ssl_keyfile_password",
                    "ssl_keyfile_format",
                    "ssl_ca_certs",
                    "ssl_cert_reqs",
                    "ssl_version",
                    "client_tls",
                    "observe_unix_scope",
                    "host",
                    "fd",
                    "prebound_socket_count",
                    "client_timeout_seconds",
                    "h11_max_incomplete_event_size",
                    "incomplete_request_buffer_length",
                    "post_response_settle_seconds",
                    "reset_contextvars",
                    "bind_conflict",
                    "required_observations",
                    "shutdown_signal_sequence",
                } & set(run_http)
                exact_keys(
                    run_http,
                    {
                        "method",
                        "path",
                        "shutdown_signal",
                        "timeout_seconds",
                        "lifespan",
                        "invocation",
                        "root_path",
                    } | optional_run_http_keys,
                    f"{case_id}.api.run_http",
                )
                if "required_observations" in run_http:
                    required = run_http["required_observations"]
                    allowed_required = {
                        "response_received",
                        "response_status",
                        "shutdown_signal_sent",
                        "shutdown_signals_sent",
                        "process_exit_code",
                        "process_timed_out",
                        "worker_replacement_observed",
                        "raw_connection_open_after_timeout",
                    }
                    if type(required) is not dict or not set(required).issubset(
                        allowed_required
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.required_observations has unsupported fields"
                        )
                    for field in (
                        "response_received",
                        "shutdown_signal_sent",
                        "process_timed_out",
                        "worker_replacement_observed",
                        "raw_connection_open_after_timeout",
                    ):
                        if field in required and type(required[field]) is not bool:
                            raise ParityError(
                                f"{case_id}.api.run_http.required_observations.{field} must be a boolean"
                            )
                    if "shutdown_signals_sent" in required and (
                        not isinstance(required["shutdown_signals_sent"], list)
                        or not required["shutdown_signals_sent"]
                        or any(
                            not isinstance(signal_name, str)
                            or signal_name not in {"SIGINT", "SIGTERM"}
                            for signal_name in required["shutdown_signals_sent"]
                        )
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.required_observations.shutdown_signals_sent must be a signal-name array"
                        )
                    if "response_status" in required and (
                        required["response_status"] is not None
                        and type(required["response_status"]) is not int
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.required_observations.response_status must be an integer or null"
                        )
                    if "process_exit_code" in required and (
                        required["process_exit_code"] is not None
                        and type(required["process_exit_code"]) is not int
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.required_observations.process_exit_code must be an integer or null"
                        )
                if run_http["invocation"] not in {
                    "api",
                    "module-cli",
                    "config-server",
                    "server-sockets",
                }:
                    raise ParityError(
                        f"{case_id}.api.run_http.invocation must be api, module-cli, config-server, or server-sockets"
                    )
                if "http_backend" in run_http:
                    if type(run_http["http_backend"]) is not str or run_http[
                        "http_backend"
                    ] not in {"auto", "h11", "httptools", "zttp"}:
                        raise ParityError(
                            f"{case_id}.api.run_http.http_backend must be auto, h11, httptools, or zttp"
                        )
                    if run_http["invocation"] != "module-cli":
                        raise ParityError(
                            f"{case_id}.api.run_http.http_backend requires module-cli invocation"
                        )
                h11_max_incomplete_event_size = run_http.get(
                    "h11_max_incomplete_event_size"
                )
                if h11_max_incomplete_event_size is not None and (
                    type(h11_max_incomplete_event_size) is not int
                    or not 1 <= h11_max_incomplete_event_size <= 65536
                    or run_http["invocation"] != "module-cli"
                    or run_http.get("http_backend") != "h11"
                ):
                    raise ParityError(
                        f"{case_id}: h11_max_incomplete_event_size requires a bounded integer and module-cli h11"
                    )
                incomplete_request_buffer_length = run_http.get(
                    "incomplete_request_buffer_length"
                )
                if incomplete_request_buffer_length is not None and (
                    type(incomplete_request_buffer_length) is not int
                    or not 64 <= incomplete_request_buffer_length <= 65536
                    or case["operation"]
                    != "python.api.run-http-incomplete-header"
                    or h11_max_incomplete_event_size is None
                    or incomplete_request_buffer_length
                    not in {
                        h11_max_incomplete_event_size,
                        h11_max_incomplete_event_size + 1,
                    }
                ):
                    raise ParityError(
                        f"{case_id}: incomplete request buffer length must equal the h11 maximum or one byte over"
                    )
                if case["operation"] == "python.api.run-http-incomplete-header" and (
                    incomplete_request_buffer_length is None
                    or h11_max_incomplete_event_size is None
                    or run_http["invocation"] != "module-cli"
                    or run_http.get("http_backend") != "h11"
                ):
                    raise ParityError(
                        f"{case_id}: h11 incomplete-header operation requires the module CLI and both size fields"
                    )
                if "factory" in run_http and type(run_http["factory"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.factory must be a boolean"
                    )
                if "callable_instance" in run_http and type(
                    run_http["callable_instance"]
                ) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.callable_instance must be a boolean"
                    )
                if "implicit_factory" in run_http and type(
                    run_http["implicit_factory"]
                ) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.implicit_factory must be a boolean"
                    )
                if run_http.get("callable_instance") and (
                    run_http.get("factory", False)
                    or run_http.get("application_interface", "asgi3") != "asgi3"
                    or run_http["invocation"] not in {"api", "module-cli"}
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.callable_instance requires an ASGI3 api or module-cli input without factory mode"
                    )
                if run_http.get("implicit_factory") and (
                    run_http.get("factory", False)
                    or run_http.get("callable_instance", False)
                    or run_http.get("application_interface", "asgi3") != "asgi3"
                    or run_http["invocation"] not in {"api", "module-cli"}
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.implicit_factory requires an ASGI3 api or module-cli input without explicit factory mode"
                    )
                if "reset_contextvars" in run_http and type(
                    run_http["reset_contextvars"]
                ) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.reset_contextvars must be a boolean"
                    )
                if "uds" in run_http and type(run_http["uds"]) is not bool:
                    raise ParityError(f"{case_id}.api.run_http.uds must be a boolean")
                if "tls" in run_http and type(run_http["tls"]) is not bool:
                    raise ParityError(f"{case_id}.api.run_http.tls must be a boolean")
                if "ssl_keyfile_password" in run_http and (
                    not isinstance(run_http["ssl_keyfile_password"], str)
                    or not run_http["ssl_keyfile_password"]
                    or not run_http.get("tls")
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.ssl_keyfile_password must be a non-empty string and requires tls=true"
                    )
                if "ssl_keyfile_format" in run_http and (
                    run_http["ssl_keyfile_format"] not in {
                        "unencrypted-rsa-with-password",
                        "pkcs12-pbe-sha1-2des",
                        "pkcs12-pbe-sha1-3des",
                        "pkcs12-pbe-sha1-3des-zero-iterations",
                        "pkcs12-pbe-sha1-3des-short-ciphertext",
                        "pkcs12-pbe-sha1-3des-invalid-decrypted-key",
                        "pkcs12-pbe-sha1-3des-malformed-outer-sequence",
                        "pkcs12-pbe-sha1-3des-trailing-outer-data",
                        "pkcs12-pbe-sha1-3des-missing-algorithm",
                        "pkcs12-pbe-sha1-3des-invalid-encrypted-data-type",
                        "pkcs12-pbe-sha1-3des-trailing-encrypted-info-field",
                        "pkcs12-pbe-sha1-3des-invalid-algorithm-oid-type",
                        "pkcs12-pbe-sha1-3des-missing-parameters",
                        "pkcs12-pbe-sha1-3des-trailing-algorithm-field",
                        "pkcs12-pbe-sha1-3des-invalid-salt-type",
                        "pkcs12-pbe-sha1-3des-missing-iterations",
                        "pkcs12-pbe-sha1-3des-trailing-parameters-field",
                        "traditional-rsa-aes128",
                        "traditional-rsa-aes192",
                        "traditional-rsa-aes256",
                        "traditional-rsa-des-ede3",
                        "traditional-ec-aes256",
                        "traditional-rsa-aes256-invalid-proc-type",
                        "traditional-rsa-aes256-unknown-header",
                        "traditional-rsa-aes256-missing-proc-type",
                        "traditional-rsa-aes256-missing-dek-info",
                        "traditional-rsa-aes256-malformed-dek-info",
                        "traditional-rsa-aes256-short-iv",
                        "traditional-rsa-aes256-missing-body",
                        "traditional-rsa-aes256-missing-end-marker",
                        "traditional-rsa-aes256-invalid-base64",
                        "traditional-rsa-aes256-empty-body",
                        "traditional-rsa-aes256-short-ciphertext",
                        "traditional-rsa-unsupported-cipher",
                        "traditional-rsa-malformed-begin-line",
                        "traditional-rsa-empty-key",
                        "traditional-rsa-invalid-utf8",
                        "traditional-dsa-encrypted",
                        "traditional-rsa-malformed-begin-suffix",
                        "traditional-rsa-aes256-high-nonhex-iv",
                        "traditional-rsa-aes256-odd-iv",
                        "traditional-rsa-aes256-nonhex-iv",
                    }
                    or not run_http.get("tls")
                    or not run_http.get("ssl_keyfile_password")
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.ssl_keyfile_format must select a supported key fixture and requires tls=true with a password"
                    )
                if "ssl_ca_certs" in run_http and (
                    run_http["ssl_ca_certs"]
                    not in {
                        "generated-ca",
                        "trusted-ca",
                        "empty-ca",
                        "missing-ca",
                        "directory-ca",
                        "malformed-ca",
                        "invalid-der-ca",
                        "non-utf8-ca",
                        "",
                    }
                    or not run_http.get("tls")
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.ssl_ca_certs must select generated-ca, trusted-ca, empty-ca, missing-ca, directory-ca, malformed-ca, invalid-der-ca, non-utf8-ca, or an empty path and requires tls=true"
                    )
                if "ssl_cert_reqs" in run_http and (
                    type(run_http["ssl_cert_reqs"]) is not int
                    or not run_http.get("tls")
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.ssl_cert_reqs must be an integer and requires tls=true"
                    )
                if "ssl_version" in run_http and (
                    type(run_http["ssl_version"]) is not int
                    or run_http["ssl_version"] != ssl.PROTOCOL_TLSv1_2
                    or not run_http.get("tls")
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.ssl_version must select TLS 1.2 and requires tls=true"
                    )
                if "client_tls" in run_http and type(run_http["client_tls"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.client_tls must be a boolean"
                    )
                if run_http.get("client_tls") and (
                    not run_http.get("tls")
                    or run_http.get("ssl_cert_reqs") not in {1, 2}
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.client_tls requires TLS and ssl_cert_reqs 1 or 2"
                    )
                if "host" in run_http and (
                    not isinstance(run_http["host"], str)
                    or not run_http["host"]
                    or "\x00" in run_http["host"]
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.host must be a non-empty NUL-free string"
                    )
                if "fd" in run_http and type(run_http["fd"]) is not bool:
                    raise ParityError(f"{case_id}.api.run_http.fd must be a boolean")
                if "bind_conflict" in run_http and type(run_http["bind_conflict"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.bind_conflict must be a boolean"
                    )
                if case["operation"] == "python.api.run-http-bind-conflict" and (
                    run_http.get("bind_conflict") is not True
                    or run_http["invocation"] != "api"
                    or run_http.get("host", "127.0.0.1") != "127.0.0.1"
                    or run_http.get("uds")
                    or run_http.get("fd")
                    or run_http.get("tls")
                ):
                    raise ParityError(
                        f"{case_id}: bind-conflict requires the public API, an occupied IPv4 loopback port, and no inherited or TLS listener"
                    )
                if case["operation"] == "python.api.run-http-uds-bind-conflict" and (
                    run_http.get("bind_conflict") is not True
                    or run_http["invocation"] != "api"
                    or run_http.get("uds") is not True
                    or run_http.get("fd")
                    or run_http.get("tls")
                ):
                    raise ParityError(
                        f"{case_id}: Unix bind-conflict requires the public API, an occupied Unix socket path, and no inherited or TLS listener"
                    )
                if "prebound_socket_count" in run_http:
                    count = run_http["prebound_socket_count"]
                    if type(count) is not int or not 1 <= count <= 8:
                        raise ParityError(
                            f"{case_id}.api.run_http.prebound_socket_count must be an integer from 1 to 8"
                        )
                    if not run_http.get("fd") or run_http["invocation"] != "server-sockets":
                        raise ParityError(
                            f"{case_id}.api.run_http.prebound_socket_count requires fd=true and the server-sockets invocation"
                        )
                if run_http.get("fd") and run_http.get("uds"):
                    raise ParityError(f"{case_id}.api.run_http cannot combine fd and uds")
                if run_http["invocation"] == "server-sockets" and not run_http.get("fd"):
                    raise ParityError(
                        f"{case_id}.api.run_http server-sockets invocation requires fd=true"
                    )
                if (
                    "observe_unix_scope" in run_http
                    and type(run_http["observe_unix_scope"]) is not bool
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.observe_unix_scope must be a boolean"
                    )
                if run_http.get("observe_unix_scope") and not run_http.get("uds"):
                    raise ParityError(
                        f"{case_id}.api.run_http.observe_unix_scope requires uds=true"
                    )
                if "backlog" in run_http and type(run_http["backlog"]) is not int:
                    raise ParityError(
                        f"{case_id}.api.run_http.backlog must be an integer"
                    )
                if "timeout_keep_alive" in run_http and type(run_http["timeout_keep_alive"]) is not int:
                    raise ParityError(
                        f"{case_id}.api.run_http.timeout_keep_alive must be an integer"
                    )
                if "timeout_graceful_shutdown" in run_http and type(
                    run_http["timeout_graceful_shutdown"]
                ) is not int:
                    raise ParityError(
                        f"{case_id}.api.run_http.timeout_graceful_shutdown must be an integer"
                    )
                if (
                    "timeout_graceful_shutdown" in run_http
                    and run_http["invocation"] != "module-cli"
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.timeout_graceful_shutdown currently requires module-cli invocation"
                    )
                if "workers" in run_http and type(run_http["workers"]) is not int:
                    raise ParityError(f"{case_id}.api.run_http.workers must be an integer")
                if "timeout_worker_healthcheck" in run_http and type(
                    run_http["timeout_worker_healthcheck"]
                ) is not int:
                    raise ParityError(
                        f"{case_id}.api.run_http.timeout_worker_healthcheck must be an integer"
                    )
                keep_alive_timeout_present = "timeout_keep_alive" in run_http
                keep_alive_probe_present = "keep_alive_probe_delay_seconds" in run_http
                if keep_alive_timeout_present != keep_alive_probe_present:
                    raise ParityError(
                        f"{case_id}: timeout_keep_alive and keep_alive_probe_delay_seconds must be provided together"
                    )
                if keep_alive_probe_present:
                    probe_delay = run_http["keep_alive_probe_delay_seconds"]
                    if type(probe_delay) is not int or not 1 <= probe_delay <= 5:
                        raise ParityError(
                            f"{case_id}.api.run_http.keep_alive_probe_delay_seconds must be from 1 through 5"
                        )
                    if probe_delay <= max(0, run_http["timeout_keep_alive"]):
                        raise ParityError(
                            f"{case_id}: the second request must arrive after the configured keep-alive timeout"
                        )
                    if run_http["timeout_seconds"] <= probe_delay + 1:
                        raise ParityError(
                            f"{case_id}: timeout_seconds must leave time for the second-request probe and shutdown"
                        )
                if run_http.get("interface", "auto") not in {"auto", "asgi2", "asgi3", "wsgi"}:
                    raise ParityError(
                        f"{case_id}.api.run_http.interface must be auto, asgi2, asgi3, or wsgi"
                    )
                if run_http.get("application_interface", "asgi3") not in {"asgi2", "asgi3", "wsgi"}:
                    raise ParityError(
                        f"{case_id}.api.run_http.application_interface must be asgi2, asgi3, or wsgi"
                    )
                if not isinstance(run_http["method"], str) or run_http["method"] not in {
                    "GET",
                    "POST",
                }:
                    raise ParityError(f"{case_id}: run_http supports GET and WSGI POST requests")
                if run_http["method"] == "POST":
                    if run_http.get("application_interface") != "wsgi":
                        raise ParityError(
                            f"{case_id}: run_http POST currently requires the WSGI probe app"
                        )
                    has_single_body = "request_body_base64" in run_http
                    has_chunked_body = "request_body_chunks_base64" in run_http
                    if has_single_body == has_chunked_body:
                        raise ParityError(
                            f"{case_id}: POST requires exactly one of request_body_base64 or request_body_chunks_base64"
                        )
                    if has_single_body:
                        encoded_body = run_http["request_body_base64"]
                        if not isinstance(encoded_body, str) or not encoded_body:
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_base64 must be a non-empty base64 string"
                            )
                        try:
                            decoded_body = base64.b64decode(encoded_body, validate=True)
                        except (ValueError, TypeError) as error:
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_base64 must be valid base64"
                            ) from error
                        if not decoded_body or len(decoded_body) > 1024 * 1024:
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_base64 must encode 1 byte through 1 MiB"
                            )
                    else:
                        encoded_chunks = run_http["request_body_chunks_base64"]
                        if (
                            not isinstance(encoded_chunks, list)
                            or not 2 <= len(encoded_chunks) <= 64
                            or any(not isinstance(chunk, str) or not chunk for chunk in encoded_chunks)
                        ):
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_chunks_base64 must contain 2 through 64 non-empty base64 chunks"
                            )
                        try:
                            decoded_chunks = [
                                base64.b64decode(chunk, validate=True)
                                for chunk in encoded_chunks
                            ]
                        except (ValueError, TypeError) as error:
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_chunks_base64 must contain valid base64"
                            ) from error
                        if any(not chunk for chunk in decoded_chunks):
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_chunks_base64 must encode non-empty chunks"
                            )
                        if sum(map(len, decoded_chunks)) > 1024 * 1024:
                            raise ParityError(
                                f"{case_id}.api.run_http.request_body_chunks_base64 must encode at most 1 MiB total"
                            )
                        headers = run_http.get("request_headers", [])
                        has_chunked_transfer_encoding = any(
                            isinstance(header, list)
                            and len(header) == 2
                            and isinstance(header[0], str)
                            and header[0].lower() == "transfer-encoding"
                            and isinstance(header[1], str)
                            and header[1].strip().lower() == "chunked"
                            for header in headers
                        )
                        has_content_length = any(
                            isinstance(header, list)
                            and len(header) == 2
                            and isinstance(header[0], str)
                            and header[0].lower() == "content-length"
                            for header in headers
                        )
                        if not has_chunked_transfer_encoding or has_content_length:
                            raise ParityError(
                                f"{case_id}: request_body_chunks_base64 requires Transfer-Encoding: chunked and no Content-Length"
                            )
                elif "request_body_base64" in run_http or "request_body_chunks_base64" in run_http:
                    raise ParityError(
                        f"{case_id}: request body fields are only valid for WSGI POST inputs"
                    )
                if (
                    not isinstance(run_http["path"], str)
                    or not run_http["path"].startswith("/")
                    or "\r" in run_http["path"]
                    or "\n" in run_http["path"]
                ):
                    raise ParityError(f"{case_id}.api.run_http.path must be an origin-form path")
                if run_http["shutdown_signal"] not in {"SIGINT", "SIGTERM"}:
                    raise ParityError(
                        f"{case_id}: run_http supports SIGINT and SIGTERM shutdown stimuli"
                    )
                shutdown_signal_sequence = run_http.get("shutdown_signal_sequence")
                if shutdown_signal_sequence is not None:
                    if (
                        not isinstance(shutdown_signal_sequence, list)
                        or len(shutdown_signal_sequence) < 2
                        or len(shutdown_signal_sequence) > 4
                        or any(
                            not isinstance(signal_name, str)
                            or signal_name not in {"SIGINT", "SIGTERM"}
                            for signal_name in shutdown_signal_sequence
                        )
                        or shutdown_signal_sequence[-1] != run_http["shutdown_signal"]
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.shutdown_signal_sequence must contain at least two supported signals and end with shutdown_signal"
                        )
                    if (
                        run_http["invocation"] not in {"api", "module-cli"}
                        or run_http["path"]
                        != "/python-api-second-signal-escalation"
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http repeated signal input requires the public escalation fixture path"
                        )
                if run_http["lifespan"] not in {"auto", "on", "off"}:
                    raise ParityError(f"{case_id}.api.run_http.lifespan must be auto, on, or off")
                log_level = run_http.get("log_level")
                if log_level is not None and not (
                    isinstance(log_level, str)
                    and log_level.lower()
                    in {"critical", "error", "warning", "info", "debug", "trace"}
                    or type(log_level) is int
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.log_level must be a Uvicorn level name or integer"
                    )
                log_config = run_http.get("log_config")
                if log_config is not None and (
                    not isinstance(log_config, str)
                    or not log_config
                    or "\x00" in log_config
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.log_config must be a non-empty path string"
                    )
                if "emit_level_logs" in run_http and type(run_http["emit_level_logs"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.emit_level_logs must be a boolean"
                    )
                if "access_log" in run_http and type(run_http["access_log"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.access_log must be a boolean"
                    )
                if "use_colors" in run_http and type(run_http["use_colors"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.use_colors must be a boolean"
                    )
                for field in ("server_header", "date_header"):
                    if field in run_http and type(run_http[field]) is not bool:
                        raise ParityError(
                            f"{case_id}.api.run_http.{field} must be a boolean"
                        )
                    if field in run_http and run_http["invocation"] != "module-cli":
                        raise ParityError(
                            f"{case_id}.api.run_http.{field} currently requires module-cli invocation"
                        )
                if not isinstance(run_http["root_path"], str):
                    raise ParityError(f"{case_id}.api.run_http.root_path must be a string")
                if "root_path_from_environment" in run_http:
                    if type(run_http["root_path_from_environment"]) is not bool:
                        raise ParityError(
                            f"{case_id}.api.run_http.root_path_from_environment must be a boolean"
                        )
                    if run_http["root_path_from_environment"] and (
                        run_http["invocation"] != "module-cli"
                        or run_http.get("environment", {}).get("UVICORN_ROOT_PATH")
                        != run_http["root_path"]
                    ):
                        raise ParityError(
                            f"{case_id}: root_path_from_environment requires module-cli invocation and a matching UVICORN_ROOT_PATH"
                        )
                for field in ("headers", "request_headers", "observe_headers"):
                    if field not in run_http:
                        continue
                    values = run_http[field]
                    if not isinstance(values, list):
                        raise ParityError(f"{case_id}.api.run_http.{field} must be an array")
                    if field in {"headers", "request_headers"}:
                        if any(
                            not isinstance(header, list)
                            or len(header) != 2
                            or any(
                                not isinstance(part, str)
                                or "\r" in part
                                or "\n" in part
                                for part in header
                            )
                            or not header[0]
                            or ":" in header[0]
                            for header in values
                        ):
                            raise ParityError(
                                f"{case_id}.api.run_http.headers must contain name/value string pairs"
                            )
                    elif (
                        any(
                            not isinstance(name, str)
                            or not name
                            or ":" in name
                            or "\r" in name
                            or "\n" in name
                            for name in values
                        )
                        or len({name.lower() for name in values}) != len(values)
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.observe_headers must contain unique header names"
                        )
                if "observe_scope" in run_http and type(run_http["observe_scope"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.observe_scope must be a boolean"
                    )
                if run_http.get("observe_scope") and run_http["invocation"] != "api":
                    raise ParityError(
                        f"{case_id}.api.run_http.observe_scope is supported only for direct API invocation"
                    )
                if "observe_loop" in run_http and type(run_http["observe_loop"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.observe_loop must be a boolean"
                    )
                if run_http.get("observe_loop") and run_http["invocation"] == "module-cli":
                    raise ParityError(
                        f"{case_id}.api.run_http.observe_loop requires a programmatic invocation"
                    )
                if "loop" in run_http:
                    loop = run_http["loop"]
                    custom_factory_path = False
                    if type(loop) is str and run_http["invocation"] in {
                        "api",
                        "config-server",
                        "server-sockets",
                    }:
                        module, separator, attribute = loop.partition(":")
                        custom_factory_path = (
                            separator == ":"
                            and bool(module)
                            and bool(attribute)
                            and all(part.isidentifier() for part in module.split("."))
                            and all(part.isidentifier() for part in attribute.split("."))
                        )
                    if type(loop) is not str or (
                        loop not in {"auto", "asyncio", "uvloop"}
                        and not custom_factory_path
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_http.loop must be auto, asyncio, uvloop, "
                            "or a programmatic module:factory import path"
                        )
                if "proxy_headers" in run_http and type(run_http["proxy_headers"]) is not bool:
                    raise ParityError(
                        f"{case_id}.api.run_http.proxy_headers must be a boolean"
                    )
                if "forwarded_allow_ips" in run_http and not isinstance(
                    run_http["forwarded_allow_ips"], str
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.forwarded_allow_ips must be a string"
                    )
                if "limit_concurrency" in run_http and (
                    type(run_http["limit_concurrency"]) is not int
                    or run_http["limit_concurrency"] < 0
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.limit_concurrency must be a non-negative integer"
                    )
                if "http_version" in run_http and run_http["http_version"] not in {
                    "1.0",
                    "1.1",
                }:
                    raise ParityError(
                        f"{case_id}.api.run_http.http_version must be 1.0 or 1.1"
                    )
                environment = run_http.get("environment", {})
                if not isinstance(environment, dict):
                    raise ParityError(
                        f"{case_id}.api.run_http.environment must be an object"
                    )
                concurrency_environment_value = environment.get(
                    "UVICORN_LIMIT_CONCURRENCY"
                )
                has_concurrency_environment = (
                    concurrency_environment_value is not None
                )
                has_concurrency_argument = "limit_concurrency" in run_http
                is_concurrency_operation = (
                    case["operation"] == "python.api.run-http-concurrency"
                )
                if is_concurrency_operation != (
                    has_concurrency_argument or has_concurrency_environment
                ):
                    raise ParityError(
                        f"{case_id}: run-http-concurrency requires a limit_concurrency argument or UVICORN_LIMIT_CONCURRENCY environment value"
                    )
                if "environment" in run_http:
                    for name, value in environment.items():
                        invalid_name = (
                            not isinstance(name, str)
                            or not name
                            or "=" in name
                            or "\x00" in name
                        )
                        valid_value = value is None or (
                            isinstance(value, str) and "\x00" not in value
                        )
                        if invalid_name or not valid_value:
                            raise ParityError(
                                f"{case_id}.api.run_http.environment entries must be valid strings or null"
                            )
                if environment.get("UVICORN_FD") not in (None, "@probe-fd"):
                    raise ParityError(
                        f"{case_id}: run_http UVICORN_FD must use @probe-fd for inherited-listener parity"
                    )
                if environment.get("UVICORN_FD") == "@probe-fd" and (
                    run_http["invocation"] != "module-cli" or not run_http.get("fd")
                ):
                    raise ParityError(
                        f"{case_id}: UVICORN_FD=@probe-fd requires module-cli invocation and fd=true"
                    )
                if has_concurrency_environment:
                    if run_http["invocation"] != "module-cli":
                        raise ParityError(
                            f"{case_id}: UVICORN_LIMIT_CONCURRENCY requires module-cli invocation"
                        )
                    if not has_concurrency_argument:
                        try:
                            environment_limit = int(concurrency_environment_value)
                        except (TypeError, ValueError) as error:
                            raise ParityError(
                                f"{case_id}: UVICORN_LIMIT_CONCURRENCY must be an integer when no explicit CLI override is present"
                            ) from error
                        if environment_limit < 0:
                            raise ParityError(
                                f"{case_id}: UVICORN_LIMIT_CONCURRENCY must be non-negative"
                            )
                environment = run_http.get("environment", {})
                if environment.get("UVICORN_HOST") is not None:
                    if run_http["invocation"] != "module-cli":
                        raise ParityError(
                            f"{case_id}: UVICORN_HOST listener inputs require module-cli invocation"
                        )
                    expected_host = run_http.get("host", "127.0.0.1")
                    if environment.get("UVICORN_HOST") != expected_host:
                        raise ParityError(
                            f"{case_id}: UVICORN_HOST must match host when testing its environment binding"
                        )
                if environment.get("UVICORN_PORT") not in (None, "@probe-port"):
                    raise ParityError(
                        f"{case_id}: run_http UVICORN_PORT must use @probe-port for dynamic listener parity"
                    )
                if environment.get("UVICORN_PORT") == "@probe-port" and run_http[
                    "invocation"
                ] != "module-cli":
                    raise ParityError(
                        f"{case_id}: UVICORN_PORT listener inputs require module-cli invocation"
                    )
                if case["operation"] == "python.api.run-http-request-limit":
                    environment = run_http.get("environment", {})
                    try:
                        request_limit = int(
                            environment["UVICORN_LIMIT_MAX_REQUESTS"]
                        )
                        request_limit_jitter = int(
                            environment.get("UVICORN_LIMIT_MAX_REQUESTS_JITTER", "0")
                        )
                    except (KeyError, TypeError, ValueError) as error:
                        raise ParityError(
                            f"{case_id}: request-limit operation requires integer limit and jitter environment values"
                        ) from error
                    if (
                        request_limit < 1
                        or request_limit_jitter < 0
                        or request_limit + request_limit_jitter > 16
                    ):
                        raise ParityError(
                            f"{case_id}: request-limit probe bound must be from 1 through 16"
                        )
                timeout_seconds = run_http["timeout_seconds"]
                if type(timeout_seconds) is not int or not 2 <= timeout_seconds <= 60:
                    raise ParityError(f"{case_id}.api.run_http.timeout_seconds must be from 2 through 60")
                client_timeout_seconds = run_http.get("client_timeout_seconds")
                if client_timeout_seconds is not None and (
                    type(client_timeout_seconds) is not int
                    or not 1 <= client_timeout_seconds <= timeout_seconds
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.client_timeout_seconds must be from 1 through timeout_seconds"
                    )
                post_response_settle_seconds = run_http.get(
                    "post_response_settle_seconds"
                )
                if post_response_settle_seconds is not None and (
                    type(post_response_settle_seconds) not in {int, float}
                    or not 0 < post_response_settle_seconds <= 2
                ):
                    raise ParityError(
                        f"{case_id}.api.run_http.post_response_settle_seconds must be greater than 0 and at most 2"
                    )
                shutdown_delay_values = [
                    value
                    for name, value in run_http.get("request_headers", [])
                    if name.lower() == "x-parity-lifespan-shutdown-delay"
                ]
                if shutdown_delay_values:
                    value = shutdown_delay_values[0]
                    if (
                        run_http["invocation"] != "module-cli"
                        or len(shutdown_delay_values) != 1
                        or not value.isascii()
                        or not value.isdigit()
                        or not 11 <= int(value) <= 30
                        or timeout_seconds < int(value) + 3
                    ):
                        raise ParityError(
                            f"{case_id}: lifespan shutdown delay must be one module-CLI header from 11 through 30 seconds, with three seconds of probe margin"
                        )
            elif case["operation"] in {
                "python.api.run-websocket",
                "python.api.run-websocket-keepalive-no-timeout",
                "python.api.run-websocket-keepalive-unbounded-timeout",
                "python.api.run-websocket-keepalive-infinite-interval",
                "python.api.run-websocket-keepalive-nan-interval",
                "python.api.run-websocket-keepalive-nan-timeout",
                "python.api.run-websocket-keepalive-disabled",
                "python.api.run-websocket-keepalive-negative-timeout",
            }:
                exact_keys(case["api"], {"run_websocket"}, f"{case_id}.api")
                run_websocket = case["api"]["run_websocket"]
                run_websocket_keys = {
                    "path",
                    "message",
                    "ws_max_size",
                    "timeout_seconds",
                }
                run_websocket_keys.update(
                    key
                    for key in (
                        "invocation",
                        "ws_backend",
                        "send_count",
                        "ws_max_queue",
                        "uds",
                        "observe_scope",
                        "observe_server_pings",
                        "suppress_server_pongs",
                        "ws_ping_interval",
                        "ws_ping_timeout",
                        "keepalive_idle_seconds",
                        "ws_per_message_deflate",
                        "observe_compression",
                    )
                    if key in run_websocket
                )
                exact_keys(
                    run_websocket,
                    run_websocket_keys,
                    f"{case_id}.api.run_websocket",
                )
                if (
                    not isinstance(run_websocket["path"], str)
                    or not run_websocket["path"].startswith("/")
                    or "\r" in run_websocket["path"]
                    or "\n" in run_websocket["path"]
                ):
                    raise ParityError(
                        f"{case_id}.api.run_websocket.path must be an origin-form path"
                    )
                if not isinstance(run_websocket["message"], str):
                    raise ParityError(f"{case_id}.api.run_websocket.message must be a string")
                if type(run_websocket["ws_max_size"]) is not int or run_websocket["ws_max_size"] < 0:
                    raise ParityError(
                        f"{case_id}.api.run_websocket.ws_max_size must be a non-negative integer"
                    )
                if "ws_max_queue" in run_websocket and type(run_websocket["ws_max_queue"]) is not int:
                    raise ParityError(
                        f"{case_id}.api.run_websocket.ws_max_queue must be an integer"
                    )
                if run_websocket.get("invocation", "api") not in {"api", "module-cli"}:
                    raise ParityError(
                        f"{case_id}.api.run_websocket.invocation must be api or module-cli"
                    )
                if "ws_backend" in run_websocket and (
                    run_websocket.get("invocation") != "module-cli"
                    or run_websocket["ws_backend"]
                    not in {"auto", "websockets", "websockets-sansio", "wsproto"}
                ):
                    raise ParityError(
                        f"{case_id}.api.run_websocket.ws_backend requires module-cli and a supported selector"
                    )
                if "send_count" in run_websocket and (
                    type(run_websocket["send_count"]) is not int
                    or not 1 <= run_websocket["send_count"] <= 32
                    or run_websocket.get("path") != "/ws-queue-delayed-reader"
                ):
                    raise ParityError(
                        f"{case_id}.api.run_websocket.send_count is limited to 1 through 32 on the delayed-reader fixture"
                    )
                if "observe_server_pings" in run_websocket and (
                    type(run_websocket["observe_server_pings"]) is not bool
                    or run_websocket.get("invocation") != "module-cli"
                ):
                    raise ParityError(
                        f"{case_id}.api.run_websocket.observe_server_pings requires module-cli"
                    )
                if run_websocket.get("suppress_server_pongs", False) and (
                    run_websocket.get("observe_server_pings") is not True
                    or run_websocket.get("invocation") != "module-cli"
                ):
                    raise ParityError(
                        f"{case_id}.api.run_websocket.suppress_server_pongs requires observed module-CLI server pings"
                    )
                for key in (
                    "uds",
                    "observe_scope",
                    "observe_server_pings",
                    "suppress_server_pongs",
                    "ws_per_message_deflate",
                    "observe_compression",
                ):
                    if key in run_websocket and type(run_websocket[key]) is not bool:
                        raise ParityError(
                            f"{case_id}.api.run_websocket.{key} must be a boolean"
                        )
                for key in ("ws_ping_interval", "ws_ping_timeout"):
                    value = run_websocket.get(key)
                    nan_interval_marker = (
                        key == "ws_ping_interval"
                        and case["operation"] == "python.api.run-websocket-keepalive-nan-interval"
                        and value == {"$float": "nan"}
                    )
                    nan_timeout_marker = (
                        key == "ws_ping_timeout"
                        and case["operation"] == "python.api.run-websocket-keepalive-nan-timeout"
                        and value == {"$float": "nan"}
                    )
                    if key in run_websocket and value is not None and (
                        not (nan_interval_marker or nan_timeout_marker)
                        and (
                            type(value) not in {int, float}
                            or (type(value) is float and math.isnan(value))
                            or (key == "ws_ping_interval" and value < 0)
                        )
                    ):
                        raise ParityError(
                            f"{case_id}.api.run_websocket.{key} must be null or a number other than NaN, with a non-negative ping interval"
                        )
                if "keepalive_idle_seconds" in run_websocket and (
                    type(run_websocket["keepalive_idle_seconds"]) not in {int, float}
                    or not math.isfinite(run_websocket["keepalive_idle_seconds"])
                    or not 0 < run_websocket["keepalive_idle_seconds"] <= 2
                ):
                    raise ParityError(
                        f"{case_id}.api.run_websocket.keepalive_idle_seconds must be positive and at most 2 seconds"
                    )
                if run_websocket.get("observe_server_pings"):
                    interval = run_websocket.get("ws_ping_interval")
                    idle_seconds = run_websocket.get("keepalive_idle_seconds")
                    if (
                        type(interval) not in {int, float}
                        or not math.isfinite(interval)
                        or interval <= 0
                        or type(idle_seconds) not in {int, float}
                        or idle_seconds < 2 * interval
                    ):
                        raise ParityError(
                            f"{case_id}: server Ping observation requires a positive finite interval and at least two intervals of idle time"
                        )
                if case["operation"] == "python.api.run-websocket-keepalive-no-timeout":
                    interval = run_websocket.get("ws_ping_interval")
                    idle_seconds = run_websocket.get("keepalive_idle_seconds")
                    if (
                        type(interval) not in {int, float}
                        or run_websocket.get("ws_ping_timeout", "missing") is not None
                        or type(idle_seconds) not in {int, float}
                        or idle_seconds < interval * 2
                    ):
                        raise ParityError(
                            f"{case_id}: no-timeout keepalive requires an interval, a null ping timeout, and an idle period of at least two intervals"
                        )
                if case["operation"] == "python.api.run-websocket-keepalive-unbounded-timeout":
                    interval = run_websocket.get("ws_ping_interval")
                    timeout = run_websocket.get("ws_ping_timeout")
                    idle_seconds = run_websocket.get("keepalive_idle_seconds")
                    if (
                        type(interval) not in {int, float}
                        or interval <= 0
                        or type(timeout) not in {int, float}
                        or timeout <= 1e20
                        or type(idle_seconds) not in {int, float}
                        or idle_seconds < interval * 2
                    ):
                        raise ParityError(
                            f"{case_id}: unbounded-timeout keepalive requires a positive interval, a timeout beyond Rust Duration range, and an idle period of at least two intervals"
                        )
                if case["operation"] == "python.api.run-websocket-keepalive-infinite-interval":
                    interval = run_websocket.get("ws_ping_interval")
                    timeout = run_websocket.get("ws_ping_timeout")
                    idle_seconds = run_websocket.get("keepalive_idle_seconds")
                    if (
                        type(interval) is not float
                        or not math.isinf(interval)
                        or interval < 0
                        or type(timeout) not in {int, float}
                        or not math.isfinite(timeout)
                        or type(idle_seconds) not in {int, float}
                        or not 0 < idle_seconds <= 2
                    ):
                        raise ParityError(
                            f"{case_id}: infinite-interval keepalive requires a positive infinite interval, finite ping timeout, and idle period from 0 through 2 seconds"
                        )
                if case["operation"] == "python.api.run-websocket-keepalive-nan-interval":
                    if (
                        run_websocket.get("ws_ping_interval") != {"$float": "nan"}
                        or type(run_websocket.get("ws_ping_timeout")) not in {int, float}
                        or not math.isfinite(run_websocket["ws_ping_timeout"])
                        or run_websocket["ws_ping_timeout"] <= 0
                    ):
                        raise ParityError(
                            f"{case_id}: NaN-interval keepalive requires the explicit NaN marker and a positive finite ping timeout"
                        )
                if case["operation"] == "python.api.run-websocket-keepalive-nan-timeout":
                    interval = run_websocket.get("ws_ping_interval")
                    idle_seconds = run_websocket.get("keepalive_idle_seconds")
                    if (
                        type(interval) not in {int, float}
                        or interval <= 0
                        or run_websocket.get("ws_ping_timeout") != {"$float": "nan"}
                        or type(idle_seconds) not in {int, float}
                        or idle_seconds < interval * 2
                    ):
                        raise ParityError(
                            f"{case_id}: NaN-timeout keepalive requires a positive interval, the explicit NaN marker, and an idle period of at least two intervals"
                        )
                if case["operation"] == "python.api.run-websocket-keepalive-disabled" and (
                    run_websocket.get("ws_ping_interval", "missing") is not None
                    or run_websocket.get("ws_ping_timeout", "missing") is not None
                ):
                    raise ParityError(
                        f"{case_id}: disabled keepalive requires explicit null ping interval and timeout settings"
                    )
                if case["operation"] == "python.api.run-websocket-keepalive-negative-timeout" and (
                    type(run_websocket.get("ws_ping_interval")) not in {int, float}
                    or run_websocket["ws_ping_interval"] <= 0
                    or type(run_websocket.get("ws_ping_timeout")) not in {int, float}
                    or run_websocket["ws_ping_timeout"] >= 0
                    or type(run_websocket.get("keepalive_idle_seconds")) not in {int, float}
                    or run_websocket["keepalive_idle_seconds"] < run_websocket["ws_ping_interval"] * 2
                ):
                    raise ParityError(
                        f"{case_id}: negative-timeout keepalive requires a positive interval, negative timeout, and idle period of at least two intervals"
                    )
                timeout_seconds = run_websocket["timeout_seconds"]
                if type(timeout_seconds) is not int or not 2 <= timeout_seconds <= 8:
                    raise ParityError(
                        f"{case_id}.api.run_websocket.timeout_seconds must be from 2 through 8"
                    )
            elif case["operation"] == "python.api.server-serve-cancellation":
                exact_keys(case["api"], {"server_serve_cancellation"}, f"{case_id}.api")
                cancellation = case["api"]["server_serve_cancellation"]
                exact_keys(
                    cancellation,
                    {"phase"},
                    f"{case_id}.api.server_serve_cancellation",
                )
                if cancellation["phase"] not in {"after-startup", "during-startup"}:
                    raise ParityError(
                        f"{case_id}.api.server_serve_cancellation.phase must be after-startup or during-startup"
                    )
            elif case["operation"] in readiness_operations:
                input_name = readiness_operations[case["operation"]]
                exact_keys(case["api"], {input_name}, f"{case_id}.api")
                if case["api"][input_name] is not True:
                    raise ParityError(f"{case_id}.api.{input_name} must be true")
            elif case["operation"] == "python.api.server-lifespan-mode-validation":
                exact_keys(case["api"], {"server_lifespan_mode"}, f"{case_id}.api")
                mode = case["api"]["server_lifespan_mode"]
                mode_keys = {"mode"}
                if mode.get("mode") == "boolean-disabled":
                    mode_keys.update(
                        {"prebound_listener", "limit_max_requests", "limit_max_requests_jitter"}
                    )
                exact_keys(mode, mode_keys, f"{case_id}.api.server_lifespan_mode")
                if mode["mode"] not in {
                    "boolean-disabled",
                    "boolean-enabled",
                    "invalid-string",
                    "invalid-type",
                }:
                    raise ParityError(
                        f"{case_id}.api.server_lifespan_mode.mode must be boolean-disabled, boolean-enabled, invalid-string, or invalid-type"
                    )
                if mode["mode"] == "boolean-disabled":
                    if mode["prebound_listener"] is not True:
                        raise ParityError(
                            f"{case_id}.api.server_lifespan_mode.prebound_listener must be true"
                        )
                    if type(mode["limit_max_requests"]) is not int or mode["limit_max_requests"] < 1:
                        raise ParityError(
                            f"{case_id}.api.server_lifespan_mode.limit_max_requests must be a positive integer"
                        )
                    if (
                        type(mode["limit_max_requests_jitter"]) is not int
                        or mode["limit_max_requests_jitter"] < 1
                    ):
                        raise ParityError(
                            f"{case_id}.api.server_lifespan_mode.limit_max_requests_jitter must be a positive integer"
                        )
            elif case["operation"] in {
                "python.api.server-lifespan-startup",
                "python.api.server-lifespan-auto-fallback",
                "python.api.server-lifespan-early-return",
            }:
                exact_keys(case["api"], {"server_lifespan_startup"}, f"{case_id}.api")
                startup = case["api"]["server_lifespan_startup"]
                exact_keys(
                    startup,
                    {"lifespan", "app_lifespan", "timeout_seconds"},
                    f"{case_id}.api.server_lifespan_startup",
                )
                expected_lifespan = {
                    "python.api.server-lifespan-startup": {"on"},
                    "python.api.server-lifespan-auto-fallback": {"auto"},
                    "python.api.server-lifespan-early-return": {"auto", "on"},
                }[case["operation"]]
                if startup["lifespan"] not in expected_lifespan:
                    raise ParityError(
                        f"{case_id}.api.server_lifespan_startup.lifespan must be one of {sorted(expected_lifespan)}"
                    )
                if startup["app_lifespan"] not in {
                    "raises-before-startup",
                    "unexpected-startup-event",
                    "returns-before-startup-event",
                }:
                    raise ParityError(
                        f"{case_id}.api.server_lifespan_startup.app_lifespan must be raises-before-startup, unexpected-startup-event, or returns-before-startup-event"
                    )
                timeout_seconds = startup["timeout_seconds"]
                if type(timeout_seconds) is not int or not 2 <= timeout_seconds <= 8:
                    raise ParityError(
                        f"{case_id}.api.server_lifespan_startup.timeout_seconds must be from 2 through 8"
                    )
            elif case["operation"] == "python.api.module-cli-lifespan-startup":
                exact_keys(case["api"], {"module_cli_lifespan_startup"}, f"{case_id}.api")
                startup = case["api"]["module_cli_lifespan_startup"]
                exact_keys(
                    startup,
                    {"lifespan", "app_lifespan", "timeout_seconds"},
                    f"{case_id}.api.module_cli_lifespan_startup",
                )
                if startup["lifespan"] != "on":
                    raise ParityError(
                        f"{case_id}.api.module_cli_lifespan_startup.lifespan must be on"
                    )
                if startup["app_lifespan"] != "raises-before-startup":
                    raise ParityError(
                        f"{case_id}.api.module_cli_lifespan_startup.app_lifespan must be raises-before-startup"
                    )
                timeout_seconds = startup["timeout_seconds"]
                if type(timeout_seconds) is not int or not 2 <= timeout_seconds <= 8:
                    raise ParityError(
                        f"{case_id}.api.module_cli_lifespan_startup.timeout_seconds must be from 2 through 8"
                    )
            elif case["operation"] == "python.api.imports-signatures":
                api_keys = {"imports", "signatures"}
                if "calls" in case["api"]:
                    api_keys.add("calls")
                if "config_probes" in case["api"]:
                    api_keys.add("config_probes")
                if "server_on_tick" in case["api"]:
                    api_keys.add("server_on_tick")
                if "server_lifecycle" in case["api"]:
                    api_keys.add("server_lifecycle")
                if "server_signals" in case["api"]:
                    api_keys.add("server_signals")
                exact_keys(case["api"], api_keys, f"{case_id}.api")
                for field in ("imports", "signatures"):
                    paths = case["api"][field]
                    if (
                        not isinstance(paths, list)
                        or not paths
                        or len(paths) != len(set(paths))
                        or any(not isinstance(path, str) or not path or "\x00" in path for path in paths)
                    ):
                        raise ParityError(f"{case_id}.api.{field} must be a unique non-empty path list")
                if "calls" in case["api"]:
                    calls = case["api"]["calls"]
                    if not isinstance(calls, list) or not calls:
                        raise ParityError(f"{case_id}.api.calls must be a non-empty array")
                    for index, call in enumerate(calls):
                        call_keys = {"target", "arguments", "keyword_arguments"}
                        if "method_calls" in call:
                            call_keys.add("method_calls")
                        exact_keys(
                            call,
                            call_keys,
                            f"{case_id}.api.calls[{index}]",
                        )
                        if (
                            not isinstance(call["target"], str)
                            or not call["target"]
                            or not isinstance(call["arguments"], list)
                            or not isinstance(call["keyword_arguments"], dict)
                        ):
                            raise ParityError(f"{case_id}.api.calls[{index}] has invalid call inputs")
                        if "method_calls" in call:
                            method_calls = call["method_calls"]
                            if not isinstance(method_calls, list) or not method_calls:
                                raise ParityError(
                                    f"{case_id}.api.calls[{index}].method_calls must be a non-empty array"
                                )
                            for method_index, method_call in enumerate(method_calls):
                                exact_keys(
                                    method_call,
                                    {"method", "arguments", "keyword_arguments"},
                                    f"{case_id}.api.calls[{index}].method_calls[{method_index}]",
                                )
                                method = method_call["method"]
                                if (
                                    not isinstance(method, str)
                                    or not method.isidentifier()
                                    or method.startswith("_")
                                    or not isinstance(method_call["arguments"], list)
                                    or not isinstance(method_call["keyword_arguments"], dict)
                                ):
                                    raise ParityError(
                                        f"{case_id}.api.calls[{index}].method_calls[{method_index}] has invalid method inputs"
                                    )
                if "config_probes" in case["api"]:
                    probes = case["api"]["config_probes"]
                    if not isinstance(probes, list) or not probes:
                        raise ParityError(
                            f"{case_id}.api.config_probes must be a non-empty array"
                        )
                    for index, probe in enumerate(probes):
                        probe_context = f"{case_id}.api.config_probes[{index}]"
                        exact_keys(
                            probe,
                            {"app", "options", "properties", "methods"},
                            probe_context,
                        )
                        if (
                            not isinstance(probe["app"], str)
                            or not probe["app"]
                            or "\x00" in probe["app"]
                            or not isinstance(probe["options"], dict)
                        ):
                            raise ParityError(
                                f"{probe_context} has invalid Config constructor inputs"
                            )
                        for field in ("properties", "methods"):
                            names = probe[field]
                            if (
                                not isinstance(names, list)
                                or any(
                                    not isinstance(name, str)
                                    or not name.isidentifier()
                                    or name.startswith("_")
                                    for name in names
                                )
                                or len(names) != len(set(names))
                            ):
                                raise ParityError(
                                    f"{probe_context}.{field} must be a unique public-name list"
                                )
                if "server_on_tick" in case["api"]:
                    probe = case["api"]["server_on_tick"]
                    probe_context = f"{case_id}.api.server_on_tick"
                    exact_keys(
                        probe,
                        {
                            "options",
                            "counter",
                            "total_requests",
                            "callback_notify",
                        },
                        probe_context,
                    )
                    if (
                        not isinstance(probe["options"], dict)
                        or type(probe["counter"]) is not int
                        or probe["counter"] < 0
                        or type(probe["total_requests"]) is not int
                        or probe["total_requests"] < 0
                        or type(probe["callback_notify"]) is not bool
                    ):
                        raise ParityError(
                            f"{probe_context} has invalid server tick inputs"
                        )
                if "server_lifecycle" in case["api"]:
                    probe = case["api"]["server_lifecycle"]
                    probe_context = f"{case_id}.api.server_lifecycle"
                    exact_keys(
                        probe,
                        {"stop_phase"},
                        probe_context,
                    )
                    if probe["stop_phase"] not in {"before_startup", "after_startup"}:
                        raise ParityError(
                            f"{probe_context}.stop_phase must be before_startup or after_startup"
                        )
                if "server_signals" in case["api"]:
                    probe = case["api"]["server_signals"]
                    probe_context = f"{case_id}.api.server_signals"
                    exact_keys(probe, {"sequences"}, probe_context)
                    sequences = probe["sequences"]
                    if not isinstance(sequences, list) or not sequences:
                        raise ParityError(
                            f"{probe_context}.sequences must be a non-empty array"
                        )
                    for sequence_index, sequence in enumerate(sequences):
                        if (
                            not isinstance(sequence, list)
                            or not sequence
                            or any(
                                not isinstance(signal_name, str)
                                or signal_name not in {"SIGINT", "SIGTERM"}
                                for signal_name in sequence
                            )
                        ):
                            raise ParityError(
                                f"{probe_context}.sequences[{sequence_index}] must contain supported signal names"
                            )
            else:
                raise ParityError(f"{case_id}: unsupported Python API operation {case['operation']!r}")
        elif kind in http_profile_ids and "response_stream" in case:
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
            if "after_close_delay_ms" in case["disconnect"]:
                disconnect_keys.add("after_close_delay_ms")
                delay_ms = case["disconnect"]["after_close_delay_ms"]
                if (
                    isinstance(delay_ms, bool)
                    or not isinstance(delay_ms, int)
                    or not 1 <= delay_ms <= 5000
                    or kind != "http1"
                    or case["disconnect"].get("wait_event")
                    != "http.disconnect.before-first-receive"
                ):
                    raise ParityError(
                        f"{case_id}: after_close_delay_ms requires the HTTP/1 pre-first-receive case and must be 1..5000"
                    )
            if "reset" in case["disconnect"]:
                disconnect_keys.add("reset")
                if case["disconnect"]["reset"] is not True:
                    raise ParityError(f"{case_id}: reset must be true when present")
            if "reset_after_complete_request" in case["disconnect"]:
                disconnect_keys.add("reset_after_complete_request")
                if (
                    case["disconnect"]["reset_after_complete_request"] is not True
                    or kind != "http1"
                    or case["disconnect"].get("empty_request") is not True
                    or "wait_event" not in case["disconnect"]
                ):
                    raise ParityError(
                        f"{case_id}: reset_after_complete_request requires an empty HTTP/1 request and a wait_event"
                    )
            if "content_length" in case["disconnect"]:
                disconnect_keys.update({"content_length", "partial_body_base64"})
                if not isinstance(case["disconnect"]["content_length"], int) or case["disconnect"]["content_length"] <= 0:
                    raise ParityError(f"{case_id}: incomplete request content length must be positive")
                try:
                    partial_body = base64.b64decode(case["disconnect"]["partial_body_base64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid partial disconnect body base64") from error
                if len(partial_body) >= case["disconnect"]["content_length"]:
                    raise ParityError(f"{case_id}: disconnect body prefix must be shorter than content_length")
            elif "partial_body_base64" in case["disconnect"]:
                disconnect_keys.add("partial_body_base64")
                if not case["disconnect"].get("malformed_chunk"):
                    raise ParityError(
                        f"{case_id}: a partial body without content-length is supported only before malformed chunk framing"
                    )
                try:
                    partial_body = base64.b64decode(case["disconnect"]["partial_body_base64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid partial malformed-chunk body base64") from error
                if not partial_body:
                    raise ParityError(f"{case_id}: malformed-chunk body prefix must be nonempty")
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
            stream_keys = {"method", "path", "headers"}
            has_encoded_chunks = "chunks_base64" in stream
            has_generated_chunks = "generated_chunks" in stream
            if has_encoded_chunks == has_generated_chunks:
                raise ParityError(
                    f"{case_id}: request streaming requires exactly one chunk source"
                )
            if has_encoded_chunks:
                stream_keys.add("chunks_base64")
            if has_generated_chunks:
                stream_keys.add("generated_chunks")
                if kind != "http1":
                    raise ParityError(
                        f"{case_id}: generated request chunks are supported only for HTTP/1.1"
                    )
            if "trailers" in stream:
                stream_keys.add("trailers")
            if "followup_path" in stream:
                stream_keys.add("followup_path")
                if not isinstance(stream["followup_path"], str) or not stream["followup_path"].startswith("/"):
                    raise ParityError(f"{case_id}: request-stream followup_path must be an origin-form path")
            if "send_all_before_read" in stream:
                stream_keys.add("send_all_before_read")
                if stream["send_all_before_read"] is not True:
                    raise ParityError(f"{case_id}: send_all_before_read must be true when present")
            if "send_body_concurrently_with_response_read" in stream:
                stream_keys.add("send_body_concurrently_with_response_read")
                if (
                    stream["send_body_concurrently_with_response_read"] is not True
                    or kind != "http1"
                    or stream.get("send_all_before_read") is True
                    or stream.get("send_remaining_after_response") is True
                ):
                    raise ParityError(
                        f"{case_id}: concurrent request-body sending requires an HTTP/1.1 streaming input"
                    )
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
            if "send_first_chunk_before_wait_event" in stream:
                stream_keys.add("send_first_chunk_before_wait_event")
                if (
                    stream["send_first_chunk_before_wait_event"] is not True
                    or kind != "http1"
                    or case.get("fault", {}).get("contract")
                    != "http-body-pump-drain-terminal-frame"
                ):
                    raise ParityError(
                        f"{case_id}: first-chunk-before-event sequencing is limited to the terminal-frame fault contract"
                    )
            if "expected_response_body_base64" in stream:
                stream_keys.add("expected_response_body_base64")
                if (
                    case.get("fault", {}).get("contract")
                    != "http-body-pump-drain-terminal-frame"
                ):
                    raise ParityError(
                        f"{case_id}: expected response body is limited to the terminal-frame fault contract"
                    )
                try:
                    base64.b64decode(stream["expected_response_body_base64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(
                        f"{case_id}: invalid expected_response_body_base64"
                    ) from error
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
            if has_encoded_chunks:
                if not isinstance(stream["chunks_base64"], list) or len(stream["chunks_base64"]) < 2:
                    raise ParityError(f"{case_id}: request streaming requires at least two input chunks")
                try:
                    for chunk in stream["chunks_base64"]:
                        base64.b64decode(chunk, validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid request-stream base64") from error
            else:
                chunks = stream["generated_chunks"]
                if not isinstance(chunks, list) or not 2 <= len(chunks) <= 16:
                    raise ParityError(
                        f"{case_id}: generated request streaming requires 2 to 16 chunks"
                    )
                total_bytes = 0
                for index, chunk in enumerate(chunks):
                    if not isinstance(chunk, dict):
                        raise ParityError(
                            f"{case_id}: generated chunk {index} must be an object"
                        )
                    exact_keys(chunk, {"byte_value", "size_bytes"}, f"{case_id}.generated_chunks[{index}]")
                    byte_value = chunk["byte_value"]
                    size_bytes = chunk["size_bytes"]
                    if (
                        not isinstance(byte_value, int)
                        or isinstance(byte_value, bool)
                        or not 0 <= byte_value <= 255
                        or not isinstance(size_bytes, int)
                        or isinstance(size_bytes, bool)
                        or not 1 <= size_bytes <= 1_048_576
                    ):
                        raise ParityError(
                            f"{case_id}: generated chunk {index} has an invalid byte or size"
                        )
                    total_bytes += size_bytes
                if total_bytes > 2_097_152:
                    raise ParityError(
                        f"{case_id}: generated request body exceeds the 2 MiB input limit"
                    )
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
            case_keys = {"case_id", "profile", "operation", "covers", "request"}
            if "server_options" in case:
                case_keys.add("server_options")
                server_options = case["server_options"]
                if not isinstance(server_options, dict):
                    raise ParityError(f"{case_id}: server_options must be an object")
                allowed_options = {
                    "proxy_headers", "forwarded_allow_ips", "limit_concurrency",
                    "headers", "server_header", "date_header",
                }
                if kind == "http1":
                    allowed_options.add("http")
                    allowed_options.add("h11_max_incomplete_event_size")
                if kind in {"http1", "http2"}:
                    allowed_options.add("reset_contextvars")
                if kind == "http1-tls":
                    allowed_options.update({"ssl_ca_certs", "ssl_cert_reqs", "ssl_version", "ssl_ciphers"})
                unknown_options = set(server_options) - allowed_options
                if unknown_options:
                    raise ParityError(
                        f"{case_id}: unsupported HTTP server options: "
                        f"{', '.join(sorted(unknown_options))}"
                    )
                if "proxy_headers" in server_options and type(
                    server_options["proxy_headers"]
                ) is not bool:
                    raise ParityError(
                        f"{case_id}: server_options.proxy_headers must be a boolean"
                    )
                if "forwarded_allow_ips" in server_options and not isinstance(
                    server_options["forwarded_allow_ips"], str
                ):
                    raise ParityError(
                        f"{case_id}: server_options.forwarded_allow_ips must be a string"
                    )
                if "headers" in server_options and (
                    not isinstance(server_options["headers"], list)
                    or any(not isinstance(header, str) for header in server_options["headers"])
                ):
                    raise ParityError(
                        f"{case_id}: server_options.headers must be a list of strings"
                    )
                for option in ("server_header", "date_header"):
                    if option in server_options and type(server_options[option]) is not bool:
                        raise ParityError(
                            f"{case_id}: server_options.{option} must be a boolean"
                        )
                if "reset_contextvars" in server_options and type(
                    server_options["reset_contextvars"]
                ) is not bool:
                    raise ParityError(
                        f"{case_id}: server_options.reset_contextvars must be a boolean"
                    )
                if "limit_concurrency" in server_options and (
                    type(server_options["limit_concurrency"]) is not int
                    or server_options["limit_concurrency"] < 0
                ):
                    raise ParityError(
                        f"{case_id}: server_options.limit_concurrency must be a non-negative integer"
                    )
                if "http" in server_options and server_options["http"] not in {
                    "auto", "h11", "httptools"
                }:
                    raise ParityError(
                        f"{case_id}: server_options.http must select auto, h11, or httptools"
                    )
                if "h11_max_incomplete_event_size" in server_options and type(
                    server_options["h11_max_incomplete_event_size"]
                ) is not int:
                    raise ParityError(
                        f"{case_id}: server_options.h11_max_incomplete_event_size must be an integer"
                    )
                if (
                    "ssl_ca_certs" in server_options
                    and server_options["ssl_ca_certs"] != "generated-ca"
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ssl_ca_certs must select the generated parity CA"
                    )
                if "ssl_cert_reqs" in server_options and (
                    type(server_options["ssl_cert_reqs"]) is not int
                    or server_options["ssl_cert_reqs"] not in {0, 1, 2}
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ssl_cert_reqs must be 0, 1, or 2"
                    )
                if "ssl_version" in server_options and (
                    type(server_options["ssl_version"]) is not int
                    or server_options["ssl_version"] != ssl.PROTOCOL_TLSv1_2
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ssl_version must select TLS 1.2"
                    )
                if "ssl_ciphers" in server_options and (
                    not isinstance(server_options["ssl_ciphers"], str)
                    or not server_options["ssl_ciphers"]
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ssl_ciphers must be a non-empty string"
                    )
            if "client_tls" in case:
                case_keys.add("client_tls")
                if kind != "http1-tls" or case["client_tls"] is not True:
                    raise ParityError(
                        f"{case_id}: client_tls is only supported as true for HTTP/1.1 TLS parity"
                    )
            exact_case_keys(case, case_keys, case_id)
            request = case["request"]
            request_keys = {"method", "path", "headers", "body_base64"}
            if "h3_grease" in request:
                request_keys.add("h3_grease")
                if not isinstance(request["h3_grease"], bool) or kind != "http3":
                    raise ParityError(f"{case_id}: h3_grease is a boolean HTTP/3 request option")
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
            if "trailers" in request:
                request_keys.add("trailers")
                if kind != "http3":
                    raise ParityError(f"{case_id}: request trailers are currently supported only for HTTP/3")
                trailers = request["trailers"]
                if (
                    not isinstance(trailers, list)
                    or not trailers
                    or any(
                        not isinstance(header, list)
                        or len(header) != 2
                        or not all(isinstance(part, str) for part in header)
                        for header in trailers
                    )
                ):
                    raise ParityError(f"{case_id}: request trailers must be nonempty pairs of strings")
                if request["method"] != "POST" or not request["body_base64"]:
                    raise ParityError(f"{case_id}: HTTP/3 request trailers require a nonempty POST body")
            if "abort_after_body" in request:
                request_keys.add("abort_after_body")
                if request["abort_after_body"] is not True or kind != "http3":
                    raise ParityError(f"{case_id}: abort_after_body is supported only for HTTP/3")
            if "malformed_data_frame_after_headers" in request:
                request_keys.add("malformed_data_frame_after_headers")
                if (
                    request["malformed_data_frame_after_headers"] is not True
                    or kind != "http3"
                    or operation != "http3.truncated-data-frame-recovery"
                    or request["method"] != "POST"
                    or request["path"] != "/h3-upload-disconnect"
                    or request["headers"] != []
                    or request["body_base64"] != ""
                ):
                    raise ParityError(
                        f"{case_id}: truncated HTTP/3 DATA input requires the declared empty POST disconnect workflow"
                    )
            if "peer_stop_before_response_headers" in request:
                request_keys.update({
                    "peer_stop_before_response_headers",
                    "same_connection_followup_path",
                })
                followup_path = request.get("same_connection_followup_path")
                if (
                    request["peer_stop_before_response_headers"] is not True
                    or kind != "http3"
                    or operation != "http3.peer-stop-cancels-held-request"
                    or request["method"] != "GET"
                    or request["path"] != "/hold"
                    or request["body_base64"] != ""
                    or request["headers"] != []
                    or not isinstance(followup_path, str)
                    or not followup_path.startswith("/")
                ):
                    raise ParityError(
                        f"{case_id}: held-request peer-stop requires the declared HTTP/3 GET and same-connection follow-up"
                    )
            if "peer_stop_while_upload_open" in request:
                request_keys.update({
                    "peer_stop_while_upload_open",
                    "same_connection_followup_path",
                })
                followup_path = request.get("same_connection_followup_path")
                content_lengths = [
                    value for name, value in request["headers"]
                    if name.lower() == "content-length"
                ]
                body_length = len(
                    base64.b64decode(request["body_base64"], validate=True)
                )
                if (
                    request["peer_stop_while_upload_open"] is not True
                    or kind != "http3"
                    or operation != "http3.peer-stop-disconnects-open-request-body"
                    or request["method"] != "POST"
                    or request["path"] != "/h3-open-upload-peer-stop"
                    or body_length == 0
                    or len(content_lengths) != 1
                    or not content_lengths[0].isdigit()
                    or int(content_lengths[0]) <= body_length
                    or not isinstance(followup_path, str)
                    or not followup_path.startswith("/")
                ):
                    raise ParityError(
                        f"{case_id}: open-upload peer stop requires the declared partial HTTP/3 POST and same-connection follow-up"
                    )
            if "complete_upload_after_response" in request:
                request_keys.update({
                    "complete_upload_after_response",
                    "same_connection_followup_path",
                })
                followup_path = request.get("same_connection_followup_path")
                if (
                    request["complete_upload_after_response"] is not True
                    or kind != "http3"
                    or operation != "http3.open-upload-retires-body-pump"
                    or request["method"] != "POST"
                    or request["path"] != "/h3-open-upload-app-return"
                    or not request["body_base64"]
                    or any(name.lower() == "content-length" for name, _ in request["headers"])
                    or not isinstance(followup_path, str)
                    or followup_path != "/h3-open-upload-followup"
                ):
                    raise ParityError(
                        f"{case_id}: post-response upload completion requires the declared streaming HTTP/3 POST and follow-up"
                    )
            if "peer_stop_after_body_complete" in request:
                request_keys.update({
                    "peer_stop_after_body_complete",
                    "same_connection_followup_path",
                })
                followup_path = request.get("same_connection_followup_path")
                content_lengths = [
                    value for name, value in request["headers"]
                    if name.lower() == "content-length"
                ]
                body_length = len(
                    base64.b64decode(request["body_base64"], validate=True)
                )
                if (
                    request["peer_stop_after_body_complete"] is not True
                    or kind != "http3"
                    or operation not in {
                        "http3.disconnect-after-request-body-complete",
                        "http3.disconnect-after-request-body-complete-cancelled-send",
                    }
                    or request["method"] != "POST"
                    or request["path"] != "/h3-disconnect-after-body"
                    or body_length == 0
                    or len(content_lengths) != 1
                    or not content_lengths[0].isdigit()
                    or int(content_lengths[0]) != body_length
                    or not isinstance(followup_path, str)
                    or not followup_path.startswith("/")
                ):
                    raise ParityError(
                        f"{case_id}: post-body peer stop requires the declared complete HTTP/3 POST and same-connection follow-up"
                    )
            elif "same_connection_followup_path" in request:
                if not {
                    "peer_stop_before_response_headers",
                    "peer_stop_after_body_complete",
                    "peer_stop_while_upload_open",
                    "complete_upload_after_response",
                }.intersection(request):
                    raise ParityError(
                        f"{case_id}: same_connection_followup_path requires an HTTP/3 peer-stop workflow"
                    )
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
            if "body_chunks_base64" in request:
                request_keys.add("body_chunks_base64")
                if kind != "http3":
                    raise ParityError(
                        f"{case_id}: explicit request DATA-frame segmentation is supported only for HTTP/3"
                    )
                chunks = request["body_chunks_base64"]
                if not isinstance(chunks, list) or len(chunks) < 2:
                    raise ParityError(
                        f"{case_id}: HTTP/3 body_chunks_base64 requires at least two nonempty chunks"
                    )
                try:
                    decoded_chunks = [base64.b64decode(chunk, validate=True) for chunk in chunks]
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid HTTP/3 body chunk base64") from error
                if any(not chunk for chunk in decoded_chunks):
                    raise ParityError(f"{case_id}: HTTP/3 body chunks must be nonempty")
                if b"".join(decoded_chunks) != base64.b64decode(
                    request["body_base64"], validate=True
                ):
                    raise ParityError(
                        f"{case_id}: HTTP/3 body chunks must concatenate to body_base64"
                    )
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
        elif kind in {
            "websocket", "websocket-tls", "websocket-websockets", "websocket-wsproto"
        }:
            case_keys = {"case_id", "profile", "operation", "covers", "websocket"}
            if "server_options" in case:
                case_keys.add("server_options")
                server_options = case["server_options"]
                if type(server_options) is not dict:
                    raise ParityError(f"{case_id}: server_options must be an object")
                unknown_options = set(server_options) - {
                    "ws_max_size",
                    "ws_max_queue",
                    "ws",
                    "ws_ping_interval",
                    "ws_ping_timeout",
                    "proxy_headers",
                    "forwarded_allow_ips",
                    "root_path",
                }
                if unknown_options:
                    raise ParityError(
                        f"{case_id}: unsupported WebSocket server options: "
                        f"{sorted(unknown_options)!r}"
                    )
                if "ws" in server_options and (
                    not isinstance(server_options["ws"], str)
                    or server_options["ws"]
                    not in {"auto", "none", "websockets", "websockets-sansio", "wsproto"}
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ws must select a Uvicorn WebSocket backend"
                    )
                if "ws_max_size" in server_options and (
                    type(server_options["ws_max_size"]) is not int
                    or server_options["ws_max_size"] < 0
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ws_max_size must be a non-negative integer"
                    )
                if "ws_max_queue" in server_options and (
                    case.get("profile") != "websocket-websockets"
                    or type(server_options["ws_max_queue"]) is not int
                    or server_options["ws_max_queue"] < 0
                ):
                    raise ParityError(
                        f"{case_id}: server_options.ws_max_queue requires the legacy websockets profile and a non-negative integer"
                    )
                for option in ("ws_ping_interval", "ws_ping_timeout"):
                    if option in server_options and (
                        type(server_options[option]) not in {int, float}
                        or not math.isfinite(server_options[option])
                        or server_options[option] <= 0
                    ):
                        raise ParityError(
                            f"{case_id}: server_options.{option} must be a finite positive number"
                        )
                if "proxy_headers" in server_options and type(
                    server_options["proxy_headers"]
                ) is not bool:
                    raise ParityError(
                        f"{case_id}: server_options.proxy_headers must be a boolean"
                    )
                if "forwarded_allow_ips" in server_options and not isinstance(
                    server_options["forwarded_allow_ips"], str
                ):
                    raise ParityError(
                        f"{case_id}: server_options.forwarded_allow_ips must be a string"
                    )
                if "root_path" in server_options and not isinstance(
                    server_options["root_path"], str
                ):
                    raise ParityError(
                        f"{case_id}: server_options.root_path must be a string"
                    )
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
            if case["operation"] in {
                "websocket.raw-frame-disconnect",
                "websocket.fragmented-message-reassembly",
                "websocket.fragmented-compressed-message-reassembly",
                "websocket.raw-size-limit-close",
                "websocket.raw-size-limit-close-uncompressed",
            }:
                websocket_keys.add("raw_frame_base64")
                if (
                    case["profile"] != "websocket"
                    or websocket.get("messages") != []
                    or not isinstance(websocket.get("followup_path"), str)
                ):
                    raise ParityError(
                        f"{case_id}: raw WebSocket frames require a plain WebSocket profile, "
                        "no high-level messages, and a follow-up path"
                    )
                try:
                    raw_frame = base64.b64decode(websocket["raw_frame_base64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ParityError(f"{case_id}: invalid raw WebSocket frame base64") from error
                if not raw_frame:
                    raise ParityError(f"{case_id}: raw WebSocket frame must not be empty")
            elif "raw_frame_base64" in websocket:
                raise ParityError(
                    f"{case_id}: raw_frame_base64 requires a raw WebSocket frame operation"
                )
            if case.get("operation") == "websocket.concurrent-session-load":
                if websocket.get("path") != "/ws/load" or websocket.get("messages") != []:
                    raise ParityError(
                        f"{case_id}: concurrent WebSocket sessions require the load echo workflow"
                    )
            if case.get("operation") == "websocket.server-keepalive":
                if (
                    case.get("profile") != "websocket"
                    or websocket.get("path") != "/ws"
                    or websocket.get("messages") != []
                    or not {"ws_ping_interval", "ws_ping_timeout"}.issubset(
                        case.get("server_options", {})
                    )
                ):
                    raise ParityError(
                        f"{case_id}: server keepalive requires the /ws idle-session workflow "
                        "and explicit ping interval and timeout settings"
                    )
            if case.get("operation") == "websocket.server-keepalive-mismatched-pong":
                if (
                    case.get("profile") != "websocket"
                    or websocket.get("path") != "/ws"
                    or websocket.get("messages") != []
                    or not {"ws_ping_interval", "ws_ping_timeout"}.issubset(
                        case.get("server_options", {})
                    )
                    or "second_pong_payload_base64" not in websocket
                ):
                    raise ParityError(
                        f"{case_id}: mismatched-Pong coverage requires the /ws idle-session workflow, "
                        "explicit keepalive settings, and a second Pong payload"
                    )
                websocket_keys.add("second_pong_payload_base64")
                try:
                    second_pong_payload = base64.b64decode(
                        websocket["second_pong_payload_base64"], validate=True
                    )
                except (ValueError, TypeError) as error:
                    raise ParityError(
                        f"{case_id}: second_pong_payload_base64 must be valid base64"
                    ) from error
                if not 1 <= len(second_pong_payload) <= 125 or len(second_pong_payload) == 4:
                    raise ParityError(
                        f"{case_id}: second Pong must be a control-frame payload whose length differs from the four-byte server Ping"
                    )
            elif "second_pong_payload_base64" in websocket:
                raise ParityError(
                    f"{case_id}: second_pong_payload_base64 requires the mismatched-Pong operation"
                )
            if case.get("operation") == "websocket.server-keepalive-unsolicited-pong":
                if (
                    case.get("profile") != "websocket"
                    or websocket.get("path") != "/ws"
                    or websocket.get("messages") != []
                    or not {"ws_ping_interval", "ws_ping_timeout"}.issubset(
                        case.get("server_options", {})
                    )
                    or "unsolicited_pong_payload_base64" not in websocket
                ):
                    raise ParityError(
                        f"{case_id}: unsolicited-Pong coverage requires the /ws idle-session workflow, "
                        "explicit keepalive settings, and a Pong payload"
                    )
                websocket_keys.add("unsolicited_pong_payload_base64")
                try:
                    unsolicited_pong_payload = base64.b64decode(
                        websocket["unsolicited_pong_payload_base64"], validate=True
                    )
                except (ValueError, TypeError) as error:
                    raise ParityError(
                        f"{case_id}: unsolicited_pong_payload_base64 must be valid base64"
                    ) from error
                if not 1 <= len(unsolicited_pong_payload) <= 125:
                    raise ParityError(
                        f"{case_id}: unsolicited Pong payload must fit a control frame"
                    )
            elif "unsolicited_pong_payload_base64" in websocket:
                raise ParityError(
                    f"{case_id}: unsolicited_pong_payload_base64 requires the unsolicited-Pong operation"
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
            if "disable_compression" in websocket:
                websocket_keys.add("disable_compression")
                if websocket["disable_compression"] is not True:
                    raise ParityError(f"{case_id}: disable_compression must be true when present")
            if "followup_path" in websocket:
                websocket_keys.add("followup_path")
                if not isinstance(websocket["followup_path"], str) or not websocket["followup_path"].startswith("/"):
                    raise ParityError(f"{case_id}: WebSocket followup_path must be origin-form")
            if "wait_for_app_event" in websocket:
                websocket_keys.add("wait_for_app_event")
                fault = case.get("fault", {})
                if (
                    not isinstance(websocket["wait_for_app_event"], str)
                    or not websocket["wait_for_app_event"]
                    or case.get("profile") != "websocket"
                    or not (
                        (
                            case.get("operation") == "websocket.final-frame-drain"
                            and websocket.get("expect_close") is True
                            and websocket.get("messages") == []
                        )
                        or (
                            case.get("operation") == "websocket.registration-failure-cleanup"
                            and fault.get("contract")
                            == "websocket-registration-failure-cancels-app-followup-200"
                        )
                        or (
                            case.get("operation") == "websocket.abrupt-disconnect"
                            and websocket.get("abrupt_disconnect") is True
                        )
                    )
                ):
                    raise ParityError(
                        f"{case_id}: deferred WebSocket event waits require a supported workflow"
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
            if "shutdown_signal" in case["lifecycle"]:
                lifecycle_keys.add("shutdown_signal")
                if (
                    case["lifecycle"]["shutdown_signal"] not in {"SIGINT", "SIGTERM"}
                    or case["profile"] != "lifecycle"
                    or case["operation"] != "lifespan.shutdown-cancellation"
                    or case["lifecycle"].get("state_path") != "/state"
                    or case["lifecycle"].get("hold_path") != "/hold"
                ):
                    raise ParityError(
                        f"{case_id}: CLI signal shutdown requires the held HTTP/1.1 lifespan cancellation workflow"
                    )
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
                    case["profile"] != "lifecycle"
                    or case["operation"] != "lifespan.active-stream-graceful-drain"
                ):
                    raise ParityError(
                        f"{case_id}: idle transport prefix requires the HTTP/1.1 graceful-drain workflow"
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
                    case["profile"] != "lifecycle"
                    or case["lifecycle"].get("stream_path") != "/stream-shutdown-hold"
                    or "hold_path" in case["lifecycle"]
                    or "keep_alive_state_connection" in case["lifecycle"]
                    or "reset_connection_after_shutdown" in case["lifecycle"]
                    or "idle_transport_prefix_base64" not in case["lifecycle"]
                ):
                    raise ParityError(
                        f"{case_id}: active-stream graceful drain requires the dedicated held-stream workflow"
                    )
            elif case["operation"] == "lifespan.active-stream-tls-graceful-drain":
                if (
                    case["profile"] != "lifecycle-tls"
                    or case["lifecycle"].get("stream_path") != "/stream-shutdown-hold"
                    or "hold_path" in case["lifecycle"]
                    or "keep_alive_state_connection" in case["lifecycle"]
                    or "reset_connection_after_shutdown" in case["lifecycle"]
                    or "idle_transport_prefix_base64" in case["lifecycle"]
                ):
                    raise ParityError(
                        f"{case_id}: TLS active-stream graceful drain must isolate the held TLS stream"
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
                    != "server-native-connection-error-during-shutdown"
                ):
                    raise ParityError(
                    f"{case_id}: native connection error requires a fault-contract held-stream workflow"
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
            case_keys = {"case_id", "profile", "operation", "covers", "startup_failure"}
            if "server_options" in case:
                case_keys.add("server_options")
                server_options = case["server_options"]
                if (
                    type(server_options) is not dict
                    or not set(server_options) <= {"inherited_fd", "host"}
                    or (
                        "inherited_fd" in server_options
                        and type(server_options["inherited_fd"]) is not bool
                    )
                    or (
                        "host" in server_options
                        and (
                            not isinstance(server_options["host"], str)
                            or server_options["host"] not in {"127.0.0.1", "::1"}
                        )
                    )
                ):
                    raise ParityError(
                        f"{case_id}: startup-failure server options only support a boolean inherited_fd and a loopback host"
                    )
            exact_case_keys(case, case_keys, case_id)
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
    requirements = []
    platform_id = current_platform_id()
    for oracle in manifest["oracles"]:
        requirements.append((oracle["id"], oracle["version"]))
        requirements.extend(
            (component["id"], component["version"])
            for component in oracle["components"]
            if "platforms" not in component or platform_id in component["platforms"]
        )
    oracle_uvicorn = None
    if any(oracle["id"] == "uvicorn" for oracle in manifest["oracles"]):
        probe = subprocess.run(
            [
                str(ORACLE_PYTHON),
                "-c",
                "import importlib.metadata, json, uvicorn; "
                "print(json.dumps({'distribution': importlib.metadata.version('uvicorn'), "
                "'module': uvicorn.__version__, 'path': uvicorn.__file__}))",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if probe.returncode != 0:
            raise ParityError(
                "could not import the Uvicorn oracle from "
                f"{ORACLE_PYTHON}: {probe.stderr[-1000:]}"
            )
        try:
            oracle_uvicorn = json.loads(probe.stdout)
        except json.JSONDecodeError as error:
            raise ParityError("Uvicorn oracle identity probe returned invalid JSON") from error
        if (
            not isinstance(oracle_uvicorn, dict)
            or oracle_uvicorn.get("distribution") != "0.54.0"
            or oracle_uvicorn.get("module") != "0.54.0"
        ):
            details = json.dumps(oracle_uvicorn, sort_keys=True)
            raise ParityError(
                "the oracle interpreter does not import genuine Uvicorn 0.54.0; "
                "pass --oracle-python for an environment without the uvicorn-rs distribution: "
                f"{details}"
            )
    requirement_names = sorted({distribution for distribution, _ in requirements})
    dependency_probe = subprocess.run(
        [
            str(ORACLE_PYTHON),
            "-c",
            "import importlib.metadata, json, sys\n"
            "versions = {}\n"
            "missing = []\n"
            "for name in json.loads(sys.argv[1]):\n"
            "    try:\n"
            "        versions[name] = importlib.metadata.version(name)\n"
            "    except importlib.metadata.PackageNotFoundError:\n"
            "        missing.append(name)\n"
            "print(json.dumps({'versions': versions, 'missing': missing}, sort_keys=True))",
            json.dumps(requirement_names),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if dependency_probe.returncode != 0:
        raise ParityError(
            f"could not inspect reference dependencies from {ORACLE_PYTHON}: "
            f"{dependency_probe.stderr[-1000:]}"
        )
    try:
        oracle_dependencies = json.loads(dependency_probe.stdout)
    except json.JSONDecodeError as error:
        raise ParityError("reference dependency probe returned invalid JSON") from error
    if not isinstance(oracle_dependencies, dict):
        raise ParityError("reference dependency probe returned an invalid result")
    missing_dependencies = oracle_dependencies.get("missing")
    dependency_versions = oracle_dependencies.get("versions")
    if not isinstance(missing_dependencies, list) or not isinstance(dependency_versions, dict):
        raise ParityError("reference dependency probe returned an invalid result")
    if missing_dependencies:
        raise ParityError(
            f"required reference dependencies are missing from {ORACLE_PYTHON}: "
            f"{', '.join(missing_dependencies)}"
        )
    for distribution, required in requirements:
        observed = dependency_versions.get(distribution)
        if not isinstance(observed, str):
            raise ParityError(
                f"reference dependency probe omitted {distribution} from {ORACLE_PYTHON}"
            )
        if observed != required:
            raise ParityError(f"{distribution} version mismatch: expected {required}, found {observed}")
        actual[distribution] = observed
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
    rustc = subprocess.run(["rustc", "--version"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    package = importlib.import_module("uvicorn_rs")
    if INSTALLED_CANDIDATE_MODE:
        checkout_adapter = (ROOT / "python" / "uvicorn_rs").resolve()
        package_path = Path(package.__file__).resolve()
        if package_path.is_relative_to(checkout_adapter):
            raise ParityError(
                "installed-candidate mode resolved uvicorn_rs from the checkout "
                f"instead of the installed wheel: {package_path}"
            )
    native_extension = Path(importlib.import_module("uvicorn_rs._native").__file__).resolve()
    try:
        native_extension_path = str(native_extension.relative_to(ROOT))
    except ValueError:
        native_extension_path = str(native_extension)
    source_files = runtime_source_hashes(ROOT)
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
            "source_files": source_files,
            "source_sha256": runtime_source_digest(source_files),
        },
    )


def current_platform_id() -> str:
    return parity_platform_id(platform.system())


def parity_platform_id(platform_name: str) -> str:
    normalized = platform_name.lower()
    if normalized.startswith(("windows", "win32")):
        return "windows"
    if normalized.startswith(("macos", "darwin")):
        return "macos"
    if normalized.startswith("linux"):
        return "linux"
    raise ParityError(f"unsupported parity platform: {platform_name}")


def default_event_loop() -> str:
    return "asyncio" if current_platform_id() == "windows" else "uvloop"


def free_port(*, tcp_and_udp: bool = False) -> int:
    last_error: OSError | None = None
    for _ in range(512):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            try:
                tcp.bind(("127.0.0.1", 0))
                port = tcp.getsockname()[1]
                if tcp_and_udp:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                        udp.bind(("127.0.0.1", port))
                return port
            except OSError as error:
                last_error = error
                continue
    raise OSError(
        f"could not find an available test port after 512 attempts: {last_error}"
    )


def make_certificate(directory: Path) -> tuple[Path, Path, Path]:
    leaf_certificate = directory / "server-leaf.pem"
    certificate = directory / "server-chain.pem"
    key = directory / "server-key.pem"
    ca_certificate = directory / "parity-ca.pem"
    ca_key_path = directory / "parity-ca-key.pem"
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "uvicorn-rs parity test CA")]
    )
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    not_before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    not_after = not_before + timedelta(days=2)
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    server = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca.public_bytes(serialization.Encoding.PEM)
    leaf_pem = server.public_bytes(serialization.Encoding.PEM)
    ca_key_path.write_bytes(
        ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    ca_certificate.write_bytes(ca_pem)
    leaf_certificate.write_bytes(leaf_pem)
    certificate.write_bytes(leaf_pem + ca_pem)
    return certificate, key, ca_certificate


def make_client_certificate(directory: Path) -> tuple[Path, Path]:
    """Create a short-lived client identity signed by the parity TLS CA."""
    ca_certificate = directory / "parity-ca.pem"
    ca_key_path = directory / "parity-ca-key.pem"
    client_certificate = directory / "client-leaf.pem"
    client_key = directory / "client-key.pem"
    ca = x509.load_pem_x509_certificate(ca_certificate.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
    client_signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "uvicorn-rs parity client")]
    )
    not_before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    not_after = not_before + timedelta(days=2)
    client = (
        x509.CertificateBuilder()
        .subject_name(client_name)
        .issuer_name(ca.subject)
        .public_key(client_signing_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(client_signing_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    client_certificate.write_bytes(client.public_bytes(serialization.Encoding.PEM))
    client_key.write_bytes(
        client_signing_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return client_certificate, client_key


def h3_client_executable_path(*, windows: bool | None = None) -> Path:
    is_windows = os.name == "nt" if windows is None else windows
    executable = "parity-http3.exe" if is_windows else "parity-http3"
    return ROOT / "target" / "release" / executable


def build_h3_client() -> Path:
    subprocess.run(
        [
            "cargo", "build", "--quiet", "--release", "--manifest-path",
            "tools/http3-probe/Cargo.toml", "--bin", "parity-http3", "--locked",
        ],
        cwd=ROOT,
        check=True,
        timeout=300,
    )
    return h3_client_executable_path()


def prebuilt_h3_client() -> Path:
    client = h3_client_executable_path()
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
    server_options: dict[str, Any] | None = None,
    trust_anchor: Path | None = None,
    client_certificate: Path | None = None,
    client_key: Path | None = None,
) -> dict[str, Any]:
    profile_id = profile["id"]
    websocket_selector = (server_options or {}).get("ws") or {
        "websocket-websockets": "websockets",
        "websocket-wsproto": "wsproto",
    }.get(profile_id, "auto")
    env = os.environ.copy()
    if server_id == "uvicorn":
        # Coverage runs add the project Python source to PYTHONPATH so the
        # instrumented target is importable. Keep that path out of the stock
        # Uvicorn reference process so it cannot shadow the isolated oracle.
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
            env.pop(name, None)
        env["PYTHONNOUSERSITE"] = "1"
    elif server_id == "uvicorn-rs":
        if INSTALLED_CANDIDATE_MODE:
            for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
                env.pop(name, None)
            env["PYTHONNOUSERSITE"] = "1"
        else:
            # The compatibility namespace lives under python/ and can be
            # shadowed by the stock Uvicorn wheel in a shared developer
            # environment. Source parity loads the adapter beside the native
            # extension built into the checkout.
            source_python_path = str(ROOT / "python")
            env["PYTHONPATH"] = os.pathsep.join(
                path for path in (source_python_path, env.get("PYTHONPATH")) if path
            )
    # Shutdown workflows restart a profile in the same temporary directory.
    # Readiness and request checkpoints must belong to the new process.
    events_path.write_text("", encoding="utf-8")
    env["ASGI_PARITY_EVENTS"] = str(events_path)
    stream_release_path = events_path.with_suffix(".stream-release")
    stream_release_path.unlink(missing_ok=True)
    env["ASGI_PARITY_STREAM_RELEASE"] = str(stream_release_path)
    disconnect_release_path = events_path.with_suffix(".disconnect-release")
    disconnect_release_path.unlink(missing_ok=True)
    env["ASGI_PARITY_DISCONNECT_RELEASE"] = str(disconnect_release_path)
    if profile_id == "websocket-tls":
        env["ASGI_PARITY_TRACE_WEBSOCKET_SCOPE"] = "1"
    if server_id == "uvicorn-rs" and coverage_profile_dir is not None:
        coverage_profile_dir.mkdir(parents=True, exist_ok=True)
        env["LLVM_PROFILE_FILE"] = str(coverage_profile_dir / "%p-%m.profraw")
    coverage_capture_shutdown = (
        os.environ.get("ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN") == "1"
    )
    coverage_site = str(ROOT / "tests" / "parity" / "coverage_site")
    if coverage_capture_shutdown:
        env["ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN"] = "1"
        env["PYTHONPATH"] = os.pathsep.join(
            path for path in (coverage_site, env.get("PYTHONPATH")) if path
        )
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
    common = [
        "--host",
        str((server_options or {}).get("host", "127.0.0.1")),
        "--port",
        str(port),
    ]
    inherited_listener = None
    inherited_listener_fds: tuple[int, ...] = ()
    if (server_options or {}).get("inherited_fd"):
        inherited_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        inherited_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        inherited_listener.set_inheritable(True)
        inherited_listener.bind(("127.0.0.1", port))
        inherited_listener.listen()
        inherited_listener_fds = (inherited_listener.fileno(),)
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
        "startup-encrypted-private-key-wrong-password",
        "startup-encrypted-private-key-invalid-utf8",
        "startup-encrypted-private-key-malformed-pem",
        "startup-encrypted-private-key-wrong-label",
        "startup-encrypted-private-key-invalid-der",
        "startup-traditional-encrypted-private-key-unsupported-cipher",
        "startup-traditional-encrypted-private-key-missing-dek-info",
        "startup-traditional-encrypted-private-key-invalid-dek-info",
        "startup-traditional-encrypted-private-key-invalid-proc-type",
        "startup-traditional-encrypted-private-key-missing-body",
        "startup-traditional-encrypted-private-key-invalid-body-base64",
        "startup-traditional-encrypted-private-key-missing-end-marker",
        "startup-traditional-unencrypted-private-key-invalid-base64",
    }
    if profile_id in startup_api_profiles:
        server_python = str(ORACLE_PYTHON) if server_id == "uvicorn" else sys.executable
        command = [
            server_python,
            str(ROOT / "tests/parity/startup_probe.py"),
            server_id,
            profile_id,
            str(certificate or ""),
            str(key or ""),
        ]
    elif profile_id in {
        "lifecycle-owned-loop",
        "lifecycle-owned-loop-eager",
        "lifecycle-server-api",
    }:
        server_python = str(ORACLE_PYTHON) if server_id == "uvicorn" else sys.executable
        api_control_path = events_path.with_suffix(".shutdown")
        api_control_path.unlink(missing_ok=True)
        command = [
            server_python,
            str(ROOT / "tests/parity/server_api_probe.py"),
            str(port),
            str(graceful_timeout_seconds),
            str(api_control_path),
        ]
        if profile_id == "lifecycle-server-api":
            command.extend(
                ["--server", "uvicorn" if server_id == "uvicorn" else "uvicorn-rs"]
            )
            if server_id == "uvicorn-rs":
                # Use Server.should_exit on both sides for this lifecycle case;
                # task-cancellation behavior has separate programmatic cases.
                command.append("--uvicorn-compat-api")
        if profile_id in {"lifecycle-owned-loop", "lifecycle-owned-loop-eager"}:
            api_snapshot_path = events_path.with_suffix(".server-api-snapshot.json")
            api_snapshot_path.unlink(missing_ok=True)
            command.extend(["--server", server_id, "--snapshot", str(api_snapshot_path)])
            if profile_id == "lifecycle-owned-loop-eager":
                command.extend(["--task-factory", "eager", "--cleanup-delay", str(async_cleanup_delay_seconds)])
    elif server_id == "uvicorn-rs":
        # Exercise the public replacement command in parity runs. Using
        # ``uvicorn_rs`` here would bypass the uvicorn namespace and could let
        # its CLI/import compatibility drift independently of server parity.
        # Match the stock oracle's explicit ASGI3 selection. The shared
        # parity app is a synchronous callable that returns an awaitable, so
        # `auto` would classify it as ASGI2 and test interface detection
        # instead of the protocol/lifecycle behavior under comparison.
        command = [
            sys.executable, "-m", "uvicorn", APP, *common,
            "--loop", default_event_loop(), "--interface", "asgi3", "--ws", websocket_selector,
        ]
        if profile_id == "startup-fault-lifespan-send-closed-on":
            command.extend(["--lifespan", "on"])
        if profile_id == "http2":
            command.extend(["--http", "zttp", "--http2"])
        if certificate and key:
            command.extend(["--ssl-certfile", str(certificate), "--ssl-keyfile", str(key)])
        command.extend(["--timeout-graceful-shutdown", str(graceful_timeout_seconds)])
    elif server_id == "uvicorn":
        server_python = str(ORACLE_PYTHON)
        http_implementation = (server_options or {}).get(
            "http", "zttp" if profile_id == "http2" else "httptools"
        )
        # Keep TLS WebSocket handshake progress in hosted diagnostics when the
        # reference adapter stalls before ASGI dispatch.
        websocket_tls_debug = (
            profile_id == "websocket-tls"
            and env.get("ASGI_PARITY_UVICORN_WEBSOCKET_DEBUG") == "1"
        )
        command = [
            server_python, "-m", "uvicorn", APP, *common, "--loop", default_event_loop(),
            # The default profile follows Uvicorn's maintained auto/SansIO
            # path; the wsproto profile selects its pinned backend explicitly.
            "--http", http_implementation, "--interface", "asgi3", "--ws", websocket_selector,
            "--lifespan", "auto",
            "--log-level", "debug" if websocket_tls_debug else "error",
            "--timeout-graceful-shutdown",
            str(graceful_timeout_seconds),
        ]
        if profile_id == "http2":
            command.append("--http2")
        if certificate and key:
            command.extend(["--ssl-certfile", str(certificate), "--ssl-keyfile", str(key)])
    elif server_id == "hypercorn":
        command = [
            sys.executable, "-m", "hypercorn", f"asgi:{APP}", "--bind", f"127.0.0.1:{port}",
            "--worker-class", default_event_loop(), "--log-level",
            "error" if observe_connection_errors else "critical", "--access-logfile", os.devnull,
            "--certfile", str(certificate), "--keyfile", str(key), "--config", str(config_path),
        ]
        if profile_id == "http3":
            command.extend(["--quic-bind", f"127.0.0.1:{port}"])
            if TRACE_HYPERCORN_H3_EVENTS:
                command = [
                    sys.executable,
                    str(ROOT / "scripts" / "trace_hypercorn_h3.py"),
                    *command[3:],
                ]
    else:
        raise ParityError(f"unknown server adapter: {server_id}")

    if server_options:
        if server_id not in {"uvicorn", "uvicorn-rs"}:
            raise ParityError(
                f"server options are not supported by the {server_id} parity adapter"
            )
        if server_options.get("inherited_fd"):
            command.extend(["--fd", str(inherited_listener_fds[0])])
        if "root_path" in server_options:
            command.extend(["--root-path", server_options["root_path"]])
        if "http" in server_options and server_id == "uvicorn-rs":
            command.extend(["--http", server_options["http"]])
        if "h11_max_incomplete_event_size" in server_options:
            command.extend(
                [
                    "--h11-max-incomplete-event-size",
                    str(server_options["h11_max_incomplete_event_size"]),
                ]
            )
        if "ws_max_size" in server_options:
            command.extend(["--ws-max-size", str(server_options["ws_max_size"])])
        if "ws_max_queue" in server_options:
            command.extend(["--ws-max-queue", str(server_options["ws_max_queue"])])
        if "ws_ping_interval" in server_options:
            command.extend(
                ["--ws-ping-interval", str(server_options["ws_ping_interval"])]
            )
        if "ws_ping_timeout" in server_options:
            command.extend(
                ["--ws-ping-timeout", str(server_options["ws_ping_timeout"])]
            )
        for option in ("server_header", "date_header"):
            if option in server_options:
                flag = option.replace("_", "-")
                command.append(f"--{flag}" if server_options[option] else f"--no-{flag}")
        for header in server_options.get("headers", []):
            command.extend(["--header", header])
        if "proxy_headers" in server_options:
            command.append(
                "--proxy-headers"
                if server_options["proxy_headers"]
                else "--no-proxy-headers"
            )
        if "forwarded_allow_ips" in server_options:
            # Click expands bare wildcards on Windows. Keep the wildcard
            # inside the option token so "*" remains Uvicorn's trust value.
            command.append(
                f"--forwarded-allow-ips={server_options['forwarded_allow_ips']}"
            )
        if "ssl_cert_reqs" in server_options:
            command.extend(["--ssl-cert-reqs", str(server_options["ssl_cert_reqs"])])
        if "ssl_version" in server_options:
            command.extend(["--ssl-version", str(server_options["ssl_version"])])
        if "ssl_ciphers" in server_options:
            command.extend(["--ssl-ciphers", server_options["ssl_ciphers"]])
        if "ssl_ca_certs" in server_options:
            if server_options["ssl_ca_certs"] != "generated-ca" or trust_anchor is None:
                raise ParityError("TLS CA option requires the generated parity CA")
            command.extend(["--ssl-ca-certs", str(trust_anchor)])
        if "limit_concurrency" in server_options:
            command.extend(
                ["--limit-concurrency", str(server_options["limit_concurrency"])]
            )
        if server_options.get("reset_contextvars"):
            command.append("--reset-contextvars")

    log_fd, log_path = tempfile.mkstemp(
        prefix=f"uvicorn-rs-{server_id}-",
        suffix=".log",
        dir=events_path.parent,
    )
    os.close(log_fd)
    log = open(log_path, "w+t", encoding="utf-8")
    process_options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {}
    )
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            text=True,
            pass_fds=inherited_listener_fds,
            **process_options,
        )
    finally:
        if inherited_listener is not None:
            inherited_listener.close()
    if expect_startup_failure:
        # Startup failure probes launch Python in separate processes; allow
        # headroom for slower CI hosts before classifying a still-running
        # process as a server behavior mismatch. The inherited-listener bridge
        # retries its Unix control-socket connection for five seconds when the
        # native receiver fails before binding that socket, so give that path
        # time to report the startup error through the CLI process.
        startup_failure_timeout = (
            10 if (server_options or {}).get("inherited_fd") else 5
        )
        deadline = time.monotonic() + startup_failure_timeout
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
    # Empty-root client-auth inputs reject every client certificate, so an
    # HTTPS readiness request cannot succeed for those cases. They use the
    # listener probe below after ASGI startup has completed.
    use_tls_readiness = profile_id in {"websocket-tls", "lifecycle-tls"} or (
        profile_id == "http1-tls"
        and client_certificate is not None
        and (server_options or {}).get("ssl_ca_certs") == "generated-ca"
    ) or (
        profile_id == "http3" and observe_connection_errors
    )
    if use_tls_readiness:
        readiness_tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        readiness_tls_context.check_hostname = False
        readiness_tls_context.verify_mode = ssl.CERT_NONE
        if client_certificate is not None and client_key is not None:
            readiness_tls_context.load_cert_chain(
                certfile=str(client_certificate), keyfile=str(client_key)
            )
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
            if client_certificate is not None and client_key is not None:
                server["client_certificate"] = client_certificate
                server["client_key"] = client_key
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
                if client_certificate is not None and client_key is not None:
                    server["client_certificate"] = client_certificate
                    server["client_key"] = client_key
                return server
        except OSError:
            time.sleep(0.05)
    stop_server({"process": process, "log": log})
    raise ParityError(f"{server_id}/{profile_id} did not open its TCP listener")


def stop_server(
    server: dict[str, Any], *, graceful: bool = False, signal_sent: bool = False,
    signal_number: int | None = None,
) -> tuple[int | None, str]:
    process: subprocess.Popen = server["process"]
    log = server["log"]
    # Hypercorn 0.18's asyncio worker handles SIGBREAK as a graceful shutdown
    # request. On Windows, terminating it directly may leave its H3 log locked
    # while the QUIC server tasks are being torn down.
    windows_hypercorn_cleanup = (
        os.name == "nt"
        and server.get("id") == "hypercorn"
        and signal_number is None
        and not signal_sent
    )
    graceful_cleanup = graceful or windows_hypercorn_cleanup
    server.setdefault("forced_kill", False)
    if log.closed:
        log_path = getattr(log, "name", None)
        if isinstance(log_path, (str, os.PathLike)):
            cleanup_error = unlink_server_log(Path(log_path))
            server["process_exit_code"] = process.returncode
            server["process_alive_after_stop"] = process.poll() is None
            if cleanup_error is None:
                server.pop("log_cleanup_error", None)
            else:
                server["log_cleanup_error"] = cleanup_error
        return process.returncode, server.get("captured_log", "")[-6000:]
    if process.poll() is None:
        server["harness_stop_requested"] = True
        if graceful_cleanup or signal_number is not None:
            server["graceful_signal_requested"] = True
        api_control_path = server.get("api_control_path")
        if api_control_path is not None:
            api_control_path.touch()
        elif not signal_sent:
            if signal_number is not None:
                if os.name == "nt" and signal_number in {
                    signal.SIGINT,
                    signal.SIGTERM,
                }:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.send_signal(signal_number)
            elif graceful_cleanup:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
            else:
                process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            server["forced_kill"] = True
            process.kill()
            process.wait(timeout=3)
    log.seek(0)
    text = log.read()
    log.close()
    # Preserve diagnostics even if Windows still has a short-lived reader or
    # subprocess handle when the profile tries to remove its temporary logs.
    server["captured_log"] = text
    server["process_exit_code"] = process.returncode
    server["process_alive_after_stop"] = process.poll() is None
    log_path = getattr(log, "name", None)
    if isinstance(log_path, (str, os.PathLike)):
        cleanup_error = unlink_server_log(Path(log_path))
        if cleanup_error is None:
            server.pop("log_cleanup_error", None)
        else:
            server["log_cleanup_error"] = cleanup_error
    # Lifecycle adapters can stop a process before profile finalization, and
    # profiles can restart several processes. Preserve the complete log so
    # validation cannot lose a panic when a handle is closed or a tail grows.
    return process.returncode, text[-6000:]


def unlink_server_log(path: Path) -> str | None:
    """Remove a closed server log, retrying transient Windows sharing locks."""
    for attempt in range(8):
        try:
            path.unlink(missing_ok=True)
            return None
        except OSError as error:
            # Windows can report ERROR_SHARING_VIOLATION briefly after the
            # server process exits. A bounded retry handles that race without
            # hiding a persistent cleanup failure from the parity result.
            if os.name != "nt" or getattr(error, "winerror", None) != 32:
                raise
            if attempt == 7:
                return str(error)
            time.sleep(0.05 * (2**attempt))


@contextmanager
def profile_temporary_directory(
    prefix: str,
    cleanup_errors: list[dict[str, Any]],
    profile_id: str,
) -> Iterator[str]:
    """Keep Windows temp cleanup failures in the parity receipt."""
    temporary = tempfile.TemporaryDirectory(prefix=prefix)
    try:
        yield temporary.name
    finally:
        try:
            temporary.cleanup()
        except OSError as error:
            if os.name != "nt":
                raise
            cleanup_errors.append({
                "profile": profile_id,
                "server": None,
                "kind": "profile_tempdir_cleanup_failure",
                "diagnostic": str(error)[-1000:],
            })


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


def wait_for_listener_closed(
    server: dict[str, Any],
    timeout: float,
    *,
    tls_context: ssl.SSLContext | None = None,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server["process"].poll() is not None:
            return False
        if tls_context is not None:
            connection = http.client.HTTPSConnection(
                "127.0.0.1",
                server["port"],
                timeout=min(0.5, max(0.05, deadline - time.monotonic())),
                context=tls_context,
            )
            try:
                # A raw TCP connect followed by close is an invalid TLS
                # handshake. If accepted during shutdown, it can itself
                # generate a connection-task error that this case rejects.
                # Use a harmless, complete HTTPS request so the probe uses a
                # valid TLS connection and closes its response cleanly.
                connection.request(
                    "GET",
                    "/__parity-readiness",
                    headers={"Connection": "close"},
                )
                response = connection.getresponse()
                response.read()
            except ConnectionRefusedError:
                return True
            except (
                http.client.HTTPException,
                ConnectionError,
                TimeoutError,
                ssl.SSLError,
            ):
                pass
            except OSError as error:
                # On macOS, TLS teardown racing listener shutdown can surface
                # as bare EINVAL instead of an SSLError. Retry until refusal.
                if error.errno != errno.EINVAL:
                    raise ParityError(
                        f"TLS listener probe failed unexpectedly: {error}"
                    ) from error
            finally:
                try:
                    connection.close()
                except OSError as error:
                    if error.errno != errno.EINVAL:
                        raise
            time.sleep(0.01)
            continue
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
    log.flush()
    size = os.fstat(log.fileno()).st_size
    if hasattr(os, "pread"):
        # Popen's inherited descriptor shares its write offset with this
        # handle. pread leaves the child's append position intact.
        return os.pread(log.fileno(), size, 0).decode("utf-8", errors="replace")
    # Windows has no os.pread. Reopen the named temporary log so this reader
    # uses an independent file position while the server continues writing.
    log_path = getattr(log, "name", None)
    if not isinstance(log_path, (str, os.PathLike)):
        raise ParityError("server log has no independent readable path")
    with open(log_path, "r", encoding="utf-8", errors="replace") as reader:
        return reader.read()


def format_adapter_exception(error: Exception) -> str:
    """Retain the Python call site for adapter failures in parity artifacts."""
    return "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )[-8_000:]


def persist_shutdown_trace(case_id: str, server: dict[str, Any], server_log: str) -> None:
    """Keep opt-in Rust/Python shutdown trace lines in focused diagnostic artifacts."""
    trace_output = os.environ.get("UVICORN_RS_SHUTDOWN_TRACE_OUTPUT")
    if not trace_output or server.get("id") != "uvicorn-rs":
        return
    lines = [
        line for line in server_log.splitlines()
        if line.startswith("uvicorn-rs: shutdown-trace ")
    ]
    if not lines:
        return
    trace_path = Path(trace_output)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as trace_file:
        for line in lines:
            trace_file.write(f"{case_id} {line}\n")


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
    server_header_values = [value for name, value in headers if name.lower() == "server"]
    date_header_present = any(name.lower() == "date" for name, _value in headers)
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
        "server_header_values": server_header_values,
        "date_header_present": date_header_present,
        "body_base64": base64.b64encode(body).decode("ascii"),
        "ordered_response_headers": ordered_response_headers,
        "response_header_values_by_name": [
            [name, values] for name, values in sorted(response_header_values_by_name.items())
        ],
        "connection_closed": False,
    }


def http1_request(
    port: int,
    request: dict[str, Any],
    *,
    ssl_context: ssl.SSLContext | None = None,
    observe_tls_version: bool = False,
    observe_tls_cipher: bool = False,
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
        observation = response_observation(response.status, response.getheaders(), payload)
        if observe_tls_version:
            tls_socket = connection.sock
            observation["negotiated_tls_version"] = (
                tls_socket.version() if isinstance(tls_socket, ssl.SSLSocket) else None
            )
        if observe_tls_cipher:
            tls_socket = connection.sock
            cipher = tls_socket.cipher() if isinstance(tls_socket, ssl.SSLSocket) else None
            observation["negotiated_tls_cipher"] = cipher[0] if cipher is not None else None
        return observation
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
    write_error_fault_consumed: bool | None = None
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
            try:
                connection.request(
                    request["method"],
                    request["path"],
                    body=body,
                    headers=dict(request["headers"]),
                )
                response = connection.getresponse()
            except http.client.RemoteDisconnected:
                if (
                    index == 0
                    and fault_control_path is not None
                    and fault_point == "server.connection-io.poll-write-error"
                ):
                    write_error_fault_consumed = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault_point
                    )
                responses.append({
                    "status": None,
                    "content_type": None,
                    "body_base64": "",
                    "connection_closed": True,
                })
                connection.close()
                continue
            except ConnectionResetError:
                if index != 0 or fault_point != "server.tcp-nodelay.set-error":
                    raise
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
                if (
                    index == 0
                    and fault_control_path is not None
                    and fault_point == "server.connection-io.poll-write-error"
                ):
                    write_error_fault_consumed = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault_point
                    )
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
                and fault_point == "server.connection-io.poll-write-error"
            ):
                write_error_fault_consumed = (
                    fault_control_path.read_text(encoding="utf-8").strip()
                    != fault_point
                )
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
        observation = {"responses": responses}
        if write_error_fault_consumed is not None:
            observation["fault_consumed"] = write_error_fault_consumed
        return observation
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


def request_stream_chunks(specification: dict[str, Any]) -> list[bytes]:
    """Decode explicit or compact deterministic chunks from one input case."""
    if "generated_chunks" in specification:
        return [
            bytes([chunk["byte_value"]]) * chunk["size_bytes"]
            for chunk in specification["generated_chunks"]
        ]
    return [base64.b64decode(item, validate=True) for item in specification["chunks_base64"]]


def http1_body_pump_shutdown_workflow(
    server: dict[str, Any], specification: dict[str, Any], fault: dict[str, Any]
) -> dict[str, Any]:
    """Hold an unread request upload in the body-pump drain until shutdown."""
    fault_control_path = server.get("coverage_fault_control_path")
    if fault_control_path is None:
        raise ParityError("body-pump shutdown workflow requires the instrumented target")
    chunks = request_stream_chunks(specification)
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
    port: int,
    specification: dict[str, Any],
    events_path: Path,
    *,
    allow_nonchunked_response: bool = False,
    fault_control_path: Path | None = None,
    fault_point: str | None = None,
) -> dict[str, Any]:
    chunks = request_stream_chunks(specification)
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    client.settimeout(10)
    reader = client.makefile("rb")
    concurrent_upload_sender = None
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
        first_request_chunk = chunks[0]
        send_first_chunk_before_wait_event = specification.get(
            "send_first_chunk_before_wait_event", False
        )
        if send_first_chunk_before_wait_event:
            client.sendall(
                f"{len(first_request_chunk):x}\r\n".encode()
                + first_request_chunk
                + b"\r\n"
            )
        if wait_event is not None:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and wait_event not in read_events(events_path):
                time.sleep(0.005)
            if wait_event not in read_events(events_path):
                raise ParityError(f"ASGI app did not reach request-stream checkpoint {wait_event!r}")
        connection_closed = False
        if not send_first_chunk_before_wait_event:
            client.sendall(
                f"{len(first_request_chunk):x}\r\n".encode()
                + first_request_chunk
                + b"\r\n"
            )

        if specification.get("send_body_concurrently_with_response_read", False):
            upload_errors: list[OSError] = []

            def send_remaining_body() -> None:
                try:
                    for chunk in chunks[1:]:
                        client.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    if specification.get("malformed_final_chunk", False):
                        client.sendall(b"not-a-size\r\n")
                    else:
                        trailer_lines = "".join(
                            f"{name}: {value}\r\n"
                            for name, value in specification.get("trailers", [])
                        )
                        client.sendall(("0\r\n" + trailer_lines + "\r\n").encode("ascii"))
                except OSError as error:
                    upload_errors.append(error)

            concurrent_upload_sender = threading.Thread(
                target=send_remaining_body,
                name="parity-http1-upload",
                daemon=True,
            )
            concurrent_upload_sender.start()

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
            if concurrent_upload_sender is not None:
                concurrent_upload_sender.join(timeout=10)
                if concurrent_upload_sender.is_alive():
                    raise ParityError("concurrent HTTP/1.1 request-body sender did not stop")
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

        is_chunked = any(
            name == "transfer-encoding" and "chunked" in value.lower()
            for name, value in response_headers
        )
        if allow_nonchunked_response and not is_chunked:
            content_length = next(
                (value for name, value in response_headers if name == "content-length"),
                None,
            )
            try:
                response_body = (
                    reader.read(int(content_length))
                    if content_length is not None
                    else reader.read()
                )
            except ConnectionResetError:
                response_body = b""
            if concurrent_upload_sender is not None:
                concurrent_upload_sender.join(timeout=10)
                if concurrent_upload_sender.is_alive():
                    raise ParityError("concurrent HTTP/1.1 request-body sender did not stop")
            result = response_observation(status, response_headers, response_body)
            result["early_body_base64"] = base64.b64encode(response_body).decode("ascii")
            result["connection_closed"] = True
            return result

        early_body = read_http1_chunk(reader)
        if early_body is None:
            raise ParityError("response finished before the request upload was complete")
        if (
            not specification.get("send_all_before_read", False)
            and not specification.get("send_body_concurrently_with_response_read", False)
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
        if concurrent_upload_sender is not None:
            concurrent_upload_sender.join(timeout=10)
            if concurrent_upload_sender.is_alive():
                raise ParityError("concurrent HTTP/1.1 request-body sender did not stop")
            connection_closed = connection_closed or bool(upload_errors)
        if specification.get("send_remaining_after_response", False) and not connection_closed:
            for chunk in chunks[1:]:
                try:
                    client.sendall(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    connection_closed = True
                    break
            if not connection_closed:
                try:
                    client.sendall(b"0\r\n\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    connection_closed = True
        fault_consumed = None
        if fault_point is not None and fault_control_path is not None:
            # Keep the peer open while the server consumes the request-body
            # terminal frame. Closing first races the drain's peer-close guard.
            deadline = time.monotonic() + 3
            while (
                fault_control_path.read_text(encoding="utf-8").strip() == fault_point
                and not connection_closed
                and time.monotonic() < deadline
            ):
                time.sleep(0.005)
            fault_consumed = (
                fault_control_path.read_text(encoding="utf-8").strip() != fault_point
            )
        result = response_observation(status, response_headers, b"".join(response_chunks))
        result["early_body_base64"] = base64.b64encode(early_body).decode("ascii")
        result["connection_closed"] = connection_closed
        if fault_point is not None:
            result["fault_consumed"] = fault_consumed is True
        return result
    finally:
        if concurrent_upload_sender is not None and concurrent_upload_sender.is_alive():
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            concurrent_upload_sender.join(timeout=1)
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
        # Encode a zero-length request body with an empty final DATA frame. The
        # zttp backend requires an END_STREAM DATA event to wake ASGI receive;
        # END_STREAM on the initial HEADERS frame currently leaves its body
        # receive pending until the connection closes.
        connection.send_headers(stream_id, headers, end_stream=False)
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
        elif empty_request:
            connection.send_data(stream_id, b"", end_stream=True)
        else:
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
            events = read_events(events_path)[events_before:]
            raise ParityError(
                "HTTP/2 app did not reach its receive checkpoint before connection close "
                f"(events={events!r})"
            )
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
    followup = http2_request(port, {
        "method": "GET", "path": specification["followup_path"], "headers": [], "body_base64": "",
    })
    observation = {
        "disconnect_event": "http.disconnect" in events,
        "followup": followup,
        "application_events": events,
    }
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
        if os.name == "nt" and getattr(error, "winerror", None) in {10053, 10054}:
            # Windows may report an aborted/reset TLS transport while the
            # client closes after every HTTP/2 response stream has completed.
            # Response integrity and resource assertions have already passed.
            return None
        return f"{type(error).__name__}: {error}"
    else:
        raw_socket.close()
        return None


def http2_request(
    port: int,
    request: dict[str, Any],
    *,
    observe_response_extensions: bool = False,
    events_path: Path | None = None,
    expected_application_events: list[str] | None = None,
) -> dict[str, Any]:
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
    events_before = len(read_events(events_path)) if events_path is not None else 0
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
    early_hints: list[dict[str, Any]] = []
    early_hint_before_final_start = False
    response_trailers: list[list[str]] = []

    def observation() -> dict[str, Any]:
        result = response_observation(status, response_headers, bytes(response_body))
        if observe_response_extensions:
            result.update({
                "early_hints": early_hints,
                "early_hint_before_final_start": early_hint_before_final_start,
                "response_trailers": response_trailers,
            })
        if events_path is not None:
            application_events = read_events(events_path)[events_before:]
            if expected_application_events:
                expected_events = set(expected_application_events)
                deadline = time.monotonic() + 2
                while (
                    not expected_events.issubset(application_events)
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.005)
                    application_events = read_events(events_path)[events_before:]
            result["application_events"] = application_events
        return result

    try:
        while True:
            try:
                received = tls_socket.recv(65536)
            except TimeoutError:
                result = observation()
                result["connection_closed"] = True
                return result
            if not received:
                result = observation()
                result["connection_closed"] = True
                return result
            events = connection.receive_data(received)
            for event in events:
                if isinstance(event, InformationalResponseReceived) and event.stream_id == stream_id:
                    informational_status = 0
                    informational_headers = []
                    for name, value in event.headers:
                        if name == ":status":
                            informational_status = int(value)
                        else:
                            informational_headers.append([name.lower(), value])
                    early_hints.append({
                        "status": informational_status,
                        "headers": informational_headers,
                    })
                    if events_path is not None and informational_status == 103:
                        application_events = read_events(events_path)[events_before:]
                        if (
                            "http2.early-hint-call" in application_events
                            and "http2.final-response-start" not in application_events
                        ):
                            early_hint_before_final_start = True
                elif isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                        else:
                            response_headers.append((name, value))
                elif isinstance(event, TrailersReceived) and event.stream_id == stream_id:
                    response_trailers.extend(
                        [name.lower(), value] for name, value in event.headers
                    )
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, stream_id)
                elif isinstance(event, StreamReset) and event.stream_id == stream_id:
                    result = observation()
                    result["connection_closed"] = True
                    return result
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    pending = connection.data_to_send()
                    if pending:
                        tls_socket.sendall(pending)
                    return observation()
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
    chunks = request_stream_chunks(specification)
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
        "h3_grease": request.get("h3_grease", True),
        "abort_after_body": request.get("abort_after_body", False),
        "abort_response_after_headers": request.get("abort_response_after_headers", False),
        "peer_stop_before_response_headers": request.get("peer_stop_before_response_headers", False),
        "peer_stop_after_body_complete": request.get("peer_stop_after_body_complete", False),
        "peer_stop_while_upload_open": request.get("peer_stop_while_upload_open", False),
        "complete_upload_after_response": request.get("complete_upload_after_response", False),
        "same_connection_followup_path": request.get("same_connection_followup_path", "/"),
        "malformed_data_frame_after_headers": request.get("malformed_data_frame_after_headers", False),
        "expect_response_error": request.get("expect_response_error", False),
        "leave_upload_open_until_response": request.get("leave_upload_open_until_response", False),
        "empty_data_frame_before_body": request.get("empty_data_frame_before_body", False),
        "trailers": request.get("trailers", []),
        "invalid_alpn": request.get("invalid_alpn", False),
    }
    if "body_chunks_base64" in request:
        specification["body_chunks_hex"] = [
            base64.b64decode(chunk, validate=True).hex()
            for chunk in request["body_chunks_base64"]
        ]
    if "authority" in request:
        specification["authority"] = request["authority"]
    if "close_error_code" in request:
        specification["close_error_code"] = request["close_error_code"]
    command = [str(client), f"127.0.0.1:{port}", str(trust_anchor)]
    input_data = json.dumps(specification)
    application_cancelled = False
    malformed_disconnect_observed = False
    if request.get("malformed_data_frame_after_headers"):
        if events_path is None:
            raise ParityError("truncated HTTP/3 DATA workflow requires ASGI event observation")
        ready_path = events_path.with_suffix(".http3-truncated-data-ready")
        release_path = events_path.with_suffix(".http3-truncated-data-release")
        ready_path.unlink(missing_ok=True)
        release_path.unlink(missing_ok=True)
        specification["malformed_result_file"] = str(ready_path)
        specification["malformed_release_file"] = str(release_path)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout = stderr = ""
        try:
            if process.stdin is None:
                raise ParityError("truncated HTTP/3 DATA client has no stdin pipe")
            process.stdin.write(json.dumps(specification))
            process.stdin.close()
            process.stdin = None

            deadline = time.monotonic() + 5
            while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            if not ready_path.exists():
                raise ParityError("truncated HTTP/3 DATA client did not send its request")

            deadline = time.monotonic() + 5
            observed_events = read_events(events_path)[events_before:]
            while (
                "http3.upload.disconnected" not in observed_events
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
                observed_events = read_events(events_path)[events_before:]
            malformed_disconnect_observed = "http3.upload.disconnected" in observed_events
            release_path.touch()
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired as error:
                raise ParityError(
                    "truncated HTTP/3 DATA client did not exit after releasing the probe"
                ) from error
        finally:
            release_path.touch()
            if process.poll() is None:
                process.kill()
                stdout, stderr = process.communicate()
        returncode = process.returncode
    elif (
        request.get("peer_stop_before_response_headers")
        or request.get("peer_stop_after_body_complete")
        or request.get("peer_stop_while_upload_open")
    ):
        if events_path is None:
            raise ParityError("HTTP/3 peer-stop workflow requires ASGI event observation")
        stop_release_path = events_path.with_suffix(".http3-peer-stop-release")
        followup_release_path = events_path.with_suffix(".http3-peer-stop-followup-release")
        stop_release_path.unlink(missing_ok=True)
        followup_release_path.unlink(missing_ok=True)
        specification["peer_stop_release_file"] = str(stop_release_path)
        specification["peer_stop_followup_release_file"] = str(followup_release_path)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout = stderr = ""
        try:
            if process.stdin is None:
                raise ParityError("HTTP/3 peer-stop client has no stdin pipe")
            process.stdin.write(json.dumps(specification))
            process.stdin.close()
            process.stdin = None

            if request.get("peer_stop_after_body_complete"):
                request_checkpoints = {
                    "http3.after-body.request-complete",
                    "http3.after-body.waiting-for-disconnect",
                }
                completion_events = {
                    "http3.after-body.disconnected",
                    "http3.after-body.cancelled-before-disconnect",
                }
            elif request.get("peer_stop_while_upload_open"):
                request_checkpoints = {
                    "http3.open-upload.body-received",
                    "http3.open-upload.waiting-for-disconnect",
                }
                completion_events = {
                    "http3.open-upload.disconnected",
                    "http3.open-upload.cancelled-before-disconnect",
                }
            else:
                request_checkpoints = {"request.hold"}
                completion_events = {"request.cancelled"}

            deadline = time.monotonic() + 5
            observed_events = set(read_events(events_path)[events_before:])
            while (
                time.monotonic() < deadline
                and not request_checkpoints.issubset(observed_events)
                and process.poll() is None
            ):
                time.sleep(0.01)
                observed_events = set(read_events(events_path)[events_before:])
            if not request_checkpoints.issubset(observed_events):
                if process.poll() is None:
                    process.kill()
                stdout, stderr = process.communicate()
                client_diagnostic = (stderr or stdout).strip()[-800:]
                raise ParityError(
                    "HTTP/3 peer-stop client did not reach the ASGI request checkpoint: "
                    f"expected={sorted(request_checkpoints)!r}, events={sorted(observed_events)!r}, "
                    f"client={client_diagnostic!r}"
                )

            stop_release_path.touch()
            deadline = time.monotonic() + 5
            observed_events = set(read_events(events_path)[events_before:])
            while (
                time.monotonic() < deadline
                and not completion_events.intersection(observed_events)
                and process.poll() is None
            ):
                time.sleep(0.01)
                observed_events = set(read_events(events_path)[events_before:])
            application_cancelled = bool(completion_events.intersection(observed_events))
            if not application_cancelled:
                raise ParityError(
                    "HTTP/3 peer STOP_SENDING did not finish the ASGI request workflow: "
                    f"expected one of={sorted(completion_events)!r}, events={sorted(observed_events)!r}"
                )

            followup_release_path.touch()
            try:
                stdout, stderr = process.communicate(timeout=20)
            except subprocess.TimeoutExpired as error:
                raise ParityError(
                    "HTTP/3 same-connection follow-up did not finish after ASGI cancellation"
                ) from error
        finally:
            stop_release_path.touch()
            followup_release_path.touch()
            if process.poll() is None:
                process.kill()
                stdout, stderr = process.communicate()
        returncode = process.returncode
    elif request.get("abort_after_body") and events_path is not None:
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
    if request.get("malformed_data_frame_after_headers"):
        if response.get("malformed_data_frame_sent") is not True:
            raise ParityError("HTTP/3 probe did not report sending the truncated DATA frame")
        case_events = read_events(events_path)[events_before:] if events_path else []
        return {
            "disconnect_event": malformed_disconnect_observed,
            "application_events": case_events,
            "peer_close_code": response.get("peer_close_code"),
        }
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
    if request.get("complete_upload_after_response"):
        if response.get("upload_finished_after_response") is not True:
            raise ParityError("HTTP/3 probe did not finish the upload after the response")
        followup = response.get("followup")
        if not isinstance(followup, dict):
            raise ParityError("HTTP/3 post-response upload probe omitted its same-connection follow-up")
        try:
            followup_body = bytes.fromhex(followup["body_hex"])
            response_body = bytes.fromhex(response["body_hex"])
        except (KeyError, TypeError, ValueError) as error:
            raise ParityError("HTTP/3 post-response upload probe returned invalid body bytes") from error
        observation = response_observation(
            response["status"],
            [("content-type", response.get("content_type") or "")],
            response_body,
        )
        followup_observation = response_observation(
            followup["status"],
            [("content-type", followup.get("content_type") or "")],
            followup_body,
        )
        case_events = read_events(events_path)[events_before:] if events_path else []
        observation.update({
            "application_cancelled": "http3.open-upload-retired.cancelled" in case_events,
            "application_events": case_events,
            "followup_healthy": followup_observation["status"] == 200,
            "followup": followup_observation,
        })
        return observation
    if request.get("peer_stop_while_upload_open"):
        if response.get("peer_stop_sent") is not True:
            raise ParityError("HTTP/3 probe did not report sending STOP_SENDING")
        if response.get("client_aborted") is not True:
            raise ParityError("HTTP/3 probe did not report the client-side request cancellation")
        followup = response.get("followup")
        if not isinstance(followup, dict):
            raise ParityError("HTTP/3 peer-stop probe omitted its same-connection follow-up")
        try:
            followup_body = bytes.fromhex(followup["body_hex"])
        except (KeyError, TypeError, ValueError) as error:
            raise ParityError("HTTP/3 peer-stop follow-up returned an invalid body") from error
        followup_observation = response_observation(
            followup["status"],
            [("content-type", followup.get("content_type") or "")],
            followup_body,
        )
        followup_observation["ordered_response_headers"] = followup.get(
            "ordered_response_headers", []
        )
        response_header_values_by_name: dict[str, list[str]] = {}
        for name, value in followup_observation["ordered_response_headers"]:
            response_header_values_by_name.setdefault(name, []).append(value)
        followup_observation["response_header_values_by_name"] = [
            [name, values] for name, values in sorted(response_header_values_by_name.items())
        ]
        case_events = read_events(events_path)[events_before:] if events_path else []
        return {
            "client_aborted": True,
            "application_cancelled": "http3.open-upload.cancelled-before-disconnect" in case_events,
            "application_events": case_events,
            "disconnect_event": "http3.open-upload.disconnected" in case_events,
            "followup_healthy": followup_observation["status"] == 200,
            "followup": followup_observation,
        }
    if request.get("peer_stop_after_body_complete"):
        if response.get("peer_stop_sent") is not True:
            raise ParityError("HTTP/3 probe did not report sending STOP_SENDING")
        if response.get("client_aborted") is not True:
            raise ParityError("HTTP/3 probe did not report the client-side request cancellation")
        followup = response.get("followup")
        if not isinstance(followup, dict):
            raise ParityError("HTTP/3 peer-stop probe omitted its same-connection follow-up")
        try:
            followup_body = bytes.fromhex(followup["body_hex"])
        except (KeyError, TypeError, ValueError) as error:
            raise ParityError("HTTP/3 peer-stop follow-up returned an invalid body") from error
        followup_observation = response_observation(
            followup["status"],
            [("content-type", followup.get("content_type") or "")],
            followup_body,
        )
        followup_observation["ordered_response_headers"] = followup.get(
            "ordered_response_headers", []
        )
        response_header_values_by_name: dict[str, list[str]] = {}
        for name, value in followup_observation["ordered_response_headers"]:
            response_header_values_by_name.setdefault(name, []).append(value)
        followup_observation["response_header_values_by_name"] = [
            [name, values] for name, values in sorted(response_header_values_by_name.items())
        ]
        case_events = read_events(events_path)[events_before:] if events_path else []
        return {
            "client_aborted": True,
            "application_cancelled": "http3.after-body.cancelled-before-disconnect" in case_events,
            "application_events": case_events,
            "disconnect_event": "http3.after-body.disconnected" in case_events,
            "followup_healthy": followup_observation["status"] == 200,
            "followup": followup_observation,
        }
    if request.get("peer_stop_before_response_headers"):
        if response.get("peer_stop_sent") is not True:
            raise ParityError("HTTP/3 probe did not report sending STOP_SENDING")
        followup = response.get("followup")
        if not isinstance(followup, dict):
            raise ParityError("HTTP/3 peer-stop probe omitted its same-connection follow-up")
        try:
            followup_body = bytes.fromhex(followup["body_hex"])
        except (KeyError, TypeError, ValueError) as error:
            raise ParityError("HTTP/3 peer-stop follow-up returned an invalid body") from error
        followup_observation = response_observation(
            followup["status"],
            [("content-type", followup.get("content_type") or "")],
            followup_body,
        )
        followup_observation["ordered_response_headers"] = followup.get(
            "ordered_response_headers", []
        )
        response_header_values_by_name: dict[str, list[str]] = {}
        for name, value in followup_observation["ordered_response_headers"]:
            response_header_values_by_name.setdefault(name, []).append(value)
        followup_observation["response_header_values_by_name"] = [
            [name, values] for name, values in sorted(response_header_values_by_name.items())
        ]
        case_events = read_events(events_path)[events_before:] if events_path else []
        return {
            "application_cancelled": application_cancelled,
            "application_events": case_events,
            "followup": followup_observation,
        }
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
    settled_rss = [result["rss_after_bytes"] for result in resource_rounds[-2:]]
    retained_rss_growth = settled_rss[-1] - settled_rss[0] if len(settled_rss) == 2 else 0
    # Initial load can warm caches and allocate reusable arenas. Check positive
    # growth between the final settled rounds; reclaimed RSS is not a leak.
    rss_stable = (
        len(resource_rounds) == rounds
        and len(settled_rss) == 2
        and max(0, retained_rss_growth) <= 16 * 1024 * 1024
    )
    task_counts = [result["idle_python_tasks"] for result in resource_rounds]
    # asyncio.all_tasks() is a point-in-time snapshot, so transient tasks can
    # settle between rounds. Reject retained task growth across the workload
    # while allowing one task of scheduling jitter at the final snapshot.
    tasks_stable = (
        len(task_counts) == rounds
        and task_counts[-1] <= task_counts[0] + 1
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
    observation["process_exit_code"] = exit_code
    observation["server_log"] = server_log
    return observation


def websocket_raw_frame_observation(
    server: dict[str, Any],
    specification: dict[str, Any],
    *,
    observe_application_events: bool = False,
) -> dict[str, Any]:
    events_path = server["events"]
    events_before = len(read_events(events_path))
    client = socket.create_connection(("127.0.0.1", server["port"]), timeout=10)
    client.settimeout(10)
    handshake_status: int | None = None
    handshake_accept_valid = False
    compression_negotiated = False
    frame_sent = False
    application_events: list[str] = []
    raw_key = "dGhlIHNhbXBsZSBub25jZQ=="
    expected_accept = base64.b64encode(
        hashlib.sha1(
            (raw_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()
    ).decode("ascii")
    offered_subprotocols = specification["subprotocols"]
    subprotocol_header = (
        f"Sec-WebSocket-Protocol: {', '.join(offered_subprotocols)}\r\n"
        if offered_subprotocols
        else ""
    )
    additional_header_lines: list[str] = []
    for name, value in specification.get("headers", []):
        if (
            not name
            or any(character in name for character in ":\r\n")
            or any(character in value for character in "\r\n")
        ):
            raise ParityError(
                "raw WebSocket headers must not contain line breaks or name separators"
            )
        try:
            f"{name}: {value}".encode("ascii")
        except UnicodeEncodeError as error:
            raise ParityError("raw WebSocket headers must contain ASCII text") from error
        additional_header_lines.append(f"{name}: {value}\r\n")
    additional_headers = "".join(additional_header_lines)
    raw_request = (
        f"GET {specification['path']} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{server['port']}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {raw_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"{subprotocol_header}{additional_headers}\r\n"
    ).encode("ascii")
    try:
        client.sendall(raw_request)
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
        if b"\r\n\r\n" in response:
            header_block = bytes(response).split(b"\r\n\r\n", 1)[0]
            lines = header_block.split(b"\r\n")
            status_parts = lines[0].split()
            if len(status_parts) >= 2 and status_parts[1].isdigit():
                handshake_status = int(status_parts[1])
            response_headers = {}
            for line in lines[1:]:
                name, separator, value = line.partition(b":")
                if separator:
                    response_headers[name.strip().lower()] = value.strip()
            handshake_accept_valid = (
                response_headers.get(b"sec-websocket-accept") == expected_accept.encode("ascii")
            )
            compression_negotiated = b"permessage-deflate" in response_headers.get(
                b"sec-websocket-extensions", b""
            ).lower()
            selected_subprotocol = response_headers.get(b"sec-websocket-protocol")
        else:
            selected_subprotocol = None
        if handshake_status == 101:
            raw_frame = base64.b64decode(specification["raw_frame_base64"], validate=True)
            try:
                client.sendall(raw_frame)
                frame_sent = True
            except OSError:
                frame_sent = False
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                application_events = read_events(events_path)[events_before:]
                if (
                    any(event.startswith("websocket.disconnect:") for event in application_events)
                    or (
                        observe_application_events
                        and any(
                            event.startswith("websocket.fragmented.message:")
                            for event in application_events
                        )
                    )
                ):
                    break
                if server["process"].poll() is not None:
                    break
                time.sleep(0.01)
    finally:
        client.close()

    disconnect_event = next(
        (event for event in application_events if event.startswith("websocket.disconnect:")),
        None,
    )
    disconnect_code = None
    if disconnect_event is not None:
        parts = disconnect_event.split(":", 2)
        if len(parts) >= 2:
            try:
                disconnect_code = int(parts[1])
            except ValueError:
                pass
    followup = http1_request(server["port"], {
        "method": "GET",
        "path": specification["followup_path"],
        "headers": [],
        "body_base64": "",
    })
    observation = {
        "handshake_status": handshake_status,
        "handshake_accept_valid": handshake_accept_valid,
        "compression_negotiated": compression_negotiated,
        "subprotocol": (
            selected_subprotocol.decode("ascii") if selected_subprotocol is not None else None
        ),
        "frame_sent": frame_sent,
        "disconnect_event": disconnect_event is not None,
        "disconnect_code": disconnect_code,
        "followup_status": followup["status"],
    }
    if observe_application_events:
        observation["application_events"] = application_events
    return observation


def websocket_server_keepalive_observation(
    server: dict[str, Any], specification: dict[str, Any]
) -> dict[str, Any]:
    """Observe server Ping, matching Pong, and the keepalive timeout close."""

    raw_key = "dGhlIHNhbXBsZSBub25jZQ=="
    expected_accept = base64.b64encode(
        hashlib.sha1(
            (raw_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()
    ).decode("ascii").encode("ascii")
    observation: dict[str, Any] = {
        "handshake_status": None,
        "handshake_accept_valid": False,
        "first_server_ping_received": False,
        "first_server_ping_payload_length": None,
        "pong_sent": False,
        "unsolicited_pong_sent": False,
        "second_server_ping_received": False,
        "second_server_ping_payload_length": None,
        "second_pong_sent": False,
        "second_pong_payload_matches_ping": None,
        "timeout_close_received": False,
        "timeout_close_code": None,
        "timeout_close_reason": None,
    }

    def read_exactly(reader: Any, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = reader.read(size - len(chunks))
            if not chunk:
                raise EOFError("WebSocket peer closed before the frame was complete")
            chunks.extend(chunk)
        return bytes(chunks)

    def read_frame(reader: Any) -> tuple[int, bytes]:
        first, second = read_exactly(reader, 2)
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(read_exactly(reader, 2), "big")
        elif length == 127:
            length = int.from_bytes(read_exactly(reader, 8), "big")
        if second & 0x80:
            mask = read_exactly(reader, 4)
            payload = read_exactly(reader, length)
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        else:
            payload = read_exactly(reader, length)
        return first & 0x0F, payload

    def send_pong(client: socket.socket, payload: bytes) -> None:
        if len(payload) > 125:
            raise ParityError("server keepalive Ping payload exceeded the control-frame limit")
        mask = b"\x13\x57\x9b\xdf"
        masked = bytes(byte ^ mask[index % len(mask)] for index, byte in enumerate(payload))
        client.sendall(bytes((0x8A, 0x80 | len(payload))) + mask + masked)

    client = socket.create_connection(("127.0.0.1", server["port"]), timeout=3)
    client.settimeout(3)
    reader = client.makefile("rb")
    try:
        request = (
            f"GET {specification['path']} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server['port']}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {raw_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        client.sendall(request)
        status_line = reader.readline()
        status_parts = status_line.split()
        if len(status_parts) >= 2 and status_parts[1].isdigit():
            observation["handshake_status"] = int(status_parts[1])
        response_headers: dict[bytes, bytes] = {}
        while status_line and (line := reader.readline()) not in {b"\r\n", b"\n", b""}:
            name, separator, value = line.partition(b":")
            if separator:
                response_headers[name.strip().lower()] = value.strip()
        observation["handshake_accept_valid"] = (
            response_headers.get(b"sec-websocket-accept") == expected_accept
        )
        if observation["handshake_status"] != 101:
            return observation

        if "unsolicited_pong_payload_base64" in specification:
            unsolicited_pong_payload = base64.b64decode(
                specification["unsolicited_pong_payload_base64"], validate=True
            )
            send_pong(client, unsolicited_pong_payload)
            observation["unsolicited_pong_sent"] = True

        try:
            first_opcode, first_payload = read_frame(reader)
        except (EOFError, OSError, TimeoutError):
            return observation
        observation["first_server_ping_received"] = first_opcode == 0x9
        if first_opcode != 0x9:
            return observation
        observation["first_server_ping_payload_length"] = len(first_payload)
        send_pong(client, first_payload)
        observation["pong_sent"] = True

        try:
            second_opcode, second_payload = read_frame(reader)
        except (EOFError, OSError, TimeoutError):
            return observation
        observation["second_server_ping_received"] = second_opcode == 0x9
        if second_opcode != 0x9:
            if second_opcode == 0x8:
                observation["timeout_close_received"] = True
                if len(second_payload) >= 2:
                    observation["timeout_close_code"] = int.from_bytes(
                        second_payload[:2], "big"
                    )
                    observation["timeout_close_reason"] = second_payload[2:].decode(
                        "utf-8", errors="replace"
                    )
            return observation
        observation["second_server_ping_payload_length"] = len(second_payload)
        if "second_pong_payload_base64" in specification:
            second_pong_payload = base64.b64decode(
                specification["second_pong_payload_base64"], validate=True
            )
            send_pong(client, second_pong_payload)
            observation["second_pong_sent"] = True
            observation["second_pong_payload_matches_ping"] = (
                second_pong_payload == second_payload
            )

        try:
            close_opcode, close_payload = read_frame(reader)
        except (EOFError, OSError, TimeoutError):
            return observation
        observation["timeout_close_received"] = close_opcode == 0x8
        if close_opcode == 0x8 and len(close_payload) >= 2:
            observation["timeout_close_code"] = int.from_bytes(close_payload[:2], "big")
            observation["timeout_close_reason"] = close_payload[2:].decode(
                "utf-8", errors="replace"
            )
        return observation
    finally:
        reader.close()
        client.close()


def websocket_observation(
    server: dict[str, Any],
    specification: dict[str, Any],
    trust_anchor: Path | None,
    *,
    fault_control_path: Path | None = None,
    fault_point: str | None = None,
) -> dict[str, Any]:
    compression_negotiated = False
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
        application_events = read_events(events_path)[events_before:]
        exit_code, shutdown_log = stop_server(server, graceful=True)
        shutdown_timeout = any(
            marker in shutdown_log
            for marker in (
                "listener shutdown exceeded the graceful timeout",
                "TCP shutdown exceeded the graceful timeout",
                "active connections exceeded the graceful-shutdown deadline",
                "timeout graceful shutdown exceeded",
            )
        )
        sigkill = getattr(signal, "SIGKILL", None)
        return {
            "status": followup["status"],
            "application_events": application_events,
            "shutdown_clean": exit_code is not None
            and not server.get("forced_kill", False)
            and (sigkill is None or exit_code != -sigkill)
            and not shutdown_timeout,
        }

    def add_fault_followup(
        observation: dict[str, Any], *, wait_for_events: bool = True
    ) -> dict[str, Any]:
        observation.setdefault("compression_negotiated", compression_negotiated)
        public_contract = fault_point in PUBLIC_INPUT_CONTRACT_POINTS
        if fault_control_path is None and not public_contract:
            return observation
        if (
            fault_point == "websocket.accept-key.header-value-error"
            and fault_control_path.read_text(encoding="utf-8").strip() == fault_point
        ):
            raise ParityError("WebSocket accept-header conversion fault was not consumed by the target")
        if fault_control_path is not None:
            observation["fault_consumed"] = (
                fault_control_path.read_text(encoding="utf-8").strip() != fault_point
            )
            fault_control_path.write_text("", encoding="utf-8")
        application_events = read_events(events_path)[events_before:]
        wait_for_app_event = specification.get("wait_for_app_event")
        if wait_for_app_event is not None:
            deadline = time.monotonic() + 2
            while wait_for_app_event not in application_events and time.monotonic() < deadline:
                time.sleep(0.01)
                application_events = read_events(events_path)[events_before:]
        elif wait_for_events or public_contract:
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
        fault_consumed = (
            fault_control_path is None
            or fault_point is None
            or fault_control_path.read_text(encoding="utf-8").strip() != fault_point
        )
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
            "fault_consumed": fault_consumed,
        }
    client_socket: socket.socket | None = None
    try:
        receive_buffer_bytes = specification.get("receive_buffer_bytes")
        if receive_buffer_bytes is not None or specification.get("abrupt_disconnect", False):
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if receive_buffer_bytes is not None:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer_bytes)
            client_socket.connect(("127.0.0.1", server["port"]))
        with websocket_connect(
            uri,
            sock=client_socket,
            subprotocols=subprotocols,
            compression=None if specification.get("disable_compression", False) else "deflate",
            additional_headers=specification.get("headers", []),
            ssl=ssl_context,
            proxy=None,
            open_timeout=20,
            close_timeout=2,
            max_queue=1 if "wait_for_app_event" in specification else 16,
            max_size=16 * 1024 * 1024 if "wait_for_app_event" in specification else 1024 * 1024,
            logger=client_logger,
        ) as websocket:
            compression_negotiated = any(
                type(extension).__name__ == "PerMessageDeflate"
                for extension in websocket.protocol.extensions
            )
            if specification.get("abrupt_disconnect", False):
                wait_for_app_event = specification.get("wait_for_app_event")
                if wait_for_app_event is not None:
                    deadline = time.monotonic() + 10
                    application_events = read_events(events_path)[events_before:]
                    while wait_for_app_event not in application_events and time.monotonic() < deadline:
                        time.sleep(0.01)
                        application_events = read_events(events_path)[events_before:]
                    if wait_for_app_event not in application_events:
                        raise ParityError(
                            f"WebSocket app did not reach disconnect wait event {wait_for_app_event!r}"
                        )
                client_socket.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                )
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
            compression_negotiated = any(
                type(extension).__name__ == "PerMessageDeflate"
                for extension in websocket.protocol.extensions
            )
            observation = {
                "handshake_established": True,
                "handshake_status": 101,
                "subprotocol": websocket.subprotocol,
                "messages": echoes,
                "compression_negotiated": compression_negotiated,
            }
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
                "handshake_established": True,
                "handshake_status": 101,
                "close_code": close.code if close is not None else None,
                "close_reason": close.reason if close is not None else None,
            },
            wait_for_events=False,
        )
    except InvalidStatus as error:
        observation = {
            "handshake_established": False,
            "handshake_status": error.response.status_code,
            "compression_negotiated": compression_negotiated,
        }
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
        "client_certificate_rejected": "client_certificate_rejected",
        "negotiated_tls_version": "negotiated_tls_version",
        "negotiated_tls_cipher": "negotiated_tls_cipher",
        "body_bytes": "body_base64",
        "ordered_body_bytes": "body_base64",
        "early_hints": "early_hints",
        "early_hint_before_final_start": "early_hint_before_final_start",
        "response_trailers": "response_trailers",
        "ordered_response_headers": "ordered_response_headers",
        "response_header_values_by_name": "response_header_values_by_name",
        "server_header_values": "server_header_values",
        "date_header_present": "date_header_present",
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
        "handshake_accept_valid": "handshake_accept_valid",
        "frame_sent": "frame_sent",
        "disconnect_code": "disconnect_code",
        "followup_status": "followup_status",
        "handshake_rejected": "handshake_rejected",
        "pong_received": "pong_received",
        "first_server_ping_received": "first_server_ping_received",
        "first_server_ping_payload_length": "first_server_ping_payload_length",
        "pong_sent": "pong_sent",
        "unsolicited_pong_sent": "unsolicited_pong_sent",
        "second_server_ping_received": "second_server_ping_received",
        "second_server_ping_payload_length": "second_server_ping_payload_length",
        "second_pong_sent": "second_pong_sent",
        "second_pong_payload_matches_ping": "second_pong_payload_matches_ping",
        "timeout_close_received": "timeout_close_received",
        "timeout_close_code": "timeout_close_code",
        "timeout_close_reason": "timeout_close_reason",
        "subprotocol": "subprotocol",
        "compression_negotiated": "compression_negotiated",
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
        "worker_replacement_observed": "worker_replacement_observed",
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
        "shutdown_clean": "shutdown_clean",
    }
    projected = {}
    for field in operation["observe"]:
        source = source_fields[field]
        if source not in raw:
            raise ParityError(f"adapter omitted declared observation {field!r}")
        projected[field] = raw[source]
    return projected


def normalize_comparison_observation(value: Any, profile_id: str) -> Any:
    """Normalize transport-independent observations before parity comparison.

    The HTTP/2 oracle is Hypercorn because Uvicorn does not implement HTTP/2.
    HTTP field order across different names is not significant (RFC 9110,
    Section 5.3), while the order of values for one field name is significant.
    Keep ``response_header_values_by_name`` in the comparison and omit the
    transport-specific global field order and server identification header.

    The HTTP/3 oracle is also Hypercorn because Uvicorn does not implement
    HTTP/3. Hypercorn exits with status zero after SIGTERM, while Uvicorn
    restores and re-raises the signal after graceful shutdown. The HTTP/3
    contract still compares whether each server terminated and its protocol
    outcome; the Uvicorn signal exit code is covered by the Uvicorn lifecycle
    profile.
    """
    if profile_id not in {"http2", "http3"}:
        return value
    if isinstance(value, dict):
        ignored_fields = set()
        if profile_id == "http2":
            ignored_fields.update({"ordered_response_headers", "server_header_values"})
        elif profile_id == "http3":
            ignored_fields.add("process_exit_code")
        return {
            key: normalize_comparison_observation(item, profile_id)
            for key, item in value.items()
            if key not in ignored_fields
        }
    if isinstance(value, list):
        return [normalize_comparison_observation(item, profile_id) for item in value]
    return value


def normalize_cli_process_stderr(stderr_base64: str) -> tuple[str, Any]:
    """Compare Python CLI diagnostics without implementation source locations.

    Python traceback frames name implementation-specific source files and line
    numbers. Runtime warnings also print the source path, line, and code line.
    CLI evidence keeps the original stderr; comparisons retain the exception
    messages and warning text while removing only those implementation details.
    """
    stderr = base64.b64decode(stderr_base64, validate=True)
    lines = stderr.splitlines()
    traceback_header = b"Traceback (most recent call last):"
    if traceback_header not in lines:
        warning_separator = b": RuntimeWarning:"
        if not any(
            b"uvicorn/" in line.replace(b"\\", b"/")
            and warning_separator in line
            for line in lines
        ):
            return ("raw", stderr)
        normalized_warning: list[bytes] = []
        skip_source_line = False
        for line in lines:
            if skip_source_line and line.startswith(b"  "):
                normalized_warning.append(b"  <source line>")
                skip_source_line = False
                continue
            normalized_line = line.replace(b"\\", b"/")
            if b"uvicorn/" in normalized_line and warning_separator in normalized_line:
                prefix, _, message = normalized_line.partition(warning_separator)
                source_path = prefix.rsplit(b"uvicorn/", 1)[1]
                source_name, separator, line_number = source_path.rpartition(b":")
                if (
                    separator
                    and line_number.isdigit()
                    and source_name.endswith(b".py")
                ):
                    normalized_warning.append(b"RuntimeWarning:" + message)
                    skip_source_line = True
                    continue
            normalized_warning.append(line)
        return ("python-runtime-warning-source", tuple(normalized_warning))

    chain_markers = {
        b"The above exception was the direct cause of the following exception:",
        b"During handling of the above exception, another exception occurred:",
    }
    normalized: list[bytes] = []
    inside_traceback = False
    found_exception = False
    for line in lines:
        if line == traceback_header:
            normalized.append(traceback_header)
            inside_traceback = True
            continue
        if not inside_traceback:
            normalized.append(line)
            continue
        if line in chain_markers:
            normalized.append(line)
            continue
        if line.startswith(b"  File ") or line.startswith(b"    ") or not line.strip():
            continue
        if not line.startswith((b" ", b"\t")):
            normalized.append(line)
            inside_traceback = False
            found_exception = True

    if not found_exception:
        return ("raw", stderr)
    return ("python-traceback-exception-chain", tuple(normalized))


def normalize_operation_comparison_observation(
    observation: dict[str, Any], operation: dict[str, Any]
) -> dict[str, Any]:
    """Apply only the comparison normalizations declared for an operation."""
    normalized = dict(observation)
    for field, policy in operation.get("comparison_normalization", {}).items():
        if policy == "python-process-diagnostics":
            normalized[field] = normalize_cli_process_stderr(normalized[field])
    return normalized


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
        if os.name == "nt":
            # Popen.terminate() is TerminateProcess on Windows, so the ASGI
            # requests cannot observe cancellation. Use the same graceful
            # control event as the active-stream shutdown contract.
            server["graceful_signal_requested"] = True
            server["process"].send_signal(signal.CTRL_BREAK_EVENT)
        else:
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
                    server["port"],
                    case["request_stream"],
                    server["events"],
                    allow_nonchunked_response=(
                        fault is not None
                        and fault["contract"] == "http-body-pump-send-stopped-without-response"
                    ),
                    fault_control_path=(
                        fault_control_path
                        if fault is not None
                        and fault["contract"] == "http-body-pump-drain-terminal-frame"
                        else None
                    ),
                    fault_point=(
                        fault["point"]
                        if fault is not None
                        and fault["contract"] == "http-body-pump-drain-terminal-frame"
                        else None
                    ),
                )
                if fault is not None and fault["contract"] == "http-request-body-conversion-error-caught":
                    observation["fault_consumed"] = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault["point"]
                    )
                if fault is not None and fault["contract"] in {
                    "http-body-pump-send-stopped-without-response",
                    "http-body-pump-oversized-frame-echo",
                }:
                    observation["fault_consumed"] = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault["point"]
                    )
                if fault is not None and fault["contract"] == "http-body-pump-send-stopped-without-response":
                    observation["followup_response"] = http1_request(
                        server["port"],
                        {
                            "method": "GET",
                            "path": case["request_stream"]["followup_path"],
                            "headers": [],
                            "body_base64": "",
                        },
                    )
                if (
                    fault is not None
                    and fault["contract"] == "http-body-pump-reaps-cancelled-task"
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
        # This selector is consumed when the target process starts, before
        # its server path is chosen. Re-arming it here would leave a stale
        # token that falsely reports startup selection as unconsumed.
        if (
            fault_control_path is not None
            and fault["point"] != "http3.legacy-path.selection"
        ):
            control_point = fault["point"] if fault["point"] in FAULT_POINTS else ""
            fault_control_path.write_text(control_point, encoding="utf-8")
        if profile["protocol"].startswith("http/1.1"):
            ssl_context = None
            if profile_id == "http1-tls":
                if trust_anchor is None:
                    raise ParityError("HTTPS profile is missing its generated trust anchor")
                ssl_context = ssl.create_default_context(cafile=str(trust_anchor))
                if case.get("client_tls") is True:
                    client_certificate = server.get("client_certificate")
                    client_key = server.get("client_key")
                    if client_certificate is None or client_key is None:
                        raise ParityError("mutual TLS case is missing its generated client identity")
                    ssl_context.load_cert_chain(
                        certfile=str(client_certificate), keyfile=str(client_key)
                    )
                if case["operation"] == "tls.client-auth-required":
                    try:
                        observation = http1_request(
                            server["port"], case["request"], ssl_context=ssl_context
                        )
                    except TimeoutError:
                        raise
                    except (ssl.SSLError, ConnectionError, http.client.HTTPException):
                        return {"client_certificate_rejected": True}
                    return {
                        "client_certificate_rejected": bool(
                            observation.get("connection_closed", False)
                        )
                    }
                if case["operation"] in {"tls.protocol-version", "tls.negotiated-cipher"}:
                    return http1_request(
                        server["port"],
                        case["request"],
                        ssl_context=ssl_context,
                        observe_tls_version=case["operation"] == "tls.protocol-version",
                        observe_tls_cipher=case["operation"] == "tls.negotiated-cipher",
                    )
            observation = http1_request(
                server["port"], case["request"], ssl_context=ssl_context
            )
            if (
                fault is not None
                and fault["contract"]
                == "server-default-header-finalization-error-closes-connection"
            ):
                if (
                    fault_control_path is None
                    or fault_control_path.read_text(encoding="utf-8").strip()
                    == fault["point"]
                ):
                    raise ParityError("default-header finalization fault was not consumed")
                observation["fault_consumed"] = True
            return observation
        if profile_id == "http2":
            response_extension_operation = case["operation"] in {
                "http2.response-early-hints",
                "http2.response-trailers",
                "http2.response-trailers-without-te",
            }
            observation = http2_request(
                server["port"],
                case["request"],
                observe_response_extensions=response_extension_operation,
                events_path=server["events"]
                if case["operation"] in {
                    "http2.response-early-hints",
                    "http2.response-trailers-without-te",
                }
                else None,
                expected_application_events=case.get("required_observations", {}).get(
                    "application_events"
                ),
            )
            if (
                fault is not None
                and fault["contract"]
                == "http2-response-event-fault-consumed-and-status-observed"
            ):
                if (
                    fault_control_path is None
                    or fault_control_path.read_text(encoding="utf-8").strip()
                    == fault["point"]
                ):
                    raise ParityError("HTTP/2 response-event fault was not consumed")
                observation["fault_consumed"] = True
            return observation
        if profile_id == "http3":
            if trust_anchor is None or h3_client is None:
                raise ParityError("HTTP/3 adapter is missing its certificate or client")
            request = case["request"]
            if case["operation"] in {"http3.peer-close", "http3.peer-close-registered"}:
                observation = http3_peer_close_request(server, trust_anchor, request, h3_client)
                if fault is not None and fault["contract"] in {
                    "http3-legacy-peer-close-no-error",
                    "http3-legacy-peer-close-unknown-code-ignored",
                    "http3-legacy-peer-close-classification-error",
                }:
                    observation["fault_consumed"] = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault["point"]
                    )
                return observation
            if request.get("hold_open_for_shutdown"):
                observation = http3_shutdown_request(server, trust_anchor, request, h3_client)
                if fault is not None and fault["point"] == "server.http3-task.shutdown-hang":
                    observation["fault_consumed"] = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault["point"]
                    )
                elif fault is not None and fault["point"] == "http3.legacy-path.selection":
                    observation["fault_consumed"] = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault["point"]
                    )
                return observation
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
                observation = {
                    "handshake_rejected": handshake_rejected,
                    "followup": followup,
                }
                if (
                    fault is not None
                    and fault["contract"] == "http3-legacy-handshake-recovery"
                ):
                    observation["fault_consumed"] = (
                        fault_control_path.read_text(encoding="utf-8").strip()
                        != fault["point"]
                    )
                return observation
            if request.get("malformed_data_frame_after_headers"):
                events_before = len(read_events(server["events"]))
                malformed_observation = http3_request(
                    server["port"],
                    trust_anchor,
                    request,
                    h3_client,
                    events_path=server["events"],
                    events_before=events_before,
                )
                followup = http3_request(
                    server["port"], trust_anchor, {
                        "method": "GET",
                        "path": "/state",
                        "headers": [],
                        "body_base64": "",
                    }, h3_client,
                )
                return {
                    "application_events": malformed_observation["application_events"],
                    "peer_close_code": malformed_observation["peer_close_code"],
                    "followup": followup,
                    "followup_healthy": followup.get("status") == 200,
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
            if (
                fault is not None
                and fault["contract"] == "http3-stream-reset-on-runtime-error"
            ):
                if (
                    fault_control_path is None
                    or fault_control_path.read_text(encoding="utf-8").strip()
                    == fault["point"]
                ):
                    raise ParityError("HTTP/3 stream runtime-error fault was not consumed")
                observation["fault_consumed"] = True
            if (
                fault is not None
                and fault["contract"] == "http3-legacy-default-header-error-resets-stream"
            ):
                if (
                    fault_control_path is None
                    or fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                ):
                    raise ParityError("HTTP/3 legacy path selection fault was not consumed")
                observation["fault_consumed"] = True
            if fault is not None and fault["contract"] == "http3-body-pump-early-exit-500":
                if (
                    fault_control_path is None
                    or fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                ):
                    raise ParityError("HTTP/3 body-pump early-exit fault was not consumed")
                observation["fault_consumed"] = True
            if (
                fault is not None
                and fault["contract"]
                == "http3-peer-stop-cancelled-send-disconnect-followup-200"
            ):
                if (
                    fault_control_path is None
                    or fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                ):
                    raise ParityError("HTTP/3 disconnect-send cancellation fault was not consumed")
                observation["fault_consumed"] = True
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
                    and fault["contract"] in {
                        "http3-body-pump-error-stop-disconnect-followup-200",
                        "http3-legacy-body-pump-delivers-disconnect-followup-200",
                    }
                    and fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]
                ):
                    raise ParityError("HTTP/3 body-pump error-stop fault was not consumed")
                result = {
                    "disconnect_event": "http3.upload.disconnected" in read_events(server["events"])[events_before:],
                    "followup": followup,
                }
                if fault is not None and fault["contract"] in {
                    "http3-body-pump-error-stop-disconnect-followup-200",
                    "http3-legacy-body-pump-delivers-disconnect-followup-200",
                }:
                    result["fault_consumed"] = True
                return result
            if fault is not None and fault["contract"] == "http3-upload-body-pump-preserves-data":
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("HTTP/3 empty-data body-pump fault was not consumed")
                observation["fault_consumed"] = True
            if (
                fault is not None
                and fault["contract"]
                in {
                    "http3-native-body-pump-pre-poll-cancel-preserves-response",
                    "http3-native-body-pump-final-message-stop-preserves-response",
                }
            ):
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("HTTP/3 body-pump cancellation fault was not consumed")
                observation["fault_consumed"] = True
            if (
                fault is not None
                and fault["contract"]
                == "http3-native-body-pump-final-message-send-error-preserves-response"
            ):
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("HTTP/3 final-message send-error fault was not consumed")
                observation["fault_consumed"] = True
            if (
                fault is not None
                and fault["contract"] == "http3-native-body-pump-sender-closed-preserves-response"
            ):
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("HTTP/3 sender-closed body-pump fault was not consumed")
                observation["fault_consumed"] = True
            if (
                fault is not None
                and fault["contract"] == "http3-native-body-pump-send-stop-preserves-response"
            ):
                if fault_control_path.read_text(encoding="utf-8").strip() == fault["point"]:
                    raise ParityError("HTTP/3 body-pump send-stop fault was not consumed")
                observation["fault_consumed"] = True
            if request.get("abort_response_after_headers"):
                followup = http3_request(
                    server["port"], trust_anchor, {
                        "method": "GET",
                        "path": "/state",
                        "headers": [],
                        "body_base64": "",
                    }, h3_client,
                )
                result = {
                    **observation,
                    "followup": followup,
                }
                return result
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
        if case.get("operation") in {
            "websocket.raw-frame-disconnect",
            "websocket.fragmented-message-reassembly",
            "websocket.fragmented-compressed-message-reassembly",
            "websocket.raw-size-limit-close",
            "websocket.raw-size-limit-close-uncompressed",
        }:
            log_offset = len(read_server_log(server))
            observation = websocket_raw_frame_observation(
                server,
                case["websocket"],
                observe_application_events=(
                    case["operation"] in {
                        "websocket.fragmented-message-reassembly",
                        "websocket.fragmented-compressed-message-reassembly",
                    }
                ),
            )
            observation["server_log"] = read_server_log(server)[log_offset:]
            return observation
        if case.get("operation") in {
            "websocket.server-keepalive",
            "websocket.server-keepalive-mismatched-pong",
            "websocket.server-keepalive-unsolicited-pong",
        }:
            log_offset = len(read_server_log(server))
            observation = websocket_server_keepalive_observation(
                server, case["websocket"]
            )
            observation["server_log"] = read_server_log(server)[log_offset:]
            return observation
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
            "server_log": server.get("startup_output", ""),
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
        server_log = read_server_log(server)
        observation = {
            "startup_error_observed": (
                "coverage-only injected MemoryError at " in server_log
                or "ASGI 'lifespan' protocol appears unsupported." in server_log
                or "uvicorn-rs: ASGI app does not support lifespan" in server_log
            ),
            "followup": followup,
        }
        fault = case.get("fault")
        control_path = server.get("coverage_fault_control_path")
        if fault is not None:
            observation["fault_consumed"] = (
                control_path is not None
                and control_path.read_text(encoding="utf-8").strip() != fault["point"]
            )
        return observation
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
            return http2_disconnect_request(server["port"], disconnect, server["events"])
        client = socket.create_connection(("127.0.0.1", server["port"]), timeout=5)
        disconnect_started = time.monotonic()
        reset_elapsed_seconds = None
        try:
            if disconnect.get("malformed_chunk"):
                prefix = base64.b64decode(
                    disconnect.get("partial_body_base64", ""), validate=True
                )
                valid_prefix = (
                    f"{len(prefix):x}\r\n".encode("ascii") + prefix + b"\r\n"
                    if prefix
                    else b""
                )
                client.sendall(
                    f"POST {disconnect['path']} HTTP/1.1\r\nHost: localhost\r\n"
                    "Transfer-Encoding: chunked\r\n\r\n".encode()
                    + valid_prefix + b"not-a-size\r\nabc\r\n0\r\n\r\n"
                )
                deadline = time.monotonic() + 3
                while (
                    time.monotonic() < deadline
                    and "http.disconnect" not in application_events()
                ):
                    time.sleep(0.01)
                if "http.disconnect" not in application_events():
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
                if disconnect.get("reset_after_complete_request"):
                    client.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_LINGER,
                        struct.pack("ii", 1, 0),
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
            after_close_delay_ms = disconnect.get("after_close_delay_ms", 0)
            if after_close_delay_ms:
                time.sleep(after_close_delay_ms / 1000)
                server["events"].with_suffix(".disconnect-release").touch()
            if disconnect.get("reset") or disconnect.get("reset_after_complete_request"):
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
        fault_consumed = None
        if (
            fault is not None
            and fault["point"] == "http.connection.peer-read-failed.wait-complete"
        ):
            fault_consumed = (
                fault_control_path.read_text(encoding="utf-8").strip() != fault["point"]
            )
        if fault_control_path is not None:
            fault_control_path.write_text("", encoding="utf-8")
        followup = http1_request(server["port"], {
            "method": "GET", "path": disconnect["followup_path"], "headers": [], "body_base64": ""
        })
        result = {
            "disconnect_event": seen,
            "followup": followup,
            "application_events": application_events(),
            "reset_elapsed_seconds": reset_elapsed_seconds,
            "disconnect_workflow_seconds": time.monotonic() - disconnect_started,
        }
        if fault_consumed is not None:
            result["fault_consumed"] = fault_consumed
        return result
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
            fault_consumed = startup
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
                fault_consumed = True
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
                "fault_consumed": fault_consumed,
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
                    and fault["contract"] == "server-native-connection-error-during-shutdown"
                ):
                    fault_control_path = server.get("coverage_fault_control_path")
                    if fault_control_path is None:
                        raise ParityError("instrumented target has no connection-write fault control")
                    server["process"].terminate()
                    if not wait_for_listener_closed(
                        server, timeout=3, tls_context=tls_context
                    ):
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

                if os.name == "nt":
                    # Popen.terminate() is an unconditional TerminateProcess
                    # on Windows, which prevents the held response from
                    # exercising graceful drain. Ctrl+Break is Uvicorn's
                    # graceful shutdown signal for this process group.
                    server["graceful_signal_requested"] = True
                    server["process"].send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    server["process"].terminate()
                # Leave the held stream enough of its three-second grace to
                # complete even when admission closure is the failed behavior.
                trace_shutdown = os.environ.get("UVICORN_RS_SHUTDOWN_TRACE") == "1"
                listener_probe_started = time.monotonic()
                if trace_shutdown:
                    print(
                        "uvicorn-rs: parity-shutdown-trace "
                        f"listener-close-probe.start timeout_s=1 "
                        f"held_stream_socket_open={connection.sock is not None}",
                        flush=True,
                    )
                listener_closed_before_release = wait_for_listener_closed(
                    server, timeout=1, tls_context=tls_context
                )
                if trace_shutdown:
                    print(
                        "uvicorn-rs: parity-shutdown-trace "
                        "listener-close-probe.finished "
                        f"elapsed_s={time.monotonic() - listener_probe_started:.6f} "
                        f"closed={listener_closed_before_release} "
                        f"server_running={server['process'].poll() is None} "
                        f"held_stream_socket_open={connection.sock is not None}",
                        flush=True,
                    )
                if server["process"].poll() is not None:
                    raise ParityError("server exited before the held response stream was released")
                if "response.shutdown.finished" in read_events(server["events"]):
                    raise ParityError("response stream finished before its shutdown release")
                release_path.touch()
                if trace_shutdown:
                    print(
                        "uvicorn-rs: parity-shutdown-trace "
                        "held-stream-release.sent",
                        flush=True,
                    )
                # Consume the remaining TLS response while graceful shutdown
                # is in progress. On Windows, the stock Uvicorn oracle cannot
                # finish its TLS close handshake if the client waits for the
                # server process to exit before reading the response body.
                # That ordering can make this parity probe time out after the
                # ASGI stream and lifespan have both already completed.
                stream_body = first_chunk + response.read()
                exit_code, server_log = stop_server(server, graceful=True, signal_sent=True)
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
            shutdown_signal = {
                "SIGINT": signal.SIGINT,
                "SIGTERM": signal.SIGTERM,
            }.get(lifecycle.get("shutdown_signal"))
            exit_code, server_log = stop_server(
                server, graceful=True, signal_number=shutdown_signal
            )
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


def fault_contract_matches(
    fault: dict[str, Any], observation: dict[str, Any], case: dict[str, Any]
) -> bool:
    if fault["contract"] == "server-unix-listener-permission-error-startup-propagates":
        return (
            fault["point"] == "server.unix-listener.set-permissions-error"
            and observation.get("fault_consumed") is True
            and observation.get("exit_code") == 0
            and observation.get("server_started") is False
            and observation.get("serve_task_finished") is True
            and observation.get("serve_raised") is True
            and observation.get("serve_timed_out") is False
            and observation.get("application_events")
            == ["lifespan.startup", "lifespan.shutdown"]
        )
    if fault["contract"] == "server-connection-invalid-default-header-source-chain":
        server_logs = observation.get("server_log_events", {})
        stderr_events = server_logs.get("stderr", []) if isinstance(server_logs, dict) else []
        connection_error_logged = any(
            isinstance(event, dict)
            and "uvicorn-rs: HTTP connection from" in event.get("message", "")
            for event in stderr_events
        )
        return (
            observation.get("fault_consumed") is True
            and observation.get("response_received") is False
            and observation.get("process_exit_code") == 0
            and observation.get("process_timed_out") is False
            and not connection_error_logged
            and any(
                isinstance(event, dict)
                and event.get("message") == "Invalid HTTP header name."
                for event in stderr_events
            )
        )
    if fault["contract"] == "server-default-header-finalization-error-closes-connection":
        return (
            fault["point"] == "server.default-header.response-finalization"
            and observation.get("fault_consumed") is True
            and observation.get("connection_closed") is True
        )
    if fault["contract"] == "http2-response-event-fault-consumed-and-status-observed":
        expected_status = (
            500
            if fault["point"]
            in {
                "http.response.early-hint.disconnected",
                "http.response.early-hint.channel-closed",
            }
            else 200
        )
        return (
            observation.get("fault_consumed") is True
            and observation.get("status") == expected_status
        )
    if fault["contract"] == "python-ssl-ca-verifier-error-propagates":
        expected_message = (
            "coverage-injected Python SSL helper failure at " + fault["point"]
        )
        return (
            observation.get("fault_consumed") is True
            and observation.get("response_received") is False
            and observation.get("process_exit_code") == 1
            and observation.get("process_timed_out") is False
            and expected_message in observation.get("fault_server_stderr", "")
        )
    if fault["contract"] == "python-ssl-ca-verifier-success-fallback-propagates":
        return (
            observation.get("fault_consumed") is True
            and observation.get("response_received") is False
            and observation.get("process_exit_code") == 1
            and observation.get("process_timed_out") is False
            and "invalid CA certificate PEM: coverage-injected Rust CA parser failure"
            in observation.get("fault_server_stderr", "")
        )
    if fault["contract"] == "python-ssl-keyfile-error-propagates":
        expected_message = (
            "coverage-injected Python SSL keyfile helper failure at " + fault["point"]
        )
        return (
            observation.get("fault_consumed") is True
            and observation.get("response_received") is False
            and observation.get("process_exit_code") == 1
            and observation.get("process_timed_out") is False
            and expected_message in observation.get("fault_server_stderr", "")
        )
    if fault["contract"] == "python-ssl-keyfile-rust-decrypt-error-propagates":
        return (
            observation.get("fault_consumed") is True
            and observation.get("response_received") is False
            and observation.get("process_exit_code") == 1
            and observation.get("process_timed_out") is False
            and "coverage-injected Rust encrypted private-key decryption failure"
            in observation.get("fault_server_stderr", "")
        )
    if fault["contract"] == "python-pkcs12-reader-error-propagates":
        return (
            observation.get("fault_consumed") is True
            and observation.get("response_received") is False
            and observation.get("process_exit_code") == 1
            and observation.get("process_timed_out") is False
        )
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
    if fault["contract"] == "http3-request-trailers-drained-as-body-only":
        body = observation.get("body_bytes")
        if not isinstance(body, str):
            return False
        try:
            payload = json.loads(base64.b64decode(body, validate=True))
        except (ValueError, json.JSONDecodeError):
            return False
        return (
            observation.get("status") == 200
            and isinstance(payload, dict)
            and payload.get("receive_types")
            and all(event_type == "http.request" for event_type in payload["receive_types"])
            and payload.get("body_base64")
            == base64.b64encode(b"h3-trailer").decode("ascii")
            and "http.request.trailers" not in payload.get("scope_extensions", [])
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
        expected_body = case["request_stream"]["expected_response_body_base64"]
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes") == expected_body
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
            and "uvicorn-rs: WebSocket request failed: WebSocket response header capacity exceeded"
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
                and observation.get("fault_consumed") is True
                and "lifespan.async-finally.started" in events
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
    if fault["contract"] == "http-response-build-error-closes-connection-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") is None
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
        )
    if fault["contract"] in {
        "http-500-then-followup-200", "http-callback-error-followup-200",
        "http-original-task-start-error-followup-200",
    }:
        responses = observation.get("responses")
        if fault["point"] == "asgi.event-type.extract":
            return (
                "coverage-only injected MemoryError at AsgiEventTypeExtract"
                in observation.get("server_log", "")
                and isinstance(responses, list)
                and len(responses) == 2
                and all(isinstance(response, dict) for response in responses)
                and responses[0].get("status") == 500
                and responses[1].get("status") == 200
            )
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
    if fault["contract"] == "http3-legacy-default-header-error-resets-stream":
        return (
            observation.get("fault_consumed") is True
            and (
                observation.get("stream_reset") is True
                or observation.get("connection_closed") is True
            )
        )
    if fault["contract"] == "http3-peer-close-classification-defensive-error":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") in {0, -signal.SIGTERM}
            and observation.get("server_error_observed") is True
        )
    if fault["contract"] == "http3-legacy-peer-close-no-error":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") in {0, -signal.SIGTERM}
            and observation.get("server_error_observed") is False
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-legacy-peer-close-unknown-code-ignored":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") in {0, -signal.SIGTERM}
            and observation.get("server_error_observed") is False
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-legacy-peer-close-classification-error":
        followup = observation.get("followup_response")
        return (
            observation.get("status") == 200
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") in {0, -signal.SIGTERM}
            and observation.get("server_error_observed") is True
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-legacy-handshake-recovery":
        followup = observation.get("followup_response")
        return (
            observation.get("handshake_rejected") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("fault_consumed") is True
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
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-upload-body-pump-preserves-data":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"read-once").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-native-body-pump-pre-poll-cancel-preserves-response":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes")
            == base64.b64encode(b"response-before-upload-complete").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-native-body-pump-sender-closed-preserves-response":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes")
            == base64.b64encode(b"response-before-upload-complete").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-native-body-pump-send-stop-preserves-response":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes")
            == base64.b64encode(b"response-before-upload-complete").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-native-body-pump-final-message-stop-preserves-response":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes")
            == base64.b64encode(b"response-before-upload-complete").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-native-body-pump-final-message-send-error-preserves-response":
        return (
            observation.get("status") == 200
            and observation.get("body_bytes")
            == base64.b64encode(b"response-before-upload-complete").decode("ascii")
            and observation.get("fault_consumed") is True
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
    if fault["contract"] == "http3-legacy-connection-task-shutdown-completes":
        return (
            observation.get("status") == 200
            and observation.get("process_terminated") is True
            and observation.get("process_exit_code") == 0
            and observation.get("fault_consumed") is True
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
    if fault["contract"] == "http2-500-generic-error-body":
        return (
            observation.get("status") == 500
            and observation.get("body_bytes")
            == base64.b64encode(b"Internal Server Error").decode("ascii")
        )
    if fault["contract"] == "http3-client-abort-disconnect-followup":
        followup = observation.get("followup_response")
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "http3-peer-stop-cancels-held-app-followup-200":
        followup = observation.get("followup_response")
        return (
            observation.get("application_cancelled") is True
            and observation.get("application_events")
            == ["request.hold", "request.cancelled"]
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("content_type") == "text/plain; charset=utf-8"
            and followup.get("body_base64")
            == base64.b64encode(b"sync-callable-awaitable").decode("ascii")
            and followup.get("connection_closed") is False
        )
    if fault["contract"] == "http3-peer-stop-open-upload-disconnect-followup-200":
        followup = observation.get("followup_response")
        application_events = observation.get("application_events")
        return (
            observation.get("client_aborted") is True
            and observation.get("application_cancelled") is False
            and observation.get("disconnect_event") is True
            and isinstance(application_events, list)
            and "http3.open-upload.body-received" in application_events
            and "http3.open-upload.body-received:True:7" in application_events
            and "http3.open-upload.waiting-for-disconnect" in application_events
            and "http3.open-upload.disconnected" in application_events
            and "http3.open-upload.cancelled-before-disconnect" not in application_events
            and observation.get("followup_healthy") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("content_type") == "text/plain; charset=utf-8"
            and followup.get("body_base64")
            == base64.b64encode(b"sync-callable-awaitable").decode("ascii")
            and followup.get("connection_closed") is False
        )
    if fault["contract"] == "http3-open-upload-app-return-retires-body-pump":
        followup = observation.get("followup_response")
        application_events = observation.get("application_events")
        return (
            observation.get("status") == 200
            and observation.get("content_type") == "text/plain; charset=utf-8"
            and observation.get("body_bytes")
            == base64.b64encode(b"response-before-open-upload-complete").decode("ascii")
            and observation.get("application_cancelled") is False
            and isinstance(application_events, list)
            and "http3.open-upload-retired.body-received" in application_events
            and "http3.open-upload-retired.body-received:True:7" in application_events
            and "http3.open-upload-retired.response-sent" in application_events
            and "http3.open-upload-retired.receive:http.request:False:0" in application_events
            and "http3.open-upload-retired.followup-drained" in application_events
            and "http3.open-upload-retired.cancelled" not in application_events
            and observation.get("followup_healthy") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("content_type") == "text/plain; charset=utf-8"
            and followup.get("body_base64")
            == base64.b64encode(b"open-upload-followup-healthy").decode("ascii")
            and followup.get("connection_closed") is False
        )
    if fault["contract"] in {
        "http3-peer-stop-after-body-complete-disconnect-followup-200",
        "http3-peer-stop-cancelled-send-disconnect-followup-200",
    }:
        followup = observation.get("followup_response")
        application_events = observation.get("application_events")
        return (
            observation.get("client_aborted") is True
            and observation.get("application_cancelled") is False
            and observation.get("disconnect_event") is True
            and isinstance(application_events, list)
            and "http3.after-body.receive:http.request:True:1" in application_events
            and "http3.after-body.request-complete" in application_events
            and "http3.after-body.waiting-for-disconnect" in application_events
            and "http3.after-body.disconnected" in application_events
            and "http3.after-body.cancelled-before-disconnect" not in application_events
            and observation.get("followup_healthy") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("content_type") == "text/plain; charset=utf-8"
            and followup.get("body_base64")
            == base64.b64encode(b"sync-callable-awaitable").decode("ascii")
            and followup.get("connection_closed") is False
            and (
                fault["contract"]
                != "http3-peer-stop-cancelled-send-disconnect-followup-200"
                or observation.get("fault_consumed") is True
            )
        )
    if fault["contract"] in {
        "http3-body-pump-error-stop-disconnect-followup-200",
        "http3-legacy-body-pump-delivers-disconnect-followup-200",
    }:
        followup = observation.get("followup")
        return (
            observation.get("disconnect_event") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and followup.get("response_header_values_by_name")
            == [["x-asgi-coverage-probe", ["present"]]]
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http3-server-shutdown-force-abort":
        return (
            observation.get("status") == 200
            and observation.get("process_terminated") is True
            and "HTTP/3 shutdown exceeded grace period" in observation.get("server_log", "")
            and observation.get("fault_consumed") is True
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
    if fault["contract"] == "http-native-service-error-close-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") is None
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
        )
    if fault["contract"] == "http-native-connection-write-error-followup-200":
        responses = observation.get("responses")
        return (
            isinstance(responses, list)
            and len(responses) == 2
            and all(isinstance(response, dict) for response in responses)
            and responses[0].get("status") is None
            and responses[0].get("connection_closed") is True
            and responses[1].get("status") == 200
            and observation.get("fault_consumed") is True
            and "uvicorn-rs: HTTP connection from" in observation.get("server_log", "")
            and "HTTP connection failed:" in observation.get("server_log", "")
        )
    if fault["contract"] == "http-concurrent-receive-after-lock-contention":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"first-second").decode("ascii")
            and "coverage observed concurrent HTTP receive lock contention"
            in observation.get("server_log", "")
        )
    if fault["contract"] == "http-request-body-conversion-error-caught":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"request-body-error-caught").decode("ascii")
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http-body-pump-send-stopped-without-response":
        followup = observation.get("followup_response")
        return (
            observation.get("status") in {None, 500}
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "http-body-pump-oversized-frame-echo":
        return (
            observation.get("status") == 200
            and observation.get("ordered_body_bytes")
            == base64.b64encode(b"aabb").decode("ascii")
            and observation.get("fault_consumed") is True
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
    if fault["contract"] == "http-connection-lifetime-closed-disconnect-followup-200":
        followup = observation.get("followup_response")
        # The disconnect runner independently requires the exact
        # wait_event_after_disconnect checkpoint before returning this
        # observation; the public observation schema exposes recovery only.
        return (
            isinstance(followup, dict)
            and followup.get("status") == 200
            and (
                fault["point"] != "http.connection.peer-read-failed.wait-complete"
                or observation.get("fault_consumed") is True
            )
        )
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
    if fault["contract"] == "server-lifespan-startup-auto-fallback-logger-failure-ignored":
        followup = observation.get("followup_response")
        return (
            observation.get("fault_consumed") is True
            and isinstance(followup, dict)
            and followup.get("status") == 200
        )
    if fault["contract"] == "server-shutdown-failure":
        return (
            observation.get("process_terminated") is True
            and isinstance(observation.get("process_exit_code"), int)
            and observation["process_exit_code"] != 0
        )
    if fault["contract"] == "server-startup-cancellation-shutdown-error-propagates":
        return (
            observation.get("fault_consumed") is True
            and observation.get("exit_code") == 0
            and observation.get("lifespan_startup_entered_before_cancel") is True
            and observation.get("server_started_before_cancel") is False
            and observation.get("serve_raised") is True
            and observation.get("serve_cancelled") is False
            and observation.get("serve_task_finished") is True
            and observation.get("server_started_before_shutdown") is False
            # The app may consume Shutdown just before cancellation aborts the
            # task join, so both event traces prove the same fault contract.
            and observation.get("application_events")
            in (
                ["lifespan.startup"],
                ["lifespan.startup", "lifespan.shutdown"],
            )
        )
    if fault["contract"] == "server-startup-bind-shutdown-error-logged":
        # Shutdown is sent before this coverage fault aborts the app task. The
        # task may consume that message first, so both event traces are valid.
        application_events = observation.get("application_events")
        return (
            observation.get("fault_consumed") is True
            and observation.get("exit_code") == 0
            and observation.get("server_started") is False
            and observation.get("serve_task_finished") is True
            and observation.get("serve_raised") is True
            and observation.get("serve_timed_out") is False
            and application_events
            in (
                ["lifespan.startup"],
                ["lifespan.startup", "lifespan.shutdown"],
            )
            and "uvicorn-rs: ASGI lifespan shutdown failed after listener setup error:"
            in observation.get("fault_server_stderr", "")
        )
    if fault["contract"] == "server-lifespan-task-cancel":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and "lifespan.shutdown.hold" in events
            and "lifespan.task-cancelled" in events
        )
    if fault["contract"] == "server-native-connection-error-during-shutdown":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and observation.get("connection_closed") is True
            and observation.get("response_stream_started") is True
            and "lifespan.shutdown" in events
            and "uvicorn-rs: HTTP connection from" in observation.get("server_log", "")
            and "HTTP connection failed:" in observation.get("server_log", "")
        )
    if fault["contract"] == "websocket-server-shutdown-force-abort":
        events = observation.get("application_events", [])
        return (
            observation.get("process_terminated") is True
            and "websocket.hold" in events
            and "websocket.app-cancelled" in events
            and observation.get("fault_consumed") is True
        )
    if fault["contract"] == "websocket-driver-send-error-followup-200":
        followup = observation.get("followup_response")
        return (
            observation.get("handshake_status") == 101
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and observation.get("fault_consumed") is True
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
    if fault["contract"] == "websocket-registration-failure-cancels-app-followup-200":
        events = observation.get("application_events", [])
        followup = observation.get("followup_response")
        held = "websocket.registration-failure.hold"
        cancelled = "websocket.registration-failure.cancelled"
        return (
            observation.get("handshake_status") != 101
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and events.count(held) == 1
            and events.count(cancelled) == 1
            and events.index(held) < events.index(cancelled)
        )
    if fault["contract"] == "websocket-handshake-error-followup-200":
        followup = observation.get("followup_response")
        return (
            (
                observation.get("handshake_status") == 500
                if fault["point"] in {
                    "websocket.accept-key.header-value-error",
                    "websocket.native-upgrade.extension-removed-after-dispatch",
                }
                else observation.get("handshake_status") != 101
            )
            and isinstance(followup, dict)
            and followup.get("status") == 200
            and (
                fault["point"] not in {
                    "websocket.peer-read-failed.wait-complete",
                    "websocket.native-upgrade.extension-removed-after-dispatch",
                }
                or observation.get("fault_consumed") is True
            )
            and (
                fault["point"] != "websocket.accept-key.header-value-error"
                or "uvicorn-rs: WebSocket request failed: failed to parse header value"
                in observation.get("server_log", "")
            )
            and (
                fault["point"]
                != "websocket.native-upgrade.extension-removed-after-dispatch"
                or "uvicorn-rs: WebSocket request failed: WebSocket Upgrade is supported only on HTTP/1.1"
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
        if fault["point"] in {
            "websocket.yawc.unexpected-continuation-frame",
            "websocket.yawc.invalid-text-frame",
            "websocket.yawc.invalid-close-reason",
            "websocket.yawc.close-reply-flush-error",
            "websocket.yawc.close-reply-flush-unexpected-frame",
        }:
            return healthy_followup and observation.get("fault_consumed") is True
        expected_disconnect = {
            "websocket.receive.channel-closed": "websocket.disconnect:1005:",
            "websocket.receive.connection-closed": "websocket.disconnect:1005:",
            "websocket.driver.connection-closed": "websocket.disconnect:1006:",
            "websocket.driver.peer-eof": "websocket.disconnect:1006:",
            "websocket.outgoing.queue-receiver-closed": "websocket.outgoing.queue-closed",
        }.get(fault["point"])
        if expected_disconnect is None:
            return (
                healthy_followup
                and (
                    fault["point"]
                    not in {
                        "websocket.peer-read-failed.unavailable",
                        "websocket.peer-read-failed.watch-fallback",
                    }
                    or observation.get("fault_consumed") is True
                )
            )
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


def run_cli_process(
    case: dict[str, Any],
    server_id: str,
    temporary_directory: Path,
    coverage_profile_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one argv input through the genuine CLI process for each side."""

    process = case["process"]
    python = ORACLE_PYTHON if server_id == "uvicorn" else Path(sys.executable)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONNOUSERSITE"] = "1"
    source_python_path = str(ROOT / "python")
    if server_id == "uvicorn-rs" and not INSTALLED_CANDIDATE_MODE:
        environment["PYTHONPATH"] = source_python_path
    if coverage_profile_dir is not None:
        environment["ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN"] = "1"
        coverage_site = str(ROOT / "tests" / "parity" / "coverage_site")
        environment["PYTHONPATH"] = os.pathsep.join(
            path
            for path in (
                coverage_site,
                source_python_path if server_id == "uvicorn-rs" else None,
            )
            if path
        )
        if server_id == "uvicorn-rs":
            target_profile_dir = coverage_profile_dir / "target"
            target_profile_dir.mkdir(parents=True, exist_ok=True)
            environment["LLVM_PROFILE_FILE"] = str(
                target_profile_dir / "%p-%m.profraw"
            )
            runtime_marker_dir = coverage_profile_dir / "runtime-probe"
            runtime_marker_dir.mkdir(parents=True, exist_ok=True)
            environment["ASGI_PARITY_COVERAGE_RUNTIME_MARKER_DIR"] = str(
                runtime_marker_dir
            )
        else:
            environment.pop("LLVM_PROFILE_FILE", None)
            environment.pop("ASGI_PARITY_COVERAGE_RUNTIME_MARKER_DIR", None)
    for name, value in process["environment"].items():
        if name == "PYTHONPATH" and server_id == "uvicorn-rs":
            environment[name] = os.pathsep.join(
                path
                for path in (
                    environment.get("PYTHONPATH"),
                    value,
                )
                if path
            )
            continue
        if name == "PYTHONPATH" and coverage_profile_dir is not None:
            environment[name] = os.pathsep.join(
                path for path in (coverage_site, value) if path
            )
            continue
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    working_directory = (
        ROOT
        if process["working_directory"] == "project"
        else temporary_directory
    )
    working_directory.mkdir(parents=True, exist_ok=True)
    if process["invocation"] == "module":
        command = [str(python), "-m", "uvicorn", *process["arguments"]]
    else:
        script_directory = subprocess.run(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('scripts'))"],
            cwd=working_directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        script_name = "uvicorn.exe" if os.name == "nt" else "uvicorn"
        script = Path(script_directory) / script_name
        if not script.is_file():
            raise ParityError(f"{case['case_id']}: installed uvicorn console script is missing: {script}")
        command = [str(script), *process["arguments"]]
    completed = subprocess.run(
        command,
        cwd=working_directory,
        env=environment,
        capture_output=True,
        timeout=process["timeout_seconds"],
        check=False,
    )
    if len(completed.stdout) > 4 * 1024 * 1024 or len(completed.stderr) > 4 * 1024 * 1024:
        raise ParityError(f"{case['case_id']}: CLI output exceeded the 4 MiB evidence bound")
    return {
        "exit_code": completed.returncode,
        "stdout_base64": base64.b64encode(completed.stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(completed.stderr).decode("ascii"),
    }


def execute_cli_profile(
    profile: dict[str, Any],
    cases: list[dict[str, Any]],
    operations: dict[str, dict[str, Any]],
    coverage_profile_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-parity-cli-") as temporary:
        temporary_directory = Path(temporary)
        for case in cases:
            operation = operations[case["operation"]]
            try:
                oracle = run_cli_process(
                    case,
                    "uvicorn",
                    temporary_directory / "cwd",
                    coverage_profile_dir,
                )
                target = run_cli_process(
                    case,
                    "uvicorn-rs",
                    temporary_directory / "cwd",
                    coverage_profile_dir,
                )
                fields = operation.get("compare", operation["observe"])
                oracle_comparison = normalize_operation_comparison_observation(
                    {field: oracle[field] for field in fields}, operation
                )
                target_comparison = normalize_operation_comparison_observation(
                    {field: target[field] for field in fields}, operation
                )
                matches = oracle_comparison == target_comparison
                difference = None
                if not matches:
                    differing_fields = [
                        field
                        for field in fields
                        if oracle[field] != target[field]
                    ]
                    difference = "CLI process observations differ: " + ", ".join(differing_fields)
                outcomes.append({
                    "case_id": case["case_id"],
                    "profile": profile["id"],
                    "operation": case["operation"],
                    "requirements": case["covers"],
                    "status": "passed" if matches else "failed",
                    "oracle_observation": oracle,
                    "target_observation": target,
                    "server_exit_codes": {
                        "oracle": oracle["exit_code"],
                        "target": target["exit_code"],
                    },
                    "difference": difference,
                })
                print(
                    f"{'PASS' if matches else 'FAIL'} {profile['id']}: {case['case_id']}",
                    flush=True,
                )
            except Exception as error:
                outcomes.append({
                    "case_id": case["case_id"],
                    "profile": profile["id"],
                    "operation": case["operation"],
                    "requirements": case["covers"],
                    "status": "infrastructure_failed",
                    "error": {"class": type(error).__name__, "message": str(error)[:5000]},
                })
                print(f"ERROR {profile['id']}: {case['case_id']}: {error}", flush=True)
        add_verification_metadata(outcomes, cases)
    return outcomes, []


def _python_api_server_log_events(
    run_http_observation: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    """Normalize server logs to stable events while retaining raw bytes in evidence."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    level_prefix = re.compile(r"^(TRACE|DEBUG|INFO|WARNING|ERROR|CRITICAL):\s*(.*)$")
    access_line = re.compile(
        r'^(?P<client>.+):(?P<client_port>\d+) - "(?P<request>.*)" '
        r'(?P<status>\d{3})(?: (?P<phrase>.*))?$'
    )
    running_line = re.compile(
        r"^(?P<prefix>Uvicorn running on https?://.+):(?P<port>\d+)"
        r"(?P<suffix> \(Press CTRL\+C to quit\))$"
    )
    fd_socket_running_line = re.compile(
        r"^Uvicorn running on socket \((?P<host>[^,]+), (?P<port>\d+)"
        r"(?P<tail>(?:, \d+, \d+)?)\) (?P<suffix>\(Press CTRL\+C to quit\))$"
    )
    unix_socket_running_line = re.compile(
        r"^Uvicorn running on unix socket .+ \(Press CTRL\+C to quit\)$"
    )
    process_pid = re.compile(
        r"(((?:Started|Finished) server|(?:Started|Stopping) (?:parent|reloader)|"
        r"(?:Terminated|Waiting for) child|Child) process \[)\d+(\])"
    )
    worker_restart_pid = re.compile(r"((?:New child process|keeping worker) \[)\d+(\])")
    exception_line = re.compile(r"^(?P<class>[A-Za-z_][\w.]*)\b(?:: ?(?P<message>.*))?$")
    proactor_accept_callback = (
        "Exception in callback BaseProactorEventLoop._start_serving.<locals>.loop("
    )
    coverage_body_pump_join = re.compile(
        r"^uvicorn-rs: request-body pumps joined: [1-9]\d*$"
    )
    shutdown_trace = re.compile(
        r"^uvicorn-rs: shutdown-trace (?:"
        r"pid=\d+ |"
        r"python t_ns=\d+ pid=\d+ thread=[^ ]+ "
        r")"
    )

    normalized: dict[str, list[dict[str, str]]] = {"stdout": [], "stderr": []}
    custom_level_prefix = re.compile(
        r"^PARITY (TRACE|DEBUG|INFO|WARNING|ERROR|CRITICAL) ([A-Za-z_][\w.]*)?: (.*)$"
    )
    for channel in normalized:
        encoded = run_http_observation.get(f"server_{channel}_base64", "")
        try:
            content = base64.b64decode(encoded).decode("utf-8", errors="replace")
        except (ValueError, TypeError) as error:
            raise ParityError(f"Python API server {channel} log is not valid base64") from error
        lines = content.splitlines()
        index = 0
        saw_ansi_colors = False
        while index < len(lines):
            if ansi_escape.search(lines[index]) and not saw_ansi_colors:
                normalized[channel].append({"kind": "ansi-colors"})
                saw_ansi_colors = True
            line = ansi_escape.sub("", lines[index])
            if shutdown_trace.match(line):
                index += 1
                continue
            # This lifecycle count is emitted only by coverage builds. Keep it
            # in the raw logs, but don't treat the coverage diagnostic as a
            # Uvicorn-visible server event in the input-only parity contract.
            if coverage_body_pump_join.fullmatch(line):
                index += 1
                continue
            if not line:
                index += 1
                continue
            # On Windows, asyncio's Proactor loop can emit this callback
            # traceback after an invalid response closes the accepted socket.
            # It is event-loop implementation noise rather than a Uvicorn
            # server log event; retain the original bytes in the evidence,
            # while comparing the server-level exception above it.
            if line.startswith(proactor_accept_callback):
                index += 1
                while index < len(lines):
                    candidate = ansi_escape.sub("", lines[index])
                    index += 1
                    if candidate == "AssertionError":
                        break
                continue
            if line == "Exception in ASGI application" and index + 1 < len(lines):
                exception = exception_line.match(
                    ansi_escape.sub("", lines[index + 1])
                )
                if exception:
                    normalized[channel].append(
                        {"kind": "raw", "message": line}
                    )
                    normalized[channel].append(
                        {
                            "kind": "exception",
                            "class": exception.group("class"),
                            "message": exception.group("message") or "",
                        }
                    )
                    index += 2
                    continue
            if line == "During handling of the above exception, another exception occurred:":
                normalized[channel].append({"kind": "traceback-chain"})
                index += 1
                continue
            if line == "Traceback (most recent call last):":
                index += 1
                while index < len(lines):
                    candidate = ansi_escape.sub("", lines[index])
                    if not candidate or candidate.startswith(" "):
                        index += 1
                        continue
                    match = exception_line.match(candidate)
                    if match:
                        normalized[channel].append(
                            {
                                "kind": "exception",
                                "class": match.group("class"),
                                "message": match.group("message") or "",
                            }
                        )
                        index += 1
                    break
                continue

            custom_level_match = custom_level_prefix.match(line)
            if custom_level_match is not None:
                level, logger, message = custom_level_match.groups()
            else:
                level_match = level_prefix.match(line)
                if level_match is None:
                    normalized[channel].append({"kind": "raw", "message": line})
                    index += 1
                    continue
                level, message = level_match.groups()
                logger = None

            access_match = access_line.match(message)
            if access_match:
                event = {
                    "kind": "access",
                    "level": level,
                    "client": f"{access_match.group('client')}:<port>",
                    "request": access_match.group("request"),
                    "status": " ".join(
                        part
                        for part in (access_match.group("status"), access_match.group("phrase"))
                        if part
                    ),
                }
                if logger is not None:
                    event["logger"] = logger
                normalized[channel].append(event)
                index += 1
                continue

            running_match = running_line.match(message)
            if running_match:
                message = (
                    f"{running_match.group('prefix')}:<port>"
                    f"{running_match.group('suffix')}"
                )
            else:
                fd_socket_match = fd_socket_running_line.match(message)
                if fd_socket_match:
                    message = (
                        "Uvicorn running on socket ("
                        f"{fd_socket_match.group('host')}, <port>"
                        f"{fd_socket_match.group('tail')}) "
                        f"{fd_socket_match.group('suffix')}"
                    )
            if unix_socket_running_line.match(message):
                message = "Uvicorn running on unix socket <uds> (Press CTRL+C to quit)"
            message = process_pid.sub(r"\1<pid>\3", message)
            message = worker_restart_pid.sub(r"\1<pid>\2", message)
            if (
                os.name == "nt"
                and channel == "stderr"
                and message == "Terminated child process [<pid>]"
            ):
                # Multiprocess.terminate() emits this informational message
                # only when the child has not exited at the instant the
                # parent checks its exit code. On Windows, Ctrl+Break also
                # reaches the workers, so scheduler timing determines whether
                # they exit before the parent's terminate loop. The process
                # exit and timeout observations remain part of parity; this
                # race-dependent log line does not.
                index += 1
                continue
            event = {"kind": "message", "level": level, "message": message}
            if logger is not None:
                event["logger"] = logger
            normalized[channel].append(event)
            index += 1
    # Worker processes emit the same lifecycle phases concurrently. Their
    # cross-process log order is scheduler-dependent, and parent-process
    # messages can split the events from one phase across several log runs.
    # For multiprocess runs, compare the complete worker lifecycle sequence
    # canonically while retaining every event and its multiplicity. Keep
    # parent and application log events in their original relative order.
    lifecycle_order = {
        "Started server process [<pid>]": 0,
        "Waiting for application startup.": 1,
        "Application startup complete.": 2,
        "Shutting down": 3,
        "Waiting for application shutdown.": 4,
        "Application shutdown complete.": 5,
        "Finished server process [<pid>]": 6,
    }
    stderr_events = normalized["stderr"]
    def lifecycle_phase(event: dict[str, str]) -> int | None:
        message = event.get("message")
        if message is None:
            return None
        return next(
            (
                order
                for prefix, order in lifecycle_order.items()
                if message == prefix or message.startswith(prefix)
            ),
            None,
        )

    has_parent_process = any(
        event.get("message", "").startswith("Started parent process [")
        for event in stderr_events
    )
    if has_parent_process:
        worker_events: list[dict[str, str]] = []
        other_events: list[dict[str, str]] = []
        insertion_index = None
        for event in stderr_events:
            if lifecycle_phase(event) is not None:
                if insertion_index is None:
                    insertion_index = len(other_events)
                worker_events.append(event)
            else:
                other_events.append(event)
        if insertion_index is not None:
            worker_events.sort(key=lambda event: lifecycle_phase(event) or 0)
            other_events[insertion_index:insertion_index] = worker_events
            stderr_events[:] = other_events
    else:
        index = 0
        while index < len(stderr_events):
            if lifecycle_phase(stderr_events[index]) is None:
                index += 1
                continue
            end = index + 1
            while end < len(stderr_events) and lifecycle_phase(stderr_events[end]) is not None:
                end += 1
            stderr_events[index:end] = sorted(
                stderr_events[index:end],
                key=lambda event: lifecycle_phase(event) or 0,
            )
            index = end

    # Invalid default headers make the probe's client retry until shutdown.
    # The number of retries depends on how quickly each server rejects a
    # request, so compare the exception event once while preserving its order
    # relative to other server logs.
    for channel, events in normalized.items():
        collapsed: list[dict[str, str]] = []
        index = 0
        while index < len(events):
            is_trailing_partial_header_failure = (
                index == len(events) - 1
                and events[index]
                == {"kind": "raw", "message": "Exception in ASGI application"}
                and len(collapsed) >= 2
                and collapsed[-2]
                == {"kind": "raw", "message": "Exception in ASGI application"}
                and collapsed[-1].get("kind") == "exception"
                and collapsed[-1].get("class") == "RuntimeError"
                and collapsed[-1].get("message")
                in {"Invalid HTTP header name.", "Invalid HTTP header value."}
            )
            if is_trailing_partial_header_failure:
                index += 1
                continue
            is_default_header_failure = (
                index + 1 < len(events)
                and events[index]
                == {"kind": "raw", "message": "Exception in ASGI application"}
                and events[index + 1].get("kind") == "exception"
                and events[index + 1].get("class") == "RuntimeError"
                and events[index + 1].get("message")
                in {"Invalid HTTP header name.", "Invalid HTTP header value."}
            )
            if not is_default_header_failure:
                collapsed.append(events[index])
                index += 1
                continue
            pair = events[index : index + 2]
            if len(collapsed) < 2 or collapsed[-2:] != pair:
                collapsed.extend(pair)
            index += 2
        normalized[channel] = collapsed
    return normalized


def run_python_api_probe(
    case: dict[str, Any],
    server_id: str,
    coverage_profile_dir: Path | None = None,
    fault_point: str | None = None,
) -> dict[str, Any]:
    """Run one input-selected Python public-surface probe on each interpreter."""

    python = ORACLE_PYTHON if server_id == "uvicorn" else Path(sys.executable)
    environment = os.environ.copy()
    environment.pop("UVICORN_RS_COVERAGE_FAULT_FILE", None)
    fault_control_directory = None
    fault_control_path = None
    fault_consumed = None
    if fault_point is not None:
        if server_id != "uvicorn-rs":
            raise ParityError("Python API fault contracts run only against uvicorn-rs")
        fault_control_directory = tempfile.TemporaryDirectory(
            prefix="uvicorn-rs-python-api-fault-"
        )
        fault_control_path = Path(fault_control_directory.name) / "coverage-fault.txt"
        fault_control_path.write_text(fault_point, encoding="utf-8")
        environment["UVICORN_RS_COVERAGE_FAULT_FILE"] = str(fault_control_path)
    coverage_capture_shutdown = (
        os.environ.get("ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN") == "1"
    )
    coverage_site = str(ROOT / "tests" / "parity" / "coverage_site")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["ASGI_PARITY_SERVER_ID"] = server_id
    if (
        os.name == "nt"
        and server_id == "uvicorn"
        and os.environ.get("UVICORN_RS_TRACE_ORACLE_SIGNAL") == "1"
    ):
        environment["ASGI_PARITY_TRACE_ORACLE_SIGNAL"] = "1"
    source_python_path = str(ROOT / "python")
    target_source_path = (
        source_python_path
        if server_id == "uvicorn-rs" and not INSTALLED_CANDIDATE_MODE
        else None
    )
    if target_source_path is not None:
        environment["PYTHONPATH"] = target_source_path
    if os.environ.get("ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN") == "1":
        # The parent signals after observing the server. The coverage-only
        # site hook keeps both implementations on a normal exit path so LLVM
        # can flush the target profile.
        environment["ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN"] = "1"
        environment["PYTHONPATH"] = os.pathsep.join(
            path for path in (coverage_site, target_source_path) if path
        )
    probe_api = dict(case["api"])
    run_http = case["api"].get("run_http", {})
    probe_run_http = dict(run_http)
    temporary_tls_assets = None
    if run_http.get("ssl_ca_certs") in {
        "generated-ca",
        "trusted-ca",
        "empty-ca",
        "missing-ca",
        "directory-ca",
        "malformed-ca",
        "invalid-der-ca",
        "non-utf8-ca",
    } or run_http.get("client_tls"):
        temporary_tls_assets = tempfile.TemporaryDirectory(
            prefix="uvicorn-rs-python-api-tls-"
        )
        tls_directory = Path(temporary_tls_assets.name)
        certificate, key, ca_certificate = make_certificate(tls_directory)
        tls_assets = {
            "server_certificate": str(certificate),
            "server_key": str(key),
            "ca_certificate": str(ca_certificate),
        }
        if run_http.get("ssl_ca_certs") == "trusted-ca":
            trusted_ca_certificate = tls_directory / "trusted-ca.pem"
            trusted_ca_certificate.write_bytes(
                Path(ca_certificate)
                .read_bytes()
                .replace(
                    b"-----BEGIN CERTIFICATE-----",
                    b"-----BEGIN TRUSTED CERTIFICATE-----",
                )
                .replace(
                    b"-----END CERTIFICATE-----",
                    b"-----END TRUSTED CERTIFICATE-----",
                )
            )
            tls_assets["trusted_ca_certificate"] = str(trusted_ca_certificate)
        if run_http.get("ssl_ca_certs") == "empty-ca":
            empty_ca_certificate = tls_directory / "empty-ca.pem"
            empty_ca_certificate.write_bytes(b"")
            tls_assets["empty_ca_certificate"] = str(empty_ca_certificate)
        if run_http.get("ssl_ca_certs") == "missing-ca":
            tls_assets["missing_ca_certificate"] = str(tls_directory / "missing-ca.pem")
        if run_http.get("ssl_ca_certs") == "directory-ca":
            directory_ca = tls_directory / "directory-ca"
            directory_ca.mkdir()
            tls_assets["directory_ca"] = str(directory_ca)
        if run_http.get("ssl_ca_certs") == "malformed-ca":
            malformed_ca_certificate = tls_directory / "malformed-ca.pem"
            malformed_ca_certificate.write_bytes(
                b"-----BEGIN CERTIFICATE-----\nnot-base64!\n-----END CERTIFICATE-----\n"
            )
            tls_assets["malformed_ca_certificate"] = str(malformed_ca_certificate)
        if run_http.get("ssl_ca_certs") == "invalid-der-ca":
            invalid_der_ca_certificate = tls_directory / "invalid-der-ca.pem"
            invalid_der_ca_certificate.write_bytes(
                b"-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----\n"
            )
            tls_assets["invalid_der_ca_certificate"] = str(invalid_der_ca_certificate)
        if run_http.get("ssl_ca_certs") == "non-utf8-ca":
            non_utf8_ca_certificate = tls_directory / "non-utf8-ca.pem"
            non_utf8_ca_certificate.write_bytes(b"\xff\xfe\x00not a PEM certificate\n")
            tls_assets["non_utf8_ca_certificate"] = str(non_utf8_ca_certificate)
        if run_http.get("client_tls"):
            client_certificate, client_key = make_client_certificate(tls_directory)
            tls_assets.update(
                {
                    "client_certificate": str(client_certificate),
                    "client_key": str(client_key),
                }
            )
        probe_run_http["_tls_assets"] = tls_assets
    if "run_http" in probe_api:
        probe_api["run_http"] = probe_run_http
    run_http_reload = case["api"].get("run_http_reload")
    for name, value in run_http.get("environment", {}).items():
        if name == "PYTHONPATH" and target_source_path is not None:
            if value is not None:
                environment[name] = os.pathsep.join(
                    path for path in (target_source_path, value) if path
                )
            continue
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    if coverage_capture_shutdown:
        case_pythonpath = run_http.get("environment", {}).get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            path
            for path in (coverage_site, target_source_path, case_pythonpath)
            if path
        )
        environment["ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN"] = "1"
    if server_id == "uvicorn-rs" and coverage_profile_dir is not None:
        environment["LLVM_PROFILE_FILE"] = str(
            coverage_profile_dir / "%p-%m.profraw"
        )
        runtime_marker_dir = coverage_profile_dir / "runtime-probe"
        runtime_marker_dir.mkdir(parents=True, exist_ok=True)
        environment["ASGI_PARITY_COVERAGE_RUNTIME_MARKER_DIR"] = str(
            runtime_marker_dir
        )
    command = [
        str(python),
        str(ROOT / "tests/parity/python_api_probe.py"),
        json.dumps(probe_api, sort_keys=True, separators=(",", ":")),
    ]
    # The probe can use one deadline for startup/request, another for reload,
    # and a final one for graceful shutdown. Keep the outer process bound above
    # the work it is supervising so timeout evidence comes from the probe.
    if "run_http" in case["api"]:
        probe_timeout = max(10, 2 * run_http.get("timeout_seconds", 5) + 10)
    elif run_http_reload is not None:
        probe_timeout = max(10, 3 * run_http_reload["timeout_seconds"] + 10)
    else:
        probe_timeout = 10
    probe_options = {}
    if os.name == "nt" and (
        "run_http" in case["api"] or "run_http_reload" in case["api"]
    ):
        # Windows HTTP probes signal their server processes. Give every probe
        # a private console so those events cannot interrupt the parity
        # coordinator sharing the runner console.
        probe_options["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            timeout=probe_timeout,
            check=False,
            **probe_options,
        )
        if fault_control_path is not None:
            fault_consumed = (
                fault_control_path.read_text(encoding="utf-8").strip() == ""
            )
    finally:
        if temporary_tls_assets is not None:
            temporary_tls_assets.cleanup()
        if fault_control_directory is not None:
            fault_control_directory.cleanup()
    if len(completed.stdout) > 4 * 1024 * 1024 or len(completed.stderr) > 4 * 1024 * 1024:
        raise ParityError(f"{case['case_id']}: Python API probe output exceeded the 4 MiB evidence bound")
    observation = {
        "exit_code": completed.returncode,
        "stdout_base64": base64.b64encode(completed.stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(completed.stderr).decode("ascii"),
    }
    if case["operation"] == "python.api.server-serve-cancellation":
        try:
            cancellation = json.loads(completed.stdout)["server_serve_cancellation"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: serve cancellation probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(cancellation) is not dict:
            raise ParityError(
                f"{case['case_id']}: serve cancellation observation must be an object"
            )
        observation.update(
            {
                name: cancellation.get(name)
                for name in (
                    "lifespan_startup_entered_before_cancel",
                    "server_started_before_cancel",
                    "serve_cancelled",
                    "serve_task_finished",
                    "listener_accepting_after_cancel",
                )
            }
        )
    if case["operation"] in {
        "python.api.run-http-reload",
        "python.api.run-http-reload-filters",
    }:
        try:
            reload_observation = json.loads(completed.stdout)["run_http_reload"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: reload probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(reload_observation) is not dict:
            raise ParityError(
                f"{case['case_id']}: reload API observation must be an object"
            )
        observation.update(
            {
                name: reload_observation.get(name)
                for name in (
                    "first_response_body_base64",
                    "second_response_body_base64",
                    "reload_observed",
                    "excluded_change_reloaded",
                    "included_change_reloaded",
                    "shutdown_signal_sent",
                    "process_exit_code",
                    "process_timed_out",
                    "process_stdout_base64",
                    "process_stderr_base64",
                    "workers_ignored_warning",
                )
            }
        )
    if case["operation"] in {
        "python.api.run-http",
        "python.api.run-http-incomplete-header",
        "python.api.run-http-signal-sequence",
        "python.api.run-http-graceful-timeout",
        "python.api.run-http-request-limit",
        "python.api.run-http-asgi-scope-contract",
        "python.api.run-http-concurrency",
        "python.api.run-http-bind-conflict",
        "python.api.run-http-uds-bind-conflict",
    }:
        try:
            run_http_observation = json.loads(completed.stdout)["run_http"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: HTTP API probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(run_http_observation) is not dict:
            raise ParityError(f"{case['case_id']}: HTTP API observation must be an object")
        shutdown_trace_output = os.environ.get("UVICORN_RS_SHUTDOWN_TRACE_OUTPUT")
        trace_oracle_signal = (
            server_id == "uvicorn"
            and os.environ.get("UVICORN_RS_TRACE_ORACLE_SIGNAL") == "1"
        )
        if shutdown_trace_output and (server_id == "uvicorn-rs" or trace_oracle_signal):
            encoded_stderr = run_http_observation.get("server_stderr_base64", "")
            try:
                server_stderr = base64.b64decode(
                    encoded_stderr, validate=True
                ).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                server_stderr = ""
            trace_lines = [
                line
                for line in server_stderr.splitlines()
                if line.startswith("uvicorn-rs: shutdown-trace ")
            ]
            if trace_lines:
                trace_path = Path(shutdown_trace_output)
                trace_path.parent.mkdir(parents=True, exist_ok=True)
                with trace_path.open("a", encoding="utf-8") as trace_file:
                    for line in trace_lines:
                        trace_file.write(f"{case['case_id']} {line}\n")
        observation.update(
            {
                name: run_http_observation.get(name)
                for name in (
                    "response_received",
                    "response_status",
                    "raw_connection_open_after_timeout",
                    "response_content_type",
                    "response_body_base64",
                    "listener_responses",
                    "idle_connection_closed",
                    "shutdown_signal_sent",
                    "shutdown_signals_sent",
                    "process_exit_code",
                    "process_timed_out",
                    "graceful_shutdown_cancellation_observed",
                    "request_limit_response_count",
                    "request_limit_range_satisfied",
                )
            }
        )
        if fault_point is not None:
            encoded_stderr = run_http_observation.get("server_stderr_base64", "")
            try:
                fault_server_stderr = base64.b64decode(
                    encoded_stderr, validate=True
                ).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                fault_server_stderr = ""
            observation["fault_consumed"] = fault_consumed
            observation["fault_server_stderr"] = fault_server_stderr
        server_log_events = _python_api_server_log_events(run_http_observation)
        observation["server_log_events"] = server_log_events
        stderr_events = server_log_events["stderr"]
        child_exit_count = sum(
            event.get("kind") == "message"
            and event.get("message") == "Child process [<pid>] died"
            for event in stderr_events
        )
        worker_start_count = sum(
            event.get("kind") == "message"
            and event.get("message", "").startswith("Started server process [")
            for event in stderr_events
        )
        observation["worker_replacement_observed"] = (
            child_exit_count > 0
            and worker_start_count
            > case["api"]["run_http"].get("workers", 1)
        )
        observation["bind_error_logged"] = any(
            "bind" in event.get("message", "").lower()
            and (
                "already in use" in event.get("message", "").lower()
                or "only one usage of each socket address"
                in event.get("message", "").lower()
            )
            for channel in server_log_events.values()
            for event in channel
        )
    if "server_lifespan_startup" in case["api"]:
        try:
            startup = json.loads(completed.stdout)["server_lifespan_startup"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: server lifespan API probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(startup) is not dict:
            raise ParityError(f"{case['case_id']}: server lifespan API observation must be an object")
        observation.update(
            {
                name: startup.get(name)
                for name in (
                    "server_started_before_shutdown",
                    "serve_task_finished_before_shutdown",
                    "serve_raised",
                    "serve_timed_out",
                    "server_exit_code",
                    "serve_exception_class",
                    "serve_exception_message",
                )
            }
        )
    if "server_startup_failure_waiter" in case["api"]:
        try:
            startup = json.loads(completed.stdout)["server_startup_failure_waiter"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: startup failure waiter returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(startup) is not dict:
            raise ParityError(
                f"{case['case_id']}: startup failure waiter observation must be an object"
            )
        observation.update(
            {
                name: startup.get(name)
                for name in (
                    "startup_failure_wait_result",
                    "dropped_control_wait_result",
                    "server_started_before_shutdown",
                    "serve_task_finished_before_shutdown",
                )
            }
        )
    if "server_startup_bind_failure_lifespan_cleanup" in case["api"]:
        try:
            startup = json.loads(completed.stdout)[
                "server_startup_bind_failure_lifespan_cleanup"
            ]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: startup bind-failure lifespan probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(startup) is not dict:
            raise ParityError(
                f"{case['case_id']}: startup bind-failure lifespan observation must be an object"
            )
        observation.update(
            {
                name: startup.get(name)
                for name in (
                    "server_started",
                    "serve_task_finished",
                    "serve_raised",
                    "serve_timed_out",
                    "application_events",
                )
            }
        )
        if fault_point is not None:
            observation["fault_server_stderr"] = completed.stderr.decode(
                "utf-8", errors="replace"
            )
    if "server_startup_uds_socket_replacement_lifespan_cleanup" in case["api"]:
        try:
            startup = json.loads(completed.stdout)[
                "server_startup_uds_socket_replacement_lifespan_cleanup"
            ]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: startup UDS replacement lifespan probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(startup) is not dict:
            raise ParityError(
                f"{case['case_id']}: startup UDS replacement lifespan observation must be an object"
            )
        observation.update(
            {
                name: startup.get(name)
                for name in (
                    "server_started",
                    "serve_task_finished",
                    "serve_raised",
                    "serve_timed_out",
                    "application_events",
                )
            }
        )
        if fault_point is not None:
            observation["fault_consumed"] = fault_consumed
    if (
        "server_startup_cancel_before_listener" in case["api"]
        or "server_startup_cancel_without_lifespan" in case["api"]
        or "server_startup_cancel_during_prebound_transfer" in case["api"]
        or "server_startup_cancel_during_prebound_transfer_without_lifespan" in case["api"]
    ):
        try:
            startup = json.loads(completed.stdout)["server_startup_cancel_before_listener"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: startup cancellation probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(startup) is not dict:
            raise ParityError(
                f"{case['case_id']}: startup cancellation observation must be an object"
            )
        observation.update(
            {
                name: startup.get(name)
                for name in (
                    "lifespan_startup_entered_before_cancel",
                    "server_started_before_cancel",
                    "serve_cancelled",
                    "serve_raised",
                    "serve_timed_out",
                    "serve_task_finished",
                    "application_events",
                    "server_started_before_shutdown",
                    "listener_transfer_blocked",
                )
            }
        )
    if "server_lifespan_mode" in case["api"]:
        try:
            mode_observation = json.loads(completed.stdout)["server_lifespan_mode"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: server lifespan mode probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(mode_observation) is not dict:
            raise ParityError(
                f"{case['case_id']}: server lifespan mode observation must be an object"
            )
        observation.update(
            {
                name: mode_observation.get(name)
                for name in (
                    "server_started_before_shutdown",
                    "serve_raised",
                    "application_events",
                )
            }
        )
    if "module_cli_lifespan_startup" in case["api"]:
        try:
            startup = json.loads(completed.stdout)["module_cli_lifespan_startup"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: module CLI lifespan probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(startup) is not dict:
            raise ParityError(f"{case['case_id']}: module CLI lifespan observation must be an object")
        observation.update(
            {
                name: startup.get(name)
                for name in (
                    "process_exit_code",
                    "process_timed_out",
                    "process_stderr_has_unhandled_task_warning",
                )
            }
        )
    if "run_websocket" in case["api"]:
        try:
            response = json.loads(completed.stdout)
            websocket = response["run_websocket"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ParityError(
                f"{case['case_id']}: WebSocket API probe returned no structured observation; "
                f"exit={completed.returncode}, "
                f"stdout={completed.stdout.decode('utf-8', errors='replace')[:2000]!r}, "
                f"stderr={completed.stderr.decode('utf-8', errors='replace')[:2000]!r}"
            ) from error
        if type(websocket) is not dict:
            raise ParityError(f"{case['case_id']}: WebSocket API observation must be an object")
        observation.update(
            {
                "handshake_status": websocket.get("handshake_status"),
                "close_code": websocket.get("close_code"),
                "message_received": websocket.get("message_received"),
                "shutdown_signal_sent": websocket.get("shutdown_signal_sent"),
                "process_exit_code": websocket.get("process_exit_code"),
                "process_timed_out": websocket.get("process_timed_out"),
                "compression_negotiated": websocket.get("compression_negotiated"),
                "server_ping_observed": websocket.get("server_ping_observed"),
            }
        )
        if "scope_observation" in websocket:
            scope_observation = websocket["scope_observation"]
            if scope_observation is not None and type(scope_observation) is not dict:
                raise ParityError(
                    f"{case['case_id']}: WebSocket scope observation must be an object or null"
                )
            if (
                case["api"]["run_websocket"].get("observe_scope", False)
                and scope_observation is None
            ):
                raise ParityError(
                    f"{case['case_id']}: requested WebSocket scope observation is missing"
                )
            observation["scope_observation"] = scope_observation
    if fault_point is not None:
        observation["fault_consumed"] = fault_consumed
    return observation


def raise_if_llvm_profile_write_failed(
    observation: dict[str, Any], case_id: str
) -> None:
    """Treat LLVM runtime profile write diagnostics as coverage infrastructure failures.

    Coverage-instrumented subprocesses report profile output errors on their
    captured server logs. Those diagnostics can otherwise look like a server
    parity mismatch and hide a transient disk or filesystem failure.
    """
    server_log_events = observation.get("server_log_events")
    if type(server_log_events) is not dict:
        return
    for channel in ("stdout", "stderr"):
        events = server_log_events.get(channel)
        if type(events) is not list:
            continue
        for event in events:
            if type(event) is not dict or event.get("kind") != "raw":
                continue
            message = event.get("message")
            if (
                isinstance(message, str)
                and message.startswith("LLVM Profile Error: Failed to write file")
            ):
                raise OSError(
                    f"{case_id}: LLVM coverage profile could not be written: "
                    f"{message[:1000]}"
                )


def required_observations_for_case(
    case: dict[str, Any], operation: dict[str, Any]
) -> dict[str, Any]:
    """Return operation requirements with any input-case override applied."""
    if "required_observations" in case:
        return case["required_observations"]
    run_http = case.get("api", {}).get("run_http", {})
    return run_http.get(
        "required_observations", operation.get("required_observations", {})
    )


def execute_python_api_profile(
    profile: dict[str, Any],
    cases: list[dict[str, Any]],
    operations: dict[str, dict[str, Any]],
    coverage_profile_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outcomes = []
    for case in cases:
        operation = operations[case["operation"]]
        try:
            if case.get("verification") == "fault-contract":
                fault = case["fault"]
                target_raw = run_python_api_probe(
                    case,
                    "uvicorn-rs",
                    coverage_profile_dir / "target"
                    if coverage_profile_dir is not None
                    else None,
                    fault_point=fault["point"],
                )
                raise_if_llvm_profile_write_failed(target_raw, case["case_id"])
                target = {name: target_raw[name] for name in operation["observe"]}
                required = (
                    {}
                    if fault["contract"]
                    == "server-unix-listener-permission-error-startup-propagates"
                    else required_observations_for_case(case, operation)
                )
                matches = all(
                    target.get(field) == value
                    for field, value in required.items()
                )
                target_requirements = operation.get("target_requirements", {})
                matches = matches and all(
                    target.get(field) == value
                    for field, value in target_requirements.items()
                )
                fault_observation = {
                    "fault_consumed": target_raw.get("fault_consumed"),
                    "fault_server_stderr": target_raw.get(
                        "fault_server_stderr", ""
                    ),
                    **target,
                }
                contract_matches = fault_contract_matches(
                    fault, fault_observation, case
                )
                matches = matches and contract_matches
                difference = (
                    None
                    if matches
                    else f"fault contract {fault['contract']!r} did not hold"
                )
                outcomes.append(
                    {
                        "case_id": case["case_id"],
                        "profile": profile["id"],
                        "operation": case["operation"],
                        "requirements": case["covers"],
                        "status": "passed" if matches else "failed",
                        "oracle_observation": None,
                        "target_observation": target,
                        "server_exit_codes": {
                            "oracle": None,
                            "target": target.get("exit_code")
                        },
                        "difference": difference,
                    }
                )
                print(
                    f"{'PASS' if matches else 'FAIL'} {profile['id']}: {case['case_id']}",
                    flush=True,
                )
                continue
            oracle_raw = run_python_api_probe(case, "uvicorn")
            target_raw = run_python_api_probe(
                case,
                "uvicorn-rs",
                coverage_profile_dir / "target"
                if coverage_profile_dir is not None
                else None,
            )
            raise_if_llvm_profile_write_failed(target_raw, case["case_id"])
            oracle = {name: oracle_raw[name] for name in operation["observe"]}
            target = {name: target_raw[name] for name in operation["observe"]}
            fields = operation.get("compare", operation["observe"])
            matches = {field: oracle[field] for field in fields} == {
                field: target[field] for field in fields
            }
            difference = None
            if not matches:
                differing_fields = [field for field in fields if oracle[field] != target[field]]
                difference = "Python API observations differ: " + ", ".join(differing_fields)
            required = required_observations_for_case(case, operation)
            if any(
                oracle.get(field) != value or target.get(field) != value
                for field, value in required.items()
            ):
                matches = False
                if difference is None:
                    difference = f"required observations did not match {required!r}"
            target_requirements = operation.get("target_requirements", {})
            if any(
                target.get(field) != value
                for field, value in target_requirements.items()
            ):
                matches = False
                if difference is None:
                    difference = (
                        f"target requirement did not match {target_requirements!r}"
                    )
            outcomes.append({
                "case_id": case["case_id"],
                "profile": profile["id"],
                "operation": case["operation"],
                "requirements": case["covers"],
                "status": "passed" if matches else "failed",
                "oracle_observation": oracle,
                "target_observation": target,
                "server_exit_codes": {
                    "oracle": oracle["exit_code"],
                    "target": target["exit_code"],
                },
                "difference": difference,
            })
            print(
                f"{'PASS' if matches else 'FAIL'} {profile['id']}: {case['case_id']}",
                flush=True,
            )
        except Exception as error:
            outcomes.append({
                "case_id": case["case_id"],
                "profile": profile["id"],
                "operation": case["operation"],
                "requirements": case["covers"],
                "status": "infrastructure_failed",
                "error": {"class": type(error).__name__, "message": str(error)[:5000]},
            })
            print(f"ERROR {profile['id']}: {case['case_id']}: {error}", flush=True)
    add_verification_metadata(outcomes, cases)
    return outcomes, []


def start_profile_servers(
    profile: dict[str, Any],
    tempdir: Path,
    cases: list[dict[str, Any]],
    coverage_profile_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any], Path | None]:
    profile_id = profile["id"]
    server_options = cases[0].get("server_options", {}) if cases else {}
    if any(case.get("server_options", {}) != server_options for case in cases):
        raise ParityError("profile cases with different server options must use separate processes")
    client_tls = any(case.get("client_tls") is True for case in cases)
    if any(case.get("client_tls", False) != client_tls for case in cases):
        raise ParityError("profile cases with different client TLS settings must use separate processes")
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
        "startup-encrypted-private-key-wrong-password",
        "startup-encrypted-private-key-invalid-utf8",
        "startup-encrypted-private-key-malformed-pem",
        "startup-encrypted-private-key-wrong-label",
        "startup-encrypted-private-key-invalid-der",
        "startup-traditional-encrypted-private-key-unsupported-cipher",
        "startup-traditional-encrypted-private-key-missing-dek-info",
        "startup-traditional-encrypted-private-key-invalid-dek-info",
        "startup-traditional-encrypted-private-key-invalid-proc-type",
        "startup-traditional-encrypted-private-key-missing-body",
        "startup-traditional-encrypted-private-key-invalid-body-base64",
        "startup-traditional-encrypted-private-key-missing-end-marker",
        "startup-traditional-unencrypted-private-key-invalid-base64",
    }
    if tls:
        certificate, key, trust_anchor = make_certificate(tempdir)
    else:
        certificate, key, trust_anchor = None, None, None
    needs_client_tls_material = client_tls or server_options.get("ssl_cert_reqs", 0) != 0
    if needs_client_tls_material:
        if trust_anchor is None:
            raise ParityError("mutual TLS requires a generated server trust anchor")
        client_certificate, client_key = make_client_certificate(tempdir)
    else:
        client_certificate, client_key = None, None
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
        initial_fault_point = next(
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
        if not initial_fault_point and profile_id == "http3":
            initial_fault_point = next(
                (
                    case["fault"]["point"]
                    for case in cases
                    if case.get("verification") == "fault-contract"
                    and case["fault"]["point"] in LEGACY_HTTP3_FAULT_POINTS
                ),
                "",
            )
        coverage_fault_control_path.write_text(initial_fault_point, encoding="utf-8")
    servers: dict[str, dict[str, Any]] = {}
    # Fault contracts execute only the instrumented target. Starting an
    # unused reference can introduce unrelated startup/shutdown failures,
    # particularly for fixtures that deliberately hold lifespan completion.
    server_ids = ["uvicorn-rs"]
    if any(case.get("verification", "oracle-parity") == "oracle-parity" for case in cases):
        server_ids.insert(0, profile["oracle"])
    try:
        for server_id in server_ids:
            # uvicorn-rs enables its QUIC endpoint whenever TLS credentials are
            # configured, including HTTPS-only parity profiles. Ensure the
            # selected port is free for both TCP and UDP before starting it.
            port = free_port(
                tcp_and_udp=(
                    profile_id == "http3"
                    or (server_id == "uvicorn-rs" and certificate is not None)
                )
            )
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
                server_options=server_options,
                trust_anchor=trust_anchor,
                client_certificate=client_certificate,
                client_key=client_key,
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
    if profile["id"] == "cli":
        return execute_cli_profile(
            profile, cases, operations, coverage_profile_dir
        )
    if profile["id"] == "python-api":
        return execute_python_api_profile(
            profile, cases, operations, coverage_profile_dir
        )
    server_option_groups: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        option_key = json.dumps(
            {
                "server_options": case.get("server_options", {}),
                "client_tls": case.get("client_tls", False),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        server_option_groups.setdefault(option_key, []).append(case)
    if len(server_option_groups) > 1:
        grouped_outcomes: dict[str, dict[str, Any]] = {}
        infrastructure_errors = []
        for case_group in server_option_groups.values():
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
    startup_cases = [
        case for case in cases
        if "startup_failure" in case or "startup_fallback" in case
        or case.get("fault", {}).get("contract") in {
            "server-eager-lifespan-registration-cleanup",
            "server-eager-lifespan-registration-cleanup-timeout",
        }
    ]
    legacy_http3_fault_cases = [
        case for case in cases
        if profile["id"] == "http3"
        and case.get("verification") == "fault-contract"
        and case["fault"]["point"] in LEGACY_HTTP3_FAULT_POINTS
    ]
    isolated_case_ids = {
        case["case_id"] for case in (*startup_cases, *legacy_http3_fault_cases)
    }
    if isolated_case_ids and (len(cases) != 1 or len(isolated_case_ids) != 1):
        # Startup faults and legacy HTTP/3 route-selection faults must be
        # armed before the target process starts. Isolate each so its
        # process-wide fault cannot disable or reroute sibling cases.
        case_groups = [
            [case for case in cases if case["case_id"] not in isolated_case_ids],
            *([case] for case in cases if case["case_id"] in isolated_case_ids),
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
    with profile_temporary_directory(
        prefix=f"uvicorn-rs-parity-{profile['id']}-",
        cleanup_errors=infrastructure_errors,
        profile_id=profile["id"],
    ) as temporary:
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
        # Hypercorn's H3 oracle can time out later requests after these cases:
        # client cancellation raises while its response writer resumes after a
        # reset, and the queued-upload early response also poisons a following
        # request. Run both at profile restart boundaries.
        def stops_server(case: dict[str, Any]) -> bool:
            return bool(
                "lifecycle" in case
                or case["operation"] in {"http3.peer-close", "http3.peer-close-registered"}
                or case.get("request", {}).get("hold_open_for_shutdown", False)
                or case.get("request_stream", {}).get("hold_until_shutdown", False)
                or case.get("websocket", {}).get("shutdown", False)
                or case.get("websocket", {}).get("shutdown_during_upgrade", False)
                or case.get("websocket", {}).get("drop_during_upgrade", False)
                # Keep the TLS scope-close probe independent from the next
                # WSS workflow. Both servers close this WebSocket normally,
                # but their TLS transports can still be draining when the
                # next case starts on the shared profile listener.
                or case["case_id"] == "websocket-tls.scope-headers-path-query-and-subprotocols"
                or case["case_id"] in {
                    "http3.client-cancels-large-response-after-headers",
                    "http3.post-first-upload-response-with-queued-chunks",
                }
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
                        persist_shutdown_trace(
                            case["case_id"], target, read_server_log(target)
                        )
                        raise ParityError(
                            f"target uvicorn-rs adapter failed: {error}\n"
                            f"{format_adapter_exception(error)}"
                        ) from error
                    target_server_log = target_raw.get("server_log")
                    if not isinstance(target_server_log, str):
                        target_server_log = read_server_log(target)
                    persist_shutdown_trace(case["case_id"], target, target_server_log)
                    operation = operations[case["operation"]]
                    target_result = project_observation(target_raw, operation)
                    if case.get("verification", "oracle-parity") == "fault-contract":
                        oracle_result = None
                        fault_observation = target_result
                        if case["fault"]["point"] == "asgi.event-type.extract":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw.get("server_log", ""),
                            }
                        elif case["fault"]["contract"] == "http3-body-pump-early-exit-500":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] in {
                            "http3-legacy-peer-close-no-error",
                            "http3-legacy-peer-close-unknown-code-ignored",
                            "http3-legacy-peer-close-classification-error",
                        }:
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] == "http3-legacy-handshake-recovery":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] in {
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
                        elif case["fault"]["contract"] == "server-unix-listener-permission-error-startup-propagates":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] == "server-default-header-finalization-error-closes-connection":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] == "http2-response-event-fault-consumed-and-status-observed":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] in {
                            "server-lifespan-startup-auto-fallback",
                            "server-lifespan-startup-auto-fallback-logger-failure-ignored",
                        }:
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] == "websocket-handshake-error-followup-200":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif (
                            case["fault"]["contract"]
                            == "http-connection-lifetime-closed-disconnect-followup-200"
                            and case["fault"]["point"]
                            == "http.connection.peer-read-failed.wait-complete"
                        ):
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif (
                            case["fault"]["contract"] == "websocket-teardown-and-followup-200"
                            and case["fault"]["point"] in {
                                "websocket.peer-read-failed.unavailable",
                                "websocket.peer-read-failed.watch-fallback",
                                "websocket.yawc.unexpected-continuation-frame",
                                "websocket.yawc.invalid-text-frame",
                                "websocket.yawc.invalid-close-reason",
                                "websocket.yawc.close-reply-flush-error",
                                "websocket.yawc.close-reply-flush-unexpected-frame",
                            }
                        ):
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] in EAGER_REGISTRATION_CLEANUP_CONTRACTS:
                            fault_observation = {**target_result, "server_log": target_raw["server_log"],
                                                 "failure_response": target_raw["failure_response"],
                                                 "followup": target_raw["followup"],
                                                 "fault_consumed": target_raw["fault_consumed"],
                                                 "lifespan_shutdown_completed": target_raw["lifespan_shutdown_completed"]}
                        elif case["fault"]["contract"] == "http-response-reset-cancels-deferred-task":
                            fault_observation = {**target_result, "application_events": target_raw["application_events"]}
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
                            "http-request-body-conversion-error-caught",
                            "http-body-pump-send-stopped-without-response",
                            "http-body-pump-oversized-frame-echo",
                        }:
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                            if case["fault"]["contract"] == "http-body-pump-send-stopped-without-response":
                                fault_observation["followup_response"] = target_raw.get(
                                    "followup_response"
                                )
                        elif case["fault"]["contract"] in {
                            "http-body-pump-error-stop-disconnect-followup-200",
                            "http-body-pump-drain-terminal-frame",
                            "http-body-pump-reaps-cancelled-task",
                            "http-body-pump-shutdown-cancelled-join",
                            "http-body-pump-shutdown-aborts-hung-pump",
                            "http-body-pump-shutdown-completes-task-before-abort",
                            "http3-upload-body-pump-preserves-data",
                            "http3-native-body-pump-pre-poll-cancel-preserves-response",
                            "http3-native-body-pump-sender-closed-preserves-response",
                            "http3-native-body-pump-send-stop-preserves-response",
                            "http3-native-body-pump-final-message-stop-preserves-response",
                            "http3-native-body-pump-final-message-send-error-preserves-response",
                            "http3-body-pump-error-stop-disconnect-followup-200",
                            "http3-legacy-body-pump-delivers-disconnect-followup-200",
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
                        elif case["fault"]["contract"] == "http-native-connection-write-error-followup-200":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] == "websocket-server-shutdown-force-abort":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] in {
                            "websocket-driver-send-error-followup-200",
                            "websocket-driver-send-error-cancels-app",
                        }:
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
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
                        elif case["fault"]["contract"] == "server-native-connection-error-during-shutdown":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                            }
                        elif case["fault"]["contract"] == "http3-server-shutdown-force-abort":
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        elif case["fault"]["contract"] in {
                            "http3-connection-task-shutdown-error",
                            "http3-connection-task-shutdown-hang-aborted",
                        }:
                            fault_observation = {
                                **target_result,
                                "server_log": target_raw["server_log"],
                            }
                        elif case["fault"]["contract"] == "http3-legacy-connection-task-shutdown-completes":
                            fault_observation = {
                                **target_result,
                                "fault_consumed": target_raw.get("fault_consumed"),
                            }
                        matches = fault_contract_matches(
                            case["fault"], fault_observation, case
                        )
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
                                "oracle_events": read_events(oracle["events"]),
                                "target_events": read_events(target["events"]),
                                "server_log": read_server_log(oracle)[-2000:],
                                "oracle_process": server_process_diagnostic(oracle),
                                "target_process": server_process_diagnostic(target),
                                "target_server_log": read_server_log(target)[-2000:],
                            }
                            raise ParityError(
                                f"oracle {oracle['id']} adapter failed: {error}; "
                                f"diagnostic={json.dumps(diagnostic, sort_keys=True)}\n"
                                f"{format_adapter_exception(error)}"
                            ) from error
                        oracle_result = project_observation(oracle_raw, operation)
                        comparison_fields = operation.get("compare", operation["observe"])
                        oracle_comparison = normalize_comparison_observation(
                            {field: oracle_result[field] for field in comparison_fields},
                            profile["id"],
                        )
                        target_comparison = normalize_comparison_observation(
                            {field: target_result[field] for field in comparison_fields},
                            profile["id"],
                        )
                        matches = oracle_comparison == target_comparison
                        required = required_observations_for_case(case, operation)
                        if any(
                            oracle_result.get(field) != value or target_result.get(field) != value
                            for field, value in required.items()
                        ):
                            matches = False
                        target_requirements = operation.get("target_requirements", {})
                        if any(
                            target_result.get(field) != value
                            for field, value in target_requirements.items()
                        ):
                            matches = False
                        if oracle_comparison != target_comparison:
                            difference = "observed public fields differ exactly"
                        elif not matches:
                            difference = (
                                f"required observation did not match {required!r}; "
                                f"target requirement did not match {target_requirements!r}"
                            )
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
            outcomes_by_case = {outcome["case_id"]: outcome for outcome in outcomes}
            for server in server_history:
                try:
                    exit_code, logs = stop_server(server)
                except Exception as error:
                    logs = server.get("captured_log", "")
                    if logs.strip():
                        print(f"--- {server['id']} server log ---\n{logs}", file=sys.stderr)
                    infrastructure_errors.append({
                        "profile": profile["id"],
                        "server": server["id"],
                        "pid": server["process"].pid,
                        "kind": "server_cleanup_failure",
                        "diagnostic": str(error)[-1000:],
                    })
                    continue
                captured_log = server.get("captured_log", logs)
                if server.get("log_cleanup_error"):
                    log_path = getattr(server.get("log"), "name", None)
                    infrastructure_errors.append({
                        "profile": profile["id"],
                        "server": server["id"],
                        "pid": server["process"].pid,
                        "attempted_cases": [
                            case["case_id"]
                            for case in server.get("attempted_cases", [])[-8:]
                        ],
                        "attempted_case_count": len(
                            server.get("attempted_cases", [])
                        ),
                        "process_exit_code": server.get("process_exit_code"),
                        "process_alive_after_stop": server.get(
                            "process_alive_after_stop"
                        ),
                        "forced_kill": server.get("forced_kill", False),
                        "log_path_exists": Path(log_path).exists()
                        if isinstance(log_path, (str, os.PathLike))
                        else None,
                        "kind": "server_log_cleanup_failure",
                        "diagnostic": server["log_cleanup_error"][-1000:],
                    })
                if captured_log.strip():
                    print(f"--- {server['id']} server log ---\n{captured_log}", file=sys.stderr)
                normal_signal_exit = server["id"] in {"uvicorn", "uvicorn-rs"} and (
                    exit_code == -signal.SIGTERM
                    or (
                        exit_code == -signal.SIGINT
                        and any(
                            case.get("lifecycle", {}).get("shutdown_signal") == "SIGINT"
                            for case in server["attempted_cases"]
                        )
                    )
                    or (
                        os.name == "nt"
                        and exit_code == 3
                        and server.get("graceful_signal_requested") is True
                        and "Finished server process [" in captured_log
                    )
                )
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
                server_outcome_key = {
                    "uvicorn": "oracle",
                    "uvicorn-rs": "target",
                }.get(server["id"])
                expected_observed_shutdown_exit = (
                    exit_code == 3
                    and server_outcome_key is not None
                    and any(
                        stops_server(case)
                        and (outcome := outcomes_by_case.get(case["case_id"])) is not None
                        and outcome.get("status") == "passed"
                        and outcome.get("server_exit_codes", {}).get(server_outcome_key)
                        == exit_code
                        for case in server.get("attempted_cases", [])
                    )
                )
                expected_windows_cleanup = (
                    os.name == "nt"
                    and server.get("harness_stop_requested") is True
                    # Popen.terminate() uses TerminateProcess on Windows,
                    # whose requested exit code is 1; this is routine profile
                    # cleanup after the case observations have been captured.
                    and exit_code == 1
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
                     and not expected_lifespan_shutdown_error
                     and not expected_observed_shutdown_exit
                     and not expected_windows_cleanup)
                ):
                    infrastructure_errors.append({
                        "profile": profile["id"],
                        "server": server["id"],
                        "pid": server["process"].pid,
                        "attempted_cases": [
                            case["case_id"]
                            for case in server.get("attempted_cases", [])[-8:]
                        ],
                        "attempted_case_count": len(
                            server.get("attempted_cases", [])
                        ),
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
    platform_id = parity_platform_id(run["environment"]["platform"])
    for oracle in manifest["oracles"]:
        pinned = [(oracle["id"], oracle["version"])]
        pinned.extend(
            (component["id"], component["version"])
            for component in oracle["components"]
            if "platforms" not in component or platform_id in component["platforms"]
        )
        for distribution, version in pinned:
            if dependencies.get(distribution) != version:
                raise ParityError(f"result identity does not match pinned {distribution} version {version}")
    exact_keys(
        run["target"],
        {"revision", "dirty", "native_extension", "cargo_lock_sha256", "source_files", "source_sha256"},
        "result.run.target",
    )
    exact_keys(run["target"]["native_extension"], {"path", "sha256"}, "result.run.target.native_extension")
    if not isinstance(run["target"]["dirty"], bool):
        raise ParityError("result target dirty flag must be boolean")
    if run["target"]["source_files"] != runtime_source_hashes(ROOT):
        raise ParityError("result runtime source inventory differs from checkout")
    if run["target"]["source_sha256"] != runtime_source_digest(run["target"]["source_files"]):
        raise ParityError("result runtime source digest does not match its file inventory")
    exact_keys(
        run["harness"],
        {
            "runner", "runner_sha256", "identity_helper", "fixture_app", "fixture_app_sha256",
            "python_api_probe", "http3_client",
        },
        "result.run.harness",
    )
    exact_keys(run["harness"]["identity_helper"], {"path", "sha256"}, "result.run.harness.identity_helper")
    exact_keys(run["harness"]["python_api_probe"], {"path", "sha256"}, "result.run.harness.python_api_probe")
    if run["harness"]["http3_client"] is not None:
        exact_keys(run["harness"]["http3_client"], {"path", "sha256"}, "result.run.harness.http3_client")
    for value, label in (
        (run["manifest"]["sha256"], "manifest"),
        (run["target"]["native_extension"]["sha256"], "native extension"),
        (run["target"]["cargo_lock_sha256"], "Cargo.lock"),
        (run["target"]["source_sha256"], "runtime source"),
        (run["harness"]["runner_sha256"], "runner"),
        (run["harness"]["identity_helper"]["sha256"], "source identity helper"),
        (run["harness"]["fixture_app_sha256"], "fixture app"),
        (run["harness"]["python_api_probe"]["sha256"], "Python API probe"),
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
    windows_ctrl_break_events = 0
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        def capture_windows_ctrl_break(signum: int, frame: Any) -> None:
            nonlocal windows_ctrl_break_events
            windows_ctrl_break_events += 1

        # Windows parity cases signal isolated server process groups. If a
        # control event leaks to this coordinator, preserve the rest of the
        # report and record the leak as an infrastructure failure instead of
        # letting the process exit before it writes the evidence artifact.
        signal.signal(signal.SIGBREAK, capture_windows_ctrl_break)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "asgi-parity" / "result.json")
    parser.add_argument(
        "--oracle-python",
        type=Path,
        default=Path(sys.executable),
        help="Python environment containing genuine upstream Uvicorn, isolated from the uvicorn-rs distribution",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="run only the named input case; repeat to select a batch",
    )
    parser.add_argument(
        "--exclude-case-id",
        action="append",
        help="exclude the named input case from a selected batch; repeat to exclude multiple cases",
    )
    parser.add_argument(
        "--profile",
        action="append",
        help="run only cases in the named manifest profile; repeat to select multiple profiles",
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
    parser.add_argument(
        "--installed-candidate",
        action="store_true",
        help=(
            "run target subprocesses against the installed uvicorn-rs wheel "
            "without prepending the checkout Python adapter"
        ),
    )
    parser.add_argument(
        "--trace-hypercorn-h3-events",
        action="store_true",
        help=(
            "wrap the Hypercorn HTTP/3 oracle with bounded stream-lifecycle tracing; "
            "requires exactly --case-id http3.early-response-with-open-upload"
        ),
    )
    args = parser.parse_args()
    global INSTALLED_CANDIDATE_MODE, ORACLE_PYTHON, TRACE_HYPERCORN_H3_EVENTS
    # Keep the venv's python symlink intact; resolving it points at the base
    # interpreter, whose site-packages do not contain the isolated oracle.
    ORACLE_PYTHON = Path(os.path.abspath(args.oracle_python))
    if not ORACLE_PYTHON.is_file() or not os.access(ORACLE_PYTHON, os.X_OK):
        parser.error(f"--oracle-python must be an executable interpreter: {ORACLE_PYTHON}")
    if args.installed_candidate and args.coverage_profile_dir:
        parser.error("--installed-candidate cannot be combined with --coverage-profile-dir")
    INSTALLED_CANDIDATE_MODE = args.installed_candidate
    TRACE_HYPERCORN_H3_EVENTS = args.trace_hypercorn_h3_events

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
    if args.profile:
        known_profiles = {profile["id"] for profile in manifest["profiles"]}
        unknown_profiles = sorted(set(args.profile) - known_profiles)
        if unknown_profiles:
            parser.error(f"unknown profile(s): {', '.join(unknown_profiles)}")
        selected_profiles = set(args.profile)
        selected_cases = [
            case for case in selected_cases if case["profile"] in selected_profiles
        ]
        if not selected_cases:
            parser.error("the selected profile and case filters matched no cases")
    if args.exclude_case_id:
        excluded = set(args.exclude_case_id)
        known = {case["case_id"] for case in inputs["cases"]}
        unknown = sorted(excluded - known)
        if unknown:
            parser.error(f"unknown excluded case ID(s): {', '.join(unknown)}")
        selected_ids = {case["case_id"] for case in selected_cases}
        outside_selection = sorted(excluded - selected_ids)
        if outside_selection:
            parser.error(
                "excluded case ID(s) are outside the selected case/profile batch: "
                + ", ".join(outside_selection)
            )
        selected_cases = [
            case for case in selected_cases if case["case_id"] not in excluded
        ]
    fault_cases = [case for case in selected_cases if case.get("verification") == "fault-contract"]
    if fault_cases and not args.fault_contracts:
        if args.case_id:
            parser.error("selected fault-contract case requires --fault-contracts and an instrumented coverage build")
        selected_cases = [case for case in selected_cases if case.get("verification", "oracle-parity") != "fault-contract"]
    if not selected_cases:
        parser.error("no runnable cases remain after applying the selected filters")
    if TRACE_HYPERCORN_H3_EVENTS and [case["case_id"] for case in selected_cases] != [
        "http3.early-response-with-open-upload"
    ]:
        parser.error(
            "--trace-hypercorn-h3-events requires exactly "
            "--case-id http3.early-response-with-open-upload"
        )
    coverage_profile_dir = args.coverage_profile_dir.resolve() if args.coverage_profile_dir else None
    if coverage_profile_dir is not None:
        if len(selected_cases) != 1 or not args.case_id:
            parser.error("--coverage-profile-dir requires exactly one selected --case-id")
        os.environ["ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN"] = "1"
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
    if windows_ctrl_break_events:
        infrastructure_errors.append(
            {
                "kind": "unexpected_harness_ctrl_break",
                "count": windows_ctrl_break_events,
                "message": "CTRL_BREAK_EVENT reached the parity coordinator while signaling a child server",
            }
        )
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
                "identity_helper": {
                    "path": "scripts/parity_identity.py",
                    "sha256": sha256(ROOT / "scripts/parity_identity.py"),
                },
                "fixture_app": str((FIXTURES / "app.py").relative_to(ROOT)),
                "fixture_app_sha256": sha256(FIXTURES / "app.py"),
                "python_api_probe": {
                    "path": str((FIXTURES / "python_api_probe.py").relative_to(ROOT)),
                    "sha256": sha256(FIXTURES / "python_api_probe.py"),
                },
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
