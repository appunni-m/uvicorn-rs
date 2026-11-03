"""Observe pinned aioquic request-end events without running a server or load."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile

import pylsqpack
from aioquic.h3.connection import H3Connection, FrameType, encode_frame
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.events import StreamDataReceived

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark_certificates import generate_server_certificate


def observe(cert, key, mode):
    configuration = QuicConfiguration(is_client=False)
    configuration.load_cert_chain(str(cert), str(key))
    quic = QuicConnection(
        configuration=configuration, original_destination_connection_id=b"12345678"
    )
    connection = H3Connection(quic)
    encoder = pylsqpack.Encoder()
    _, headers = encoder.encode(0, [
        (b":method", b"POST"), (b":scheme", b"https"),
        (b":authority", b"localhost"), (b":path", b"/upload/4"),
        (b"content-length", b"4"),
    ])
    wire = encode_frame(FrameType.HEADERS, headers) + encode_frame(FrameType.DATA, b"aaaa")
    if mode != "data-fin":
        wire += encode_frame(0x21, b"grease")
    inputs = [StreamDataReceived(
        data=wire, end_stream=mode != "data-grease-lone-fin", stream_id=0
    )]
    if mode == "data-grease-lone-fin":
        inputs.append(StreamDataReceived(data=b"", end_stream=True, stream_id=0))
    events = [event for item in inputs for event in connection.handle_event(item)]
    return {
        "case": mode,
        "wire_sha256": hashlib.sha256(wire).hexdigest(),
        "events": [{
            "type": type(event).__name__,
            "stream_ended": getattr(event, "stream_ended", None),
            "body_bytes": len(getattr(event, "data", b"")),
        } for event in events],
        "request_end_delivered": any(getattr(event, "stream_ended", False) for event in events),
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="aioquic-fin-reproducer-") as directory:
        _, cert, key = generate_server_certificate(Path(directory))
        rows = [observe(cert, key, mode) for mode in (
            "data-fin", "data-grease-fin", "data-grease-lone-fin"
        )]
    print(json.dumps({"aioquic_version": importlib.metadata.version("aioquic"), "rows": rows}, indent=2))
