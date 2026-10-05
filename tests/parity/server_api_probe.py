"""Exercise public server APIs while keeping the caller's event loop alive."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import _record, app
from uvicorn_rs import Server


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int)
    parser.add_argument("graceful_timeout", type=int)
    parser.add_argument("shutdown_path", type=Path)
    parser.add_argument("--server", choices=("uvicorn", "uvicorn-rs"), default="uvicorn-rs")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--task-factory", choices=("asyncio", "eager"), default="asyncio")
    parser.add_argument("--cleanup-delay", type=float, default=0.5)
    args = parser.parse_args()
    application_tasks = set()
    lifespan_tasks = set()
    lifespan_shutdown_completed = False

    async def observed_app(scope, receive, send):
        nonlocal lifespan_shutdown_completed
        if scope["type"] == "http":
            application_tasks.add(asyncio.current_task())
        elif scope["type"] == "lifespan":
            lifespan_tasks.add(asyncio.current_task())

        async def observed_send(message):
            nonlocal lifespan_shutdown_completed
            await send(message)
            if scope["type"] == "lifespan" and message.get("type") == "lifespan.shutdown.complete":
                lifespan_shutdown_completed = True

        cancelled = False
        try:
            await app(scope, receive, observed_send)
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            if cancelled and args.task_factory == "eager":
                role = "lifespan" if scope["type"] == "lifespan" else "application"
                _record(f"{role}.async-finally.started")
                await asyncio.sleep(args.cleanup_delay)
                _record(f"{role}.async-finally.finished")

    application = observed_app if args.snapshot is not None else app
    if args.task_factory == "eager":
        asyncio.get_running_loop().set_task_factory(asyncio.eager_task_factory)
    if args.server == "uvicorn":
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(
            application,
            host="127.0.0.1",
            port=args.port,
            loop="asyncio",
            http="httptools",
            interface="asgi3",
            lifespan="on",
            log_level="error",
            access_log=False,
            timeout_graceful_shutdown=args.graceful_timeout,
        ))
    else:
        server = Server(
            application,
            host="127.0.0.1",
            port=args.port,
            graceful_timeout=args.graceful_timeout,
        )
    server_task = asyncio.create_task(server.serve())

    while not server_task.done() and not args.shutdown_path.exists():
        await asyncio.sleep(0.01)

    if server_task.done():
        await server_task
        return

    loop = asyncio.get_running_loop()
    shutdown_started = loop.time()
    if args.server == "uvicorn":
        server.should_exit = True
    else:
        server_task.cancel()
    serve_cancellation_propagated = False
    try:
        await server_task
    except asyncio.CancelledError:
        serve_cancellation_propagated = True

    if args.snapshot is not None:
        events_path = Path(os.environ["ASGI_PARITY_EVENTS"])
        # Snapshot immediately after serve() settles, while the owning loop
        # still runs. Cleanup below and asyncio.run() must not supply evidence
        # for server-owned application cancellation or completion.
        snapshot = {
            "server_task_finished": server_task.done(),
            "serve_cancellation_propagated": serve_cancellation_propagated,
            "application_tasks_finished_before_probe_cleanup": (
                bool(application_tasks) and all(task.done() for task in application_tasks)
            ),
            "lifespan_tasks_finished_before_probe_cleanup": (
                bool(lifespan_tasks) and all(task.done() for task in lifespan_tasks)
            ),
            "loop_alive_after_server_return": loop.is_running(),
            "shutdown_elapsed_seconds": loop.time() - shutdown_started,
            "lifespan_shutdown_completed": lifespan_shutdown_completed,
            "application_events": [
                json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()
                if line
            ],
        }
        args.snapshot.write_text(json.dumps(snapshot), encoding="utf-8")
        pending_tasks = [task for task in application_tasks | lifespan_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
