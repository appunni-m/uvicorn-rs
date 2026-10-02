"""Checks that the initial call, coroutine, and ContextVar stay on asyncio."""

import asyncio
from contextvars import ContextVar
from threading import get_ident


request_context = ContextVar("request_context", default="missing")
request_context.set("caller-context")
import_thread = get_ident()


def app(scope, receive, send):
    """A sync callable returning an awaitable, as allowed at this boundary."""
    call_on_import_thread = get_ident() == import_thread
    return respond(scope, receive, send, call_on_import_thread)


async def respond(scope, receive, send, call_on_import_thread):
    request = await receive()
    loop_running = asyncio.get_running_loop().is_running()
    context_value = request_context.get()
    body = (
        f"call_thread={call_on_import_thread};loop={loop_running};"
        f"context={context_value};request={request.get('body', b'').decode()}"
    ).encode()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body, "more_body": False})
