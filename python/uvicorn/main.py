# Copyright (c) 2026 Appunni M
# CLI option definitions are adapted from Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Uvicorn-compatible command-line surface backed by uvicorn-rs."""

from __future__ import annotations

import platform
import ssl
import sys
from typing import Any, get_args

import click

from uvicorn import __version__
from uvicorn.config import LOGGING_CONFIG


LEVEL_CHOICES = click.Choice(["critical", "error", "warning", "info", "debug", "trace"])
LIFESPAN_CHOICES = click.Choice(["auto", "on", "off"])
INTERFACE_CHOICES = click.Choice(["auto", "asgi3", "asgi2", "wsgi"])


def _metavar_from_type(_type: Any) -> str:
    return f"[{'|'.join(key for key in get_args(_type) if key != 'none')}]"


def print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(
        "Running uvicorn {version} with {py_implementation} {py_version} on {system}".format(
            version=__version__,
            py_implementation=platform.python_implementation(),
            py_version=sys.version.split()[0],
            system=platform.system(),
        )
    )
    ctx.exit()


@click.command(context_settings={"auto_envvar_prefix": "UVICORN"})
@click.argument("app", envvar="UVICORN_APP")
@click.option("--host", type=str, default="127.0.0.1", help="Bind socket to this host.", show_default=True)
@click.option(
    "--port",
    type=int,
    default=8000,
    help="Bind socket to this port. If 0, an available port will be picked.",
    show_default=True,
)
@click.option("--uds", type=str, default=None, help="Bind to a UNIX domain socket.")
@click.option("--fd", type=int, default=None, help="Bind to socket from this file descriptor.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload.")
@click.option(
    "--reload-dir",
    "reload_dirs",
    multiple=True,
    help="Set reload directories explicitly, instead of using the current working directory.",
    type=click.Path(exists=True),
)
@click.option(
    "--reload-include",
    "reload_includes",
    multiple=True,
    help="Set glob patterns to include while watching for files. Includes '*.py' "
    "by default; these defaults can be overridden with `--reload-exclude`. "
    "This option has no effect unless watchfiles is installed.",
)
@click.option(
    "--reload-exclude",
    "reload_excludes",
    multiple=True,
    help="Set glob patterns to exclude while watching for files. Includes "
    "'.*, .py[cod], .sw.*, ~*' by default; these defaults can be overridden "
    "with `--reload-include`. This option has no effect unless watchfiles is "
    "installed.",
)
@click.option(
    "--reload-delay",
    type=float,
    default=0.25,
    show_default=True,
    help="Delay between previous and next check if application needs to be. Defaults to 0.25s.",
)
@click.option(
    "--workers",
    default=None,
    type=int,
    help="Number of worker processes. Defaults to the $WEB_CONCURRENCY environment"
    " variable if available, or 1. Not valid with --reload.",
)
@click.option(
    "--loop",
    type=str,
    metavar="[auto|asyncio|uvloop|zuvloop]",
    default="auto",
    help="Event loop factory implementation.",
    show_default=True,
)
@click.option(
    "--http",
    type=str,
    metavar="[auto|h11|httptools|zttp]",
    default="auto",
    help="HTTP protocol implementation.",
    show_default=True,
)
@click.option(
    "--http2",
    is_flag=True,
    default=False,
    help="Enable HTTP/2 support. Requires --http zttp.",
    show_default=True,
)
@click.option(
    "--ws",
    type=str,
    metavar="[auto|websockets|websockets-sansio|wsproto]",
    default="auto",
    help="WebSocket protocol implementation.",
    show_default=True,
)
@click.option("--ws-max-size", type=int, default=16777216, help="WebSocket max size message in bytes", show_default=True)
@click.option(
    "--ws-max-queue",
    type=int,
    default=32,
    help="The maximum length of the WebSocket message queue.",
    show_default=True,
)
@click.option(
    "--ws-ping-interval",
    type=float,
    default=20.0,
    help="WebSocket ping interval in seconds.",
    show_default=True,
)
@click.option(
    "--ws-ping-timeout",
    type=float,
    default=20.0,
    help="WebSocket ping timeout in seconds.",
    show_default=True,
)
@click.option(
    "--ws-per-message-deflate",
    type=bool,
    default=True,
    help="WebSocket per-message-deflate compression",
    show_default=True,
)
@click.option("--lifespan", type=LIFESPAN_CHOICES, default="auto", help="Lifespan implementation.", show_default=True)
@click.option(
    "--interface",
    type=INTERFACE_CHOICES,
    default="auto",
    help="Select ASGI3, ASGI2, or WSGI as the application interface.",
    show_default=True,
)
@click.option("--env-file", type=click.Path(exists=True), default=None, help="Environment configuration file.", show_default=True)
@click.option(
    "--log-config",
    type=click.Path(exists=True),
    default=None,
    help="Logging configuration file. Supported formats: .ini, .json, .yaml.",
    show_default=True,
)
@click.option(
    "--log-level",
    type=LEVEL_CHOICES,
    default=None,
    help="Log level. [default: info]",
    show_default=True,
)
@click.option("--access-log/--no-access-log", is_flag=True, default=True, help="Enable/Disable access log.")
@click.option("--use-colors/--no-use-colors", is_flag=True, default=None, help="Enable/Disable colorized logging.")
@click.option(
    "--proxy-headers/--no-proxy-headers",
    is_flag=True,
    default=True,
    help="Enable/Disable X-Forwarded-Proto, X-Forwarded-For to populate url scheme and remote address info.",
)
@click.option("--server-header/--no-server-header", is_flag=True, default=True, help="Enable/Disable default Server header.")
@click.option("--date-header/--no-date-header", is_flag=True, default=True, help="Enable/Disable default Date header.")
@click.option(
    "--forwarded-allow-ips",
    type=str,
    default=None,
    help="Comma separated list of IP Addresses, IP Networks, or literals "
    "(e.g. UNIX Socket path) to trust with proxy headers. Defaults to the "
    "$FORWARDED_ALLOW_IPS environment variable if available, or '127.0.0.1,::1'. "
    "The literal '*' means trust everything.",
)
@click.option("--root-path", type=str, default="", help="Set the ASGI 'root_path' for applications submounted below a given URL path.")
@click.option(
    "--limit-concurrency",
    type=int,
    default=None,
    help="Maximum number of concurrent connections or tasks to allow, before issuing HTTP 503 responses.",
)
@click.option("--backlog", type=int, default=2048, help="Maximum number of connections to hold in backlog")
@click.option(
    "--limit-max-requests",
    type=int,
    default=None,
    help="Maximum number of requests to service before terminating the process.",
)
@click.option(
    "--limit-max-requests-jitter",
    type=int,
    default=0,
    help="Maximum jitter to add to limit_max_requests."
    " Staggers worker restarts to avoid all workers restarting simultaneously.",
    show_default=True,
)
@click.option(
    "--timeout-keep-alive",
    type=int,
    default=5,
    help="Close Keep-Alive connections if no new data is received within this timeout (in seconds).",
    show_default=True,
)
@click.option("--timeout-graceful-shutdown", type=int, default=None, help="Maximum number of seconds to wait for graceful shutdown.")
@click.option(
    "--timeout-worker-healthcheck",
    type=int,
    default=5,
    help="Maximum number of seconds to wait for a worker to respond to a healthcheck.",
    show_default=True,
)
@click.option("--ssl-keyfile", type=str, default=None, help="SSL key file", show_default=True)
@click.option("--ssl-certfile", type=str, default=None, help="SSL certificate file", show_default=True)
@click.option("--ssl-keyfile-password", type=str, default=None, help="SSL keyfile password", show_default=True)
@click.option(
    "--ssl-version",
    type=int,
    default=int(ssl.PROTOCOL_TLS_SERVER),
    help="SSL version to use (see stdlib ssl module's)",
    show_default=True,
)
@click.option(
    "--ssl-cert-reqs",
    type=int,
    default=int(ssl.CERT_NONE),
    help="Whether client certificate is required (see stdlib ssl module's)",
    show_default=True,
)
@click.option("--ssl-ca-certs", type=str, default=None, help="CA certificates file", show_default=True)
@click.option(
    "--ssl-ciphers",
    type=str,
    default=None,
    help="Ciphers to use (see stdlib ssl module's). Defaults to OpenSSL's safe defaults.",
    show_default=True,
)
@click.option("--header", "headers", multiple=True, help="Specify custom default HTTP response headers as a Name:Value pair")
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Display the uvicorn version and exit.",
)
@click.option(
    "--app-dir",
    default="",
    show_default=True,
    help="Look for APP in the specified directory, by adding this to the PYTHONPATH."
    " Defaults to the current working directory.",
)
@click.option(
    "--h11-max-incomplete-event-size",
    "h11_max_incomplete_event_size",
    type=int,
    default=None,
    help="For h11, the maximum number of bytes to buffer of an incomplete event.",
)
@click.option(
    "--reset-contextvars",
    is_flag=True,
    default=False,
    help="Run each ASGI request in a fresh contextvars.Context. Hides context set in the lifespan.",
    show_default=True,
)
@click.option(
    "--factory",
    is_flag=True,
    default=False,
    help="Treat APP as an application factory, i.e. a () -> <ASGI app> callable.",
    show_default=True,
)
@click.pass_context
def main(ctx: click.Context, app: str, **options: Any) -> None:
    from uvicorn_rs.cli import main as prototype_main

    supported = {
        "host", "port", "loop", "ssl_certfile", "ssl_keyfile",
        "timeout_graceful_shutdown", "app_dir", "factory", "lifespan", "root_path",
        "env_file",
        "headers", "server_header", "date_header", "interface",
        "ws_max_size", "proxy_headers", "forwarded_allow_ips",
        "limit_concurrency",
    }
    # Uvicorn normalizes workers=0 to 1 and runs workers=1 in the current
    # process. Neither value requires process supervision from the adapter.
    if options["workers"] in (0, 1):
        supported.add("workers")
    # Uvicorn consults this timeout only in its multi-process supervisor. It
    # has no effect when the CLI runs the single-process server.
    if options["workers"] in (None, 0, 1):
        supported.add("timeout_worker_healthcheck")
    # Explicit auto selection is equivalent to the Rust server's default
    # HTTP/1.1 and WebSocket implementations.
    # The Rust engine has one native HTTP implementation. Uvicorn's explicit
    # httptools selection is compatible with that path just like auto; h11
    # remains unsupported until its observable parser behavior is covered.
    if options["http"] in {"auto", "httptools"}:
        supported.add("http")
    if options["ws"] == "auto":
        supported.add("ws")
    unsupported = [
        parameter.name
        for parameter in ctx.command.params
        if parameter.name not in supported | {"app", "version"}
        and ctx.get_parameter_source(parameter.name) is not click.core.ParameterSource.DEFAULT
    ]
    if unsupported:
        raise click.ClickException(
            "these Uvicorn settings are not implemented by uvicorn-rs yet: "
            + ", ".join(unsupported)
        )
    if options["interface"] not in {"auto", "asgi2", "asgi3"}:
        raise click.ClickException(
            "uvicorn-rs currently supports only the ASGI 2 and ASGI 3 application interfaces"
        )

    loop = options["loop"]
    if loop == "auto":
        try:
            import uvloop  # noqa: F401
        except ImportError:
            loop = "asyncio"
        else:
            loop = "uvloop"
    argv = [app, "--host", options["host"], "--port", str(options["port"]), "--loop", loop]
    if options["lifespan"] != "auto":
        argv.extend(("--lifespan", options["lifespan"]))
    if options["ssl_certfile"]:
        argv.extend(("--certfile", options["ssl_certfile"]))
    if options["ssl_keyfile"]:
        argv.extend(("--keyfile", options["ssl_keyfile"]))
    if options["app_dir"]:
        argv.extend(("--app-dir", options["app_dir"]))
    if options["factory"]:
        argv.append("--factory")
    if options["env_file"]:
        argv.extend(("--env-file", options["env_file"]))
    if options["root_path"]:
        argv.extend(("--root-path", options["root_path"]))
    for header in options["headers"]:
        argv.extend(("--header", header))
    if not options["server_header"]:
        argv.append("--no-server-header")
    if not options["date_header"]:
        argv.append("--no-date-header")
    if not options["proxy_headers"]:
        argv.append("--no-proxy-headers")
    if options["forwarded_allow_ips"] is not None:
        argv.extend(("--forwarded-allow-ips", options["forwarded_allow_ips"]))
    if options["interface"] != "auto":
        argv.extend(("--interface", options["interface"]))
    if options["ws_max_size"] != 16 * 1024 * 1024:
        argv.extend(("--ws-max-size", str(options["ws_max_size"])))
    graceful_timeout = options["timeout_graceful_shutdown"]
    if graceful_timeout is not None:
        argv.extend(("--graceful-timeout", str(graceful_timeout)))
    if options["limit_concurrency"] is not None:
        argv.extend(("--limit-concurrency", str(options["limit_concurrency"])))
    prototype_main(argv, prog="uvicorn")


