"""Source inventory shared by benchmark capture and acceptance verification."""

from __future__ import annotations

import subprocess
from pathlib import Path


def workspace_rust_source_paths(root: Path) -> list[str]:
    """Return every tracked or nonignored Rust source and Cargo manifest."""
    workspace_files = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
    ).decode().split("\0")
    return sorted(
        name for name in workspace_files
        if name and (root / name).is_file()
        and (name.endswith(".rs") or Path(name).name == "Cargo.toml")
    )
