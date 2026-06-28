"""Operator greeting — a Jarvis-style boot greeting.

Assembles the real situation (time of day, what's pending, the next calendar
event, near deadlines) and has RAMBO phrase it in one or two spoken sentences.
Reuses the proactive pending/deadline helpers and the calendar so the greeting
reflects what actually needs the operator.

Env:
  RAMBO_OPERATOR_NAME  what RAMBO calls you (default "Daniel")
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime

log = logging.getLogger("rambo.greeting")


def _part_of_day(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _operator_name() -> str:
    from operator_identity import address
    return address()


def _now_local() -> datetime:
    """Local time for the greeting, so 'morning/evening' matches the operator's
    clock rather than the container's UTC. Shares PROACTIVE_TZ with the nudges."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(os.environ.get("PROACTIVE_TZ", "America/Detroit")))
    except Exception:
        return datetime.now()


async def _gather(orchestrator) -> dict:
    from proactive_nudges import _pending_parts, list_deadlines
    facts: dict = {"pending": [], "next_event": None, "deadlines": []}
    try:
        facts["pending"] = await _pending_parts(orchestrator)
    except Exception:
        pass
    try:
        from google_calendar import upcoming_events
        evs = await upcoming_events(window_minutes=720)  # next 12h
        facts["next_event"] = evs[0] if evs else None
    except Exception:
        pass
    kr = getattr(orchestrator, "keeper_repo", None)
    if kr:
        try:
            today = date.today()
            for d in await list_deadlines(kr):
                try:
                    if 0 <= (date.fromisoformat(d["due"]) - today).days <= 3:
                        facts["deadlines"].append(d)
                except ValueError:
                    pass
        except Exception:
            pass
    return facts


def _fact_bits(facts: dict) -> list[str]:
    bits = []
    ev = facts.get("next_event")
    if ev:
        bits.append(f"next up: \"{ev['summary']}\" in {ev['minutes_until']} minutes")
    if facts.get("pending"):
        bits.append("waiting on you: " + ", ".join(facts["pending"]))
    if facts.get("deadlines"):
        bits.append("deadlines soon: "
                    + ", ".join(f"{d['text']} due {d['due']}" for d in facts["deadlines"]))
    return bits


async def generate_greeting(orchestrator) -> str:
    greet, name = _part_of_day(_now_local().hour), _operator_name()
    facts = await _gather(orchestrator)
    bits = _fact_bits(facts)

    llm = getattr(orchestrator, "llm", None)
    if llm and bits:
        prompt = (
            f"You are R.A.M.B.O greeting your operator the moment the console boots. "
            f"Time of day: {greet}. Operator's name: {name}. "
            f"What's true right now: {'; '.join(bits)}. "
            "Write a 1-2 sentence SPOKEN greeting in R.A.M.B.O's voice — sharp, "
            "confident, a little warm, zero filler. Greet them by name and tell them "
            "what actually needs them. Plain text only, no markdown."
        )
        try:
            import model_config
            from usage_capture import record_usage
            resp = await llm.messages.create(
                model=model_config.fast_model(), max_tokens=220,
                messages=[{"role": "user", "content": prompt}],
            )
            try:
                await record_usage(model_config.fast_model(), resp.usage, source="greeting")
            except Exception:
                pass
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", None) == "text").strip()
            if text:
                return text
        except Exception:
            log.exception("greeting synthesis failed")

    # Template fallback (no LLM or nothing pending).
    base = f"{greet}, {name}."
    if bits:
        return base + " " + " ".join(b[0].upper() + b[1:] + "." for b in bits)
    return base + " All quiet — standing by."


async def generate_farewell(orchestrator) -> str:
    """Spoken sign-off for the shutdown sequence — mirrors generate_greeting but
    closes the session. Nothing is actually killed; this is the cinematic farewell
    before the console drops to standby."""
    name = _operator_name()
    hour = _now_local().hour
    sign = "Good night" if (hour >= 21 or hour < 5) else "Goodbye"
    facts = await _gather(orchestrator)
    pending = facts.get("pending") or []

    llm = getattr(orchestrator, "llm", None)
    if llm:
        note = ("Still waiting on the operator: " + ", ".join(pending) + "."
                if pending else "All quiet — nothing outstanding.")
        prompt = (
            f"You are R.A.M.B.O signing off as your operator shuts the console down "
            f"for now. Operator's name: {name}. {note} "
            "Write a 1-2 sentence SPOKEN farewell in R.A.M.B.O's voice — sharp, "
            "confident, a little warm. Say goodbye by name, note you'll be on "
            "standby, and if something's still waiting mention it briefly. Plain "
            "text only, no markdown."
        )
        try:
            import model_config
            from usage_capture import record_usage
            resp = await llm.messages.create(
                model=model_config.fast_model(), max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            try:
                await record_usage(model_config.fast_model(), resp.usage, source="farewell")
            except Exception:
                pass
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", None) == "text").strip()
            if text:
                return text
        except Exception:
            log.exception("farewell synthesis failed")

    # Template fallback.
    base = f"{sign}, {name}. Powering down to standby."
    if pending:
        base += " For when you're back: " + ", ".join(pending) + "."
    return base
