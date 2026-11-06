#!/usr/bin/env python3
"""Focused policy tests for exact macOS Uvicorn oracle timeouts."""

from __future__ import annotations

import base64
import copy
import json
import unittest

from macos_reference_exceptions import (
    CASE_ID,
    ERROR_PREFIX,
    EXPECTED_CANDIDATE_OBSERVATION,
    EXPECTED_CASE,
    EXPECTED_EXCEPTION_RECEIPT,
    EXPECTED_EXCEPTION_RECEIPTS,
    EXPECTED_SCOPE_CANDIDATE_EVENTS,
    EXPECTED_SCOPE_CANDIDATE_OBSERVATION,
    EXPECTED_SCOPE_CASE,
    EXPECTED_SCOPE_EXCEPTION_RECEIPT,
    POLICY_ID,
    SCOPE_CASE_ID,
    SCOPE_DIAGNOSTIC_MARKER,
    SCOPE_ERROR_PREFIX,
    parity_gate_errors,
    validate_reference_failure,
    validate_reference_row,
)


ENVIRONMENT = {
    "platform": "macOS-15.8.2-arm64-arm-64bit",
    "machine": "arm64",
    "dependencies": {"uvicorn": "0.54.0", "websockets": "17.1"},
}


def raw_message(**overrides):
    diagnostic = {
        "case_id": CASE_ID,
        "profile": "websocket-tls",
        "oracle_events": ["lifespan.startup"],
        "target_events": ["lifespan.startup", "websocket.scope:/ws"],
        "server_log": (
            "INFO:     Started server process [1234]\n"
            "INFO:     Application startup complete.\n"
            "INFO:     Uvicorn running on https://127.0.0.1:43209 (Press CTRL+C to quit)\n"
        ),
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


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def scope_observation():
    scope = {
        "type": "websocket",
        "asgi_version": "3.0",
        "http_version": "1.1",
        "scheme": "wss",
        "path": "/ws-scope-echo/raw space-é",
        "raw_path_base64": _b64(b"/ws-scope-echo/raw%20space-%C3%A9"),
        "query_string_base64": _b64(b"tag=second&tag=first&plus=a+b&escaped=%2B"),
        "root_path": "",
        "headers_base64": [
            [_b64(b"connection"), _b64(b"Upgrade")],
            [_b64(b"host"), _b64(b"127.0.0.1:<port>")],
            [_b64(b"sec-websocket-version"), _b64(b"13")],
            [_b64(b"sec-websocket-extensions"), _b64(b"permessage-deflate; client_max_window_bits")],
            [_b64(b"sec-websocket-protocol"), _b64(b"scope-v1, parity")],
            [_b64(b"upgrade"), _b64(b"websocket")],
            [_b64(b"user-agent"), _b64(b"Python/3.12 websockets/17.1")],
            [_b64(b"x-duplicate"), _b64(b"second")],
            [_b64(b"x-duplicate"), _b64(b"first")],
        ],
        "client": ["127.0.0.1", "<port>"],
        "server": ["127.0.0.1", "<port>"],
        "subprotocols": ["scope-v1", "parity"],
        "state": {"parity-token": "ready"},
    }
    observation = copy.deepcopy(EXPECTED_SCOPE_CANDIDATE_OBSERVATION)
    observation["ordered_messages"] = [{
        "kind": "text",
        "value": json.dumps(scope, separators=(",", ":"), ensure_ascii=False),
    }]
    return observation


def scope_raw_message(**overrides):
    diagnostic = {
        "case_id": SCOPE_CASE_ID,
        "profile": "websocket-tls",
        "oracle_events": ["lifespan.startup"],
        "target_events": copy.deepcopy(EXPECTED_SCOPE_CANDIDATE_EVENTS),
        "server_log": (
            "INFO:     Started server process [23063]\n"
            "INFO:     Application startup complete.\n"
            "INFO:     Uvicorn running on https://127.0.0.1:52581 (Press CTRL+C to quit)\n"
        ),
        "oracle_process": {
            "alive": True,
            "attempted_cases": [SCOPE_CASE_ID],
            "exit_code": None,
            "pid": 23063,
        },
        "target_process": {
            "alive": True,
            "attempted_cases": [SCOPE_CASE_ID],
            "exit_code": None,
            "pid": 23064,
        },
        "target_observation": scope_observation(),
        "target_server_log": (
            "INFO:     Started server process [23064]\n"
            "INFO:     Application startup complete.\n"
            "INFO:     Uvicorn running on https://127.0.0.1:52583 (Press CTRL+C to quit)\n"
        ),
    }
    diagnostic.update(overrides)
    client_trace = (
        "DEBUG = connection is CONNECTING\n"
        "DEBUG > GET " + EXPECTED_SCOPE_CASE["websocket"]["path"] + " HTTP/1.1\n"
        "DEBUG > Upgrade: websocket\n"
        "DEBUG > EOF\n"
        "DEBUG = connection is CLOSED\n"
        "DEBUG ! error while receiving data\n"
        "Traceback (most recent call last):\nOSError: [Errno 9] Bad file descriptor"
    )
    return (
        SCOPE_ERROR_PREFIX
        + client_trace
        + SCOPE_DIAGNOSTIC_MARKER
        + json.dumps(diagnostic, sort_keys=True)
        + "\nTraceback (most recent call last):\n"
        + "TimeoutError: timed out while waiting for handshake response"
    )


class MacOSReferenceExceptionTests(unittest.TestCase):
    def test_exact_text_timeout_preserves_candidate_only_evidence(self):
        decision = validate_reference_failure(raw_message(), EXPECTED_CASE, ENVIRONMENT)
        self.assertEqual(decision["policy_id"], POLICY_ID)
        self.assertEqual(decision["raw_status"], "infrastructure_failed")
        self.assertEqual(decision["candidate_observation"], EXPECTED_CANDIDATE_OBSERVATION)
        self.assertEqual(decision["root_cause"], "unknown")
        self.assertIsNone(decision["performance_pair"])

    def test_exact_scope_timeout_preserves_candidate_scope_and_header_evidence(self):
        decision = validate_reference_failure(
            scope_raw_message(), EXPECTED_SCOPE_CASE, ENVIRONMENT
        )
        self.assertEqual(decision["policy_id"], POLICY_ID)
        self.assertEqual(decision["case_id"], SCOPE_CASE_ID)
        self.assertEqual(decision["candidate_observation"], EXPECTED_SCOPE_CANDIDATE_OBSERVATION)
        self.assertEqual(decision["candidate_events"], EXPECTED_SCOPE_CANDIDATE_EVENTS)
        self.assertEqual(decision["root_cause"], "unknown")
        self.assertIsNone(decision["performance_pair"])

    def test_reference_row_keeps_raw_infrastructure_failure(self):
        for case, message in (
            (EXPECTED_CASE, raw_message()),
            (EXPECTED_SCOPE_CASE, scope_raw_message()),
        ):
            with self.subTest(case=case["case_id"]):
                row = {
                    "case_id": case["case_id"],
                    "status": "infrastructure_failed",
                    "error": {"class": "ParityError", "message": message},
                }
                self.assertEqual(
                    validate_reference_row(row, case, ENVIRONMENT)["raw_status"],
                    "infrastructure_failed",
                )
                row["status"] = "passed"
                with self.assertRaisesRegex(ValueError, "raw status was rewritten"):
                    validate_reference_row(row, case, ENVIRONMENT)

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

    def test_other_failure_signatures_and_client_requests_are_rejected(self):
        messages = (
            "oracle uvicorn adapter failed: connection refused",
            raw_message().replace(
                "timed out while waiting for handshake response",
                "connection reset by peer",
            ),
            scope_raw_message().replace(
                EXPECTED_SCOPE_CASE["websocket"]["path"], "/different-path", 1
            ),
        )
        for message, case in zip(messages, (EXPECTED_CASE, EXPECTED_CASE, EXPECTED_SCOPE_CASE)):
            with self.subTest(message=message[:80]), self.assertRaises(ValueError):
                validate_reference_failure(message, case, ENVIRONMENT)

    def test_candidate_must_complete_the_expected_text_exchange(self):
        diagnostic = json.loads(raw_message()[len(ERROR_PREFIX):].partition("\nTraceback ")[0])
        diagnostic["target_observation"]["ordered_messages"][0]["value"] = "wrong"
        with self.assertRaisesRegex(ValueError, "candidate did not complete"):
            validate_reference_failure(raw_message(**diagnostic), EXPECTED_CASE, ENVIRONMENT)

    def test_candidate_must_preserve_scope_query_and_duplicate_headers(self):
        diagnostic = json.loads(
            scope_raw_message()
            .partition(SCOPE_DIAGNOSTIC_MARKER)[2]
            .partition("\nTraceback ")[0]
        )
        observation = diagnostic["target_observation"]
        scope = json.loads(observation["ordered_messages"][0]["value"])
        scope["query_string_base64"] = _b64(b"wrong=query")
        observation["ordered_messages"][0]["value"] = json.dumps(
            scope, separators=(",", ":"), ensure_ascii=False
        )
        with self.assertRaisesRegex(ValueError, "indexed WebSocket scope values"):
            validate_reference_failure(
                scope_raw_message(**diagnostic), EXPECTED_SCOPE_CASE, ENVIRONMENT
            )

        diagnostic = json.loads(
            scope_raw_message()
            .partition(SCOPE_DIAGNOSTIC_MARKER)[2]
            .partition("\nTraceback ")[0]
        )
        observation = diagnostic["target_observation"]
        scope = json.loads(observation["ordered_messages"][0]["value"])
        scope["headers_base64"][-1][1] = _b64(b"second")
        observation["ordered_messages"][0]["value"] = json.dumps(
            scope, separators=(",", ":"), ensure_ascii=False
        )
        with self.assertRaisesRegex(ValueError, "duplicate header order"):
            validate_reference_failure(
                scope_raw_message(**diagnostic), EXPECTED_SCOPE_CASE, ENVIRONMENT
            )

    def test_reference_must_fail_before_scope_and_candidate_must_reach_it(self):
        for field, value in (
            ("oracle_events", ["lifespan.startup", "websocket.scope:/ws"]),
            ("target_events", ["lifespan.startup"]),
        ):
            diagnostic = json.loads(
                scope_raw_message()
                .partition(SCOPE_DIAGNOSTIC_MARKER)[2]
                .partition("\nTraceback ")[0]
            )
            diagnostic[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_reference_failure(
                    scope_raw_message(**diagnostic), EXPECTED_SCOPE_CASE, ENVIRONMENT
                )

    def test_input_case_must_remain_exact(self):
        case = copy.deepcopy(EXPECTED_CASE)
        case["websocket"]["messages"][0]["value"] = "different"
        with self.assertRaisesRegex(ValueError, "not the exact indexed"):
            validate_reference_failure(raw_message(), case, ENVIRONMENT)

    def test_gate_accepts_either_one_exact_exception_without_a_ratio(self):
        for receipt in EXPECTED_EXCEPTION_RECEIPTS:
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
                "accepted_reference_exceptions": [copy.deepcopy(receipt)],
                "before_parity_identity_sha256": "b" * 64,
                "native_sha256": "c" * 64,
                "exception_policy_id": POLICY_ID,
                "exception_policy_sha256": "d" * 64,
                "performance_pair": None,
            }
            self.assertEqual(
                parity_gate_errors(gate, expected_policy_sha256="d" * 64), []
            )
            self.assertIn(
                "reference_exception_policy_hash_differs_from_frozen_harness",
                parity_gate_errors(gate, expected_policy_sha256="e" * 64),
            )
            gate["accepted_reference_exceptions"][0]["raw_status"] = "passed"
            self.assertIn(
                "reference_exception_receipt_is_unrecognized_or_malformed",
                parity_gate_errors(gate),
            )

    def test_gate_rejects_multiple_exceptions_extra_failures_and_claimed_performance(self):
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
            "accepted_reference_exceptions": [
                copy.deepcopy(EXPECTED_EXCEPTION_RECEIPT),
                copy.deepcopy(EXPECTED_SCOPE_EXCEPTION_RECEIPT),
            ],
            "before_parity_identity_sha256": "b" * 64,
            "native_sha256": "c" * 64,
            "exception_policy_id": POLICY_ID,
            "exception_policy_sha256": "d" * 64,
            "performance_pair": {"ratio": 1.2},
        }
        errors = parity_gate_errors(gate)
        self.assertIn("reference_exception_raw_parity_summary_is_inconsistent", errors)
        self.assertIn("reference_exception_receipt_is_unrecognized_or_malformed", errors)
        self.assertIn("reference_exception_must_not_claim_a_performance_pair", errors)


if __name__ == "__main__":
    unittest.main()
