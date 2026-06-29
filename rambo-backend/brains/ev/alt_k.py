"""Alt-strikeout board + parlay EV. Joins the k_model P(line+) ladder to real
book (FanDuel + best-of-book) pitcher_strikeouts_alternate odds. Pure-Python
math here; the board/repo glue is added in later tasks. Data-only."""
from __future__ import annotations

import math

import os

from brains.ev import k_model
from brains.ev.k_model import binom_prob_over
from brains.ev.line_shop import american_to_decimal

DB_PATH = os.environ.get("RAMBO_DB_PATH", "data/mlb_ingest.db")
ALT_K_BOARD_SIZE = 11


def leg_ev(model_p: float, american_price: int) -> float:
    """EV per 1u for a single over leg: model_p * decimal_payout - 1."""
    return round(model_p * american_to_decimal(american_price) - 1.0, 4)


def parlay_ev(legs: list[dict]) -> dict:
    """Independent-leg parlay. legs: [{"p": float, "price": int}, ...].
    combined_p = prod(p); payout = prod(decimal odds); ev = combined_p*payout - 1."""
    if not legs:
        return {"combined_p": 0.0, "payout": 0.0, "ev": -1.0}
    combined_p, payout = 1.0, 1.0
    for leg in legs:
        combined_p *= leg["p"]
        payout *= american_to_decimal(leg["price"])
    return {"combined_p": round(combined_p, 4), "payout": round(payout, 4),
            "ev": round(combined_p * payout - 1.0, 4)}


def _threshold_for_line(line: float) -> int:
    """Alt over line L is cleared by ceil(L) Ks (7.5 -> 8+)."""
    return math.ceil(line + 1e-9)


def price_legs(proj: dict, odds_rows: list[dict], *,
               thresholds=(8, 9, 10)) -> list[dict]:
    n = round(proj["batters_faced"])
    rate = proj["k_rate"]
    # group priced rows by threshold
    by_t: dict[int, list[dict]] = {}
    for r in odds_rows:
        if r.get("over_price") is None or r.get("line") is None:
            continue
        by_t.setdefault(_threshold_for_line(r["line"]), []).append(r)
    legs = []
    for t in thresholds:
        model_p = round(binom_prob_over(n, rate, t), 4)
        rows = by_t.get(t, [])
        fanduel = None
        for r in rows:
            if (r.get("book") or "").lower() == "fanduel":
                fanduel = {"price": r["over_price"],
                           "ev": leg_ev(model_p, r["over_price"])}
                break
        best = None
        if rows:
            br = max(rows, key=lambda r: american_to_decimal(r["over_price"]))
            best = {"book": br.get("book") or "", "price": br["over_price"],
                    "ev": leg_ev(model_p, br["over_price"])}
        legs.append({"threshold": t, "model_p": model_p,
                     "fanduel": fanduel, "best": best})
    return legs


def _open(repo):
    if repo is not None:
        return repo, None
    from db.migrate import get_connection
    from repositories.mlb_repo import MlbRepo
    conn = get_connection(DB_PATH)
    return MlbRepo(conn), conn


def _alt_prompt(rows: list[dict], as_of, book) -> str:
    stamp = " · ".join(x for x in ("Alt-strikeout model (FanDuel + best book)",
                                   f"as of {as_of}" if as_of else None, book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    lines = []
    for r in rows:
        head = f"{r['rank']}. {r['name']}"
        if r["team"] or r["opponent"]:
            head += f" ({r['team']} vs {r['opponent']})"
        parts = [head]
        for t in r["thresholds"]:
            seg = f"{t['threshold']}+ {round(t['model_p']*100)}%"
            if t["best"]:
                seg += f" (best {t['best']['price']:+d} ev {t['best']['ev']:+.2f})"
            parts.append(seg)
        parts.append(f"proj {r['k_mean']} K")
        lines.append(" — ".join(parts))
    body = "\n".join(lines) or "(no probable starters available yet)"
    return banner + (
        'Create a premium sports-betting "alt-strikeout board" graphic for the brand '
        '"Chances Make Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        'Big brush title at the top: "ALT-K BOARD". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(rows)} starting pitchers. Each row shows "
        "the pitcher (team vs opponent), the 8+/9+/10+ strikeout probabilities with the "
        "best book price and EV, and the projected K total. Even spacing.\n\n"
        "KEY: N+ % = our model probability of at least N strikeouts; price = best "
        "available alt-strikeout over; EV is per 1 unit. Most alt-K overs are −EV — the "
        "value is the rare +EV threshold, not chasing every arm. NOT guarantees.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, add, or invent any name, team, number, %, or odds.\n\n"
        f"PITCHERS:\n{body}"
    )


def alt_k_board(date: str, repo=None, *, count: int = ALT_K_BOARD_SIZE,
                as_of: str | None = None, book: str | None = None) -> dict:
    from brains.ev.watch import _opp_team_id
    repo, conn = _open(repo)
    try:
        # alt-K odds rows grouped by pitcher mlb_id
        odds_by_pid: dict[int, list[dict]] = {}
        for p in repo.latest_props(market="SO_ALT", official_date=date):
            if p.get("mlb_id") is None:
                continue
            odds_by_pid.setdefault(p["mlb_id"], []).append(p)

        scored, seen = [], set()
        for s in repo.probable_starters(date):
            mid = s["mlb_id"]
            if mid in seen:
                continue
            seen.add(mid)
            starter = {
                "mlb_id": mid, "name": s.get("name") or "",
                "team_abbr": s.get("team_abbr", ""), "opponent_abbr": s.get("opponent_abbr", ""),
                "opponent_team_id": _opp_team_id(repo, s.get("game_pk"), s.get("team_abbr", "")),
            }
            proj = k_model.k_projection(repo, date, starter)
            if proj is None or proj["k_mean"] <= 0:
                continue
            legs = price_legs(proj, odds_by_pid.get(mid, []))
            scored.append((proj, legs))
        scored.sort(key=lambda pl: pl[0]["ladder"].get(9, 0.0), reverse=True)

        rows = []
        for i, (proj, legs) in enumerate(scored[:count]):
            rows.append({
                "rank": i + 1, "name": (proj["name"] or "").upper(),
                "team": proj["team_abbr"], "opponent": proj["opponent_abbr"],
                "k_rate": round(proj["k_rate"], 3),
                "batters_faced": round(proj["batters_faced"], 1),
                "k_mean": round(proj["k_mean"], 1), "thresholds": legs,
            })
        return {"title": "ALT-K BOARD", "product": "Strikeout model (alt-K)",
                "count": len(rows), "rows": rows,
                "prompt": _alt_prompt(rows, as_of, book)}
    finally:
        if conn is not None:
            conn.close()
