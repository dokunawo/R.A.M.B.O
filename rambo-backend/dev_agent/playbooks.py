"""Load coding playbooks into the dev agent's system prompt.

Phase 4: give RAMBO's self-coding agent the high-leverage engineering disciplines
(TDD, systematic debugging, verification-before-completion) — distilled from the
superpowers skills and adapted to what the local CodingAgent can actually do
(it has read/write/edit/list tools, no command execution). The Claude-Code-harness
-specific skills (worktrees, the Skill tool, MCP plumbing) are intentionally left out.

Selection via RAMBO_DEV_PLAYBOOKS:
  - unset  → all playbooks (default)
  - "off"  → none
  - "test-driven-development,systematic-debugging" → just those, in that order
"""
from __future__ import annotations

import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "playbooks"

# Default order — verification last so it's the freshest instruction before the
# agent wraps up.
DEFAULT_PLAYBOOKS = (
    "test-driven-development",
    "systematic-debugging",
    "verification-before-completion",
)


def available() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.md"))


def _selected() -> list[str]:
    env = os.environ.get("RAMBO_DEV_PLAYBOOKS")
    if env is None:
        return list(DEFAULT_PLAYBOOKS)
    env = env.strip()
    if env.lower() == "off":
        return []
    return [name.strip() for name in env.split(",") if name.strip()]


def load_playbooks(names: list[str] | None = None) -> str:
    """Return the selected playbooks as one markdown block (or '' if none)."""
    names = names if names is not None else _selected()
    blocks: list[str] = []
    for name in names:
        path = _DIR / f"{name}.md"
        if path.exists():
            blocks.append(path.read_text(encoding="utf-8").strip())
    if not blocks:
        return ""
    return (
        "\n\n## Engineering playbooks (follow these while you work)\n\n"
        + "\n\n---\n\n".join(blocks)
    )
