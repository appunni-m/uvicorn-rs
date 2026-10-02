"""ASGI WebSocket echo app for black-box protocol probes."""


async def app(scope, receive, send):
    assert scope["type"] == "websocket"
    await receive()
    if scope["path"] == "/reject":
        await send({"type": "websocket.close", "code": 1008, "reason": "denied"})
        return

    await send(
        {
            "type": "websocket.accept",
            "subprotocol": "chat",
            "headers": [(b"x-asgi-ws", b"accepted")],
        }
    )
    while True:
        message = await receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("text") is not None:
            await send({"type": "websocket.send", "text": message["text"]})
        elif message.get("bytes") is not None:
            await send({"type": "websocket.send", "bytes": message["bytes"]})
