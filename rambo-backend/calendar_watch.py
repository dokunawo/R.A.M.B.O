"""Proactive calendar watch — Phase 2 (proactive intelligence).

Polls the calendar on a cadence and, when a TIMED event is approaching the
configurable lead window, proactively nudges the operator: shows an on-screen
card, speaks it (ElevenLabs), and logs it. Each event is nudged once.

The nudge text is built dynamically from the real event (title, minutes
remaining, location) — it is NOT a fixed string. "Meeting in 20 minutes, leave
now" was only an example; what's actually said reflects the event.

Env:
  PROACTIVE_CALENDAR     "on"/"off" — enable the watch loop (default "on")
  CALENDAR_LEAD_MINUTES  nudge when an event starts within this many minutes (default 20)
  CALENDAR_POLL_SECONDS  how often to poll the calendar (default 120)
  CALENDAR_SPEAK         "on"/"off" — speak the nudge via ElevenLabs (default "on")
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("rambo.calendar_watch")

DISPLAY_AGENT = "pilot"  # proactive nudges show under Pilot (the dispatcher)


def _enabled() -> bool:
    return os.environ.get("PROACTIVE_CALENDAR", "on").strip().lower() not in ("off", "0", "false")


def _lead_minutes() -> int:
    try:
        return max(1, int(os.environ.get("CALENDAR_LEAD_MINUTES", "20")))
    except ValueError:
        return 20


def _poll_seconds() -> int:
    try:
        return max(30, int(os.environ.get("CALENDAR_POLL_SECONDS", "120")))
    except ValueError:
        return 120


def _speak_enabled() -> bool:
    return os.environ.get("CALENDAR_SPEAK", "on").strip().lower() not in ("off", "0", "false")


def compose_nudge(event: dict) -> str:
    """Build a natural, DYNAMIC heads-up from a real event. Phrasing varies by how
    soon it is; the title/location/time come straight from the event."""
    title = (event.get("summary") or "an event").strip()
    mins = int(event.get("minutes_until", 0))
    location = (event.get("location") or "").strip()

    if mins <= 0:
        when = "is starting now"
    elif mins == 1:
        when = "starts in 1 minute"
    else:
        when = f"starts in {mins} minutes"

    msg = f'Heads up — "{title}" {when}.'
    if location:
        msg += f" It's at {location}."
    return msg


async def _deliver(orchestrator, event: dict) -> None:
    msg = compose_nudge(event)
    # (1) On-screen card + activity log line.
    try:
        await orchestrator._response(DISPLAY_AGENT, msg)
        await orchestrator.broadcast(f"[{DISPLAY_AGENT.capitalize()}] {msg}")
    except Exception:
        log.exception("calendar nudge display failed")
    # (2) Speak it (ElevenLabs), best-effort.
    if _speak_enabled():
        try:
            await orchestrator._voice_text(msg)
        except Exception:
            log.exception("calendar nudge speech failed")


async def check_once(orchestrator, notified: set[str] | None = None) -> list[dict]:
    """One poll: nudge any event entering the lead window that we haven't nudged
    yet. Returns the events nudged this pass. `notified` tracks event ids across
    polls so each event fires once."""
    if notified is None:
        notified = set()
    lead = _lead_minutes()
    try:
        from google_calendar import upcoming_events
        events = await upcoming_events(window_minutes=lead)
    except Exception:
        log.info("calendar watch: calendar unavailable")
        return []

    fired = []
    seen_ids = set()
    for ev in events:
        eid = ev.get("id") or f"{ev.get('summary')}@{ev.get('start')}"
        seen_ids.add(eid)
        if ev.get("minutes_until", 999) <= lead and eid not in notified:
            await _deliver(orchestrator, ev)
            notified.add(eid)
            fired.append(ev)
    # Forget events that have passed out of the window so a recurring slot can
    # nudge again next time it comes around.
    for stale in [i for i in notified if i not in seen_ids]:
        notified.discard(stale)
    return fired


async def calendar_watch_scheduler(orchestrator) -> None:
    """Poll the calendar every CALENDAR_POLL_SECONDS and nudge approaching events.
    Runs forever; disabled cleanly when PROACTIVE_CALENDAR=off."""
    if not _enabled():
        log.info("calendar watch disabled (PROACTIVE_CALENDAR=off)")
        return
    notified: set[str] = set()
    log.info("calendar watch on: lead=%dm poll=%ds", _lead_minutes(), _poll_seconds())
    while True:
        try:
            await check_once(orchestrator, notified)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("calendar watch poll failed")
        await asyncio.sleep(_poll_seconds())
