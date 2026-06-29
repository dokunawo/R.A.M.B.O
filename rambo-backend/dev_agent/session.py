"""Dev session driver — orchestrates one self-code change end to end.

draft_change(): worktree → coding agent → commit → diff → impact → persist as
                pending_review. Never merges.
merge_change(): merge the reviewed branch into base, then clean up.
reject_change(): discard the branch + worktree, untouched base.
escalate_change(): write a review-request artifact for a Claude Code session.

Both the /dev/* endpoints and the orchestrator's dev lane call these, so the
logic lives in one place.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path

from dev_agent import git_workspace as gw
from dev_agent import impact as impact_mod
from dev_agent.coding_agent import CodingAgent
from dev_agent.repo import DevRepo

logger = logging.getLogger(__name__)

# Where escalated changes are written for a human/Claude review session.
ESCALATION_DIR = Path(__file__).resolve().parent.parent / "data" / "escalations"


def _ws_from_row(row: dict) -> gw.GitWorkspace:
    return gw.GitWorkspace(
        change_id=row["id"],
        repo_root=gw.resolve_repo_root(),
        base_branch=row.get("base_branch") or "main",
        branch=row["branch"],
        worktree_path=Path(row["worktree_path"]),
    )


async def draft_change(*, llm, repo: DevRepo, change_id: str, goal: str,
                       personality_text: str = "", on_event=None) -> dict:
    """Run the full draft pipeline. Returns the impact dict (or raises-safe error dict)."""
    on_event = on_event or (lambda *a, **k: None)
    eta_s = max(30, min(180, 25 + len(goal) // 6))
    ws = None
    try:
        on_event(stage="workspace", msg="Creating isolated worktree", eta_s=eta_s)
        ws = await gw.create_workspace(change_id)

        on_event(stage="coding", msg="Drafting the change")
        agent = CodingAgent(llm, ws.worktree_path, personality_text=personality_text,
                            on_event=lambda **k: on_event(stage="tool", **k))
        await agent.run(goal)

        changed = await gw.commit_paths(
            ws, f"RAMBO self-change: {goal[:72]}", sorted(agent.touched),
        )
        if not changed:
            await repo.set_status(change_id, "failed")
            await gw.discard(ws)
            return {"recommendation": "hold", "summary": "Agent made no changes.",
                    "affects": [], "risk": "low", "rationale": "Nothing to review."}

        on_event(stage="impact", msg="Analyzing impact")
        diff = await gw.diff(ws)
        stat = await gw.diff(ws, stat=True)
        result = await impact_mod.analyze(llm, goal, diff, stat)

        await repo.set_proposal(
            change_id, branch=ws.branch, worktree_path=str(ws.worktree_path),
            base_branch=ws.base_branch, diff=diff, stat=stat, impact=result,
        )
        on_event(stage="ready", msg="Change ready for review",
                 recommendation=result.get("recommendation"))
        return result
    except Exception as e:  # noqa: BLE001
        logger.exception("draft_change failed for %s", change_id)
        try:
            await repo.set_error(change_id, str(e))
            if ws is not None:
                await gw.discard(ws)
        except Exception:
            logger.exception("cleanup after failed draft also failed")
        return {"recommendation": "hold", "summary": f"Draft failed: {e}",
                "affects": [], "risk": "high", "rationale": "Error during drafting."}


async def merge_change(repo: DevRepo, change_id: str,
                       run_full_tests: bool = False) -> dict:
    row = await repo.get(change_id)
    if row is None:
        return {"error": "not found"}
    if row["status"] != "pending_review":
        return {"error": f"not in reviewable state (is {row['status']})"}
    ws = _ws_from_row(row)

    # Optional gate: run the WHOLE suite in the worktree first. A red suite
    # blocks the merge and leaves the change reviewable (status untouched).
    tests = None
    if run_full_tests:
        from dev_agent import test_gate
        tests = await test_gate.run_full_suite(ws.worktree_path)
        if not tests.get("passed"):
            return {"error": "test gate failed — merge blocked",
                    "id": change_id, "status": row["status"], "tests": tests}

    try:
        await gw.merge(ws)
    except gw.GitWorkspaceError as e:
        return {"error": str(e)}
    await repo.set_status(change_id, "merged")
    try:
        await gw.discard(ws)
    except Exception:
        logger.exception("post-merge worktree cleanup failed for %s", change_id)
    result = {"status": "merged", "id": change_id,
              "note": "Merged to base branch. Restart the backend to take it live (no auto-reload)."}
    if tests is not None:
        result["tests"] = tests
    return result


async def reject_change(repo: DevRepo, change_id: str) -> dict:
    row = await repo.get(change_id)
    if row is None:
        return {"error": "not found"}
    if row["status"] in ("merged", "rejected"):
        return {"error": f"not in rejectable state (is {row['status']})"}
    # Prune any worktree/branch this change created. Tolerant of a draft that
    # crashed before recording them (status still 'drafting', branch/worktree NULL
    # in the DB yet a rambo/dev-<id> branch left on disk) — so a stuck draft can
    # finally be rejected instead of lingering forever.
    try:
        await gw.prune_change(change_id, branch=row.get("branch"),
                              worktree_path=row.get("worktree_path"))
    except Exception:
        logger.exception("cleanup failed on reject for %s", change_id)
    await repo.set_status(change_id, "rejected")
    return {"status": "rejected", "id": change_id}


async def sweep_stale_drafts(repo: DevRepo, max_age_minutes: int = 60) -> int:
    """Self-heal: clear `drafting` changes that never advanced (the draft crashed
    or was interrupted mid-run). Any change still in `drafting` older than
    `max_age_minutes` has its dangling branch/worktree pruned and its row deleted,
    so it stops haunting the Changes history. Returns how many were swept.
    Best-effort — never raises into the caller (e.g. startup)."""
    try:
        rows = await repo.list_drafting()
    except Exception:
        return 0
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=max_age_minutes)
    swept = 0
    for row in rows:
        try:
            updated = _dt.datetime.fromisoformat(row.get("updated_at") or "")
        except (ValueError, TypeError):
            updated = None
        # A fresh draft may be legitimately in flight — only sweep stale ones.
        if updated is not None and updated > cutoff:
            continue
        try:
            await gw.prune_change(row["id"], branch=row.get("branch"),
                                  worktree_path=row.get("worktree_path"))
            await repo.delete(row["id"])
            swept += 1
        except Exception:
            logger.exception("failed to sweep stale draft %s", row.get("id"))
    return swept


async def escalate_change(repo: DevRepo, change_id: str) -> dict:
    row = await repo.get(change_id)
    if row is None:
        return {"error": "not found"}
    ESCALATION_DIR.mkdir(parents=True, exist_ok=True)
    artifact = ESCALATION_DIR / f"{change_id}.md"
    impact = row.get("impact") or {}
    artifact.write_text(
        f"# RAMBO self-change escalation — {change_id}\n\n"
        f"## Goal\n{row['goal']}\n\n"
        f"## RAMBO's assessment\n"
        f"- Recommendation: {impact.get('recommendation')}\n"
        f"- Risk: {impact.get('risk')}\n"
        f"- Summary: {impact.get('summary')}\n"
        f"- Rationale: {impact.get('rationale')}\n"
        f"- Affects: {', '.join(impact.get('affects') or []) or '(none listed)'}\n\n"
        f"## Branch\n`{row.get('branch')}` (worktree: `{row.get('worktree_path')}`)\n\n"
        f"## Diff\n```diff\n{row.get('diff') or '(none)'}\n```\n",
        encoding="utf-8",
    )
    await repo.set_status(change_id, "escalated")
    return {"status": "escalated", "id": change_id, "artifact": str(artifact),
            "note": "Diff + assessment written for a Claude Code review session. "
                    "Branch left intact for follow-up."}
