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

HYPERCORN_H3_SLOW_READER_LINUX_X86_64 = {
    "policy_id": "hypercorn-0.18.0-h3-slow-reader-linux-x86-64-stream-keyerror",
    "category": "http3",
    "workload": "slow-reader-backpressure",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Linux",
    "machine": "x86_64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "Hypercorn 0.18.0 asyncio raised KeyError(52) for an HTTP/3 stream ID "
        "absent from its stream map during slow-reader backpressure. The client "
        "completed 28 requests before two requests timed out waiting for response "
        "headers; the retained log does not establish event ordering or causal "
        "direction. On the same source, uvicorn-rs asyncio passed five "
        "candidate-only repetitions of 40 requests each with zero failures and "
        "clean shutdown. Keep this exact reference cell candidate-only; no "
        "matched speed comparison is available."
    ),
}

HYPERCORN_H3_SLOW_READER_LINUX_X86_64_UVLOOP = {
    "policy_id": "hypercorn-0.18.0-h3-slow-reader-linux-x86-64-uvloop-stream-keyerror",
    "category": "http3",
    "workload": "slow-reader-backpressure",
    "reference": "hypercorn-uvloop",
    "candidate": "uvicorn-rs-uvloop",
    "platform_system": "Linux",
    "machine": "x86_64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "On Linux x86-64, Hypercorn 0.18.0 uvloop raised KeyError(72) in "
        "its HTTP/3 stream-map lookup during slow-reader backpressure. The "
        "client completed 38 requests and received 39,845,888 response bytes "
        "before two requests timed out waiting for response headers. The "
        "retained traceback confirms the missing stream lookup but does not "
        "establish event ordering or causal direction. The category stopped "
        "before uvicorn-rs uvloop ran, so the exact candidate cell must still "
        "pass every candidate-only repetition with correct responses and clean "
        "shutdown; no matched speed comparison is available."
    ),
}

HYPERCORN_H3_FIXED_LINUX_X86_64_UVLOOP = {
    "policy_id": "hypercorn-0.18.0-h3-fixed-linux-x86-64-uvloop-header-timeout",
    "category": "http3",
    "workload": "fixed",
    "reference": "hypercorn-uvloop",
    "candidate": "uvicorn-rs-uvloop",
    "platform_system": "Linux",
    "machine": "x86_64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "In the exact-main benchmark run, Hypercorn 0.18.0 uvloop failed the "
        "fixed FastAPI reference workload on Linux x86-64: the client attempted "
        "4,792 requests and recorded one timeout waiting for HTTP/3 response "
        "headers. The retained reference output has no server traceback, so the "
        "cause is unconfirmed. Keep only this exact reference cell candidate-only; "
        "uvicorn-rs uvloop must still pass all five repetitions with correct "
        "responses and graceful shutdown. Do not emit a matched speed ratio."
    ),
}

HYPERCORN_H3_LARGE_RESPONSE_MACOS_ARM64 = {
    "policy_id": "hypercorn-0.18.0-h3-large-response-macos-arm64-stream-keyerror",
    "category": "http3",
    "workload": "large-response",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Darwin",
    "machine": "arm64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "On macOS ARM64, Hypercorn 0.18.0 asyncio raised KeyError(400) while "
        "serving a 1 MiB HTTP/3 large response. The client received 189,714 "
        "of 1,048,576 declared bytes before the QUIC UDP task failed. The "
        "retained log confirms the missing stream-map lookup and truncated "
        "body, but does not establish event ordering. Keep the uvicorn-rs "
        "asyncio candidate as a full correctness- and lifecycle-checked "
        "candidate-only cell; no matched speedup is available for this pair."
    ),
}

HYPERCORN_H3_LARGE_RESPONSE_LINUX_X86_64 = {
    "policy_id": "hypercorn-0.18.0-h3-large-response-linux-x86-64-stream-keyerror",
    "category": "http3",
    "workload": "large-response",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Linux",
    "machine": "x86_64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "On Linux x86-64, Hypercorn 0.18.0 asyncio raised KeyError(96) while "
        "looking up an HTTP/3 stream during a 1 MiB large response. The client "
        "received 997,497 of 1,048,576 declared bytes before the reference "
        "failed. The retained trace confirms the missing stream-map lookup and "
        "truncated response, but does not establish event ordering. On the same "
        "source, uvicorn-rs asyncio passed five candidate-only repetitions with "
        "zero failures and clean shutdown. Keep this exact reference cell "
        "candidate-only; no matched speed comparison is available."
    ),
}

