"""A minimal fixed-response ASGI app shared by both benchmark servers."""


async def app(scope, receive, send):
    await receive()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-length", b"12"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello World!", "more_body": False})
