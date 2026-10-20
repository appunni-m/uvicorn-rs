"""A small ASGI 3 app for the first server round-trip probe."""


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
        return

    if scope["type"] != "http":
        return

    request = await receive()
    request_body = request.get("body", b"")
    response_body = (
        f"{scope['method']} {scope['path']} {scope['http_version']} ".encode()
        + request_body
    )
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": response_body, "more_body": False})
