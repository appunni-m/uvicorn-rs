"""Uvicorn import namespace provided by the uvicorn-rs-py distribution.

This package is a compatibility facade over the Rust-native server. Its
version identifies the installed uvicorn-rs-py distribution; it does not claim
full compatibility with an upstream Uvicorn release.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("uvicorn-rs-py")
except PackageNotFoundError:  # pragma: no cover - source-tree fallback
    __version__ = "0.1.0"

__all__ = ["__version__"]
