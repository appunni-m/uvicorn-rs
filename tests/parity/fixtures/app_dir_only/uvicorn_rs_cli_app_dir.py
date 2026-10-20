"""Minimal import fixture for the Uvicorn CLI ``--app-dir`` parity case."""

import os

present = True


def factory_type_error():
    raise TypeError("factory sentinel")


def factory_env_file_error():
    value = os.environ.get("UVICORN_RS_PARITY_FACTORY_SENTINEL", "missing")
    raise TypeError(f"factory env sentinel: {value}")
