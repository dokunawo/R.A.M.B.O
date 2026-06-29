import json
from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev import k_backtest


def _conn(tmp_path):
    conn = get_connection(str(tmp_path / "t.db"))
    apply_migrations(conn, "db/migrations")
    return conn


def _pit_log(conn, mlb_id, date, k, bf, opp_team):
    conn.execute("INSERT OR IGNORE INTO players (mlb_id, full_name, updated_at) "
                 "VALUES (?,?,?)", (mlb_id, f"P{mlb_id}", "2026-06-28T00:00:00Z"))
    conn.commit()
    stats = json.dumps({"stat": {"strikeOuts": k, "battersFaced": bf}})
    conn.execute(
        "INSERT INTO player_game_logs (mlb_id, game_pk, game_date, stat_group, "
        "opponent_team_id, stats, source, scraped_at) VALUES (?,?,?,?,?,?,?,?)",
        (mlb_id, None, date, "pitching", opp_team, stats, "mlb/statsapi:stats",
         "2026-06-28T00:00:00Z"))
    conn.commit()


def test_k_backtest_grades_thresholds_leakfree(tmp_path):
    conn = _conn(tmp_path)
    # history (so as-of projection is buildable) + graded starts in May
    for d in ("2026-04-02", "2026-04-09", "2026-04-16", "2026-04-23"):
        _pit_log(conn, 50, d, 8, 25, 200)
    _pit_log(conn, 50, "2026-05-05", 11, 26, 200)   # actual 11 K -> hits 6..10
    _pit_log(conn, 50, "2026-05-12", 3, 24, 200)    # actual 3 K -> misses 6..10
    repo = MlbRepo(conn)
    out = k_backtest.run(repo, "2026-05-01", "2026-05-31", thresholds=(6, 9))
    assert out["n_starts"] == 2
    assert set(out.keys()) >= {6, 9, "n_starts", "skipped"}
    # the 11-K start wins both thresholds; the 3-K start loses both
    assert out[6]["n"] == 2 and out[9]["n"] == 2
    assert 0.0 <= out[6]["win_rate"] <= 1.0


def test_k_backtest_skips_starts_without_history(tmp_path):
    conn = _conn(tmp_path)
    _pit_log(conn, 50, "2026-04-01", 7, 25, 200)    # first start: no prior -> projection None
    repo = MlbRepo(conn)
    out = k_backtest.run(repo, "2026-04-01", "2026-04-30", thresholds=(6,))
    assert out["n_starts"] == 0 and out["skipped"] == 1


def test_k_backtest_omits_meaningless_odds_metrics(tmp_path):
    """Verify that roi and avg_clv are removed from graded thresholds.
    These metrics are meaningless in pure calibration (sentinel odds=100)."""
    conn = _conn(tmp_path)
    # history + graded start
    for d in ("2026-04-02", "2026-04-09"):
        _pit_log(conn, 50, d, 8, 25, 200)
    _pit_log(conn, 50, "2026-05-05", 9, 26, 200)
    repo = MlbRepo(conn)
    out = k_backtest.run(repo, "2026-05-01", "2026-05-31", thresholds=(6, 9))
    # Check that roi and avg_clv are NOT in the metrics dict
    assert "roi" not in out[6], "roi should be omitted for pure calibration"
    assert "avg_clv" not in out[6], "avg_clv should be omitted for pure calibration"
    assert "roi" not in out[9], "roi should be omitted for pure calibration"
    assert "avg_clv" not in out[9], "avg_clv should be omitted for pure calibration"
    # Check that honest calibration metrics ARE present
    assert "brier" in out[6]
    assert "log_loss" in out[6]
    assert "calibration" in out[6]
    assert "n" in out[6]
    assert "win_rate" in out[6]
