"""Input-only Uvicorn extension protocol used by the WebSocket parity matrix."""

from __future__ import annotations

import asyncio
import base64
import hashlib


class ParityCustomWebSocketProtocol(asyncio.Protocol):
    """Echo WebSocket frames with lifespan state to prove custom-class dispatch."""

    def __init__(self, config, server_state, app_state):
        self.config = config
        self.server_state = server_state
        self.app_state = app_state
        self.transport = None
        self.buffer = bytearray()
        self.handshake_complete = False
        self.prefix = (
            b"ready:"
            if app_state.get("parity-token") == "ready"
            else b"missing-lifespan-state:"
        )

    def connection_made(self, transport):
        self.transport = transport
        self.server_state.connections.add(self)
        if transport.get_extra_info("ssl_object") is not None:
            self.prefix = (
                b"ready-tls:"
                if self.app_state.get("parity-token") == "ready"
                else b"missing-tls-lifespan-state:"
            )

    def data_received(self, data):
        if self.transport is None:
            return
        self.buffer.extend(data)
        if not self.handshake_complete:
            delimiter = self.buffer.find(b"\r\n\r\n")
            if delimiter < 0:
                return
            request = bytes(self.buffer[: delimiter + 4])
            del self.buffer[: delimiter + 4]
            self._accept_handshake(request)
        if self.handshake_complete:
            self._process_frames()

    def _accept_handshake(self, request):
        if self.transport is None:
            return
        key = None
        for line in request.split(b"\r\n")[1:]:
            name, separator, value = line.partition(b":")
            if separator and name.strip().lower() == b"sec-websocket-key":
                key = value.strip()
                break
        if not key:
            self.transport.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            self.transport.close()
            return
        accept = base64.b64encode(
            hashlib.sha1(
                key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            ).digest()
        )
        self.transport.write(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: "
            + accept
            + b"\r\n\r\n"
        )
        self.server_state.total_requests += 1
        self.handshake_complete = True

    def _process_frames(self):
        while self.transport is not None and len(self.buffer) >= 2:
            first, second = self.buffer[0], self.buffer[1]
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            payload_length = second & 0x7F
            offset = 2
            if payload_length == 126:
                if len(self.buffer) < offset + 2:
                    return
                payload_length = int.from_bytes(self.buffer[offset : offset + 2], "big")
                offset += 2
            elif payload_length == 127:
                if len(self.buffer) < offset + 8:
                    return
                payload_length = int.from_bytes(self.buffer[offset : offset + 8], "big")
                offset += 8
            mask = b""
            if masked:
                if len(self.buffer) < offset + 4:
                    return
                mask = bytes(self.buffer[offset : offset + 4])
                offset += 4
            if len(self.buffer) < offset + payload_length:
                return
            payload = bytes(self.buffer[offset : offset + payload_length])
            del self.buffer[: offset + payload_length]
            if masked:
                payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            if opcode == 0x8:
                self.transport.write(_frame(0x8, payload))
                self.transport.close()
                return
            if opcode == 0x9:
                self.transport.write(_frame(0xA, payload))
                continue
            if opcode in {0x1, 0x2}:
                response_opcode = opcode
                response = self.prefix + payload
                self.transport.write(_frame(response_opcode, response))

    def shutdown(self):
        if self.transport is not None:
            if self.handshake_complete:
                self.transport.write(_frame(0x8, (1001).to_bytes(2, "big")))
            self.transport.close()

    def connection_lost(self, exc):
        self.server_state.connections.discard(self)
        self.transport = None


def _frame(opcode, payload):
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes((first, length))
    elif length < 65536:
        header = bytes((first, 126)) + length.to_bytes(2, "big")
    else:
        header = bytes((first, 127)) + length.to_bytes(8, "big")
    return header + payload
