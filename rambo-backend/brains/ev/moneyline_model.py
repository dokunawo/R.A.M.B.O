from __future__ import annotations

# Transparent team moneyline model: Pythagorean win expectation from runs
# scored/allowed, blended into a matchup win probability (log5), compared to the
# de-vigged sportsbook line. edge = model_win_prob − no-vig_book_prob.

PYTHAG_EXP = 1.83  # standard MLB Pythagorean exponent


def pythag_winpct(runs_scored: float, runs_allowed: float,
                  exp: float = PYTHAG_EXP) -> float:
    """Expected win% from runs scored/allowed. Neutral (0.5) if no data."""
    rs, ra = float(runs_scored or 0), float(runs_allowed or 0)
    if rs <= 0 and ra <= 0:
        return 0.5
    denom = rs ** exp + ra ** exp
    return rs ** exp / denom if denom > 0 else 0.5


def matchup_winprob(home_winpct: float, away_winpct: float) -> float:
    """log5 — probability the home team beats the away team given each team's
    overall win%. (Home-field advantage omitted in v1.)"""
    num = home_winpct * (1.0 - away_winpct)
    den = num + (1.0 - home_winpct) * away_winpct
    return num / den if den > 0 else 0.5


def american_to_implied(odds: int) -> float:
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


def devig_two_way(home_odds: int, away_odds: int) -> tuple[float, float]:
    """Two-way no-vig probabilities (home, away), summing to 1.0."""
    ih, ia = american_to_implied(home_odds), american_to_implied(away_odds)
    total = ih + ia
    return ih / total, ia / total
