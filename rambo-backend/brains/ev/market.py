from __future__ import annotations
import math
from brains.ev.features import build_hr_features, build_count_features
from brains.ev.hr_model import hr_probability, edge, breakeven
from brains.ev.count_model import poisson_prob_over
from brains.ev.moneyline_model import (pythag_winpct, matchup_winprob, devig_two_way,
                                       expected_runs, winprob_from_runs)
from brains.ev.types import Pick, CountFeatures

_HEADSHOT = ("https://img.mlbstatic.com/mlb-photos/image/upload/"
             "w_180,q_auto/v1/people/{mlb_id}/headshot/67/current")
_TEAM_LOGO = "https://www.mlbstatic.com/team-logos/{team_id}.svg"

def _initials(name: str) -> str:
    toks = name.replace("-", " ").split()
    return "".join(t[0] for t in toks if t and t[0].isalpha())[:3].upper()


def _count_pick(market: str, feat: CountFeatures, p: float, *,
                word: str, glow: str) -> Pick:
    model_p = round(p, 4)
    return Pick(
        market=market, mlb_id=feat.mlb_id, name=feat.name.upper(),
        initials=_initials(feat.name), team=feat.team_abbr,
        opponent=feat.opponent_abbr, hand=feat.pitcher_hand,
        pick=f"{math.ceil(feat.line)}+ {word} — OVER", line=feat.line,
        multiplier=feat.multiplier, breakeven=round(breakeven(feat.multiplier), 4),
        model_p=model_p, edge=round(edge(model_p, feat.multiplier), 4),
        support=feat.support, tags=["EDGE"], glow=glow,
        headshot_url=_HEADSHOT.format(mlb_id=feat.mlb_id), rationale="",
    )

class HRMarket:
    market_key = "hr"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        props = [p for p in repo.latest_props(market="HR", resolved_only=True)
                 if p["line"] == 0.5 and p["multiplier"]]
        picks: list[Pick] = []
        for prop in props:
            feat = build_hr_features(repo, date, prop)
            if feat is None:
                continue
            p = hr_probability(feat.hr_rate, feat.park_factor)
            model_p = round(p, 4)
            picks.append(Pick(
                market="hr", mlb_id=feat.mlb_id, name=feat.name.upper(),
                initials=_initials(feat.name), team=feat.team_abbr,
                opponent=feat.opponent_abbr, hand=feat.pitcher_hand,
                pick="1+ HOME RUN — OVER", line=feat.line,
                multiplier=feat.multiplier, breakeven=round(breakeven(feat.multiplier), 4),
                model_p=model_p, edge=round(edge(model_p, feat.multiplier), 4),
                support=f"{feat.season_hr} HR", tags=["EDGE"], glow="gold",
                headshot_url=_HEADSHOT.format(mlb_id=feat.mlb_id), rationale="",
            ))
        return picks

class HRRMarket:
    """Hits + Runs + RBIs (batter). Poisson on per-game H+R+RBI."""
    market_key = "hrr"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        props = [p for p in repo.latest_props(market="H+R+RBI", resolved_only=True)
                 if p["multiplier"]]
        picks: list[Pick] = []
        for prop in props:
            feat = build_count_features(repo, date, prop,
                                        stat_keys=["hits", "runs", "rbi"], label="H+R+RBI")
            if feat is None:
                continue
            p = poisson_prob_over(feat.per_game_mean, feat.line)
            picks.append(_count_pick("hrr", feat, p, word="H+R+RBI", glow="blue"))
        return picks


class SBMarket:
    """Stolen Bases (batter). Poisson on per-game SB."""
    market_key = "sb"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        props = [p for p in repo.latest_props(market="SB", resolved_only=True)
                 if p["multiplier"]]
        picks: list[Pick] = []
        for prop in props:
            feat = build_count_features(repo, date, prop,
                                        stat_keys=["stolenBases"], label="SB")
            if feat is None:
                continue
            p = poisson_prob_over(feat.per_game_mean, feat.line)
            picks.append(_count_pick("sb", feat, p, word="STOLEN BASE", glow="green"))
        return picks


