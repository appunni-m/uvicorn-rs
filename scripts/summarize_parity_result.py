#!/usr/bin/env python3
"""Emit concise GitHub annotations for a black-box parity result."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def escape_command_value(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: summarize_parity_result.py RESULT.json", file=sys.stderr)
        return 2

    result_path = Path(sys.argv[1])
    if not result_path.is_file():
        print(
            "::error title=ASGI parity::No structured result was written; "
            "inspect the retained parity log artifact."
        )
        return 0

    result = json.loads(result_path.read_text(encoding="utf-8"))
    summary = result.get("summary", {})
    print(
        "::notice title=ASGI parity::"
        f"{summary.get('passed', 0)}/{summary.get('selected', 0)} cases passed; "
        f"failed={summary.get('failed', 0)}, "
        f"infrastructure_failed={summary.get('infrastructure_failed', 0)}, "
        f"not_run={summary.get('not_run', 0)}"
    )

    for case in result.get("cases", []):
        if case.get("status") != "passed":
            profile = escape_command_value(str(case.get("profile", "unknown profile")))
            case_id = escape_command_value(str(case.get("case_id", "unknown case")))
            status = escape_command_value(str(case.get("status", "unknown status")))
            print(
                f"::error title=ASGI parity {profile}::"
                f"{case_id} status={status}; see retained parity log artifact."
            )

    for error in result.get("infrastructure_errors", []):
        profile = escape_command_value(str(error.get("profile") or "unknown profile"))
        server = escape_command_value(str(error.get("server") or "unknown server"))
        kind = escape_command_value(str(error.get("kind", "unknown error")))
        print(
            f"::error title=ASGI parity infrastructure {profile}::"
            f"{kind} server={server}; see retained parity log artifact."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
