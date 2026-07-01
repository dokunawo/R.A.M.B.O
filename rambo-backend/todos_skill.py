"""Deterministic (no LLM) to-do list skill: add / list / complete / delete, with
priority, due dates (via temporal.resolve_temporal), and recurrence. See the
"Boundary note" in docs/superpowers/plans/2026-06-30-tasks-todo-manager.md for why
this is a distinct concept from the existing watchlist "deadlines"."""
from __future__ import annotations

import difflib
import re
from datetime import date, datetime

from temporal import resolve_temporal

_DOW_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_ADD_RE = re.compile(
    r"\b(add a task(?: to)?|add task(?: to)?|new task(?: to)?|remind me to|"
    r"i need to|i have to|i've got to|ive got to|put .+ on my (?:to-?do )?list)\b",
    re.IGNORECASE)
# "put X on my (to-do )?list" is an unambiguous ADD trigger, but its own trailing
# "...list" text also satisfies _LIST_RE's bare "to-?do list"/"task list"
# alternatives (e.g. "put call mom on my to-do list"). Checked FIRST, before the
# general complete/delete/list/add order below, so this one phrasing never loses
# to the general LIST check.
_PUT_ADD_RE = re.compile(r"^put\s+.+\s+on my (?:to-?do )?list\b", re.IGNORECASE)
_LIST_RE = re.compile(
    r"\b(what'?s on my list|my tasks|task list|to-?do list|what do i need to do|"
    r"what'?s on my to-?do list)\b", re.IGNORECASE)
_COMPLETE_RE = re.compile(
    r"\b(mark .+ (?:as )?done|complete\b|finished\b|check off|i did\b)\b", re.IGNORECASE)
_DELETE_RE = re.compile(
    r"\b(remove .+ task|delete .+ task|drop .+ (?:from my )?list)\b", re.IGNORECASE)

_HIGH_RE = re.compile(r"\b(urgent|important|asap|critical|high priority)\b", re.IGNORECASE)
_LOW_RE = re.compile(r"\b(low priority|whenever|someday|no rush)\b", re.IGNORECASE)

