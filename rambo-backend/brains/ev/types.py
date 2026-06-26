from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Pick:
    market: str            # "hr"
    mlb_id: int
    name: str              # display, upper-cased
    initials: str          # badge, e.g. "AJ"
    team: str              # abbr
    opponent: str          # abbr
    hand: str              # opposing pitcher hand ("L"/"R"/"")
    pick: str              # "1+ HOME RUN — OVER"
    line: float
    multiplier: float
    breakeven: float       # 1/multiplier
    model_p: float
    edge: float
    support: str           # e.g. "58 HR"
    tags: list[str]        # ["EDGE"]
    glow: str              # badge ring colour
    headshot_url: str
    rationale: str = ""

@dataclass
class HRFeatures:
    mlb_id: int
    name: str
    team_abbr: str
    opponent_abbr: str
    pitcher_hand: str
    hr_rate: float         # chosen per-PA rate (vs-hand or overall)
    park_factor: float
    line: float
    multiplier: float
    season_hr: int
