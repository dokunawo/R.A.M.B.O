"""Tests for the system briefing (boot card + on-demand 'catch me up')."""
import asyncio
import pytest

import system_briefing as sb


# ── boot-state round-trip ────────────────────────────────────────────────────
def test_boot_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_DATA_DIR", str(tmp_path))
    assert sb._read_last_boot() is None          # missing file → None
    sb._write_last_boot("2026-06-27T12:00:00Z")
    assert sb._read_last_boot() == "2026-06-27T12:00:00Z"


# ── _changes_since fallback chain ────────────────────────────────────────────
def _fake_git(mapping):
    """mapping: predicate(args)->(rc, out); first match wins."""
    async def _git(*args):
        for pred, result in mapping:
            if pred(args):
                return result
        return (1, "")
    return _git


def test_changes_since_uses_since_when_present(monkeypatch):
    monkeypatch.setattr("codebase_skill._git",
                        _fake_git([(lambda a: "--since=2026-06-26T00:00:00Z" in a, (0, "abc fix (1 hour ago)\n"))]))
    out = asyncio.run(sb._changes_since("2026-06-26T00:00:00Z"))
    assert out == ["abc fix (1 hour ago)"]


def test_changes_since_empty_since_does_not_fall_back(monkeypatch):
    # since_iso present but no commits → honest empty, NOT the 24h fallback
    monkeypatch.setattr("codebase_skill._git",
                        _fake_git([(lambda a: any(x.startswith("--since=2026") for x in a), (0, ""))]))
    out = asyncio.run(sb._changes_since("2026-06-27T18:00:00Z"))
    assert out == []


def test_changes_since_falls_back_to_lookback_then_count(monkeypatch):
    # no prior boot → 24h lookback empty → last-N returns commits
    def pred_lookback(a): return any(x == "--since=24 hours ago" for x in a)
    def pred_count(a): return "-n" in a
    monkeypatch.setattr("codebase_skill._git",
                        _fake_git([(pred_lookback, (0, "")), (pred_count, (0, "zzz feat (3 days ago)\n"))]))
    out = asyncio.run(sb._changes_since(None))
    assert out == ["zzz feat (3 days ago)"]


# ── suggested tasks parser ───────────────────────────────────────────────────
def test_suggested_tasks_parses_roadmap_and_handoff(tmp_path, monkeypatch):
    (tmp_path / "ROADMAP.md").write_text(
        "## Forward plan\n### Short term\n- Do thing A\n- Do thing B\n### Mid term\n- later\n",
        encoding="utf-8")
    (tmp_path / "HANDOFF.md").write_text(
        "## Stuff\n### Next action\nShip the betting boards.\n", encoding="utf-8")
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))
    tasks = sb._suggested_tasks(limit=4)
    assert tasks[0] == "(HANDOFF) Ship the betting boards."
    assert "Do thing A" in tasks and "Do thing B" in tasks
    assert "later" not in tasks            # Mid term excluded


def test_suggested_tasks_graceful_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("RAMBO_REPO_ROOT", str(tmp_path))   # empty dir
    assert sb._suggested_tasks() == []


# ── weather: default city vs ctx coords ──────────────────────────────────────
def test_weather_uses_ctx_coords_when_present(monkeypatch):
    seen = {}
    async def fake_weather(goal, ctx):
        seen["goal"], seen["ctx"] = goal, ctx
        return "Weather — here"
    monkeypatch.setattr("skills.weather_skill", fake_weather)
    asyncio.run(sb._weather({"lat": 42.3, "lon": -83.0}))
    assert seen["goal"] == "weather" and seen["ctx"]["lat"] == 42.3   # coords win


def test_weather_defaults_to_home_city(monkeypatch):
    seen = {}
    async def fake_weather(goal, ctx):
        seen["goal"] = goal
        return "Weather — Detroit"
    monkeypatch.setattr("skills.weather_skill", fake_weather)
    monkeypatch.setenv("RAMBO_HOME_CITY", "Detroit")
    asyncio.run(sb._weather(None))
    assert "Detroit" in seen["goal"]


# ── render ───────────────────────────────────────────────────────────────────
def _full_data():
    return {
        "date": "Saturday, June 27, 2026", "time": "12:00 PM", "greet": "Good afternoon",
        "name": "Daniel",
        "changes": ["abc feat: boards (1h)", "def fix: lock (2h)"],
        "uncommitted": 2,
        "tasks": ["Ship X", "Wire Y"],
        "weather": "Weather — Detroit\n  72°F",
        "pending": ["2 code reviews"],
        "calendar": [{"summary": "Shoot", "minutes_until": 90}],
        "doctrine": {"target": "$10K by Q4", "stale": None},
        "health": {"cpu": 12.0, "ram": 48.0, "disk": 60.0},
        "cost": {"cost_usd": 1.23, "call_count": 40},
    }


def test_render_full_includes_sections():
    out = sb.render_full(_full_data())
    for s in ("System Briefing", "Recent changes", "abc feat", "Suggested next targets",
              "Weather", "Waiting on you", "uncommitted", "North star", "System:"):
        assert s in out
    assert "None" not in out


