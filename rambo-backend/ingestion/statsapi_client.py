"""
R.A.M.B.O. MLB Betting Agent — MLB Stats API client (Step 2)
ingestion/statsapi_client.py

The FREE half of ingestion. Direct httpx calls to statsapi.mlb.com for roster,
schedule, and player stats — the data the reference plan paid Apify for. Returns
the same `RunResult` shape as the Apify wrapper so `raw_store.land_raw` lands both
paths identically. No spend guard, no token: these calls cost nothing.

Each call gets a fresh synthetic run_id (timestamped) so re-pulls land as new raw
rows and the normalizer always upserts the latest state.

VERIFY: schedule/probablePitcher/lineups shapes were checked live. The
/people/{id}/stats split shape must still be eyeballed before the EV brain trusts it.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Optional

import httpx

from config import statsapi as cfg
from ingestion.apify_client_wrapper import RunResult

logger = logging.getLogger("rambo.ingestion.statsapi")

DEFAULT_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "RAMBO-ingest/1.0 (+statsapi)"}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _client(client: Optional[httpx.Client]) -> httpx.Client:
    return client or httpx.Client(timeout=DEFAULT_TIMEOUT, headers=_HEADERS)


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    resp = client.get(cfg.BASE + path, params=params)
    resp.raise_for_status()
    return resp.json()


def _run_result(source_id: str, kind: str, items: list[dict]) -> RunResult:
    run_id = f"statsapi:{kind}:{_now_iso()}"
    return RunResult(
        actor_id=source_id, run_id=run_id, dataset_id=run_id,
        items=items, item_count=len(items), estimated_cost_usd=0.0,
    )


def fetch_schedule(date_iso: str, *, client: Optional[httpx.Client] = None) -> RunResult:
    """Schedule for one date → one item per game (probablePitcher + lineups + team
    hydrated). Lands under SOURCE_SCHEDULE; normalized by the scoreboard mapper."""
    own = client is None
    client = _client(client)
    try:
        params = {**cfg.DEFAULT_PARAMS["schedule"], "date": date_iso}
        data = _get(client, cfg.ENDPOINTS["schedule"], params)
        games: list[dict[str, Any]] = []
        for d in data.get("dates", []):
            games.extend(d.get("games", []))
        logger.info("statsapi schedule %s: %d games", date_iso, len(games))
        return _run_result(cfg.SOURCE_SCHEDULE, "schedule", games)
    finally:
        if own:
            client.close()


def fetch_active_players(season: int, *, client: Optional[httpx.Client] = None) -> RunResult:
    """All active MLB players for a season → one item per player (full bio: id,
    name, bats/throws, position, currentTeam). The roster seed normalizes these."""
    own = client is None
    client = _client(client)
    try:
        path = cfg.ENDPOINTS["sport_players"].format(sport_id=cfg.SPORT_ID)
        params = {**cfg.DEFAULT_PARAMS["sport_players"], "season": season}
        data = _get(client, path, params)
        people = data.get("people", [])
        logger.info("statsapi active players %s: %d", season, len(people))
        return _run_result(cfg.SOURCE_ROSTER, "roster", people)
    finally:
        if own:
            client.close()


def fetch_team_stats(season: int, *, client: Optional[httpx.Client] = None) -> RunResult:
    """All teams' season runs scored (hitting) + runs allowed (pitching), merged
    into one item per team: {team_id, name, runs_scored, runs_allowed, games_played}.
    Feeds the moneyline Pythagorean model. Lands under SOURCE_TEAMS."""
    own = client is None
    client = _client(client)
    try:
        def _splits(group: str) -> list[dict]:
            params = {**cfg.DEFAULT_PARAMS["teams_stats"], "season": season, "group": group}
            data = _get(client, cfg.ENDPOINTS["teams_stats"], params)
            blocks = data.get("stats") or []
            return blocks[0].get("splits", []) if blocks else []

        teams: dict[int, dict[str, Any]] = {}
        for sp in _splits("hitting"):
            t = sp.get("team") or {}
            tid = t.get("id")
            if tid is None:
                continue
            teams[tid] = {"team_id": tid, "name": t.get("name"),
                          "runs_scored": (sp.get("stat") or {}).get("runs"),
                          "runs_allowed": None, "games_played": None}
        for sp in _splits("pitching"):
            t = sp.get("team") or {}
            tid = t.get("id")
            if tid is None:
                continue
            row = teams.setdefault(tid, {"team_id": tid, "name": t.get("name"),
                                         "runs_scored": None})
            stat = sp.get("stat") or {}
            row["runs_allowed"] = stat.get("runs")
            row["games_played"] = stat.get("gamesPlayed")
        items = [{**v, "season": season} for v in teams.values()]
        logger.info("statsapi team stats %s: %d teams", season, len(items))
        return _run_result(cfg.SOURCE_TEAMS, "teams", items)
    finally:
        if own:
            client.close()


def fetch_player_stats(mlb_id: int, season: int, *,
                       group: str = "hitting",
                       client: Optional[httpx.Client] = None) -> RunResult:
    """Season totals + vs-RHP/LHP splits + game log for one player, in one call.
    Returns a single-item RunResult carrying mlb_id alongside the raw stats bundle
    so the stats mapper keys on the canonical id without another lookup."""
    own = client is None
    client = _client(client)
    try:
        path = cfg.ENDPOINTS["people_stats"].format(person_id=mlb_id)
        params = {**cfg.DEFAULT_PARAMS["people_stats"], "season": season, "group": group}
        data = _get(client, path, params)
        item = {"mlb_id": mlb_id, "season": season, "group": group, "stats_raw": data}
        return _run_result(cfg.SOURCE_STATS, "stats", [item])
    finally:
        if own:
            client.close()
