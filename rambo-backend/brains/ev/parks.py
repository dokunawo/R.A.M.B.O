from __future__ import annotations

# Approximate HR park factors (1.0 = neutral). Refine from Statcast park factors later.
PARK_HR_FACTOR: dict[str, float] = {
    "COL": 1.18, "CIN": 1.12, "NYY": 1.10, "PHI": 1.07, "BAL": 1.06,
    "MIL": 1.05, "BOS": 1.04, "ARI": 1.03, "ATL": 1.02, "HOU": 1.02,
    "TOR": 1.01, "CHC": 1.00, "LAD": 1.00, "MIN": 1.00, "TEX": 1.00,
    "WSH": 0.99, "STL": 0.98, "SD": 0.97, "NYM": 0.97, "CLE": 0.97,
    "CWS": 0.97, "TB": 0.96, "DET": 0.95, "KC": 0.95, "LAA": 0.95,
    "SEA": 0.93, "OAK": 0.92, "PIT": 0.92, "MIA": 0.90, "SF": 0.88,
}

def hr_factor(team_abbr: str) -> float:
    return PARK_HR_FACTOR.get((team_abbr or "").upper(), 1.0)
