"""PrizePicks model-confidence boards. Per market, score each PrizePicks prop by
the model's probability of clearing the line (reusing RAMBO's existing prop
models), pick the favored side, and rank by confidence. No per-prop multiplier."""
from __future__ import annotations

import os

from brains.ev.features import build_hr_features_core, build_count_features_core
from brains.ev.hr_model import hr_probability
from brains.ev.count_model import poisson_prob_over
from brains.ev import k_model

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
BOARD_SIZE = 11

# market -> (stat label, count-model stat_keys / None for HR & SO which use their own model)
_COUNT_KEYS = {
    "TB": ["totalBases"], "H": ["hits"],
    "H+R+RBI": ["hits", "runs", "rbi"], "SB": ["stolenBases"],
}


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _p_over(repo, date, market, prop) -> tuple[float, str] | None:
    """model P(over the line) + a support string, or None if no usable sample."""
    mid, line = prop["mlb_id"], prop["line"]
    name = prop["player_name_raw"] or ""
    if market == "HR":
        feat = build_hr_features_core(repo, date, mid, name, line=line)
        if feat is None:
            return None
        return hr_probability(feat.hr_rate, feat.park_factor), feat.support
    if market == "SO":
        ctx = repo.player_game_context(mid, date) or {}
        proj = k_model.k_projection(repo, date, {
            "mlb_id": mid, "name": name, "team_abbr": ctx.get("team_abbr", ""),
            "opponent_abbr": ctx.get("opponent_abbr", ""),
            "opponent_team_id": None}, max_j=20)
        if proj is None:
            return None
        from math import ceil
        return (k_model.binom_prob_over(round(proj["batters_faced"]), proj["k_rate"],
                                        ceil(line + 1e-9)),
                f"{proj['k_mean']:.1f} proj K")
    keys = _COUNT_KEYS.get(market)
    if not keys:
        return None
    feat = build_count_features_core(repo, date, mid, name, stat_keys=keys,
                                     label=market, group="hitting")
    if feat is None:
        return None
    return poisson_prob_over(feat.per_game_mean, line), feat.support


def prizepicks_board(date: str, market: str, repo=None, *, count: int = BOARD_SIZE) -> dict:
    repo, conn = _open(repo)
    try:
        scored = []
        for prop in repo.latest_props(market=market, official_date=date):
            if prop["book"] != "prizepicks" or prop["mlb_id"] is None:
                continue
            ctx = repo.player_game_context(prop["mlb_id"], date)
            if ctx is None:
                continue                       # not on today's slate
            got = _p_over(repo, date, market, prop)
            if got is None:
                continue
            p_over, support = got
            side = "over" if p_over >= 0.5 else "under"
            p = p_over if side == "over" else 1.0 - p_over
            scored.append({
                "name": (prop["player_name_raw"] or "").upper(),
                "team": ctx.get("team_abbr", ""), "opponent": ctx.get("opponent_abbr", ""),
                "stat": market, "line": prop["line"], "side": side,
                "model_pct": round(p * 100), "support": support, "_p": p,
            })
        scored.sort(key=lambda r: r["_p"], reverse=True)
        rows = [{k: v for k, v in r.items() if k != "_p"} | {"rank": i + 1}
                for i, r in enumerate(scored[:count])]
        prompt = _prompt(rows, market)
        return {"title": f"PRIZEPICKS — {market}", "product": "PrizePicks",
                "market": market, "count": len(rows), "rows": rows, "prompt": prompt}
    finally:
        if conn is not None:
            conn.close()


def _prompt(rows: list[dict], market: str) -> str:
    head = (f'Create a premium "Chances Make Champions" PrizePicks {market} board. '
            "Numbered list; each row: player (team vs opp), the pick (over/under the "
            "line), and our model %.\n\nPICKS:\n")
    body = "\n".join(
        f"{r['rank']}. {r['name']} ({r['team']} vs {r['opponent']}) — "
        f"{r['side'].upper()} {r['line']} {market} — {r['model_pct']}%"
        for r in rows) or "(no PrizePicks props available)"
    return head + body
