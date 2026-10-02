"""Raises an identifiable Python exception to exercise bridge error handling."""


async def app(scope, receive, send):
    raise RuntimeError("bridge exception sentinel")
