"""Proactive idle + deadline nudges — Phase 2.

Idle nudge: if the operator has been inactive a while (during waking hours) AND
things are actually waiting on them, RAMBO gently surfaces what's pending. The
message is built from the real pending counts — nothing fires when nothing is
waiting, so it can't nag.

Deadline nudge: deadlines the operator registers (Keeper, tag `deadline` with a
`due:<ISO>` tag) are surfaced once a day when they fall within the lead window.

Env:
  PROACTIVE_IDLE       "on"/"off" (default "on")
  IDLE_MINUTES         minutes of inactivity before an idle nudge (default 45)
  PROACTIVE_DEADLINES  "on"/"off" (default "on")
  DEADLINE_LEAD_DAYS   surface deadlines within this many days (default 2)
  PROACTIVE_TZ         IANA tz for waking-hours / day math (default America/Detroit)
  PROACTIVE_WAKE       waking window "HH-HH" local, no nudges outside it (default 8-22)
  PROACTIVE_SPEAK      "on"/"off" — speak nudges (default "off")
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, date

log = logging.getLogger("rambo.proactive")

DISPLAY_AGENT = "pilot"
DEADLINE_TAG = "deadline"

# ── Operator activity tracking (updated from /rambo/execute) ──────
_last_active = time.monotonic()


def mark_active() -> None:
    global _last_active
    _last_active = time.monotonic()


def idle_seconds() -> float:
    return time.monotonic() - _last_active


# ── Config helpers ───────────────────────────────────────────────
def _on(name: str, default: str = "on") -> bool:
    return os.environ.get(name, default).strip().lower() in ("on", "1", "true")


def _idle_minutes() -> int:
    try:
        return max(5, int(os.environ.get("IDLE_MINUTES", "45")))
    except ValueError:
        return 45


def _lead_days() -> int:
    try:
        return max(0, int(os.environ.get("DEADLINE_LEAD_DAYS", "2")))
    except ValueError:
        return 2


def _now_local() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(os.environ.get("PROACTIVE_TZ", "America/Detroit")))
    except Exception:
        return datetime.now()


def _within_waking_hours() -> bool:
    raw = os.environ.get("PROACTIVE_WAKE", "8-22")
    try:
        start, end = (int(x) for x in raw.split("-")[:2])
    except Exception:
        start, end = 8, 22
    return start <= _now_local().hour < end


async def _surface(orchestrator, msg: str) -> None:
    try:
        await orchestrator._response(DISPLAY_AGENT, msg)
        await orchestrator.broadcast(f"[{DISPLAY_AGENT.capitalize()}] {msg}")
    except Exception:
        log.exception("nudge surface failed")
    if _on("PROACTIVE_SPEAK", "off"):
        try:
            await orchestrator._voice_text(msg)
        except Exception:
            pass


# ── Idle nudge ───────────────────────────────────────────────────
async def _pending_parts(orchestrator) -> list[str]:
    """Human-readable pieces describing what's actually waiting on the operator."""
    parts = []
    try:
        from factory import confirmations
        n = len(confirmations.list_pending())
        if n:
            parts.append(f"{n} action{'s' if n != 1 else ''} to approve")
    except Exception:
        pass
    try:
        from factory import handoff
        n = len(handoff.list_pending())
        if n:
            parts.append(f"{n} proposed handoff{'s' if n != 1 else ''}")
    except Exception:
        pass
    fr = getattr(orchestrator, "factory_repo", None)
    if fr:
        try:
            from factory.repo import State
            n = len(await fr.list_by_status(State.AWAITING_APPROVAL))
            if n:
                parts.append(f"{n} agent{'s' if n != 1 else ''} awaiting approval")
        except Exception:
            pass
    dr = getattr(orchestrator, "dev_repo", None)
    if dr:
        try:
            n = len(await dr.list_pending())
            if n:
                parts.append(f"{n} code change{'s' if n != 1 else ''} to review")
        except Exception:
            pass
    return parts


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"


async def check_idle(orchestrator, state: dict) -> str | None:
    """Nudge once per idle stretch when work is waiting. Returns the message sent."""
    if not _on("PROACTIVE_IDLE"):
        return None
    if idle_seconds() < _idle_minutes() * 60:
        state["idle_fired"] = False  # operator is active → re-arm
        return None
    if not _within_waking_hours() or state.get("idle_fired"):
        return None
    parts = await _pending_parts(orchestrator)
    if not parts:
        return None  # nothing waiting → never nag
    msg = f"While you've been away, {_join(parts)} — whenever you're ready."
    await _surface(orchestrator, msg)
    state["idle_fired"] = True
    return msg


# ── Deadlines ────────────────────────────────────────────────────
_DUE_RE = re.compile(r"due:(\d{4}-\d{2}-\d{2})")


_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}


def _parse_due(when: str) -> date | None:
    """Resolve a deadline date from natural language or ISO. Handles ISO dates,
    today/tomorrow, weekday names ('Friday', 'next Friday' → next occurrence),
    'in N days/weeks', and falls back to the shared temporal resolver."""
    from datetime import timedelta
    w = (when or "").strip().lower()
    if not w:
        return None
    try:
        return date.fromisoformat(w)
    except ValueError:
        pass
    m = re.search(r"in\s+(\d+)\s+(day|days|week|weeks)", w)
    if m:
        n = int(m.group(1)) * (7 if "week" in m.group(2) else 1)
        return date.today() + timedelta(days=n)
    if "tomorrow" in w:
        return date.today() + timedelta(days=1)
    if "today" in w or "tonight" in w:
        return date.today()
    for name, idx in _WEEKDAYS.items():
        if name in w:
            delta = (idx - date.today().weekday()) % 7
            if delta == 0:
                delta = 7  # "Friday" on a Friday means the next one
            return date.today() + timedelta(days=delta)
    from temporal import resolve_temporal
    ranges = resolve_temporal(when)
    return ranges[0].start.date() if ranges else None


