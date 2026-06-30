# rambo-backend/brains/ev/prizepicks_tiers.py
"""PrizePicks tier board (goblin/standard/demon). Per player, the line ladder
across tiers with our model P(over) at each line. No payout/EV — PrizePicks
doesn't expose tier multipliers. Reuses prizepicks_board._p_over."""
from __future__ import annotations

import os

from brains.ev.prizepicks_board import _p_over

BOARD_SIZE = 11
_TIER_ORDER = ("goblin", "standard", "demon")


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db"))
    return MlbRepo(conn), conn


def prizepicks_tiers(date: str, market: str, repo=None, *, count: int = BOARD_SIZE) -> dict:
    repo, conn = _open(repo)
    try:
        by_player: dict = {}
        for prop in repo.latest_props(market=market, official_date=date, odds_type=None):
            if prop.get("book") != "prizepicks" or prop.get("mlb_id") is None:
                continue
            tier = prop.get("odds_type") or "standard"
            if tier not in _TIER_ORDER:
                continue
            ctx = repo.player_game_context(prop["mlb_id"], date)
            if ctx is None:
                continue
            got = _p_over(repo, date, market, prop)
            if got is None:
                continue
            p_over, _support = got
            entry = by_player.setdefault(prop["mlb_id"], {
                "name": (prop.get("player_name_raw") or "").upper(),
                "team": ctx.get("team_abbr", ""), "opponent": ctx.get("opponent_abbr", ""),
                "market": market, "tiers": {}})
            entry["tiers"][tier] = {"line": prop["line"], "model_pct": round(p_over * 100)}

        def _rank_key(e: dict) -> float:
            t = e["tiers"]
            if "standard" in t:
                return t["standard"]["model_pct"]
            return max(v["model_pct"] for v in t.values())

        rows = sorted((e for e in by_player.values() if e["tiers"]),
                      key=_rank_key, reverse=True)[:count]
        return {"title": f"PRIZEPICKS TIERS — {market}", "product": "PrizePicks",
                "market": market, "count": len(rows), "rows": rows,
                "prompt": _prompt(rows, market)}
    finally:
        if conn is not None:
            conn.close()


def _prompt(rows: list[dict], market: str) -> str:
    head = (f'Create a premium "Chances Make Champions" PrizePicks {market} TIERS '
            "board. For each player show the goblin / standard / demon line and our "
            "model % to go over it.\n\n"
            "KEY: goblin = safer, lower line; demon = swing, higher line. These are "
            "model probabilities, NOT guarantees. PrizePicks does not publish tier "
            "payouts, so no EV is shown.\n\nPLAYERS:\n")
    lines = []
    for i, r in enumerate(rows, 1):
        segs = [f"{t} {r['tiers'][t]['line']} ({r['tiers'][t]['model_pct']}%)"
                for t in _TIER_ORDER if t in r["tiers"]]
        lines.append(f"{i}. {r['name']} ({r['team']} vs {r['opponent']}) — "
                     + " · ".join(segs))
    return head + ("\n".join(lines) or "(no PrizePicks tier props available)")
