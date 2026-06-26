"""
R.A.M.B.O. MLB Betting Agent — Normalization pass (Step 3.5)
ingestion/normalize.py

Reads raw_ingest and writes the typed tables (games, players, player_*, *_lines).
This is the LAST place raw JSON is touched — every Brain downstream reads the typed
tables only.

Design:
  * Dispatch by source id (statsapi synthetic ids + paid Apify actor ids) -> a mapper.
  * Each mapper returns True (row handled, watermark set) or False (defer, retry next
    pass) — e.g. odds whose game isn't loaded yet defer until the schedule lands.
  * Watermark = raw_ingest.normalized_at. NULL means "not done yet".
  * Current-state tables (games, players) UPSERT. Line tables conflict on the STORED
    snapshot_key -> DO NOTHING (append-only, deduped to the minute).
  * Player linkage for props is DEFERRED to the ID resolver (Step 4): map_props writes
    mlb_id=NULL and keeps player_name_raw. Stats from statsapi already carry the
    canonical mlb_id, so they need no resolution.

FIELD PATHS: the statsapi roster/schedule/stats paths were verified live; the odds +
DK Pick6 paths were verified from real dataset items (maxItems=1). Re-verify if an
actor changes its output.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config.statsapi import SOURCE_ROSTER, SOURCE_SCHEDULE, SOURCE_STATS

logger = logging.getLogger("rambo.ingestion.normalize")


# --- tolerant extraction helpers -------------------------------------------

def _dig(d: Any, *path: str | int, default: Any = None) -> Any:
    cur = d
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and -len(cur) <= key < len(cur):
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- upsert / insert helpers -----------------------------------------------

def _upsert_player(conn: sqlite3.Connection, p: dict, scraped_at: str) -> None:
    conn.execute(
        """INSERT INTO players
             (mlb_id, full_name, position, bats, throws, birth_date, country,
              current_team_id, updated_at)
           VALUES (:mlb_id,:full_name,:position,:bats,:throws,:birth_date,:country,
              :current_team_id,:updated_at)
           ON CONFLICT(mlb_id) DO UPDATE SET
             full_name=excluded.full_name, position=excluded.position,
             bats=excluded.bats, throws=excluded.throws,
             current_team_id=excluded.current_team_id, updated_at=excluded.updated_at;""",
        {**p, "updated_at": scraped_at},
    )


def _self_alias(conn: sqlite3.Connection, mlb_id: int, name: str, scraped_at: str) -> None:
    conn.execute(
        """INSERT INTO player_aliases
             (mlb_id, source, source_player_id, source_name, confidence, created_at)
           VALUES (?, 'mlb', ?, ?, 1.0, ?)
           ON CONFLICT(source, source_player_id) DO NOTHING;""",
        (mlb_id, str(mlb_id), name, scraped_at),
    )


def _upsert_game(conn: sqlite3.Connection, g: dict, scraped_at: str) -> None:
    conn.execute(
        """INSERT INTO games
             (game_pk, official_date, season, game_type, status_detail,
              home_team_id, home_team_name, away_team_id, away_team_name,
              home_score, away_score, venue_id, venue_name, day_night,
              double_header, scheduled_innings, url, scraped_at)
           VALUES (:game_pk,:official_date,:season,:game_type,:status_detail,
              :home_team_id,:home_team_name,:away_team_id,:away_team_name,
              :home_score,:away_score,:venue_id,:venue_name,:day_night,
              :double_header,:scheduled_innings,:url,:scraped_at)
           ON CONFLICT(game_pk) DO UPDATE SET
              status_detail=excluded.status_detail,
              home_score=excluded.home_score, away_score=excluded.away_score,
              scraped_at=excluded.scraped_at;""",
        {**g, "scraped_at": scraped_at},
    )


def _insert_odds(conn: sqlite3.Connection, o: dict) -> None:
    conn.execute(
        """INSERT INTO odds_lines
             (game_pk, book, market, side, line, price, captured_at)
           VALUES (:game_pk,:book,:market,:side,:line,:price,:captured_at)
           ON CONFLICT(snapshot_key) DO NOTHING;""",
        o,
    )


def _insert_prop(conn: sqlite3.Connection, p: dict) -> None:
    conn.execute(
        """INSERT INTO prop_lines
             (game_pk, mlb_id, book, market, line, over_price, under_price,
              multiplier, player_name_raw, captured_at)
           VALUES (:game_pk,:mlb_id,:book,:market,:line,:over_price,:under_price,
              :multiplier,:player_name_raw,:captured_at)
           ON CONFLICT(snapshot_key) DO NOTHING;""",
        p,
    )


def _upsert_season_stats(conn: sqlite3.Connection, s: dict, scraped_at: str) -> None:
    conn.execute(
        """INSERT INTO player_season_stats
             (mlb_id, season, stat_group, stats, source, as_of_date, scraped_at)
           VALUES (:mlb_id,:season,:stat_group,:stats,:source,:as_of_date,:scraped_at)
           ON CONFLICT(mlb_id, season, stat_group, source, as_of_date) DO UPDATE SET
              stats=excluded.stats, scraped_at=excluded.scraped_at;""",
        {**s, "scraped_at": scraped_at},
    )


def _upsert_game_log(conn: sqlite3.Connection, gl: dict, scraped_at: str) -> None:
    conn.execute(
        """INSERT INTO player_game_logs
             (mlb_id, game_pk, game_date, stat_group, opponent_team_id, is_home,
              stats, source, scraped_at)
           VALUES (:mlb_id,:game_pk,:game_date,:stat_group,:opponent_team_id,:is_home,
              :stats,:source,:scraped_at)
           ON CONFLICT(mlb_id, game_date, stat_group, source) DO UPDATE SET
              stats=excluded.stats, scraped_at=excluded.scraped_at;""",
        {**gl, "scraped_at": scraped_at},
    )


def _match_game_pk(conn: sqlite3.Connection, official_date: Optional[str],
                   home_name: Optional[str], away_name: Optional[str]) -> Optional[int]:
    """Best-effort link of a paid feed's event to an MLB game by date + full team
    names (both statsapi and the odds actor use full names, e.g. 'Pittsburgh
    Pirates'). Returns None if no exact match (the row still lands, game_pk NULL)."""
    if not (official_date and home_name and away_name):
        return None
    row = conn.execute(
        "SELECT game_pk FROM games WHERE official_date=? AND home_team_name=? "
        "AND away_team_name=?",
        (official_date, home_name, away_name),
    ).fetchone()
    return row[0] if row else None


# --- per-source mappers -----------------------------------------------------
# Each returns True (handled, set watermark) or False (defer, retry next pass).

def map_roster(conn, item, scraped_at) -> bool:
    """statsapi /sports/{id}/players record -> upsert canonical players. Also
    self-aliases the MLBAM id under source 'mlb' for instant later linking."""
    mlb_id = _as_int(_first(item, "id", "playerId", "mlbId"))
    full_name = _first(item, "fullName", "name")
    if mlb_id is None or full_name is None:
        return False
    _upsert_player(conn, {
        "mlb_id": mlb_id,
        "full_name": full_name,
        "position": _dig(item, "primaryPosition", "abbreviation"),
        "bats": _dig(item, "batSide", "code"),
        "throws": _dig(item, "pitchHand", "code"),
        "birth_date": _first(item, "birthDate"),
        "country": _first(item, "birthCountry", "country"),
        "current_team_id": _as_int(_dig(item, "currentTeam", "id")),
    }, scraped_at)
    _self_alias(conn, mlb_id, full_name, scraped_at)
    return True


def map_scoreboard(conn, item, scraped_at) -> bool:
    """statsapi schedule game -> games (verified shape)."""
    game_pk = _as_int(_first(item, "gamePk", "gameId"))
    if game_pk is None:
        return False
    _upsert_game(conn, {
        "game_pk": game_pk,
        "official_date": _first(item, "officialDate", "gameDate"),
        "season": _as_int(_first(item, "season")),
        "game_type": _first(item, "gameType"),
        "status_detail": _dig(item, "status", "detailedState"),
        "home_team_id": _as_int(_dig(item, "teams", "home", "team", "id")),
        "home_team_name": _dig(item, "teams", "home", "team", "name"),
        "away_team_id": _as_int(_dig(item, "teams", "away", "team", "id")),
        "away_team_name": _dig(item, "teams", "away", "team", "name"),
        "home_score": _as_int(_dig(item, "teams", "home", "score")),
        "away_score": _as_int(_dig(item, "teams", "away", "score")),
        "venue_id": _as_int(_dig(item, "venue", "id")),
        "venue_name": _dig(item, "venue", "name"),
        "day_night": _first(item, "dayNight"),
        "double_header": _first(item, "doubleHeader"),
        "scheduled_innings": _as_int(_first(item, "scheduledInnings")),
        "url": _first(item, "link", "url"),
    }, scraped_at)
    return True


def map_stats(conn, item, scraped_at) -> bool:
    """statsapi player stats bundle {mlb_id, season, group, stats_raw} ->
    player_season_stats (season totals + L/R splits as JSON) + player_game_logs."""
    mlb_id = _as_int(item.get("mlb_id"))
    season = _as_int(item.get("season"))
    group = item.get("group") or "hitting"
    raw = item.get("stats_raw") or {}
    if mlb_id is None or season is None:
        return False

    season_stat: Any = None
    splits: dict[str, Any] = {}
    game_logs: list = []
    for blk in raw.get("stats", []):
        disp = _dig(blk, "type", "displayName")
        sp = blk.get("splits", []) or []
        if disp == "season" and sp:
            season_stat = sp[0].get("stat")
        elif disp == "statSplits":
            for s in sp:
                code = _dig(s, "split", "code") or _first(s, "sitCode")
                if code:
                    splits[code] = s.get("stat")
        elif disp == "gameLog":
            game_logs = sp

    if season_stat is not None or splits:
        _upsert_season_stats(conn, {
            "mlb_id": mlb_id, "season": season, "stat_group": group,
            "stats": json.dumps({"season": season_stat, "splits": splits},
                                separators=(",", ":")),
            "source": "mlb", "as_of_date": scraped_at[:10],
        }, scraped_at)

    for s in game_logs:
        gdate = _first(s, "date") or _dig(s, "split", "date")
        if gdate is None:
            continue
        _upsert_game_log(conn, {
            "mlb_id": mlb_id,
            # game_pk left NULL: game logs are historical games not in `games`
            # (which only holds the current slate); the FK would fail. The raw
            # gamePk is still preserved inside the stored stats JSON below.
            "game_pk": None,
            "game_date": gdate,
            "stat_group": group,
            "opponent_team_id": _as_int(_dig(s, "opponent", "id")),
            "is_home": 1 if _first(s, "isHome") else 0,
            "stats": json.dumps(s, separators=(",", ":")),
            "source": "mlb",
        }, scraped_at)
    return True


_ODDS_MARKET = {"h2h": "moneyline", "spreads": "spread", "totals": "total"}


def _odds_side(item: dict, home_name, away_name) -> Optional[str]:
    name = (_first(item, "outcomeName", "side", default="") or "").strip()
    if _first(item, "marketKey") == "totals":
        low = name.lower()
        if "over" in low:
            return "over"
        if "under" in low:
            return "under"
    if home_name and name == home_name:
        return "home"
    if away_name and name == away_name:
        return "away"
    return name.lower() or None


def map_odds(conn, item, scraped_at) -> bool:
    """seemuapps sports-odds row -> odds_lines (verified shape: bookmaker, marketKey,
    outcomeName, priceAmerican, point, eventId). Links to a game by date + team names."""
    book = _first(item, "bookmaker", "book")
    market_key = _first(item, "marketKey", "market")
    price = _as_int(_first(item, "priceAmerican", "price"))
    if book is None or market_key is None or price is None:
        return False
    home_name = _first(item, "homeTeam")
    away_name = _first(item, "awayTeam")
    commence = _first(item, "commenceTime")
    side = _odds_side(item, home_name, away_name)
    if side is None:
        return False
    _insert_odds(conn, {
        "game_pk": _match_game_pk(conn, commence[:10] if commence else None,
                                  home_name, away_name),
        "book": book,
        "market": _ODDS_MARKET.get(market_key, market_key),
        "side": side,
        "line": _as_float(_first(item, "point", "line")),
        "price": price,
        "captured_at": _first(item, "fetchedAt", "capturedAt", default=scraped_at),
    })
    return True


def map_props(conn, item, scraped_at) -> bool:
    """DK Pick6 prop -> prop_lines (verified shape: player_name, line, stat_abbr,
    over/under_multiplier). mlb_id stays NULL until the ID resolver links it (Step 4).
    Non-MLB rows are intentionally skipped (watermark set)."""
    if (_first(item, "league", default="") or "").upper() != "MLB":
        return True  # handled: not our sport, don't reprocess
    market = _first(item, "stat_abbr", "stat", "market")
    line = _as_float(_first(item, "line", "value"))
    player = _first(item, "player_name", "player", "playerName")
    if market is None or line is None or player is None:
        return False
    _insert_prop(conn, {
        "game_pk": None,      # linked later via player team + date
        "mlb_id": None,       # resolved downstream by IdResolver (Step 4)
        "book": _first(item, "platform", "book", default="dk_pick6"),
        "market": market,     # e.g. 'HR' — book->EV taxonomy mapping is a TODO
        "line": line,
        "over_price": _as_int(_first(item, "over_price", "overPrice")),
        "under_price": _as_int(_first(item, "under_price", "underPrice")),
        "multiplier": _as_float(_first(item, "over_multiplier", "multiplier")),
        "player_name_raw": player,
        "captured_at": _first(item, "updated_at", "captured_at", default=scraped_at),
    })
    return True


DISPATCH: dict[str, Callable] = {
    SOURCE_ROSTER: map_roster,
    SOURCE_SCHEDULE: map_scoreboard,
    SOURCE_STATS: map_stats,
    "seemuapps/sports-odds-scraper": map_odds,
    "zen-studio/draftkings-pick6-player-props": map_props,
}


# --- driver -----------------------------------------------------------------

def normalize_pending(conn: sqlite3.Connection, limit: Optional[int] = None) -> dict[str, int]:
    """Process raw_ingest rows with normalized_at IS NULL, dispatching by source id.
    Stats/roster key directly on mlb_id; props defer player-linking to the resolver."""
    q = ("SELECT id, actor_id, payload, scraped_at FROM raw_ingest "
         "WHERE normalized_at IS NULL ORDER BY id")
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()

    stats = {"processed": 0, "deferred": 0, "unknown_actor": 0}
    for row in rows:
        mapper = DISPATCH.get(row["actor_id"])
        if mapper is None:
            stats["unknown_actor"] += 1
            continue
        item = json.loads(row["payload"])
        conn.execute("BEGIN;")
        try:
            handled = mapper(conn, item, row["scraped_at"])
            if handled:
                conn.execute("UPDATE raw_ingest SET normalized_at=? WHERE id=?",
                             (_now(), row["id"]))
                stats["processed"] += 1
            else:
                stats["deferred"] += 1
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
    logger.info("normalize_pending: %s", stats)
    return stats


def renormalize_actor(conn: sqlite3.Connection, actor_id: str) -> int:
    """Clear the watermark for one source's raw rows so they reprocess on the next
    normalize_pending() — e.g. after resolving players in review. No re-pull."""
    cur = conn.execute(
        "UPDATE raw_ingest SET normalized_at=NULL WHERE actor_id=?", (actor_id,)
    )
    return cur.rowcount
