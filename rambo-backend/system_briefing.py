"""System Briefing — the boot briefing + the on-demand "catch me up" update.

One composer backs both: `gather_briefing()` collects best-effort sections (a
failed section is omitted, never raised); `render_full()` is the on-screen boot
card (deterministic markdown, no LLM) and `render_concise()` is the short spoken
update. Strictly read-only — the only thing written anywhere is the tiny
`data/boot_state.json` "last boot" timestamp (never the repo).

Reuses existing pieces rather than reinventing them:
  - codebase_skill._git        → read-only git for recent changes / dirty check
  - greeting._now_local        → operator-local clock (America/Detroit)
  - skills.weather_skill       → Open-Meteo weather (no key)
  - proactive_nudges._pending_parts → what's waiting on the operator
  - google_calendar.upcoming_events → today's events
  - chief_of_staff helpers     → north-star target + staleness
  - usage_dashboard.get_dashboard   → today's API cost
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Module-level orchestrator handle (set at startup, mirrors dev_agent.set_dev_agent).
# Sections that need it degrade gracefully when it's None.
_ORCH = None


def set_orchestrator(orch) -> None:
    global _ORCH
    _ORCH = orch


# ── "since last boot" state (data/boot_state.json) ──────────────────────────
def _state_path() -> Path:
    return Path(os.environ.get("RAMBO_DATA_DIR", "data")) / "boot_state.json"


def _read_last_boot() -> str | None:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8")).get("last_boot")
    except Exception:
        return None


def _write_last_boot(ts: str) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_boot": ts}), encoding="utf-8")


# ── recent changes (git) ────────────────────────────────────────────────────
def _cap_commits(out: str) -> list[str]:
    n = int(os.environ.get("RAMBO_CHANGES_MAX", "15"))
    return [ln.strip() for ln in out.splitlines() if ln.strip()][:n]


async def _changes_since(since_iso: str | None) -> list[str]:
    """Commits to show. If a prior boot is known, show what changed since then
    (empty = nothing new, which is the honest answer). Otherwise fall back to the
    last 24h, then the last N commits."""
    from codebase_skill import _git
    fmt = "--format=%h %s (%cr)"
    if since_iso:
        rc, out = await _git("log", "--no-merges", f"--since={since_iso}", fmt)
        if rc == 0:
            return _cap_commits(out)            # may be empty — correct
    lookback = os.environ.get("RAMBO_CHANGES_LOOKBACK", "24 hours ago")
    rc, out = await _git("log", "--no-merges", f"--since={lookback}", fmt)
    if rc == 0 and out.strip():
        return _cap_commits(out)
    rc, out = await _git("log", "--no-merges", "-n",
                         os.environ.get("RAMBO_CHANGES_MAX", "15"), fmt)
    return _cap_commits(out) if rc == 0 else []


async def _uncommitted_count() -> int | None:
    from codebase_skill import _git
    rc, out = await _git("status", "--porcelain")
    if rc != 0:
        return None
    return len([ln for ln in out.splitlines() if ln.strip()])


# ── suggested roadmap tasks (parse the planning docs) ───────────────────────
def _repo_root() -> Path:
    return Path(os.environ.get("RAMBO_REPO_ROOT", "/repo"))


def _read_doc(name: str) -> str:
    try:
        return (_repo_root() / name).read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_section(text: str, heading: str) -> str:
    """Body under a `##`/`###` heading matching `heading`, up to the next heading.
    (chief_of_staff's extractor only matches level-2 `##`; ROADMAP/HANDOFF use
    level-3, so we accept 1-4 `#`.)"""
    m = re.search(rf'^#{{1,4}}\s+.*{re.escape(heading)}.*$', text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r'^#{1,4}\s+', text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    return text[start:end].strip()


def _clean_md(s: str) -> str:
    """Strip markdown emphasis/code/links so a task reads cleanly when spoken."""
    s = re.sub(r"[*`#]+", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)   # [text](url) -> text
    return s.strip()


def _bullets(section: str) -> list[str]:
    return [_clean_md(ln.lstrip("-* ")) for ln in section.splitlines() if ln.strip().startswith(("-", "*"))]


def _suggested_tasks(limit: int = 4) -> list[str]:
    tasks = _bullets(_extract_section(_read_doc("ROADMAP.md"), "Short term"))
    next_action = _extract_section(_read_doc("HANDOFF.md"), "Next action")
    if next_action:
        first = next((_clean_md(ln) for ln in next_action.splitlines() if ln.strip()), "")
        if first:
            tasks.insert(0, f"(HANDOFF) {first}")
    # de-dup, keep order, cap
    seen, out = set(), []
    for t in tasks:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:limit]


# ── weather ─────────────────────────────────────────────────────────────────
async def _weather(ctx: dict | None) -> str:
    from skills import weather_skill
    if ctx and ctx.get("lat") and ctx.get("lon"):
        return await weather_skill("weather", ctx)        # browser coords win
    city = os.environ.get("RAMBO_HOME_CITY", "Detroit")
    return await weather_skill(f"weather in {city}", {})


# ── orchestrator-dependent sections (degrade if unset) ──────────────────────
async def _pending(orch) -> list[str]:
    if not orch:
        return []
    try:
        from proactive_nudges import _pending_parts
        return await _pending_parts(orch)
    except Exception:
        return []


async def _calendar_today() -> list[dict]:
    from google_calendar import upcoming_events
    return await upcoming_events(window_minutes=720)


def _doctrine() -> dict | None:
    from chief_of_staff import _find_doctrine, _parse_frontmatter, _staleness_check
    p = _find_doctrine()
    if not p:
        return None
    fm = _parse_frontmatter(p.read_text(encoding="utf-8"))
    if not fm:
        return None
    return {"target": fm.get("target"), "stale": _staleness_check(fm)}


def _health() -> dict | None:
    import psutil
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return {"cpu": psutil.cpu_percent(interval=None), "ram": vm.percent, "disk": du.percent}


async def _cost_today() -> dict | None:
    import usage_capture
    from usage_dashboard import get_dashboard
    repo = getattr(usage_capture, "_repo", None)
    if not repo:
        return None
    return (await get_dashboard(repo)).get("today")


# ── gather ──────────────────────────────────────────────────────────────────
async def _safe(coro):
    try:
        return await coro
    except Exception:
        return None


def _safe_sync(fn):
    try:
        return fn()
    except Exception:
        return None


async def gather_briefing(orchestrator=None, ctx: dict | None = None) -> dict:
    """Collect every section best-effort. Each section is independent; a failure
    omits that section rather than breaking the briefing."""
    orch = orchestrator if orchestrator is not None else _ORCH
    from greeting import _now_local, _part_of_day, _operator_name
    now = _now_local()
    data: dict = {
        "date": now.strftime("%A, %B %d, %Y"),
        "time": now.strftime("%-I:%M %p") if os.name != "nt" else now.strftime("%I:%M %p").lstrip("0"),
        "greet": _part_of_day(now.hour),
        "name": _safe_sync(_operator_name) or "Operator",
        "changes": await _safe(_changes_since(_read_last_boot())) or [],
        "uncommitted": await _safe(_uncommitted_count()),
        "tasks": _safe_sync(_suggested_tasks) or [],
        "weather": await _safe(_weather(ctx)),
        "pending": await _safe(_pending(orch)) or [],
        "calendar": await _safe(_calendar_today()) or [],
        "doctrine": _safe_sync(_doctrine),
        "health": _safe_sync(_health),
        "cost": await _safe(_cost_today()),
    }
    return data


# ── render ──────────────────────────────────────────────────────────────────
def render_full(data: dict) -> str:
    """Deterministic on-screen boot card (markdown). No LLM."""
    L: list[str] = [f"# System Briefing — {data.get('date', '')}  ·  {data.get('time', '')}"]

    changes = data.get("changes") or []
    L.append("\n**Recent changes**")
    if changes:
        L += [f"  - {c}" for c in changes]
    else:
        L.append("  - Nothing new since your last session.")

    tasks = data.get("tasks") or []
    if tasks:
        L.append("\n**Suggested next targets**")
        L += [f"  - {t}" for t in tasks]

    if data.get("weather"):
        L.append("\n**Weather**")
        L += [f"  {ln}" for ln in str(data["weather"]).splitlines() if ln.strip()]

    pending = data.get("pending") or []
    if pending:
        L.append("\n**Waiting on you**")
        L += [f"  - {p}" for p in pending]

    unc = data.get("uncommitted")
    if unc:
        L.append(f"\n⚠️ {unc} uncommitted file(s) in the repo.")

    cal = data.get("calendar") or []
    if cal:
        L.append("\n**Today**")
        L += [f"  - {e.get('summary', '(event)')} — in {e.get('minutes_until', '?')} min" for e in cal[:4]]

    doc = data.get("doctrine")
    if doc and doc.get("target"):
        L.append(f"\n**North star:** {doc['target']}")
        if doc.get("stale"):
            L.append(f"  {doc['stale']}")

    h, c = data.get("health"), data.get("cost")
    bits = []
    if h:
        bits.append(f"CPU {h['cpu']:.0f}% · RAM {h['ram']:.0f}% · disk {h['disk']:.0f}%")
    if c:
        bits.append(f"API today ${c.get('cost_usd', 0):.2f} ({c.get('call_count', 0)} calls)")
    if bits:
        L.append("\n**System:** " + "  ·  ".join(bits))

    return "\n".join(L)


def _spoken_weather(w: str | None) -> str:
    """Flatten the multi-line weather block into one spoken clause.
    "Weather — Detroit, MI (US)\\n  partly cloudy\\n  64°F …" →
    "Weather in Detroit, MI (US): partly cloudy, 64°F, …"."""
    if not w:
        return ""
    lines = [ln.strip() for ln in str(w).splitlines() if ln.strip()]
    if not lines:
        return ""
    place = re.sub(r"^weather\s*[—\-:]\s*", "", lines[0], flags=re.IGNORECASE).strip()
    rest = ", ".join(lines[1:]).replace("·", ",")
    rest = re.sub(r"\s*,\s*(?:,\s*)*", ", ", rest)   # tidy spacing + drop doubled commas
    rest = re.sub(r"\s{2,}", " ", rest).strip().strip(",").strip()
    if place and rest:
        return f"Weather in {place}: {rest}."
    return f"Weather: {rest or place}." if (rest or place) else ""


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _today_phrase(date: str | None) -> str:
    """'Sunday, June 28, 2026' -> 'Today is Sunday, June 28th.' (drop the year,
    ordinalize the day — reads naturally aloud)."""
    if not date:
        return ""
    d = re.sub(r",?\s*\d{4}\s*$", "", date).strip()              # drop the year
    m = re.search(r"\b(\d{1,2})\b", d)
    if m:
        d = d[:m.start()] + _ordinal(int(m.group(1))) + d[m.end():]
    return f"Today is {d}." if d else ""


def _clean_task(t: str) -> str:
    """Reduce a roadmap/HANDOFF target to a short spoken phrase — drop the
    '(HANDOFF)' tag, doc/section references (§2a, ROADMAP.md), and keep only the
    first clause so it doesn't read like a paragraph."""
    t = re.sub(r"^\(HANDOFF\)\s*", "", t)
    t = re.split(r"\s+[—–-]\s+|(?<=[a-z])\.\s", t)[0]            # first clause/sentence
    t = re.sub(r"\bsee\s+§?\s*\w[\w.\s]*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"§\s*\w+|\bROADMAP(?:\.md)?\b|\bHANDOFF\.md\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(active thread|next action|next)\s*[:\-]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" .,:;—–-")
    return (t[:70].rsplit(" ", 1)[0] + "…") if len(t) > 70 else t


