#!/usr/bin/env python3
"""Focused policy tests for exact macOS Uvicorn oracle timeouts."""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import sys
import unittest

import check_ci_evidence as evidence
from parity_identity import runtime_source_digest, runtime_source_hashes
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
ROOT = Path(__file__).resolve().parents[1]


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


def text_trace_raw_message(**overrides):
    diagnostic = json.loads(raw_message()[len(ERROR_PREFIX):].partition("\nTraceback ")[0])
    diagnostic.update(overrides)
    client_trace = (
        "DEBUG = connection is CONNECTING\n"
        "DEBUG > GET /ws?parity=tls HTTP/1.1\n"
        "DEBUG > Upgrade: websocket\n"
        "DEBUG > EOF\n"
        "DEBUG ! error while receiving data\n"
        "OSError: [Errno 9] Bad file descriptor"
    )
    return (
        SCOPE_ERROR_PREFIX
        + client_trace
        + SCOPE_DIAGNOSTIC_MARKER
        + json.dumps(diagnostic, sort_keys=True)
        + "\nTraceback (most recent call last):\n"
        + "TimeoutError: timed out while waiting for handshake response"
    )


def macos_parity_result():
    manifest, cases, input_paths = evidence.load_contract()
    case = next(item for item in cases if item["case_id"] == CASE_ID)
    dependencies = {}
    for oracle in manifest["oracles"]:
        dependencies[oracle["id"]] = oracle["version"]
        dependencies.update(
            (component["id"], component["version"])
            for component in oracle["components"]
            if "platforms" not in component or "macos" in component["platforms"]
        )
    source_files = runtime_source_hashes(ROOT)
    result = {
        "schema": manifest["result_schema"],
        "status": "failed",
        "summary": {
            "selected": 1, "executed": 1, "passed": 0, "failed": 0,
            "infrastructure_failed": 1, "not_run": 0,
        },
        "cases": [{
            "case_id": CASE_ID,
            "profile": case["profile"],
            "operation": case["operation"],
            "requirements": case["covers"],
            "verification": case.get("verification", "oracle-parity"),
            "fault": case.get("fault"),
            "status": "infrastructure_failed",
            "error": {"class": "ParityError", "message": text_trace_raw_message()},
        }],
        "infrastructure_errors": [],
        "run": {
            "run_id": "unit-macos-reference-fixture",
            "started_at": "fixture",
            "finished_at": "fixture",
            "manifest": {
                "path": "tests/parity/manifest.json",
                "schema": manifest["schema"],
                "sha256": evidence.sha256(evidence.MANIFEST_PATH),
            },
            "inputs": [{
                "path": path.relative_to(ROOT).as_posix(),
                "schema": evidence.source_constant(ROOT / "scripts/run_parity.py", "INPUT_SCHEMA"),
                "sha256": evidence.sha256(path),
            } for path in input_paths],
            "environment": {
                **ENVIRONMENT,
                "python": "3.12.13",
                "rustc": "fixture",
                "dependencies": dependencies,
            },
            "target": {
                "revision": evidence.git_commit(),
                "dirty": False,
                "native_extension": {"path": "target/fixture.dylib", "sha256": "a" * 64},
                "cargo_lock_sha256": evidence.sha256(ROOT / "Cargo.lock"),
                "source_files": source_files,
                "source_sha256": runtime_source_digest(source_files),
            },
            "harness": {
                "runner": "scripts/run_parity.py",
                "runner_sha256": evidence.sha256(ROOT / "scripts/run_parity.py"),
                "identity_helper": {
                    "path": "scripts/parity_identity.py",
                    "sha256": evidence.sha256(ROOT / "scripts/parity_identity.py"),
                },
                "fixture_app": "tests/parity/app.py",
                "fixture_app_sha256": evidence.sha256(ROOT / "tests/parity/app.py"),
                "python_api_probe": {
                    "path": "tests/parity/python_api_probe.py",
                    "sha256": evidence.sha256(ROOT / "tests/parity/python_api_probe.py"),
                },
                "http3_client": None,
            },
            "command": [
                sys.executable,
                "scripts/run_parity.py",
                "--continue-after-macos-reference-wss-handshake-timeout",
            ],
        },
    }
    return result, case


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

    def test_captured_text_timeout_trace_preserves_candidate_only_evidence(self):
        decision = validate_reference_failure(
            text_trace_raw_message(), EXPECTED_CASE, ENVIRONMENT
        )
        self.assertEqual(decision["policy_id"], POLICY_ID)
        self.assertEqual(decision["case_id"], CASE_ID)
        self.assertEqual(decision["candidate_observation"], EXPECTED_CANDIDATE_OBSERVATION)
        self.assertEqual(decision["root_cause"], "unknown")
        self.assertIsNone(decision["performance_pair"])

    def test_ci_checker_accepts_only_the_retained_candidate_success_and_raw_failure(self):
        result, case = macos_parity_result()
        checked = evidence.validate_parity(
            result,
            expected_cases=[case],
            allow_macos_reference_wss_handshake_timeout=True,
        )
        self.assertEqual(checked["status"], "accepted_with_reference_exception")
        self.assertEqual(checked["raw_parity_status"], "failed")
        self.assertEqual(checked["raw_parity_summary"]["infrastructure_failed"], 1)
        self.assertEqual(len(checked["accepted_reference_defects"]), 1)
        self.assertEqual(
            checked["accepted_reference_defects"][0]["policy_id"], POLICY_ID
        )
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_parity(result, expected_cases=[case])

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
