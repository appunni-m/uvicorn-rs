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
import ssl
import sys
from configparser import RawConfigParser
from typing import Any, Awaitable, Callable, IO


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


def _configure_asgi_interface(app: Any, interface: str) -> tuple[Any, str]:
    """Select Uvicorn's ASGI2/ASGI3 call shape and adapt ASGI2 for Rust."""
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
    raise NotImplementedError(
        f"uvicorn-rs does not support interface={interface!r}"
    )


class Config:
    """Store Uvicorn-shaped options and resolve an application for Rust serving.

    The constructor accepts the Uvicorn 0.54.0 public settings. The current
    native runtime implements the single-process ASGI 3 TCP path; unsupported
    settings are rejected by :meth:`validate_native_runtime` before binding.
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
        ssl_version: int = ssl.PROTOCOL_TLS_SERVER,
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

        if env_file is not None:
            from dotenv import load_dotenv

            print(f"INFO:     Loading environment from '{env_file}'", file=sys.stderr)
            load_dotenv(dotenv_path=env_file)

        if forwarded_allow_ips is None:
            self.forwarded_allow_ips = os.environ.get(
                "FORWARDED_ALLOW_IPS", "127.0.0.1,::1"
            )

        self.workers = workers or 1
        if workers is None and "WEB_CONCURRENCY" in os.environ:
            self.workers = int(os.environ["WEB_CONCURRENCY"])
        self.loaded = False
        self.loaded_app: Any = None
        self.loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None
        self.configure_logging()

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

    def get_loop_factory(self):
        """Return the event-loop factory selected by ``loop``."""
        if self.loop in {"auto", "uvloop"}:
            try:
                import uvloop
            except ImportError:
                if self.loop == "uvloop":
                    raise
                return None
            return uvloop.new_event_loop
        if self.loop == "asyncio":
            return asyncio.new_event_loop
        raise NotImplementedError(f"uvicorn-rs does not support loop={self.loop!r}")

    def load_app(self):
        """Import an application target, exiting with Uvicorn's load status."""
        if not isinstance(self.app, str):
            return self.app
        from uvicorn_rs.cli import ImportFromStringError, _load_app

        try:
            return _load_app(self.app)
        except ImportFromStringError as exc:
            print(f"ERROR:    Error loading ASGI app. {exc}", file=sys.stderr)
            raise SystemExit(3) from exc

    def load(self) -> None:
        """Resolve the import target and optional no-argument app factory."""
        if self.loaded:
            raise AssertionError("Config is already loaded")
        _validate_http2_backend(self.http, self.http2)
        self.loaded_app = self.load_app()
        try:
            self.loaded_app = self.loaded_app()
        except TypeError as exc:
            if self.factory:
                print(f"ERROR:    Error loading ASGI app factory: {exc}", file=sys.stderr)
                raise SystemExit(3) from exc
        else:
            if not self.factory:
                print(
                    "WARNING:  ASGI app factory detected. Using it, but please consider setting the --factory flag explicitly.",
                    file=sys.stderr,
                )
        self.loaded_app, self.interface = _configure_asgi_interface(
            self.loaded_app, self.interface
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

    def validate_native_runtime(self) -> None:
        """Reject settings whose semantics are not implemented by this runtime."""
        unsupported = []
        checks = (
            (self.uds is not None, "uds"),
            (self.fd is not None, "fd"),
            (self.reload, "reload"),
            (self.workers != 1, "workers"),
            (self.loop not in {"auto", "asyncio", "uvloop"}, "loop"),
            (self.http not in {"auto", "httptools"}, "http"),
            (self.ws != "auto", "ws"),
            (self.ws_max_queue != 32, "ws_max_queue"),
            (self.ws_ping_interval != 20.0, "ws_ping_interval"),
            (self.ws_ping_timeout != 20.0, "ws_ping_timeout"),
            (self.ws_per_message_deflate is not True, "ws_per_message_deflate"),
            (self.lifespan not in {"auto", "on", "off"}, "lifespan"),
            (self.interface not in {"auto", "asgi2", "asgi3"}, "interface"),
            (
                self.log_config is not None and self.log_config != LOGGING_CONFIG,
                "log_config",
            ),
            (self.log_level not in (None, "error", 40), "log_level"),
            (self.use_colors is not None, "use_colors"),
            (self.limit_max_requests is not None, "limit_max_requests"),
            (self.limit_max_requests_jitter != 0, "limit_max_requests_jitter"),
            (self.backlog != 2048, "backlog"),
            (self.timeout_keep_alive != 5, "timeout_keep_alive"),
            (self.timeout_notify != 30, "timeout_notify"),
            (self.timeout_worker_healthcheck != 5, "timeout_worker_healthcheck"),
            (self.callback_notify is not None, "callback_notify"),
            (self.ssl_context_factory is not None, "ssl_context_factory"),
            (self.ssl_keyfile_password is not None, "ssl_keyfile_password"),
            (self.ssl_ca_certs is not None, "ssl_ca_certs"),
            (self.ssl_ciphers is not None, "ssl_ciphers"),
            (self.ssl_version != ssl.PROTOCOL_TLS_SERVER, "ssl_version"),
            (self.ssl_cert_reqs != ssl.CERT_NONE, "ssl_cert_reqs"),
            (self.h11_max_incomplete_event_size is not None, "h11_max_incomplete_event_size"),
            (self.reset_contextvars, "reset_contextvars"),
        )
        unsupported.extend(name for enabled, name in checks if enabled)
        if unsupported:
            names = ", ".join(unsupported)
            raise NotImplementedError(
                f"uvicorn-rs does not implement these Uvicorn Config settings yet: {names}"
            )
