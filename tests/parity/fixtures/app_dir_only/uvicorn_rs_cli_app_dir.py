"""Minimal import fixture for the Uvicorn CLI ``--app-dir`` parity case."""

import os

present = True


def factory_type_error():
    raise TypeError("factory sentinel")


def factory_env_file_error():
    value = os.environ.get("UVICORN_RS_PARITY_FACTORY_SENTINEL", "missing")
    raise TypeError(f"factory env sentinel: {value}")


def factory_dotenv_syntax_error():
    source = os.environ.get("UVICORN_RS_PARITY_DOTENV_SOURCE", "missing")
    expanded = os.environ.get("UVICORN_RS_PARITY_DOTENV_EXPANSION", "missing")
    raise TypeError(f"factory dotenv values: {source}; {expanded}")
