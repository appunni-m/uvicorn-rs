"""Focused tests for the narrow Hypercorn H3 reference exception."""

from __future__ import annotations

import unittest
from pathlib import Path

from benchmark_reference_exceptions import (
    HYPERCORN_H3_FIXED_LINUX_AARCH64,
    HYPERCORN_H3_FIXED_LINUX_X86_64,
    HYPERCORN_H3_FIXED_LINUX_X86_64_UVLOOP,
    HYPERCORN_H3_LARGE_RESPONSE_LINUX_AARCH64,
    HYPERCORN_H3_LARGE_RESPONSE_MACOS_ARM64,
    HYPERCORN_H3_LARGE_RESPONSE_LINUX_X86_64,
    HYPERCORN_H3_SLOW_READER_LINUX_AARCH64,
    HYPERCORN_H3_SLOW_READER_LINUX_X86_64,
    HYPERCORN_H3_SLOW_READER_LINUX_X86_64_UVLOOP,
    HYPERCORN_H3_VALIDATED_ROUTE_LINUX_AARCH64,
    active_reference_exclusions,
    exclusions_by_workload,
    reference_exclusion_metadata_errors,
)
from run_benchmark_categories import expected_rows


ROOT = Path(__file__).resolve().parents[1]
H3_RUNNER = ROOT / "scripts" / "run_h3_category_bench.py"
WORKLOAD = "slow-reader-backpressure"
SERVERS = [
    "hypercorn-asyncio",
    "hypercorn-uvloop",
    "uvicorn-rs-asyncio",
    "uvicorn-rs-uvloop",
]


def matching_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": [WORKLOAD],
        "servers": SERVERS,
        "platform_system": "Linux",
        "machine": "aarch64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_macos_large_response_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": ["large-response"],
        "servers": SERVERS,
        "platform_system": "Darwin",
        "machine": "arm64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_linux_x86_large_response_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": ["large-response"],
        "servers": SERVERS,
        "platform_system": "Linux",
        "machine": "x86_64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_linux_aarch64_large_response_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": ["large-response"],
        "servers": SERVERS,
        "platform_system": "Linux",
        "machine": "aarch64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_linux_aarch64_validated_route_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": ["fastapi-validated-route"],
        "servers": SERVERS,
        "platform_system": "Linux",
        "machine": "aarch64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_linux_x86_fixed_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": ["fixed"],
        "servers": SERVERS,
        "platform_system": "Linux",
        "machine": "x86_64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_linux_x86_fixed_uvloop_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": ["fixed"],
        "servers": ["hypercorn-uvloop", "uvicorn-rs-uvloop"],
        "platform_system": "Linux",
        "machine": "x86_64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_x86_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": [WORKLOAD],
        "servers": SERVERS,
        "platform_system": "Linux",
        "machine": "x86_64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


def matching_x86_uvloop_exclusion(**overrides):
    context = {
        "category": "http3",
        "workloads": [WORKLOAD],
        "servers": ["hypercorn-uvloop", "uvicorn-rs-uvloop"],
        "platform_system": "Linux",
        "machine": "x86_64",
        "hypercorn_version": "0.18.0",
    }
    context.update(overrides)
    return active_reference_exclusions(**context)


