from __future__ import annotations
import math
from brains.ev.features import build_hr_features, build_count_features
from brains.ev.hr_model import hr_probability, edge, breakeven
from brains.ev.count_model import poisson_prob_over
from brains.ev.types import Pick, CountFeatures

_HEADSHOT = ("https://img.mlbstatic.com/mlb-photos/image/upload/"
             "w_180,q_auto/v1/people/{mlb_id}/headshot/67/current")

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


REGISTRY: dict[str, object] = {"hr": HRMarket(), "hrr": HRRMarket(), "sb": SBMarket()}
