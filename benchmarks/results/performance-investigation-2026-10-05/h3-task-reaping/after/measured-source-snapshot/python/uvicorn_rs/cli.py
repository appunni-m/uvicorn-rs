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
    parser = argparse.ArgumentParser(prog="uvicorn-rs")
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
        print("uvicorn-rs: --certfile and --keyfile must be provided together", file=sys.stderr)
        raise SystemExit(2)
    try:
        app = _load_app(args.app)
    except (ImportError, ValueError) as exc:
        print(f"uvicorn-rs: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    loop_factory = None
    if args.loop == "uvloop":
        try:
            import uvloop
        except ImportError as exc:
            print("uvicorn-rs: --loop uvloop requires uvloop to be installed", file=sys.stderr)
            raise SystemExit(2) from exc
        loop_factory = uvloop.new_event_loop

    async def run():
        server_task = asyncio.create_task(
            Server(
                app,
                args.host,
                args.port,
                args.certfile,
                args.keyfile,
                args.graceful_timeout,
            ).serve()
        )
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(signal.SIGTERM, server_task.cancel)
        except (AttributeError, NotImplementedError, RuntimeError):
            pass
        try:
            await server_task
        except asyncio.CancelledError:
            return
        finally:
            try:
                loop.remove_signal_handler(signal.SIGTERM)
            except (AttributeError, NotImplementedError, RuntimeError):
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


if __name__ == "__main__":
    main()