class HypercornH3ReferenceExceptionTests(unittest.TestCase):
    def test_only_exact_linux_arm64_full_pair_is_excluded(self):
        self.assertEqual(matching_exclusion(), [HYPERCORN_H3_SLOW_READER_LINUX_AARCH64])

        cases = (
            {"category": "http2"},
            {"workloads": ["protocol-scope"]},
            {"platform_system": "Darwin"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(matching_exclusion(**overrides), [])
        self.assertEqual(
            matching_exclusion(machine="x86_64"),
            [
                HYPERCORN_H3_SLOW_READER_LINUX_X86_64,
                HYPERCORN_H3_SLOW_READER_LINUX_X86_64_UVLOOP,
            ],
        )

    def test_only_exact_linux_x86_64_slow_reader_pair_is_excluded(self):
        self.assertEqual(
            matching_x86_exclusion(),
            [
                HYPERCORN_H3_SLOW_READER_LINUX_X86_64,
                HYPERCORN_H3_SLOW_READER_LINUX_X86_64_UVLOOP,
            ],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["protocol-scope"]},
            {"platform_system": "Darwin"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(matching_x86_exclusion(**overrides), [])
        self.assertEqual(
            matching_x86_exclusion(machine="aarch64"),
            [HYPERCORN_H3_SLOW_READER_LINUX_AARCH64],
        )

    def test_only_exact_linux_x86_64_uvloop_slow_reader_pair_is_excluded(self):
        self.assertEqual(
            matching_x86_uvloop_exclusion(),
            [HYPERCORN_H3_SLOW_READER_LINUX_X86_64_UVLOOP],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["protocol-scope"]},
            {"platform_system": "Darwin"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-uvloop"]},
            {"servers": ["uvicorn-rs-uvloop"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(matching_x86_uvloop_exclusion(**overrides), [])

    def test_only_exact_macos_arm64_large_response_pair_is_excluded(self):
        self.assertEqual(
            matching_macos_large_response_exclusion(),
            [HYPERCORN_H3_LARGE_RESPONSE_MACOS_ARM64],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["protocol-scope"]},
            {"workloads": ["slow-reader-backpressure"]},
            {"platform_system": "Linux"},
            {"machine": "aarch64"},
            {"machine": "x86_64"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(matching_macos_large_response_exclusion(**overrides), [])

    def test_only_exact_linux_x86_64_large_response_pair_is_excluded(self):
        self.assertEqual(
            matching_linux_x86_large_response_exclusion(),
            [HYPERCORN_H3_LARGE_RESPONSE_LINUX_X86_64],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["protocol-scope"]},
            {"platform_system": "Darwin"},
            {"machine": "aarch64"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertNotIn(
                    HYPERCORN_H3_LARGE_RESPONSE_LINUX_X86_64,
                    matching_linux_x86_large_response_exclusion(**overrides),
                )

    def test_only_exact_linux_aarch64_large_response_pair_is_excluded(self):
        self.assertEqual(
            matching_linux_aarch64_large_response_exclusion(),
            [HYPERCORN_H3_LARGE_RESPONSE_LINUX_AARCH64],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["fixed"]},
            {"platform_system": "Darwin"},
            {"machine": "x86_64"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertNotIn(
                    HYPERCORN_H3_LARGE_RESPONSE_LINUX_AARCH64,
                    matching_linux_aarch64_large_response_exclusion(**overrides),
                )

    def test_only_exact_linux_aarch64_validated_route_pair_is_excluded(self):
        self.assertEqual(
            matching_linux_aarch64_validated_route_exclusion(),
            [HYPERCORN_H3_VALIDATED_ROUTE_LINUX_AARCH64],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["fixed"]},
            {"platform_system": "Darwin"},
            {"machine": "x86_64"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertNotIn(
                    HYPERCORN_H3_VALIDATED_ROUTE_LINUX_AARCH64,
                    matching_linux_aarch64_validated_route_exclusion(**overrides),
                )

    def test_linux_aarch64_validated_route_plan_keeps_all_candidate_repetitions(self):
        workload = "fastapi-validated-route"
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=[workload],
        )
        exclusions = matching_linux_aarch64_validated_route_exclusion()
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=[workload],
            excluded_servers_by_workload=exclusions_by_workload(exclusions),
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 15)
        self.assertEqual(
            planned - admitted,
            {(workload, "hypercorn-asyncio", number) for number in range(1, 6)},
        )
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {(workload, "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )

    def test_only_exact_linux_x86_64_fixed_pair_is_excluded(self):
        self.assertEqual(
            matching_linux_x86_fixed_exclusion(),
            [
                HYPERCORN_H3_FIXED_LINUX_X86_64_UVLOOP,
                HYPERCORN_H3_FIXED_LINUX_X86_64,
            ],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["protocol-scope"]},
            {"platform_system": "Darwin"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-asyncio"]},
            {"servers": ["uvicorn-rs-asyncio"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertEqual(matching_linux_x86_fixed_exclusion(**overrides), [])
        self.assertEqual(
            matching_linux_x86_fixed_exclusion(machine="aarch64"),
            [HYPERCORN_H3_FIXED_LINUX_AARCH64],
        )

    def test_only_exact_linux_x86_64_fixed_uvloop_pair_is_excluded(self):
        self.assertEqual(
            matching_linux_x86_fixed_uvloop_exclusion(),
            [HYPERCORN_H3_FIXED_LINUX_X86_64_UVLOOP],
        )

        cases = (
            {"category": "http2"},
            {"workloads": ["slow-reader-backpressure"]},
            {"platform_system": "Darwin"},
            {"machine": "aarch64"},
            {"hypercorn_version": "0.18.1"},
            {"servers": ["hypercorn-uvloop"]},
            {"servers": ["uvicorn-rs-uvloop"]},
            {"enabled": False},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertNotIn(
                    HYPERCORN_H3_FIXED_LINUX_X86_64_UVLOOP,
                    matching_linux_x86_fixed_uvloop_exclusion(**overrides),
                )

    def test_plan_skips_only_the_failed_reference_and_keeps_candidate_repetitions(self):
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=[WORKLOAD],
        )
        exclusion_map = exclusions_by_workload(matching_exclusion())
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=[WORKLOAD],
            excluded_servers_by_workload=exclusion_map,
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 15)
        self.assertEqual(planned - admitted, {
            (WORKLOAD, "hypercorn-asyncio", number) for number in range(1, 6)
        })
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {(WORKLOAD, "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )

    def test_x86_plan_skips_only_the_failed_reference_and_keeps_candidate_repetitions(self):
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=[WORKLOAD],
        )
        exclusion_map = exclusions_by_workload(matching_x86_exclusion())
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=[WORKLOAD],
            excluded_servers_by_workload=exclusion_map,
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 10)
        self.assertEqual(planned - admitted, {
            (WORKLOAD, server, number)
            for server in ("hypercorn-asyncio", "hypercorn-uvloop")
            for number in range(1, 6)
        })
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {(WORKLOAD, "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-uvloop"},
            {(WORKLOAD, "uvicorn-rs-uvloop", number) for number in range(1, 6)},
        )

    def test_macos_plan_keeps_every_candidate_repetition(self):
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["large-response"],
        )
        exclusions = matching_macos_large_response_exclusion()
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["large-response"],
            excluded_servers_by_workload=exclusions_by_workload(exclusions),
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 15)
        self.assertEqual(planned - admitted, {
            ("large-response", "hypercorn-asyncio", number)
            for number in range(1, 6)
        })
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {("large-response", "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )

    def test_linux_x86_large_response_plan_keeps_every_candidate_repetition(self):
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["large-response"],
        )
        exclusions = matching_linux_x86_large_response_exclusion()
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["large-response"],
            excluded_servers_by_workload=exclusions_by_workload(exclusions),
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 15)
        self.assertEqual(
            planned - admitted,
            {("large-response", "hypercorn-asyncio", number) for number in range(1, 6)},
        )
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {("large-response", "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )

    def test_linux_aarch64_large_response_plan_keeps_every_candidate_repetition(self):
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["large-response"],
        )
        exclusions = matching_linux_aarch64_large_response_exclusion()
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["large-response"],
            excluded_servers_by_workload=exclusions_by_workload(exclusions),
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 15)
        self.assertEqual(
            planned - admitted,
            {("large-response", "hypercorn-asyncio", number) for number in range(1, 6)},
        )
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {("large-response", "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )

    def test_linux_x86_fixed_plan_keeps_every_candidate_repetition(self):
        planned = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["fixed"],
        )
        exclusions = matching_linux_x86_fixed_exclusion()
        admitted = expected_rows(
            H3_RUNNER,
            "http3",
            SERVERS,
            5,
            selected_workloads=["fixed"],
            excluded_servers_by_workload=exclusions_by_workload(exclusions),
        )

        self.assertEqual(len(planned), 20)
        self.assertEqual(len(admitted), 10)
        self.assertEqual(
            planned - admitted,
            {
                ("fixed", server, number)
                for server in ("hypercorn-asyncio", "hypercorn-uvloop")
                for number in range(1, 6)
            },
        )
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-asyncio"},
            {("fixed", "uvicorn-rs-asyncio", number) for number in range(1, 6)},
        )
        self.assertEqual(
            {row for row in admitted if row[1] == "uvicorn-rs-uvloop"},
            {("fixed", "uvicorn-rs-uvloop", number) for number in range(1, 6)},
        )

    def test_metadata_accepts_only_the_recorded_context_and_server_map(self):
        exclusions = matching_exclusion()
        metadata = {
            "workloads": [WORKLOAD],
            "servers": {name: {} for name in SERVERS},
            "platform_system": "Linux",
            "machine": "aarch64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["machine"] = "x86_64"
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )
        metadata["machine"] = "x86_64"
        metadata["excluded_servers_by_workload"] = {}
        self.assertIn(
            "reference_exclusion_server_map_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_x86_metadata_accepts_only_the_recorded_context_and_server_map(self):
        exclusions = matching_x86_exclusion()
        metadata = {
            "workloads": [WORKLOAD],
            "servers": {name: {} for name in SERVERS},
            "platform_system": "Linux",
            "machine": "x86_64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["machine"] = "aarch64"
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )
        metadata["machine"] = "aarch64"
        metadata["excluded_servers_by_workload"] = {}
        self.assertIn(
            "reference_exclusion_server_map_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_macos_metadata_accepts_only_the_recorded_context_and_server_map(self):
        exclusions = matching_macos_large_response_exclusion()
        metadata = {
            "workloads": ["large-response"],
            "servers": {name: {} for name in SERVERS},
            "platform_system": "Darwin",
            "machine": "arm64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["platform_system"] = "Linux"
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )
        metadata["platform_system"] = "Darwin"
        metadata["reference_exclusions"] = []
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_linux_x86_large_response_metadata_accepts_only_recorded_context(self):
        exclusions = matching_linux_x86_large_response_exclusion()
        metadata = {
            "workloads": ["large-response"],
            "servers": {name: {} for name in SERVERS},
            "platform_system": "Linux",
            "machine": "x86_64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["machine"] = "aarch64"
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_linux_aarch64_large_response_metadata_accepts_only_recorded_context(self):
        exclusions = matching_linux_aarch64_large_response_exclusion()
        metadata = {
            "workloads": ["large-response"],
            "servers": {name: {} for name in SERVERS},
            "platform_system": "Linux",
            "machine": "aarch64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["machine"] = "x86_64"
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )
        metadata["machine"] = "aarch64"
        metadata["excluded_servers_by_workload"] = {}
        self.assertIn(
            "reference_exclusion_server_map_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_linux_x86_fixed_metadata_accepts_only_recorded_context(self):
        exclusions = matching_linux_x86_fixed_exclusion()
        metadata = {
            "workloads": ["fixed"],
            "servers": {name: {} for name in SERVERS},
            "platform_system": "Linux",
            "machine": "x86_64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["workloads"] = ["slow-reader-backpressure"]
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_linux_x86_fixed_uvloop_metadata_accepts_only_recorded_context(self):
        exclusions = matching_linux_x86_fixed_uvloop_exclusion()
        metadata = {
            "workloads": ["fixed"],
            "servers": {name: {} for name in ("hypercorn-uvloop", "uvicorn-rs-uvloop")},
            "platform_system": "Linux",
            "machine": "x86_64",
            "hypercorn": "0.18.0",
            "reference_exclusions": exclusions,
            "excluded_servers_by_workload": exclusions_by_workload(exclusions),
        }
        self.assertEqual(reference_exclusion_metadata_errors("http3", metadata), [])

        metadata["servers"] = {"hypercorn-uvloop": {}}
        self.assertIn(
            "reference_exclusion_receipt_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )
        metadata["servers"] = {
            "hypercorn-uvloop": {},
            "uvicorn-rs-uvloop": {},
        }
        metadata["workloads"] = ["fixed"]
        metadata["excluded_servers_by_workload"] = {}
        self.assertIn(
            "reference_exclusion_server_map_unrecognized_or_context_mismatched",
            reference_exclusion_metadata_errors("http3", metadata),
        )

    def test_other_categories_reject_any_reference_exclusion(self):
        self.assertEqual(
            reference_exclusion_metadata_errors(
                "http2",
                {"reference_exclusions": [{}], "excluded_servers_by_workload": {}},
            ),
            ["reference_exclusions_are_not_allowed_for_this_category"],
        )


if __name__ == "__main__":
    unittest.main()
