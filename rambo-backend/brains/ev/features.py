from __future__ import annotations
import json
from typing import Optional
from brains.ev.parks import hr_factor
from brains.ev.types import HRFeatures

def _hr_rate(stat: Optional[dict]) -> Optional[float]:
    if not stat:
        return None
    try:
        hr = float(stat.get("homeRuns"))
        pa = float(stat.get("plateAppearances"))
    except (TypeError, ValueError):
        return None
    return hr / pa if pa > 0 else None

def build_hr_features(repo, date: str, prop: dict) -> Optional[HRFeatures]:
    mlb_id = prop["mlb_id"]
    season = int(date[:4])
    rows = repo.player_season(mlb_id, season, "hitting")
    if not rows:
        return None
    stats = json.loads(rows[0]["stats"])
    season_stat = stats.get("season") or {}
    overall = _hr_rate(season_stat)
    if overall is None:
        return None
    season_hr = int(season_stat.get("homeRuns") or 0)

    team_abbr = opp_abbr = ""
    park = 1.0
    hand = ""
    rate = overall
    ctx = repo.player_game_context(mlb_id, date)
    if ctx:
        team_abbr = ctx["team_abbr"] or ""
        opp_abbr = ctx["opponent_abbr"] or ""
        park = hr_factor(ctx["home_abbr"])
        if ctx["opp_pitcher_id"]:
            hand = repo.pitcher_throws(ctx["opp_pitcher_id"]) or ""
        splits = stats.get("splits") or {}
        if hand == "L":
            rate = _hr_rate(splits.get("vl")) or overall
        elif hand == "R":
            rate = _hr_rate(splits.get("vr")) or overall

    return HRFeatures(
        mlb_id=mlb_id, name=prop["player_name_raw"], team_abbr=team_abbr,
        opponent_abbr=opp_abbr, pitcher_hand=hand, hr_rate=rate,
        park_factor=park, line=prop["line"], multiplier=prop["multiplier"],
        season_hr=season_hr,
    )
