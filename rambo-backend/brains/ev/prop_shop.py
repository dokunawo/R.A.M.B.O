"""Prop line shopping — grade each DK Pick6 leg against the real sportsbook market.

Pick6 is a multiplier pick'em (EV = P × mult − 1, so a leg's breakeven is 1/mult).
With sportsbook props now ingested (The Odds API per-event), we can de-vig each
book's over/under to a fair P(over) and ask: does the Pick6 multiplier beat the
book consensus fair line? Positive `value` = the Pick6 Over leg is +EV vs the
market — the honest signal a pick'em leg is actually worth taking.

Matches by (mlb_id, market, line) so the same player/market/number is compared.
"""
from __future__ import annotations

from brains.ev.moneyline_model import devig_two_way


def _is_pick6(book) -> bool:
    return "pick6" in (book or "").lower()


def compare_props(pick6_props, book_props) -> list[dict]:
    """pick6_props: rows with a `multiplier`; book_props: rows with over/under
    American prices. Both must carry mlb_id/market/line. Returns one comparison
    per Pick6 leg that has matching book prices, best `value` first."""
    idx: dict = {}
    for b in book_props:
        if (b.get("mlb_id") is None or b.get("over_price") is None
                or b.get("under_price") is None):
            continue
        idx.setdefault((b["mlb_id"], b["market"], b["line"]), []).append(b)

    out = []
    for p in pick6_props:
        mult = p.get("multiplier")
        if p.get("mlb_id") is None or not mult:
            continue
        books = idx.get((p["mlb_id"], p["market"], p["line"]))
        if not books:
            continue
        fairs, best = [], None
        for b in books:
            fair_over, _ = devig_two_way(b["over_price"], b["under_price"])
            fairs.append(fair_over)
            if best is None or b["over_price"] > best["over_price"]:
                best = b
        consensus = sum(fairs) / len(fairs)
        breakeven = 1.0 / mult
        value = consensus - breakeven
        out.append({
            "mlb_id": p["mlb_id"], "player": p.get("player_name_raw"),
            "market": p["market"], "line": p["line"],
            "pick6_multiplier": mult, "pick6_breakeven": round(breakeven, 4),
            "book_consensus_over": round(consensus, 4), "n_books": len(books),
            "best_book": best["book"], "best_over_price": best["over_price"],
            "value": round(value, 4),
            "verdict": "+EV vs books" if value > 0 else "-EV vs books",
        })
    out.sort(key=lambda r: r["value"], reverse=True)
    return out


def prop_shop_slate(repo, date: str, market: str | None = None) -> list[dict]:
    """Compare Pick6 legs to sportsbook props for every game on `date`."""
    props = []
    for g in repo.games_on(date):
        props += repo.latest_props(game_pk=g["game_pk"], market=market, resolved_only=True)
    pick6 = [p for p in props if _is_pick6(p.get("book")) and p.get("multiplier")]
    book = [p for p in props if not _is_pick6(p.get("book"))]
    return compare_props(pick6, book)
