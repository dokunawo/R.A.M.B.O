"""Nightly reflection — consolidates the day into durable memory.

Once a day it reviews the day's completed dispatches and freshly-written
memories, asks the fast model to synthesize a few higher-order insights (recurring
patterns, stable preferences, themes), and writes them back into Keeper as
verified memories tagged ``reflection``. This turns raw activity logs into learned
patterns — the consolidation loop behind the "learns you over time" goal.

Reflection-tagged memories are excluded from the next day's input so insights
don't recursively feed on themselves.

Env:
  REFLECTION_TIME  "HH:MM" local time to run (default 23:30)
  REFLECTION_TZ    IANA tz for that time (default America/Detroit)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

log = logging.getLogger("rambo.reflection")

REFLECTION_TAG = "reflection"
_MAX_INSIGHTS = 3


def _today_bounds(now: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the local day containing ``now``, as tz-aware UTC for
    comparison against stored ISO timestamps."""
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local


def _within(ts_raw: str, start: datetime, end: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(ts_raw)
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    s = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    e = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return s <= ts < e


async def gather_day_material(dispatch_repo, keeper_repo, now: datetime) -> str:
    """Build the raw text block of today's activity for the synthesizer, or ''.

    Pulls today's dispatches and today's non-reflection memories. Returns '' when
    there's nothing worth reflecting on."""
    start, end = _today_bounds(now)
    lines: list[str] = []

    if dispatch_repo is not None:
        try:
            rows = await dispatch_repo.get_recent(limit=50)
        except Exception:
            rows = []
        done = [r for r in rows if _within(r.get("completed_at") or r.get("updated_at", ""), start, end)]
        if done:
            lines.append("TODAY'S TASKS:")
            for r in done:
                tail = f" — {r['summary']}" if r.get("summary") else ""
                lines.append(f"  - [{r.get('status','')}] {r['goal']}{tail}")

    if keeper_repo is not None:
        try:
            mems = await keeper_repo.query("", limit=50)
        except Exception:
            mems = []
        fresh = [
            m for m in mems
            if _within(m.get("updated_at", ""), start, end)
            and REFLECTION_TAG not in (m.get("tags") or "")
        ]
        if fresh:
            lines.append("TODAY'S NEW MEMORIES:")
            for m in fresh:
                lines.append(f"  - {m['key']}: {m['value']}")

    return "\n".join(lines).strip()


async def synthesize(llm, fast_model: str, raw: str, record_usage=None) -> list[dict]:
    """Ask the fast model for up to a few durable insights. Returns a list of
    {key, value} dicts (possibly empty). Best-effort: bad/empty output → []."""
    if not llm or not raw:
        return []
    prompt = (
        "You are consolidating a personal AI's day into durable long-term memory.\n"
        "From the activity below, extract up to "
        f"{_MAX_INSIGHTS} HIGHER-ORDER insights about the user or recurring "
        "patterns worth remembering long-term. Skip one-off trivia. If nothing is "
        "durable, return an empty array.\n"
        'Respond ONLY with a JSON array of objects like '
        '[{"key": "short_slug", "value": "the insight"}].\n\n'
        f"{raw}"
    )
    resp = await llm.messages.create(
        model=fast_model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    if record_usage is not None:
        try:
            await record_usage(fast_model, resp.usage, source="reflection")
        except Exception:
            pass
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    return _parse_insights(text)


def _parse_insights(text: str) -> list[dict]:
    if not text:
        return []
    # Tolerate code fences / surrounding prose by grabbing the first JSON array.
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if key and value:
            slug = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") or "insight"
            out.append({"key": f"reflection_{slug}", "value": value})
    return out[:_MAX_INSIGHTS]


async def run_reflection(orchestrator, now: datetime | None = None) -> list[dict]:
    """Gather → synthesize → persist. Returns the insights written (possibly [])."""
    now = now or datetime.now()
    dispatch_repo = getattr(orchestrator, "dispatch_repo", None)
    keeper_repo = getattr(orchestrator, "keeper_repo", None)
    if keeper_repo is None:
        return []

    raw = await gather_day_material(dispatch_repo, keeper_repo, now)
    if not raw:
        log.info("reflection: nothing to consolidate today")
        return []

    from usage_capture import record_usage
    import model_config
    insights = await synthesize(
        orchestrator.llm, model_config.fast_model(), raw, record_usage
    )
    written = []
    for ins in insights:
        try:
            await keeper_repo.write(
                ins["key"], ins["value"], tags=REFLECTION_TAG, confidence="verified"
            )
            written.append(ins)
        except Exception:
            log.exception("reflection: failed to store insight %s", ins.get("key"))

    if written:
        try:
            await orchestrator.broadcast(
                f"[Keeper] Nightly reflection stored {len(written)} insight(s)."
            )
        except Exception:
            pass

    # Roll the accumulated insights up into a single durable operator profile,
    # which is what _build_operator_context injects into every reply.
    await refresh_operator_profile(orchestrator)
    return written


PROFILE_KEY = "operator_profile"
PROFILE_TAG = "profile"


async def refresh_operator_profile(orchestrator) -> str | None:
    """Synthesize a short, stable profile of the operator from accumulated
    reflection insights and store it as the `operator_profile` Keeper entry. This
    is the seed that compounds over time and personalizes every response. Returns
    the profile text, or None if there's nothing to synthesize."""
    keeper_repo = getattr(orchestrator, "keeper_repo", None)
    llm = getattr(orchestrator, "llm", None)
    if keeper_repo is None or llm is None:
        return None
    try:
        insights = await keeper_repo.query(search=REFLECTION_TAG, limit=50)
    except Exception:
        return None
    if not insights:
        return None

    bullets = "\n".join(
        f"- {m.get('value', '')}" for m in insights if m.get("value")
    )
    prompt = (
        "You maintain a living profile of the operator of a personal AI. "
        "From the accumulated observations below, write a concise profile (4-6 "
        "short lines) capturing stable traits, preferences, working style, and "
        "recurring priorities. Present tense, second person ('You ...'). No "
        "preamble, just the profile lines.\n\n"
        f"{bullets}"
    )
    import model_config
    from usage_capture import record_usage
    try:
        resp = await llm.messages.create(
            model=model_config.fast_model(),
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            await record_usage(model_config.fast_model(), resp.usage, source="reflection")
        except Exception:
            pass
        profile = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
    except Exception:
        log.exception("profile synthesis failed")
        return None
    if not profile:
        return None
    try:
        await keeper_repo.write(PROFILE_KEY, profile, tags=PROFILE_TAG, confidence="verified")
    except Exception:
        log.exception("failed to store operator profile")
        return None
    return profile


def _reflection_time() -> tuple[int, int]:
    raw = os.environ.get("REFLECTION_TIME", "23:30").strip()
    try:
        hh, mm = (int(x) for x in raw.split(":")[:2])
        return hh, mm
    except Exception:
        return 23, 30


def _now_local() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(os.environ.get("REFLECTION_TZ", "America/Detroit")))
    except Exception:
        return datetime.now()


async def reflection_scheduler(orchestrator) -> None:
    """Fire run_reflection once per day at the configured local time. Runs forever."""
    while True:
        hh, mm = _reflection_time()
        now = _now_local()
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        wait = max(1.0, (nxt - now).total_seconds())
        log.info("Next reflection at %s (%.0f min)", nxt.isoformat(), wait / 60)
        try:
            await asyncio.sleep(wait)
            await run_reflection(orchestrator, _now_local())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("reflection run failed")
            await asyncio.sleep(60)
