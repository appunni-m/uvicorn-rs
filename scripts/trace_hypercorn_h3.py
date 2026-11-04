#!/usr/bin/env python3
"""Run Hypercorn with a bounded HTTP/3 stream-lifecycle trace."""

from __future__ import annotations

import atexit
import json
import sys
import time
from collections import deque
from pathlib import Path


# Executing this wrapper by file path puts ``scripts/`` at sys.path[0], unlike
# ``python -m hypercorn`` which keeps the working directory importable. Restore
# the repository root so Hypercorn can resolve the benchmark app target.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aioquic.h3.connection import H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from hypercorn.__main__ import main as hypercorn_main
from hypercorn.protocol.events import StreamClosed
from hypercorn.protocol.h3 import H3Protocol


MAX_TRACE_EVENTS = 512
TRACE_SCHEMA = "hypercorn-h3-stream-v5"
_protocols_by_connection: dict[int, H3Protocol] = {}
_trace_records: deque[dict[str, object]] = deque(maxlen=MAX_TRACE_EVENTS)
_recorded_events = 0
_overwritten_events = 0
_trace_flushed = False


def _record(protocol: H3Protocol | None, event: str, **fields: object) -> None:
    global _recorded_events, _overwritten_events
    _recorded_events += 1
    record: dict[str, object] = {
        "trace": TRACE_SCHEMA,
        "sequence": _recorded_events,
        "time_ns": time.monotonic_ns(),
        "event": event,
    }
    if protocol is not None:
        record["connection_id"] = id(protocol.connection)
        record["active_stream_ids"] = sorted(protocol.streams)[:64]
    record.update(fields)
    if len(_trace_records) == MAX_TRACE_EVENTS:
        _overwritten_events += 1
    _trace_records.append(record)


def _flush_trace(reason: str) -> None:
    global _trace_flushed
    if _trace_flushed:
        return
    _trace_flushed = True
    for record in _trace_records:
        sys.stderr.write("H3TRACE " + json.dumps(record, sort_keys=True) + "\n")
    sys.stderr.write(
        "H3TRACE "
        + json.dumps(
            {
                "trace": TRACE_SCHEMA,
                "event": "summary",
                "recorded_events": _recorded_events,
                "retained_events": len(_trace_records),
                "overwritten_events": _overwritten_events,
                "max_events": MAX_TRACE_EVENTS,
                "flush_reason": reason,
            },
            sort_keys=True,
        )
        + "\n"
    )
    sys.stderr.flush()


def _trace_summary() -> None:
    _flush_trace("process-exit")


class _TracedStreamMap(dict):
    """Record the exact lookup that would otherwise raise the missing-stream error."""

    def __init__(self, protocol: H3Protocol, streams: dict) -> None:
        super().__init__(streams)
        self.protocol = protocol

    def __getitem__(self, stream_id: int):
        try:
            return super().__getitem__(stream_id)
        except KeyError:
            _record(
                self.protocol,
                "stream_lookup_missing",
                stream_id=stream_id,
                quic_event_type=getattr(self.protocol, "_trace_quic_event_type", None),
                mapped_at_lookup=False,
            )
            raise


_original_protocol_init = H3Protocol.__init__


def _traced_protocol_init(self: H3Protocol, *args: object, **kwargs: object) -> None:
    _original_protocol_init(self, *args, **kwargs)
    self.streams = _TracedStreamMap(self, self.streams)
    _protocols_by_connection[id(self.connection)] = self
    _record(self, "connection_created")


H3Protocol.__init__ = _traced_protocol_init  # type: ignore[method-assign]

_original_handle_event = H3Connection.handle_event


