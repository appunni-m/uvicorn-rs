"""Exercise experiment admission without building or timing any server."""

import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

import analyze_peer_read_comparison as analyzer


class ComparisonAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        pair = {"workload": "fastapi-fixed", "loop": "asyncio", "concurrency": 64,
                "repeat": 1, "variant_order": ["fresh", "reuse"]}
        self.plan = {"pairs": [dict(pair, repeat=i) for i in range(1, 4)],
                     "planned_pairs": 3, "duration_seconds": 5, "warmup_seconds": 1,
                     "seed": 20261103}
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_text(json.dumps(self.plan))
        self.execution = {"plan_sha256": analyzer.sha(self.plan_path), "complete": True,
            "variants": {v: {"git_commit": v, "runtime_files": {"src/lib.rs": v},
                              "native_sha256": v} for v in ("fresh", "reuse")}, "attempts": []}
        for index, planned in enumerate(self.plan["pairs"], 1):
            for variant in planned["variant_order"]:
                report = {"metadata": {"diagnostic_only": False,
                    "workloads": [planned["workload"]], "repetitions": 1,
                    "identity_stable": True, "dirty_target": False, "rustc": "fixture",
                    "modified_or_unrecorded_dependencies": [], "git_revision": variant,
                    "identity_before": {"source_files": {"src/lib.rs": variant}},
                    "identity_after": {"source_files": {"src/lib.rs": variant}},
                    "duration_seconds": 5, "warmup_seconds": 1, "seed": 20261103,
                    "python_environment": {"python": "fixture"}},
                    "rows": [{"server": "uvicorn-rs-asyncio", "workload": "fastapi-fixed",
                        "concurrency": 64, "timing_valid": True, "failures": 0,
                        "requests_per_second": 100 if variant == "fresh" else 110,
                        "measurement_identity": {"native_sha256_before": variant,
                                                 "native_sha256_after": variant}}]}
                path = self.root / f"{index}-{variant}.json"
                path.write_text(json.dumps(report))
                self.execution["attempts"].append({"pair": index, **planned, "variant": variant,
                    "report_file": path.name, "report_sha256": analyzer.sha(path), "returncode": 0})

    def edit_first(self, mutate, rehash=True):
        attempt = self.execution["attempts"][0]
        path = self.root / attempt["report_file"]
        report = json.loads(path.read_text())
        mutate(report)
        path.write_text(json.dumps(report))
        if rehash:
            attempt["report_sha256"] = analyzer.sha(path)

    def analyze(self):
        execution_path = self.root / "execution.json"
        execution_path.write_text(json.dumps(self.execution))
        output = self.root / "analysis.json"
        with patch("sys.argv", ["analyzer", str(execution_path), "--output", str(output)]):
            with contextlib.redirect_stdout(io.StringIO()):
                analyzer.main()
        return json.loads(output.read_text())

    def test_complete_adjacent_pairs(self):
        group = self.analyze()["groups"]["fastapi-fixed/asyncio"]
        self.assertTrue(group["minimum_three_valid_pairs"])
        self.assertEqual(group["metrics"]["requests_per_second"]["paired_reuse_over_fresh"]["median"], 1.1)

    def test_changed_native_rejects_whole_pair(self):
        self.edit_first(lambda r: r["rows"][0]["measurement_identity"].update(native_sha256_after="drift"))
        result = self.analyze()
        self.assertFalse(result["groups"]["fastapi-fixed/asyncio"]["minimum_three_valid_pairs"])
        self.assertEqual(result["groups"]["fastapi-fixed/asyncio"]["valid_pairs"], [2, 3])
        self.assertIn("missing_or_changed_sample_native_identity", result["rejected_attempts"][0]["reasons"])

    def test_noise_is_retained_without_replacement(self):
        self.edit_first(lambda r: r["rows"][0].update(timing_valid=False, timing_invalid_reasons=["host_contention"]))
        result = self.analyze()
        self.assertEqual(result["groups"]["fastapi-fixed/asyncio"]["planned_pairs"], 3)
        self.assertIn("host_contention", result["rejected_attempts"][0]["reasons"])

    def test_source_drift_and_modified_artifacts_are_rejected(self):
        self.edit_first(lambda r: r["metadata"]["identity_before"]["source_files"].update({"src/lib.rs": "drift"}))
        with self.assertRaises(AssertionError):
            self.analyze()

    def test_artifact_digest_is_checked(self):
        self.edit_first(lambda r: r.update(extra="modified"), rehash=False)
        with self.assertRaises(AssertionError):
            self.analyze()

    def test_frozen_plan_covers_cells_and_preserves_order(self):
        source = Path(__file__).resolve().parents[1] / "tests/performance/peer-read-comparison.json"
        plan = json.loads(source.read_text())
        self.assertEqual(len(plan["pairs"]), 40)
        cells = {(p["workload"], p["loop"]) for p in plan["pairs"]}
        self.assertEqual(len(cells), 8)
        for workload, loop in cells:
            rows = [p for p in plan["pairs"] if (p["workload"], p["loop"]) == (workload, loop)]
            self.assertEqual({p["repeat"] for p in rows}, set(range(1, 6)))
            self.assertIn(sum(p["variant_order"] == ["fresh", "reuse"] for p in rows), (2, 3))
        self.assertEqual(len(set(plan["case_ids"])), 13)

    def test_focused_dispatch_cannot_start_full_matrix_jobs(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github/workflows/benchmark-categories.yml").read_text())
        event = SimpleNamespace(head_commit=SimpleNamespace(message="normal change"))
        for mode in ("full", "focused-fastapi-match", "focused-fastapi-stage", "focused-h2",
                     "focused-h3", "peer-read-comparison", "future-focused-mode"):
            for name in ("categories", "aggregate", "update-docs"):
                expression = workflow["jobs"][name]["if"].removeprefix("${{").removesuffix("}}")
                expression = re.sub(r"!(?!=)", "not ", expression).replace("&&", " and ").replace("||", " or ")
                environment = {
                    "github": SimpleNamespace(event_name="workflow_dispatch", event=event,
                        ref="refs/heads/main", repository="appunni-m/uvicorn-rs"),
                    "inputs": SimpleNamespace(run_mode=mode), "always": lambda: True,
                    "contains": lambda text, part: part in text,
                    "needs": SimpleNamespace(categories=SimpleNamespace(result="success")),
                }
                self.assertEqual(bool(eval(expression, {"__builtins__": {}}, environment)), mode == "full", (mode, name))


if __name__ == "__main__":
    unittest.main()
