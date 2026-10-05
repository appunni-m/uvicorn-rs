"""Small ASGI app used to verify negotiated HTTP protocol scopes."""


async def app(scope, receive, send):
    assert scope["type"] == "http"
    body = f"http_version={scope['http_version']}".encode()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body, "more_body": False})
