#!/usr/bin/env python3
"""Policy regression fixtures, not new live Windows qualification evidence."""

from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import check_ci_evidence as evidence
from test_windows_reference_hang import encode, fixture
from windows_reference_startup import (
    CRASH_RESTART_CASE_ID,
    CRASH_RESTART_POLICY,
    POLICY,
    SIGINT_HANG_POLICY,
    SIGBREAK_POLICY,
    TWO_CRASH_RESTART_HANG_POLICY,
    TWO_CRASH_RESTART_CASE_ID,
    TWO_CRASH_RESTART_POLICY,
    WEB_CONCURRENCY_CASE_ID,
    WEB_CONCURRENCY_NO_REPLACEMENT_POLICY,
    WEB_CONCURRENCY_STARTUP_POLICY,
    _windows_log_events,
    diagnostic_input,
)


ROOT = Path(__file__).resolve().parents[1]


def _listen_traceback():
    frames = [
        (r"C:\Python\Lib\multiprocessing\process.py", 314, "_bootstrap", "self.run()"),
        (r"C:\Python\Lib\multiprocessing\process.py", 108, "run", "self._target(*self._args, **self._kwargs)"),
        (
            r"C:\agent\uvicorn_rs_upstream_oracle\Lib\site-packages\uvicorn\_subprocess.py",
            80, "subprocess_started", "target(sockets=sockets)",
        ),
        (
            r"C:\agent\uvicorn_rs_upstream_oracle\Lib\site-packages\uvicorn\supervisors\multiprocess.py",
            77, "target", "self.server.run(sockets)",
        ),
        (
            r"C:\agent\uvicorn_rs_upstream_oracle\Lib\site-packages\uvicorn\server.py",
            86, "run", "return asyncio_run(self.serve(sockets=sockets), loop_factory=self.config.get_loop_factory())",
        ),
        (r"C:\Python\Lib\asyncio\runners.py", 195, "run", "return runner.run(main)"),
        (r"C:\Python\Lib\asyncio\runners.py", 118, "run", "return self._loop.run_until_complete(task)"),
        (r"C:\Python\Lib\asyncio\base_events.py", 691, "run_until_complete", "return future.result()"),
        (
            r"C:\agent\uvicorn_rs_upstream_oracle\Lib\site-packages\uvicorn\server.py",
            90, "serve", "await self._serve(sockets)",
        ),
        (
            r"C:\agent\uvicorn_rs_upstream_oracle\Lib\site-packages\uvicorn\server.py",
            105, "_serve", "await self.startup(sockets=sockets)",
        ),
        (
            r"C:\agent\uvicorn_rs_upstream_oracle\Lib\site-packages\uvicorn\server.py",
            154, "startup",
            "server = await loop.create_server(create_protocol, sock=sock, ssl=config.ssl, backlog=config.backlog)",
        ),
        (r"C:\Python\Lib\asyncio\base_events.py", 1609, "create_server", "server._start_serving()"),
        (r"C:\Python\Lib\asyncio\base_events.py", 316, "_start_serving", "sock.listen(self._backlog)"),
    ]
    return (
        "Process SpawnProcess-1:\nTraceback (most recent call last):\n"
        + "".join(f'  File "{path}", line {line}, in {function}\n    {source}\n'
                  for path, line, function, source in frames)
        + "OSError: [WinError 10022] An invalid argument was supplied\n"
    )


