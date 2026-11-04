#!/usr/bin/env python3
"""Check fresh-checkout coverage replay without executing project servers."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import check_ci_evidence as evidence
from coverage_toolchain import ToolchainError, capture_coverage_tools, validate_coverage_tools


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tools_fixture() -> dict[str, dict[str, str]]:
    return {name: {"path": f"/producer/{name}", "sha256": str(index) * 64, "version": f"{name} fixture"}
            for index, name in enumerate(("rustc", "cargo", "cargo_llvm_cov", "llvm_cov", "llvm_profdata"), 1)}


class CoverageReplayTests(unittest.TestCase):
    def test_physical_lines_union_overlapping_function_spans(self) -> None:
        regions = {
            "outer": {"file": "src/lib.rs", "start": {"line": 1, "column": 1},
                      "end": {"line": 3, "column": 1}, "covered": True},
            "closure": {"file": "src/lib.rs", "start": {"line": 2, "column": 1},
                        "end": {"line": 4, "column": 1}, "covered": True},
        }
        # Two function spans each have two lines, but share physical line 2.
        text = f"SF:{ROOT / 'src/lib.rs'}\nDA:1,1\nDA:2,2\nDA:3,1\nend_of_record\n"
        with patch.object(evidence, "EXECUTABLE_SOURCE_SET", ("src/lib.rs",)):
            actual = evidence.validate_llvm_physical_lines(evidence.parse_llvm_lcov_lines(text), regions)
        self.assertEqual(actual['src/lib.rs'], {
            'lcov_lines': 3, 'region_span_lines': 3,
            'lcov_covered_lines': 3, 'covered_region_span_lines': 3,
        })

    def test_physical_line_replay_rejects_changed_sets_with_equal_totals(self) -> None:
        regions = {
            "covered": {"file": "src/lib.rs", "start": {"line": 1, "column": 1},
                        "end": {"line": 3, "column": 1}, "covered": True},
            "uncovered": {"file": "src/lib.rs", "start": {"line": 3, "column": 1},
                          "end": {"line": 4, "column": 1}, "covered": False},
        }
        with patch.object(evidence, "EXECUTABLE_SOURCE_SET", ("src/lib.rs",)):
            for records in ({1: 1, 2: 1, 4: 0}, {1: 1, 2: 0, 3: 1}, {}):
                with self.subTest(records=records), self.assertRaises(evidence.EvidenceError):
                    evidence.validate_llvm_physical_lines({"src/lib.rs": records}, regions)
            with self.assertRaises(evidence.EvidenceError):
                evidence.validate_llvm_physical_lines({}, regions)
            with self.assertRaises(evidence.EvidenceError):
                evidence.validate_llvm_physical_lines({"src/lib.rs": {1: 1, 2: 1, 3: 0},
                                                      "src/upload_trace.rs": {1: 1}}, regions)

    def test_physical_line_parser_rejects_duplicate_and_malformed_counters(self) -> None:
        source = f"SF:{ROOT / 'src/lib.rs'}\n"
        for suffix in ("DA:1,1\nDA:1,2\n", "DA:1,-1\n", "DA:0,1\n", "DA:a,1\n",
                       "DA:1\n", f"DA:1,1\n{source}DA:2,1\n"):
            with self.subTest(suffix=suffix), self.assertRaises(evidence.EvidenceError):
                evidence.parse_llvm_lcov_lines(source + suffix)

    def test_physical_line_replay_rejects_llvm_diagnostics(self) -> None:
        for returncode, stderr in ((1, "profile mismatch"), (0, "warning: stale profile")):
            result = subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)
            with patch.object(evidence.subprocess, "run", return_value=result):
                with self.assertRaises(evidence.EvidenceError):
                    evidence.replay_llvm_physical_lines(Path("profile"), llvm_cov=Path("llvm-cov"),
                                                        binaries=(Path("one"), Path("two")), regions={})

    def test_declared_native_tls_directory_binds_every_fixture_file(self) -> None:
        _, _, input_paths = evidence.load_contract()
        selected = evidence.expected_source_hashes(ROOT / "scripts/run_unified_coverage.py", input_paths)
        directory = "tests/native-core/tls"
        expected = {path.relative_to(ROOT).as_posix(): digest(path)
                    for path in (ROOT / directory).rglob("*") if path.is_file()}
        self.assertTrue(expected)
        self.assertNotIn(directory, selected)
        self.assertEqual({name: value for name, value in selected.items()
                          if name.startswith(directory + "/")}, expected)

    def test_report_directory_binds_nested_and_non_rust_inputs(self) -> None:
        (ROOT / "target").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="coverage-inputs-", dir=ROOT / "target") as temporary:
            directory = Path(temporary)
            nested = directory / "nested" / "fixture.pem"
            nested.parent.mkdir()
            nested.write_bytes(b"first fixture")
            hidden = directory / ".fixture.json"
            hidden.write_bytes(b"{}")
            relative = directory.relative_to(ROOT).as_posix()
            original_constant = evidence.source_constant

            def source_constant(path: Path, name: str):
                return [relative] if name == "REPORT_INPUT_PATHS" else original_constant(path, name)

            with patch.object(evidence, "source_constant", side_effect=source_constant):
                def inputs():
                    selected = evidence.expected_source_hashes(ROOT / "scripts/run_unified_coverage.py", [])
                    return {name: value for name, value in selected.items() if name.startswith(relative + "/")}

                before = inputs()
                self.assertEqual(before, {path.relative_to(ROOT).as_posix(): digest(path)
                                          for path in (nested, hidden)})
                nested.write_bytes(b"changed fixture")
                self.assertNotEqual(inputs(), before)
                hidden.unlink()
                self.assertNotIn(hidden.relative_to(ROOT).as_posix(), inputs())
                added = directory / "added.txt"
                added.write_bytes(b"new input")
                self.assertEqual(inputs()[added.relative_to(ROOT).as_posix()], digest(added))

    def test_missing_declared_report_input_is_rejected(self) -> None:
        original_constant = evidence.source_constant

        def source_constant(path: Path, name: str):
            return ["target/missing-coverage-input/fixture.pem"] if name == "REPORT_INPUT_PATHS" else original_constant(path, name)

        with patch.object(evidence, "source_constant", side_effect=source_constant):
            with self.assertRaisesRegex(evidence.EvidenceError, "missing declared report input"):
                evidence.expected_source_hashes(ROOT / "scripts/run_unified_coverage.py", [])

    def test_relocated_exact_llvm_does_not_require_build_tools(self) -> None:
        expected = tools_fixture()
        actual = {name: {**expected[name], "path": f"/reviewer/{name}"}
                  for name in ("llvm_cov", "llvm_profdata")}
        paths = {name: Path(row["path"]) for name, row in actual.items()}
        before = deepcopy(expected)
        with patch("coverage_toolchain.capture_coverage_tools", return_value=(actual, paths)) as capture:
            self.assertEqual(validate_coverage_tools(expected, replay=True), tuple(paths.values()))
        capture.assert_called_once_with(include_build_tools=False)
        self.assertEqual(expected, before)

    def test_replay_rejects_changed_llvm_bytes_or_version(self) -> None:
        expected = tools_fixture()
        for tool in ("llvm_cov", "llvm_profdata"):
            for field, value in (("sha256", "0" * 64), ("version", "other LLVM")):
                with self.subTest(tool=tool, field=field):
                    actual = deepcopy(expected)
                    actual[tool][field] = value
                    with patch("coverage_toolchain.capture_coverage_tools", return_value=(actual, {})):
                        with self.assertRaises(ToolchainError):
                            validate_coverage_tools(expected, replay=True)

    def test_live_validation_still_requires_exact_full_toolchain(self) -> None:
        expected = tools_fixture()
        actual = deepcopy(expected)
        actual["cargo"]["path"] = "/elsewhere/cargo"
        with patch("coverage_toolchain.capture_coverage_tools", return_value=(actual, {})):
            with self.assertRaises(ToolchainError):
                validate_coverage_tools(expected)

    def test_replay_rejects_malformed_original_receipts(self) -> None:
        for field, value in (("path", "relative/tool"), ("sha256", "invalid"), ("version", "")):
            with self.subTest(field=field):
                expected = tools_fixture()
                expected["cargo"][field] = value
                with self.assertRaises(ToolchainError):
                    validate_coverage_tools(expected, replay=True)

    def test_offline_objects_are_required_and_hash_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            build = {"native_extension": "python/original.so", "native_runner": "target/native_core_contracts"}
            for key, data in (("native_extension", b"extension fixture"), ("native_runner", b"runner fixture")):
                original = root / build[key]
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(data)
                build[f"{key}_sha256"] = digest(original)
            with patch.object(evidence, "ROOT", root):
                # Existing build outputs cannot substitute for a missing raw snapshot.
                with self.assertRaises(evidence.EvidenceError):
                    evidence.resolve_coverage_binaries(build, "target/raw/run", offline=True)
                objects = root / "target/raw/run/coverage-objects"
                objects.mkdir(parents=True)
                retained = (objects / "native-extension", objects / "native_core_contracts")
                for key, destination in zip(("native_extension", "native_runner"), retained):
                    shutil.copy2(root / build[key], destination)
                    (root / build[key]).unlink()
                self.assertEqual(evidence.resolve_coverage_binaries(build, "target/raw/run", offline=True), retained)
                for path in retained:
                    original = path.read_bytes()
                    path.write_bytes(b"changed object")
                    with self.assertRaises(evidence.EvidenceError):
                        evidence.resolve_coverage_binaries(build, "target/raw/run", offline=True)
                    path.write_bytes(original)
                with self.assertRaises(evidence.EvidenceError):
                    evidence.resolve_coverage_binaries(build, "../escape", offline=True)


def smoke() -> None:
    """Export actual retained Rust objects after deleting their original paths."""
    receipts, _ = capture_coverage_tools()
    (ROOT / "target").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coverage-replay-", dir=ROOT / "target") as temporary:
        root = Path(temporary)
        objects = root / "raw/run/coverage-objects"
        objects.mkdir(parents=True)
        build: dict[str, str] = {}
        profiles = []
        for index, (key, retained_name) in enumerate((("native_extension", "native-extension"),
                                                       ("native_runner", "native_core_contracts"))):
            source = root / f"fixture_{index}.rs"
            source.write_text(f'#[inline(never)] fn observed_{index}() -> u32 {{ {index + 1} }}\n'
                              f'fn main() {{ let read = || observed_{index}(); println!("{{}}", read()); }}\n')
            binary = root / f"original_{index}" / retained_name
            binary.parent.mkdir()
            subprocess.run(["rustc", "--edition=2021", "-C", "instrument-coverage", str(source),
                            "-o", str(binary)], check=True, capture_output=True, timeout=60)
            profile = root / f"fixture_{index}.profraw"
            subprocess.run([str(binary)], env={**os.environ, "LLVM_PROFILE_FILE": str(profile)},
                           check=True, capture_output=True, timeout=10)
            profiles.append(profile)
            build[key] = str(binary.relative_to(root))
            build[f"{key}_sha256"] = digest(binary)
            shutil.copy2(binary, objects / retained_name)
            binary.unlink()
        with patch.object(evidence, "ROOT", root):
            binaries = evidence.resolve_coverage_binaries(build, "raw/run", offline=True)
            llvm_cov, llvm_profdata = validate_coverage_tools(receipts, replay=True)
            merged = root / "aggregate.profdata"
            subprocess.run([str(llvm_profdata), "merge", "-sparse", "-o", str(merged),
                            *(str(profile) for profile in profiles)], check=True, capture_output=True, timeout=30)
            exported = evidence.export_llvm_profile(merged, label="retained-object smoke", llvm_cov=llvm_cov,
                                                    binaries=binaries)
            paths = tuple(f"fixture_{index}.rs" for index in range(2))
            regions = {path: {"file": path, "start": {"line": 1, "column": 1},
                              "end": {"line": 3, "column": 1}, "covered": True}
                       for path in paths}
            with patch.object(evidence, "PRODUCTION_SOURCE_SET", paths), \
                 patch.object(evidence, "EXECUTABLE_SOURCE_SET", paths), \
                 patch.object(evidence, "NO_COUNTER_SOURCE_SET", ()):
                physical = evidence.replay_llvm_physical_lines(merged, llvm_cov=llvm_cov,
                                                              binaries=binaries, regions=regions)
        raw_lines = [row["summary"]["lines"]["count"] for row in exported["data"][0]["files"]]
        if raw_lines != [3, 3] or any(row["lcov_lines"] != 2 for row in physical.values()):
            raise AssertionError(f"overlapping function-line fixture differs: {raw_lines}, {physical}")
        totals = exported["data"][0]["totals"]["regions"]
        if totals["count"] <= 0 or totals["covered"] != totals["count"]:
            raise AssertionError(f"retained fixture regions were not fully measured: {totals}")
        print(json.dumps({"status": "passed", "scope": "tooling fixture, not server coverage",
                          "objects": 2, "original_objects_removed": True, "regions": totals,
                          "raw_function_lines": raw_lines, "physical_lines": physical}, sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1:] == ["--smoke"]:
        smoke()
    else:
        unittest.main()
