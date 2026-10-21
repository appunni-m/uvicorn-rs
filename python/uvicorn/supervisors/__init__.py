# Copyright (c) 2026 Appunni M
# Part of the Uvicorn-compatible Python process supervisor.
# SPDX-License-Identifier: BSD-3-Clause

"""Process supervision used by the Uvicorn-compatible entry points."""

from .multiprocess import Multiprocess

__all__ = ["Multiprocess"]
