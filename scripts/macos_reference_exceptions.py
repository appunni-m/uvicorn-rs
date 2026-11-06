"""Exact candidate-only acceptance for the intermittent macOS WSS oracle timeout.

The raw parity row remains infrastructure_failed. This module validates the
one observed Uvicorn 0.54.0 timeout and the candidate's independent response;
it does not infer a root cause or turn the reference failure into a parity pass.
"""

from __future__ import annotations

import json
from typing import Any


POLICY_ID = "uvicorn-0.54.0-macos-arm64-wss-handshake-timeout-candidate-clean@1"
CASE_ID = "websocket-tls.text-round-trip-with-query-and-subprotocol"
ERROR_PREFIX = (
    "oracle uvicorn adapter failed: timed out while waiting for handshake response; "
    "diagnostic="
)
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
EXPECTED_CANDIDATE_OBSERVATION = {
    "ordered_messages": [{"kind": "text", "value": "tls-websocket"}],
    "subprotocol": "parity",
}
EXPECTED_EXCEPTION_RECEIPT = {
    "policy_id": POLICY_ID,
    "case_id": CASE_ID,
    "raw_status": "infrastructure_failed",
    "candidate_observation": EXPECTED_CANDIDATE_OBSERVATION,
    "reference_events": ["lifespan.startup"],
    "candidate_events": ["lifespan.startup", "websocket.scope:/ws"],
    "root_cause": "unknown",
    "performance_pair": None,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"{POLICY_ID}: {message}")


def _eligible_context(case: dict[str, Any], environment: dict[str, Any]) -> None:
    _require(case == EXPECTED_CASE, "input is not the exact indexed TLS WebSocket case")
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


def validate_reference_failure(
    error_message: str,
    case: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Validate the precise oracle timeout and return candidate-only evidence."""
    _eligible_context(case, environment)
    _require(error_message.startswith(ERROR_PREFIX), "failure is not the recorded handshake timeout")
    diagnostic_and_traceback = error_message[len(ERROR_PREFIX):]
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
    _require(diagnostic["case_id"] == CASE_ID and diagnostic["profile"] == "websocket-tls",
             "raw diagnostic identifies a different case or profile")
    _require(diagnostic["oracle_events"] == ["lifespan.startup"],
             "reference reached additional ASGI events")
    _require(diagnostic["target_events"] == ["lifespan.startup", "websocket.scope:/ws"],
             "candidate did not reach the expected WebSocket scope")
    for label in ("oracle_process", "target_process"):
        process = diagnostic[label]
        _require(
            isinstance(process, dict)
            and process.get("alive") is True
            and process.get("exit_code") is None
            and process.get("attempted_cases") == [CASE_ID],
            f"{label} was not alive on the exact attempted case",
        )
    _require(
        diagnostic["target_observation"] == EXPECTED_CANDIDATE_OBSERVATION,
        "candidate did not complete the expected TLS WebSocket exchange",
    )
    target_log = diagnostic["target_server_log"]
    _require(
        isinstance(target_log, str)
        and "Application startup complete." in target_log
        and "Uvicorn running on https://127.0.0.1:" in target_log
        and not any(marker in target_log for marker in ("Traceback", "ERROR:", "CRITICAL:")),
        "candidate server log does not show clean startup",
    )
    _require(isinstance(diagnostic["server_log"], str), "reference server log is malformed")
    return {
        "policy_id": POLICY_ID,
        "case_id": CASE_ID,
        "raw_status": "infrastructure_failed",
        "candidate_observation": diagnostic["target_observation"],
        "reference_events": diagnostic["oracle_events"],
        "candidate_events": diagnostic["target_events"],
        "root_cause": "unknown",
        "performance_pair": None,
    }


def validate_reference_row(
    row: dict[str, Any],
    case: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Validate one retained raw infrastructure-failure row."""
    _require(row.get("case_id") == CASE_ID, "row identifies a different case")
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
        if exceptions != [EXPECTED_EXCEPTION_RECEIPT]:
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
