"""Run frozen normal-build categories sequentially; retain every attempt."""

import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/performance-2026-10-05/categories-error-logs"
OUT.mkdir(exist_ok=False)
PYTHON = ROOT / ".venv/bin/python"
EXPECTED_SOURCE = "81c239b5f596cf4be18cc71bc3b537c02224c0f1e1ab35174e6386f5203510cd"
EXPECTED_NATIVE = "8f69afda0be9d121d304c674d5638f470da6939fbed58ce809457284df6585b6"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workload_names(path):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "WORKLOADS"
            for target in node.targets
        ):
            return [ast.literal_eval(key) for key in node.value.keys]
    raise ValueError(f"No WORKLOADS in {path}")


def identity():
    return {
        "source": digest(ROOT / "src/lib.rs"),
        "native": digest(ROOT / "python/uvicorn_rs/_native.abi3.so"),
        "harness": {
            str(path.relative_to(ROOT)): digest(path)
            for path in sorted((ROOT / "scripts").glob("*.py"))
            if path.name.startswith("run_") or path.name == "benchmark_evidence.py"
        },
        "examples": {
            str(path.relative_to(ROOT)): digest(path)
            for path in sorted((ROOT / "examples").glob("*.py"))
        },
    }


before = identity()
if before["source"] != EXPECTED_SOURCE or before["native"] != EXPECTED_NATIVE:
    raise RuntimeError("Canonical normal build has not been restored")
record = {
    "schema": "uvicorn-rs-sequential-category-run@1",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "status": "running_not_proven",
    "identity_before": before,
    "category_runs": [],
    "limitations": [
        "frozen dirty local checkout, not a release baseline",
        "same-host closed-loop load; contention-invalid rows remain excluded",
        "protocol-specific latency boundaries are not comparable across protocols",
        "H3 uploads have no qualifying Hypercorn oracle performance result",
        "exception diagnostic costs differ and cannot be ranked",
    ],
}


def checkpoint():
    temporary = OUT / "run.json.next"
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(OUT / "run.json")


checkpoint()
configs = [
    ("http1", "run_http_category_bench.py", "uvicorn-uvloop-httptools"),
    ("http2", "run_h2_category_bench.py", "hypercorn-uvloop"),
    ("http3", "run_h3_category_bench.py", "hypercorn-uvloop"),
    ("websocket", "run_websocket_category_bench.py", "uvicorn-uvloop-websockets"),
    ("lifecycle", "run_lifecycle_bench.py", "uvicorn-uvloop-httptools"),
]
environment = os.environ.copy()
environment.update(RUSTC_WRAPPER="", RUSTC_WORKSPACE_WRAPPER="")
failed = False
try:
    for label, script_name, reference in configs:
        script = ROOT / "scripts" / script_name
        output = OUT / f"{label}.json"
        command = [str(PYTHON), str(script), "--servers", reference,
                   "uvicorn-rs-uvloop", "--repetitions", "3", "--seed", "20261005",
                   "--output", str(output)]
        if label != "lifecycle":
            command += ["--workloads", *workload_names(script), "--duration", "5",
                        "--warmup", "1", "--concurrency", "64"]
        entry = {"category": label, "command": command,
                 "started_at": datetime.now(timezone.utc).isoformat()}
        record["category_runs"].append(entry)
        checkpoint()
        print(json.dumps({"event": "starting", **entry}), flush=True)
        with (OUT / f"{label}.log").open("x") as log:
            result = subprocess.run(command, cwd=ROOT, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT)
        entry.update(exit_code=result.returncode,
                     finished_at=datetime.now(timezone.utc).isoformat())
        if output.exists():
            report = json.loads(output.read_text())
            rows = report["rows"]
            entry.update(report_sha256=digest(output), rows=len(rows),
                         correctness_failures=sum(row["failures"] for row in rows),
                         timing_valid_rows=sum(row["timing_valid"] for row in rows),
                         performance_evidence_status=report["metadata"]["performance_evidence_status"])
        failed |= result.returncode != 0
        if identity() != before:
            raise RuntimeError("Measured source/native/harness changed during categories")
        checkpoint()
        print(json.dumps({"event": "finished", **entry}), flush=True)
    record["status"] = "completed_with_failures" if failed else "completed_correctness_gated"
except BaseException as caught:
    record["status"] = "failed_not_proven"
    record["error"] = {"type": type(caught).__name__, "message": str(caught)}
    failed = True
    raise
finally:
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    record["identity_after"] = identity()
    checkpoint()
sys.exit(1 if failed else 0)
