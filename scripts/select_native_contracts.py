#!/usr/bin/env python3
"""Select normal native inputs while retaining their complete manifest identity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def select(manifest: Path, output: Path, receipt: Path) -> dict:
    """Validate case lanes and write an input-only normal selection and receipt."""
    if len({path.resolve() for path in (manifest, output, receipt)}) != 3:
        raise ValueError("manifest, output and receipt must be different files")
    source_bytes = manifest.read_bytes()
    document = json.loads(source_bytes)
    if not isinstance(document, dict):
        raise ValueError("native manifest must be an object")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("native case index must be a nonempty list")
    lanes: dict[str, list[dict]] = {"target-contract": [], "fault-contract": []}
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("native case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError("native case IDs must be nonempty unique strings")
        ids.add(case_id)
        mode = case.get("verification", "target-contract")
        if not isinstance(mode, str) or mode not in lanes:
            raise ValueError(f"unknown native verification mode: {mode}")
        fault = case.get("fault")
        if mode == "target-contract" and fault is not None:
            raise ValueError("normal native case declares a coverage fault")
        if mode == "fault-contract" and (
            not isinstance(fault, dict)
            or not isinstance(fault.get("point"), str)
            or not fault["point"]
        ):
            raise ValueError("native fault case must declare a fault point")
        lanes[mode].append(case)
    if not lanes["target-contract"]:
        raise ValueError("normal native lane must contain at least one case")
    selected_bytes = (
        json.dumps({**document, "cases": lanes["target-contract"]}, indent=2) + "\n"
    ).encode()
    selection = {
        "schema": "uvicorn-rs-native-lane-selection@1",
        "lane": "normal",
        "source": {"path": str(manifest), "sha256": hashlib.sha256(source_bytes).hexdigest()},
        "output": {"path": str(output), "sha256": hashlib.sha256(selected_bytes).hexdigest()},
        "manifest_count": len(cases),
        "selected_ids": [case["id"] for case in lanes["target-contract"]],
        "coverage_only_ids": [case["id"] for case in lanes["fault-contract"]],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(selected_bytes)
    receipt.write_text(json.dumps(selection, indent=2) + "\n")
    return selection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("tests/native-core/manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("target/native-contracts/normal-inputs.json"))
    parser.add_argument("--receipt", type=Path, default=Path("target/native-contracts/normal-selection.json"))
    args = parser.parse_args()
    try:
        selection = select(args.manifest, args.output, args.receipt)
    except (OSError, ValueError) as error:
        parser.exit(1, f"native lane selection failed: {error}\n")
    print(
        f"Native normal lane: {len(selection['selected_ids'])}/{selection['manifest_count']} inputs; "
        f"{len(selection['coverage_only_ids'])} coverage-only inputs remain in unified coverage"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
