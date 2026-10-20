# Copyright (c) 2026 Appunni M
# Copyright © 2017-present, Encode OSS Ltd and contributors.
# SPDX-License-Identifier: BSD-3-Clause

"""Apply trusted X-Forwarded-For and X-Forwarded-Proto headers to ASGI scopes."""

from __future__ import annotations

import functools
import ipaddress
from collections.abc import Awaitable, Callable
from typing import Any


ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]],
    Awaitable[None],
]


class ProxyHeadersMiddleware:
    """Honor forwarding headers only when the connecting host is trusted."""

    def __init__(
        self, app: ASGIApp, trusted_hosts: list[str] | str = "127.0.0.1"
    ) -> None:
        self.app = app
        self.trusted_hosts = _TrustedHosts(trusted_hosts)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[Any]],
        send: Callable[..., Awaitable[Any]],
    ) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)

        client_addr = scope.get("client")
        client_host = client_addr[0] if client_addr else None
        if client_host in self.trusted_hosts:
            forwarded_proto: bytes | None = None
            forwarded_for: list[bytes] = []
            for name, value in scope["headers"]:
                if name == b"x-forwarded-proto":
                    forwarded_proto = value
                elif name == b"x-forwarded-for":
                    forwarded_for.append(value)

            if forwarded_proto is not None:
                scheme = forwarded_proto.decode("latin1").strip()
                if scheme in {"http", "https", "ws", "wss"}:
                    scope["scheme"] = (
                        scheme.replace("http", "ws")
                        if scope["type"] == "websocket"
                        else scheme
                    )

            if forwarded_for:
                forwarded = b", ".join(forwarded_for).decode("latin1")
                host, port = self.trusted_hosts.get_trusted_client_address(forwarded)
                if host:
                    scope["client"] = (host, port)

        return await self.app(scope, receive, send)


def _parse_raw_hosts(value: str) -> list[str]:
    return [item.strip() for item in value.split(",")]


def _parse_host_port(value: str) -> tuple[str, int]:
    """Parse an IPv4/hostname port suffix or a bracketed IPv6 port suffix."""
    if value.startswith("["):
        bracket_end = value.find("]")
        if bracket_end == -1:
            return value, 0
        host = value[1:bracket_end]
        remainder = value[bracket_end + 1 :]
        if not remainder:
            return host, 0
        if not remainder.startswith(":"):
            return value, 0
        try:
            return host, int(remainder[1:])
        except ValueError:
            return host, 0

    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        try:
            return host, int(port)
        except ValueError:
            return value, 0
    return value, 0


class _TrustedHosts:
    """Match trusted IP addresses, networks, and literal transport hosts."""

    def __init__(self, trusted_hosts: list[str] | str) -> None:
        self.always_trust = trusted_hosts in ("*", ["*"])
        self.trusted_literals: set[str] = set()
        self.trusted_hosts: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        self.trusted_networks: set[
            ipaddress.IPv4Network | ipaddress.IPv6Network
        ] = set()

        if not self.always_trust:
            hosts = (
                _parse_raw_hosts(trusted_hosts)
                if isinstance(trusted_hosts, str)
                else trusted_hosts
            )
            for host in hosts:
                if "/" in host:
                    try:
                        self.trusted_networks.add(ipaddress.ip_network(host))
                    except ValueError:
                        self.trusted_literals.add(host)
                else:
                    try:
                        self.trusted_hosts.add(ipaddress.ip_address(host))
                    except ValueError:
                        self.trusted_literals.add(host)

        self._trusts = functools.lru_cache(maxsize=4096)(self._compute_trust)

    def __contains__(self, host: str | None) -> bool:
        if self.always_trust:
            return True
        if not host:
            return False
        if len(host) > 253:
            return self._compute_trust(host)
        return self._trusts(host)

    def _compute_trust(self, host: str) -> bool:
        try:
            address = ipaddress.ip_address(host)
            return address in self.trusted_hosts or any(
                address in network for network in self.trusted_networks
            )
        except ValueError:
            return host in self.trusted_literals

    def get_trusted_client_address(self, forwarded_for: str) -> tuple[str, int]:
        """Select the first untrusted address from the proxy chain."""
        hosts = _parse_raw_hosts(forwarded_for)
        if self.always_trust:
            return _parse_host_port(hosts[0])
        for host_port in reversed(hosts):
            host, port = _parse_host_port(host_port)
            if host not in self:
                return host, port
        return _parse_host_port(hosts[0])
