#!/usr/bin/env python3
"""Exercise platform workflow command construction without running parity."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PlatformShellTests(unittest.TestCase):
    def test_strict_and_windows_commands_under_nounset(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        start = workflow.index("          run_platform_parity() {")
        end = workflow.index("\n          }", start) + len("\n          }")
        function = "\n".join(line[10:] for line in workflow[start:end].splitlines())
        function = function.replace("${{ matrix.platform }}", "fixture-platform")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            stub = path / "python"
            stub.write_text("#!/bin/sh\ncase \"$1\" in\n"
                            "scripts/run_parity.py) exit \"$FAKE_PARITY_EXIT\";;\n"
                            "*) printf '%s\\n' \"$@\" > \"$CAPTURE\";;\nesac\n")
            stub.chmod(0o700)
            for platform, parity_exit, expected_exit in (
                ("macOS", 0, 0), ("macOS", 1, 1), ("macOS", 2, 2),
                ("Windows", 0, 0), ("Windows", 1, 0), ("Windows", 2, 2),
            ):
                with self.subTest(platform=platform, parity_exit=parity_exit):
                    capture = path / f"{platform}-{parity_exit}.txt"
                    env = {**os.environ, "RUNNER_OS": platform,
                           "FAKE_PARITY_EXIT": str(parity_exit), "CAPTURE": str(capture),
                           "STUB_PYTHON": str(stub)}
                    script = ('set -euo pipefail\ncandidate_python="$STUB_PYTHON"\n'
                              'oracle_python=fixture-oracle\n' + function
                              + '\nrun_platform_parity --case-id fixture-case\n')
                    result = subprocess.run(["/bin/bash", "-c", script], env=env,
                                            text=True, capture_output=True)
                    self.assertEqual(result.returncode, expected_exit, result.stderr)
                    if expected_exit:
                        self.assertFalse(capture.exists())
                    else:
                        args = capture.read_text().splitlines()
                        self.assertEqual(args[:5], ["scripts/check_ci_evidence.py", "parity",
                            "target/parity-fixture-platform.json", "--offline", "--require-clean"])
                        self.assertEqual(args[-2:], ["--case-id", "fixture-case"])
                        self.assertEqual("--accept-windows-reference-hang" in args, platform == "Windows")


if __name__ == "__main__":
    unittest.main()
