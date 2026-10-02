#!/usr/bin/env python3
"""Multiplexed HTTP/2 load client with full response-body validation."""

from __future__ import annotations

import asyncio
import json
import ssl
import sys
import time

from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import DataReceived, ResponseReceived, StreamEnded, StreamReset, WindowUpdated


class H2Client:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.connection = H2Connection(
            config=H2Configuration(client_side=True, header_encoding="utf-8")
        )
        self.connection.initiate_connection()
        self.writer.write(self.connection.data_to_send())
        self.states: dict[int, dict] = {}
        self.read_delay_ms = 0
        self.send_lock = asyncio.Lock()
        self.window_changed = asyncio.Event()
        self.reader_task = asyncio.create_task(self._read_responses())

    async def _write_pending(self) -> None:
        data = self.connection.data_to_send()
        if data:
            self.writer.write(data)
            await self.writer.drain()

    async def _read_responses(self) -> None:
        try:
            while data := await self.reader.read(65536):
                events = self.connection.receive_data(data)
                for event in events:
                    if isinstance(event, ResponseReceived):
                        state = self.states[event.stream_id]
                        state["status"] = int(dict(event.headers)[":status"])
                    elif isinstance(event, DataReceived):
                        state = self.states[event.stream_id]
                        state["body"].extend(event.data)
                        if self.read_delay_ms > 0:
                            await asyncio.sleep(self.read_delay_ms / 1000)
                        self.connection.acknowledge_received_data(
                            event.flow_controlled_length, event.stream_id
                        )
                    elif isinstance(event, StreamEnded):
                        state = self.states[event.stream_id]
                        if not state["future"].done():
                            state["future"].set_result((state["status"], bytes(state["body"])))
                    elif isinstance(event, StreamReset):
                        state = self.states.get(event.stream_id)
                        if state is not None and not state["future"].done():
                            state["future"].set_exception(RuntimeError("HTTP/2 stream reset"))
                    elif isinstance(event, WindowUpdated):
                        self.window_changed.set()
                await self._write_pending()
        except Exception as error:
            for state in self.states.values():
                if not state["future"].done():
                    state["future"].set_exception(error)

    async def _send(self, stream_id: int, chunk: bytes | None, end_stream: bool = False) -> None:
        async with self.send_lock:
            if chunk is None:
                self.connection.end_stream(stream_id)
            else:
                self.connection.send_data(stream_id, chunk, end_stream=end_stream)
            await self._write_pending()

    async def request(self, config: dict, upload_body: bytes) -> tuple[int, bytes]:
        async with self.send_lock:
            stream_id = self.connection.get_next_available_stream_id()
            future = asyncio.get_running_loop().create_future()
            self.states[stream_id] = {"future": future, "status": 0, "body": bytearray()}
            headers = [
                (":method", "POST" if config.get("upload_bytes", 0) else "GET"),
                (":scheme", "https"),
                (":authority", f"localhost:{config['port']}"),
                (":path", config["path"]),
                ("user-agent", "uvicorn-rs-category-benchmark/1"),
            ]
            for name, value in config.get("headers", []):
                headers.append((name.lower(), value))
            self.connection.send_headers(
                stream_id, headers, end_stream=(config.get("upload_bytes", 0) == 0)
            )
            await self._write_pending()

        upload_bytes = config.get("upload_bytes", 0)
        if upload_bytes:
            chunk_size = config.get("upload_chunk_bytes", 65_536)
            offset = 0
            while offset < upload_bytes:
                length = await self._send_upload_chunk(
                    stream_id, upload_body, offset, min(chunk_size, upload_bytes - offset)
                )
                offset += length
            await self._send(stream_id, None)

        try:
            status, response_body = await asyncio.wait_for(
                future, timeout=config.get("request_timeout_seconds", 10.0)
            )
        except asyncio.TimeoutError as error:
            state = self.states.get(stream_id, {})
            raise RuntimeError(
                "HTTP/2 response timed out "
                f"(stream={stream_id}, status={state.get('status')}, "
                f"received_body_bytes={len(state.get('body', b''))})"
            ) from error
        del self.states[stream_id]
        return status, response_body

    async def _send_upload_chunk(
        self, stream_id: int, body: bytes, offset: int, wanted: int
    ) -> int:
        while True:
            async with self.send_lock:
                window = min(
                    self.connection.local_flow_control_window(stream_id),
                    self.connection.max_outbound_frame_size,
                )
                if window > 0:
                    length = min(window, wanted)
                    self.connection.send_data(stream_id, body[offset : offset + length])
                    await self._write_pending()
                    return length
                self.window_changed.clear()
            await asyncio.wait_for(self.window_changed.wait(), timeout=10)

    async def close(self) -> None:
        self.reader_task.cancel()
        await asyncio.gather(self.reader_task, return_exceptions=True)
        self.writer.close()
        await self.writer.wait_closed()


