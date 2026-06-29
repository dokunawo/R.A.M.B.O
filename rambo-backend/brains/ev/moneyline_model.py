from __future__ import annotations

# Transparent team moneyline model: Pythagorean win expectation from runs
# scored/allowed, blended into a matchup win probability (log5), compared to the
# de-vigged sportsbook line. edge = model_win_prob − no-vig_book_prob.

PYTHAG_EXP = 1.83  # standard MLB Pythagorean exponent
LG_ERA = 4.20      # league-average ERA (run-suppression baseline)

# Market-anchoring: the de-vigged closing line is the sharpest estimate available,
# so we treat it as the prior and let our (unvalidated) model only nudge it. We also
# clamp the model to realistic single-game MLB bounds — no real MLB game is a 90%
# favorite — so a miscalibrated model can't produce absurd "edges".
W_BOOK = 0.80       # weight on the market vs our model
GAME_P_LO = 0.35    # realistic single-game win-prob floor
GAME_P_HI = 0.67    # ...and ceiling


def market_anchored_prob(model_p: float, book_p: float, *, w_book: float = W_BOOK,
                         lo: float = GAME_P_LO, hi: float = GAME_P_HI) -> float:
    """Blend our model toward the de-vigged market price (book = prior), after
    clamping the model to a plausible single-game range. Returns a win prob that
    sits near the market and only leans where the model has real, bounded signal."""
    clamped = max(lo, min(hi, model_p))
    return w_book * book_p + (1.0 - w_book) * clamped


def expected_runs(team_runs_per_game: float, opp_starter_era: float,
                  lg_era: float = LG_ERA) -> float:
    """A team's expected runs this game = its season runs/game scaled by the
    opposing starter's ERA vs league average. A 2.10 ERA ace (half league) ~halves
    the offense's expected output; a league-average starter leaves it unchanged."""
    if team_runs_per_game <= 0 or lg_era <= 0:
        return 0.0
    return team_runs_per_game * (opp_starter_era / lg_era)


def winprob_from_runs(exp_home: float, exp_away: float,
                      exp: float = PYTHAG_EXP) -> float:
    """Pythagenpat-style win prob from each side's expected runs this game."""
    if exp_home <= 0 and exp_away <= 0:
        return 0.5
    denom = exp_home ** exp + exp_away ** exp
    return exp_home ** exp / denom if denom > 0 else 0.5


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


def evaluate_game(repo, season: int, g: dict) -> dict | None:
    """Both-side model/book numbers for one `moneyline_slate` game, or None when
    team run data is missing. `diff = model_home - book_home` (signed lean toward
    home). model_home/model_away are market-anchored and sum to 1.0."""
    hr, ar = repo.team_runs(g["home_team_id"], season), repo.team_runs(g["away_team_id"], season)
    if not hr or not ar:
        return None
    home_era = repo.pitcher_era(g["home_probable_pitcher_id"], season)
    away_era = repo.pitcher_era(g["away_probable_pitcher_id"], season)
    hg, ag = hr["games_played"], ar["games_played"]
    if home_era and away_era and hg and ag:
        exp_home = expected_runs(hr["runs_scored"] / hg, away_era)
        exp_away = expected_runs(ar["runs_scored"] / ag, home_era)
        model_home = winprob_from_runs(exp_home, exp_away)
        home_support = f"vs {away_era:.2f} ERA SP"
        away_support = f"vs {home_era:.2f} ERA SP"
    else:
        model_home = matchup_winprob(
            pythag_winpct(hr["runs_scored"], hr["runs_allowed"]),
            pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
        home_support = away_support = "Pythag (no SP)"
    book_home, book_away = devig_two_way(g["home_price"], g["away_price"])
    anchored_home = market_anchored_prob(model_home, book_home)
    return {
        "game_pk": g["game_pk"], "game_datetime": g.get("game_datetime"),
        "home_abbr": g["home_team_abbr"], "away_abbr": g["away_team_abbr"],
        "home_price": g["home_price"], "away_price": g["away_price"],
        "book_home": book_home, "book_away": book_away,
        "model_home": anchored_home, "model_away": 1.0 - anchored_home,
        "diff": anchored_home - book_home,
        "home_support": home_support, "away_support": away_support,
    }


def evaluate_game_asof(repo, season: int, g: dict, before_date: str) -> dict | None:
    """Point-in-time twin of evaluate_game: builds team-run and starter-ERA
    features from data STRICTLY BEFORE `before_date` (no leakage), anchors to the
    given de-vigged line, and returns the same dict shape. None when as-of team
    run data is missing. Used by the walk-forward backtest."""
    hr = repo.team_runs_asof(g["home_team_id"], season, before_date)
    ar = repo.team_runs_asof(g["away_team_id"], season, before_date)
    if not hr or not ar:
        return None
    home_era = repo.pitcher_era_asof(g["home_probable_pitcher_id"], season, before_date)
    away_era = repo.pitcher_era_asof(g["away_probable_pitcher_id"], season, before_date)
    hg, ag = hr["games_played"], ar["games_played"]
    if home_era and away_era and hg and ag:
        exp_home = expected_runs(hr["runs_scored"] / hg, away_era)
        exp_away = expected_runs(ar["runs_scored"] / ag, home_era)
        model_home = winprob_from_runs(exp_home, exp_away)
    else:
        model_home = matchup_winprob(
            pythag_winpct(hr["runs_scored"], hr["runs_allowed"]),
            pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
    book_home, book_away = devig_two_way(g["home_price"], g["away_price"])
    anchored_home = market_anchored_prob(model_home, book_home)
    return {
        "game_pk": g["game_pk"],
        "home_abbr": g["home_team_abbr"], "away_abbr": g["away_team_abbr"],
        "home_price": g["home_price"], "away_price": g["away_price"],
        "book_home": book_home, "book_away": book_away,
        "model_home": anchored_home, "model_away": 1.0 - anchored_home,
        "diff": anchored_home - book_home,
    }
