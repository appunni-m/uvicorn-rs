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
import time
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

    def request(self, enabled, reset=False, max_requests=1, trace_requests=None,
                tcp_diagnostics=False):
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
                "1", "1", "upload", "/upload", "0", "8192", "200", "", "1024",
                str(max_requests)],
                env={
                    **os.environ,
                    "UVICORN_RS_UPLOAD_TRACE": "1" if enabled else "",
                    "UVICORN_RS_UPLOAD_TRACE_REQUESTS": trace_requests or "",
                    "UVICORN_RS_HTTP_CLIENT_TCP_DIAGNOSTICS": (
                        "1" if tcp_diagnostics else ""
                    ),
                },
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
        self.assertEqual(traced["upload_trace"]["request_selection"], ["all"])

    def test_successful_upload_trace_is_bounded_and_correlated(self):
        traced, headers = self.request(True)
        diagnostics = traced["upload_trace"]
        self.assertEqual(
            diagnostics["successful_transfer_trace_limit_per_worker"], 32,
        )
        self.assertEqual(len(diagnostics["successful_transfers"]), 1)
        transfer = diagnostics["successful_transfers"][0]
        self.assertEqual(transfer["request_id"], headers[0])
        self.assertEqual(transfer["expected_upload_bytes"], 8192)
        self.assertEqual(transfer["callback_bytes"], 8192)
        self.assertEqual(transfer["curl_uploaded_bytes"], 8192)
        self.assertEqual(transfer["response_code"], 200)
        self.assertGreater(transfer["elapsed_ms"], 0)
        events = transfer["events"]
        offsets = [event["offset_ns"] for event in events]
        self.assertEqual(offsets, sorted(offsets))
        self.assertTrue(any(event["event"] == "read-callback" for event in events))
        self.assertTrue(any(event["event"] == "curl-progress" for event in events))

    def test_request_selection_traces_only_the_selected_worker_attempt(self):
        traced, headers = self.request(
            True,
            max_requests=3,
            trace_requests="0:2",
            tcp_diagnostics=True,
        )
        diagnostics = traced["upload_trace"]
        self.assertEqual(diagnostics["request_selection"], ["0:2"])
        self.assertTrue(diagnostics["tcp_info_enabled"])
        self.assertEqual(len(headers), 3)
        self.assertIsNone(headers[0])
        self.assertRegex(headers[1], r"^\d+-0-2$")
        self.assertIsNone(headers[2])
        self.assertEqual(len(diagnostics["successful_transfers"]), 1)
        transfer = diagnostics["successful_transfers"][0]
        self.assertEqual(transfer["request_id"], headers[1])
        self.assertEqual(transfer["worker_attempt"], 2)
        self.assertEqual(diagnostics["callback_bytes"], 8192)
        self.assertIn("tcp_info_before", transfer)
        self.assertIn("sampled", transfer["tcp_info_before"])
        progress = [event for event in transfer["events"]
                    if event["event"] == "curl-progress"]
        self.assertTrue(progress)
        self.assertIn("tcp_info", progress[0])
        self.assertIn("sampled", progress[0]["tcp_info"])

    def test_request_selection_rejects_non_decimal_attempts(self):
        result = subprocess.run(
            [str(self.binary), "127.0.0.1", "1", "1", "1", "upload", "/upload",
             "0", "8192", "200", "", "1024", "1"],
            env={
                **os.environ,
                "UVICORN_RS_UPLOAD_TRACE": "1",
                "UVICORN_RS_UPLOAD_TRACE_REQUESTS": "0:-1",
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("comma-separated worker:attempt pairs", result.stderr)

    def test_request_selection_rejects_workers_outside_concurrency(self):
        result = subprocess.run(
            [str(self.binary), "127.0.0.1", "1", "1", "1", "upload", "/upload",
             "0", "8192", "200", "", "1024", "1"],
            env={
                **os.environ,
                "UVICORN_RS_UPLOAD_TRACE": "1",
                "UVICORN_RS_UPLOAD_TRACE_REQUESTS": "1:1",
            },
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside concurrency 1", result.stderr)

    def test_transport_failure_retains_correlated_callback_timestamps(self):
        result, headers = self.request(True, reset=True, tcp_diagnostics=True)
        trace = result["first_failure"]["upload_trace"]
        self.assertEqual(trace["request_id"], headers[0])
        self.assertIn("tcp_info_before", trace)
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

    def test_upload_trace_counts_reused_and_closed_connections(self):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                reply = f"bytes={len(body)}".encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            command = [str(self.binary), "127.0.0.1", str(server.server_port),
                "1", "1", "upload", "/upload", "0", "8192", "200", "", "1024", "2"]

            def run(extra_headers):
                result = subprocess.run(
                    [*command, *extra_headers],
                    env={**os.environ, "UVICORN_RS_UPLOAD_TRACE": "1"},
                    capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)["upload_trace"]["connection_counts"]

            persistent = run([])
            closed = run(["Connection: close"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(persistent, {
            "curl_successful_transfers": 2,
            "new_connections": 1,
            "reused_transfers": 1,
        })
        self.assertEqual(closed, {
            "curl_successful_transfers": 2,
            "new_connections": 2,
            "reused_transfers": 0,
        })


class FailureReportTests(unittest.TestCase):
    def test_repeated_live_server_checkpoints_deduplicate_retained_events(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import run_http_category_bench as bench

        request_id = "77-2-9"
        summary = (
            f"uvicorn-rs-upload-trace schema=1 request={request_id} lane=pump "
            "origin_unix_ns=1700000000000000000 origin_uncertainty_ns=4 "
            "expected_bytes=1024 emission_reason=in-progress-checkpoint "
        )
        events = [
            f"uvicorn-rs-upload-event request={request_id} lane=pump event_index=1 "
            "offset_ns=10 event=start bytes=0 flag=false",
            f"uvicorn-rs-upload-event request={request_id} lane=pump event_index=2 "
            "offset_ns=1000000010 event=read-frame-pending bytes=0 flag=false "
            "duration_ns=1000000000",
        ]
        server_output = "\n".join([
            summary + "snapshot_index=1 read_bytes=512 offered_bytes=0 delivered_bytes=0 "
            "events_seen=2 events_retained=2 events_dropped=0",
            *events,
            summary + "snapshot_index=2 read_bytes=512 offered_bytes=0 delivered_bytes=0 "
            "events_seen=2 events_retained=2 events_dropped=0",
            *events,
        ])

        trace = bench._server_upload_trace(server_output, request_id)
        self.assertEqual([item["snapshot_index"] for item in trace["trace_records"]], [1, 2])
        self.assertEqual([event["event_index"] for event in trace["events"]], [1, 2])
        self.assertEqual(trace["events"][-1]["duration_ns"], 1_000_000_000)

    def test_server_trace_is_correlated_by_client_request_id(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import run_http_category_bench as bench

        server_output = "\n".join([
            "uvicorn-rs-upload-trace schema=1 request=77-2-9 lane=pump "
            "origin_unix_ns=1700000000000000000 origin_uncertainty_ns=4 "
            "expected_bytes=1024 emission_reason=body-size-mismatch "
            "read_bytes=1024 offered_bytes=1024 delivered_bytes=1024 "
            "events_seen=3 events_retained=3 events_dropped=0",
            "uvicorn-rs-upload-event request=77-2-9 lane=pump offset_ns=10 "
            "event=read-wait bytes=0 flag=false",
            "uvicorn-rs-upload-event request=77-2-9 lane=pump offset_ns=1000010 "
            "event=read-data bytes=1024 flag=false",
            "uvicorn-rs-upload-event request=77-2-9 lane=pump offset_ns=1000020 "
            "event=queue-send-finished bytes=0 flag=false duration_ns=2500000",
            "uvicorn-rs-upload-trace schema=1 request=77-2-9 lane=asgi "
            "origin_unix_ns=1700000000001000000 origin_uncertainty_ns=5 "
            "expected_bytes=1024 emission_reason=slow "
            "read_bytes=0 offered_bytes=0 delivered_bytes=1024 "
            "events_seen=3 events_retained=3 events_dropped=0",
            "uvicorn-rs-upload-event request=77-2-9 lane=asgi offset_ns=20 "
            "event=asgi-deliver bytes=1024 flag=true",
            "uvicorn-rs-upload-event request=77-2-9 lane=asgi offset_ns=30 "
            "event=asgi-response-start-queued bytes=0 flag=false value=200",
            "uvicorn-rs-connection-trace schema=1 pid=44 connection=3 "
            "peer=127.0.0.1:41003 peer_port=41003 elapsed_ns=9000000 "
            "read_bytes=1049000 write_bytes=500 read_ready_polls=12 "
            "read_pending_polls=5 read_eof=1 read_errors=0 write_ready_polls=3 "
            "write_pending_polls=0 write_errors=0 max_read_wait_ns=7000000 "
            "max_write_wait_ns=0 events_seen=2 events_retained=2 events_dropped=0",
            "uvicorn-rs-connection-event schema=1 pid=44 connection=3 peer_port=41003 "
            "offset_ns=1000 event=request-dispatched bytes=0 read_total=1049000 "
            "write_total=0 request_id=77-2-9",
        ])
        metrics = {
            "upload_trace": {
                "calibration_monotonic_before": 10.0,
                "calibration_monotonic_after": 10.000002,
                "calibration_unix": 1700000000.0,
            },
            "first_failure": {
                "transfer": {"local_port": 41003},
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
        self.assertEqual(trace["server_trace"]["trace_records"][0]["expected_bytes"], 1024)
        self.assertEqual(trace["server_connection_trace"]["status"], "matched")
        self.assertEqual(
            trace["server_connection_trace"]["connections"][0]["peer_port"],
            41003,
        )
        self.assertEqual(
            trace["server_connection_trace"]["connections"][0]["events"][0]["request_id"],
            "77-2-9",
        )
        self.assertEqual(
            trace["server_trace"]["trace_records"][0]["emission_reason"],
            "body-size-mismatch",
        )
        response_start = next(
            event for event in trace["server_trace"]["events"]
            if event["event"] == "asgi-response-start-queued"
        )
        self.assertEqual(response_start["value"], 200)
        self.assertEqual(
            [event["source"] for event in trace["correlated_timeline"]],
            [
                "uvicorn-rs",
                "libcurl",
                "uvicorn-rs",
                "uvicorn-rs",
                "uvicorn-rs",
                "uvicorn-rs",
            ],
        )
        pump_events = [
            event for event in trace["server_trace"]["events"]
            if event["lane"] == "pump"
        ]
        self.assertEqual(pump_events[1]["delta_from_previous_lane_event_ns"], 1_000_000)
        self.assertEqual(pump_events[2]["duration_ns"], 2_500_000)

    def test_slowest_asgi_trace_is_joined_to_matching_rust_request(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import run_http_category_bench as bench

        server_output = "\n".join([
            "uvicorn-rs-upload-trace schema=1 request=88-1-42 lane=asgi "
            "origin_unix_ns=1700000000000000000 origin_uncertainty_ns=3 "
            "expected_bytes=1024 emission_reason=slow "
            "read_bytes=0 offered_bytes=0 delivered_bytes=1024 "
            "events_seen=1 events_retained=1 events_dropped=0",
            "uvicorn-rs-upload-event request=88-1-42 lane=asgi offset_ns=30 "
            "event=asgi-deliver bytes=1024 flag=true",
        ])
        diagnostics = {
            "paths": {
                "/upload/1024": {
                    "upload_trace": {
                        "traces": [{
                            "request_id": "88-1-42",
                            "origin_unix_ns": 1_700_000_000_000_000_010,
                            "origin_uncertainty_ns": 5,
                            "events": [
                                {"offset_ns": 10, "event": "app-start"},
                                {"offset_ns": 40, "event": "receive-ready"},
                            ],
                        }],
                    },
                },
            },
        }

        result = bench._correlate_asgi_upload_traces(diagnostics, server_output)
        trace = diagnostics["paths"]["/upload/1024"]["upload_trace"]["traces"][0]
        self.assertEqual(result["wrapper_slow_trace_count"], 1)
        self.assertEqual(result["matched_request_count"], 1)
        self.assertEqual(result["matched_rust_lane_trace_count"], 1)
        self.assertEqual(trace["uvicorn_rs_server_trace"]["status"], "matched")
        self.assertEqual(
            [event["source"] for event in trace["correlated_timeline"]],
            ["asgi-wrapper", "uvicorn-rs", "asgi-wrapper"],
        )

    def test_slowest_asgi_trace_joins_client_server_and_rust_timelines(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import run_http_category_bench as bench

        request_id = "88-1-43"
        server_output = "\n".join([
            f"uvicorn-rs-upload-trace schema=1 request={request_id} lane=pump "
            "origin_unix_ns=1700000000000000000 origin_uncertainty_ns=3 "
            "expected_bytes=1024 emission_reason=slow "
            "read_bytes=1024 offered_bytes=1024 delivered_bytes=1024 "
            "events_seen=2 events_retained=2 events_dropped=0",
            f"uvicorn-rs-upload-event request={request_id} lane=pump "
            "offset_ns=1500000 event=read-data bytes=1024 flag=false",
        ])
        diagnostics = {
            "paths": {"/upload/1024": {"upload_trace": {"traces": [{
                "request_id": request_id,
                "origin_unix_ns": 1_700_000_000_000_000_000,
                "origin_uncertainty_ns": 5,
                "events": [{"offset_ns": 1_000_000, "event": "receive-ready"}],
            }]}}},
        }
        client_metrics = {
            "upload_trace": {
                "calibration_monotonic_before": 10.0,
                "calibration_monotonic_after": 10.000002,
                "calibration_unix": 1_700_000_000.0,
                "successful_transfers": [{
                    "request_id": request_id,
                    "started": 10.0,
                    "elapsed_ms": 2.0,
                    "callback_bytes": 1024,
                    "events": [{
                        "offset_ns": 500_000,
                        "event": "curl-progress",
                        "curl_uploaded_bytes": 1024,
                    }],
                }],
            },
        }

        result = bench._correlate_asgi_upload_traces(
            diagnostics, server_output, client_metrics,
        )
        trace = diagnostics["paths"]["/upload/1024"]["upload_trace"]["traces"][0]
        self.assertEqual(result["matched_request_count"], 1)
        self.assertEqual(result["matched_client_upload_trace_count"], 1)
        self.assertEqual(trace["libcurl_client_trace_status"], "matched")
        timeline = trace["correlated_timeline"]
        self.assertEqual(
            [event["source"] for event in timeline],
            ["libcurl", "asgi-wrapper", "uvicorn-rs"],
        )
        self.assertEqual(timeline[0]["curl_uploaded_bytes"], 1024)

    def test_bounded_client_collection_drains_large_trace_output(self):
        with patch.object(sys, "path", [str(ROOT / "scripts"), *sys.path]):
            import benchmark_evidence

        client = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 1048576)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Leave a short deadline so this regression stays fast if collection
        # accidentally returns to waiting on a child blocked by a full pipe.
        client.benchmark_started = time.monotonic() - 29.5
        monitor = types.SimpleNamespace(sample=lambda: None)
        try:
            with patch.object(benchmark_evidence, "check_server_alive"), \
                 patch.object(benchmark_evidence, "_refresh_owned"):
                stdout, stderr = benchmark_evidence.collect_bounded_client(
                    client, 0.05, object(), monitor, interval=0.01,
                )
        finally:
            if client.poll() is None:
                client.kill()
            client.wait(timeout=2)

        self.assertEqual(len(stdout), 1_048_576)
        self.assertEqual(stderr, "")

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
