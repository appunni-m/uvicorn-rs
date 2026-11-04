"""Uvicorn import namespace provided by the ``uvicorn-rs`` distribution.

``__version__`` identifies the pinned Uvicorn compatibility baseline. The
installable distribution has its own version in package metadata.
"""

__version__ = "0.54.0"

from .config import Config
from .main import main, run
from .server import Server

__all__ = ["main", "run", "Config", "Server"]
