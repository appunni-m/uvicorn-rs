"""Separate improvement acceptance for a captured stock Windows startup failure.

Raw parity and the reference remain unchanged. Only the recorded two-worker
listen failure and one successful replacement qualify. A separately enabled
hang policy is required when the same run also needs the captured TCP wakeup.
"""

from __future__ import annotations

import json
import re
from typing import Any

from windows_reference_hang import (
    POLICY as SIGINT_HANG_POLICY,
    SIGBREAK_CASE_ID, SIGBREAK_POLICY, _decode, _reference_recovery,
    eligible_input, validate_candidate_lifecycle,
)


POLICY = "uvicorn-0.54.0-windows-two-worker-listen-winerror10022@1"
CASE_ID = "python-api.module-cli-two-workers-serve-request"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"{POLICY}: {message}")


def _windows_log_events(raw: dict[str, Any]) -> dict[str, Any]:
    from run_parity import _python_api_server_log_events

    events = _python_api_server_log_events(raw)
    # Replay the runner's existing Windows-only normalization on any review
    # host. The parser otherwise selects this rule from the review host's OS.
    events["stderr"] = [event for event in events["stderr"] if event != {
        "kind": "message", "level": "INFO", "message": "Terminated child process [<pid>]",
    }]
    return events


def validate_reference_startup(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any]
) -> dict[str, Any]:
    """Accept one identified reference defect only with a clean candidate."""
    return _validate_reference_startup(row, case, environment, with_shutdown_hang=False)


def validate_reference_startup_and_hang(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any]
) -> dict[str, Any]:
    """Require both defect signatures on an explicitly reviewed worker input."""
    return _validate_reference_startup(row, case, environment, with_shutdown_hang=True)