class KMarket:
    """Pitcher Strikeouts. Poisson on per-start K (strikeOuts / gamesStarted).
    Uses pitching stats; no batter hand-split. (DK Pick6 market code 'K'.)"""
    market_key = "k"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        props = [p for p in repo.latest_props(market="K", resolved_only=True)
                 if p["multiplier"]]
        picks: list[Pick] = []
        for prop in props:
            feat = build_count_features(repo, date, prop, stat_keys=["strikeOuts"],
                                        label="K", group="pitching",
                                        games_key="gamesStarted", use_splits=False)
            if feat is None:
                continue
            p = poisson_prob_over(feat.per_game_mean, feat.line)
            picks.append(_count_pick("k", feat, p, word="STRIKEOUTS", glow="gold"))
        return picks


class MoneylineMarket:
    """Team moneyline. Pythagorean win expectation (runs scored/allowed) blended via
    log5, compared to the de-vigged sportsbook line. One +EV side per game.
    Team-based: `mlb_id` carries the team id, headshot is the team logo, `breakeven`
    holds the no-vig book win%, `multiplier` holds the American price."""
    market_key = "ml"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        season = int(date[:4])
        picks: list[Pick] = []
        for g in repo.moneyline_slate(date):
            hr, ar = repo.team_runs(g["home_team_id"], season), repo.team_runs(g["away_team_id"], season)
            if not hr or not ar:
                continue
            home_era = repo.pitcher_era(g["home_probable_pitcher_id"], season)
            away_era = repo.pitcher_era(g["away_probable_pitcher_id"], season)
            hg, ag = hr["games_played"], ar["games_played"]
            if home_era and away_era and hg and ag:
                # pitcher-adjusted: each offense vs the OPPOSING starter
                exp_home = expected_runs(hr["runs_scored"] / hg, away_era)
                exp_away = expected_runs(ar["runs_scored"] / ag, home_era)
                model_home = winprob_from_runs(exp_home, exp_away)
                home_support = f"vs {away_era:.2f} ERA SP"
                away_support = f"vs {home_era:.2f} ERA SP"
            else:
                # fallback: pure season Pythagorean (no starter info)
                model_home = matchup_winprob(
                    pythag_winpct(hr["runs_scored"], hr["runs_allowed"]),
                    pythag_winpct(ar["runs_scored"], ar["runs_allowed"]))
                home_support = away_support = "Pythag (no SP)"
            book_home, book_away = devig_two_way(g["home_price"], g["away_price"])
            if model_home - book_home >= (1.0 - model_home) - book_away:
                tid, abbr, opp = g["home_team_id"], g["home_team_abbr"], g["away_team_abbr"]
                mp, bp, price, support = model_home, book_home, g["home_price"], home_support
            else:
                tid, abbr, opp = g["away_team_id"], g["away_team_abbr"], g["home_team_abbr"]
                mp, bp, price, support = 1.0 - model_home, book_away, g["away_price"], away_support
            abbr = abbr or ""
            picks.append(Pick(
                market="ml", mlb_id=tid, name=abbr.upper(), initials=abbr.upper(),
                team=abbr, opponent=opp or "", hand="",
                pick=f"MONEYLINE ({price:+d})", line=0.0, multiplier=float(price),
                breakeven=round(bp, 4), model_p=round(mp, 4), edge=round(mp - bp, 4),
                support=support, tags=["EDGE"], glow="gold",
                headshot_url=_TEAM_LOGO.format(team_id=tid), rationale="",
            ))
        return picks


REGISTRY: dict[str, object] = {
    "hr": HRMarket(), "hrr": HRRMarket(), "sb": SBMarket(), "k": KMarket(),
    "ml": MoneylineMarket(),
}
