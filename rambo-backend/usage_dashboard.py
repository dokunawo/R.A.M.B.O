from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from pricing import MODEL_PRICING, _resolve_model

_cache: dict | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 60.0


async def get_dashboard(repo) -> dict:
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    utc_now = datetime.now(timezone.utc)
    month_start = utc_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_start = utc_now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = utc_now.isoformat()

    prev_month_end = (utc_now.replace(day=1) - timedelta(seconds=1)).isoformat()
    prev_month_start = (utc_now.replace(day=1) - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    mtd = await repo.usage_since(month_start, end)
    today = await repo.usage_since(today_start, end)
    prev = await repo.usage_since(prev_month_start, prev_month_end)

    cache_savings = _compute_cache_savings(
        mtd["total_cache_read"],
        mtd.get("by_model", []),
    )

    prev_cost = prev["total_cost"]
    mtd_cost = mtd["total_cost"]
    if prev_cost > 0:
        mom_delta = ((mtd_cost - prev_cost) / prev_cost) * 100
    else:
        mom_delta = 0.0

    payload = {
        "month_to_date": {
            "cost_usd": mtd_cost,
            "input_tokens": mtd["total_input"],
            "output_tokens": mtd["total_output"],
            "cache_write_tokens": mtd["total_cache_write"],
            "cache_read_tokens": mtd["total_cache_read"],
            "call_count": mtd["call_count"],
        },
        "today": {
            "cost_usd": today["total_cost"],
            "call_count": today["call_count"],
        },
        "by_model": mtd.get("by_model", []),
        "by_day": mtd.get("by_day", []),
        "cache_savings_usd": cache_savings,
        "mom_delta_pct": round(mom_delta, 1),
        "prev_month_cost_usd": prev_cost,
    }

    _cache = payload
    _cache_ts = now
    return payload


def _compute_cache_savings(cache_read_tokens: int, by_model: list[dict]) -> float:
    if cache_read_tokens == 0:
        return 0.0
    avg_input_rate = 0.0
    avg_cache_read_rate = 0.0
    if by_model:
        model_name = by_model[0].get("model", "")
        rates = _resolve_model(model_name)
        if rates:
            avg_input_rate = rates["input"]
            avg_cache_read_rate = rates["cache_read"]
    if avg_input_rate == 0:
        return 0.0
    full_price = cache_read_tokens * avg_input_rate / 1_000_000
    actual_price = cache_read_tokens * avg_cache_read_rate / 1_000_000
    return full_price - actual_price


def clear_cache():
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0