def _validate_reference_startup(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any], *,
    with_shutdown_hang: bool,
) -> dict[str, Any]:
    # Reuse the existing independent candidate contract, not reference behavior.
    validate_candidate_lifecycle(row, case)
    sigbreak = case.get("case_id") == SIGBREAK_CASE_ID
    shutdown_signal = "SIGTERM" if sigbreak else "SIGINT"
    console_signal = "SIGBREAK" if sigbreak else "SIGINT"
    _require(eligible_input(case) and case["case_id"] in {CASE_ID, SIGBREAK_CASE_ID},
             "input is outside the captured explicit two-worker case")
    _require(case["api"]["run_http"] == {
        "method": "GET", "path": "/python-api-two-workers-sigterm" if sigbreak
        else "/python-api-two-workers", "shutdown_signal": shutdown_signal,
        "timeout_seconds": 12, "lifespan": "auto", "invocation": "module-cli",
        "root_path": "", "post_response_settle_seconds": 1, "workers": 2,
    }, "captured request or deadline changed")
    _require(environment["platform"].lower().startswith(("windows", "win32")), "not Windows")
    _require(environment["machine"].lower() in {"amd64", "x86_64"}, "not Windows x86-64")
    _require(environment["python"] == "3.12.13", "captured Python version changed")
    _require(environment["dependencies"].get("uvicorn") == "0.54.0", "reference version changed")
    _require(row.get("status") == "failed", "raw comparison must remain failed")
    oracle, target = row["oracle_observation"], row["target_observation"]
    _require(set(oracle) == set(target), "reference observation envelope differs")
    _require(row["server_exit_codes"] == {"oracle": 0, "target": 0}, "probe process failed")
    _require(oracle["worker_replacement_observed"] is True
             and oracle["worker_start_count"] == 3
             and oracle["worker_clean_shutdown_count"] == 2,
             "not one replaced reference worker with two clean surviving workers")
    for side in (oracle, target):
        expected_timeout = with_shutdown_hang and side is oracle
        _require(side["exit_code"] == 0 and side["process_exit_code"] == 0
                 and side["process_timed_out"] is expected_timeout,
                 "probe or server failed or has an unexpected timeout")
        _require(side["response_received"] is True and side["response_status"] == 200,
                 "request was not served")
        _require(side["shutdown_signal_sent"] is True and side["shutdown_signals_sent"] == [shutdown_signal],
                 "signal sequence differs")
        raw = json.loads(_decode(side["stdout_base64"]))["run_http"]
        if not (with_shutdown_hang and side is oracle):
            _require("reference_shutdown_diagnostic" in raw
                     and raw["reference_shutdown_diagnostic"] is None, "wakeup or missing diagnostic evidence")
        for field in ("process_timed_out", "process_exit_code", "shutdown_signal_sent",
                      "shutdown_signals_sent", "response_received", "response_status",
                      "response_content_type", "response_body_base64", "listener_responses",
                      "idle_connection_closed"):
            _require(raw[field] == side[field], f"raw evidence disagrees with {field}")
        # This is the existing pure log parser; no server or reference is run.
        _require(_windows_log_events(raw) == side["server_log_events"],
                 "normalized server events disagree with retained raw logs")
    _require(oracle["server_log_events"]["stdout"] == target["server_log_events"]["stdout"],
             "access or other stdout events differ")

    raw = json.loads(_decode(oracle["stdout_base64"]))["run_http"]
    log = _decode(raw["server_stderr_base64"]).replace("\r\n", "\n")
    crash = re.search(
        r"(?m)^Process SpawnProcess-\d+:\nTraceback \(most recent call last\):\n"
        r"(?P<frames>.*?)^OSError: \[WinError 10022\] An invalid argument was supplied\n",
        log, re.DOTALL,
    )
    _require(crash is not None and log.count("Traceback (most recent call last):") == 1,
             "not the single captured startup traceback")
    frames = re.findall(r'^  File "([^"\n]+)", line \d+, in (\w+)\n    ([^\n]*)',
                        crash["frames"], re.MULTILINE)
    _require(len(frames) == 13, "startup traceback shape changed")
    tail = [(path.replace("\\", "/").lower(), function, source)
            for path, function, source in frames[-3:]]
    expected_tail = (
        ("/uvicorn/server.py", "startup",
         "server = await loop.create_server(create_protocol, sock=sock, ssl=config.ssl, backlog=config.backlog)"),
        ("/asyncio/base_events.py", "create_server", "server._start_serving()"),
        ("/asyncio/base_events.py", "_start_serving", "sock.listen(self._backlog)"),
    )
    _require(all(path.endswith(suffix) and function == expected_function and source == expected_source
                 for (path, function, source), (suffix, expected_function, expected_source)
                 in zip(tail, expected_tail)), "failure is not create_server -> sock.listen")

    remainder = log[:crash.start()] + log[crash.end():]
    allowed_message = re.compile(
        r"INFO:\s+(?:Uvicorn running on http://127\.0\.0\.1:\d+ \(Press CTRL\+C to quit\)|"
        r"Started (?:parent|server) process \[\d+\]|Waiting for application (?:startup|shutdown)\.|"
        r"Application (?:startup|shutdown) complete\.|ASGI 'lifespan' protocol appears unsupported\.|"
        r"Shutting down|Finished server process \[\d+\]|Waiting for child process \[\d+\]|"
        r"Child process \[\d+\] died|Received " + console_signal + r", exiting\.|"
        + (r"Terminated child process \[\d+\]|" if with_shutdown_hang or sigbreak else "")
        + r"Stopping parent process \[\d+\])"
    )
    _require(all(allowed_message.fullmatch(line) for line in remainder.splitlines() if line),
             "additional reference error or unreviewed log message")
    starts = re.findall(r"Started server process \[(\d+)\]", remainder)
    finishes = re.findall(r"Finished server process \[(\d+)\]", remainder)
    died = re.findall(r"Child process \[(\d+)\] died", remainder)
    parents = re.findall(r"Started parent process \[(\d+)\]", remainder)
    _require(len(starts) == len(set(starts)) == 3 and len(died) == 1
             and died[0] in starts[:2], "not one original worker failure and one replacement")
    _require(len(parents) == 1 and parents[0] not in starts, "missing supervisor identity")
    _require(len(finishes) == 2 and set(finishes) == set(starts) - set(died),
             "surviving workers did not finish cleanly")
    _require(remainder.count("Application startup complete.") == 3
             and remainder.count("Application shutdown complete.") == 2
             and remainder.count("ASGI 'lifespan' protocol appears unsupported.") == 1,
             "incomplete worker lifespans")
    _require(remainder.index(f"Child process [{died[0]}] died")
             < remainder.index(f"Started server process [{starts[2]}]")
             < remainder.index(f"Received {console_signal}, exiting."), "replacement was not before shutdown")
    _require(remainder.count(f"Received {console_signal}, exiting.") == 1
             and re.findall(r"Stopping parent process \[(\d+)\]", remainder) == parents,
             "supervisor did not complete one console-signal shutdown")
    joins = re.findall(r"Waiting for child process \[(\d+)\]", remainder)
    _require(len(joins) == 3 and set(joins) == set(starts),
             "supervisor did not join all children")
    _require(crash.start() < log.index(f"Child process [{died[0]}] died"),
             "traceback was not before the observed replacement")
    if with_shutdown_hang:
        raw_target = json.loads(_decode(target["stdout_base64"]))["run_http"]
        before = _reference_recovery(raw, raw_target, case).replace("\r\n", "\n")
        before_finishes = re.findall(r"Finished server process \[(\d+)\]", before)
        _require(len(before_finishes) == 1 and before_finishes[0] in finishes,
                 "not one clean surviving worker stalled before the wakeup")
        pending = (set(finishes) - set(before_finishes)).pop()
        _require(f"Waiting for child process [{pending}]" in before
                 and before.count("Application shutdown complete.") == 1
                 and before.count(f"Received {console_signal}, exiting.") == 1
                 and "Stopping parent process" not in before,
                 "pre-wakeup evidence does not show the captured supervisor join stall")
    if with_shutdown_hang or sigbreak:
        terminated = re.findall(r"Terminated child process \[(\d+)\]", remainder)
        _require(len(terminated) == len(set(terminated))
                 and set(terminated) <= set(finishes), "unreviewed child termination")
    hang_policy = SIGBREAK_POLICY if sigbreak else SIGINT_HANG_POLICY
    return {"case_id": case["case_id"],
            "policy": f"{POLICY}+{hang_policy}" if with_shutdown_hang else POLICY,
            "raw_comparison": "failed", "candidate_contract": "passed"}