def run(
    app: ASGIApplication | Callable[..., Any] | str,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    uds: str | None = None,
    fd: int | None = None,
    loop: LoopFactoryType | str = "auto",
    http: type[asyncio.Protocol] | HTTPProtocolType | str = "auto",
    http2: bool = False,
    ws: type[asyncio.Protocol] | WSProtocolType | str = "auto",
    ws_max_size: int = 16 * 1024 * 1024,
    ws_max_queue: int = 32,
    ws_ping_interval: float | None = 20.0,
    ws_ping_timeout: float | None = 20.0,
    ws_per_message_deflate: bool = True,
    lifespan: LifespanType = "auto",
    interface: InterfaceType = "auto",
    reload: bool = False,
    reload_dirs: list[str] | str | None = None,
    reload_includes: list[str] | str | None = None,
    reload_excludes: list[str] | str | None = None,
    reload_delay: float = 0.25,
    workers: int | None = None,
    env_file: str | os.PathLike[str] | None = None,
    log_config: dict[str, Any] | str | os.PathLike[str] | RawConfigParser | IO[Any] | None = LOGGING_CONFIG,
    log_level: str | int | None = None,
    access_log: bool = True,
    proxy_headers: bool = True,
    server_header: bool = True,
    date_header: bool = True,
    forwarded_allow_ips: list[str] | str | None = None,
    root_path: str = "",
    limit_concurrency: int | None = None,
    backlog: int = 2048,
    limit_max_requests: int | None = None,
    limit_max_requests_jitter: int = 0,
    timeout_keep_alive: int = 5,
    timeout_graceful_shutdown: int | None = None,
    timeout_worker_healthcheck: int = 5,
    ssl_keyfile: str | os.PathLike[str] | None = None,
    ssl_certfile: str | os.PathLike[str] | None = None,
    ssl_keyfile_password: str | None = None,
    ssl_version: int = ssl.PROTOCOL_TLS_SERVER,
    ssl_cert_reqs: int = ssl.CERT_NONE,
    ssl_ca_certs: str | os.PathLike[str] | None = None,
    ssl_ciphers: str | None = None,
    ssl_context_factory: Callable[[Config, Callable[[], ssl.SSLContext]], ssl.SSLContext] | None = None,
    headers: list[tuple[str, str]] | None = None,
    use_colors: bool | None = None,
    app_dir: str | None = None,
    factory: bool = False,
    h11_max_incomplete_event_size: int | None = None,
    reset_contextvars: bool = False,
) -> None:
    """Run the Rust server using the Uvicorn 0.54.0 ``run`` call shape."""
    if app_dir is not None:
        sys.path.insert(0, app_dir)

    from .config import Config
    from .server import Server

    config = Config(
        app,
        host=host,
        port=port,
        uds=uds,
        fd=fd,
        loop=loop,
        http=http,
        http2=http2,
        ws=ws,
        ws_max_size=ws_max_size,
        ws_max_queue=ws_max_queue,
        ws_ping_interval=ws_ping_interval,
        ws_ping_timeout=ws_ping_timeout,
        ws_per_message_deflate=ws_per_message_deflate,
        lifespan=lifespan,
        interface=interface,
        reload=reload,
        reload_dirs=reload_dirs,
        reload_includes=reload_includes,
        reload_excludes=reload_excludes,
        reload_delay=reload_delay,
        workers=workers,
        env_file=env_file,
        log_config=log_config,
        log_level=log_level,
        access_log=access_log,
        proxy_headers=proxy_headers,
        server_header=server_header,
        date_header=date_header,
        forwarded_allow_ips=forwarded_allow_ips,
        root_path=root_path,
        limit_concurrency=limit_concurrency,
        backlog=backlog,
        limit_max_requests=limit_max_requests,
        limit_max_requests_jitter=limit_max_requests_jitter,
        timeout_keep_alive=timeout_keep_alive,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        timeout_worker_healthcheck=timeout_worker_healthcheck,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        ssl_keyfile_password=ssl_keyfile_password,
        ssl_version=ssl_version,
        ssl_cert_reqs=ssl_cert_reqs,
        ssl_ca_certs=ssl_ca_certs,
        ssl_ciphers=ssl_ciphers,
        ssl_context_factory=ssl_context_factory,
        headers=headers or [],
        use_colors=use_colors,
        factory=factory,
        h11_max_incomplete_event_size=h11_max_incomplete_event_size,
        reset_contextvars=reset_contextvars,
    )
    try:
        Server(config).run()
    except KeyboardInterrupt:
        pass
