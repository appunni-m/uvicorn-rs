"""Command-line entry point."""

import argparse
import asyncio
import importlib
import os
import signal
import sys

from .server import Server


class ImportFromStringError(Exception):
    """An application import string could not be resolved."""


def _load_app(import_string):
    if not isinstance(import_string, str):
        return import_string
    module_name, separator, attrs = import_string.partition(":")
    if not module_name or not separator or not attrs:
        raise ImportFromStringError(
            f'Import string "{import_string}" must be in format "<module>:<attribute>".'
        )
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise ImportFromStringError(
            f'Could not import module "{module_name}".'
        ) from None
    instance = module
    try:
        for attr in attrs.split("."):
            instance = getattr(instance, attr)
    except AttributeError:
        raise ImportFromStringError(
            f'Attribute "{attrs}" not found in module "{module_name}".'
        ) from None
    return instance


def _parse_args(argv=None, prog="uvicorn-rs-py"):
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("app", help="ASGI application as module:app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--loop", choices=("asyncio", "uvloop"), default="asyncio")
    parser.add_argument("--lifespan", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--app-dir", default="")
    parser.add_argument("--root-path", default="")
    parser.add_argument("--factory", action="store_true")
    parser.add_argument("--certfile", help="PEM certificate chain; enables HTTPS and HTTP/3")
    parser.add_argument("--keyfile", help="PEM private key for --certfile")
    parser.add_argument("--graceful-timeout", type=int, default=10)
    parser.add_argument("--header", dest="headers", action="append", default=[])
    parser.add_argument("--server-header", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--date-header", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv=None, prog="uvicorn-rs-py"):
    args = _parse_args(argv, prog)
    if bool(args.certfile) != bool(args.keyfile):
        print(f"{prog}: --certfile and --keyfile must be provided together", file=sys.stderr)
        raise SystemExit(2)
    # Console-script launchers put their own directory at sys.path[0]. Uvicorn
    # resolves application imports from the working directory by default.
    app_dir = os.getcwd()
    if not sys.path or os.path.abspath(sys.path[0] or app_dir) != app_dir:
        sys.path.insert(0, app_dir)
    if args.app_dir:
        sys.path.insert(0, args.app_dir)
    try:
        app = _load_app(args.app)
    except ImportFromStringError as exc:
        print(f"ERROR:    Error loading ASGI app. {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    try:
        app = app()
    except TypeError as exc:
        if args.factory:
            print(f"ERROR:    Error loading ASGI app factory: {exc}", file=sys.stderr)
            raise SystemExit(3) from exc
    else:
        if not args.factory:
            print(
                "WARNING:  ASGI app factory detected. Using it, but please consider setting the --factory flag explicitly.",
                file=sys.stderr,
            )

    loop_factory = None
    if args.loop == "uvloop":
        try:
            import uvloop
        except ImportError as exc:
            print(f"{prog}: --loop uvloop requires uvloop to be installed", file=sys.stderr)
            raise SystemExit(2) from exc
        loop_factory = uvloop.new_event_loop

    async def run():
        loop = asyncio.get_running_loop()
        shutdown_requested = asyncio.Event()
        encoded_headers = [
            (name.lower().encode("latin1"), value.encode("latin1"))
            for name, value in (header.split(":", 1) for header in args.headers)
        ]
        if args.server_header and b"server" not in dict(encoded_headers):
            encoded_headers.insert(0, (b"server", b"uvicorn"))
        server = Server(
            app,
            args.host,
            args.port,
            args.certfile,
            args.keyfile,
            args.graceful_timeout,
            lifespan=args.lifespan != "off",
            root_path=args.root_path,
            default_headers=encoded_headers,
            date_header=args.date_header,
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
