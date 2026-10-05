"""Minimal glue that invokes ASGI callables on their owning Python loop."""


async def invoke(app, scope, io):
    async def receive():
        result = io.receive()
        if isinstance(result, dict):
            return result
        return await result

    async def send(message):
        pending = io.send(message)
        if pending is not None:
            await pending

    await app(scope, receive, send)
