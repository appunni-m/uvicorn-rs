"""Focused tests for the narrow Hypercorn H3 reference exception."""

from __future__ import annotations

import unittest
from pathlib import Path

from benchmark_reference_exceptions import (
    HYPERCORN_H3_SLOW_READER_LINUX_AARCH64,
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


class HypercornH3ReferenceExceptionTests(unittest.TestCase):
    def test_only_exact_linux_arm64_full_pair_is_excluded(self):
        self.assertEqual(matching_exclusion(), [HYPERCORN_H3_SLOW_READER_LINUX_AARCH64])

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
                self.assertEqual(matching_exclusion(**overrides), [])

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
        metadata["machine"] = "aarch64"
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