def _traced_handle_event(self: H3Connection, quic_event: object):
    protocol = _protocols_by_connection.get(id(self))
    quic_event_type = type(quic_event).__name__
    quic_stream_id = getattr(quic_event, "stream_id", None)
    quic_data = getattr(quic_event, "data", None)
    internal_streams = getattr(self, "_stream", None)
    aioquic_stream_present_before = (
        quic_stream_id in internal_streams
        if isinstance(quic_stream_id, int) and isinstance(internal_streams, dict)
        else None
    )
    _record(
        protocol,
        "quic_event_before_h3_decode",
        quic_event_type=quic_event_type,
        quic_stream_id=quic_stream_id,
        data_length=(
            len(quic_data)
            if isinstance(quic_data, (bytes, bytearray, memoryview))
            else None
        ),
        quic_end_stream=getattr(
            quic_event, "end_stream", getattr(quic_event, "fin", None)
        ),
        hypercorn_stream_present_before=(
            quic_stream_id in protocol.streams
            if protocol is not None and isinstance(quic_stream_id, int)
            else None
        ),
        aioquic_stream_present_before=aioquic_stream_present_before,
    )
    try:
        events = _original_handle_event(self, quic_event)
    except BaseException as error:
        _record(
            protocol,
            "h3_decode_error",
            quic_event_type=quic_event_type,
            quic_stream_id=quic_stream_id,
            error_type=type(error).__name__,
            error_key=(
                repr(error.args[0])
                if isinstance(error, KeyError) and error.args
                else None
            ),
        )
        raise

    internal_streams = getattr(self, "_stream", None)
    aioquic_stream_present_after = (
        quic_stream_id in internal_streams
        if isinstance(quic_stream_id, int) and isinstance(internal_streams, dict)
        else None
    )
    for event in events:
        stream_id = getattr(event, "stream_id", None)
        mapped_before = (
            protocol is not None
            and isinstance(stream_id, int)
            and stream_id in protocol.streams
        )
        if isinstance(event, HeadersReceived):
            _record(
                protocol,
                "HeadersReceived",
                quic_event_type=type(quic_event).__name__,
                stream_id=event.stream_id,
                stream_ended=event.stream_ended,
                mapped_before=mapped_before,
                aioquic_stream_present_after=aioquic_stream_present_after,
            )
        elif isinstance(event, DataReceived):
            _record(
                protocol,
                "DataReceived",
                quic_event_type=type(quic_event).__name__,
                stream_id=event.stream_id,
                stream_ended=event.stream_ended,
                data_length=len(event.data),
                mapped_before=mapped_before,
                aioquic_stream_present_after=aioquic_stream_present_after,
            )
        else:
            _record(
                protocol,
                "H3Event",
                h3_event_type=type(event).__name__,
                quic_event_type=type(quic_event).__name__,
                stream_id=stream_id,
                mapped_before=mapped_before,
                aioquic_stream_present_after=aioquic_stream_present_after,
            )
    return events


H3Connection.handle_event = _traced_handle_event  # type: ignore[method-assign]

_original_stream_send = H3Protocol.stream_send


async def _traced_stream_send(self: H3Protocol, event: object) -> None:
    if isinstance(event, StreamClosed):
        mapped_before = event.stream_id in self.streams
        _record(
            self,
            "StreamClosed_before_pop",
            stream_id=event.stream_id,
            mapped_before=mapped_before,
        )
        try:
            await _original_stream_send(self, event)
        finally:
            _record(
                self,
                "StreamClosed_after_pop",
                stream_id=event.stream_id,
                mapped_after=event.stream_id in self.streams,
            )
        return
    await _original_stream_send(self, event)


H3Protocol.stream_send = _traced_stream_send  # type: ignore[method-assign]

_original_create_stream = H3Protocol._create_stream


async def _traced_create_stream(self: H3Protocol, request: HeadersReceived) -> None:
    stream_id = request.stream_id
    method = next(
        (value.decode("ascii", errors="replace") for name, value in request.headers if name == b":method"),
        None,
    )
    fields = {
        "stream_id": stream_id,
        "request_method": method,
        "stream_ended": request.stream_ended,
    }
    _record(
        self,
        "stream_create_start",
        mapped_before=stream_id in self.streams,
        **fields,
    )
    error_type: str | None = None
    try:
        await _original_create_stream(self, request)
    except BaseException as error:
        error_type = type(error).__name__
        raise
    finally:
        _record(
            self,
            "stream_create_error" if error_type is not None else "stream_create_end",
            mapped_after=stream_id in self.streams,
            error_type=error_type,
            **fields,
        )


H3Protocol._create_stream = _traced_create_stream  # type: ignore[method-assign]

_original_protocol_handle = H3Protocol.handle


async def _traced_protocol_handle(self: H3Protocol, quic_event: object) -> None:
    self._trace_quic_event_type = type(quic_event).__name__
    try:
        await _original_protocol_handle(self, quic_event)
    except KeyError as error:
        key = error.args[0] if error.args else None
        _record(
            self,
            "protocol_handle_KeyError",
            key=repr(key) if key is not None else repr(error),
            stream_id=key if isinstance(key, int) else None,
            mapped_at_error=isinstance(key, int) and key in self.streams,
            quic_event_type=type(quic_event).__name__,
        )
        _flush_trace("protocol-handle-key-error")
        raise
    finally:
        self._trace_quic_event_type = None


H3Protocol.handle = _traced_protocol_handle  # type: ignore[method-assign]

atexit.register(_trace_summary)

if __name__ == "__main__":
    raise SystemExit(hypercorn_main(sys.argv[1:]))
