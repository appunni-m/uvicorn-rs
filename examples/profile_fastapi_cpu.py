"""Diagnostic FastAPI app that accounts for CPU in its synchronous CPU route.

The endpoint and response stay the same as ``examples.bench_fastapi``. The
wrapper records thread CPU only during the signal-gated benchmark window and
writes a receipt when the server exits.
"""

from __future__ import annotations

import atexit
import functools
import json
import os
import threading
from pathlib import Path
from time import thread_time_ns

from fastapi.routing import APIRoute

from examples.bench_fastapi import app


_LOCK = threading.Lock()
_ACTIVE = False
_CPU_NS: list[int] = []


def _start_measurement() -> None:
    """Reset measurements immediately before the timed client load."""
    global _ACTIVE
    with _LOCK:
        _CPU_NS.clear()
        _ACTIVE = True


def _stop_measurement() -> None:
    """Stop counting synchronous endpoint CPU at the end of the timed load."""
    global _ACTIVE
    with _LOCK:
        _ACTIVE = False


def _measured_endpoint(endpoint):
    @functools.wraps(endpoint)
    def call(*args, **kwargs):
        with _LOCK:
            active = _ACTIVE
        if not active:
            return endpoint(*args, **kwargs)

        started = thread_time_ns()
        try:
            return endpoint(*args, **kwargs)
        finally:
            elapsed = max(0, thread_time_ns() - started)
            with _LOCK:
                _CPU_NS.append(elapsed)

    return call


_cpu_route_found = False
for _route in app.routes:
    if isinstance(_route, APIRoute) and _route.path == "/cpu/{iterations}":
        _wrapped = _measured_endpoint(_route.endpoint)
        _route.endpoint = _wrapped
        _route.dependant.call = _wrapped
        _cpu_route_found = True
        break

if not _cpu_route_found:
    raise RuntimeError("FastAPI CPU benchmark route was not found")


def _write_measurement() -> None:
    destination = os.environ.get("UVICORN_RS_CPU_ROUTE_PROFILE_OUT")
    if not destination:
        return
    with _LOCK:
        samples = list(_CPU_NS)
    values = sorted(samples)

    def percentile(fraction: float) -> int | None:
        if not values:
            return None
        index = max(0, min(len(values) - 1, round(fraction * (len(values) - 1))))
        return values[index]

    report = {
        "schema": "uvicorn-rs-fastapi-sync-route-cpu@1",
        "route": "/cpu/{iterations}",
        "thread_cpu_timer": "time.thread_time_ns",
        "requests_measured": len(values),
        "total_endpoint_thread_cpu_ns": sum(values),
        "mean_endpoint_thread_cpu_ns": round(sum(values) / len(values)) if values else None,
        "p50_endpoint_thread_cpu_ns": percentile(0.50),
        "p95_endpoint_thread_cpu_ns": percentile(0.95),
        "p99_endpoint_thread_cpu_ns": percentile(0.99),
        "messages_and_responses_unchanged": True,
        "measurement_boundary": (
            "Synchronous FastAPI endpoint function, including checksum loop and response-model "
            "construction; excludes FastAPI response serialization and server transport."
        ),
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


atexit.register(_write_measurement)
