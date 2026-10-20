"""Minimal glue that invokes ASGI callables on their owning Python loop."""

import logging
from urllib.parse import quote


error_logger = logging.getLogger("uvicorn.error")
access_logger = logging.getLogger("uvicorn.access")


def log_concurrency_limit_rejection(
    client_host, client_port, method, path, query, http_version
):
    """Emit Uvicorn's warning and access records for a Rust-generated 503."""
    error_logger.warning("Exceeded concurrency limit.")
    if access_logger.hasHandlers():
        full_path = quote(path)
        if query:
            full_path = f"{full_path}?{query}"
        access_logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "%s:%d" % (client_host, client_port),
            method,
            full_path,
            http_version,
            503,
        )


async def invoke(app, scope, io):
    scope_type = scope.get("type")
    if scope_type == "lifespan":
        error_logger.info("Waiting for application startup.")

    async def receive():
        result = io.receive()
        if isinstance(result, dict):
            message = result
        else:
            message = await result
        if scope_type == "lifespan" and message.get("type") == "lifespan.shutdown":
            error_logger.info("Waiting for application shutdown.")
        return message

    async def send(message):
        pending = io.send(message)
        if pending is not None:
            await pending
        if not isinstance(message, dict):
            return
        event_type = message.get("type")
        if scope_type == "lifespan":
            if event_type == "lifespan.startup.complete":
                error_logger.info("Application startup complete.")
            elif event_type == "lifespan.shutdown.complete":
                error_logger.info("Application shutdown complete.")
        elif scope_type == "http" and event_type == "http.response.start" and access_logger.hasHandlers():
            client = scope.get("client")
            client_addr = "%s:%d" % client if client else ""
            full_path = quote(scope["path"])
            if scope["query_string"]:
                full_path = f"{full_path}?{scope['query_string'].decode('ascii')}"
            access_logger.info(
                '%s - "%s %s HTTP/%s" %d',
                client_addr,
                scope["method"],
                full_path,
                scope["http_version"],
                message["status"],
            )

    await app(scope, receive, send)
