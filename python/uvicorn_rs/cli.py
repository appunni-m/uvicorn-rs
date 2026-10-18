"""Command-line entry point."""

import argparse
import asyncio
import importlib
import signal
import sys

from .server import Server


def _load_app(import_string):
    try:
        module_name, app_name = import_string.split(":", maxsplit=1)
    except ValueError as exc:
        raise ValueError("application must use module:app syntax") from exc
    if not module_name or not app_name:
        raise ValueError("application must use module:app syntax")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, app_name)
    except AttributeError as exc:
        raise ValueError(f"application attribute {app_name!r} was not found") from exc


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="uvicorn-rs-py")
    parser.add_argument("app", help="ASGI application as module:app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--loop", choices=("asyncio", "uvloop"), default="asyncio")
    parser.add_argument("--certfile", help="PEM certificate chain; enables HTTPS and HTTP/3")
    parser.add_argument("--keyfile", help="PEM private key for --certfile")
    parser.add_argument("--graceful-timeout", type=int, default=10)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if bool(args.certfile) != bool(args.keyfile):
        print("uvicorn-rs-py: --certfile and --keyfile must be provided together", file=sys.stderr)
        raise SystemExit(2)
    try:
        app = _load_app(args.app)
    except (ImportError, ValueError) as exc:
        print(f"uvicorn-rs-py: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    loop_factory = None
    if args.loop == "uvloop":
        try:
            import uvloop
        except ImportError as exc:
            print("uvicorn-rs-py: --loop uvloop requires uvloop to be installed", file=sys.stderr)
            raise SystemExit(2) from exc
        loop_factory = uvloop.new_event_loop

    async def run():
        loop = asyncio.get_running_loop()
        shutdown_requested = asyncio.Event()
        server = Server(
            app,
            args.host,
            args.port,
            args.certfile,
            args.keyfile,
            args.graceful_timeout,
        )
        server_task = asyncio.create_task(
            server.serve()
        )
        shutdown_task = asyncio.create_task(shutdown_requested.wait())
        loop_signal_handlers = []
        fallback_signal_handlers = {}

        def request_shutdown(_signum, _frame):
            loop.call_soon_threadsafe(shutdown_requested.set)

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, shutdown_requested.set)
                loop_signal_handlers.append(signum)
            except (AttributeError, NotImplementedError, RuntimeError, ValueError):
                try:
                    fallback_signal_handlers[signum] = signal.getsignal(signum)
                    signal.signal(signum, request_shutdown)
                except (AttributeError, OSError, ValueError):
                    continue

        try:
            completed, _ = await asyncio.wait(
                (server_task, shutdown_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if server_task in completed:
                await server_task
                return

            # Stop the Rust runtime through its control token and leave the
            # Python task alive until the PyO3 future reports completion.
            server.shutdown()
            await asyncio.shield(server_task)
        except asyncio.CancelledError:
            # Preserve cancellation from callers that cancel the CLI coroutine
            # directly, but drain the native runtime before propagating it.
            server.shutdown()
            try:
                await asyncio.shield(server_task)
            except asyncio.CancelledError:
                pass
            raise
        finally:
            shutdown_task.cancel()
            await asyncio.gather(shutdown_task, return_exceptions=True)
            for signum in loop_signal_handlers:
                try:
                    loop.remove_signal_handler(signum)
                except (AttributeError, NotImplementedError, RuntimeError, ValueError):
                    pass
            for signum, previous_handler in fallback_signal_handlers.items():
                try:
                    signal.signal(signum, previous_handler)
                except (AttributeError, OSError, ValueError):
                    pass

    previous_signal_handlers = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous_signal_handlers[signum] = signal.getsignal(signum)
        except (AttributeError, OSError, ValueError):
            pass
    try:
        if sys.version_info >= (3, 11):
            with asyncio.Runner(loop_factory=loop_factory) as runner:
                runner.run(run())
        else:
            if loop_factory is not None:
                import uvloop

                uvloop.install()
            asyncio.run(run())
    except KeyboardInterrupt:
        return
    finally:
        # asyncio.Runner may install its own SIGINT handler before run() starts.
        # Restore the process handlers that were active when main() was called.
        for signum, previous_handler in previous_signal_handlers.items():
            try:
                signal.signal(signum, previous_handler)
            except (AttributeError, OSError, ValueError):
                pass


if __name__ == "__main__":
    main()
