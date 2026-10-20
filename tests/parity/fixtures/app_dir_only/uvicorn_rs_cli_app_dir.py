"""Minimal import fixture for the Uvicorn CLI ``--app-dir`` parity case."""

present = True


def factory_type_error():
    raise TypeError("factory sentinel")