_DAILY_RE = re.compile(r"\b(every ?day|daily)\b", re.IGNORECASE)
_WEEKDAYS_RE = re.compile(r"\b(every ?weekday|weekdays)\b", re.IGNORECASE)
_WEEKLY_NAMED_RE = re.compile(
    r"\bevery (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_WEEKLY_BARE_RE = re.compile(r"\b(every ?week|weekly)\b", re.IGNORECASE)
_MONTHLY_RE = re.compile(r"\b(every ?month|monthly)\b", re.IGNORECASE)


def detect_intent(goal: str) -> str | None:
    g = goal or ""
    if _PUT_ADD_RE.search((g or "").strip()):
        return "add"
    # Complete/delete/list are checked before add: "add" triggers are broader and
    # some phrasing overlaps ("i need to" vs "i did"), so the more specific,
    # action-on-existing-item intents win first.
    if _COMPLETE_RE.search(g):
        return "complete"
    if _DELETE_RE.search(g):
        return "delete"
    if _LIST_RE.search(g):
        return "list"
    if _ADD_RE.search(g):
        return "add"
    if _LIST_RE.search(g):
        return "list"
    return None


def extract_priority(text: str) -> str:
    if _HIGH_RE.search(text or ""):
        return "high"
    if _LOW_RE.search(text or ""):
        return "low"
    return "normal"


def extract_recurrence(text: str, now: date | None = None) -> str | None:
    t = text or ""
    if _DAILY_RE.search(t):
        return "daily"
    if _WEEKDAYS_RE.search(t):
        return "weekdays"
    m = _WEEKLY_NAMED_RE.search(t)
    if m:
        return f"weekly:{m.group(1).lower()}"
    if _WEEKLY_BARE_RE.search(t):
        dow = _DOW_NAMES[(now or date.today()).weekday()]
        return f"weekly:{dow}"
    if _MONTHLY_RE.search(t):
        return "monthly"
    return None


def extract_due(text: str, now: datetime | None = None) -> tuple[str | None, str | None]:
    ranges = resolve_temporal(text or "", now=now)
    if not ranges:
        return None, None
    r = ranges[0]
    return r.start.date().isoformat(), r.phrase


def clean_task_text(intent: str, text: str, due_phrase: str | None = None,
                    priority_phrase: str | None = None) -> str:
    t = text or ""
    if intent == "add":
        m = re.search(r"put\s+(.+?)\s+on my (?:to-?do )?list", t, re.IGNORECASE)
        if m:
            t = m.group(1)
        else:
            t = _ADD_RE.sub("", t, count=1)
    if due_phrase:
        t = re.sub(re.escape(due_phrase), "", t, flags=re.IGNORECASE)
    if priority_phrase:
        t = re.sub(re.escape(priority_phrase), "", t, flags=re.IGNORECASE)
    t = re.sub(r"^[\s,:.\-]+|[\s,:.\-]+$", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


_COMPLETE_WRAP_RE = re.compile(r"mark\s+(.+?)\s+(?:as\s+)?done\b", re.IGNORECASE)
_COMPLETE_PREFIX_RE = re.compile(
    r"^(?:complete|finished|check off|i did)\s+(?:the\s+)?(.+)$", re.IGNORECASE)
_DELETE_TARGET_RE = re.compile(
    r"^(?:remove|delete|drop)\s+(?:the\s+)?(.+?)"
    r"(?:\s+task|\s+from my (?:to-?do )?list)?$", re.IGNORECASE)


def extract_target_phrase(intent: str, text: str) -> str:
    """The spoken task-NAME portion of a complete/delete utterance, with the
    trigger phrase and any trailing 'task'/'from my list' wrapper stripped.

    Deliberately NOT implemented as re.sub(the broad intent-detection regex, "",
    text): that regex's `.+` wildcard is written to DETECT the intent (it doesn't
    care what it consumes), and blindly substituting it over the whole utterance
    can eat the task name itself. E.g. "mark call as done" — the broad complete
    regex `mark .+ (?:as )?done` matches the ENTIRE string (since "call" can
    satisfy the wildcard just as well as any longer phrase), so re.sub-ing it away
    leaves an EMPTY spoken string — silently breaking fuzzy match / the ambiguous-
    match ask. This function uses a NON-GREEDY, narrowly-scoped capture group
    instead, so "call" is captured, not consumed."""
    t = (text or "").strip()
    if intent == "complete":
        m = _COMPLETE_WRAP_RE.search(t)
        if m:
            return m.group(1).strip()
        m = _COMPLETE_PREFIX_RE.search(t)
        return m.group(1).strip() if m else t
    if intent == "delete":
        m = _DELETE_TARGET_RE.search(t)
        return m.group(1).strip() if m else t
    return t


def find_match(spoken: str, open_tasks: list[dict]) -> tuple[dict | None, list[dict]]:
    """(single_match, candidates). Substring containment first (either direction);
    falls back to a fuzzy close-match. Ambiguous or no hit -> match is None."""
    spoken_l = (spoken or "").lower().strip()
    if not spoken_l:
        return None, []
    contains = [t for t in open_tasks
               if spoken_l in t["text"].lower() or t["text"].lower() in spoken_l]
    if len(contains) == 1:
        return contains[0], []
    if len(contains) > 1:
        return None, contains
    texts = [t["text"] for t in open_tasks]
    # 0.5 lets "clean the garage" fuzzy-match "call the vet" (actual SequenceMatcher
    # ratio 0.571 > 0.5) — a real false positive, confirmed by running difflib
    # directly, not by hand-estimating the ratio. 0.6 is the verified-correct value.
    close = difflib.get_close_matches(spoken, texts, n=3, cutoff=0.6)
    matches = [t for t in open_tasks if t["text"] in close]
    if len(matches) == 1:
        return matches[0], []
    return None, matches
