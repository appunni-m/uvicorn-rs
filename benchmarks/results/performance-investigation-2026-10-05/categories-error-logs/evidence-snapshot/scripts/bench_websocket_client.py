#!/usr/bin/env python3
"""Concurrent WebSocket handshake and echo load client with payload equality gates."""

from __future__ import annotations

import asyncio
import json
import sys
import time

import websockets


async def run(config: dict) -> dict:
    uri = f"ws://{config.get('host', '127.0.0.1')}:{config['port']}{config.get('path', '/echo')}"
    concurrency = int(config.get("concurrency", 32))
    duration = float(config.get("seconds", 3))
    mode = config.get("mode", "text")
    payload_bytes = int(config.get("payload_bytes", 32))
    payload = bytes([120]) * payload_bytes
    text_payload = payload.decode("ascii")
    latencies: list[float] = []
    failures: list[str] = []
    requests = 0
    request_bytes = 0
    response_bytes = 0
    started = time.perf_counter()
    deadline = started + duration

    async def connect():
        return await websockets.connect(
            uri,
            subprotocols=["bench"],
            ping_interval=None,
            max_size=max(1_048_576, payload_bytes * 2),
        )

    if mode == "handshake":
        async def handshake_worker() -> None:
            nonlocal requests
            while time.perf_counter() < deadline:
                operation_started = time.perf_counter()
                try:
                    websocket = await connect()
                    if websocket.subprotocol != "bench":
                        failures.append(f"unexpected subprotocol: {websocket.subprotocol!r}")
                    await websocket.close()
                    latencies.append((time.perf_counter() - operation_started) * 1000)
                    requests += 1
                except Exception as error:
                    failures.append(str(error))
                    return

        await asyncio.gather(*(handshake_worker() for _ in range(concurrency)))
    else:
        connections = await asyncio.gather(*(connect() for _ in range(concurrency)))
        try:
            for websocket in connections:
                if websocket.subprotocol != "bench":
                    failures.append(f"unexpected subprotocol: {websocket.subprotocol!r}")
                warm_payload = text_payload if mode == "text" else payload
                await websocket.send(warm_payload)
                if await websocket.recv() != warm_payload:
                    failures.append("warm-up echo payload mismatch")
                if failures:
                    raise RuntimeError(failures[0])
            started = time.perf_counter()
            deadline = started + duration

            async def echo_worker(websocket) -> None:
                nonlocal requests, request_bytes, response_bytes
                while time.perf_counter() < deadline:
                    operation_started = time.perf_counter()
                    try:
                        value = text_payload if mode == "text" else payload
                        await websocket.send(value)
                        echoed = await websocket.recv()
                    except Exception as error:
                        failures.append(str(error))
                        return
                    if echoed != value:
                        failures.append("echo payload differed from the complete request bytes")
                        return
                    byte_count = len(value.encode("ascii")) if isinstance(value, str) else len(value)
                    requests += 1
                    request_bytes += byte_count
                    response_bytes += byte_count
                    latencies.append((time.perf_counter() - operation_started) * 1000)

            await asyncio.gather(*(echo_worker(websocket) for websocket in connections))
        finally:
            await asyncio.gather(*(websocket.close() for websocket in connections), return_exceptions=True)

    elapsed = time.perf_counter() - started
    latencies.sort()

    def percentile(p: float) -> float:
        if not latencies:
            return 0.0
        index = max(0, min(len(latencies) - 1, int(p * len(latencies) + 0.999999) - 1))
        return latencies[index]

    return {
        "requests": requests,
        "duration_seconds": elapsed,
        "messages_per_second": requests / elapsed,
        "request_body_bytes": request_bytes,
        "response_body_bytes": response_bytes,
        "payload_bytes_per_second": (request_bytes + response_bytes) / elapsed,
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "failures": len(failures),
        "first_failure": {"error": failures[0]} if failures else None,
    }


if __name__ == "__main__":
    result = asyncio.run(run(json.loads(sys.argv[1])))
    print(json.dumps(result, separators=(",", ":")))
    if result["failures"] or result["requests"] == 0:
        raise SystemExit(1)
