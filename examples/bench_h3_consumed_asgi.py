"""Protocol-scope workload that consumes the complete ASGI request body."""

from .bench_matrix_asgi import _receive_request, app as base_app


async def app(scope, receive, send):
    if scope["type"] != "http" or scope["path"] != "/protocol-consumed":
        await base_app(scope, receive, send)
        return

    size = await _receive_request(receive)
    if size is None:
        return
    body = f"http_version={scope['http_version']};bytes={size}".encode("ascii")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", str(len(body)).encode("ascii"))],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})
