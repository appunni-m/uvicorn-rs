"""Contract tests for the live, input-only ASGI parity suite."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.run_parity import (
    FIXTURES,
    ParityError,
    RESULT_SCHEMA,
    load_contract,
    validate_result_shape,
)


class ParityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="uvicorn-rs-parity-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.fixture_root = Path(self.temporary.name) / "parity"
        shutil.copytree(FIXTURES, self.fixture_root)
        self.manifest_path = self.fixture_root / "manifest.json"

    def load(self):
        return load_contract(self.manifest_path, self.fixture_root)

    def read_json(self, path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, value) -> None:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_active_inputs_are_indexed_and_cover_every_operation_and_profile(self) -> None:
        manifest, inputs, paths = self.load()
        self.assertEqual(len(paths), 5)
        self.assertEqual(len(inputs["cases"]), 19)
        self.assertEqual(
            {case["profile"] for case in inputs["cases"]},
            {profile["id"] for profile in manifest["profiles"]},
        )
        self.assertEqual(
            {case["operation"] for case in inputs["cases"]},
            {operation["id"] for operation in manifest["operations"]},
        )
        self.assertEqual(
            manifest["inputs"],
            [str(path.relative_to(self.fixture_root)) for path in paths],
        )

    def test_rejects_unknown_manifest_fields(self) -> None:
        manifest = self.read_json(self.manifest_path)
        manifest["untracked_policy"] = "must fail closed"
        self.write_json(self.manifest_path, manifest)
        with self.assertRaisesRegex(ParityError, "manifest fields differ"):
            self.load()

    def test_rejects_expected_output_embedded_in_inputs(self) -> None:
        input_path = self.fixture_root / "inputs" / "http1.json"
        document = self.read_json(input_path)
        document["cases"][0]["expected_status"] = 200
        self.write_json(input_path, document)
        with self.assertRaisesRegex(ParityError, "may not contain observed results"):
            self.load()

    def test_rejects_unindexed_active_input(self) -> None:
        extra = self.fixture_root / "inputs" / "unindexed.json"
        extra.write_text('{"schema":"uvicorn-rs-parity/input@2","cases":[]}\n', encoding="utf-8")
        with self.assertRaisesRegex(ParityError, "input index differs from files"):
            self.load()

    def test_rejects_duplicate_case_ids_across_input_files(self) -> None:
        source = self.read_json(self.fixture_root / "inputs" / "http1.json")
        destination_path = self.fixture_root / "inputs" / "http2.json"
        destination = self.read_json(destination_path)
        duplicate = dict(source["cases"][0])
        duplicate["profile"] = "http2"
        duplicate["operation"] = "http.scope-and-body"
        duplicate["covers"] = ["http.scope-and-body"]
        destination["cases"].append(duplicate)
        self.write_json(destination_path, destination)
        with self.assertRaisesRegex(ParityError, "duplicate case ID"):
            self.load()

    def test_result_validator_rejects_missing_selected_case(self) -> None:
        manifest, inputs, _ = self.load()
        cases = inputs["cases"]
        recorded = [
            {
                "case_id": case["case_id"],
                "profile": case["profile"],
                "operation": case["operation"],
                "requirements": case["covers"],
                "status": "passed",
            }
            for case in cases[:-1]
        ]
        result = {
            "schema": RESULT_SCHEMA,
            "run": {
                "run_id": "contract-test",
                "started_at": "2026-10-02T00:00:00Z",
                "finished_at": "2026-10-02T00:00:01Z",
                "manifest": {
                    "path": "tests/parity/manifest.json",
                    "schema": manifest["schema"],
                    "sha256": "0" * 64,
                },
                "inputs": [
                    {"path": f"tests/parity/{path}", "schema": "uvicorn-rs-parity/input@2", "sha256": "0" * 64}
                    for path in manifest["inputs"]
                ],
                "environment": {
                    "python": "3.12.13",
                    "platform": "test-platform",
                    "machine": "test-machine",
                    "rustc": "rustc test",
                    "dependencies": {
                        dependency["id"]: dependency["version"]
                        for oracle in manifest["oracles"]
                        for dependency in [{"id": oracle["id"], "version": oracle["version"]}, *oracle["components"]]
                    },
                },
                "target": {
                    "revision": "test-revision",
                    "dirty": False,
                    "native_extension": {"path": "test-extension", "sha256": "0" * 64},
                    "cargo_lock_sha256": "0" * 64,
                },
                "harness": {
                    "runner": "scripts/run_parity.py",
                    "runner_sha256": "0" * 64,
                    "fixture_app": "tests/parity/app.py",
                    "fixture_app_sha256": "0" * 64,
                    "http3_client": None,
                },
                "command": ["python", "scripts/run_parity.py"],
            },
            "status": "completed",
            "summary": {
                "selected": len(cases),
                "executed": len(cases),
                "passed": len(cases),
                "failed": 0,
                "not_run": 0,
                "infrastructure_failed": 0,
            },
            "cases": recorded,
            "infrastructure_errors": [],
        }
        with self.assertRaisesRegex(ParityError, "do not exactly match selected input"):
            validate_result_shape(result, cases, manifest)


if __name__ == "__main__":
    unittest.main()
