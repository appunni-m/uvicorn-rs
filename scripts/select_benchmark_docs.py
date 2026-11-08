#!/usr/bin/env python3
"""Select the main-branch benchmark run and aggregate for documentation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen


ALLOWED_EVENTS = {"push", "schedule", "workflow_dispatch"}
WORKFLOW_NAME = "ASGI performance matrix"


def github_get(path: str) -> dict:
    repository = os.environ["GITHUB_REPOSITORY"]
    request = Request(
        f"https://api.github.com/repos/{repository}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def select_run():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name == "workflow_run":
        run_id = int(os.environ["TRIGGER_RUN_ID"])
        attempt = int(os.environ["TRIGGER_RUN_ATTEMPT"])
        run = github_get(f"actions/runs/{run_id}")
        if run.get("id") != run_id:
            raise SystemExit("benchmark workflow run ID differs from the triggering event")
        if run.get("run_attempt") != attempt:
            return {"_stale_event": True}
        if (run.get("name") != WORKFLOW_NAME
                or run.get("head_branch") != "main"
                or run.get("event") not in ALLOWED_EVENTS
                or run.get("status") != "completed"
                or run.get("repository", {}).get("full_name") != os.environ["GITHUB_REPOSITORY"]
                or run.get("head_repository", {}).get("full_name") != os.environ["GITHUB_REPOSITORY"]):
            raise SystemExit("triggering benchmark is not a completed main-branch run in this repository")
        return run

    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        return None
    source_commit = os.environ.get("GITHUB_SHA") if event_name == "push" else None
    payload = github_get(
        "actions/workflows/benchmark-categories.yml/runs?head_branch=main&per_page=100"
    )
    runs = [run for run in payload.get("workflow_runs", [])
            if run.get("name") == WORKFLOW_NAME
            and run.get("head_branch") == "main"
            and (source_commit is None or run.get("head_sha") == source_commit)
            and run.get("event") in ALLOWED_EVENTS
            and run.get("status") == "completed"]
    if not runs:
        return None
    return max(runs, key=lambda run: (run.get("run_number", 0), run.get("run_attempt", 0)))


def select_artifact(run: dict) -> tuple[str, str]:
    run_id = run["id"]
    attempt = run["run_attempt"]
    expected_name = f"asgi-benchmark-matrix-{run_id}-{attempt}"
    artifacts = github_get(f"actions/runs/{run_id}/artifacts?per_page=100").get("artifacts", [])
    matches = [artifact for artifact in artifacts
               if artifact.get("name") == expected_name and artifact.get("expired") is False]
    if len(matches) > 1:
        raise SystemExit(f"expected at most one {expected_name} artifact, found {len(matches)}")
    if not matches:
        return "", ""
    artifact = matches[0]
    digest = artifact.get("digest")
    if (type(artifact.get("id")) is not int or artifact["id"] <= 0
            or not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None):
        raise SystemExit("benchmark artifact ID or digest is invalid")
    return str(artifact["id"]), digest


def main() -> int:
    output_path = Path(os.environ["GITHUB_OUTPUT"])
    run = select_run()
    if run is None:
        output_path.write_text("found=false\nstale=false\n", encoding="utf-8")
        print("No completed main benchmark run is available for the documentation snapshot.")
        return 0
    if run.pop("_stale_event", False):
        output_path.write_text("found=false\nstale=true\n", encoding="utf-8")
        print("Ignoring a stale workflow_run event for an older benchmark attempt.")
        return 0

    artifact_id, digest = select_artifact(run)
    values = {
        "found": "true",
        "stale": "false",
        "run-id": run["id"],
        "run-attempt": run["run_attempt"],
        "commit": run["head_sha"],
        "conclusion": run.get("conclusion") or "unknown",
        "artifact-id": artifact_id,
        "artifact-digest": digest,
    }
    with output_path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")
    print(json.dumps(values, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
