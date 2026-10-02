"""ASGI app used to verify client-disconnect task cancellation."""

import asyncio
import sys


disconnect_seen = asyncio.Event()
send_error_seen = asyncio.Event()


async def app(scope, receive, send):
    if scope["path"] == "/slow":
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnect_seen.set()
                break
        return

    if scope["path"] == "/send-after-disconnect":
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
        try:
            await send({"type": "http.response.start", "status": 200, "headers": []})
        except OSError:
            send_error_seen.set()
        return

    if scope["path"] == "/cancelled":
        try:
            await asyncio.wait_for(disconnect_seen.wait(), timeout=2)
        except asyncio.TimeoutError:
            status, body = 504, b"http.disconnect was not delivered"
        else:
            status, body = 200, b"http.disconnect delivered"
    elif scope["path"] == "/send-error":
        try:
            await asyncio.wait_for(send_error_seen.wait(), timeout=2)
        except asyncio.TimeoutError:
            status, body = 504, b"send did not raise OSError"
        else:
            status, body = 200, b"send raised OSError"
    elif scope["path"] == "/hold":
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            print("APP_CANCELLED_BY_SHUTDOWN", file=sys.stderr, flush=True)
            raise
        return
    else:
        status, body = 404, b"not found"

    await send({"type": "http.response.start", "status": status, "headers": []})
    await send({"type": "http.response.body", "body": body, "more_body": False})
