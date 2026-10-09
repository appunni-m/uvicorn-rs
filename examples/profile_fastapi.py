"""Diagnostic ASGI stage timings for the maintained FastAPI benchmark app.

This wrapper keeps the ASGI messages unchanged. Its measurements are
diagnostic-only: timing calls around every send and receive perturb the
request path and must not be used as ordinary performance results.
"""

from __future__ import annotations

import atexit
import json
import math
import os
from array import array
from collections import Counter
from pathlib import Path
from time import perf_counter_ns

from examples.bench_fastapi import app as fastapi_app


_MAX_RETAINED_PER_PATH = 250_000
_DURATION_FIELDS = (
    "asgi_app_wall_ns",
    "asgi_receive_await_ns",
    "asgi_send_await_ns",
    "app_outside_asgi_io_await_ns",
)
_VALUE_FIELDS = (
    "receive_calls",
    "send_calls",
    "request_body_bytes",
    "response_body_bytes",
)
_REQUESTS: dict[str, int] = Counter()
_TOTALS: dict[str, Counter] = {}
_SAMPLES: dict[str, dict[str, array]] = {}


def _path_stats(path: str) -> tuple[Counter, dict[str, array]]:
    totals = _TOTALS.setdefault(path, Counter())
    samples = _SAMPLES.get(path)
    if samples is None:
        samples = {name: array("Q") for name in (*_DURATION_FIELDS, *_VALUE_FIELDS)}
        _SAMPLES[path] = samples
    return totals, samples


async def app(scope, receive, send):
    """Time FastAPI and each awaited ASGI send/receive call without rewriting messages."""
    if scope.get("type") != "http":
        await fastapi_app(scope, receive, send)
        return

    path = str(scope.get("path", ""))
    totals, samples = _path_stats(path)
    request = {
        "receive_calls": 0,
        "send_calls": 0,
        "request_body_bytes": 0,
        "response_body_bytes": 0,
        "receive_await_ns": 0,
        "send_await_ns": 0,
        "message_types": Counter(),
    }

    async def timed_receive():
        started = perf_counter_ns()
        try:
            message = await receive()
        finally:
            request["receive_await_ns"] += perf_counter_ns() - started
            request["receive_calls"] += 1
        if isinstance(message, dict):
            message_type = message.get("type")
            if isinstance(message_type, str):
                request["message_types"][f"receive:{message_type}"] += 1
            if message_type == "http.request":
                request["request_body_bytes"] += len(message.get("body", b""))
        return message

    async def timed_send(message):
        request["send_calls"] += 1
        if isinstance(message, dict):
            message_type = message.get("type")
            if isinstance(message_type, str):
                request["message_types"][f"send:{message_type}"] += 1
            if message_type == "http.response.body":
                request["response_body_bytes"] += len(message.get("body", b""))
        started = perf_counter_ns()
        try:
            await send(message)
        finally:
            request["send_await_ns"] += perf_counter_ns() - started

    app_started = perf_counter_ns()
    try:
        await fastapi_app(scope, timed_receive, timed_send)
    finally:
        app_wall_ns = perf_counter_ns() - app_started
        receive_ns = request["receive_await_ns"]
        send_ns = request["send_await_ns"]
        outside_ns = max(0, app_wall_ns - receive_ns - send_ns)
        _REQUESTS[path] += 1
        totals["requests_seen"] += 1
        for key, value in request["message_types"].items():
            totals[key] += value
        for key, value in request.items():
            if key != "message_types":
                totals[key] += value
        values = {
            "asgi_app_wall_ns": app_wall_ns,
            "asgi_receive_await_ns": receive_ns,
            "asgi_send_await_ns": send_ns,
            "app_outside_asgi_io_await_ns": outside_ns,
            **{key: request[key] for key in _VALUE_FIELDS},
        }
        for key, value in values.items():
            retained = samples[key]
            if len(retained) < _MAX_RETAINED_PER_PATH:
                retained.append(value)


def _percentile(sorted_values: list[int], quantile: float) -> int | None:
    if not sorted_values:
        return None
    return sorted_values[max(0, math.ceil(quantile * len(sorted_values)) - 1)]


def _distribution(values: array) -> dict[str, int | None]:
    ordered = sorted(values)
    return {
        "samples": len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "mean": round(sum(ordered) / len(ordered)) if ordered else None,
    }


def _write_timings() -> None:
    destination = os.environ.get("UVICORN_RS_ASGI_TIMINGS")
    if not destination:
        return

    paths = {}
    for path, totals in _TOTALS.items():
        samples = _SAMPLES[path]
        app_wall = _distribution(samples["asgi_app_wall_ns"])
        paths[path] = {
            "requests_seen": _REQUESTS[path],
            "durations_retained": min(
                len(samples["asgi_app_wall_ns"]), _MAX_RETAINED_PER_PATH
            ),
            "retention_limit_per_path": _MAX_RETAINED_PER_PATH,
            "per_request": {
                name: _distribution(samples[name])
                for name in (*_DURATION_FIELDS, *_VALUE_FIELDS)
            },
            "p50_ns": app_wall["p50"],
            "p95_ns": app_wall["p95"],
            "p99_ns": app_wall["p99"],
            "mean_ns": app_wall["mean"],
            "totals": dict(sorted(totals.items())),
        }

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "profiling_only": True,
                "measurement": (
                    "per-request FastAPI ASGI-call wall time and awaited send/receive time; "
                    "outside_asgi_io_await includes Python/framework work and any other awaits, "
                    "so it is not CPU time"
                ),
                "messages_unchanged": True,
                "paths": paths,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


atexit.register(_write_timings)