def test_render_sparse_omits_empty_and_says_nothing_new():
    data = {"date": "D", "time": "T", "changes": [], "tasks": [], "pending": [],
            "calendar": [], "uncommitted": 0, "weather": None, "doctrine": None,
            "health": None, "cost": None}
    full = sb.render_full(data)
    assert "Nothing new since your last session." in full
    assert "Weather" not in full and "Waiting on you" not in full
    assert "None" not in full
    concise = sb.render_concise(data)
    assert "Nothing new since you were last here." in concise
    assert "\n" not in concise and "None" not in concise


def test_render_concise_flows_naturally():
    concise = sb.render_concise(_full_data())
    # greeting + natural "Today is" date (no year, ordinal day), no robotic header
    assert "Good afternoon, Daniel." in concise
    assert "Today is Saturday, June 27th." in concise
    assert "2026" not in concise and "System Briefing" not in concise
    # changes + weather + the SINGLE top focus (not the whole list)
    assert "2 changes landed" in concise and "abc feat: boards (1h)" in concise
    assert "Weather in Detroit" in concise
    assert "Your main focus: Ship X." in concise and "Wire Y" not in concise
    # calendar + pending + uncommitted
    assert "Shoot" in concise and "2 code reviews" in concise
    assert "uncommitted file" in concise
    # north star + a system line ARE spoken now (operator wants them read aloud)
    assert "north star" in concise.lower() and "$10K by Q4" in concise
    assert "System check" in concise and "CPU 12 percent" in concise
    # plain text, single line
    assert "**" not in concise and "#" not in concise and "\n" not in concise


def test_render_concise_boot_omits_duplicate_greeting():
    # boot path: /greeting already greets, so include_greeting=False must NOT re-greet
    concise = sb.render_concise(_full_data(), include_greeting=False)
    assert not concise.startswith("Good ")          # no second "Good afternoon, Daniel."
    assert "Good afternoon" not in concise
    assert concise.startswith("Today is Saturday, June 27th.")
    # still speaks the north star + system in the boot briefing
    assert "north star" in concise.lower() and "System check" in concise


def test_render_concise_cleans_roadmap_cruft_and_skips_weather_errors():
    data = {"greet": "Good morning", "name": "Daniel", "date": "Sunday, June 28, 2026",
            "changes": [], "calendar": [], "pending": [], "uncommitted": 1,
            "weather": "I couldn't resolve a location. Try \"weather in <city>\".",
            "tasks": ["(HANDOFF) Active thread: MLB betting edge engine (CMC) — "
                      "see §2a and ROADMAP.md. Next betting steps: prop link"]}
    concise = sb.render_concise(data)
    # roadmap tag / section / doc refs stripped, first clause only
    assert "Your main focus: MLB betting edge engine" in concise
    assert "(HANDOFF)" not in concise and "§2a" not in concise
    assert "ROADMAP" not in concise and "see " not in concise
    # the weather error is omitted entirely
    assert "couldn't" not in concise.lower()
    assert "1 uncommitted file" in concise


# ── gather best-effort + orchestrator degradation ───────────────────────────
def _stub_sections(monkeypatch, **over):
    """Patch all heavy section helpers to safe defaults; override per test."""
    async def aret(v):
        return v
    monkeypatch.setattr(sb, "_changes_since", lambda since: aret(over.get("changes", ["c (1h)"])))
    monkeypatch.setattr(sb, "_uncommitted_count", lambda: aret(over.get("unc", 0)))
    monkeypatch.setattr(sb, "_weather", lambda ctx: aret(over.get("weather", "W")))
    monkeypatch.setattr(sb, "_pending", lambda orch: aret(over.get("pending", [])))
    monkeypatch.setattr(sb, "_calendar_today", lambda: aret(over.get("cal", [])))
    monkeypatch.setattr(sb, "_cost_today", lambda: aret(over.get("cost", None)))
    monkeypatch.setattr(sb, "_suggested_tasks", lambda *a, **k: over.get("tasks", ["T"]))
    monkeypatch.setattr(sb, "_doctrine", lambda: over.get("doctrine", None))
    monkeypatch.setattr(sb, "_health", lambda: over.get("health", None))
    monkeypatch.setattr(sb, "_read_last_boot", lambda: None)


def test_gather_best_effort_survives_a_failing_section(monkeypatch):
    _stub_sections(monkeypatch)
    async def boom(since):
        raise RuntimeError("git exploded")
    monkeypatch.setattr(sb, "_changes_since", boom)
    data = asyncio.run(sb.gather_briefing(None))
    assert data["changes"] == []          # failed section omitted, not raised
    assert data["weather"] == "W"         # other sections still present


def test_gather_without_orchestrator_still_composes(monkeypatch):
    _stub_sections(monkeypatch, pending=[])
    data = asyncio.run(sb.gather_briefing(None))
    assert data["weather"] == "W" and data["tasks"] == ["T"]
    assert data["pending"] == []          # orchestrator-only section degraded


# ── routing / matcher ────────────────────────────────────────────────────────
def test_matcher_routes_status_vs_codebase_vs_calendar():
    from skills import match_skill
    assert match_skill("catch me up")["name"] == "system_update"
    assert match_skill("system status")["name"] == "system_update"
    assert match_skill("give me an update")["name"] == "system_update"
    assert match_skill("what changed in orchestrator.py")["name"] == "codebase"
    m = match_skill("update my calendar")
    assert m is None or m["name"] != "system_update"   # must not steal calendar
