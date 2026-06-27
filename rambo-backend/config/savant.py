"""Baseball Savant (Statcast) config — free custom-leaderboard CSV for batter power
quality (barrel% + hard-hit%), the HR-model signals cowork uses. player_id is MLBAM."""
from __future__ import annotations

SOURCE_ID = "savant:statcast"


def csv_url(year: int) -> str:
    return ("https://baseballsavant.mlb.com/leaderboard/custom?"
            f"year={year}&type=batter&min=10"
            "&selections=barrel_batted_rate,hard_hit_percent&csv=true")
