"""
Generates the recent activity AUTO block from git log (last 14 days).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def generate(repo_root: Path | None = None) -> str:
    root = repo_root or _REPO_ROOT

    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--since=14 days ago", "--no-merges", "--format=%h %s (%cr)"],
            capture_output=True, text=True, cwd=str(root), timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "_unavailable — git not found or timed out_"

    if result.returncode != 0:
        return "_unavailable — not a git repository_"

    lines = result.stdout.strip().splitlines()
    if not lines:
        return "_No commits in the last 14 days._"

    out = [f"Last 14 days — {len(lines)} commit{'s' if len(lines) != 1 else ''}:", ""]
    for line in lines[:20]:
        out.append(f"- `{line}`")
    if len(lines) > 20:
        out.append(f"- … and {len(lines) - 20} more")

    return "\n".join(out)
