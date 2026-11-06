"""Exact candidate-only acceptance for macOS ARM64 Uvicorn WSS timeouts.

The raw parity rows remain infrastructure failures. This module validates at
most one precise Uvicorn 0.54.0 reference timeout and the candidate's
independent result; it does not infer a root cause or turn a reference failure
into a parity pass.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import unquote, urlsplit


POLICY_ID = "uvicorn-0.54.0-macos-arm64-wss-handshake-timeout-candidate-clean@2"
CASE_ID = "websocket-tls.text-round-trip-with-query-and-subprotocol"
SCOPE_CASE_ID = "websocket-tls.scope-headers-path-query-and-subprotocols"
MACOS_REFERENCE_CASE_IDS = frozenset({CASE_ID, SCOPE_CASE_ID})
ERROR_PREFIX = (
    "oracle uvicorn adapter failed: timed out while waiting for handshake response; "
    "diagnostic="
)
SCOPE_ERROR_PREFIX = "oracle uvicorn adapter failed: WebSocket client timed out; client_trace="
SCOPE_DIAGNOSTIC_MARKER = "; diagnostic="
EXPECTED_CASE = {
    "case_id": CASE_ID,
    "profile": "websocket-tls",
    "operation": "websocket.message-exchange",
    "covers": ["websocket.message-exchange"],
    "websocket": {
        "path": "/ws?parity=tls",
        "subprotocols": ["parity"],
        "messages": [{"kind": "text", "value": "tls-websocket"}],
    },
}
EXPECTED_SCOPE_CASE = {
    "case_id": SCOPE_CASE_ID,
    "profile": "websocket-tls",
    "operation": "websocket.scope-and-messages",
    "covers": ["websocket.scope-and-messages"],
    "websocket": {
        "path": "/ws-scope-echo/raw%20space-%C3%A9?tag=second&tag=first&plus=a+b&escaped=%2B",
        "subprotocols": ["scope-v1", "parity"],
        "messages": [],
        "headers": [["x-duplicate", "second"], ["x-duplicate", "first"]],
        "expect_close": True,
    },
}
EXPECTED_CANDIDATE_OBSERVATION = {
    "ordered_messages": [{"kind": "text", "value": "tls-websocket"}],
    "subprotocol": "parity",
}
EXPECTED_SCOPE_CANDIDATE_EVENTS = [
    "lifespan.startup",
    "websocket.scope:/ws-scope-echo/raw space-é",
]
EXPECTED_SCOPE_CANDIDATE_OBSERVATION = {
    "close_code": 1000,
    "close_reason": "scope complete",
    "subprotocol": "parity",
}


def _exception_receipt(
    case_id: str,
    candidate_observation: dict[str, Any],
    candidate_events: list[str],
) -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "case_id": case_id,
        "raw_status": "infrastructure_failed",
        "candidate_observation": candidate_observation,
        "reference_events": ["lifespan.startup"],
        "candidate_events": candidate_events,
        "root_cause": "unknown",
        "performance_pair": None,
    }


EXPECTED_EXCEPTION_RECEIPT = _exception_receipt(
    CASE_ID,
    EXPECTED_CANDIDATE_OBSERVATION,
    ["lifespan.startup", "websocket.scope:/ws"],
)
EXPECTED_SCOPE_EXCEPTION_RECEIPT = _exception_receipt(
    SCOPE_CASE_ID,
    EXPECTED_SCOPE_CANDIDATE_OBSERVATION,
    EXPECTED_SCOPE_CANDIDATE_EVENTS,
)
EXPECTED_EXCEPTION_RECEIPTS = (
    EXPECTED_EXCEPTION_RECEIPT,
    EXPECTED_SCOPE_EXCEPTION_RECEIPT,
)
EXPECTED_CASES = {
    CASE_ID: EXPECTED_CASE,
    SCOPE_CASE_ID: EXPECTED_SCOPE_CASE,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"{POLICY_ID}: {message}")


def _eligible_context(case: dict[str, Any], environment: dict[str, Any]) -> str:
    case_id = case.get("case_id") if isinstance(case, dict) else None
    expected_case = EXPECTED_CASES.get(case_id)
    _require(expected_case is not None, "input is not one of the indexed TLS WebSocket cases")
    _require(case == expected_case, "input is not the exact indexed TLS WebSocket case")
    _require(
        isinstance(environment, dict)
        and isinstance(environment.get("platform"), str)
        and environment["platform"].lower().startswith(("macos", "darwin"))
        and environment.get("machine") == "arm64",
        "runtime is not macOS ARM64",
    )
    dependencies = environment.get("dependencies")
    _require(
        isinstance(dependencies, dict)
        and dependencies.get("uvicorn") == "0.54.0"
        and dependencies.get("websockets") == "17.1",
        "reference dependency versions differ from the captured failure",
    )
    return case_id


def _parse_failure_diagnostic(error_message: str, case_id: str) -> dict[str, Any]:
    if case_id == CASE_ID:
        _require(error_message.startswith(ERROR_PREFIX), "failure is not the recorded handshake timeout")
        diagnostic_and_traceback = error_message[len(ERROR_PREFIX):]
    else:
        _require(
            error_message.startswith(SCOPE_ERROR_PREFIX),
            "failure is not the recorded scope WebSocket timeout",
        )
        client_trace_and_diagnostic = error_message[len(SCOPE_ERROR_PREFIX):]
        client_trace, separator, diagnostic_and_traceback = client_trace_and_diagnostic.partition(
            SCOPE_DIAGNOSTIC_MARKER
        )
        _require(bool(separator), "raw WebSocket client trace or diagnostic marker is missing")
        _require(
            "DEBUG > GET " + EXPECTED_SCOPE_CASE["websocket"]["path"] + " HTTP/1.1" in client_trace
            and "DEBUG > Upgrade: websocket" in client_trace
            and "DEBUG > EOF" in client_trace,
            "client trace does not identify the exact indexed WSS request",
        )

    diagnostic_text, separator, traceback_text = diagnostic_and_traceback.partition("\nTraceback ")
    _require(bool(separator), "raw timeout traceback is missing")
    _require(
        "TimeoutError: timed out while waiting for handshake response" in traceback_text,
        "raw traceback does not identify the handshake timeout",
    )
    try:
        diagnostic = json.loads(diagnostic_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{POLICY_ID}: raw diagnostic JSON is invalid") from error
    _require(
        isinstance(diagnostic, dict)
        and set(diagnostic) == {
            "case_id", "profile", "oracle_events", "target_events", "server_log",
            "oracle_process", "target_process", "target_observation", "target_server_log",
        },
        "raw diagnostic fields differ from the recorded failure envelope",
    )
    return diagnostic


def _validate_scope_candidate_observation(observation: Any) -> None:
    _require(isinstance(observation, dict), "candidate observation is malformed")
    _require(
        observation.get("close_code") == EXPECTED_SCOPE_CANDIDATE_OBSERVATION["close_code"]
        and observation.get("close_reason") == EXPECTED_SCOPE_CANDIDATE_OBSERVATION["close_reason"]
        and observation.get("subprotocol") == EXPECTED_SCOPE_CANDIDATE_OBSERVATION["subprotocol"],
        "candidate did not complete the expected WebSocket scope close",
    )
    messages = observation.get("ordered_messages")
    _require(
        isinstance(messages, list)
        and len(messages) == 1
        and isinstance(messages[0], dict)
        and messages[0].get("kind") == "text"
        and isinstance(messages[0].get("value"), str),
        "candidate did not return the expected WebSocket scope observation",
    )
    try:
        scope = json.loads(messages[0]["value"])
    except json.JSONDecodeError as error:
        raise ValueError(f"{POLICY_ID}: candidate scope observation is invalid JSON") from error

    path = EXPECTED_SCOPE_CASE["websocket"]["path"]
    parsed = urlsplit(path)
    expected_path = unquote(parsed.path)
    expected_raw_path = base64.b64encode(parsed.path.encode("ascii")).decode("ascii")
    expected_query = base64.b64encode(parsed.query.encode("ascii")).decode("ascii")
    _require(
        isinstance(scope, dict)
        and scope.get("type") == "websocket"
        and scope.get("asgi_version") == "3.0"
        and scope.get("http_version") == "1.1"
        and scope.get("scheme") == "wss"
        and scope.get("path") == expected_path
        and scope.get("raw_path_base64") == expected_raw_path
        and scope.get("query_string_base64") == expected_query
        and scope.get("subprotocols") == EXPECTED_SCOPE_CASE["websocket"]["subprotocols"]
        and scope.get("state") == {"parity-token": "ready"},
        "candidate did not preserve the indexed WebSocket scope values",
    )
    encoded_headers = scope.get("headers_base64")
    _require(isinstance(encoded_headers, list), "candidate scope headers are missing")
    try:
        headers = [
            (base64.b64decode(pair[0], validate=True).lower(), base64.b64decode(pair[1], validate=True))
            for pair in encoded_headers
            if isinstance(pair, list) and len(pair) == 2
        ]
    except (ValueError, TypeError) as error:
        raise ValueError(f"{POLICY_ID}: candidate scope headers are malformed") from error
    _require(len(headers) == len(encoded_headers), "candidate scope headers are malformed")
    duplicate_headers = [pair for pair in headers if pair[0] == b"x-duplicate"]
    expected_duplicates = [(b"x-duplicate", b"second"), (b"x-duplicate", b"first")]
    _require(duplicate_headers == expected_duplicates, "candidate did not preserve duplicate header order")
    protocol_headers = [value for name, value in headers if name == b"sec-websocket-protocol"]
    _require(
        protocol_headers == [b"scope-v1, parity"],
        "candidate did not preserve the requested WebSocket subprotocols",
    )


def validate_reference_failure(
    error_message: str,
    case: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Validate one precise oracle timeout and return candidate-only evidence."""
    case_id = _eligible_context(case, environment)
    diagnostic = _parse_failure_diagnostic(error_message, case_id)
    _require(
        diagnostic["case_id"] == case_id and diagnostic["profile"] == "websocket-tls",
        "raw diagnostic identifies a different case or profile",
    )
    expected_candidate_events = (
        EXPECTED_SCOPE_CANDIDATE_EVENTS
        if case_id == SCOPE_CASE_ID
        else ["lifespan.startup", "websocket.scope:/ws"]
    )
    _require(
        diagnostic["oracle_events"] == ["lifespan.startup"],
        "reference reached additional ASGI events",
    )
    _require(
        diagnostic["target_events"] == expected_candidate_events,
        "candidate did not reach the expected WebSocket scope",
    )
    for label in ("oracle_process", "target_process"):
        process = diagnostic[label]
        _require(
            isinstance(process, dict)
            and process.get("alive") is True
            and process.get("exit_code") is None
            and process.get("attempted_cases") == [case_id],
            f"{label} was not alive on the exact attempted case",
        )
    target_observation = diagnostic["target_observation"]
    if case_id == CASE_ID:
        _require(
            target_observation == EXPECTED_CANDIDATE_OBSERVATION,
            "candidate did not complete the expected exchange",
        )
    else:
        _validate_scope_candidate_observation(target_observation)
        target_observation = EXPECTED_SCOPE_CANDIDATE_OBSERVATION
    target_log = diagnostic["target_server_log"]
    _require(
        isinstance(target_log, str)
        and "Application startup complete." in target_log
        and "Uvicorn running on https://127.0.0.1:" in target_log
        and not any(marker in target_log for marker in ("Traceback", "ERROR:", "CRITICAL:")),
        "candidate server log does not show clean startup",
    )
    reference_log = diagnostic["server_log"]
    _require(
        isinstance(reference_log, str)
        and "Application startup complete." in reference_log
        and "Uvicorn running on https://127.0.0.1:" in reference_log
        and not any(marker in reference_log for marker in ("Traceback", "ERROR:", "CRITICAL:")),
        "reference server log does not show clean startup before the handshake timeout",
    )
    return _exception_receipt(
        case_id,
        target_observation,
        diagnostic["target_events"],
    )


