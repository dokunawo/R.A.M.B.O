"""Proactive to-do nudges: once per calendar day, speak any open task that's due
today or overdue. Mirrors calendar_watch.py's shape and delivery calls exactly.

Env:
  PROACTIVE_TODOS       "on"/"off" — enable the watch loop (default "on")
  TODOS_POLL_SECONDS    how often to poll (default 300)
  TODOS_SPEAK           "on"/"off" — speak the nudge via ElevenLabs (default "on")
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

import todos_skill

log = logging.getLogger("rambo.todos_watch")

DISPLAY_AGENT = "keeper"


def _enabled() -> bool:
    return os.environ.get("PROACTIVE_TODOS", "on").strip().lower() not in ("off", "0", "false")


def _poll_seconds() -> int:
    try:
        return max(60, int(os.environ.get("TODOS_POLL_SECONDS", "300")))
    except ValueError:
        return 300


def _speak_enabled() -> bool:
    return os.environ.get("TODOS_SPEAK", "on").strip().lower() not in ("off", "0", "false")


def _today_str() -> str:
    return date.today().isoformat()


def compose_nudge(task: dict) -> str:
    due = task.get("due_date") or ""
    today = _today_str()
    when = "is due today" if due == today else f"was due {due}"
    return f'Heads up — "{task["text"]}" {when}.'


async def _deliver(orchestrator, task: dict) -> None:
    msg = compose_nudge(task)
    try:
        await orchestrator._response(DISPLAY_AGENT, msg)
        await orchestrator.broadcast(f"[{DISPLAY_AGENT.capitalize()}] {msg}")
    except Exception:
        log.exception("todo nudge display failed")
    if _speak_enabled():
        try:
            await orchestrator._voice_text(msg)
        except Exception:
            log.exception("todo nudge speech failed")


async def check_once(orchestrator, notified_today: set[int] | None = None,
                     today: str | None = None) -> list[dict]:
    """One poll: nudge any open task due today or overdue that hasn't been
    notified yet TODAY. `notified_today` is cleared by the caller when the date
    rolls over (see the scheduler below) so an overdue task re-nudges once daily."""
    if notified_today is None:
        notified_today = set()
    repo = todos_skill.get_repo()
    if repo is None:
        return []
    today = today or _today_str()
    try:
        due = await repo.due_on_or_before(today)
    except Exception:
        log.exception("todos watch: repo unavailable")
        return []
    fired = []
    for t in due:
        if t["id"] not in notified_today:
            await _deliver(orchestrator, t)
            notified_today.add(t["id"])
            fired.append(t)
    return fired


async def todos_watch_scheduler(orchestrator) -> None:
    """Poll every TODOS_POLL_SECONDS; re-arm the notified set at each new day so a
    still-open overdue task nudges again once daily until completed."""
    if not _enabled():
        log.info("todos watch disabled (PROACTIVE_TODOS=off)")
        return
    notified: set[int] = set()
    last_day = _today_str()
    log.info("todos watch on: poll=%ds", _poll_seconds())
    while True:
        try:
            today = _today_str()
            if today != last_day:
                notified.clear()
                last_day = today
            await check_once(orchestrator, notified, today=today)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("todos watch poll failed")
        await asyncio.sleep(_poll_seconds())
