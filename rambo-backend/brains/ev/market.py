from __future__ import annotations
from brains.ev.features import build_hr_features
from brains.ev.hr_model import hr_probability, edge, breakeven
from brains.ev.types import Pick

_HEADSHOT = ("https://img.mlbstatic.com/mlb-photos/image/upload/"
             "w_180,q_auto/v1/people/{mlb_id}/headshot/67/current")

def _initials(name: str) -> str:
    toks = name.replace("-", " ").split()
    return "".join(t[0] for t in toks if t and t[0].isalpha())[:3].upper()

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

REGISTRY: dict[str, object] = {"hr": HRMarket()}
