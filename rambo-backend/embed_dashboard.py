"""Build the Voyage embedding credit payload for the EMBED HUD.

Voyage gives every account a large free-token allotment (200M) plus any prepaid
balance. Voyage exposes no balance API, so this tracker is computed locally from
usage.db (rows where model LIKE 'voyage%'), mirroring the local path of the TTS
dashboard. Never raises into the request path.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import embeddings
from pricing import _resolve_model

DEFAULT_FREE_TOKENS = 200_000_000  # 200M free per account
DEFAULT_CREDIT_USD = 20.0


def _free_tokens() -> int:
    raw = os.environ.get("VOYAGE_FREE_TOKENS", "").strip()
    try:
        return int(raw) if raw else DEFAULT_FREE_TOKENS
    except ValueError:
        return DEFAULT_FREE_TOKENS


def _credit_usd() -> float:
    raw = os.environ.get("VOYAGE_CREDIT_USD", "").strip()
    try:
        return float(raw) if raw else DEFAULT_CREDIT_USD
    except ValueError:
        return DEFAULT_CREDIT_USD


def _overage_rate() -> float:
    """$/token charged once the free allotment is exhausted, for the active model."""
    rates = _resolve_model(embeddings.embed_model())
    return (rates["input"] / 1_000_000) if rates else 0.0


def _month_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


async def get_embed_dashboard(repo) -> dict:
    free_limit = _free_tokens()
    credit = _credit_usd()

    try:
        all_time = await repo.voyage_totals() if repo else {"tokens": 0, "calls": 0}
        mtd = await repo.voyage_totals(_month_start()) if repo else {"tokens": 0, "calls": 0, "cost": 0.0}
    except Exception:
        all_time = {"tokens": 0, "calls": 0}
        mtd = {"tokens": 0, "calls": 0, "cost": 0.0}

    used = int(all_time.get("tokens", 0) or 0)
    free_remaining = max(0, free_limit - used)

    # Paid balance is only touched after the free allotment is gone.
    overage_tokens = max(0, used - free_limit)
    spent_usd = overage_tokens * _overage_rate()
    balance_remaining = max(0.0, credit - spent_usd)

    return {
        # token block mirrors the VOICE HUD shape (used/limit/remaining).
        "tokens": {"used": used, "limit": free_limit, "remaining": free_remaining},
        "credit": {
            "balance_usd": round(credit, 2),
            "spent_usd": round(spent_usd, 4),
            "remaining_usd": round(balance_remaining, 2),
        },
        "month_to_date": {
            "tokens": int(mtd.get("tokens", 0) or 0),
            "calls": int(mtd.get("calls", 0) or 0),
        },
        "model": embeddings.embed_model(),
        "active": embeddings.is_available(),
        "source": "local",
    }
