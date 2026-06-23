from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from usage_repo import UsageRepo

logger = logging.getLogger(__name__)

_repo: UsageRepo | None = None


def set_usage_repo(repo: UsageRepo) -> None:
    global _repo
    _repo = repo


async def record_usage(model: str, usage, source: str = "conversation") -> None:
    """Best-effort recording. Never raises into the conversation path."""
    try:
        if _repo is None:
            return

        from pricing import compute_cost

        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        cost = compute_cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        )

        await _repo.record(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
            cost_usd=cost,
            source=source,
        )
    except Exception:
        logger.exception("Failed to record usage — swallowed")
