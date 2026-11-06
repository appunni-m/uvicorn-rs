#!/usr/bin/env python3
"""Focused policy tests for the exact macOS Uvicorn oracle timeout."""

from __future__ import annotations

import copy
import json
import unittest

from macos_reference_exceptions import (
    CASE_ID,
    ERROR_PREFIX,
    EXPECTED_CANDIDATE_OBSERVATION,
    EXPECTED_CASE,
    EXPECTED_EXCEPTION_RECEIPT,
    POLICY_ID,
    parity_gate_errors,
    validate_reference_failure,
    validate_reference_row,
)


ENVIRONMENT = {
    "platform": "macOS-15.7.7-arm64-arm-64bit",
    "machine": "arm64",
    "dependencies": {"uvicorn": "0.54.0", "websockets": "17.1"},
}


def raw_message(**overrides):
    diagnostic = {
        "case_id": CASE_ID,
        "profile": "websocket-tls",
        "oracle_events": ["lifespan.startup"],
        "target_events": ["lifespan.startup", "websocket.scope:/ws"],
        "server_log": "",
        "oracle_process": {
            "alive": True,
            "attempted_cases": [CASE_ID],
            "exit_code": None,
            "pid": 1234,
        },
        "target_process": {
            "alive": True,
            "attempted_cases": [CASE_ID],
            "exit_code": None,
            "pid": 1235,
        },
        "target_observation": copy.deepcopy(EXPECTED_CANDIDATE_OBSERVATION),
        "target_server_log": (
            "INFO:     Started server process [1235]\n"
            "INFO:     Application startup complete.\n"
            "INFO:     Uvicorn running on https://127.0.0.1:43210 (Press CTRL+C to quit)\n"
        ),
    }
    diagnostic.update(overrides)
    return (
        ERROR_PREFIX
        + json.dumps(diagnostic, sort_keys=True)
        + "\nTraceback (most recent call last):\n"
        + "TimeoutError: timed out while waiting for handshake response"
    )


