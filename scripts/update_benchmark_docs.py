#!/usr/bin/env python3
"""Render the selected main benchmark receipt into a documentation build."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from benchmark_identity import positive_integer_identity


BEGIN = "<!-- BEGIN GENERATED LATEST ATTEMPT -->"
END = "<!-- END GENERATED LATEST ATTEMPT -->"
SYSTEM_NAMES = {
    "linux-x86_64": "Linux x86-64",
    "linux-aarch64": "Linux ARM64",
    "macos-arm64": "macOS ARM64",
}


def verify_checksums(directory: Path) -> None:
    sums_path = directory / "SHA256SUMS"
    if not sums_path.is_file():
        raise SystemExit("benchmark aggregate is missing SHA256SUMS")
    verified = set()
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        relative = Path(name)
        if (not separator or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or relative.is_absolute() or ".." in relative.parts):
            raise SystemExit("benchmark aggregate contains an invalid checksum entry")
        if name in verified:
            raise SystemExit(f"benchmark aggregate repeats a checksum entry: {name}")
        path = directory / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit(f"benchmark aggregate checksum mismatch: {name}")
        verified.add(name)
    if not {"matrix.json", "report.md"}.issubset(verified):
        raise SystemExit("benchmark aggregate checksums must include matrix.json and report.md")


def replace_generated_section(path: Path, content: str) -> None:
    document = path.read_text(encoding="utf-8")
    if document.count(BEGIN) != 1 or document.count(END) != 1:
        raise SystemExit(f"{path} must contain exactly one generated-attempt marker pair")
    before, remainder = document.split(BEGIN, 1)
    _, after = remainder.split(END, 1)
    path.write_text(f"{before}{BEGIN}\n{content.strip()}\n{END}{after}", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--conclusion", required=True)
    parser.add_argument("--artifact-id", default="")
    parser.add_argument("--artifact-digest", default="")
    parser.add_argument("--aggregate-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.run_id <= 0 or args.run_attempt <= 0:
        raise SystemExit("benchmark run ID and attempt must be positive integers")
    if re.fullmatch(r"[0-9a-f]{40}", args.commit) is None:
        raise SystemExit("benchmark commit must be a full lowercase Git SHA")
    url = f"https://github.com/{args.repository}/actions/runs/{args.run_id}"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    lines = [
        "## Latest automated benchmark attempt",
        "",
        f"- Run: [{args.run_id} (attempt {args.run_attempt})]({url})",
        f"- Commit: [`{args.commit}`](https://github.com/{args.repository}/commit/{args.commit})",
        f"- Recorded: {timestamp}",
        f"- Workflow conclusion: `{args.conclusion}`",
    ]

    aggregate = args.aggregate_directory
    matrix_path = aggregate / "matrix.json"
    report_path = aggregate / "report.md"
    if matrix_path.is_file() and report_path.is_file():
        verify_checksums(aggregate)
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        if (matrix.get("schema") != "uvicorn-rs-benchmark-matrix@2"
                or positive_integer_identity(matrix.get("run_id")) != args.run_id
                or positive_integer_identity(matrix.get("run_attempt")) != args.run_attempt
                or matrix.get("commit") != args.commit
                or matrix.get("repository") != args.repository
                or matrix.get("workflow_run_url") != url):
            raise SystemExit("benchmark aggregate identity differs from the selected workflow run")
        systems = matrix.get("systems")
        expected_systems = set(SYSTEM_NAMES)
        if (not isinstance(systems, list)
                or {item.get("system_id") for item in systems if isinstance(item, dict)} != expected_systems
                or len(systems) != len(expected_systems)):
            raise SystemExit("benchmark aggregate is missing or duplicating one of the three system receipts")
        if (not args.artifact_id or re.fullmatch(r"[0-9]+", args.artifact_id) is None
                or re.fullmatch(r"sha256:[0-9a-f]{64}", args.artifact_digest) is None):
            raise SystemExit("downloaded aggregate is missing its GitHub artifact identity")
        for system in systems:
            system_id = system.get("system_id")
            label = SYSTEM_NAMES.get(system_id)
            if label is None:
                raise SystemExit(f"unexpected benchmark system in aggregate: {system_id}")
            lines.append(
                f"- {label} category matrix: `{system.get('matrix_status')}` "
                f"(`{system.get('driver_status')}`, {system.get('qualified_pairs')} qualified pairs)"
            )
        complete_systems = all(
            system.get("matrix_status") == "validated_complete_system" for system in systems
        )
        if ((matrix.get("status") == "validated_complete_matrix") != complete_systems):
            raise SystemExit("aggregate matrix status disagrees with its system receipts")
        lines += ["", f"Aggregate: `{matrix.get('status')}`"]
        if args.artifact_id and re.fullmatch(r"[0-9]+", args.artifact_id):
            artifact_url = f"{url}/artifacts/{args.artifact_id}"
            digest = args.artifact_digest.removeprefix("sha256:")
            if digest and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise SystemExit("selected benchmark aggregate digest is malformed")
            digest_note = f" with SHA-256 `{digest}`" if digest else ""
            lines.append(f"Aggregate artifact: [{args.artifact_id}]({artifact_url}){digest_note}.")

        if matrix.get("status") == "validated_complete_matrix":
            Path("docs/benchmark-results.md").write_text(
                report_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            lines += [
                "",
                "All three systems produced a complete validated matrix. This report is rendered from the checksummed aggregate artifact; raw platform bundles remain attached to the benchmark workflow run.",
            ]
        elif matrix.get("status") == "validated_partial_matrix":
            lines += [
                "",
                "The aggregate contains a validated partial matrix. The previous complete benchmark report remains unchanged; inspect this run's artifact for the partial inputs.",
            ]
        else:
            raise SystemExit("benchmark aggregate status is not recognized")
    else:
        lines += [
            "- Aggregate: unavailable; no validated matrix artifact was produced.",
            "",
            f"The previous complete benchmark report remains unchanged. Inspect the [workflow run]({url}) for its job results and retained system artifacts.",
        ]

    replace_generated_section(Path("docs/benchmark-status.md"), "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
