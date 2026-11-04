#!/usr/bin/env python3
"""Tooling checks against in-memory ASGI and tiny HTTP stubs; not benchmarks."""

import asyncio
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def wrapper(app):
    spec = importlib.util.spec_from_file_location("trace_wrapper_fixture", ROOT / "examples/profile_fastapi.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"examples.bench_fastapi": types.SimpleNamespace(app=app)}):
        spec.loader.exec_module(module)
    return module


class AsgiTraceTests(unittest.TestCase):
    def test_messages_are_preserved_and_tail_is_bounded(self):
        message = {"type": "http.request", "body": b"x", "more_body": True}
        response = {"type": "http.response.body", "body": b"ok"}
        sent = []

        async def app(scope, receive, send):
            for _ in range(300):
                self.assertIs(await receive(), message)
            await send(response)

        async def receive():
            return message

        async def send(value):
            sent.append(value)

        module = wrapper(app)
        with patch.dict(os.environ, {"UVICORN_RS_UPLOAD_TRACE": "1"}):
            asyncio.run(module.app({"type": "http", "path": "/upload",
                "headers": [(b"x-uvicorn-rs-upload-trace", b"1-0-1")]}, receive, send))
        self.assertIs(sent[0], response)
        trace = module._UPLOAD_TRACES["/upload"][0]
        self.assertEqual(trace["request_body_bytes"], 300)
        self.assertEqual(len(trace["events"]), 128)
        self.assertGreater(trace["events_dropped"], 0)
        self.assertEqual(trace["events"][-1]["event"], "app-end")
        self.assertEqual(trace["request_id"], "1-0-1")
        offsets = [event["offset_ns"] for event in trace["events"]]
        self.assertEqual(offsets, sorted(offsets))

    def test_cancellation_survives_and_is_recorded(self):
        async def app(scope, receive, send):
            await receive()

        async def receive():
            raise asyncio.CancelledError()

        module = wrapper(app)
        with patch.dict(os.environ, {"UVICORN_RS_UPLOAD_TRACE": "1"}):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(module.app({"type": "http", "path": "/upload",
                    "headers": [(b"x-uvicorn-rs-upload-trace", b"1-0-1")]}, receive, None))
        events = module._UPLOAD_TRACES["/upload"][0]["events"]
        self.assertIn({"event": "receive-error", "error_class": "CancelledError"},
                      [{key: value for key, value in event.items() if key != "offset_ns"} for event in events])

    def test_unset_opt_in_does_not_retain_a_trace(self):
        async def app(scope, receive, send):
            pass

        module = wrapper(app)
        with patch.dict(os.environ, {"UVICORN_RS_UPLOAD_TRACE": ""}):
            asyncio.run(module.app({"type": "http", "path": "/upload",
                "headers": [(b"x-uvicorn-rs-upload-trace", b"1-0-1")]}, None, None))
        self.assertEqual(module._UPLOAD_TRACES, {})


class ClientTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="upload-trace-tooling-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / "client"
        flags = shlex.split(subprocess.check_output(["curl-config", "--cflags", "--libs"], text=True))
        subprocess.run(["cc", "-O2", "-std=c11", "-pthread", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "scripts/bench_http_client.c"), "-o", str(cls.binary), *flags], check=True)

    def request(self, enabled, reset=False):
        headers = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                headers.append(self.headers.get("X-Uvicorn-Rs-Upload-Trace"))
                if reset:
                    self.close_connection = True
                    return
                body = self.rfile.read(int(self.headers["Content-Length"]))
                reply = f"bytes={len(body)}".encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(reply)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run([str(self.binary), "127.0.0.1", str(server.server_port),
                "1", "1", "upload", "/upload", "0", "8192", "200", "", "1024", "1"],
                env={**os.environ, "UVICORN_RS_UPLOAD_TRACE": "1" if enabled else ""},
                capture_output=True, text=True, timeout=20)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(result.returncode, 1 if reset else 0, result.stderr)
        return json.loads(result.stdout), headers

    def test_opt_in_header_counts_and_normal_absence(self):
        normal, headers = self.request(False)
        self.assertEqual(headers, [None])
        self.assertNotIn("upload_trace", normal)
        traced, headers = self.request(True)
        self.assertRegex(headers[0], r"^\d+-0-1$")
        self.assertEqual(traced["upload_trace"]["callback_calls"], 8)
        self.assertEqual(traced["upload_trace"]["callback_bytes"], 8192)
        self.assertEqual(traced["upload_trace"]["timeout_ms"], 15000)

    def test_transport_failure_retains_correlated_callback_timestamps(self):
        result, headers = self.request(True, reset=True)
        trace = result["first_failure"]["upload_trace"]
        self.assertEqual(trace["request_id"], headers[0])
        self.assertGreaterEqual(trace["completed"], trace["started"])
        if trace["callback_calls"]:
            self.assertGreaterEqual(trace["last_callback"], trace["first_callback"])
            self.assertGreaterEqual(trace["first_callback"], trace["started"])
        self.assertGreater(trace["events_seen"], 0)
        self.assertGreater(trace["events_retained"], 0)
        offsets = [event["offset_ns"] for event in trace["events"]]
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(any(event["event"] == "read-callback" for event in trace["events"]))
        self.assertTrue(any(event["event"] == "curl-progress" for event in trace["events"]))