def _weather_ok(w: str | None) -> bool:
    """True only for a real reading — skip error/placeholder strings so the voice
    never reads 'I couldn't resolve a location…'."""
    if not w:
        return False
    low = str(w).lower()
    return not any(s in low for s in ("couldn't", "could not", "try \"weather", "allow location"))


def render_concise(data: dict, include_greeting: bool = True) -> str:
    """Spoken briefing — short, natural, flowing. Greeting + 'Today is …', what
    changed, weather (only if real), the single top focus (cleaned of roadmap
    cruft), calendar, what's waiting, an uncommitted nudge, the north-star goal,
    and a one-line system health readout.

    `include_greeting=False` drops the "{greet}, {name}." opener (keeping just the
    'Today is …' date phrase) — used by the boot path, where /greeting already
    greets the operator, so the two utterances don't double up the greeting."""
    out: list[str] = []

    greet, name = data.get("greet"), data.get("name")
    today = _today_phrase(data.get("date"))
    if include_greeting and greet and name:
        out.append(f"{greet}, {name}." + (f" {today}" if today else ""))
    elif today:
        out.append(today)

    changes = data.get("changes") or []
    if changes:
        n = len(changes)
        out.append(f"{n} change{'s' if n != 1 else ''} landed since you were last "
                   f"here. The latest is {changes[0]}.")
    else:
        out.append("Nothing new since you were last here.")

    if _weather_ok(data.get("weather")):
        out.append(_spoken_weather(data.get("weather")))

    # Just the single top target, cleaned — not the whole roadmap list.
    for t in (data.get("tasks") or []):
        focus = _clean_task(t)
        if focus:
            out.append(f"Your main focus: {focus}.")
            break

    cal = data.get("calendar") or []
    if cal:
        evs = [f"{e.get('summary', 'an event')} in {e.get('minutes_until', '?')} minutes"
               for e in cal[:3]]
        out.append("On your calendar: " + ", ".join(evs) + ".")

    pending = data.get("pending") or []
    if pending:
        out.append(f"Waiting on you: {', '.join(pending)}.")

    unc = data.get("uncommitted")
    if unc:
        out.append(f"And there {'is' if unc == 1 else 'are'} {unc} uncommitted "
                   f"file{'s' if unc != 1 else ''} in the repo.")

    doc = data.get("doctrine")
    if doc and doc.get("target"):
        out.append(f"Your north star: {doc['target']}.")

    h, c = data.get("health"), data.get("cost")
    if h or c:
        bits = []
        if h:
            bits.append(f"CPU {h['cpu']:.0f} percent, RAM {h['ram']:.0f} percent, "
                        f"disk {h['disk']:.0f} percent")
        if c:
            bits.append(f"${c.get('cost_usd', 0):.2f} of API spend today across "
                        f"{c.get('call_count', 0)} call{'s' if c.get('call_count', 0) != 1 else ''}")
        out.append("System check: " + "; ".join(bits) + ".")

    return " ".join(out)


async def compose_briefing(orchestrator=None, ctx: dict | None = None, mode: str = "full") -> str:
    data = await gather_briefing(orchestrator, ctx)
    return render_concise(data) if mode == "concise" else render_full(data)
