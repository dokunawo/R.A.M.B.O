"""Tests for the proactive calendar watch — dynamic nudge text + once-per-event."""

import pytest

import calendar_watch


def test_compose_nudge_is_dynamic():
    """The nudge reflects the real event, not a hardcoded string."""
    m = calendar_watch.compose_nudge(
        {"summary": "Dentist", "minutes_until": 15, "location": "5th & Main"}
    )
    assert "Dentist" in m
    assert "15 minutes" in m
    assert "5th & Main" in m
    # Not the placeholder example phrasing.
    assert "leave now" not in m.lower()


def test_compose_nudge_singular_and_now():
    assert "1 minute" in calendar_watch.compose_nudge({"summary": "Standup", "minutes_until": 1})
    assert "starting now" in calendar_watch.compose_nudge({"summary": "Call", "minutes_until": 0})


def test_compose_nudge_no_location():
    m = calendar_watch.compose_nudge({"summary": "Focus block", "minutes_until": 10})
    assert "Focus block" in m and "10 minutes" in m
    assert "It's at" not in m


@pytest.mark.asyncio
async def test_check_once_fires_within_lead_and_dedupes(monkeypatch):
    monkeypatch.setenv("CALENDAR_LEAD_MINUTES", "20")
    # Two events: one inside the lead window, one outside.
    events = [
        {"id": "a", "summary": "Soon", "minutes_until": 10, "location": "", "start": "x"},
        {"id": "b", "summary": "Later", "minutes_until": 40, "location": "", "start": "y"},
    ]

    async def _fake_upcoming(window_minutes=60):
        return events

    monkeypatch.setattr("google_calendar.upcoming_events", _fake_upcoming)

    delivered = []

    class _StubOrch:
        async def _response(self, agent, msg): delivered.append(msg)
        async def broadcast(self, msg): pass
        async def _voice_text(self, msg): pass

    monkeypatch.setenv("CALENDAR_SPEAK", "off")
    orch = _StubOrch()
    notified = set()

    fired1 = await calendar_watch.check_once(orch, notified)
    assert [e["id"] for e in fired1] == ["a"]          # only the in-window event
    assert any("Soon" in d for d in delivered)

    # Second pass: same events → no re-fire (deduped).
    fired2 = await calendar_watch.check_once(orch, notified)
    assert fired2 == []
