"""
EV Brain read API (data-only). GET /betting/daily-edge + /betting/slip return the
ranked picks / slip; POST /betting/prep sources the full multi-feed board for a date.
Every read carries provenance (data-as-of + book + product label + stale guard) so
this engine never quietly serves stale lines and its product is never mistaken for a
cowork sportsbook-prop play. Imports no bet-placement capability (Sentinel boundary).
"""
from __future__ import annotations
import datetime
import os
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, HTTPException
from brains.ev.engine import daily_edge
from brains.ev.market import REGISTRY
from brains.ev.slip import build_slip, PRODUCT
from brains.ev.watch import player_watch, moneyline_board, strikeout_watch, hits_tb_watch

router = APIRouter(prefix="/betting", tags=["betting"])

_DB = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
_MAX_AGE_H = float(os.environ.get("RAMBO_ODDS_MAX_AGE_H", "6"))


def _data_as_of(market: str) -> Optional[str]:
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    try:
        conn = get_connection(_DB)
        try:
            return MlbRepo(conn).latest_capture("moneyline" if market == "ml" else "prop")
        finally:
            conn.close()
    except Exception:
        return None


def _provenance(market: str) -> dict:
    as_of = _data_as_of(market)
    book = "DraftKings" if market == "ml" else "DraftKings Pick6"
    now = datetime.datetime.now(datetime.timezone.utc)
    stale, age_h = False, None
    if as_of:
        try:
            t = datetime.datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            age_h = (now - t).total_seconds() / 3600
            stale = age_h > _MAX_AGE_H
        except ValueError:
            pass
    prov = {"generated_at": now.isoformat(), "data_as_of": as_of, "book": book,
            "product": PRODUCT.get(market, market.upper()), "stale": stale}
    if stale and age_h is not None:
        prov["warning"] = f"⚠ lines are {age_h:.0f}h old — re-pull before betting"
    return prov, as_of, book


@router.get("/daily-edge")
def get_daily_edge(market: str = "hr", date: Optional[str] = None,
                   threshold: float = 0.0) -> dict:
    """Ranked picks for one market (+ provenance). `threshold=-1.0` includes −EV."""
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        picks = daily_edge(d, market, threshold=threshold)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"daily_edge failed: {e}") from e
    prov, _, _ = _provenance(market)
    return {"market": market, "date": d, "count": len(picks),
            "picks": [asdict(p) for p in picks], "provenance": prov}


@router.get("/slip")
def get_slip(market: str = "hr", date: Optional[str] = None,
             count: Optional[int] = None) -> dict:
    """Fixed-size slip roster + a ready-to-paste ChatGPT prompt (+ provenance)."""
    if market not in REGISTRY:
        raise HTTPException(status_code=404,
                            detail=f"unknown market '{market}' (valid: {sorted(REGISTRY)})")
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, book = _provenance(market)
        picks = daily_edge(d, market, threshold=-1.0)
        slip = build_slip(picks, market, count=count, as_of=as_of, book=book)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"slip failed: {e}") from e
    return {"market": market, "date": d, **slip, "provenance": prov}


@router.get("/player-watch")
def get_player_watch(date: Optional[str] = None) -> dict:
    """Top-11 HR board + a ready-to-paste ChatGPT image prompt (+ provenance)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, _ = _provenance("hr")
        watch = player_watch(d, as_of=as_of, book="DraftKings Pick6")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"player_watch failed: {e}") from e
    return {"date": d, **watch, "provenance": prov}


@router.get("/moneyline-board")
def get_moneyline_board(date: Optional[str] = None) -> dict:
    """Every slate game (book odds + model %) + a ChatGPT image prompt (+ provenance)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, book = _provenance("ml")
        board = moneyline_board(d, as_of=as_of, book=book)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"moneyline_board failed: {e}") from e
    return {"date": d, **board, "provenance": prov}