class MacOSReferenceExceptionTests(unittest.TestCase):
    def test_exact_failure_preserves_candidate_only_evidence(self):
        decision = validate_reference_failure(raw_message(), EXPECTED_CASE, ENVIRONMENT)
        self.assertEqual(decision["policy_id"], POLICY_ID)
        self.assertEqual(decision["raw_status"], "infrastructure_failed")
        self.assertEqual(decision["candidate_observation"], EXPECTED_CANDIDATE_OBSERVATION)
        self.assertEqual(decision["root_cause"], "unknown")
        self.assertIsNone(decision["performance_pair"])

    def test_reference_row_must_retain_raw_infrastructure_failure(self):
        row = {
            "case_id": CASE_ID,
            "status": "infrastructure_failed",
            "error": {"class": "ParityError", "message": raw_message()},
        }
        self.assertEqual(
            validate_reference_row(row, EXPECTED_CASE, ENVIRONMENT)["policy_id"],
            POLICY_ID,
        )
        row["status"] = "passed"
        with self.assertRaisesRegex(ValueError, "raw status was rewritten"):
            validate_reference_row(row, EXPECTED_CASE, ENVIRONMENT)

    def test_only_exact_platform_and_dependency_context_is_eligible(self):
        for overrides in (
            {"platform": "Linux-6.12-x86_64"},
            {"machine": "x86_64"},
            {"dependencies": {"uvicorn": "0.54.1", "websockets": "17.1"}},
            {"dependencies": {"uvicorn": "0.54.0", "websockets": "17.2"}},
        ):
            environment = {**ENVIRONMENT, **overrides}
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                validate_reference_failure(raw_message(), EXPECTED_CASE, environment)

    def test_other_failure_signatures_are_rejected(self):
        messages = (
            "oracle uvicorn adapter failed: connection refused",
            raw_message().replace(
                "timed out while waiting for handshake response",
                "connection reset by peer",
            ),
        )
        for message in messages:
            with self.subTest(message=message[:80]), self.assertRaises(ValueError):
                validate_reference_failure(message, EXPECTED_CASE, ENVIRONMENT)

    def test_candidate_must_complete_the_expected_exchange(self):
        diagnostic = json.loads(raw_message()[len(ERROR_PREFIX):].partition("\nTraceback ")[0])
        diagnostic["target_observation"]["ordered_messages"][0]["value"] = "wrong"
        with self.assertRaisesRegex(ValueError, "candidate did not complete"):
            validate_reference_failure(
                raw_message(**diagnostic), EXPECTED_CASE, ENVIRONMENT
            )

    def test_reference_must_fail_before_application_scope_and_candidate_must_reach_scope(self):
        for field, value in (
            ("oracle_events", ["lifespan.startup", "websocket.scope:/ws"]),
            ("target_events", ["lifespan.startup"]),
        ):
            diagnostic = json.loads(raw_message()[len(ERROR_PREFIX):].partition("\nTraceback ")[0])
            diagnostic[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_reference_failure(
                    raw_message(**diagnostic), EXPECTED_CASE, ENVIRONMENT
                )

    def test_input_case_must_remain_exact(self):
        case = copy.deepcopy(EXPECTED_CASE)
        case["websocket"]["messages"][0]["value"] = "different"
        with self.assertRaisesRegex(ValueError, "not the exact indexed"):
            validate_reference_failure(raw_message(), case, ENVIRONMENT)

    def test_accepted_gate_receipt_keeps_raw_failure_and_has_no_ratio(self):
        gate = {
            "status": "accepted_with_reference_exception",
            "public_cases": 786,
            "parity_report": "target/benchmark-preparation/parity.json",
            "parity_report_sha256": "a" * 64,
            "raw_parity_status": "failed",
            "raw_parity_summary": {
                "selected": 786,
                "executed": 786,
                "passed": 785,
                "failed": 0,
                "not_run": 0,
                "infrastructure_failed": 1,
            },
            "accepted_reference_exceptions": [copy.deepcopy(EXPECTED_EXCEPTION_RECEIPT)],
            "before_parity_identity_sha256": "b" * 64,
            "native_sha256": "c" * 64,
            "exception_policy_id": POLICY_ID,
            "exception_policy_sha256": "d" * 64,
            "performance_pair": None,
        }
        self.assertEqual(parity_gate_errors(gate, expected_policy_sha256="d" * 64), [])
        self.assertIn(
            "reference_exception_policy_hash_differs_from_frozen_harness",
            parity_gate_errors(gate, expected_policy_sha256="e" * 64),
        )

        gate["accepted_reference_exceptions"][0]["raw_status"] = "passed"
        self.assertIn(
            "reference_exception_receipt_is_unrecognized_or_malformed",
            parity_gate_errors(gate),
        )

    def test_gate_receipt_rejects_extra_failures_and_claimed_performance(self):
        gate = {
            "status": "accepted_with_reference_exception",
            "public_cases": 786,
            "parity_report": "target/benchmark-preparation/parity.json",
            "parity_report_sha256": "a" * 64,
            "raw_parity_status": "failed",
            "raw_parity_summary": {
                "selected": 786,
                "executed": 786,
                "passed": 784,
                "failed": 1,
                "not_run": 0,
                "infrastructure_failed": 1,
            },
            "accepted_reference_exceptions": [copy.deepcopy(EXPECTED_EXCEPTION_RECEIPT)],
            "before_parity_identity_sha256": "b" * 64,
            "native_sha256": "c" * 64,
            "exception_policy_id": POLICY_ID,
            "exception_policy_sha256": "d" * 64,
            "performance_pair": {"ratio": 1.2},
        }
        errors = parity_gate_errors(gate)
        self.assertIn("reference_exception_raw_parity_summary_is_inconsistent", errors)
        self.assertIn("reference_exception_must_not_claim_a_performance_pair", errors)


if __name__ == "__main__":
    unittest.main()
