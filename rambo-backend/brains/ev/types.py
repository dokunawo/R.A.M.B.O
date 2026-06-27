from __future__ import annotations
from dataclasses import dataclass

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
    game_pk: int = 0
    game_datetime: str = ""

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
    recent_hr: int = 0          # HR over the last-15 window (recency signal)
    support: str = ""           # display, e.g. "4 HR L15" (falls back to season)
    temp_park: bool = False     # temp venue (A's/Rays) — park factor unverified

@dataclass
class CountFeatures:
    """Per-game counting-prop features (H+R+RBI, SB, K). `per_game_mean` is the
    chosen Poisson mean (vs-hand split or overall)."""
    mlb_id: int
    name: str
    team_abbr: str
    opponent_abbr: str
    pitcher_hand: str
    per_game_mean: float
    line: float
    multiplier: float
    support: str
