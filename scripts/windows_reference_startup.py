"""Separate improvement acceptance for captured stock Windows worker failures.

Raw parity and the reference remain unchanged. Only exact reviewed worker
inputs, the recorded listen failure, and the candidate's expected replacement
and shutdown behavior qualify. A separately enabled hang policy is required
when the same run also needs the captured TCP wakeup.
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


POLICY = "uvicorn-0.54.0-windows-two-worker-listen-winerror10022@2"
CASE_ID = "python-api.module-cli-two-workers-serve-request"
CRASH_RESTART_CASE_ID = "python-api.module-cli-worker-crash-restarts"
TWO_CRASH_RESTART_CASE_ID = "python-api.module-cli-worker-restarts-after-two-crashes"
CRASH_RESTART_POLICY = "uvicorn-0.54.0-windows-worker-restart-listen-winerror10022@1"
TWO_CRASH_RESTART_POLICY = "uvicorn-0.54.0-windows-two-crashes-listen-winerror10022@1"

_CRASH_RESTART_INPUT = {
    "method": "GET", "path": "/python-api-worker-restart",
    "shutdown_signal": "SIGINT", "timeout_seconds": 20,
    "lifespan": "off", "invocation": "module-cli", "root_path": "",
    "workers": 2, "environment": {"ASGI_PARITY_WORKER_CRASH_ONCE": "1"},
}
_TWO_CRASH_RESTART_INPUT = {
    "method": "GET", "path": "/python-api-worker-restart",
    "shutdown_signal": "SIGINT", "timeout_seconds": 20,
    "client_timeout_seconds": 15, "lifespan": "off",
    "invocation": "module-cli", "root_path": "", "workers": 2,
    "environment": {"ASGI_PARITY_WORKER_CRASH_COUNT": "2"},
    "required_observations": {
        "response_received": True, "response_status": 200,
        "process_timed_out": False, "worker_replacement_observed": True,
    },
}


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


def diagnostic_input(case: dict[str, Any]) -> bool:
    """Retain full reference timeout evidence for the two reviewed crash inputs."""
    expected = {
        CRASH_RESTART_CASE_ID: _CRASH_RESTART_INPUT,
        TWO_CRASH_RESTART_CASE_ID: _TWO_CRASH_RESTART_INPUT,
    }.get(case.get("case_id"))
    return (
        expected is not None
        and case.get("profile") == "python-api"
        and case.get("operation") == "python.api.run-http"
        and case.get("verification", "oracle-parity") == "oracle-parity"
        and case.get("api", {}).get("run_http") == expected
    )


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
    case_id = case.get("case_id")
    if case_id == CRASH_RESTART_CASE_ID:
        _validate_crash_restart_reference(row, case, environment, crash_count=1,
                                          with_shutdown_hang=False)
        return {"case_id": case_id, "policy": CRASH_RESTART_POLICY,
                "raw_comparison": "failed", "candidate_contract": "passed"}
    if case_id == TWO_CRASH_RESTART_CASE_ID:
        _validate_crash_restart_reference(row, case, environment, crash_count=2,
                                          with_shutdown_hang=with_shutdown_hang)
        policy = TWO_CRASH_RESTART_POLICY
        if with_shutdown_hang:
            policy = f"{policy}+{SIGINT_HANG_POLICY}"
        return {"case_id": case_id, "policy": policy,
                "raw_comparison": "failed", "candidate_contract": "passed"}

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


def _policy_require(policy: str, condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"{policy}: {message}")


def _raw_observation(
    observation: dict[str, Any], *, policy: str, side: str,
) -> dict[str, Any]:
    _policy_require(policy, isinstance(observation, dict), f"{side} observation is missing")
    try:
        raw = json.loads(_decode(observation["stdout_base64"]))["run_http"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{policy}: {side} raw HTTP observation is malformed") from error
    for field in (
        "process_timed_out", "process_exit_code", "shutdown_signal_sent",
        "shutdown_signals_sent", "response_received", "response_status",
        "response_content_type", "response_body_base64", "listener_responses",
        "idle_connection_closed",
    ):
        _policy_require(policy, raw.get(field) == observation.get(field),
                        f"{side} raw evidence disagrees with {field}")
    _policy_require(policy, _windows_log_events(raw) == observation.get("server_log_events"),
                    f"{side} normalized log events disagree with retained raw logs")
    return raw


def _listen_error_remainder(log: str, *, policy: str) -> tuple[re.Match[str], str]:
    log = log.replace("\r\n", "\n")
    crash = re.search(
        r"(?m)^Process SpawnProcess-\d+:\nTraceback \(most recent call last\):\n"
        r"(?P<frames>.*?)^OSError: \[WinError 10022\] An invalid argument was supplied\n",
        log, re.DOTALL,
    )
    _policy_require(policy, crash is not None
                    and log.count("Traceback (most recent call last):") == 1,
                    "not the single captured startup traceback")
    assert crash is not None
    frames = re.findall(r'^  File "([^"\n]+)", line \d+, in (\w+)\n    ([^\n]*)',
                        crash["frames"], re.MULTILINE)
    _policy_require(policy, len(frames) == 13, "startup traceback shape changed")
    tail = [(path.replace("\\", "/").lower(), function, source)
            for path, function, source in frames[-3:]]
    expected_tail = (
        ("/uvicorn/server.py", "startup",
         "server = await loop.create_server(create_protocol, sock=sock, ssl=config.ssl, backlog=config.backlog)"),
        ("/asyncio/base_events.py", "create_server", "server._start_serving()"),
        ("/asyncio/base_events.py", "_start_serving", "sock.listen(self._backlog)"),
    )
    _policy_require(policy, all(
        path.endswith(suffix) and function == expected_function and source == expected_source
        for (path, function, source), (suffix, expected_function, expected_source)
        in zip(tail, expected_tail)
    ), "failure is not create_server -> sock.listen")
    return crash, log[:crash.start()] + log[crash.end():]


def _worker_log_counts(log: str, *, policy: str, starts: int, deaths: int) -> tuple[list[str], list[str]]:
    start_ids = re.findall(r"Started server process \[(\d+)\]", log)
    death_ids = re.findall(r"Child process \[(\d+)\] died", log)
    finish_ids = re.findall(r"Finished server process \[(\d+)\]", log)
    parent_ids = re.findall(r"Started parent process \[(\d+)\]", log)
    _policy_require(policy, len(start_ids) == len(set(start_ids)) == starts,
                    f"expected {starts} unique worker starts")
    _policy_require(policy, len(death_ids) == len(set(death_ids)) == deaths
                    and set(death_ids) <= set(start_ids),
                    f"expected {deaths} identified worker crashes")
    _policy_require(policy, len(finish_ids) == len(set(finish_ids)) == 2
                    and set(finish_ids) == set(start_ids) - set(death_ids),
                    "the two surviving workers did not shut down cleanly")
    _policy_require(policy, len(parent_ids) == 1 and parent_ids[0] not in start_ids,
                    "missing unique worker supervisor")
    return start_ids, finish_ids


def _validate_crash_restart_reference(
    row: dict[str, Any], case: dict[str, Any], environment: dict[str, Any], *,
    crash_count: int, with_shutdown_hang: bool,
) -> None:
    case_id = CRASH_RESTART_CASE_ID if crash_count == 1 else TWO_CRASH_RESTART_CASE_ID
    policy = CRASH_RESTART_POLICY if crash_count == 1 else TWO_CRASH_RESTART_POLICY
    expected_input = _CRASH_RESTART_INPUT if crash_count == 1 else _TWO_CRASH_RESTART_INPUT
    _policy_require(policy, diagnostic_input(case) and case_id == case.get("case_id")
                    and case["api"]["run_http"] == expected_input,
                    "input is outside the exact reviewed worker-crash workflow")
    _policy_require(policy, environment["platform"].lower().startswith(("windows", "win32")),
                    "not Windows")
    _policy_require(policy, environment["machine"].lower() in {"amd64", "x86_64"},
                    "not Windows x86-64")
    _policy_require(policy, environment["python"] == "3.12.13", "captured Python version changed")
    _policy_require(policy, environment["dependencies"].get("uvicorn") == "0.54.0",
                    "reference version changed")
    _policy_require(policy, row.get("status") == "failed", "raw comparison must remain failed")
    _policy_require(policy, row.get("server_exit_codes") == {"oracle": 0, "target": 0},
                    "probe process failed")
    difference = row.get("difference", "")
    prefix = "Python API observations differ: "
    _policy_require(policy, isinstance(difference, str) and difference.startswith(prefix),
                    "raw mismatch reason is missing")
    difference_fields = {field.strip() for field in difference[len(prefix):].split(",")}
    expected_differences = {"server_log_events"}
    if with_shutdown_hang:
        expected_differences.add("process_timed_out")
    _policy_require(policy, difference_fields == expected_differences,
                    "raw mismatch includes an unreviewed observation difference")

    oracle, target = row["oracle_observation"], row["target_observation"]
    _policy_require(policy, isinstance(oracle, dict) and isinstance(target, dict)
                    and set(oracle) == set(target), "reference observation envelope differs")
    expected_reference_starts = crash_count + 3  # two workers + injected crash(es) + listen failure
    expected_candidate_starts = crash_count + 2
    expected_reference_deaths = crash_count + 1
    for side, observation, timed_out, expected_starts, expected_deaths in (
        ("oracle", oracle, with_shutdown_hang, expected_reference_starts, expected_reference_deaths),
        ("target", target, False, expected_candidate_starts, crash_count),
    ):
        _policy_require(policy, observation["exit_code"] == 0
                        and observation["process_exit_code"] == 0
                        and observation["process_timed_out"] is timed_out,
                        f"{side} process outcome differs from the captured policy")
        _policy_require(policy, observation["response_received"] is True
                        and observation["response_status"] == 200,
                        f"{side} did not serve the request")
        _policy_require(policy, observation["shutdown_signal_sent"] is True
                        and observation["shutdown_signals_sent"] == ["SIGINT"],
                        f"{side} signal sequence differs")
        _policy_require(policy, observation["worker_start_count"] == expected_starts
                        and observation["worker_replacement_observed"] is True
                        and observation["worker_clean_shutdown_count"] == 2,
                        f"{side} restart or shutdown counts differ")
        raw = _raw_observation(observation, policy=policy, side=side)
        diagnostic = raw.get("reference_shutdown_diagnostic")
        if side == "target" or not with_shutdown_hang:
            _policy_require(policy, diagnostic is None,
                            f"{side} needed a timeout wakeup or has unexpected diagnostic evidence")
        raw_log = _decode(raw["server_stderr_base64"]).replace("\r\n", "\n")
        if side == "target":
            _policy_require(policy, not re.search(r"Traceback|WinError|ERROR:|CRITICAL:", raw_log),
                            "candidate reproduced the reference startup failure")
            clean_log = raw_log
            listen_failure = None
        else:
            listen_failure, clean_log = _listen_error_remainder(raw_log, policy=policy)
        starts, finishes = _worker_log_counts(
            clean_log, policy=policy, starts=expected_starts, deaths=expected_deaths
        )
        _policy_require(policy, clean_log.count("Received SIGINT, exiting.") == 1
                        and clean_log.count("Stopping parent process") == 1
                        and clean_log.count("Shutting down") == 2,
                        f"{side} did not follow the captured one-signal worker shutdown")
        joins = set(re.findall(r"Waiting for child process \[(\d+)\]", clean_log))
        _policy_require(policy, set(starts) <= joins,
                        f"{side} supervisor did not join all started workers")
        signal_position = clean_log.index("Received SIGINT, exiting.")
        stop_match = re.search(r"Stopping parent process \[(\d+)\]", clean_log)
        start_positions = [match.start() for match in re.finditer(
            r"Started server process \[\d+\]", clean_log
        )]
        death_positions = [match.start() for match in re.finditer(
            r"Child process \[\d+\] died", clean_log
        )]
        finish_positions = [match.start() for match in re.finditer(
            r"Finished server process \[\d+\]", clean_log
        )]
        _policy_require(policy, max(start_positions) < signal_position
                        and max(death_positions) < signal_position,
                        f"{side} replaced a worker after shutdown began")
        for index, position in enumerate(death_positions):
            replacements_after = sum(
                position < start < signal_position for start in start_positions
            )
            _policy_require(policy, replacements_after >= len(death_positions) - index,
                            f"{side} did not replace each failed worker before shutdown")
        _policy_require(policy, stop_match is not None
                        and stop_match.start() > max(finish_positions),
                        f"{side} supervisor stopped before both workers finished")
        if listen_failure is not None:
            first_death = re.search(r"(?m)^INFO:\s+Child process \[\d+\] died", raw_log)
            _policy_require(policy, first_death is not None
                            and listen_failure.end() <= first_death.start(),
                            "startup failure was not before worker replacement")
        terminated = set(re.findall(r"Terminated child process \[(\d+)\]", clean_log))
        _policy_require(policy, terminated <= set(finishes),
                        f"{side} terminated a worker outside the captured shutdown")
        if side == "target":
            _policy_require(policy, terminated == set(finishes),
                            "candidate did not finish both surviving workers")
        if side == "oracle":
            _policy_require(policy, clean_log.count("Traceback (most recent call last):") == 0,
                            "reference has an additional unreviewed traceback")
            allowed = re.compile(
                r"INFO:\s+(?:Uvicorn running on http://127\.0\.0\.1:\d+ \(Press CTRL\+C to quit\)|"
                r"Started parent process \[\d+\]|Started server process \[\d+\]|"
                r"Waiting for child process \[\d+\]|Child process \[\d+\] died|"
                r"Shutting down|Received SIGINT, exiting\.|Terminated child process \[\d+\]|"
                r"Finished server process \[\d+\]|Stopping parent process \[\d+\])"
            )
            _policy_require(policy, all(allowed.fullmatch(line) for line in clean_log.splitlines() if line),
                            "additional reference error or unreviewed log message")

    _policy_require(policy, oracle["server_log_events"]["stdout"]
                    == target["server_log_events"]["stdout"],
                    "access or other stdout events differ")
    target_raw = _raw_observation(target, policy=policy, side="target")
    oracle_raw = _raw_observation(oracle, policy=policy, side="oracle")
    _policy_require(policy, oracle_raw["response_body_base64"] == target_raw["response_body_base64"]
                    and oracle_raw["response_content_type"] == target_raw["response_content_type"]
                    and oracle_raw["listener_responses"] == target_raw["listener_responses"],
                    "HTTP response differs")
    if with_shutdown_hang:
        before = _reference_recovery(oracle_raw, target_raw, case).replace("\r\n", "\n")
        before_finishes = re.findall(r"Finished server process \[(\d+)\]", before)
        oracle_log = _decode(oracle_raw["server_stderr_base64"]).replace("\r\n", "\n")
        oracle_crash, oracle_remainder = _listen_error_remainder(oracle_log, policy=policy)
        _, full_finishes = _worker_log_counts(
            oracle_remainder, policy=policy,
            starts=expected_reference_starts, deaths=expected_reference_deaths,
        )
        pending_finishes = set(full_finishes) - set(before_finishes)
        _policy_require(policy, len(before_finishes) == 1
                        and before_finishes[0] in full_finishes
                        and len(pending_finishes) == 1
                        and f"Waiting for child process [{next(iter(pending_finishes))}]" in before
                        and f"Traceback (most recent call last):" in before
                        and oracle_crash.end() <= len(before),
                        "pre-wakeup evidence does not retain startup and one clean worker")
        _policy_require(policy, "Received SIGINT, exiting." in before
                        and "Stopping parent process" not in before,
                        "pre-wakeup evidence does not show a supervisor join stall")
