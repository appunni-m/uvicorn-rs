#!/usr/bin/env python3
"""Policy regression fixtures, not new live Windows qualification evidence."""

import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_ci_evidence as evidence
from test_windows_reference_hang import encode, fixture
from windows_reference_startup import POLICY, SIGBREAK_POLICY, _windows_log_events


ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
