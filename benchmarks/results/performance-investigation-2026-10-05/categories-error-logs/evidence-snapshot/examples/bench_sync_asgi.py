"""Synchronous ASGI callable returning an awaitable, for bridge benchmarks."""


async def _app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    await receive()
    body = b"Hello World!"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", b"12")],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


def app(scope, receive, send):
    return _app(scope, receive, send)
