"""Two-chunk fixed-body ASGI benchmark used by both servers."""


async def app(scope, receive, send):
    await receive()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"Hello ", "more_body": True})
    await send({"type": "http.response.body", "body": b"World!", "more_body": False})
