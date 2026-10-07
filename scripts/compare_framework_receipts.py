"""Require the same integration observations across both isolated frameworks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load_receipt(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema") != "uvicorn-rs-starlette-integration@1"
        or value.get("status") != "passed"
    ):
        raise ValueError(f"not a passed framework integration receipt: {path}")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starlette", type=Path, required=True)
    parser.add_argument("--starlette-rs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    upstream = load_receipt(args.starlette.resolve())
    rust_framework = load_receipt(args.starlette_rs.resolve())
    upstream_identity = upstream["identity"]
    rust_identity = rust_framework["identity"]

    if (
        upstream["app"] != rust_framework["app"]
        or upstream["same_app_for_both_servers"] is not True
    ):
        raise ValueError("framework comparisons did not use the same shared ASGI app")
    if (
        upstream_identity["integration_app_sha256"]
        != rust_identity["integration_app_sha256"]
    ):
        raise ValueError("framework receipts identify different app source files")
    if upstream_identity["probe_sha256"] != rust_identity["probe_sha256"]:
        raise ValueError("framework receipts identify different probe source files")
    for field in (
        "python",
        "uvicorn_version",
        "uvicorn_rs_version",
        "server_wheel_sha256",
        "uvicorn_rs_native_sha256",
    ):
        if upstream_identity[field] != rust_identity[field]:
            raise ValueError(f"framework receipts have different {field}")
    if upstream_identity["framework_distribution"] != "starlette":
        raise ValueError("first receipt is not the upstream Starlette distribution")
    if rust_identity["framework_distribution"] != "starlette-rs-py":
        raise ValueError("second receipt is not the starlette-rs-py distribution")
    if (
        upstream_identity["uvicorn_rs_runtime_requirements"]
        or rust_identity["uvicorn_rs_runtime_requirements"]
    ):
        raise ValueError("uvicorn-rs has unexpected framework runtime requirements")
    if upstream_identity["uvicorn_rs_bundle_has_framework"] is not False:
        raise ValueError("upstream receipt reports a bundled framework")
    if rust_identity["uvicorn_rs_bundle_has_framework"] is not False:
        raise ValueError("starlette-rs receipt reports a bundled framework")

    upstream_observations = upstream["servers"]["uvicorn"]["observations"]
    candidate_observations = upstream["servers"]["uvicorn-rs"]["observations"]
    rust_upstream_observations = rust_framework["servers"]["uvicorn"]["observations"]
    rust_candidate_observations = rust_framework["servers"]["uvicorn-rs"][
        "observations"
    ]
    if upstream_observations != candidate_observations:
        raise ValueError(
            "upstream Starlette Uvicorn and uvicorn-rs observations differ"
        )
    if rust_upstream_observations != rust_candidate_observations:
        raise ValueError("starlette-rs Uvicorn and uvicorn-rs observations differ")
    if upstream_observations != rust_upstream_observations:
        raise ValueError("Uvicorn observations differ between the two frameworks")
    if candidate_observations != rust_candidate_observations:
        raise ValueError("uvicorn-rs observations differ between the two frameworks")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "uvicorn-rs-framework-matrix-comparison@1",
        "status": "passed",
        "app": upstream["app"],
        "app_sha256": upstream_identity["integration_app_sha256"],
        "probe_sha256": upstream_identity["probe_sha256"],
        "server_wheel_sha256": upstream_identity["server_wheel_sha256"],
        "uvicorn_version": upstream_identity["uvicorn_version"],
        "uvicorn_rs_version": upstream_identity["uvicorn_rs_version"],
        "frameworks": {
            "starlette": upstream_identity["framework_version"],
            "starlette-rs-py": rust_identity["framework_version"],
        },
        "matched_observation_categories": sorted(upstream_observations),
        "match_count": len(upstream_observations),
        "receipts": {
            "starlette_sha256": hashlib.sha256(
                args.starlette.resolve().read_bytes()
            ).hexdigest(),
            "starlette_rs_sha256": hashlib.sha256(
                args.starlette_rs.resolve().read_bytes()
            ).hexdigest(),
        },
        "scope_note": (
            "Selected shared-app integration parity; the starlette-rs WebSocket case uses a plain "
            "ASGI scope handler because this framework revision does not expose WebSocketRoute."
        ),
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "passed", "receipt": str(args.output)}))


if __name__ == "__main__":
    main()
