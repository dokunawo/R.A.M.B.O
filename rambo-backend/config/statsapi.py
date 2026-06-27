"""
R.A.M.B.O. MLB Betting Agent — MLB Stats API config (Step 1)
config/statsapi.py

The FREE, public, keyless source for everything MLB publishes: rosters, schedule,
player season stats + handedness splits, and game logs. Used directly (httpx, in
the Step 2 client) in place of the three paid Apify actors the reference plan used
for this data.

Items land in raw_ingest under synthetic source ids ('mlb/statsapi:<kind>') so the
normalize dispatch treats them like any other feed. No spend guard — these are free.

Endpoint/param values below are templates the Step 2 client fills in. The schedule
+ probablePitcher + lineups shapes were spot-verified live; the stats/splits/gameLog
shapes must be re-verified against one real response in Step 3 before trusting them.
"""

from __future__ import annotations

BASE = "https://statsapi.mlb.com/api/v1"
SPORT_ID = 1  # MLB

# Synthetic source ids for raw_ingest (mirror the Apify actor_id convention).
SOURCE_ROSTER = "mlb/statsapi:roster"
SOURCE_SCHEDULE = "mlb/statsapi:schedule"
SOURCE_STATS = "mlb/statsapi:stats"
SOURCE_TEAMS = "mlb/statsapi:teams"
SOURCE_RECENT = "mlb/statsapi:recent"     # last-N-day date-range leaderboard
SOURCE_LINEUPS = "mlb/statsapi:lineups"   # confirmed boxscore battingOrder

# Path suffixes under BASE. {placeholders} are filled by the Step 2 client.
ENDPOINTS: dict[str, str] = {
    "schedule": "/schedule",
    "teams": "/teams",
    "team_roster": "/teams/{team_id}/roster",
    "sport_players": "/sports/{sport_id}/players",   # all active players + bio, one call
    "people": "/people/{person_id}",
    "people_stats": "/people/{person_id}/stats",
    "teams_stats": "/teams/stats",                   # all teams' season stats, one call/group
    "stats_range": "/stats",                          # league leaderboard for a date range
    "boxscore": "/game/{game_pk}/boxscore",           # confirmed lineups (battingOrder)
}

# Default query params per logical call (merged with runtime args).
DEFAULT_PARAMS: dict[str, dict] = {
    "schedule": {
        "sportId": SPORT_ID,
        "hydrate": "probablePitcher,lineups,team",
    },
    "teams": {"sportId": SPORT_ID, "activeStatus": "Y"},
    "team_roster": {"rosterType": "active"},
    "sport_players": {"sportId": SPORT_ID},   # season added at call time
    # Season totals + vs-RHP/LHP splits + game log in one call (sitCodes vr/vl).
    # VERIFY these stat/split keys against a real /people/{id}/stats response.
    "people_stats": {"stats": "season,statSplits,gameLog", "group": "hitting",
                     "sitCodes": "vr,vl"},
    # All teams' season runs (group=hitting → scored, group=pitching → allowed).
    "teams_stats": {"sportIds": SPORT_ID, "stats": "season"},
    # League-wide last-N-day leaderboard (group + startDate/endDate added at call time).
    "stats_range": {"stats": "byDateRange", "sportId": SPORT_ID, "limit": 2000},
}