HYPERCORN_H3_LARGE_RESPONSE_LINUX_AARCH64 = {
    "policy_id": "hypercorn-0.18.0-h3-large-response-linux-aarch64-header-timeout",
    "category": "http3",
    "workload": "large-response",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Linux",
    "machine": "aarch64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "In the exact-main benchmark run, Hypercorn 0.18.0 asyncio failed the "
        "1 MiB large-response reference workload on Linux ARM64 at repetition 2. "
        "The client recorded one timeout waiting for HTTP/3 response headers "
        "while reporting 10 MiB of response data. The retained reference output "
        "does not establish the cause. Keep only this exact reference cell "
        "candidate-only; uvicorn-rs asyncio must still pass all five repetitions "
        "with correct responses and graceful shutdown. Do not emit a matched "
        "speed ratio."
    ),
}

HYPERCORN_H3_FIXED_LINUX_X86_64 = {
    "policy_id": "hypercorn-0.18.0-h3-fixed-linux-x86-64-stream-keyerror",
    "category": "http3",
    "workload": "fixed",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Linux",
    "machine": "x86_64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "Hypercorn 0.18.0 asyncio raised KeyError(19072) while indexing its "
        "HTTP/3 stream map during the fixed FastAPI workload. The client "
        "completed 4,769 requests before one request timed out waiting for "
        "response headers. The retained server trace confirms the missing "
        "stream-map lookup but does not establish event ordering or root cause. "
        "On the same source, uvicorn-rs asyncio passed all five repetitions "
        "with zero failures, valid timing, and clean shutdown. Keep this exact "
        "reference cell candidate-only; no matched speed comparison is "
        "available."
    ),
}

HYPERCORN_H3_FIXED_LINUX_AARCH64 = {
    "policy_id": "hypercorn-0.18.0-h3-fixed-linux-aarch64-stream-keyerror",
    "category": "http3",
    "workload": "fixed",
    "reference": "hypercorn-asyncio",
    "candidate": "uvicorn-rs-asyncio",
    "platform_system": "Linux",
    "machine": "aarch64",
    "hypercorn_version": "0.18.0",
    "reason": (
        "On Linux ARM64, Hypercorn 0.18.0 asyncio raised KeyError(17172) "
        "while indexing its HTTP/3 stream map during the fixed FastAPI "
        "workload. The client reported 4,294 requests and one timeout "
        "waiting for response headers. The retained server traceback "
        "confirms the missing stream-map lookup, but does not establish "
        "event ordering or root cause. In the same exact-source run, "
        "uvicorn-rs asyncio and uvloop each passed repetitions 1-3 with "
        "zero failures, valid timing, and graceful shutdown; repetitions "
        "4-5 were not reached. Keep this exact reference cell candidate-only "
        "and emit no matched speed ratio for it. A complete qualifying run "
        "must still collect every candidate repetition."
    ),
}

HYPERCORN_H3_REFERENCE_EXCEPTIONS = (
    HYPERCORN_H3_SLOW_READER_LINUX_AARCH64,
    HYPERCORN_H3_SLOW_READER_LINUX_X86_64,
    HYPERCORN_H3_SLOW_READER_LINUX_X86_64_UVLOOP,
    HYPERCORN_H3_FIXED_LINUX_X86_64_UVLOOP,
    HYPERCORN_H3_LARGE_RESPONSE_MACOS_ARM64,
    HYPERCORN_H3_LARGE_RESPONSE_LINUX_X86_64,
    HYPERCORN_H3_LARGE_RESPONSE_LINUX_AARCH64,
    HYPERCORN_H3_FIXED_LINUX_X86_64,
    HYPERCORN_H3_FIXED_LINUX_AARCH64,
)


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
    """Return only confirmed exceptions matching this exact run context."""
    if not enabled:
        return []
    return [
        dict(policy)
        for policy in HYPERCORN_H3_REFERENCE_EXCEPTIONS
        if category == policy["category"]
        and policy["workload"] in workloads
        and policy["reference"] in servers
        and policy["candidate"] in servers
        and platform_system == policy["platform_system"]
        and machine == policy["machine"]
        and hypercorn_version == policy["hypercorn_version"]
    ]


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
    if category != "http3":
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
