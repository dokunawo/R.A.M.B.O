from __future__ import annotations
import json
import os
from typing import Optional
from brains.ev.parks import hr_factor
from brains.ev.types import HRFeatures, CountFeatures

# Recency weight: recent (last-15) form is the primary signal, season-long is context
# (cowork philosophy). Tunable via RAMBO_RECENT_WEIGHT.
RECENT_WEIGHT = float(os.environ.get("RAMBO_RECENT_WEIGHT", "0.55"))


def _blend(recent: Optional[float], season: Optional[float],
           w: float = RECENT_WEIGHT) -> Optional[float]:
    """Weighted blend of recent vs season; falls back to whichever exists."""
    if recent is None:
        return season
    if season is None:
        return recent
    return w * recent + (1.0 - w) * season


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

    # Recency: blend the season/matchup rate with the last-15 HR rate.
    recent = repo.player_recent(mlb_id, "hitting")
    rate = _blend(_hr_rate(recent), rate)
    recent_hr = int((recent or {}).get("homeRuns") or 0)
    support = f"{recent_hr} HR L15" if recent is not None else f"{season_hr} HR"

    return HRFeatures(
        mlb_id=mlb_id, name=prop["player_name_raw"], team_abbr=team_abbr,
        opponent_abbr=opp_abbr, pitcher_hand=hand, hr_rate=rate,
        park_factor=park, line=prop["line"], multiplier=prop["multiplier"],
        season_hr=season_hr, recent_hr=recent_hr, support=support,
    )


def _per_game_sum(stat: Optional[dict], keys: list[str],
                  games_key: str = "gamesPlayed") -> Optional[float]:
    """Mean per game of summed stat keys (e.g. hits+runs+rbi) / gamesPlayed."""
    if not stat:
        return None
    try:
        games = float(stat.get(games_key))
        total = sum(float(stat.get(k) or 0) for k in keys)
    except (TypeError, ValueError):
        return None
    return total / games if games > 0 else None


def build_count_features(repo, date: str, prop: dict, *, stat_keys: list[str],
                         label: str, group: str = "hitting",
                         games_key: str = "gamesPlayed",
                         use_splits: bool = True) -> Optional[CountFeatures]:
    """Per-game counting-prop features (H+R+RBI, SB, K). For batter props
    (`use_splits=True`) it picks the vs-hand split mean when the opposing pitcher's
    hand is known. For pitcher props (K, `use_splits=False`) the opposing-pitcher
    hand is irrelevant, so it uses the overall per-start mean. No park factor."""
    mlb_id = prop["mlb_id"]
    season = int(date[:4])
    rows = repo.player_season(mlb_id, season, group)
    if not rows:
        return None
    stats = json.loads(rows[0]["stats"])
    overall = _per_game_sum(stats.get("season") or {}, stat_keys, games_key)
    if overall is None:
        return None

    team_abbr = opp_abbr = ""
    hand = ""
    mean = overall
    ctx = repo.player_game_context(mlb_id, date)
    if ctx:
        team_abbr = ctx["team_abbr"] or ""
        opp_abbr = ctx["opponent_abbr"] or ""
        if use_splits and ctx["opp_pitcher_id"]:
            hand = repo.pitcher_throws(ctx["opp_pitcher_id"]) or ""
            splits = stats.get("splits") or {}
            if hand == "L":
                mean = _per_game_sum(splits.get("vl"), stat_keys, games_key) or overall
            elif hand == "R":
                mean = _per_game_sum(splits.get("vr"), stat_keys, games_key) or overall

    # Recency: blend the season/matchup mean with the last-15 per-game mean.
    recent_mean = _per_game_sum(repo.player_recent(mlb_id, group), stat_keys, games_key)
    mean = _blend(recent_mean, mean)
    shown = recent_mean if recent_mean is not None else overall
    window = "L15" if recent_mean is not None else "season"

    return CountFeatures(
        mlb_id=mlb_id, name=prop["player_name_raw"], team_abbr=team_abbr,
        opponent_abbr=opp_abbr, pitcher_hand=hand, per_game_mean=mean,
        line=prop["line"], multiplier=prop["multiplier"],
        support=f"{shown:.1f} {label}/gm {window}",
    )
