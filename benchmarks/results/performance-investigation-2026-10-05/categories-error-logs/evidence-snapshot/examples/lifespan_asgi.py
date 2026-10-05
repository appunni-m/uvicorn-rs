"""ASGI app used to verify lifespan startup, state, and shutdown."""

import asyncio
import sys


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                scope["state"]["token"] = "startup-token"
                scope["state"]["nested"] = {"count": 0}
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                print("LIFESPAN_SHUTDOWN_COMPLETE", file=sys.stderr, flush=True)
                await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        if scope["path"] == "/hold":
            print("APP_HOLD_STARTED", file=sys.stderr, flush=True)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                print("APP_CANCELLED_BY_SHUTDOWN", file=sys.stderr, flush=True)
                raise
        state = scope["state"]
        observed = f"{state['token']}:{state['nested']['count']}"
        state["token"] = "request-token"
        state["nested"]["count"] += 1
        body = observed.encode()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body, "more_body": False})
