"""PrizePicks ingestion config — direct public API (free), MLB only. Power/Flex
payout tables are PrizePicks' published standard values; verify against current
payouts (they can vary by region/promo)."""
from __future__ import annotations

BASE = "https://api.prizepicks.com"
LEAGUE_ID = 2            # MLB
SOURCE_ID = "prizepicks"

# PrizePicks stat_type -> RAMBO market key. Only these (standard tier) are kept.
STAT_MARKET_MAP = {
    "Home Runs": "HR",
    "Pitcher Strikeouts": "SO",
    "Total Bases": "TB",
    "Hits": "H",
    "Hits+Runs+RBIs": "H+R+RBI",
    "Stolen Bases": "SB",
}

# Power Play: all N legs must hit -> fixed multiplier.
POWER = {2: 3.0, 3: 5.0, 4: 10.0, 5: 20.0, 6: 37.5}

# Flex Play: partial payouts. FLEX[n_legs][n_hits] = multiplier (missing key = 0).
FLEX = {
    3: {3: 2.25, 2: 1.25},
    4: {4: 5.0, 3: 1.5},
    5: {5: 10.0, 4: 2.0, 3: 0.4},
    6: {6: 25.0, 5: 2.0, 4: 0.4},
}
