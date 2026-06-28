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


# Statcast power baselines (league-average barrel% / hard-hit%).
LG_BARREL, LG_HARD_HIT = 7.5, 39.0


def _power_modifier(sc: Optional[dict]) -> float:
    """barrel% + hard-hit% -> HR-rate multiplier; hot bat boosts, weak fades. Clamped
    so a quality signal nudges (not overrides) the realized rate."""
    if not sc:
        return 1.0
    b, h = sc.get("barrel_rate"), sc.get("hard_hit")
    rb = (b / LG_BARREL) if b else 1.0
    rh = (h / LG_HARD_HIT) if h else 1.0
    return max(0.75, min(1.35, 0.65 * rb + 0.35 * rh))   # barrel weighted (HR proxy)


# Temp venues with no multi-year HR park factor (A's at Sutter Health, Rays at
# Steinbrenner) — park factor is unverified, so HR legs there get flagged, no boost.
TEMP_PARKS = {"ATH", "OAK", "SAC", "TB"}


def _weather_modifier(weather: Optional[dict]) -> float:
    """temp + field-relative wind -> HR-rate multiplier (heat & wind-out boost,
    wind-in fades). Neutral when weather isn't posted yet. Clamped."""
    if not weather:
        return 1.0
    m = 1.0
    try:
        if weather.get("temp") is not None:
            m *= 1.0 + max(-0.10, min(0.12, (float(weather["temp"]) - 70) * 0.004))
    except (TypeError, ValueError):
        pass
    wind = (weather.get("wind") or "").lower()
    if "out" in wind:
        m *= 1.08
    elif "in" in wind:
        m *= 0.92
    return max(0.85, min(1.20, m))


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
    """HR features for a DK Pick6 prop. Carries the prop's line/multiplier (used by
    the HR market for edge)."""
    return build_hr_features_core(
        repo, date, prop["mlb_id"], prop["player_name_raw"],
        line=prop["line"], multiplier=prop["multiplier"])


def build_hr_features_core(repo, date: str, mlb_id: int, name: str, *,
                           line: float = 0.5,
                           multiplier: float = 0.0) -> Optional[HRFeatures]:
    """HR features for ANY hitter from their mlb_id (no prop required) — powers the
    slate-wide Player Watch pool. `line`/`multiplier` default to a 1+ HR line with no
    payout; pass the prop's values to drive the propped-market edge math."""
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
    temp_park = False
    weather_mod = 1.0
    ctx = repo.player_game_context(mlb_id, date)
    if ctx:
        team_abbr = ctx["team_abbr"] or ""
        opp_abbr = ctx["opponent_abbr"] or ""
        home_abbr = ctx["home_abbr"] or ""
        temp_park = home_abbr in TEMP_PARKS
        park = 1.0 if temp_park else hr_factor(home_abbr)   # temp park = no verified boost
        if ctx["opp_pitcher_id"]:
            hand = repo.pitcher_throws(ctx["opp_pitcher_id"]) or ""
        splits = stats.get("splits") or {}
        if hand == "L":
            rate = _hr_rate(splits.get("vl")) or overall
        elif hand == "R":
            rate = _hr_rate(splits.get("vr")) or overall
        weather_mod = _weather_modifier(repo.game_weather(ctx["game_pk"]))

    # Recency: blend the season/matchup rate with the last-15 HR rate.
    recent = repo.player_recent(mlb_id, "hitting")
    rate = _blend(_hr_rate(recent), rate)
    # Statcast power quality + weather nudge the rate.
    rate = rate * _power_modifier(repo.player_statcast(mlb_id, season)) * weather_mod
    recent_hr = int((recent or {}).get("homeRuns") or 0)
    support = f"{recent_hr} HR L15" if recent is not None else f"{season_hr} HR"
    if temp_park:
        support += " · TEMP PARK"

    return HRFeatures(
        mlb_id=mlb_id, name=name, team_abbr=team_abbr,
        opponent_abbr=opp_abbr, pitcher_hand=hand, hr_rate=rate,
        park_factor=park, line=line, multiplier=multiplier,
        season_hr=season_hr, recent_hr=recent_hr, support=support, temp_park=temp_park,
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
    """Per-game counting-prop features for a DK Pick6 prop (carries line/multiplier)."""
    return build_count_features_core(
        repo, date, prop["mlb_id"], prop["player_name_raw"],
        stat_keys=stat_keys, label=label, group=group, games_key=games_key,
        use_splits=use_splits, line=prop["line"], multiplier=prop["multiplier"])


def build_count_features_core(repo, date: str, mlb_id: int, name: str, *,
                              stat_keys: list[str], label: str, group: str = "hitting",
                              games_key: str = "gamesPlayed", use_splits: bool = True,
                              line: float = 0.0, multiplier: float = 0.0
                              ) -> Optional[CountFeatures]:
    """Per-game counting-prop features for ANY player from their mlb_id (no prop
    required) — powers slate-wide boards like Strikeout Watch. For batter props
    (`use_splits=True`) it picks the vs-hand split mean when the opposing pitcher's
    hand is known. For pitcher props (K, `use_splits=False`) it uses the overall
    per-start mean. No park factor."""
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
        mlb_id=mlb_id, name=name, team_abbr=team_abbr,
        opponent_abbr=opp_abbr, pitcher_hand=hand, per_game_mean=mean,
        line=line, multiplier=multiplier,
        support=f"{shown:.1f} {label}/gm {window}",
    )
