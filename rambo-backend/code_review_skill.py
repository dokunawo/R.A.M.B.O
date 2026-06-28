"""code_review_skill — voice-triggered review of the operator's OPEN changes.

"Operator, review the auth module" → reads the uncommitted diff (working tree
vs HEAD) from the read-only `/repo` mount, optionally scoped to a named module
or file, and asks the LLM for a focused code review. Strictly read-only — reuses
codebase_skill's `_git` (git diff/status only, no writes).

Mirrors codebase_skill: gather grounding context (the diff), then let the model
compose the answer. Degrades cleanly when the API key is missing, the repo isn't
mounted, or there are no open changes to review.
"""
from __future__ import annotations

import os
import re

from codebase_skill import REPO, _git

# Diff size cap so a huge working tree doesn't blow the token budget.
_MAX_DIFF_CHARS = 12_000

# Words after "review" that are NOT a module/file name — filler we skip when
# pulling the scope token out of the goal.
_GENERIC = {
    "the", "my", "a", "an", "some", "any", "this", "that", "these", "those",
    "module", "modules", "file", "files", "code", "changes", "change", "diff",
    "diffs", "function", "edits", "edit", "open", "uncommitted", "working",
    "tree", "repo", "repository", "current", "latest", "please", "operator",
    "rambo", "for", "me", "to", "of", "in", "and", "all", "everything",
}


def match_code_review(goal: str) -> bool:
    """True for "review the auth module", "review my changes", "review foo.py".
    Requires the word "review" plus either a named file or a code-ish noun, so it
    never steals "review my calendar" / "review my day" (those have no code cue)."""
    low = goal.lower()
    if "review" not in low:
        return False
    if re.search(r"[\w/-]+\.\w{1,5}", goal):       # a filename was named
        return True
    return any(w in low for w in (
        "module", "changes", "change", "code", "diff", "function",
        "my edits", "open changes", "working tree", "uncommitted", "the repo",
    ))


def _scope_token(goal: str) -> str | None:
    """Pull the module/file the operator wants reviewed out of the goal, or None
    for "review my changes" (= review everything that's open)."""
    files = re.findall(r"[\w./-]+\.\w{1,5}", goal)
    if files:
        return files[0]
    m = re.search(r"review\b(.*)$", goal, re.IGNORECASE)
    if not m:
        return None
    words = re.findall(r"[A-Za-z0-9_./-]+", m.group(1).lower())
    cand = [w for w in words if w not in _GENERIC]
    return cand[0] if cand else None


async def _changed_files() -> list[str]:
    """Tracked files with working-tree changes vs HEAD (newest diff scope)."""
    rc, out = await _git("diff", "--name-only", "HEAD")
    if rc != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


async def code_review_skill(goal: str, ctx: dict) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "[Review DEGRADED] Code review needs ANTHROPIC_API_KEY on the backend."

    if not os.path.exists(os.path.join(REPO, ".git")):
        return ("[Review DEGRADED] I can't see my own repository — the repo isn't "
                "mounted at /repo. (Add `- ./:/repo:ro` to the backend's volumes.)")

    try:
        changed = await _changed_files()
    except Exception as e:
        return f"[Review DEGRADED] Couldn't read the working tree: {e}"

    if not changed:
        return "There are no open changes to review — the working tree is clean."

    token = _scope_token(goal)
    if token:
        paths = [f for f in changed if token.lower() in f.lower()]
        if not paths:
            opts = ", ".join(sorted({f.split("/")[0] for f in changed})) or "nothing"
            return (f"No open changes match \"{token}\". Currently changed areas: {opts}.")
        scope_label = f'"{token}"'
    else:
        paths = changed
        scope_label = "all open changes"

    try:
        rc, diff = await _git("diff", "HEAD", "--", *paths)
    except Exception as e:
        return f"[Review DEGRADED] git diff failed: {e}"
    if rc != 0 or not diff.strip():
        return f"Nothing to review under {scope_label} — no diff against HEAD."

    truncated = len(diff) > _MAX_DIFF_CHARS
    if truncated:
        diff = diff[:_MAX_DIFF_CHARS] + "\n… (diff truncated)"

    file_list = "\n".join(f"  - {p}" for p in paths)
    context = (
        f"## Files under review ({scope_label})\n{file_list}\n\n"
        f"## Uncommitted diff (working tree vs HEAD)\n```diff\n{diff}\n```"
    )

    try:
        import anthropic
        import model_config
        client = anthropic.AsyncAnthropic(api_key=key)
        resp = await client.messages.create(
            model=model_config.default_model(),
            max_tokens=1024,
            system=(
                "You are R.A.M.B.O reviewing the operator's OWN uncommitted code "
                "changes before they commit. Give a focused, senior-engineer code "
                "review of ONLY the diff provided: call out correctness bugs, "
                "risky edge cases, and concrete improvements, citing the actual "
                "files. Skip nitpicks. Be concise and speak plainly (this is read "
                "aloud). End with a one-line verdict: 'Looks good to commit' or "
                "'Needs work' with the single most important reason.\n\n"
                f"=== CHANGE CONTEXT ===\n{context}"
            ),
            messages=[{"role": "user", "content": goal}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        text = "\n".join(p for p in parts if p).strip()
        return text or "[Review] Read the diff but produced no review text."
    except Exception as e:
        return f"[Review DEGRADED] Review failed: {e}"
