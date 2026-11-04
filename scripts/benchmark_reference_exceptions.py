"""Narrow, source-auditable exceptions for confirmed benchmark references."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

HYPERCORN_H3_SLOW_READER_LINUX_AARCH64 = {
    "policy_id": "hypercorn-0.18.0-h3-slow-reader-linux-aarch64-stream-keyerror",
    "category": "http3",
    "workload": "slow-reader-backpressure",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Linux",
    "machine": "aarch64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "Hypercorn 0.18.0 asyncio raised KeyError for a stream ID absent from "
        "its HTTP/3 stream map during slow-reader backpressure, and two probe "
        "requests timed out waiting for response headers. The retained log "
        "does not establish event ordering or causal direction. Keep "
        "uvicorn-rs asyncio as a correctness and lifecycle checked "
        "candidate-only cell."
    ),
}


def installed_hypercorn_version() -> str | None:
    try:
        return version("hypercorn")
    except PackageNotFoundError:
        return None


def active_reference_exclusions(
    category: str,
    workloads: list[str],
    *,
    servers: list[str],
    platform_system: str | None,
    machine: str | None,
    hypercorn_version: str | None,
    enabled: bool = True,
) -> list[dict]:
    """Return only the confirmed exception matching this exact run context."""
    policy = HYPERCORN_H3_SLOW_READER_LINUX_AARCH64
    if (
        enabled
        and category == policy["category"]
        and policy["workload"] in workloads
        and policy["reference"] in servers
        and policy["candidate"] in servers
        and platform_system == policy["platform_system"]
        and machine == policy["machine"]
        and hypercorn_version == policy["hypercorn_version"]
    ):
        return [dict(policy)]
    return []


def exclusions_by_workload(records: list[dict]) -> dict[str, dict[str, str]]:
    """Map each excluded reference cell to its stable policy ID and reason."""
    result: dict[str, dict[str, str]] = {}
    for record in records:
        result.setdefault(record["workload"], {})[record["reference"]] = (
            f"{record['policy_id']}: {record['reason']}"
        )
    return result


def reference_exclusion_metadata_errors(category: str, metadata: dict) -> list[str]:
    """Reject unrecognized, missing, or context-mismatched reference skips."""
    if category != HYPERCORN_H3_SLOW_READER_LINUX_AARCH64["category"]:
        if metadata.get("reference_exclusions", []) or metadata.get("excluded_servers_by_workload", {}):
            return ["reference_exclusions_are_not_allowed_for_this_category"]
        return []

    workloads = metadata.get("workloads")
    if not isinstance(workloads, list) or not all(isinstance(name, str) for name in workloads):
        return ["reference_exclusion_workload_inventory_missing_or_malformed"]

    servers = metadata.get("servers")
    if not isinstance(servers, dict) or not all(isinstance(name, str) for name in servers):
        return ["reference_exclusion_server_inventory_missing_or_malformed"]

    expected = active_reference_exclusions(
        category,
        workloads,
        servers=list(servers),
        platform_system=metadata.get("platform_system"),
        machine=metadata.get("machine"),
        hypercorn_version=metadata.get("hypercorn"),
    )
    actual = metadata.get("reference_exclusions", [])
    actual_by_workload = metadata.get("excluded_servers_by_workload", {})
    expected_by_workload = exclusions_by_workload(expected)
    errors = []
    if actual != expected:
        errors.append("reference_exclusion_receipt_unrecognized_or_context_mismatched")
    if actual_by_workload != expected_by_workload:
        errors.append("reference_exclusion_server_map_unrecognized_or_context_mismatched")
    return errors
