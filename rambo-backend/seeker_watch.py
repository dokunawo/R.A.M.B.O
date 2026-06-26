"""Proactive Seeker crawls — Phase 2.

The operator registers "watch" topics (e.g. "AI agent frameworks", "NVDA
stock"). On a cadence the Seeker web-searches each, summarizes what's current,
and — only when the finding has materially changed since last time — proactively
surfaces it (on-screen card + optional speech). Topics and last results live in
Keeper, so nothing new is stored and dedup is durable across restarts.

No-op when there are no watch topics, so it's silent until you ask RAMBO to keep
an eye on something.

Env:
  PROACTIVE_SEEKER    "on"/"off" (default "on")
  SEEKER_CRAWL_HOURS  hours between crawls (default 6)
  SEEKER_SPEAK        "on"/"off" — speak new findings (default "off")
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

log = logging.getLogger("rambo.seeker_watch")

WATCH_TAG = "watch"
RESULT_TAG = "watch_result"
DISPLAY_AGENT = "seeker"


def _enabled() -> bool:
    return os.environ.get("PROACTIVE_SEEKER", "on").strip().lower() not in ("off", "0", "false")


def _crawl_hours() -> float:
    try:
        return max(0.25, float(os.environ.get("SEEKER_CRAWL_HOURS", "6")))
    except ValueError:
        return 6.0


def _speak_enabled() -> bool:
    return os.environ.get("SEEKER_SPEAK", "off").strip().lower() in ("on", "1", "true")


def slugify(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (topic or "").lower()).strip("_") or "topic"


def _norm(text: str) -> str:
    """Normalize for change-detection (collapse whitespace, lowercase)."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


async def add_topic(keeper_repo, topic: str) -> str:
    slug = slugify(topic)
    await keeper_repo.write(f"{WATCH_TAG}_{slug}", topic.strip(), tags=WATCH_TAG, confidence="verified")
    return slug


async def list_topics(keeper_repo) -> list[dict]:
    rows = await keeper_repo.query(search=WATCH_TAG, limit=100)
    # query matches the tag substring; keep only true watch entries.
    return [{"slug": r["key"].removeprefix(f"{WATCH_TAG}_"), "topic": r["value"]}
            for r in rows if r.get("key", "").startswith(f"{WATCH_TAG}_") and r.get("tags") == WATCH_TAG]


async def remove_topic(keeper_repo, slug: str) -> bool:
    ok = await keeper_repo.delete(f"{WATCH_TAG}_{slug}")
    await keeper_repo.delete(f"{RESULT_TAG}_{slug}")  # forget its last result too
    return ok


async def crawl_once(orchestrator) -> list[dict]:
    """Crawl every watch topic; surface + store only materially-new findings.
    Returns the list of topics that produced a new finding this pass."""
    keeper_repo = getattr(orchestrator, "keeper_repo", None)
    if keeper_repo is None:
        return []
    topics = await list_topics(keeper_repo)
    if not topics:
        return []

    from skills import web_search_skill
    surfaced = []
    for t in topics:
        slug, topic = t["slug"], t["topic"]
        try:
            finding = await web_search_skill(
                f"What's the latest on: {topic}? Summarize only what's current or "
                "newly changed, in 2-3 sentences. If nothing notable, say 'no change'.",
                {},
            )
        except Exception:
            log.exception("seeker crawl failed for %s", slug)
            continue
        if not finding or "[seeker degraded]" in finding.lower():
            continue
        if "no change" in _norm(finding) and len(_norm(finding)) < 40:
            continue

        prev = await keeper_repo.read(f"{RESULT_TAG}_{slug}")
        if prev and _norm(prev.get("value", "")) == _norm(finding):
            continue  # nothing materially new since last crawl

        await keeper_repo.write(f"{RESULT_TAG}_{slug}", finding, tags=RESULT_TAG, confidence="hint")
        msg = f'On "{topic}": {finding.strip()}'
        try:
            await orchestrator._response(DISPLAY_AGENT, msg)
            await orchestrator.broadcast(f"[Seeker] New on \"{topic}\".")
        except Exception:
            log.exception("seeker surface failed")
        if _speak_enabled():
            try:
                await orchestrator._voice_text(f'Heads up on {topic}. {finding.strip()}')
            except Exception:
                pass
        surfaced.append(t)
    return surfaced


async def seeker_watch_scheduler(orchestrator) -> None:
    """Crawl watch topics every SEEKER_CRAWL_HOURS. No-op without topics."""
    if not _enabled():
        log.info("seeker watch disabled (PROACTIVE_SEEKER=off)")
        return
    log.info("seeker watch on: every %.1fh", _crawl_hours())
    while True:
        try:
            await crawl_once(orchestrator)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("seeker watch crawl failed")
        await asyncio.sleep(_crawl_hours() * 3600)