def expected_body(config: dict) -> bytes:
    if config.get("response_bytes", 0):
        return b"x" * config["response_bytes"]
    if "expected_body" in config:
        return config["expected_body"].encode()
    mode = config.get("mode", "fixed")
    if mode == "upload":
        return f"bytes={config['upload_bytes']}".encode()
    if mode == "scope":
        return b"scope-ok"
    if mode == "context":
        return b"request-context"
    if mode == "exception":
        return b"Internal Server Error"
    return b"Hello World!"


async def run(config: dict) -> dict:
    tls = ssl.create_default_context()
    tls.check_hostname = False
    tls.verify_mode = ssl.CERT_NONE
    tls.set_alpn_protocols(["h2"])
    expected = expected_body(config)
    upload_body = b"a" * config.get("upload_bytes", 0)
    latencies: list[float] = []
    failures: list[str] = []
    request_body_bytes = 0
    response_body_bytes = 0
    deadline = time.perf_counter() + config["seconds"]
    started = time.perf_counter()

    async def one_connection() -> None:
        nonlocal request_body_bytes, response_body_bytes
        reader, writer = await asyncio.open_connection(
            config.get("host", "127.0.0.1"),
            config["port"],
            ssl=tls,
            server_hostname="localhost",
        )
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is None or ssl_object.selected_alpn_protocol() != "h2":
            raise RuntimeError("TLS did not negotiate HTTP/2 via ALPN")
        client = H2Client(reader, writer)
        client.read_delay_ms = config.get("read_delay_ms", 0)

        async def worker() -> None:
            nonlocal request_body_bytes, response_body_bytes
            while time.perf_counter() < deadline:
                request_started = time.perf_counter()
                try:
                    status, body = await client.request(config, upload_body)
                except Exception as error:
                    failures.append(str(error))
                    return
                if status != config.get("expected_status", 200):
                    failures.append(f"unexpected status {status}")
                if body != expected:
                    failures.append(
                        f"response body mismatch ({len(body)} bytes, expected {len(expected)})"
                    )
                latencies.append((time.perf_counter() - request_started) * 1000)
                request_body_bytes += config.get("upload_bytes", 0)
                response_body_bytes += len(body)

        try:
            await asyncio.gather(*(worker() for _ in range(config.get("streams_per_connection", 16))))
        finally:
            await client.close()

    try:
        await asyncio.gather(
            *(one_connection() for _ in range(config.get("connections", 8)))
        )
    except Exception as error:
        failures.append(str(error))
    elapsed = time.perf_counter() - started
    latencies.sort()

    def percentile(p: float) -> float:
        if not latencies:
            return 0.0
        return latencies[max(0, min(len(latencies) - 1, int(p * len(latencies) + 0.999999) - 1))]

    return {
        "requests": len(latencies),
        "duration_seconds": elapsed,
        "requests_per_second": len(latencies) / elapsed,
        "request_body_bytes": request_body_bytes,
        "response_body_bytes": response_body_bytes,
        "application_bytes_per_second": (request_body_bytes + response_body_bytes) / elapsed,
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "failures": len(failures),
        "first_failure": {"error": failures[0]} if failures else None,
        "protocol": "h2 (TLS ALPN verified)",
    }


if __name__ == "__main__":
    config = json.loads(sys.argv[1])
    try:
        import uvloop
    except ImportError:
        result = asyncio.run(run(config))
    else:
        result = uvloop.run(run(config))
    print(json.dumps(result, separators=(",", ":")))
    if result["failures"] or result["requests"] == 0:
        raise SystemExit(1)
