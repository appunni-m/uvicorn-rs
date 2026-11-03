#!/usr/bin/env python3
"""Policy regression fixtures; these are not live Windows acceptance evidence."""

from __future__ import annotations

import base64
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check_ci_evidence as evidence
from parity_identity import runtime_source_digest, runtime_source_hashes
from run_parity import _python_api_server_log_events
from windows_reference_hang import CASE_IDS, diagnostic_input, eligible_input, validate_reference_hang


ROOT = Path(__file__).resolve().parents[1]


def encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def fixture():
    manifest, cases, paths = evidence.load_contract()
    case = next(c for c in cases if c["case_id"] == "python-api.module-cli-two-workers-serve-request")
    captured = json.loads((ROOT / "tools/upstream/uvicorn-windows/evidence/ci635-failure-and-wakeup.json").read_text())
    log = captured["server_log"]
    before = log[:log.rfind("INFO:     Shutting down")]
    raw = {
        "process_timed_out": False, "process_exit_code": 0,
        "shutdown_signal_sent": True, "shutdown_signals_sent": ["SIGINT"],
        "response_received": True, "response_status": 200,
        "response_content_type": "text/plain", "response_body_base64": encode("ok"),
        "listener_responses": [{"status": 200, "body_base64": encode("ok")}],
        "server_stdout_base64": "", "server_stderr_base64": encode(log),
        "reference_shutdown_diagnostic": None,
    }
    operation = next(o for o in manifest["operations"] if o["id"] == case["operation"])
    target = {field: raw.get(field) for field in operation["observe"]}
    target.update({"exit_code": 0, "stderr_base64": "",
                   "server_log_events": _python_api_server_log_events(raw),
                   "worker_replacement_observed": False, "worker_start_count": 2,
                   "worker_clean_shutdown_count": 2,
                   "stdout_base64": encode(json.dumps({"run_http": raw}))})
    oracle_raw = deepcopy(raw)
    oracle_raw["process_timed_out"] = True
    oracle_raw["reference_shutdown_diagnostic"] = {
        "stderr_before_connection_base64": encode(before), "timeout_seconds": 12,
        "recovery_timeout_seconds": 3, "connection_opened": True,
        "exit_code_after_connection": 0, "error": None,
    }
    oracle = {**deepcopy(target), "process_timed_out": True,
              "stdout_base64": encode(json.dumps({"run_http": oracle_raw}))}
    row = {"case_id": case["case_id"], "profile": case["profile"],
           "operation": case["operation"], "requirements": case["covers"],
           "verification": "oracle-parity", "fault": None, "status": "failed",
           "difference": "Python API observations differ: process_timed_out",
           "oracle_observation": oracle, "target_observation": target,
           "server_exit_codes": {"oracle": 0, "target": 0}}
    dependencies = {}
    for oracle_spec in manifest["oracles"]:
        dependencies[oracle_spec["id"]] = oracle_spec["version"]
        dependencies.update({c["id"]: c["version"] for c in oracle_spec["components"]
                             if "platforms" not in c or "windows" in c["platforms"]})
    source_files = runtime_source_hashes(ROOT)
    harness = {"runner": "scripts/run_parity.py", "runner_sha256": evidence.sha256(ROOT / "scripts/run_parity.py"),
               "identity_helper": {"path": "scripts/parity_identity.py", "sha256": evidence.sha256(ROOT / "scripts/parity_identity.py")},
               "fixture_app": "tests/parity/app.py", "fixture_app_sha256": evidence.sha256(ROOT / "tests/parity/app.py"),
               "python_api_probe": {"path": "tests/parity/python_api_probe.py", "sha256": evidence.sha256(ROOT / "tests/parity/python_api_probe.py")},
               "http3_client": None}
    result = {"schema": manifest["result_schema"], "status": "failed", "cases": [row], "infrastructure_errors": [],
              "summary": {"selected": 1, "executed": 1, "passed": 0, "failed": 1, "not_run": 0, "infrastructure_failed": 0},
              "run": {"run_id": "unit-fixture-not-a-live-receipt", "started_at": "fixture", "finished_at": "fixture",
                      "manifest": {"path": "tests/parity/manifest.json", "schema": manifest["schema"], "sha256": evidence.sha256(evidence.MANIFEST_PATH)},
                      "inputs": [{"path": p.relative_to(ROOT).as_posix(), "schema": evidence.source_constant(ROOT / "scripts/run_parity.py", "INPUT_SCHEMA"),
                                  "sha256": evidence.sha256(p)} for p in paths],
                      "environment": {"python": "3.12.13", "platform": captured["platform"], "machine": "AMD64", "rustc": "fixture", "dependencies": dependencies},
                      "target": {"revision": evidence.git_commit(), "dirty": False, "native_extension": {"path": "fixture.pyd", "sha256": "a" * 64},
                                 "cargo_lock_sha256": evidence.sha256(ROOT / "Cargo.lock"), "source_files": source_files, "source_sha256": runtime_source_digest(source_files)},
                      "harness": harness, "command": ["python", "scripts/run_parity.py", "--case-id", case["case_id"]]}}
    return result, case


class ReferenceHangPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template, cls.case_template = fixture()

    def setUp(self):
        self.result, self.case = deepcopy(self.template), deepcopy(self.case_template)
        self.row = self.result["cases"][0]

    def check(self, **kwargs):
        return evidence.validate_parity(self.result, expected_cases=[self.case],
                                        allow_windows_reference_hang=True, **kwargs)

    def change_raw(self, side, edit):
        observation = self.row[f"{side}_observation"]
        raw = json.loads(base64.b64decode(observation["stdout_base64"]))
        edit(raw["run_http"])
        observation["stdout_base64"] = encode(json.dumps(raw))

    def test_acceptance_retains_failed_parity_and_does_not_mutate_evidence(self):
        original = deepcopy(self.result)
        checked = self.check()
        self.assertEqual(checked["status"], "accepted_with_reference_exception")
        self.assertEqual(checked["raw_parity_summary"]["failed"], 1)
        self.assertEqual(len(checked["accepted_reference_defects"]), 1)
        self.assertEqual(self.result, original)

    def test_default_gate_still_rejects_reference_failure(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(self.result, expected_cases=[self.case])

    def test_normal_parity_pass_needs_no_exception(self):
        self.row.update(status="passed", difference=None,
                        oracle_observation=deepcopy(self.row["target_observation"]))
        self.result["status"] = "completed"
        self.result["summary"].update(passed=1, failed=0)
        checked = self.check()
        self.assertEqual(checked["status"], "passed")
        self.assertEqual(checked["accepted_reference_defects"], [])
        self.assertEqual(checked["candidate_contract_cases"], [self.case["case_id"]])

    def test_equal_reference_and_candidate_crashes_cannot_pass_by_agreeing(self):
        self.row["target_observation"]["worker_replacement_observed"] = True
        self.row["target_observation"]["worker_start_count"] = 3
        self.row.update(status="passed", difference=None,
                        oracle_observation=deepcopy(self.row["target_observation"]))
        self.result["status"] = "completed"
        self.result["summary"].update(passed=1, failed=0)
        with self.assertRaises(evidence.EvidenceError):
            self.check()

    def test_cli_writes_separate_receipt_without_rewriting_raw_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw, receipt = Path(temporary) / "raw.json", Path(temporary) / "acceptance.json"
            raw.write_text(json.dumps(self.result))
            before = raw.read_bytes()
            command = [sys.executable, str(ROOT / "scripts/check_ci_evidence.py"), "parity", str(raw),
                       "--offline", "--require-clean", "--case-id", self.case["case_id"],
                       "--accept-windows-reference-hang", "--acceptance-output", str(receipt)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            decision = json.loads(receipt.read_text())
            self.assertEqual(decision["decision"]["raw_parity_status"], "failed")
            self.assertEqual(decision["parity_report"]["sha256"], evidence.sha256(raw))
            self.assertEqual(raw.read_bytes(), before)
            command[-1] = str(raw)
            rejected = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(raw.read_bytes(), before)

    def test_exact_reviewed_input_selection(self):
        _, cases, _ = evidence.load_contract()
        self.assertEqual({c["case_id"] for c in cases if eligible_input(c)}, CASE_IDS)

    def test_sigbreak_diagnostic_does_not_expand_acceptance(self):
        _, cases, _ = evidence.load_contract()
        case = next(c for c in cases if c["case_id"] ==
                    "python-api.module-cli-two-workers-stop-on-sigterm")
        self.assertTrue(diagnostic_input(case))
        self.assertFalse(eligible_input(case))
        with self.assertRaisesRegex(ValueError, "outside the three reviewed"):
            validate_reference_hang(self.row, case, self.result["run"]["environment"])
        for field, value in (("workers", 3), ("shutdown_signal", "SIGINT"),
                             ("shutdown_signal_sequence", ["SIGTERM", "SIGTERM"])):
            changed = deepcopy(case)
            changed["api"]["run_http"][field] = value
            self.assertFalse(diagnostic_input(changed), field)

    def test_exact_diagnostic_input_selection(self):
        _, cases, _ = evidence.load_contract()
        self.assertEqual({c["case_id"] for c in cases if diagnostic_input(c)},
                         CASE_IDS | {"python-api.module-cli-two-workers-stop-on-sigterm"})

    def test_rejects_candidate_failures(self):
        for field, value in (("process_timed_out", True), ("process_exit_code", 1),
                             ("response_status", 503), ("worker_start_count", 3),
                             ("worker_clean_shutdown_count", 1), ("worker_replacement_observed", True),
                             ("shutdown_signals_sent", ["SIGINT", "SIGINT"]),
                             ("response_body_base64", encode("wrong body"))):
            with self.subTest(field=field):
                original = deepcopy(self.row["target_observation"])
                self.row["target_observation"][field] = value
                with self.assertRaises(evidence.EvidenceError):
                    self.check()
                self.row["target_observation"] = original

    def test_rejects_other_reference_failures(self):
        for edit in (
            lambda r: r.update(reference_shutdown_diagnostic=None),
            lambda r: r["reference_shutdown_diagnostic"].update(connection_opened=False),
            lambda r: r["reference_shutdown_diagnostic"].update(exit_code_after_connection=None, error="TimeoutExpired"),
            lambda r: r["reference_shutdown_diagnostic"].update(timeout_seconds=30),
            lambda r: r["reference_shutdown_diagnostic"].update(stderr_before_connection_base64=encode("startup WinError(10022)")),
            lambda r: r.update(process_timed_out=False),
        ):
            with self.subTest(edit=edit):
                self.result = deepcopy(self.template)
                self.row = self.result["cases"][0]
                self.change_raw("oracle", edit)
                with self.assertRaises(evidence.EvidenceError):
                    self.check()

    def test_rejects_candidate_wakeup(self):
        self.change_raw("target", lambda r: r.update(reference_shutdown_diagnostic={"connection_opened": True}))
        with self.assertRaises(evidence.EvidenceError):
            self.check()

    def test_rejects_other_platform_versions_or_relabelled_result(self):
        for location, key, value in (
            ("environment", "platform", "Linux"), ("dependencies", "uvicorn", "0.55.0"),
            ("target", "revision", "wrong-revision"), ("target", "source_sha256", "0" * 64),
            ("result", "status", "completed"), ("row", "difference", None),
            ("row", "status", "infrastructure_failed"),
        ):
            with self.subTest(key=key):
                self.result = deepcopy(self.template)
                self.row = self.result["cases"][0]
                objects = {"result": self.result, "row": self.row, **self.result["run"],
                           "dependencies": self.result["run"]["environment"]["dependencies"]}
                objects[location][key] = value
                with self.assertRaises(evidence.EvidenceError):
                    self.check()

    def test_rejects_missing_case_and_native_mismatch(self):
        with self.assertRaises(evidence.EvidenceError):
            self.check(expected_native_sha256="b" * 64)
        self.result["cases"] = []
        with self.assertRaises(evidence.EvidenceError):
            self.check()


if __name__ == "__main__":
    unittest.main()
