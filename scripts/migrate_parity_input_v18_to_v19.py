#!/usr/bin/env python3
"""Migrate maintained parity inputs from schema @18 to @19.

Schema @19 allows the Python API HTTP-run stimulus to invoke ``Config`` and
``Server.run()`` directly, in addition to ``uvicorn.run`` and the module CLI.
This migration changes only each input document's root schema marker.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = ROOT / "tests" / "parity" / "inputs"
SCHEMA_V18 = "uvicorn-rs-parity/input@18"
SCHEMA_V19 = "uvicorn-rs-parity/input@19"


def migrate(path: Path) -> bool:
    """Migrate one input document; return whether its bytes changed."""
    raw = path.read_bytes()
    document = json.loads(raw)
    if type(document) is not dict or set(document) != {"schema", "cases"}:
        raise ValueError(f"{path}: input document must contain exactly schema and cases")
    if type(document["cases"]) is not list:
        raise ValueError(f"{path}: cases must be an array")
    if document["schema"] == SCHEMA_V19:
        return False
    if document["schema"] != SCHEMA_V18:
        raise ValueError(f"{path}: expected {SCHEMA_V18!r} or {SCHEMA_V19!r}")

    old_marker = f'"schema": "{SCHEMA_V18}"'.encode("utf-8")
    new_marker = f'"schema": "{SCHEMA_V19}"'.encode("utf-8")
    if raw.count(old_marker) != 1:
        raise ValueError(f"{path}: could not locate one root schema marker")
    path.write_bytes(raw.replace(old_marker, new_marker, 1))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="input JSON files or directories (defaults to tests/parity/inputs)",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    for path in args.paths or [DEFAULT_INPUTS]:
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
        else:
            paths.append(path)
    if not paths:
        parser.error("no parity input documents found")

    try:
        for path in paths:
            changed = migrate(path)
            print(f"{'MIGRATED' if changed else 'UNCHANGED'} {path}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
