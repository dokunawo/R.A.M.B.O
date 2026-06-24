"""Build the ElevenLabs voice-credit payload for the HUD.

Combines the local month-to-date character count with the real ElevenLabs
balance when the key has User:Read (otherwise real is None and the HUD falls
back to local). Never raises into the request path.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from tts import get_subscription

DEFAULT_MONTHLY_LIMIT = 10000  # ElevenLabs free tier


def _month_bounds():
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # First day of next month → reset date.
    if start.month == 12:
        reset = start.replace(year=start.year + 1, month=1)
    else:
        reset = start.replace(month=start.month + 1)
    return start.isoformat(), now.isoformat(), reset.date().isoformat()


def _limit() -> int:
    raw = os.environ.get("ELEVENLABS_MONTHLY_LIMIT", "").strip()
    try:
        return int(raw) if raw else DEFAULT_MONTHLY_LIMIT
    except ValueError:
        return DEFAULT_MONTHLY_LIMIT


async def get_tts_dashboard(repo, api_key: str | None) -> dict:
    start, end, reset_date = _month_bounds()
    limit = _limit()

    try:
        used = await repo.characters_since(start, end) if repo else 0
    except Exception:
        used = 0
    local = {"used": used, "limit": limit, "remaining": max(0, limit - used)}

    real = None
    try:
        sub = await get_subscription(api_key)
        if sub:
            rlimit = sub["limit"]
            rused = sub["used"]
            real = {"used": rused, "limit": rlimit, "remaining": max(0, rlimit - rused)}
    except Exception:
        real = None

    return {
        "local": local,
        "real": real,
        "source": "real" if real else "local",
        "reset_date": reset_date,
    }
