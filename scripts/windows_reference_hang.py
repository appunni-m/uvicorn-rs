"""Explicit acceptance for recorded stock-Uvicorn worker-shutdown defects.

The raw comparison stays failed. The Windows two-worker console-signal hang
must match its captured log signature, and the candidate must complete its
worker lifecycle cleanly on the same input. When captured stock evidence has
the bounded TCP wakeup, its recovery is also checked.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any


POLICY = "uvicorn-0.54.0-windows-two-worker-sigint-tcp-wakeup@2"
SIGBREAK_POLICY = "uvicorn-0.54.0-windows-two-worker-sigbreak-tcp-wakeup@1"
SIGBREAK_STALL_POLICY = "uvicorn-0.54.0-windows-two-worker-sigbreak-stall-candidate-clean@1"
SIGBREAK_CASE_ID = "python-api.module-cli-two-workers-stop-on-sigterm"
UVICORN_WORKERS_CASE_ID = "python-api.module-cli-two-workers-from-uvicorn-workers-environment"
CASE_IDS = {
    "python-api.module-cli-two-workers-serve-request",
    "python-api.module-cli-web-concurrency-two-workers-serve-request",
    "python-api.module-cli-explicit-workers-overrides-web-concurrency",
    UVICORN_WORKERS_CASE_ID,
    SIGBREAK_CASE_ID,
}


def _eligible_worker_input(
    case: dict[str, Any], case_ids: set[str], shutdown_signal: str
) -> bool:
    request = case.get("api", {}).get("run_http", {})
    environment = request.get("environment", {})
    return (
        case.get("case_id") in case_ids
        and case.get("profile") == "python-api"
        and case.get("operation") == "python.api.run-http"
        and case.get("verification", "oracle-parity") == "oracle-parity"
        and set(request) <= {
            "invocation", "lifespan", "method", "path", "root_path",
            "shutdown_signal", "timeout_seconds", "post_response_settle_seconds",
            "workers", "environment",
        }
        and request.get("invocation") == "module-cli"
        and request.get("lifespan") == "auto"
        and request.get("method") == "GET"
        and request.get("shutdown_signal") == shutdown_signal
        and request.get("root_path") == ""
        and set(environment) <= {"WEB_CONCURRENCY"}
        and (
            request.get("workers") == 2 if "workers" in request
            else environment.get("WEB_CONCURRENCY") == "2"
        )
    )


def eligible_input(case: dict[str, Any]) -> bool:
    if case.get("case_id") == UVICORN_WORKERS_CASE_ID:
        return (
            case.get("profile") == "python-api"
            and case.get("operation") == "python.api.run-http"
            and case.get("verification", "oracle-parity") == "oracle-parity"
            and case.get("api", {}).get("run_http") == {
                "method": "GET",
                "path": "/python-api-two-workers",
                "shutdown_signal": "SIGINT",
                "timeout_seconds": 12,
                "lifespan": "auto",
                "invocation": "module-cli",
                "root_path": "",
                "post_response_settle_seconds": 1,
                "environment": {"UVICORN_WORKERS": "2"},
            }
        )
    if case.get("case_id") == SIGBREAK_CASE_ID:
        return _eligible_worker_input(case, {SIGBREAK_CASE_ID}, "SIGTERM") and (
            case["api"]["run_http"] == {
                "method": "GET", "path": "/python-api-two-workers-sigterm",
                "shutdown_signal": "SIGTERM", "timeout_seconds": 12,
                "lifespan": "auto", "invocation": "module-cli", "root_path": "",
                "post_response_settle_seconds": 1, "workers": 2,
            }
        )
    return _eligible_worker_input(case, CASE_IDS - {SIGBREAK_CASE_ID}, "SIGINT")


def diagnostic_input(case: dict[str, Any]) -> bool:
    """Retain failed observations; acceptance separately checks every signature."""
    return eligible_input(case)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"{POLICY}: {message}")


def _decode(value: str) -> str:
    return base64.b64decode(value, validate=True).decode("utf-8")


def _clean_lifecycle(log: str, *, completed: bool, shutdown_signal: str = "SIGINT") -> None:
    """Count real worker identities, preserving startup and cleanup evidence."""
    starts = re.findall(r"Started server process \[(\d+)\]", log)
    finishes = re.findall(r"Finished server process \[(\d+)\]", log)
    parents = re.findall(r"Started parent process \[(\d+)\]", log)
    _require(len(starts) == len(set(starts)) == 2, "not exactly two original workers")
    _require(len(parents) == 1 and parents[0] not in starts, "missing supervisor identity")
    _require(log.count("Application startup complete.") == 2, "workers did not finish startup")
    _require(not re.search(
        r"Traceback|WinError|ERROR:|CRITICAL:|Child process \[\d+\] died|"
        r"timeout graceful shutdown exceeded", log
    ), "crash, replacement, or application error is outside this exception")
    console_signal = "SIGBREAK" if shutdown_signal == "SIGTERM" else "SIGINT"
    _require(log.count(f"Received {console_signal}, exiting.") == 1,
             f"supervisor did not acknowledge one {console_signal}")
    if completed:
        _require(len(finishes) == 2 and set(finishes) == set(starts), "workers did not finish cleanly")
        _require(log.count("Application shutdown complete.") == 2, "lifespan cleanup is incomplete")
        _require(f"Stopping parent process [{parents[0]}]" in log, "supervisor did not finish")
    else:
        _require(len(finishes) == 1 and finishes[0] in starts, "not the captured one-worker stall")
        pending = (set(starts) - set(finishes)).pop()
        _require(f"Waiting for child process [{pending}]" in log, "supervisor was not joining stalled worker")
        _require("Stopping parent process" not in log, "supervisor had already finished")


def validate_candidate_lifecycle(row: dict[str, Any], case: dict[str, Any]) -> None:
    """Require a clean candidate even when a defective reference happens to match."""
    _require(eligible_input(case), "candidate contract input is outside the reviewed scope")
    target = row["target_observation"]
    _require(row["server_exit_codes"]["target"] == target["exit_code"] == 0, "candidate probe failed")
    _require(target["response_received"] is True and target["response_status"] == 200,
             "candidate did not serve the request")
    _require(target["process_timed_out"] is False and target["process_exit_code"] == 0,
             "candidate did not exit within the original deadline")
    shutdown_signal = case["api"]["run_http"]["shutdown_signal"]
    _require(target["shutdown_signal_sent"] is True and target["shutdown_signals_sent"] == [shutdown_signal],
             "candidate required a different signal sequence")
    _require(target["worker_replacement_observed"] is False
             and target["worker_start_count"] == target["worker_clean_shutdown_count"] == 2,
             "candidate worker lifecycle is not clean")
    raw = json.loads(_decode(target["stdout_base64"]))["run_http"]
    _require("reference_shutdown_diagnostic" in raw and raw["reference_shutdown_diagnostic"] is None,
             "candidate needed a wakeup or lacks evidence")
    for field in ("process_timed_out", "process_exit_code", "shutdown_signals_sent",
                  "response_received", "response_status", "response_body_base64", "listener_responses"):
        _require(raw[field] == target[field], f"candidate raw evidence disagrees with {field}")
    _clean_lifecycle(_decode(raw["server_stderr_base64"]), completed=True,
                     shutdown_signal=shutdown_signal)


def _reference_recovery(raw_oracle: dict, raw_target: dict, case: dict) -> str:
    """Require the unchanged deadline and exactly one bounded stock-only wakeup."""
    diagnostic = raw_oracle["reference_shutdown_diagnostic"]
    _require(isinstance(diagnostic, dict) and set(diagnostic) == {
        "stderr_before_connection_base64", "timeout_seconds", "recovery_timeout_seconds",
        "connection_opened", "exit_code_after_connection", "error",
    }, "missing bounded post-timeout diagnostic")
    _require(diagnostic["timeout_seconds"] == case["api"]["run_http"]["timeout_seconds"]
             and diagnostic["recovery_timeout_seconds"] == 3, "deadline changed")
    _require(diagnostic["connection_opened"] is True
             and diagnostic["exit_code_after_connection"] == 0
             and diagnostic["error"] is None, "one TCP connection did not release shutdown")
    _require("reference_shutdown_diagnostic" in raw_target
             and raw_target["reference_shutdown_diagnostic"] is None, "candidate needed a wakeup or lacks evidence")
    before = _decode(diagnostic["stderr_before_connection_base64"])
    _require(_decode(raw_oracle["server_stderr_base64"]).startswith(before),
             "pre-wakeup log is not a prefix of the retained complete log")
    return before


def _validate_sigbreak_stall(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any],
    oracle: dict[str, Any], target: dict[str, Any],
    raw_oracle: dict[str, Any], raw_target: dict[str, Any],
) -> dict[str, Any]:
    """Accept only the captured stock SIGBREAK join stall with a clean candidate."""
    _require(case.get("case_id") == SIGBREAK_CASE_ID and eligible_input(case),
             "input is outside the exact two-worker SIGBREAK case")
    _require(environment["platform"].lower().startswith(("windows", "win32")), "not Windows")
    _require(environment["dependencies"].get("uvicorn") == "0.54.0", "reference version changed")
    _require(environment["machine"].lower() in {"amd64", "x86_64"}
             and environment["python"] == "3.12.13", "captured SIGBREAK environment changed")
    _require(row.get("status") == "failed" and bool(row.get("difference")),
             "raw comparison must retain the reference failure")
    _require(row["server_exit_codes"] == {"oracle": 0, "target": 0}, "probe process failed")
    for label, observation in (("reference", oracle), ("candidate", target)):
        _require(observation["exit_code"] == 0, f"{label} probe failed")
        _require(observation["response_received"] is True and observation["response_status"] == 200,
                 f"{label} did not serve the request")
        _require(observation["shutdown_signal_sent"] is True
                 and observation["shutdown_signals_sent"] == ["SIGTERM"],
                 f"{label} signal sequence differs")
        _require(observation["worker_replacement_observed"] is False
                 and observation["worker_start_count"] == 2,
                 f"{label} did not retain the original two workers")

    _require(oracle["process_timed_out"] is True
             and type(oracle["process_exit_code"]) is int
             and oracle["process_exit_code"] != 0,
             "reference did not retain the timed-out worker shutdown")
    _require(target["process_timed_out"] is False and target["process_exit_code"] == 0
             and target["worker_clean_shutdown_count"] == 2,
             "candidate did not finish both workers within the original deadline")
    for field in ("response_content_type", "response_body_base64", "listener_responses"):
        _require(oracle[field] == target[field], f"served response differs: {field}")
    _require(raw_oracle.get("reference_shutdown_diagnostic") is None
             and raw_target.get("reference_shutdown_diagnostic") is None,
             "this policy covers only the captured no-wakeup reference stall")
    for side, raw in ((oracle, raw_oracle), (target, raw_target)):
        for field in ("process_timed_out", "process_exit_code", "shutdown_signals_sent",
                      "response_received", "response_status", "response_content_type",
                      "response_body_base64", "listener_responses"):
            _require(raw[field] == side[field], f"raw evidence disagrees with {field}")
    _clean_lifecycle(_decode(raw_oracle["server_stderr_base64"]), completed=False,
                     shutdown_signal="SIGTERM")
    _clean_lifecycle(_decode(raw_target["server_stderr_base64"]), completed=True,
                     shutdown_signal="SIGTERM")
    return {"case_id": case["case_id"], "policy": SIGBREAK_STALL_POLICY,
            "raw_comparison": "failed", "candidate_contract": "passed",
            "reference_signature": "one worker remains in supervisor join after SIGBREAK"}


def validate_reference_hang(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any]
) -> dict[str, Any]:
    """Reject generic timeouts, other platforms/versions, and candidate defects."""
    _require(eligible_input(case), "input is outside the reviewed Windows worker cases")
    _require(environment["platform"].lower().startswith(("windows", "win32")), "not Windows")
    _require(environment["dependencies"].get("uvicorn") == "0.54.0", "reference version changed")
    shutdown_signal = case["api"]["run_http"]["shutdown_signal"]
    if shutdown_signal == "SIGTERM":
        _require(environment["machine"].lower() in {"amd64", "x86_64"}
                 and environment["python"] == "3.12.13", "captured SIGBREAK environment changed")
    _require(row.get("status") == "failed", "raw comparison must remain failed")
    oracle = row["oracle_observation"]
    target = row["target_observation"]
    _require(set(oracle) == set(target), "reference observation envelope differs")
    _require(row["server_exit_codes"] == {"oracle": 0, "target": 0}, "probe process failed")
    raw_oracle = json.loads(_decode(oracle["stdout_base64"]))["run_http"]
    raw_target = json.loads(_decode(target["stdout_base64"]))["run_http"]
    if shutdown_signal == "SIGTERM" and raw_oracle.get("reference_shutdown_diagnostic") is None:
        return _validate_sigbreak_stall(
            row, case, environment, oracle, target, raw_oracle, raw_target
        )
    for label, observation in (("reference", oracle), ("candidate", target)):
        _require(observation["exit_code"] == 0, f"{label} probe failed")
        _require(observation["response_received"] is True and observation["response_status"] == 200,
                 f"{label} did not serve the request")
        _require(observation["shutdown_signal_sent"] is True
                 and observation["shutdown_signals_sent"] == [shutdown_signal], f"{label} signal sequence differs")
        _require(observation["process_exit_code"] == 0, f"{label} did not exit cleanly")
        _require(observation["worker_replacement_observed"] is False, f"{label} replaced a worker")
        _require(observation["worker_start_count"] == observation["worker_clean_shutdown_count"] == 2,
                 f"{label} worker lifecycle is incomplete")
    _require(oracle["process_timed_out"] is True, "reference did not time out")
    _require(target["process_timed_out"] is False, "candidate exceeded the original deadline")
    before = _reference_recovery(raw_oracle, raw_target, case)
    for side, raw in ((oracle, raw_oracle), (target, raw_target)):
        for field in ("process_timed_out", "process_exit_code", "shutdown_signals_sent",
                      "response_received", "response_status", "response_body_base64", "listener_responses"):
            _require(raw[field] == side[field], f"raw evidence disagrees with {field}")
        _clean_lifecycle(_decode(raw["server_stderr_base64"]), completed=True,
                         shutdown_signal=shutdown_signal)
    _clean_lifecycle(before, completed=False, shutdown_signal=shutdown_signal)
    return {"case_id": case["case_id"],
            "policy": SIGBREAK_POLICY if shutdown_signal == "SIGTERM" else POLICY,
            "raw_comparison": "failed", "candidate_contract": "passed"}