@router.get("/strikeout-watch")
def get_strikeout_watch(date: Optional[str] = None) -> dict:
    """Top-11 probable starters by P(9+ K) for alt-strikeout parlays (+ prompt)."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, _ = _provenance("k")
        board = strikeout_watch(d, as_of=as_of, book=None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"strikeout_watch failed: {e}") from e
    return {"date": d, **board, "provenance": prov}


@router.get("/hits-tb-watch")
def get_hits_tb_watch(date: Optional[str] = None) -> dict:
    """Top-11 hitters by P(2+ total bases) (+ P(1+ hit)) for hits/TB parlays."""
    d = date or datetime.date.today().isoformat()
    try:
        prov, as_of, _ = _provenance("hrr")
        board = hits_tb_watch(d, as_of=as_of, book=None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"hits_tb_watch failed: {e}") from e
    return {"date": d, **board, "provenance": prov}


@router.get("/line-shop")
def get_line_shop(date: Optional[str] = None) -> dict:
    """Best moneyline price per side across ALL books + each book's no-vig
    consensus and the line-shopping value of the best number. Multi-book by
    construction (The Odds API REGIONS=us). Read-only, with provenance."""
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    from brains.ev.line_shop import line_shop_slate
    d = date or datetime.date.today().isoformat()
    try:
        prov, _, _ = _provenance("ml")
        conn = get_connection(_DB)
        try:
            games = line_shop_slate(MlbRepo(conn), d)
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"line_shop failed: {e}") from e
    return {"date": d, "games": games, "provenance": prov}


@router.get("/clv")
def get_clv(date: Optional[str] = None) -> dict:
    """Closing Line Value for RAMBO's moneyline leans: per game the opening vs
    closing reference-book line and whether the close moved toward the lean, plus
    a beat-the-close summary. Read-only, from the odds_lines history."""
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    from brains.ev.clv import clv_slate
    from brains.ev.moneyline_model import evaluate_game
    d = date or datetime.date.today().isoformat()
    season = int(d[:4])
    try:
        prov, _, _ = _provenance("ml")
        conn = get_connection(_DB)
        try:
            repo = MlbRepo(conn)
            leans = {}
            for g in repo.moneyline_slate(d):
                ev = evaluate_game(repo, season, g)
                if ev:
                    leans[g["game_pk"]] = "home" if ev["diff"] > 0 else "away"
            games = clv_slate(repo, d, leans)
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"clv failed: {e}") from e
    graded = [g for g in games if g.get("clv_pts") is not None]
    beat = sum(1 for g in graded if g["beat_close"])
    summary = {
        "graded": len(graded),
        "beat_close": beat,
        "beat_close_rate": round(beat / len(graded), 3) if graded else None,
        "avg_clv_pts": round(sum(g["clv_pts"] for g in graded) / len(graded), 4) if graded else None,
    }
    return {"date": d, "games": games, "summary": summary, "provenance": prov}


@router.post("/backfill-results")
def post_backfill_results(start: str, end: str) -> dict:
    """Backfill final scores for past games (free statsapi schedule) over a date
    range, so the backtest harness has outcomes to grade. Idempotent."""
    from db.migrate import get_connection
    from ingestion.backfill import backfill_results
    conn = get_connection(_DB)
    try:
        return backfill_results(conn, start, end)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"backfill failed: {e}") from e
    finally:
        conn.close()


@router.post("/pull-book-props")
def post_pull_book_props(date: Optional[str] = None,
                         max_events: Optional[int] = None) -> dict:
    """Pull sportsbook player props (The Odds API per-event) and normalize them
    into prop_lines, then resolve player ids. COSTS CREDITS: events × markets
    (us region). Pass max_events=1 for a ~len(markets)-credit smoke test."""
    from db.migrate import get_connection
    from ingestion.sources import pull_source
    from ingestion.normalize import normalize_pending
    conn = get_connection(_DB)
    try:
        landed = pull_source(conn, "odds_props",
                             {"date": date, "max_events": max_events})
        normalize_pending(conn)
        try:
            from brains.id_resolver import IdResolver
            resolved = IdResolver(conn).run_unresolved_props()
        except Exception:
            resolved = None
        return {"pulled": landed.get("items"), "resolved": resolved}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"pull-book-props failed: {e}") from e
    finally:
        conn.close()


@router.get("/prop-shop")
def get_prop_shop(date: Optional[str] = None, market: Optional[str] = None) -> dict:
    """Grade Pick6 legs against the sportsbook market: per leg, the Pick6 breakeven
    vs the de-vigged book consensus fair line, the best book/price, and whether the
    leg is +EV. Read-only; needs sportsbook props pulled first (pull-book-props)."""
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    from brains.ev.prop_shop import prop_shop_slate
    d = date or datetime.date.today().isoformat()
    try:
        prov, _, _ = _provenance("hr")
        conn = get_connection(_DB)
        try:
            rows = prop_shop_slate(MlbRepo(conn), d, market=market)
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"prop_shop failed: {e}") from e
    plus = sum(1 for r in rows if r["value"] > 0)
    return {"date": d, "legs": rows,
            "summary": {"compared": len(rows), "plus_ev": plus}, "provenance": prov}


@router.post("/prep")
def post_prep(date: Optional[str] = None, with_props: bool = True) -> dict:
    """Pull + normalize the full multi-source board for `date` (schedule, The Odds API,
    last-15 recency, lineups, team stats, Pick6 props) and top up player stats."""
    from db.migrate import get_connection
    from ingestion.prep import prep_slate
    d = date or datetime.date.today().isoformat()
    conn = get_connection(_DB)
    try:
        return prep_slate(conn, d, with_props=with_props)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"prep failed: {e}") from e
    finally:
        conn.close()


@router.get("/backtest")
def backtest_endpoint(start: str, end: str) -> dict:
    """Walk-forward moneyline backtest over [start,end]: calibration + ROI/CLV at the
    early and closing line. Data-only; grades historical picks, never places bets."""
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    from brains.ev.walkforward import run
    conn = get_connection(_DB)
    try:
        return run(MlbRepo(conn), start, end)
    finally:
        conn.close()
