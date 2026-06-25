"""Temporal expression resolution.

Turns relative date phrases in a user's text ("yesterday", "this week",
"last 3 days") into explicit [start, end) datetime ranges, so downstream
consumers — the LLM router, the calendar skill, dispatch-history queries —
resolve "what did we do yesterday?" against real dates instead of guessing.

Pure stdlib, no deps. The single entry point is :func:`resolve_temporal`.

Conventions:
  * Ranges are half-open: ``start <= t < end``.
  * Weeks start on Monday.
  * Naive ``now`` → naive bounds; tz-aware ``now`` → tz-aware bounds (the
    tzinfo of ``now`` is preserved).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TemporalRange:
    """A resolved relative phrase and the [start, end) window it denotes."""

    phrase: str          # the matched surface text, e.g. "last week"
    start: datetime
    end: datetime

    def label(self) -> str:
        """Human/LLM-readable one-liner, e.g. 'yesterday: 2026-06-24'."""
        s = self.start.strftime("%Y-%m-%d")
        # For a single-day window, show one date; otherwise show the span.
        if self.end - self.start <= timedelta(days=1):
            return f"{self.phrase}: {s}"
        last = (self.end - timedelta(days=1)).strftime("%Y-%m-%d")
        return f"{self.phrase}: {s} to {last}"


def _day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_start(dt: datetime) -> datetime:
    """Monday 00:00 of the week containing ``dt``."""
    monday = _day_start(dt) - timedelta(days=dt.weekday())
    return monday


def resolve_temporal(text: str, now: datetime | None = None) -> list[TemporalRange]:
    """Find relative date phrases in ``text`` and resolve them against ``now``.

    Returns a list of :class:`TemporalRange`, in first-seen order, de-duplicated
    by phrase. Empty when nothing matches. ``now`` defaults to ``datetime.now()``
    (local, naive) so callers may inject a fixed clock for determinism/tests.
    """
    if not text:
        return []
    if now is None:
        now = datetime.now()

    today = _day_start(now)
    day = timedelta(days=1)
    week_start = _week_start(now)
    lower = text.lower()

    out: list[TemporalRange] = []
    seen: set[str] = set()

    def add(phrase: str, start: datetime, end: datetime) -> None:
        if phrase in seen:
            return
        seen.add(phrase)
        out.append(TemporalRange(phrase=phrase, start=start, end=end))

    # --- "last/past N days" (relative window ending now) ---
    for m in re.finditer(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", lower):
        n = int(m.group(1))
        if n >= 1:
            add(m.group(0), today - (n - 1) * day, today + day)

    # --- single-day phrases ---
    if re.search(r"\btoday\b", lower):
        add("today", today, today + day)
    if re.search(r"\byesterday\b", lower):
        add("yesterday", today - day, today)
    if re.search(r"\btomorrow\b", lower):
        add("tomorrow", today + day, today + 2 * day)

    # --- parts of today ---
    if re.search(r"\bthis morning\b", lower):
        add("this morning", today, today + timedelta(hours=12))
    if re.search(r"\bthis afternoon\b", lower):
        add("this afternoon", today + timedelta(hours=12), today + timedelta(hours=17))
    if re.search(r"\b(?:this evening|tonight)\b", lower):
        m = re.search(r"\b(this evening|tonight)\b", lower)
        add(m.group(1), today + timedelta(hours=17), today + day)

    # --- week phrases (Monday-anchored) ---
    if re.search(r"\blast week\b", lower):
        add("last week", week_start - 7 * day, week_start)
    if re.search(r"\bnext week\b", lower):
        add("next week", week_start + 7 * day, week_start + 14 * day)
    # "this week" / bare "week" — only after the more specific last/next checks.
    if re.search(r"\bthis week\b", lower):
        add("this week", week_start, week_start + 7 * day)

    return out


def format_temporal_context(ranges: list[TemporalRange]) -> str:
    """One-line-per-phrase block for injection into an LLM prompt, or ''."""
    if not ranges:
        return ""
    lines = "\n".join(f"  - {r.label()}" for r in ranges)
    return "RESOLVED DATES (interpret relative references against these):\n" + lines
