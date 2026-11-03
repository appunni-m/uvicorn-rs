#!/usr/bin/env python3
"""Fail fast on native manifest/coverage-validator drift, without running servers."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from check_ci_evidence import EvidenceError, validate_native_case_contracts


class NativeFaultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "tests/native-core/manifest.json"
        cls.cases = json.loads(path.read_text())["cases"]
        cls.fault = next(c for c in cls.cases if c.get("verification") == "fault-contract")

    def test_all_indexed_native_contracts_are_registered(self):
        self.assertEqual(validate_native_case_contracts(self.cases), [c["id"] for c in self.cases])

    def test_rejects_unknown_fault_points_and_wrong_bindings(self):
        for field, value in (("operation", "unknown-operation"), ("scenario", "wrong-scenario"),
                             ("verification", "unknown-verification"),
                             ("fault", {"point": "unknown-fault"}),
                             ("fault", {"point": self.fault["fault"]["point"], "extra": True}),
                             ("fault", None)):
            with self.subTest(field=field, value=value):
                case = deepcopy(self.fault)
                case[field] = value
                with self.assertRaises(EvidenceError):
                    validate_native_case_contracts([case])

    def test_rejects_invalid_indexes(self):
        for cases in ([], None, [self.fault, self.fault], [{}], [False]):
            with self.subTest(cases=cases), self.assertRaises(EvidenceError):
                validate_native_case_contracts(cases)

    def test_nonfault_contract_cannot_smuggle_in_a_fault(self):
        case = {**self.fault, "verification": "target-contract"}
        with self.assertRaises(EvidenceError):
            validate_native_case_contracts([case])


if __name__ == "__main__":
    unittest.main()
