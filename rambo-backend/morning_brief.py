"""Recurring morning brief.

Composes a daily brief (date + today's calendar + doctrine priorities when a
north-star doc exists), then (1) displays it on screen as an Architect response
card via the activity WebSocket and (2) emails it through Echo when SMTP is
configured. A background scheduler fires it once a day at MORNING_BRIEF_TIME.

Env:
  MORNING_BRIEF_TIME  "HH:MM" local time to send (default 07:00)
  MORNING_BRIEF_TZ    IANA tz for that time (default America/Detroit)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

log = logging.getLogger("rambo.morning_brief")

DISPLAY_AGENT = "architect"   # whose card the brief shows under on screen


async def generate_brief() -> str:
    now = datetime.now()
    parts = [f"☀️ Morning Brief — {now.strftime('%A, %B %d, %Y')}"]

    # Today's calendar (Google, server-side; skipped gracefully if unavailable).
    try:
        from google_calendar import calendar_skill
        cal = await calendar_skill("what's on my calendar today", {})
        if cal and cal.strip():
            parts.append("\n📅 Today\n" + cal.strip())
    except Exception as e:
        log.info("brief: calendar unavailable (%s)", e)

    # Doctrine priorities (only if a valid north-star doc exists).
    try:
        from chief_of_staff import chief_of_staff_skill
        cos = await chief_of_staff_skill("morning brief", {})
        if cos and "north-star" not in cos.lower() and "invalid or missing" not in cos.lower():
            parts.append("\n🎯 Priorities\n" + cos.strip())
    except Exception as e:
        log.info("brief: chief-of-staff unavailable (%s)", e)

    parts.append("\n— R.A.M.B.O, standing by.")
    return "\n".join(parts)


async def run_brief(orchestrator) -> str:
    """Generate the brief, show it on screen, and email it. Returns the text."""
    brief = await generate_brief()

    # (1) On-screen card via the activity WebSocket.
    try:
        await orchestrator._response(DISPLAY_AGENT, brief)
        await orchestrator.broadcast(f"[{DISPLAY_AGENT.capitalize()}] Morning brief delivered.")
    except Exception:
        log.exception("brief: on-screen display failed")

    # (2) Email via Echo (best-effort).
    try:
        from echo_messaging import send_email, is_configured
        if is_configured():
            subject = f"R.A.M.B.O Morning Brief — {datetime.now().strftime('%b %d')}"
            send_email(subject=subject, body=brief)
    except Exception:
        log.exception("brief: email failed")

    return brief


def _brief_time() -> tuple[int, int]:
    raw = os.environ.get("MORNING_BRIEF_TIME", "07:00").strip()
    try:
        hh, mm = (int(x) for x in raw.split(":")[:2])
        return hh, mm
    except Exception:
        return 7, 0


def _now_local() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(os.environ.get("MORNING_BRIEF_TZ", "America/Detroit")))
    except Exception:
        return datetime.now()


async def brief_scheduler(orchestrator) -> None:
    """Fire run_brief once per day at the configured local time. Runs forever."""
    while True:
        hh, mm = _brief_time()
        now = _now_local()
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        wait = max(1.0, (nxt - now).total_seconds())
        log.info("Next morning brief at %s (%.0f min)", nxt.isoformat(), wait / 60)
        try:
            await asyncio.sleep(wait)
            await run_brief(orchestrator)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("morning brief run failed")
            await asyncio.sleep(60)   # avoid a tight error loop
