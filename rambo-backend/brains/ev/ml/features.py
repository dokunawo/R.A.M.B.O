"""Point-in-time features for the learned moneyline model. A game's features are
built as-of its own date via the leak-free _asof reads, so training rows never see
their own outcome. Three features: run differential, starter-ERA differential,
Pythagorean win% differential — all home-minus-away."""
from __future__ import annotations

from brains.ev.moneyline_model import pythag_winpct

LG_ERA = 4.20
FEATURE_NAMES = ["run_diff", "era_diff", "pythag_diff"]


def game_feature_vector(repo, season: int, game: dict,
                        before_date: str) -> list[float] | None:
    """[run_diff, era_diff, pythag_diff] for one game, or None if as-of team-run
    data is missing. era_diff = away_era - home_era (positive favors home)."""
    hr = repo.team_runs_asof(game["home_team_id"], season, before_date)
    ar = repo.team_runs_asof(game["away_team_id"], season, before_date)
    if not hr or not ar:
        return None
    hg, ag = hr["games_played"], ar["games_played"]
    if hg <= 0 or ag <= 0:
        return None
    run_diff = ((hr["runs_scored"] - hr["runs_allowed"]) / hg
                - (ar["runs_scored"] - ar["runs_allowed"]) / ag)
    home_era = repo.pitcher_era_asof(game["home_probable_pitcher_id"], season,
                                     before_date)
    if home_era is None:
        home_era = LG_ERA
    away_era = repo.pitcher_era_asof(game["away_probable_pitcher_id"], season,
                                     before_date)
    if away_era is None:
        away_era = LG_ERA
    era_diff = away_era - home_era
    pythag_diff = (pythag_winpct(hr["runs_scored"], hr["runs_allowed"])
                   - pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
    return [run_diff, era_diff, pythag_diff]


def training_set(repo, season: int,
                 before_date: str) -> tuple[list[list[float]], list[int]]:
    """Labeled training matrix from all final games strictly before `before_date`.
    Each game's features are as-of ITS OWN date (leak-free); label = 1 if home won."""
    X: list[list[float]] = []
    y: list[int] = []
    for g in repo.training_games(season, before_date):
        vec = game_feature_vector(repo, season, g, g["official_date"])
        if vec is None:
            continue
        X.append(vec)
        y.append(1 if g["home_score"] > g["away_score"] else 0)
    return X, y
