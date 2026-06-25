"""codebase_skill — read-only self-awareness for R.A.M.B.O.

Lets R.A.M.B.O answer questions about its OWN source and recent changes by
reading the repo (mounted read-only at /repo, including .git) and letting the
LLM explain what it finds. Strictly read-only: only `git log/show/diff/ls-files`
and capped file reads. No writes, no checkout — the :ro mount enforces this too.

Mirrors the shape of web_search_skill in skills.py: gather grounding context,
then let the model compose the answer. Degrades cleanly (errors surfaced, never
swallowed) when the repo or the API key is unavailable.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

REPO = "/repo"
_MAX_FILE_CHARS = 10_000      # per-file read cap (matches tool_registry._read_file)
_MAX_FILES = 3                # how many files to pull in for a file/architecture answer

# Phrases that mean "tell me about recent changes" vs. "tell me about the code".
_CHANGE_HINTS = (
    "what changed", "what did we change", "what did we just", "what have we",
    "recent change", "recent commit", "latest commit", "last commit",
    "git log", "what did you change", "what's new", "whats new",
)


async def _git(*args: str) -> tuple[int, str]:
    """Run a read-only git command in /repo. Returns (returncode, combined output).
    `-c safe.directory=*` avoids git's dubious-ownership refusal when the repo is
    owned by the host user but the container runs as root."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-c", "safe.directory=*", "-C", REPO, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return proc.returncode, out.decode("utf-8", errors="replace")


def _wants_changes(goal: str) -> bool:
    low = goal.lower()
    return any(h in low for h in _CHANGE_HINTS)


def _candidate_filenames(goal: str) -> list[str]:
    """Pull likely file references out of the goal (e.g. 'orchestrator.py')."""
    return re.findall(r"[\w./-]+\.\w{1,5}", goal)


async def _gather_changes_context() -> str:
    rc1, log = await _git("log", "--oneline", "-n", "15")
    rc2, show = await _git("show", "--stat", "--format=%h %s%n%an, %ar", "HEAD")
    if rc1 != 0 and rc2 != 0:
        return ""
    return (
        "## Recent commits (newest first)\n" + log.strip() +
        "\n\n## Most recent commit (files changed)\n" + show.strip()
    )


async def _gather_file_context(goal: str) -> str:
    # Resolve candidate filenames against tracked files (respects .gitignore).
    rc, listing = await _git("ls-files")
    if rc != 0:
        return ""
    tracked = listing.splitlines()
    wanted = _candidate_filenames(goal)

    matches: list[str] = []
    for token in wanted:
        base = token.lstrip("./")
        matches += [t for t in tracked if t.endswith(base) or base in t]
    # De-dup, preserve order, cap.
    seen, picked = set(), []
    for m in matches:
        if m not in seen:
            seen.add(m)
            picked.append(m)
        if len(picked) >= _MAX_FILES:
            break

    if not picked:
        # No specific file named — give the model a high-level map of the tree.
        top = "\n".join(sorted({t.split("/")[0] for t in tracked}))
        return f"## Repository top-level structure\n{top}\n\n(Tracked files: {len(tracked)})"

    parts = []
    for rel in picked:
        try:
            text = Path(REPO, rel).read_text(encoding="utf-8", errors="replace")[:_MAX_FILE_CHARS]
        except Exception as e:
            text = f"(could not read: {e})"
        parts.append(f"## File: {rel}\n```\n{text}\n```")
    return "\n\n".join(parts)


async def codebase_skill(goal: str, ctx: dict) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "[Codebase DEGRADED] Self-awareness needs ANTHROPIC_API_KEY on the backend."

    if not Path(REPO, ".git").exists():
        return ("[Codebase DEGRADED] I can't see my own repository — the repo isn't "
                "mounted at /repo. (Add `- ./:/repo:ro` to the backend's volumes.)")

    try:
        if _wants_changes(goal):
            context = await _gather_changes_context()
        else:
            context = await _gather_file_context(goal)
    except Exception as e:
        return f"[Codebase DEGRADED] Couldn't read the repository: {e}"

    if not context.strip():
        return "[Codebase DEGRADED] git returned nothing — is /repo a valid git repo?"

    try:
        import anthropic
        import model_config
        client = anthropic.AsyncAnthropic(api_key=key)
        resp = await client.messages.create(
            model=model_config.default_model(),
            max_tokens=1024,
            system=(
                "You are R.A.M.B.O answering questions about your OWN source code "
                "and history. Use ONLY the repository context provided below — git "
                "output and file contents — to answer concretely and in plain "
                "language. Name the actual files/commits involved. If the context "
                "doesn't contain the answer, say so plainly rather than guessing.\n\n"
                f"=== REPOSITORY CONTEXT ===\n{context}"
            ),
            messages=[{"role": "user", "content": goal}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        text = "\n".join(p for p in parts if p).strip()
        return text or "[Codebase] Read the repo but produced no answer text."
    except Exception as e:
        return f"[Codebase DEGRADED] Analysis failed: {e}"
