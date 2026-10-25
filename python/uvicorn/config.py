# Copyright (c) 2026 Appunni M
# Public constructor shape follows Uvicorn 0.54.0.
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Uvicorn-compatible configuration facade for the Rust server engine."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import logging.config
import os
import socket
import ssl
import sys
from configparser import RawConfigParser
from pathlib import Path
from typing import Any, Awaitable, Callable, IO, Literal

from uvicorn._ansi import style
from uvicorn._types import ASGIApplication
from uvicorn.importer import ImportFromStringError, import_from_string


HTTPProtocolType = Literal["auto", "h11", "httptools", "zttp"]
WSProtocolType = Literal[
    "auto", "none", "websockets", "websockets-sansio", "wsproto"
]
LifespanType = Literal["auto", "on", "off"]
LoopFactoryType = Literal["none", "auto", "asyncio", "uvloop", "zuvloop"]
InterfaceType = Literal["auto", "asgi3", "asgi2", "wsgi"]

SSL_PROTOCOL_VERSION: int = ssl.PROTOCOL_TLS_SERVER


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}

LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "trace": 5,
}

STARTUP_FAILURE = 3


def is_dir(path: Path) -> bool:
    """Return whether a reload pattern resolves to an existing directory."""
    try:
        if not path.is_absolute():
            path = path.resolve()
        return path.is_dir()
    except OSError:
        return False


def resolve_reload_patterns(
    patterns_list: list[str], directories_list: list[str]
) -> tuple[list[str], list[Path]]:
    """Resolve reload patterns into stable file patterns and watch roots."""
    directories = list(set(map(Path, directories_list.copy())))
    patterns = patterns_list.copy()
    current_working_directory = Path.cwd()
    for pattern in patterns_list:
        if pattern == ".*":
            continue
        patterns.append(pattern)
        if is_dir(Path(pattern)):
            directories.append(Path(pattern))
        else:
            for match in current_working_directory.glob(pattern):
                if is_dir(match):
                    directories.append(match)

    directories = list(set(map(Path, directories)))
    directories = [path.resolve() for path in directories if is_dir(path)]
    children = []
    for index, directory in enumerate(directories):
        for other in directories[index + 1 :]:
            if directory in other.parents:
                children.append(other)
            elif other in directory.parents:
                children.append(directory)
    directories = list(set(directories).difference(children))
    return list(set(patterns)), directories


def _normalize_dirs(dirs: list[str] | str | None) -> list[str]:
    if dirs is None:
        return []
    if isinstance(dirs, str):
        return [dirs]
    return list(set(dirs))


def _validate_http2_backend(http: object, enabled: bool) -> None:
    """Match Uvicorn's HTTP/2 backend requirement before loading the app."""
    if enabled and http != "zttp":
        raise ValueError(
            "HTTP/2 requires the `zttp` HTTP protocol. Install it with `pip install zttp`, "
            "then select it with `http='zttp'`. See "
            "https://uvicorn.dev/concepts/http2/ for more information."
        )


