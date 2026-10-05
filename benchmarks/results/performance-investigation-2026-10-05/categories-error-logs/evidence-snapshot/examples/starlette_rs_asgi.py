"""Optional integration example for the independent starlette-rs package."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def homepage(request):
    return PlainTextResponse("starlette-rs ASGI app")


app = Starlette(routes=[Route("/", homepage)])
