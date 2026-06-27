"""Per-market betting-slip export. Turns the EV brain's ranked `Pick`s into a
fixed-size roster + a ready-to-paste ChatGPT prompt the operator uses to generate
the slip graphic. Formatting only — no modeling. See `api/betting.py` (/betting/slip)."""
from __future__ import annotations
from brains.ev.types import Pick

# Roster size per market (operator-set; overridable via the endpoint's `count`).
SLIP_SIZE = {"hr": 6, "hrr": 8, "sb": 6, "k": 6, "ml": 8}

MARKET_TITLE = {
    "hr": "HOME RUNS", "hrr": "HITS + RUNS + RBIS", "sb": "STOLEN BASES",
    "k": "STRIKEOUTS", "ml": "MONEYLINE",
}

# Lane label so a number here is never mistaken for a cowork-style sportsbook prop.
PRODUCT = {
    "hr": "DK Pick6", "hrr": "DK Pick6", "sb": "DK Pick6", "k": "DK Pick6",
    "ml": "Moneyline (de-vig book lean)",
}


def slip_label(pick: Pick) -> str:
    """Short slip phrasing. Props drop the '— OVER' suffix; moneyline becomes
    '{TEAM} ML {+/-price}' (price is the American odds carried in `multiplier`)."""
    if pick.market == "ml":
        return f"{pick.team} ML {int(pick.multiplier):+d}"
    return pick.pick.split("—")[0].strip()      # "1+ HOME RUN — OVER" -> "1+ HOME RUN"


def _confidence_word(market: str) -> str:
    return "to win" if market == "ml" else "to hit"


def build_slip(picks: list[Pick], market: str, count: int | None = None, *,
               as_of: str | None = None, book: str | None = None) -> dict:
    """Rank `picks` for the slip (props by hit-probability, moneyline by lean),
    take the top N, and return the roster + a copy-paste ChatGPT prompt. `as_of`/
    `book` stamp the slip's provenance (product label + data-as-of)."""
    requested = count or SLIP_SIZE.get(market, 6)
    product = PRODUCT.get(market, market.upper())
    if market == "ml":
        ordered = sorted(picks, key=lambda p: (p.game_datetime or "~", p.team))
    else:
        ordered = sorted(picks, key=lambda p: p.model_p, reverse=True)
    # One play per player: prop ladders repeat a player; keep each player's first
    # (best-ranked / earliest) row before taking the top N.
    seen: set[int] = set()
    ranked: list[Pick] = []
    for p in ordered:
        if p.mlb_id in seen:
            continue
        seen.add(p.mlb_id)
        ranked.append(p)
    ranked = ranked[:requested]

    players = [{
        "rank": i + 1,
        "mlb_id": p.mlb_id,
        "name": p.name,
        "team": p.team,
        "opponent": p.opponent,
        "hand": p.hand,
        "pick": slip_label(p),
        "model_pct": round(p.model_p * 100),
        "edge_pct": round(p.edge * 100, 1),
        "support": p.support,
    } for i, p in enumerate(ranked)]

    title = MARKET_TITLE.get(market, market.upper())
    return {
        "title": title,
        "product": product,
        "count": len(players),
        "requested": requested,
        "shortfall": max(0, requested - len(players)),
        "players": players,
        "prompt": _build_prompt(title, market, players, product, as_of, book),
    }


def _build_prompt(title: str, market: str, players: list[dict],
                  product: str = "", as_of: str | None = None,
                  book: str | None = None) -> str:
    conf = _confidence_word(market)
    stamp = " · ".join(x for x in (product, f"as of {as_of}" if as_of else None,
                                   book) if x)
    banner = f"[{stamp}]\n\n" if stamp else ""
    lines = []
    for p in players:
        if market == "ml":
            lines.append(f"{p['rank']}. {p['team']} vs {p['opponent']} — "
                         f"{p['pick']} — {p['model_pct']}% {conf}")
        else:
            lines.append(f"{p['rank']}. {p['name']} ({p['team']} vs {p['opponent']}) — "
                         f"{p['pick']} — {p['model_pct']}% {conf}")
    roster = "\n".join(lines) if lines else "(no plays available for this market today)"

    return banner + (
        'Create a premium sports-betting slip graphic for the brand "Chances Make '
        'Champions" (CMC).\n\n'
        "STYLE: cinematic, black background with gold and amber smoke, floating gold "
        "dust, a gold crown, gritty brush/graffiti lettering, neon-gold accents. "
        f'Big brush title at the top: "{title}". Moody, high-end, premium.\n\n'
        f"LAYOUT: a clean numbered list of {len(players)} plays. Each row shows the "
        "player/team, the matchup (team vs opponent), the pick, and the model "
        "confidence %. Even spacing, easy to read.\n\n"
        "CRITICAL: reproduce ALL text below EXACTLY as written — do not change, "
        "abbreviate, reorder, or misspell any name, team, number, or %.\n\n"
        f"PLAYS:\n{roster}"
    )