class _ASGI2Adapter:
    """Adapt the two-call ASGI interface to the ASGI3 app shape Rust serves."""

    def __init__(self, app: Callable[..., Any]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        await self.app(scope)(receive, send)


def _configure_asgi_interface(
    app: Any, interface: str, lifespan: str
) -> tuple[Any, str]:
    """Select the Uvicorn interface and adapt Python callables for Rust."""
    if interface == "auto":
        if inspect.isclass(app):
            use_asgi3 = hasattr(app, "__await__")
        elif inspect.isfunction(app):
            use_asgi3 = inspect.iscoroutinefunction(app)
        else:
            call = getattr(app, "__call__", None)
            use_asgi3 = inspect.iscoroutinefunction(call)
        interface = "asgi3" if use_asgi3 else "asgi2"
    if interface == "asgi2":
        return _ASGI2Adapter(app), interface
    if interface == "asgi3":
        return app, interface
    if interface == "wsgi":
        from uvicorn.middleware.wsgi import WSGILifespanAdapter, WSGIMiddleware

        return WSGILifespanAdapter(WSGIMiddleware(app), lifespan), interface
    raise NotImplementedError(
        f"uvicorn-rs does not support interface={interface!r}"
    )


class Config:
    """Store Uvicorn-shaped options and resolve an application for Rust serving.

    The constructor accepts the Uvicorn 0.54.0 public settings. The current
    native runtime implements the single-process ASGI 3 TCP and Unix-domain
    socket paths; unsupported
    settings are rejected by :meth:`_validate_native_runtime` before binding.
    """

    def __init__(
        self,
        app: ASGIApplication | Callable[..., Any] | str,
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
        env_file: str | os.PathLike[str] | None = None,
        log_config: dict[str, Any] | str | os.PathLike[str] | RawConfigParser | IO[Any] | None = LOGGING_CONFIG,
        log_level: str | int | None = None,
        access_log: bool = True,
        use_colors: bool | None = None,
        interface: InterfaceType = "auto",
        reload: bool = False,
        reload_dirs: list[str] | str | None = None,
        reload_delay: float = 0.25,
        reload_includes: list[str] | str | None = None,
        reload_excludes: list[str] | str | None = None,
        workers: int | None = None,
        proxy_headers: bool = True,
        server_header: bool = True,
        date_header: bool = True,
        forwarded_allow_ips: list[str] | str | None = None,
        root_path: str = "",
        limit_concurrency: int | None = None,
        limit_max_requests: int | None = None,
        limit_max_requests_jitter: int = 0,
        backlog: int = 2048,
        timeout_keep_alive: int = 5,
        timeout_notify: int = 30,
        timeout_graceful_shutdown: int | None = None,
        timeout_worker_healthcheck: int = 5,
        callback_notify: Callable[..., Awaitable[None]] | None = None,
        ssl_keyfile: str | os.PathLike[str] | None = None,
        ssl_certfile: str | os.PathLike[str] | None = None,
        ssl_keyfile_password: str | None = None,
        ssl_version: int = SSL_PROTOCOL_VERSION,
        ssl_cert_reqs: int = ssl.CERT_NONE,
        ssl_ca_certs: str | os.PathLike[str] | None = None,
        ssl_ciphers: str | None = None,
        ssl_context_factory: Callable[[Config, Callable[[], ssl.SSLContext]], ssl.SSLContext] | None = None,
        headers: list[tuple[str, str]] | None = None,
        factory: bool = False,
        h11_max_incomplete_event_size: int | None = None,
        reset_contextvars: bool = False,
    ) -> None:
        values = locals().copy()
        values.pop("self")
        for name, value in values.items():
            setattr(self, name, value)

        self.configure_logging()

        if env_file is not None:
            from dotenv import load_dotenv

            logging.getLogger("uvicorn.error").info(
                "Loading environment from '%s'", env_file
            )
            load_dotenv(dotenv_path=env_file)

        if forwarded_allow_ips is None:
            self.forwarded_allow_ips = os.environ.get(
                "FORWARDED_ALLOW_IPS", "127.0.0.1,::1"
            )

        self.workers = workers or 1
        if workers is None and "WEB_CONCURRENCY" in os.environ:
            self.workers = int(os.environ["WEB_CONCURRENCY"])
        self._worker_mode = False
        self.loaded = False
        self.loaded_app: Any = None
        self.loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None

        self.reload_dirs: list[Path] = []
        self.reload_dirs_excludes: list[Path] = []
        self.reload_includes: list[str] = []
        self.reload_excludes: list[str] = []
        logger = logging.getLogger("uvicorn.error")
        if (reload_dirs or reload_includes or reload_excludes) and not self.should_reload:
            logger.warning(
                "Current configuration will not reload as not all conditions are met, "
                "please refer to documentation."
            )
        if self.should_reload:
            normalized_dirs = _normalize_dirs(reload_dirs)
            normalized_includes = _normalize_dirs(reload_includes)
            normalized_excludes = _normalize_dirs(reload_excludes)
            self.reload_includes, self.reload_dirs = resolve_reload_patterns(
                normalized_includes, normalized_dirs
            )
            self.reload_excludes, self.reload_dirs_excludes = resolve_reload_patterns(
                normalized_excludes, []
            )

            configured_dirs = self.reload_dirs.copy()
            for excluded_dir in self.reload_dirs_excludes:
                for reload_dir in configured_dirs:
                    if excluded_dir == reload_dir or excluded_dir in reload_dir.parents:
                        try:
                            self.reload_dirs.remove(reload_dir)
                        except ValueError:
                            pass

            for pattern in self.reload_excludes:
                if pattern in self.reload_includes:
                    self.reload_includes.remove(pattern)

            if not self.reload_dirs:
                if normalized_dirs:
                    logger.warning(
                        "Provided reload directories %s did not contain valid "
                        "directories, watching current working directory.",
                        normalized_dirs,
                    )
                self.reload_dirs = [Path.cwd()]

            logger.info(
                "Will watch for changes in these directories: %s",
                sorted(map(str, self.reload_dirs)),
            )

        if self.reload and self.workers > 1:
            logger.warning('"workers" flag is ignored when reloading is enabled.')

    def configure_logging(self) -> None:
        """Apply Uvicorn's logging configuration and access-log settings."""
        logging.addLevelName(5, "TRACE")

        if self.log_config is not None:
            if isinstance(self.log_config, os.PathLike):
                self.log_config = os.fspath(self.log_config)

            if isinstance(self.log_config, dict):
                if self.use_colors in (True, False):
                    self.log_config["formatters"]["default"]["use_colors"] = self.use_colors
                    self.log_config["formatters"]["access"]["use_colors"] = self.use_colors
                logging.config.dictConfig(self.log_config)
            elif isinstance(self.log_config, str) and self.log_config.endswith(".json"):
                with open(self.log_config, encoding="utf-8") as file:
                    logging.config.dictConfig(json.load(file))
            elif isinstance(self.log_config, str) and self.log_config.endswith((".yaml", ".yml")):
                try:
                    import yaml
                except ImportError as error:
                    raise ImportError(
                        "Install the PyYAML package or uvicorn[standard] to use "
                        "`--log-config` with YAML files."
                    ) from error
                with open(self.log_config, encoding="utf-8") as file:
                    logging.config.dictConfig(yaml.safe_load(file))
            else:
                logging.config.fileConfig(self.log_config, disable_existing_loggers=False)

        if self.log_level is not None:
            log_level = (
                LOG_LEVELS[self.log_level.lower()]
                if isinstance(self.log_level, str)
                else self.log_level
            )
            logging.getLogger("uvicorn.error").setLevel(log_level)
            logging.getLogger("uvicorn.access").setLevel(log_level)
            logging.getLogger("uvicorn.asgi").setLevel(log_level)
        if self.access_log is False:
            access_logger = logging.getLogger("uvicorn.access")
            access_logger.handlers = []
            access_logger.propagate = False

    def bind_socket(self) -> socket.socket:
        """Bind the listener once in the parent before spawning workers."""
        logger = logging.getLogger("uvicorn.error")
        if self.uds is not None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(self.uds)
                os.chmod(self.uds, 0o666)
            except OSError as error:
                logger.error(error)
                raise SystemExit(STARTUP_FAILURE)
            message = "Uvicorn running on unix socket %s (Press CTRL+C to quit)"
            logger_args: tuple[Any, ...] = (self.uds,)
            color_message = (
                "Uvicorn running on "
                + style("%s", bold=True)
                + " (Press CTRL+C to quit)"
            )
        elif self.fd is not None:
            sock = socket.socket(fileno=os.dup(self.fd))
            message = "Uvicorn running on socket %s (Press CTRL+C to quit)"
            logger_args = (sock.getsockname(),)
            color_message = (
                "Uvicorn running on "
                + style("%s", bold=True)
                + " (Press CTRL+C to quit)"
            )
        else:
            family = socket.AF_INET6 if self.host and ":" in self.host else socket.AF_INET
            sock = socket.socket(family=family)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((self.host, self.port))
            except OSError as error:
                logger.error(error)
                raise SystemExit(STARTUP_FAILURE)
            if family == socket.AF_INET6:
                address_format = "%s://[%s]:%d"
            else:
                address_format = "%s://%s:%d"
            message = (
                f"Uvicorn running on {address_format} (Press CTRL+C to quit)"
            )
            color_message = (
                "Uvicorn running on "
                + style(address_format, bold=True)
                + " (Press CTRL+C to quit)"
            )
            protocol = "https" if self.ssl_certfile else "http"
            logger_args = (protocol, self.host, sock.getsockname()[1])
        logger.info(message, *logger_args, extra={"color_message": color_message})
        sock.set_inheritable(True)
        return sock

    def get_loop_factory(self) -> Callable[[], asyncio.AbstractEventLoop] | None:
        """Return the event-loop factory selected by ``loop``."""
        if self.loop == "none":
            # Uvicorn's ``none`` selector leaves asyncio's default factory in
            # control. ``asyncio.Runner(loop_factory=None)`` has that behavior.
            return None
        if self.loop in {"auto", "uvloop"}:
            try:
                import uvloop
            except ImportError:
                if self.loop == "uvloop":
                    raise
                return self._asyncio_loop_factory()
            return uvloop.new_event_loop
        if self.loop == "asyncio":
            return self._asyncio_loop_factory()
        if self.loop == "zuvloop":
            import zuvloop

            return zuvloop.new_event_loop
        try:
            return import_from_string(self.loop)
        except ImportFromStringError as exc:
            logging.getLogger("uvicorn.error").error(
                "Error loading custom loop setup function. %s" % exc
            )
            raise SystemExit(STARTUP_FAILURE) from exc

    def _asyncio_loop_factory(self):
        if sys.platform == "win32" and not self.use_subprocess:
            return asyncio.ProactorEventLoop
        return asyncio.SelectorEventLoop

    def setup_event_loop(self) -> None:
        """Keep Uvicorn's retired method diagnostic for API compatibility."""
        raise AttributeError(
            "The `setup_event_loop` method was replaced by `get_loop_factory` in uvicorn 0.36.0.\n"
            "None of those methods are supposed to be used directly. If you are doing it, please let me know here: "
            "https://github.com/Kludex/uvicorn/discussions/2706. Thank you, and sorry for the inconvenience."
        )

    def load_app(self) -> Any:
        """Import an application target, exiting with Uvicorn's load status."""
        try:
            return import_from_string(self.app)
        except ImportFromStringError as exc:
            logging.getLogger("uvicorn.error").error(
                "Error loading ASGI app. %s" % exc
            )
            raise SystemExit(3) from exc

    def load(self) -> None:
        """Resolve the import target and optional no-argument app factory."""
        if self.loaded:
            raise AssertionError("Config is already loaded")
        self._validate_native_runtime()
        _validate_http2_backend(self.http, self.http2)
        self.loaded_app = self.load_app()
        try:
            self.loaded_app = self.loaded_app()
        except TypeError as exc:
            if self.factory:
                logging.getLogger("uvicorn.error").error(
                    "Error loading ASGI app factory: %s", exc
                )
                raise SystemExit(3) from exc
        else:
            if not self.factory:
                logging.getLogger("uvicorn.error").warning(
                    "ASGI app factory detected. Using it, but please consider "
                    "setting the --factory flag explicitly."
                )
        self.loaded_app, self.interface = _configure_asgi_interface(
            self.loaded_app, self.interface, self.lifespan
        )
        if self.proxy_headers:
            from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

            self.loaded_app = ProxyHeadersMiddleware(
                self.loaded_app, trusted_hosts=self.forwarded_allow_ips
            )
        encoded_headers = [
            (name.lower().encode("latin1"), value.encode("latin1"))
            for name, value in (self.headers or [])
        ]
        self.encoded_headers = (
            [(b"server", b"uvicorn")] + encoded_headers
            if b"server" not in dict(encoded_headers) and self.server_header
            else encoded_headers
        )
        self.loaded = True

    def _validate_native_runtime(self) -> None:
        """Reject settings whose semantics are not implemented by this runtime."""
        unsupported = []
        supported_ssl_versions = {ssl.PROTOCOL_TLS, ssl.PROTOCOL_TLS_SERVER}
        tls12_protocol = getattr(ssl, "PROTOCOL_TLSv1_2", None)
        if tls12_protocol is not None:
            supported_ssl_versions.add(tls12_protocol)
        # Uvicorn treats unknown HTTP and WebSocket selector strings as import
        # paths. Resolve those before rejecting custom implementations so an
        # invalid selector keeps the pinned CLI/API import diagnostic.
        if isinstance(self.http, str) and self.http not in {
            "auto",
            "h11",
            "httptools",
            "zttp",
        }:
            import_from_string(self.http)
        if isinstance(self.ws, str) and self.ws not in {
            "auto",
            "none",
            "websockets",
            "websockets-sansio",
            "wsproto",
        }:
            import_from_string(self.ws)
        # These Uvicorn selectors route to the Rust engine's native WebSocket
        # implementation. Only the legacy websockets selector applies its
        # configured receive queue; the other backends do not consume it.
        checks = (
            (self.uds is not None and os.name == "nt", "uds"),
            (self.fd is not None and os.name == "nt", "fd"),
            # Uvicorn runs workers=0 and workers=1 in the current process.
            # WEB_CONCURRENCY=0 reaches Config without the explicit-value
            # normalization and is still a single-process configuration.
            (self.workers not in (0, 1) and not self.should_reload, "workers"),
            (self.http not in {"auto", "h11", "httptools", "zttp"}, "http"),
            (
                self.ws
                not in {"auto", "none", "websockets", "websockets-sansio", "wsproto"},
                "ws",
            ),
            (self.lifespan not in {"auto", "on", "off"}, "lifespan"),
            (self.interface not in {"auto", "asgi2", "asgi3", "wsgi"}, "interface"),
            (
                self.log_level is not None
                and not (
                    isinstance(self.log_level, str)
                    and self.log_level.lower() in LOG_LEVELS
                    or isinstance(self.log_level, int)
                ),
                "log_level",
            ),
            (self.ssl_context_factory is not None, "ssl_context_factory"),
            (self.ssl_version not in supported_ssl_versions, "ssl_version"),
        )
        if (
            self.http == "h11"
            and self.h11_max_incomplete_event_size is not None
            and self.h11_max_incomplete_event_size < 8 * 1024
        ):
            raise ValueError(
                "h11_max_incomplete_event_size must be at least 8192 bytes "
                "for the native HTTP/1 parser"
            )
        unsupported.extend(name for enabled, name in checks if enabled)
        if unsupported:
            names = ", ".join(unsupported)
            raise NotImplementedError(
                f"uvicorn-rs does not implement these Uvicorn Config settings yet: {names}"
            )

    @property
    def _native_tls_version(self) -> str:
        """Map supported Python SSL protocol selectors to Rustls versions."""
        if self.ssl_version == getattr(ssl, "PROTOCOL_TLSv1_2", None):
            return "tls12"
        return "default"

    @property
    def _native_tls_cipher_suites(self) -> list[int] | None:
        """Resolve Uvicorn's cipher expression to TLS 1.2 suite identifiers."""
        if self.ssl_certfile is None or self.ssl_ciphers is None:
            return None

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.set_ciphers(self.ssl_ciphers)
        return list(
            dict.fromkeys(
                cipher["id"] & 0xFFFF
                for cipher in context.get_ciphers()
                if cipher["protocol"] != "TLSv1.3"
            )
        )

    @property
    def asgi_version(self) -> Literal["2.0", "3.0"]:
        """Return the ASGI version associated with the selected interface."""
        mapping: dict[str, Literal["2.0", "3.0"]] = {
            "asgi2": "2.0",
            "asgi3": "3.0",
            "wsgi": "3.0",
        }
        return mapping[self.interface]

    @property
    def is_ssl(self) -> bool:
        """Whether the configuration enables TLS through any supported input."""
        return bool(self.ssl_keyfile or self.ssl_certfile or self.ssl_context_factory)

    @property
    def should_reload(self) -> bool:
        """Whether an import-string app is supervised by the reload process."""
        return isinstance(self.app, str) and self.reload

    @property
    def use_subprocess(self) -> bool:
        """Whether this configuration starts a reload or worker subprocess."""
        return bool(self.reload or self.workers > 1)
