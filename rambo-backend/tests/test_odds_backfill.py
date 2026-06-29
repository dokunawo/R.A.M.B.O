from db.migrate import get_connection, apply_migrations
from ingestion import odds_backfill


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def test_snapshot_times_offsets():
    early, close = odds_backfill.snapshot_times("2026-05-01T23:05:00+00:00")
    assert early == "2026-05-01T19:05:00+00:00"   # -4h
    assert close == "2026-05-01T23:00:00+00:00"   # -5min


def _final_dt(conn, pk, date, dt):
    conn.execute(
        "INSERT INTO games (game_pk, official_date, game_datetime, home_team_id, "
        "away_team_id, home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pk, date, dt, 1, 2, "AAA", "BBB", 4, 3, "2026-06-28T00:00:00Z"))


def test_backfill_dedups_snapshots_and_counts(tmp_path):
    conn = _conn(tmp_path)
    # two games at the SAME first pitch -> early/close instants shared -> 2 calls total
    _final_dt(conn, 10, "2026-05-01", "2026-05-01T23:05:00+00:00")
    _final_dt(conn, 11, "2026-05-01", "2026-05-01T23:05:00+00:00")
    calls = []

    def fake_pull(c, source, params):
        calls.append(params["snapshot"])
        return {"items": 2}

    out = odds_backfill.backfill_odds(conn, "2026-05-01", "2026-05-01", pull=fake_pull)
    assert sorted(set(calls)) == ["2026-05-01T19:05:00+00:00", "2026-05-01T23:00:00+00:00"]
    assert len(calls) == 2                      # deduped, not 4
    assert out["snapshots"] == 2


def test_backfill_skips_games_without_datetime(tmp_path):
    conn = _conn(tmp_path)
    conn.execute(
        "INSERT INTO games (game_pk, official_date, home_team_id, away_team_id, "
        "home_team_abbr, away_team_abbr, home_score, away_score, scraped_at) "
        "VALUES (99,'2026-05-01',1,2,'AAA','BBB',4,3,'2026-06-28T00:00:00Z')")
    out = odds_backfill.backfill_odds(conn, "2026-05-01", "2026-05-01",
                                      pull=lambda *a, **k: {"items": 0})
    assert out["skipped_no_datetime"] == 1
    assert out["snapshots"] == 0
