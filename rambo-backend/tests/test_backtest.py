"""Tests for the backtest harness, final-games read, and results backfill."""
import math

from db.migrate import get_connection, apply_migrations
from repositories.mlb_repo import MlbRepo
from brains.ev import backtest as bt
from ingestion import backfill


# ── harness math ──────────────────────────────────────────────────────────────
def test_american_to_decimal():
    assert math.isclose(bt.american_to_decimal(100), 2.0)
    assert math.isclose(bt.american_to_decimal(-200), 1.5)


def test_flat_roi_break_even_pickem():
    # one +100 win (+1), one +100 loss (-1) → ROI 0
    recs = [{"p": 0.5, "win": True, "odds": 100}, {"p": 0.5, "win": False, "odds": 100}]
    assert math.isclose(bt.flat_roi(recs), 0.0)


def test_flat_roi_positive_when_dogs_hit():
    recs = [{"p": 0.4, "win": True, "odds": 200}, {"p": 0.4, "win": False, "odds": 200}]
    assert math.isclose(bt.flat_roi(recs), 0.5)   # (+2 −1)/2


def test_brier_and_log_loss_at_half():
    recs = [{"p": 0.5, "win": True, "odds": 100}, {"p": 0.5, "win": False, "odds": 100}]
    assert math.isclose(bt.brier(recs), 0.25)
    assert math.isclose(bt.log_loss(recs), math.log(2), rel_tol=1e-9)


def test_calibration_buckets_pred_vs_actual():
    recs = [{"p": 0.9, "win": True, "odds": -300}, {"p": 0.9, "win": True, "odds": -300},
            {"p": 0.1, "win": False, "odds": 250}, {"p": 0.1, "win": True, "odds": 250}]
    cal = bt.calibration(recs, bins=10)
    hi = next(b for b in cal if b["bin"][0] == 0.9)
    lo = next(b for b in cal if b["bin"][0] == 0.1)
    assert hi["n"] == 2 and hi["pred"] == 0.9 and hi["actual"] == 1.0
    assert lo["n"] == 2 and lo["actual"] == 0.5


def test_avg_clv_uses_close_when_present():
    recs = [{"p": 0.5, "win": True, "odds": 120, "close": 100},   # beat the close
            {"p": 0.5, "win": False, "odds": 100}]                # no close → ignored
    assert bt.avg_clv(recs) > 0
    assert bt.avg_clv([{"p": 0.5, "win": True, "odds": 100}]) is None


def test_evaluate_shape():
    recs = [{"p": 0.6, "win": True, "odds": -120, "close": -110}]
    out = bt.evaluate(recs)
    assert out["n"] == 1 and out["win_rate"] == 1.0
    assert "roi" in out and "brier" in out and "log_loss" in out
    assert out["avg_clv"] is not None and isinstance(out["calibration"], list)


def test_evaluate_empty():
    out = bt.evaluate([])
    assert out["n"] == 0 and out["win_rate"] is None and out["avg_clv"] is None


# ── final_games read ──────────────────────────────────────────────────────────
def test_final_games_only_completed_in_range(tmp_path):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_abbr, away_team_abbr, "
                 "home_score, away_score, scraped_at) VALUES (1,'2026-06-20','NYY','BOS',5,3,'x')")
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_abbr, away_team_abbr, "
                 "scraped_at) VALUES (2,'2026-06-21','LAD','SF','x')")   # no score yet
    conn.execute("INSERT INTO games (game_pk, official_date, home_team_abbr, away_team_abbr, "
                 "home_score, away_score, scraped_at) VALUES (3,'2026-07-01','CHC','STL',2,4,'x')")
    conn.commit()
    games = MlbRepo(conn).final_games("2026-06-01", "2026-06-30")
    assert [g["game_pk"] for g in games] == [1]      # 2 unfinished, 3 out of range


# ── backfill glue ─────────────────────────────────────────────────────────────
def test_backfill_loops_dates_and_counts_finals(tmp_path, monkeypatch):
    conn = get_connection(str(tmp_path / "t.db")); apply_migrations(conn, "db/migrations")
    seen = []

    def fake_pull(_conn, source, params):
        seen.append(params["date"])
        # land a finished game on the first date
        if params["date"] == "2026-06-01":
            _conn.execute("INSERT INTO games (game_pk, official_date, home_team_abbr, "
                          "away_team_abbr, home_score, away_score, scraped_at) "
                          "VALUES (10,'2026-06-01','NYY','BOS',4,2,'x')")
        return {"items": 1}

    monkeypatch.setattr(backfill, "pull_source", fake_pull)
    monkeypatch.setattr(backfill, "normalize_pending", lambda _c: None)
    out = backfill.backfill_results(conn, "2026-06-01", "2026-06-03")
    assert seen == ["2026-06-01", "2026-06-02", "2026-06-03"]
    assert out["days"] == 3 and out["games_pulled"] == 3 and out["finals"] == 1
