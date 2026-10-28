"""Minimal glue that invokes ASGI callables on their owning Python loop."""

import array
import asyncio
import contextvars
import os
import socket
import sys
import time
import logging
from urllib.parse import quote


error_logger = logging.getLogger("uvicorn.error")
access_logger = logging.getLogger("uvicorn.access")


def send_listener_fds(path, listeners, stop_event=None):
    """Transfer pre-bound TCP listeners, stopping if Rust exits before bind."""
    if not hasattr(socket, "SCM_RIGHTS"):
        raise NotImplementedError("inherited TCP listeners require Unix descriptor passing")
    listeners = list(listeners)
    if not listeners:
        raise ValueError("at least one pre-bound TCP listener is required")
    for listener in listeners:
        # Uvicorn wraps --fd listeners as AF_UNIX even when the descriptor is
        # an IPv4 or IPv6 socket. Detect the underlying descriptor's family so
        # worker mode validates the same TCP listener that single-worker mode
        # passes to the native server.
        with socket.socket(fileno=os.dup(listener.fileno())) as actual_listener:
            if actual_listener.family not in (socket.AF_INET, socket.AF_INET6):
                raise ValueError("only pre-bound IPv4 and IPv6 TCP listeners are supported")
            if actual_listener.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
                raise ValueError("the inherited socket must be a TCP stream listener")
    for listener in listeners:
        listener.setblocking(False)
    deadline = time.monotonic() + 5.0
    while True:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
            try:
                control.connect(path)
            except (FileNotFoundError, ConnectionRefusedError):
                if stop_event is not None and stop_event.is_set():
                    return
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
                continue
            for listener in listeners:
                descriptors = array.array("i", [listener.fileno()])
                sent = control.sendmsg(
                    [b"L"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors)]
                )
                if sent != 1:
                    raise OSError("incomplete inherited listener descriptor transfer")
            control.sendall(b"E")
            return


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
    response_started = False
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
        nonlocal response_started
        if (
            scope_type == "http"
            and isinstance(message, dict)
            and message.get("type") == "http.response.start"
        ):
            # Uvicorn treats a response-start attempt as committed before its
            # protocol validates status and headers. If validation fails, do
            # not turn that exception into a second, synthetic HTTP 500.
            response_started = True
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
        elif scope_type == "http" and event_type == "http.response.start":
            if access_logger.hasHandlers():
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

    try:
        await app(scope, receive, send)
    except BaseException as error:
        if scope_type != "http":
            raise
        if response_started:
            error_logger.exception("Exception in ASGI application")
            try:
                setattr(error, "_uvicorn_rs_logged_asgi_error", True)
            except BaseException:
                pass
            raise
        error_logger.exception("Exception in ASGI application")
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"" if scope.get("http_version") == "3" else b"Internal Server Error",
            }
        )


async def invoke_with_reset_contextvars(app, scope, io):
    """Invoke HTTP requests in an empty context, matching Uvicorn's option."""
    if scope.get("type") != "http":
        await invoke(app, scope, io)
        return

    loop = asyncio.get_running_loop()
    invocation = invoke(app, scope, io)
    if sys.version_info >= (3, 11):
        task = loop.create_task(invocation, context=contextvars.Context())
    else:
        task = contextvars.Context().run(loop.create_task, invocation)
    await task
