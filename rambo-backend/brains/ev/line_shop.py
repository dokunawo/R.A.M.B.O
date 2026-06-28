"""Moneyline line shopping — compare every book's price for a game and surface
the best available number plus its value vs the no-vig market consensus.

The data is already multi-book: The Odds API returns all US books (REGIONS=us)
into odds_lines, so this needs no new feed or budget. Pure functions over
latest-odds rows; the slate helper pulls them from MlbRepo.

"Edge" here is line-shopping value: how much the BEST available price beats the
market's own no-vig consensus fair probability — i.e. a book being generous
relative to the field, not a model claim. Honest by construction.
"""
from __future__ import annotations

from brains.ev.moneyline_model import devig_two_way

_SIDES = ("home", "away")


def american_to_decimal(odds: int) -> float:
    """Decimal payout incl. stake. +150 -> 2.5, -120 -> 1.8333…"""
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def _by_book(rows) -> dict:
    """Collapse latest moneyline rows to {book: {side: price}}, dropping live /
    suspended (price 0) lines whose numbers would poison a comparison."""
    out: dict = {}
    for r in rows:
        if r.get("market") != "moneyline":
            continue
        book, side, price = r.get("book") or "", r.get("side"), r.get("price")
        if not price or side not in _SIDES or "Live" in book:
            continue
        out.setdefault(book, {})[side] = price
    return out


def line_shop_game(rows) -> dict | None:
    """Best price per side + no-vig consensus + value across all books, for ONE
    game's latest moneyline rows (MlbRepo.latest_odds(game_pk, 'moneyline')).
    Returns None when no book quotes both sides."""
    by_book = _by_book(rows)
    two_sided = {b: s for b, s in by_book.items() if "home" in s and "away" in s}
    if not two_sided:
        return None

    # Consensus fair probability per side = mean of each book's no-vig number.
    consensus = {}
    for side in _SIDES:
        fair = []
        for s in two_sided.values():
            fh, fa = devig_two_way(s["home"], s["away"])
            fair.append(fh if side == "home" else fa)
        consensus[side] = sum(fair) / len(fair)

    sides = {}
    for side in _SIDES:
        quotes = [(b, s[side]) for b, s in by_book.items() if side in s]
        best_book, best_price = max(quotes, key=lambda bp: bp[1])   # best payout
        worst_price = min(p for _, p in quotes)
        fair_p = consensus[side]
        sides[side] = {
            "best_book": best_book,
            "best_price": best_price,
            "worst_price": worst_price,
            "consensus_prob": round(fair_p, 4),
            # +EV vs the field's own fair line — line-shopping value, not a model edge
            "edge": round(american_to_decimal(best_price) * fair_p - 1, 4),
            "n_quotes": len(quotes),
        }
    return {"n_books": len(two_sided), "sides": sides}


def line_shop_slate(repo, date: str) -> list[dict]:
    """Line-shop every game on `date` that has multi-book moneyline odds."""
    out = []
    for g in repo.moneyline_slate(date):
        shop = line_shop_game(repo.latest_odds(g["game_pk"], "moneyline"))
        if not shop:
            continue
        out.append({
            "game_pk": g["game_pk"],
            "home": g["home_team_abbr"],
            "away": g["away_team_abbr"],
            "game_datetime": g.get("game_datetime"),
            **shop,
        })
    return out
