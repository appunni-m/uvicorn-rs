"""Command-line entry point."""

import argparse
import importlib
import os
import sys


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
    parser.add_argument("--uds", help="Bind to a Unix domain socket")
    parser.add_argument("--fd", type=int, help="Use an inherited listening socket descriptor")
    parser.add_argument("--loop", choices=("asyncio", "uvloop"), default="asyncio")
    parser.add_argument(
        "--log-level",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
    )
    parser.add_argument("--log-config")
    parser.add_argument(
        "--access-log", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--use-colors", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--lifespan", choices=("auto", "on", "off"), default="auto")
    parser.add_argument(
        "--interface", choices=("auto", "asgi3", "asgi2", "wsgi"), default="auto"
    )
    parser.add_argument("--app-dir", default="")
    parser.add_argument("--root-path", default="")
    parser.add_argument("--factory", action="store_true")
    parser.add_argument("--env-file")
    parser.add_argument("--certfile", help="PEM certificate chain; enables HTTPS and HTTP/3")
    parser.add_argument("--keyfile", help="PEM private key for --certfile")
    parser.add_argument("--graceful-timeout", type=int, default=10)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--timeout-worker-healthcheck", type=int, default=5)
    parser.add_argument("--limit-concurrency", type=int)
    parser.add_argument("--limit-max-requests", type=int)
    parser.add_argument("--limit-max-requests-jitter", type=int, default=0)
    parser.add_argument(
        "--backlog",
        type=int,
        default=2048,
        help="Maximum number of connections to hold in backlog",
    )
    parser.add_argument(
        "--timeout-keep-alive",
        type=int,
        default=5,
        help="Close idle keep-alive connections after this many seconds",
    )
    parser.add_argument("--ws-max-size", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--ws-ping-interval", type=float, default=20.0)
    parser.add_argument("--ws-ping-timeout", type=float, default=20.0)
    parser.add_argument("--header", dest="headers", action="append", default=[])
    parser.add_argument("--server-header", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--date-header", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--proxy-headers", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--forwarded-allow-ips")
    return parser.parse_args(argv)


def main(argv=None, prog="uvicorn-rs-py"):
    args = _parse_args(argv, prog)
    if not args.app_dir:
        app_directory = os.getcwd()
        if app_directory not in sys.path:
            sys.path.insert(0, app_directory)
    if bool(args.certfile) != bool(args.keyfile):
        print(
            f"{prog}: --certfile and --keyfile must be provided together",
            file=sys.stderr,
        )
        raise SystemExit(2)
    from uvicorn import run as uvicorn_run
    from uvicorn.config import LOGGING_CONFIG

    headers = [header.split(":", 1) for header in args.headers]
    uvicorn_run(
        args.app,
        host=args.host,
        port=args.port,
        uds=args.uds,
        fd=args.fd,
        loop=args.loop,
        log_config=LOGGING_CONFIG if args.log_config is None else args.log_config,
        log_level=args.log_level,
        access_log=args.access_log,
        use_colors=args.use_colors,
        lifespan=args.lifespan,
        interface=args.interface,
        env_file=args.env_file,
        forwarded_allow_ips=args.forwarded_allow_ips,
        proxy_headers=args.proxy_headers,
        root_path=args.root_path,
        limit_concurrency=args.limit_concurrency,
        limit_max_requests=args.limit_max_requests,
        limit_max_requests_jitter=args.limit_max_requests_jitter,
        backlog=args.backlog,
        timeout_keep_alive=args.timeout_keep_alive,
        ws_max_size=args.ws_max_size,
        ws_ping_interval=args.ws_ping_interval,
        ws_ping_timeout=args.ws_ping_timeout,
        timeout_graceful_shutdown=args.graceful_timeout,
        workers=args.workers,
        timeout_worker_healthcheck=args.timeout_worker_healthcheck,
        ssl_certfile=args.certfile,
        ssl_keyfile=args.keyfile,
        headers=headers,
        server_header=args.server_header,
        date_header=args.date_header,
        app_dir=args.app_dir or None,
        factory=args.factory,
    )


if __name__ == "__main__":
    main()
