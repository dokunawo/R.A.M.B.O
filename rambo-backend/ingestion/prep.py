"""Slate prep — one call that pulls every source for a date so slips are built on a
fully-sourced, fresh board (schedule + The Odds API + last-15 recency + lineups +
team stats + DK Pick6 props), resolves prop players, and tops up the per-player stats
the models need. Used by POST /betting/prep."""
from __future__ import annotations

import datetime as _dt
import logging
import sqlite3

from ingestion.sources import pull_source
from ingestion.normalize import normalize_pending

logger = logging.getLogger("rambo.ingestion.prep")

_BATTER_MARKETS = ("HR", "H+R+RBI", "SB", "H")


def _has_stats(conn, mlb_id, season, group) -> bool:
    return conn.execute(
        "SELECT 1 FROM player_season_stats WHERE mlb_id=? AND season=? AND stat_group=?",
        (mlb_id, season, group)).fetchone() is not None


def prep_slate(conn: sqlite3.Connection, date: str | None = None,
               with_props: bool = True) -> dict:
    """Pull + normalize the full multi-source board for `date`. Returns a summary."""
    from brains.id_resolver import IdResolver

    d = date or _dt.date.today().isoformat()
    season = int(d[:4])
    summary: dict = {"date": d}

    summary["schedule"] = pull_source(conn, "schedule", {"date": d})["items"]
    summary["odds"] = pull_source(conn, "odds_api", {"date": d})["items"]
    summary["team_stats"] = pull_source(conn, "team_stats", {"season": season})["items"]
    try:
        summary["statcast"] = pull_source(conn, "statcast", {"season": season})["items"]
    except Exception as exc:                            # Savant hiccup shouldn't abort prep
        logger.warning("statcast pull failed: %s", exc)
    summary["recent_hitting"] = pull_source(
        conn, "recent_stats", {"group": "hitting", "end_date": d})["items"]
    summary["recent_pitching"] = pull_source(
        conn, "recent_stats", {"group": "pitching", "end_date": d})["items"]
    if with_props:
        # DK Pick6 props come from a third-party Apify actor that can go down (it
        # may "succeed" yet return 0). Guard it so a dead source can't abort the
        # whole slate, and report the count so callers can warn when it's empty.
        try:
            summary["props"] = pull_source(conn, "props", {"overrides": {"maxItems": 100}})["items"]
        except Exception as exc:
            logger.warning("DK Pick6 props pull failed: %s", exc)
            summary["props"] = 0
        if not summary["props"]:
            logger.warning("DK Pick6 props returned 0 — source may be down; "
                           "Pick6 boards (HR/HRR/SB/K) will be stale or empty.")
    normalize_pending(conn)

    # confirmed lineups for each scheduled game
    games = [g[0] for g in conn.execute(
        "SELECT game_pk FROM games WHERE official_date=?", (d,))]
    lineups = 0
    for gp in games:
        try:
            lineups += pull_source(conn, "lineups", {"game_pk": gp})["items"]
        except Exception as exc:                       # one bad boxscore shouldn't abort prep
            logger.warning("lineup pull failed for %s: %s", gp, exc)
        try:
            pull_source(conn, "weather", {"game_pk": gp})
        except Exception as exc:
            logger.warning("weather pull failed for %s: %s", gp, exc)
    normalize_pending(conn)
    summary["lineups"] = lineups

    # resolve prop player names, then link each prop to its scheduled game (and
    # confirm the player's team is actually playing today), then top up the
    # per-player stats the models need
    summary["resolved"] = IdResolver(conn).run_unresolved_props()
    from ingestion.link import link_prop_games
    summary["linked"] = link_prop_games(conn, d)
    batters = [r[0] for r in conn.execute(
        f"SELECT DISTINCT mlb_id FROM prop_lines WHERE mlb_id IS NOT NULL "
        f"AND market IN ({','.join('?' * len(_BATTER_MARKETS))})", _BATTER_MARKETS)]
    # Player Watch ranks the WHOLE slate, so pull hitting stats for every hitter in a
    # confirmed lineup too (free statsapi), not just the propped ones. Dedupe, keep
    # the propped batters first.
    lineup_batters = [r[0] for r in conn.execute(
        "SELECT DISTINCT gl.mlb_id FROM game_lineups gl JOIN games g ON g.game_pk=gl.game_pk "
        "WHERE g.official_date=? AND gl.mlb_id IS NOT NULL", (d,))]
    batters = list(dict.fromkeys(batters + lineup_batters))
    pitchers = [r[0] for r in conn.execute(
        "SELECT DISTINCT mlb_id FROM prop_lines WHERE mlb_id IS NOT NULL AND market='SO'")]
    # moneyline needs each probable starter's ERA
    starters = [r[0] for r in conn.execute(
        "SELECT home_probable_pitcher_id FROM games WHERE official_date=? "
        "UNION SELECT away_probable_pitcher_id FROM games WHERE official_date=?", (d, d))
        if r[0] is not None]
    pulled = 0
    for mid in batters:
        if not _has_stats(conn, mid, season, "hitting"):
            try:
                pull_source(conn, "stats", {"season": season, "player_id": mid, "group": "hitting"})
                pulled += 1
            except Exception:
                pass
    for mid in set(pitchers) | set(starters):
        if not _has_stats(conn, mid, season, "pitching"):
            try:
                pull_source(conn, "stats", {"season": season, "player_id": mid, "group": "pitching"})
                pulled += 1
            except Exception:
                pass
    normalize_pending(conn)
    summary["stat_pulls"] = pulled
    return summary
