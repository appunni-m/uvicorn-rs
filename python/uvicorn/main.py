"""Command-line adapter exposed as ``uvicorn``.

The adapter currently supports the prototype option set. The Uvicorn 0.54.0
CLI contract remains tracked by the public compatibility matrix.
"""

from uvicorn_rs.cli import main as _main


def main() -> None:
    """Run the uvicorn-rs-py command through the ``uvicorn`` entry point."""
    _main(prog="uvicorn")