async def add_deadline(keeper_repo, text: str, when: str) -> dict:
    """Register a deadline. `when` is natural ('next Friday', 'in 3 days') or ISO.
    Stored in Keeper with a due: tag."""
    due = _parse_due(when)
    if due is None:
        return {"error": f"couldn't understand a date from '{when}'"}
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "deadline"
    await keeper_repo.write(
        f"{DEADLINE_TAG}_{slug}", text.strip(),
        tags=f"{DEADLINE_TAG},due:{due.isoformat()}", confidence="verified",
    )
    return {"text": text.strip(), "due": due.isoformat()}


async def list_deadlines(keeper_repo) -> list[dict]:
    rows = await keeper_repo.query(search=DEADLINE_TAG, limit=100)
    out = []
    for r in rows:
        m = _DUE_RE.search(r.get("tags", ""))
        if not m or not r.get("key", "").startswith(f"{DEADLINE_TAG}_"):
            continue
        out.append({"key": r["key"], "text": r["value"], "due": m.group(1)})
    return sorted(out, key=lambda d: d["due"])


async def remove_deadline(keeper_repo, slug: str) -> bool:
    return await keeper_repo.delete(f"{DEADLINE_TAG}_{slug}")


async def check_deadlines(orchestrator, state: dict) -> list[dict]:
    """Surface deadlines within the lead window, once per deadline per day."""
    if not _on("PROACTIVE_DEADLINES"):
        return []
    keeper_repo = getattr(orchestrator, "keeper_repo", None)
    if keeper_repo is None:
        return []
    today = _now_local().date()
    lead = _lead_days()
    fired_today = state.setdefault("deadline_fired", {})
    surfaced = []
    for d in await list_deadlines(keeper_repo):
        try:
            due = date.fromisoformat(d["due"])
        except ValueError:
            continue
        days = (due - today).days
        if days < 0 or days > lead:
            continue
        marker = f"{d['key']}@{today.isoformat()}"
        if fired_today.get(marker):
            continue
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
        await _surface(orchestrator, f'Deadline: "{d["text"]}" is due {when} ({d["due"]}).')
        fired_today[marker] = True
        surfaced.append(d)
    return surfaced


# ── Predictive suggestions (opt-in) ──────────────────────────────
# Cross-domain "you usually X — want me to Y?" nudges. Off by default because
# they're speculative + cost an LLM call; enable with PROACTIVE_SUGGESTIONS=on.
async def check_suggestions(orchestrator, state: dict) -> str | None:
    if not _on("PROACTIVE_SUGGESTIONS", "off"):
        return None
    if not _within_waking_hours():
        return None
    today = _now_local().date().isoformat()
    if state.get("suggestion_day") == today:   # at most one per day
        return None
    keeper_repo = getattr(orchestrator, "keeper_repo", None)
    llm = getattr(orchestrator, "llm", None)
    if keeper_repo is None or llm is None:
        return None

    profile = await keeper_repo.read("operator_profile")
    profile_txt = (profile or {}).get("value", "")
    cal = ""
    try:
        from google_calendar import upcoming_events
        evs = await upcoming_events(window_minutes=720)
        cal = "; ".join(f"{e['summary']} in {e['minutes_until']}m" for e in evs[:5]) or "nothing soon"
    except Exception:
        pass
    if not profile_txt:
        return None  # nothing learned yet → don't guess

    prompt = (
        "You are R.A.M.B.O. Based ONLY on what you know about the operator and "
        "today's schedule, suggest ONE genuinely helpful, specific proactive action "
        "— or reply exactly 'NONE' if nothing is worth interrupting them for.\n\n"
        f"Operator profile:\n{profile_txt}\n\nToday's calendar: {cal}\n\n"
        "One sentence, spoken voice, no preamble. 'NONE' if unsure."
    )
    try:
        import model_config
        from usage_capture import record_usage
        resp = await llm.messages.create(
            model=model_config.fast_model(), max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            await record_usage(model_config.fast_model(), resp.usage, source="suggestion")
        except Exception:
            pass
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", None) == "text").strip()
    except Exception:
        log.exception("suggestion synthesis failed")
        return None
    state["suggestion_day"] = today  # mark even on NONE so we don't retry all day
    if not text or text.strip().upper().startswith("NONE"):
        return None
    await _surface(orchestrator, text)
    return text


# ── Scheduler ────────────────────────────────────────────────────
def _tick_seconds() -> int:
    try:
        return max(60, int(os.environ.get("PROACTIVE_TICK_SECONDS", "300")))
    except ValueError:
        return 300


async def proactive_scheduler(orchestrator) -> None:
    """Single loop driving idle + deadline nudges. Each is independently gated."""
    state: dict = {}
    log.info("proactive nudges on: idle=%s deadlines=%s",
             _on("PROACTIVE_IDLE"), _on("PROACTIVE_DEADLINES"))
    while True:
        try:
            await check_idle(orchestrator, state)
            await check_deadlines(orchestrator, state)
            await check_suggestions(orchestrator, state)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("proactive tick failed")
        await asyncio.sleep(_tick_seconds())