def validate_reference_row(
    row: dict[str, Any],
    case: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Validate one retained raw infrastructure-failure row."""
    case_id = case.get("case_id") if isinstance(case, dict) else None
    _require(
        isinstance(case_id, str)
        and row.get("case_id") == case_id
        and case_id in MACOS_REFERENCE_CASE_IDS,
             "row identifies a different or ineligible case")
    _require(row.get("status") == "infrastructure_failed", "raw status was rewritten")
    error = row.get("error")
    _require(isinstance(error, dict), "raw error envelope is malformed")
    _require(error.get("class") == "ParityError", "raw error class differs")
    message = error.get("message")
    _require(isinstance(message, str), "raw error message is missing")
    return validate_reference_failure(message, case, environment)


def parity_gate_errors(
    gate: dict[str, Any], *, expected_policy_sha256: str | None = None
) -> list[str]:
    """Validate the compact source-bound parity decision stored in a benchmark run."""
    errors = []
    if not isinstance(gate, dict):
        return ["public_parity_gate_missing_or_malformed"]
    status = gate.get("status")
    raw_status = gate.get("raw_parity_status")
    public_cases = gate.get("public_cases")
    summary = gate.get("raw_parity_summary")
    exceptions = gate.get("accepted_reference_exceptions")
    if type(public_cases) is not int or public_cases <= 0:
        errors.append("public_parity_case_count_missing_or_invalid")
    if not isinstance(summary, dict):
        errors.append("public_parity_raw_summary_missing_or_invalid")
    elif status == "passed":
        expected = {
            "selected": public_cases, "executed": public_cases, "passed": public_cases,
            "failed": 0, "not_run": 0, "infrastructure_failed": 0,
        }
        if raw_status != "completed" or summary != expected or exceptions != []:
            errors.append("passing_public_parity_receipt_is_inconsistent")
    elif status == "accepted_with_reference_exception":
        expected = {
            "selected": public_cases, "executed": public_cases, "passed": public_cases - 1,
            "failed": 0, "not_run": 0, "infrastructure_failed": 1,
        }
        if raw_status != "failed" or summary != expected:
            errors.append("reference_exception_raw_parity_summary_is_inconsistent")
        if (
            not isinstance(exceptions, list)
            or len(exceptions) != 1
            or exceptions[0] not in EXPECTED_EXCEPTION_RECEIPTS
        ):
            errors.append("reference_exception_receipt_is_unrecognized_or_malformed")
        if gate.get("exception_policy_id") != POLICY_ID:
            errors.append("reference_exception_policy_id_is_unrecognized")
        policy_hash = gate.get("exception_policy_sha256")
        if not _valid_sha256(policy_hash):
            errors.append("reference_exception_policy_hash_is_missing_or_invalid")
        elif expected_policy_sha256 is None:
            errors.append("reference_exception_frozen_harness_identity_is_missing")
        elif policy_hash != expected_policy_sha256:
            errors.append("reference_exception_policy_hash_differs_from_frozen_harness")
        if gate.get("performance_pair", "missing") is not None:
            errors.append("reference_exception_must_not_claim_a_performance_pair")
    else:
        errors.append("public_parity_gate_missing_or_failed")
    for field in ("parity_report_sha256", "before_parity_identity_sha256", "native_sha256"):
        if not _valid_sha256(gate.get(field)):
            errors.append(f"public_parity_{field}_missing_or_invalid")
    if not isinstance(gate.get("parity_report"), str) or not gate["parity_report"]:
        errors.append("public_parity_report_path_missing")
    return errors


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
