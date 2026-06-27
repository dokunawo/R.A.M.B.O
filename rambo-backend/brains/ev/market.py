from __future__ import annotations
import math
from brains.ev.features import build_hr_features, build_count_features
from brains.ev.hr_model import hr_probability, edge, breakeven
from brains.ev.count_model import poisson_prob_over
from brains.ev.moneyline_model import (pythag_winpct, matchup_winprob, devig_two_way,
                                       expected_runs, winprob_from_runs,
                                       market_anchored_prob, evaluate_game)
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
                support=feat.support,
                tags=["EDGE"] + (["TEMP PARK"] if feat.temp_park else []), glow="gold",
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
    Uses pitching stats; no batter hand-split. (DK Pick6 labels this market 'SO'.)"""
    market_key = "k"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        props = [p for p in repo.latest_props(market="SO", resolved_only=True)
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
    """Team moneyline. Pitcher-adjusted run model, then MARKET-ANCHORED to the
    de-vigged book (the book is the sharp prior; the model only nudges it within
    realistic bounds). Output is an honest 'lean', not a claimed +EV play.
    Team-based: `mlb_id` carries the team id, headshot is the team logo, `breakeven`
    holds the no-vig book win%, `model_p` the anchored win%, `edge` the lean."""
    market_key = "ml"

    def raw_picks(self, repo, date: str) -> list[Pick]:
        season = int(date[:4])
        picks: list[Pick] = []
        for g in repo.moneyline_slate(date):
            ev = evaluate_game(repo, season, g)
            if ev is None:
                continue
            if ev["diff"] >= 0:
                tid, abbr, opp = g["home_team_id"], ev["home_abbr"], ev["away_abbr"]
                mp, bp, price, support = (ev["model_home"], ev["book_home"],
                                          g["home_price"], ev["home_support"])
            else:
                tid, abbr, opp = g["away_team_id"], ev["away_abbr"], ev["home_abbr"]
                mp, bp, price, support = (ev["model_away"], ev["book_away"],
                                          g["away_price"], ev["away_support"])
            abbr = abbr or ""
            picks.append(Pick(
                market="ml", mlb_id=tid, name=abbr.upper(), initials=abbr.upper(),
                team=abbr, opponent=opp or "", hand="",
                pick=f"MONEYLINE LEAN ({price:+d})", line=0.0, multiplier=float(price),
                breakeven=round(bp, 4), model_p=round(mp, 4), edge=round(mp - bp, 4),
                support=support, tags=["LEAN"], glow="gold",
                headshot_url=_TEAM_LOGO.format(team_id=tid), rationale="",
                game_pk=ev["game_pk"], game_datetime=ev["game_datetime"] or "",
            ))
        return picks


REGISTRY: dict[str, object] = {
    "hr": HRMarket(), "hrr": HRRMarket(), "sb": SBMarket(), "k": KMarket(),
    "ml": MoneylineMarket(),
}
