"""Strict parsing helpers for identifiers in benchmark evidence."""

from __future__ import annotations

import re


def positive_integer_identity(value: object) -> int | None:
    """Return a positive integer encoded as an int or canonical decimal string.

    Earlier benchmark aggregates wrote GitHub's numeric run identifiers as
    strings. Accept those unambiguous values while rejecting booleans, floats,
    zero, negative values, and non-canonical decimal encodings.
    """
    if type(value) is int:
        return value if value > 0 else None
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    return None
