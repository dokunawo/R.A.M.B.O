"""Tests for temporal expression resolution."""

from datetime import datetime, timedelta

from temporal import resolve_temporal, format_temporal_context


# Fixed clock: Thursday, 2026-06-25, 14:30 local.
NOW = datetime(2026, 6, 25, 14, 30)


def _by_phrase(text):
    return {r.phrase: r for r in resolve_temporal(text, NOW)}


def test_today():
    r = _by_phrase("what's on my calendar today")["today"]
    assert r.start == datetime(2026, 6, 25)
    assert r.end == datetime(2026, 6, 26)


def test_yesterday():
    r = _by_phrase("what did we work on yesterday")["yesterday"]
    assert r.start == datetime(2026, 6, 24)
    assert r.end == datetime(2026, 6, 25)


def test_tomorrow():
    r = _by_phrase("anything tomorrow")["tomorrow"]
    assert r.start == datetime(2026, 6, 26)
    assert r.end == datetime(2026, 6, 27)


def test_this_week_monday_anchored():
    # 2026-06-25 is a Thursday; Monday of that week is 2026-06-22.
    r = _by_phrase("summarize this week")["this week"]
    assert r.start == datetime(2026, 6, 22)
    assert r.end == datetime(2026, 6, 29)


def test_last_week():
    r = _by_phrase("what happened last week")["last week"]
    assert r.start == datetime(2026, 6, 15)
    assert r.end == datetime(2026, 6, 22)


def test_next_week():
    r = _by_phrase("plan next week")["next week"]
    assert r.start == datetime(2026, 6, 29)
    assert r.end == datetime(2026, 7, 6)


def test_last_n_days():
    r = _by_phrase("show the last 3 days")["last 3 days"]
    # Inclusive of today: 23rd, 24th, 25th.
    assert r.start == datetime(2026, 6, 23)
    assert r.end == datetime(2026, 6, 26)


def test_this_morning():
    r = _by_phrase("what did I do this morning")["this morning"]
    assert r.start == datetime(2026, 6, 25, 0, 0)
    assert r.end == datetime(2026, 6, 25, 12, 0)


def test_last_week_not_matched_as_this_week():
    phrases = set(_by_phrase("last week"))
    assert "last week" in phrases
    assert "this week" not in phrases


def test_no_match_returns_empty():
    assert resolve_temporal("just a normal sentence", NOW) == []
    assert resolve_temporal("", NOW) == []


def test_label_single_and_span():
    r = resolve_temporal("yesterday", NOW)[0]
    assert r.label() == "yesterday: 2026-06-24"
    rng = resolve_temporal("this week", NOW)[0]
    assert rng.label() == "this week: 2026-06-22 to 2026-06-28"


def test_format_context_block():
    ranges = resolve_temporal("what did we do yesterday and last week", NOW)
    block = format_temporal_context(ranges)
    assert "RESOLVED DATES" in block
    assert "yesterday: 2026-06-24" in block
    assert "last week: 2026-06-15 to 2026-06-21" in block
    assert format_temporal_context([]) == ""


def test_tz_aware_now_preserved():
    from datetime import timezone
    aware = datetime(2026, 6, 25, 14, 30, tzinfo=timezone.utc)
    r = resolve_temporal("yesterday", aware)[0]
    assert r.start.tzinfo == timezone.utc