class FailureReportTests(unittest.TestCase):
    def test_server_trace_is_correlated_by_client_request_id(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import run_http_category_bench as bench

        server_output = "\n".join([
            "uvicorn-rs-upload-trace schema=1 request=77-2-9 lane=pump "
            "origin_unix_ns=1700000000000000000 origin_uncertainty_ns=4 "
            "read_bytes=1024 offered_bytes=1024 delivered_bytes=1024 "
            "events_seen=3 events_retained=3 events_dropped=0",
            "uvicorn-rs-upload-event request=77-2-9 lane=pump offset_ns=10 "
            "event=read-wait bytes=0 flag=false",
            "uvicorn-rs-upload-event request=77-2-9 lane=pump offset_ns=1000010 "
            "event=read-data bytes=1024 flag=false",
            "uvicorn-rs-upload-trace schema=1 request=77-2-9 lane=asgi "
            "origin_unix_ns=1700000000001000000 origin_uncertainty_ns=5 "
            "read_bytes=0 offered_bytes=0 delivered_bytes=1024 "
            "events_seen=2 events_retained=2 events_dropped=0",
            "uvicorn-rs-upload-event request=77-2-9 lane=asgi offset_ns=20 "
            "event=asgi-deliver bytes=1024 flag=true",
        ])
        metrics = {
            "upload_trace": {
                "calibration_monotonic_before": 10.0,
                "calibration_monotonic_after": 10.000002,
                "calibration_unix": 1700000000.0,
            },
            "first_failure": {
                "upload_trace": {
                    "request_id": "77-2-9",
                    "started": 10.0,
                    "events": [{"event": "curl-progress", "offset_ns": 1_000_000}],
                },
            },
        }
        bench._correlate_upload_trace(metrics, server_output)
        trace = metrics["first_failure"]["upload_trace"]
        self.assertEqual(trace["server_trace"]["status"], "matched")
        self.assertEqual(len(trace["server_trace"]["trace_records"]), 2)
        self.assertEqual(
            [event["source"] for event in trace["correlated_timeline"]],
            ["uvicorn-rs", "libcurl", "uvicorn-rs", "uvicorn-rs"],
        )
        pump_events = [
            event for event in trace["server_trace"]["events"]
            if event["lane"] == "pump"
        ]
        self.assertEqual(pump_events[1]["delta_from_previous_lane_event_ns"], 1_000_000)

    def test_measured_failure_keeps_client_metrics_through_sample_cleanup(self):
        # Exercise the actual measured-sample error path without starting a
        # server or load generator. The first failure must survive cleanup.
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import run_http_category_bench as bench

        payload = {"requests": 7, "failures": 1, "first_failure": {
            "upload_trace": {"request_id": "1-0-1", "callback_calls": 819},
        }}
        for returncode in [1, 0]:
            with self.subTest(returncode=returncode), \
                 patch.object(bench, "_command", return_value=[]), \
                 patch.object(bench, "_client_command", return_value=[]), \
                 patch.object(bench, "_wait_ready"), \
                 patch.object(bench, "owned_process", side_effect=[
                     types.SimpleNamespace(pid=os.getpid()),
                     types.SimpleNamespace(returncode=returncode, pid=os.getpid()),
                 ]), \
                 patch.object(bench, "SampleMonitor"), \
                 patch.object(bench, "collect_bounded_client", return_value=(json.dumps(payload), "")), \
                 patch.object(bench, "_stop_server"), \
                 patch.object(bench, "stop_client"), \
                 patch.object(bench, "_runtime_diagnostics", return_value=None):
                with self.assertRaises(bench._BenchmarkCaseFailure) as raised:
                    bench._sample("uvicorn-rs-asyncio", {}, "fastapi-upload-1m-write-1k",
                                  1, 0, 1, Path(sys.executable), Path(sys.executable))
                retained = raised.exception.partial_client_metrics
                self.assertEqual(retained["requests"], payload["requests"])
                self.assertEqual(
                    retained["first_failure"]["upload_trace"]["server_trace"]["status"],
                    "no_matching_server_request_id",
                )


if __name__ == "__main__":
    unittest.main()