def _worker_log(base: int, *, crash_count: int, listen_failure: bool, stalled: bool) -> tuple[str, str | None]:
    next_pid = base
    parent = next_pid + 99
    next_pid += 1
    starts = [next_pid, next_pid + 1]
    active = list(starts)
    next_pid += 2
    lines = [
        f"INFO:     Uvicorn running on http://127.0.0.1:{base + 5000} (Press CTRL+C to quit)",
        f"INFO:     Started parent process [{parent}]",
        *(f"INFO:     Started server process [{pid}]" for pid in starts),
    ]
    if listen_failure:
        lines.append(_listen_traceback().rstrip("\n"))
    failed_workers = crash_count + (1 if listen_failure else 0)
    for _ in range(failed_workers):
        failed = active.pop(0)
        lines.extend((
            f"INFO:     Waiting for child process [{failed}]",
            f"INFO:     Child process [{failed}] died",
        ))
        replacement = next_pid
        next_pid += 1
        starts.append(replacement)
        active.append(replacement)
        lines.append(f"INFO:     Started server process [{replacement}]")
    survivors = active
    lines.extend((
        "INFO:     Received SIGINT, exiting.",
        "INFO:     Shutting down",
        "INFO:     Shutting down",
        *(f"INFO:     Terminated child process [{pid}]" for pid in survivors),
        f"INFO:     Waiting for child process [{survivors[0]}]",
        f"INFO:     Finished server process [{survivors[0]}]",
        f"INFO:     Waiting for child process [{survivors[1]}]",
    ))
    before = "\n".join(lines) + "\n"
    lines.append(f"INFO:     Finished server process [{survivors[1]}]")
    lines.extend((f"INFO:     Waiting for child process [{pid}]" for pid in survivors))
    lines.append(f"INFO:     Stopping parent process [{parent}]")
    return "\n".join(lines) + "\n", before if stalled else None


def _worker_crash_fixture(
    case_id: str, *, with_shutdown_hang: bool = False, listen_failure: bool = True,
):
    result, _ = fixture()
    _, cases, _ = evidence.load_contract()
    case = deepcopy(next(item for item in cases if item["case_id"] == case_id))
    crash_count = 1 if case_id == CRASH_RESTART_CASE_ID else 2
    reference_log, before = _worker_log(
        3000, crash_count=crash_count, listen_failure=listen_failure, stalled=with_shutdown_hang,
    )
    candidate_log, _ = _worker_log(
        4000, crash_count=crash_count, listen_failure=False, stalled=False,
    )
    response_body = b"python-api-worker-restarted"

    def observation(log, *, timeout, side):
        diagnostic = None
        if side == "oracle" and with_shutdown_hang:
            diagnostic = {
                "stderr_before_connection_base64": encode(before),
                "timeout_seconds": 20, "recovery_timeout_seconds": 3,
                "connection_opened": True, "exit_code_after_connection": 0,
                "error": None,
            }
        raw = {
            "process_timed_out": timeout,
            "process_exit_code": 0,
            "shutdown_signal_sent": True,
            "shutdown_signals_sent": ["SIGINT"],
            "response_received": True,
            "response_status": 200,
            "response_content_type": "text/plain",
            "response_body_base64": encode(response_body.decode()),
            "listener_responses": [{"status": 200, "body_base64": encode(response_body.decode())}],
            "idle_connection_closed": None,
            "server_stdout_base64": "",
            "server_stderr_base64": encode(log),
            "reference_shutdown_diagnostic": diagnostic,
        }
        starts = re.findall(r"Started server process \[(\d+)\]", log)
        deaths = re.findall(r"Child process \[(\d+)\] died", log)
        manifest, _, _ = evidence.load_contract()
        operation = next(item for item in manifest["operations"] if item["id"] == case["operation"])
        output = {field: raw.get(field) for field in operation["observe"]}
        output.update({
            "exit_code": 0,
            "stdout_base64": encode(json.dumps({"run_http": raw})),
            "stderr_base64": "",
            "server_log_events": _windows_log_events(raw),
            "worker_replacement_observed": bool(deaths),
            "worker_start_count": len(starts),
            "worker_clean_shutdown_count": 2,
        })
        return output

    oracle = observation(reference_log, timeout=with_shutdown_hang, side="oracle")
    target = observation(candidate_log, timeout=False, side="target")
    difference_fields = []
    if oracle["process_timed_out"] != target["process_timed_out"]:
        difference_fields.append("process_timed_out")
    if oracle["server_log_events"] != target["server_log_events"]:
        difference_fields.append("server_log_events")
    row = {
        "case_id": case["case_id"], "profile": case["profile"],
        "operation": case["operation"], "requirements": case["covers"],
        "verification": "oracle-parity", "fault": None, "status": "failed",
        "difference": f"Python API observations differ: {', '.join(difference_fields)}",
        "oracle_observation": oracle, "target_observation": target,
        "server_exit_codes": {"oracle": 0, "target": 0},
    }
    result["cases"] = [row]
    result["status"] = "failed"
    result["summary"] = {
        "selected": 1, "executed": 1, "passed": 0, "failed": 1,
        "not_run": 0, "infrastructure_failed": 0,
    }
    result["run"]["environment"].update(
        python="3.12.13", platform="Windows-2022Server-10.0.20348-SP0", machine="AMD64"
    )
    result["run"]["command"] = ["python", "scripts/run_parity.py", "--case-id", case_id]
    return result, case


class ReferenceStartupPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template, cls.case_template = fixture()
        cls.capture = json.loads((ROOT / "tools/upstream/uvicorn-windows/evidence/ci637-startup-worker-failure.json").read_text())
        cls.template["cases"] = [cls.capture["row"]]
        cls.template["run"]["environment"] = cls.capture["environment"]

    def setUp(self):
        self.result, self.case = deepcopy(self.template), deepcopy(self.case_template)
        self.row = self.result["cases"][0]

    def check(self, **kwargs):
        return evidence.validate_parity(self.result, expected_cases=[self.case],
                                       allow_windows_reference_startup=True, **kwargs)

    def load_web_concurrency_no_replacement_capture(self):
        capture = json.loads(
            (ROOT / "tools/upstream/uvicorn-windows/evidence/"
             "ci707-web-concurrency-no-replacement.json").read_text()
        )
        _, cases, _ = evidence.load_contract()
        self.case = deepcopy(next(item for item in cases
                                  if item["case_id"] == WEB_CONCURRENCY_CASE_ID))
        self.result = deepcopy(self.template)
        self.row = deepcopy(capture["row"])
        self.result["cases"] = [self.row]
        self.result["status"] = "failed"
        self.result["summary"] = {
            "selected": 1, "executed": 1, "passed": 0, "failed": 1,
            "not_run": 0, "infrastructure_failed": 0,
        }
        self.result["run"]["environment"] = deepcopy(capture["environment"])
        self.result["run"]["command"] = [
            "python", "scripts/run_parity.py", "--case-id", WEB_CONCURRENCY_CASE_ID,
        ]

    def edit_raw(self, side, edit):
        observation = self.row[side + "_observation"]
        raw = json.loads(base64.b64decode(observation["stdout_base64"]))
        edit(raw["run_http"])
        observation["stdout_base64"] = encode(json.dumps(raw))
        observation["server_log_events"] = _windows_log_events(raw["run_http"])

    def edit_log(self, edit):
        self.edit_raw("oracle", lambda raw: raw.update(server_stderr_base64=encode(
            edit(base64.b64decode(raw["server_stderr_base64"]).decode()))))

    def test_captured_defect_accepted_without_changing_failed_parity(self):
        before = deepcopy(self.result)
        decision = self.check()
        self.assertEqual(decision["status"], "accepted_with_reference_exception")
        self.assertEqual(decision["raw_parity_summary"]["failed"], 1)
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"], POLICY)
        self.assertEqual(decision["candidate_contract_cases"], [self.case["case_id"]])
        self.assertEqual(self.result, before)

    def test_web_concurrency_startup_failure_has_its_own_exact_input_policy(self):
        _, cases, _ = evidence.load_contract()
        self.case = deepcopy(next(item for item in cases
                                  if item["case_id"] == WEB_CONCURRENCY_CASE_ID))
        self.row.update(case_id=self.case["case_id"], profile=self.case["profile"],
                        operation=self.case["operation"], requirements=self.case["covers"])
        self.result["run"]["command"] = [
            "python", "scripts/run_parity.py", "--case-id", WEB_CONCURRENCY_CASE_ID,
        ]
        decision = self.check()
        self.assertEqual(decision["status"], "accepted_with_reference_exception")
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"],
                         WEB_CONCURRENCY_STARTUP_POLICY)
        self.assertEqual(decision["raw_parity_summary"]["failed"], 1)
        self.assertEqual(decision["candidate_contract_cases"], [WEB_CONCURRENCY_CASE_ID])

        changed = deepcopy(self.case)
        changed["api"]["run_http"]["environment"]["WEB_CONCURRENCY"] = "3"
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(
                self.result, expected_cases=[changed], allow_windows_reference_startup=True,
            )

    def test_web_concurrency_no_replacement_failure_is_accepted_without_rewriting_parity(self):
        self.load_web_concurrency_no_replacement_capture()
        before = deepcopy(self.result)
        decision = self.check()
        self.assertEqual(decision["status"], "accepted_with_reference_exception")
        self.assertEqual(decision["raw_parity_status"], "failed")
        self.assertEqual(decision["raw_parity_summary"]["failed"], 1)
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"],
                         WEB_CONCURRENCY_NO_REPLACEMENT_POLICY)
        self.assertEqual(decision["accepted_reference_defects"][0]["startup_exception"], True)
        self.assertEqual(decision["candidate_contract_cases"], [WEB_CONCURRENCY_CASE_ID])
        self.assertEqual(self.result, before)

    def test_web_concurrency_no_replacement_policy_rejects_changed_evidence(self):
        mutations = (
            ("reference worker count", lambda: self.row["oracle_observation"].update(
                worker_clean_shutdown_count=2)),
            ("candidate worker count", lambda: self.row["target_observation"].update(
                worker_clean_shutdown_count=1)),
            ("reference error", lambda: self.edit_raw(
                "oracle", lambda raw: raw.update(server_stderr_base64=encode(
                    base64.b64decode(raw["server_stderr_base64"]).decode().replace(
                        "WinError 10022", "WinError 10038"))))),
            ("extra candidate error", lambda: self.edit_raw(
                "target", lambda raw: raw.update(server_stderr_base64=encode(
                    base64.b64decode(raw["server_stderr_base64"]).decode()
                    + "ERROR: unrelated failure\n")))),
            ("changed input", lambda: self.case["api"]["run_http"]["environment"].__setitem__(
                "WEB_CONCURRENCY", "3")),
            ("changed Python", lambda: self.result["run"]["environment"].update(
                python="3.13.0")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                self.load_web_concurrency_no_replacement_capture()
                mutate()
                with self.assertRaises(evidence.EvidenceError):
                    self.check()

    def test_default_and_shutdown_policy_still_reject_startup_failure(self):
        for kwargs in ({}, {"allow_windows_reference_hang": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(evidence.EvidenceError):
                evidence.validate_parity(self.result, expected_cases=[self.case], **kwargs)

    def test_startup_policy_does_not_accept_shutdown_hang(self):
        result, case = fixture()
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case], allow_windows_reference_startup=True)
        for result, case in ((result, case), (self.result, self.case)):
            decision = evidence.validate_parity(result, expected_cases=[case],
                allow_windows_reference_hang=True, allow_windows_reference_startup=True)
            self.assertEqual(len(decision["accepted_reference_defects"]), 1)

    def test_rejects_other_crashes_or_incomplete_reference_lifecycle(self):
        for old, new in (
            ("WinError 10022", "WinError 10038"),
            ("sock.listen(self._backlog)", "sock.accept()"),
            ("in startup", "in shutdown"),
            ("Child process [6196] died", "Child process [7012] died"),
            ("Finished server process [7012]", "Finished server process [6196]"),
            ("Application startup complete.", "Application startup incomplete."),
            ("Stopping parent process [3628]", "Stopping parent process [9999]"),
            ("Received SIGINT, exiting.", "Received SIGTERM, exiting."),
        ):
            with self.subTest(old=old):
                self.setUp()
                self.edit_log(lambda log: log.replace(old, new))
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
        for extra in ("ERROR:     another failure\n", "Traceback (most recent call last):\n",
                      "INFO:     Started server process [9999]\n"):
            with self.subTest(extra=extra):
                self.setUp()
                self.edit_log(lambda log: log + extra)
                with self.assertRaises(evidence.EvidenceError):
                    self.check()

    def test_rejects_raw_normalized_disagreement_and_wakeup(self):
        for field, value in (("response_status", 503), ("process_timed_out", True),
                             ("reference_shutdown_diagnostic", {"connection_opened": True})):
            with self.subTest(field=field):
                self.setUp()
                self.edit_raw("oracle", lambda raw: raw.update({field: value}))
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
        self.setUp()
        self.row["oracle_observation"]["server_log_events"]["stderr"] = []
        with self.assertRaisesRegex(evidence.EvidenceError, "normalized server events disagree"):
            self.check()

    def test_response_mismatch_is_not_waived_even_with_consistent_raw_evidence(self):
        self.row["target_observation"]["response_body_base64"] = encode("wrong body")
        self.edit_raw("target", lambda raw: raw.update(response_body_base64=encode("wrong body")))
        with self.assertRaisesRegex(evidence.EvidenceError, "live observations differ"):
            self.check()

    def test_candidate_cannot_crash_or_hang_to_match_reference(self):
        for field, value in (("process_timed_out", True), ("process_exit_code", 1),
                             ("worker_replacement_observed", True), ("worker_start_count", 3),
                             ("worker_clean_shutdown_count", 1),
                             ("shutdown_signals_sent", ["SIGINT", "SIGINT"])):
            with self.subTest(field=field):
                self.setUp()
                self.row["target_observation"][field] = value
                with self.assertRaises(evidence.EvidenceError):
                    self.check()

    def test_rejects_unreviewed_platform_version_and_case(self):
        for key, value in (("platform", "Linux"), ("machine", "ARM64"), ("python", "3.13.0")):
            with self.subTest(key=key):
                self.setUp()
                self.result["run"]["environment"][key] = value
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
        self.setUp()
        self.result["run"]["environment"]["dependencies"]["uvicorn"] = "0.55.0"
        with self.assertRaises(evidence.EvidenceError):
            self.check()
        self.setUp()
        self.case["api"]["run_http"]["shutdown_signal"] = "SIGTERM"
        with self.assertRaises(evidence.EvidenceError):
            self.check()
        self.setUp()
        self.case["api"]["run_http"]["timeout_seconds"] = 30
        with self.assertRaisesRegex(evidence.EvidenceError, "deadline changed"):
            self.check()

    def test_different_stdout_events_cannot_hide_behind_startup_acceptance(self):
        self.edit_raw("oracle", lambda raw: raw.update(server_stdout_base64=encode("unexpected stdout\n")))
        with self.assertRaisesRegex(evidence.EvidenceError, "stdout events differ"):
            self.check()

    def test_cli_requires_explicit_policy_and_preserves_raw_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, receipt = Path(directory) / "raw.json", Path(directory) / "acceptance.json"
            raw.write_text(json.dumps(self.result))
            before = raw.read_bytes()
            command = [sys.executable, str(ROOT / "scripts/check_ci_evidence.py"), "parity", str(raw),
                       "--offline", "--require-clean", "--case-id", self.case["case_id"],
                       "--accept-windows-reference-startup", "--acceptance-output", str(receipt)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            accepted = json.loads(receipt.read_text())
            self.assertEqual(accepted["startup_policy_sha256"], evidence.sha256(ROOT / "scripts/windows_reference_startup.py"))
            self.assertEqual(accepted["decision"]["raw_parity_status"], "failed")
            self.assertEqual(raw.read_bytes(), before)
            command[-1] = str(raw)
            self.assertNotEqual(subprocess.run(command, capture_output=True, timeout=20).returncode, 0)
            self.assertEqual(raw.read_bytes(), before)


class CombinedReferenceDefectTests(unittest.TestCase):
    """Replay the captured pair of defects without manufacturing a live receipt."""

    @classmethod
    def setUpClass(cls):
        cls.template, _ = fixture()
        capture = json.loads((ROOT / "tools/upstream/uvicorn-windows/evidence/ci641-sigbreak-startup-and-hang.json").read_text())
        cls.template["cases"] = [capture["row"]]
        cls.template["run"]["environment"] = capture["environment"]
        _, cases, _ = evidence.load_contract()
        cls.case_template = next(c for c in cases if c["case_id"] == capture["row"]["case_id"])

    def setUp(self):
        self.result, self.case = deepcopy(self.template), deepcopy(self.case_template)
        self.row = self.result["cases"][0]

    def check(self):
        return evidence.validate_parity(self.result, expected_cases=[self.case],
            allow_windows_reference_startup=True, allow_windows_reference_hang=True)

    def edit_raw(self, side, edit):
        observation = self.row[side + "_observation"]
        raw = json.loads(base64.b64decode(observation["stdout_base64"]))["run_http"]
        edit(raw)
        observation["stdout_base64"] = encode(json.dumps({"run_http": raw}))
        observation["server_log_events"] = _windows_log_events(raw)

    def test_both_explicit_policies_required_and_raw_failure_retained(self):
        before = deepcopy(self.result)
        decision = self.check()
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"],
                         f"{POLICY}+{SIGBREAK_POLICY}")
        self.assertEqual(decision["raw_parity_summary"]["failed"], 1)
        self.assertEqual(decision["candidate_contract_cases"], [self.case["case_id"]])
        self.assertEqual(self.result, before)
        for kwargs in ({}, {"allow_windows_reference_startup": True},
                       {"allow_windows_reference_hang": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(evidence.EvidenceError):
                evidence.validate_parity(self.result, expected_cases=[self.case], **kwargs)

    def test_composition_also_checks_the_previously_reviewed_sigint_input(self):
        _, cases, _ = evidence.load_contract()
        self.case = next(c for c in cases if c["case_id"] ==
                         "python-api.module-cli-two-workers-serve-request")
        self.row["case_id"] = self.case["case_id"]
        for side in ("oracle", "target"):
            self.row[side + "_observation"]["shutdown_signals_sent"] = ["SIGINT"]
            def edit(raw):
                raw["shutdown_signals_sent"] = ["SIGINT"]
                raw["server_stderr_base64"] = encode(base64.b64decode(
                    raw["server_stderr_base64"]).decode().replace("SIGBREAK", "SIGINT"))
                if raw["reference_shutdown_diagnostic"] is not None:
                    diagnostic = raw["reference_shutdown_diagnostic"]
                    diagnostic["stderr_before_connection_base64"] = encode(base64.b64decode(
                        diagnostic["stderr_before_connection_base64"]).decode().replace("SIGBREAK", "SIGINT"))
            self.edit_raw(side, edit)
        self.assertEqual(self.check()["status"], "accepted_with_reference_exception")

    def test_sigbreak_startup_without_hang_needs_no_hang_waiver(self):
        self.row["oracle_observation"]["process_timed_out"] = False
        self.edit_raw("oracle", lambda raw: raw.update(
            process_timed_out=False, reference_shutdown_diagnostic=None))
        decision = evidence.validate_parity(self.result, expected_cases=[self.case],
                                           allow_windows_reference_startup=True)
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"], POLICY)

    def test_candidate_must_remain_independently_clean(self):
        for field, value in (("process_timed_out", True), ("process_exit_code", 1),
                             ("worker_replacement_observed", True), ("worker_start_count", 3),
                             ("worker_clean_shutdown_count", 1),
                             ("shutdown_signals_sent", ["SIGTERM", "SIGTERM"])):
            with self.subTest(field=field):
                self.setUp()
                self.row["target_observation"][field] = value
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
        self.setUp()
        self.edit_raw("target", lambda raw: raw.update(reference_shutdown_diagnostic={"connection_opened": True}))
        with self.assertRaises(evidence.EvidenceError):
            self.check()
        self.setUp()
        self.row["target_observation"] = deepcopy(self.row["oracle_observation"])
        self.row.update(status="passed", difference=None)
        self.result.update(status="completed")
        self.result["summary"].update(passed=1, failed=0)
        with self.assertRaises(evidence.EvidenceError):
            self.check()

    def test_no_response_mismatch_is_waived(self):
        self.row["target_observation"]["response_body_base64"] = encode("wrong")
        self.edit_raw("target", lambda raw: raw.update(response_body_base64=encode("wrong")))
        with self.assertRaisesRegex(evidence.EvidenceError, "live observations differ"):
            self.check()

    def test_both_signatures_must_be_complete(self):
        for old, new in (("WinError 10022", "WinError 10038"),
                         ("sock.listen(self._backlog)", "sock.accept()"),
                         ("Received SIGBREAK", "Received SIGINT"),
                         ("Finished server process [4984]", "Finished server process [1292]")):
            with self.subTest(old=old):
                self.setUp()
                self.edit_raw("oracle", lambda raw: raw.update(server_stderr_base64=encode(
                    base64.b64decode(raw["server_stderr_base64"]).decode().replace(old, new))))
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
        self.setUp()
        self.edit_raw("oracle", lambda raw: raw.update(server_stderr_base64=encode(
            base64.b64decode(raw["server_stderr_base64"]).decode() + "ERROR: unrelated failure\n")))
        with self.assertRaises(evidence.EvidenceError):
            self.check()

    def test_wakeup_deadline_and_pre_wakeup_join_are_required(self):
        for changes in ({"connection_opened": False}, {"exit_code_after_connection": 1},
                        {"timeout_seconds": 30}, {"error": "TimeoutExpired"},
                        {"stderr_before_connection_base64": encode("unrelated log")},
                        {"stderr_before_connection_base64": ""}):
            with self.subTest(changes=changes):
                self.setUp()
                self.edit_raw("oracle", lambda raw: raw["reference_shutdown_diagnostic"].update(changes))
                with self.assertRaises(evidence.EvidenceError):
                    self.check()

    def test_scope_does_not_expand_to_other_inputs_or_versions(self):
        for key, value in (("workers", 3), ("timeout_seconds", 30),
                           ("shutdown_signal", "SIGINT"), ("path", "/other")):
            with self.subTest(key=key):
                self.setUp()
                self.case["api"]["run_http"][key] = value
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
        self.setUp()
        self.result["run"]["environment"]["dependencies"]["uvicorn"] = "0.55.0"
        with self.assertRaises(evidence.EvidenceError):
            self.check()


class WorkerCrashReferencePolicyTests(unittest.TestCase):
    def test_one_injected_crash_keeps_candidate_recovery_and_accepts_only_stock_listen_error(self):
        result, case = _worker_crash_fixture(CRASH_RESTART_CASE_ID)
        before = deepcopy(result)
        decision = evidence.validate_parity(
            result, expected_cases=[case], allow_windows_reference_startup=True,
        )
        self.assertEqual(decision["status"], "accepted_with_reference_exception")
        self.assertEqual(decision["raw_parity_status"], "failed")
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"], CRASH_RESTART_POLICY)
        self.assertEqual(decision["candidate_contract_cases"], [CRASH_RESTART_CASE_ID])
        self.assertEqual(result, before)

    def test_two_crash_timeout_needs_both_startup_and_hang_policies(self):
        result, case = _worker_crash_fixture(TWO_CRASH_RESTART_CASE_ID, with_shutdown_hang=True)
        decision = evidence.validate_parity(
            result, expected_cases=[case], allow_windows_reference_startup=True,
            allow_windows_reference_hang=True,
        )
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"],
                         f"{TWO_CRASH_RESTART_POLICY}+{SIGINT_HANG_POLICY}")
        self.assertEqual(decision["raw_parity_summary"]["failed"], 1)
        self.assertEqual(decision["candidate_contract_cases"], [TWO_CRASH_RESTART_CASE_ID])
        for kwargs in ({}, {"allow_windows_reference_startup": True},
                       {"allow_windows_reference_hang": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(evidence.EvidenceError):
                evidence.validate_parity(result, expected_cases=[case], **kwargs)

    def test_two_crash_startup_error_without_timeout_needs_only_startup_policy(self):
        result, case = _worker_crash_fixture(TWO_CRASH_RESTART_CASE_ID)
        decision = evidence.validate_parity(
            result, expected_cases=[case], allow_windows_reference_startup=True,
        )
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"], TWO_CRASH_RESTART_POLICY)

    def test_two_crash_reference_hang_without_startup_failure_is_accepted_by_hang_policy(self):
        result, case = _worker_crash_fixture(
            TWO_CRASH_RESTART_CASE_ID, with_shutdown_hang=True, listen_failure=False,
        )
        decision = evidence.validate_parity(
            result, expected_cases=[case], allow_windows_reference_hang=True,
        )
        self.assertEqual(decision["status"], "accepted_with_reference_exception")
        self.assertEqual(decision["raw_parity_status"], "failed")
        self.assertEqual(decision["raw_parity_summary"]["failed"], 1)
        self.assertEqual(decision["accepted_reference_defects"][0]["policy"],
                         TWO_CRASH_RESTART_HANG_POLICY)
        self.assertEqual(decision["candidate_contract_cases"], [TWO_CRASH_RESTART_CASE_ID])
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case])
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(
                result, expected_cases=[case], allow_windows_reference_startup=True,
            )

    def test_two_crash_reference_hang_requires_wakeup_and_clean_candidate(self):
        for side, field, value in (
            ("target", "process_timed_out", True),
            ("oracle", "process_timed_out", False),
        ):
            result, case = _worker_crash_fixture(
                TWO_CRASH_RESTART_CASE_ID, with_shutdown_hang=True, listen_failure=False,
            )
            result["cases"][0][f"{side}_observation"][field] = value
            with self.subTest(side=side, field=field), self.assertRaises(evidence.EvidenceError):
                evidence.validate_parity(
                    result, expected_cases=[case], allow_windows_reference_hang=True,
                )

        result, case = _worker_crash_fixture(
            TWO_CRASH_RESTART_CASE_ID, with_shutdown_hang=True, listen_failure=False,
        )
        observation = result["cases"][0]["oracle_observation"]
        raw = json.loads(base64.b64decode(observation["stdout_base64"]))
        raw["run_http"]["reference_shutdown_diagnostic"]["connection_opened"] = False
        observation["stdout_base64"] = encode(json.dumps(raw))
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(
                result, expected_cases=[case], allow_windows_reference_hang=True,
            )

    def test_candidate_must_perform_the_declared_crashes_and_shutdown(self):
        result, case = _worker_crash_fixture(CRASH_RESTART_CASE_ID)
        result["cases"][0]["target_observation"]["worker_start_count"] = 2
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case],
                                     allow_windows_reference_startup=True)

        result, case = _worker_crash_fixture(TWO_CRASH_RESTART_CASE_ID, with_shutdown_hang=True)
        result["cases"][0]["target_observation"]["process_timed_out"] = True
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case],
                allow_windows_reference_startup=True, allow_windows_reference_hang=True)

    def test_reference_wakeup_and_error_signature_are_exact(self):
        result, case = _worker_crash_fixture(TWO_CRASH_RESTART_CASE_ID, with_shutdown_hang=True)
        observation = result["cases"][0]["oracle_observation"]
        raw = json.loads(base64.b64decode(observation["stdout_base64"]))["run_http"]
        diagnostic = raw["reference_shutdown_diagnostic"]
        diagnostic["connection_opened"] = False
        observation["stdout_base64"] = encode(json.dumps({"run_http": raw}))
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case],
                allow_windows_reference_startup=True, allow_windows_reference_hang=True)

        result, case = _worker_crash_fixture(CRASH_RESTART_CASE_ID)
        observation = result["cases"][0]["oracle_observation"]
        raw = json.loads(base64.b64decode(observation["stdout_base64"]))["run_http"]
        raw["server_stderr_base64"] = encode(
            base64.b64decode(raw["server_stderr_base64"]).decode().replace("WinError 10022", "WinError 10038")
        )
        observation["stdout_base64"] = encode(json.dumps({"run_http": raw}))
        observation["server_log_events"] = _windows_log_events(raw)
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case],
                                     allow_windows_reference_startup=True)

    def test_timeout_diagnostics_are_retained_only_for_exact_crash_inputs(self):
        _, cases, _ = evidence.load_contract()
        cases_by_id = {case["case_id"]: case for case in cases}
        self.assertTrue(diagnostic_input(cases_by_id[CRASH_RESTART_CASE_ID]))
        self.assertTrue(diagnostic_input(cases_by_id[TWO_CRASH_RESTART_CASE_ID]))
        changed = deepcopy(cases_by_id[TWO_CRASH_RESTART_CASE_ID])
        changed["api"]["run_http"]["timeout_seconds"] += 1
        self.assertFalse(diagnostic_input(changed))
        self.assertFalse(diagnostic_input(cases_by_id["python-api.module-cli-two-workers-serve-request"]))


if __name__ == "__main__":
    unittest.main()
