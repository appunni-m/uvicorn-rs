"""Explicit acceptance for one recorded stock-Uvicorn defect, outside parity.

The raw comparison stays failed. This policy accepts only the Windows
two-worker SIGINT timeout that completes after one diagnostic TCP connection,
with an independently clean candidate lifecycle on the same input.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any


POLICY = "uvicorn-0.54.0-windows-two-worker-sigint-tcp-wakeup@1"
CASE_IDS = {
    "python-api.module-cli-two-workers-serve-request",
    "python-api.module-cli-web-concurrency-two-workers-serve-request",
    "python-api.module-cli-explicit-workers-overrides-web-concurrency",
}


def eligible_input(case: dict[str, Any]) -> bool:
    request = case.get("api", {}).get("run_http", {})
    environment = request.get("environment", {})
    return (
        case.get("case_id") in CASE_IDS
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
        and request.get("shutdown_signal") == "SIGINT"
        and request.get("root_path") == ""
        and set(environment) <= {"WEB_CONCURRENCY"}
        and (
            request.get("workers") == 2 if "workers" in request
            else environment.get("WEB_CONCURRENCY") == "2"
        )
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"{POLICY}: {message}")


def _decode(value: str) -> str:
    return base64.b64decode(value, validate=True).decode("utf-8")


def _clean_lifecycle(log: str, *, completed: bool) -> None:
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
    _require("Received SIGINT, exiting." in log, "supervisor did not acknowledge SIGINT")
    if completed:
        _require(len(finishes) == 2 and set(finishes) == set(starts), "workers did not finish cleanly")
        _require(log.count("Application shutdown complete.") == 2, "lifespan cleanup is incomplete")
        _require(f"Stopping parent process [{parents[0]}]" in log, "supervisor did not finish")
    else:
        _require(len(finishes) == 1 and finishes[0] in starts, "not the captured one-worker stall")
        pending = (set(starts) - set(finishes)).pop()
        _require(f"Waiting for child process [{pending}]" in log, "supervisor was not joining stalled worker")
        _require("Stopping parent process" not in log, "supervisor had already finished")


def validate_reference_hang(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any]
) -> dict[str, Any]:
    """Reject generic timeouts, other platforms/versions, and candidate defects."""
    _require(eligible_input(case), "input is outside the three reviewed Windows worker cases")
    _require(environment["platform"].lower().startswith(("windows", "win32")), "not Windows")
    _require(environment["dependencies"].get("uvicorn") == "0.54.0", "reference version changed")
    _require(row.get("status") == "failed", "raw comparison must remain failed")
    oracle = row["oracle_observation"]
    target = row["target_observation"]
    _require(row["server_exit_codes"] == {"oracle": 0, "target": 0}, "probe process failed")
    for label, observation in (("reference", oracle), ("candidate", target)):
        _require(observation["exit_code"] == 0, f"{label} probe failed")
        _require(observation["response_received"] is True and observation["response_status"] == 200,
                 f"{label} did not serve the request")
        _require(observation["shutdown_signal_sent"] is True
                 and observation["shutdown_signals_sent"] == ["SIGINT"], f"{label} signal sequence differs")
        _require(observation["process_exit_code"] == 0, f"{label} did not exit cleanly")
        _require(observation["worker_replacement_observed"] is False, f"{label} replaced a worker")
        _require(observation["worker_start_count"] == observation["worker_clean_shutdown_count"] == 2,
                 f"{label} worker lifecycle is incomplete")
    _require(oracle["process_timed_out"] is True, "reference did not time out")
    _require(target["process_timed_out"] is False, "candidate exceeded the original deadline")
    raw_oracle = json.loads(_decode(oracle["stdout_base64"]))["run_http"]
    raw_target = json.loads(_decode(target["stdout_base64"]))["run_http"]
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
    for side, raw in ((oracle, raw_oracle), (target, raw_target)):
        for field in ("process_timed_out", "process_exit_code", "shutdown_signals_sent",
                      "response_received", "response_status", "response_body_base64", "listener_responses"):
            _require(raw[field] == side[field], f"raw evidence disagrees with {field}")
        _clean_lifecycle(_decode(raw["server_stderr_base64"]), completed=True)
    _clean_lifecycle(_decode(diagnostic["stderr_before_connection_base64"]), completed=False)
    return {"case_id": case["case_id"], "policy": POLICY,
            "raw_comparison": "failed", "candidate_contract": "passed"}
