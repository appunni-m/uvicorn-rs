"""ASGI app used for request/response streaming probes."""

import asyncio


async def app(scope, receive, send):
    if scope["path"] == "/upload":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            if body:
                await send(
                    {"type": "http.response.body", "body": body, "more_body": True}
                )
            if not message.get("more_body", False):
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
                return

    if scope["path"] == "/response":
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {"type": "http.response.body", "body": b"first", "more_body": True}
        )
        await asyncio.sleep(0.05)
        await send(
            {"type": "http.response.body", "body": b"second", "more_body": True}
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        return

    await send({"type": "http.response.start", "status": 404, "headers": []})
    await send({"type": "http.response.body", "body": b"missing", "more_body": False})
