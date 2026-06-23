"""Central prompt-cache configuration.

One source of truth for the `cache_control` marker used across every cached
call site (personality, sub-agent loop, router, research, conversation
history). Lets us tune the cache TTL in one place.

Why this exists: the default ephemeral cache lives ~5 minutes. R.A.M.B.O's
traffic is sparse (background sweeps, occasional operator turns), so a cache
WRITE often expires before the next call can READ it — you pay the 1.25x write
premium repeatedly and never collect the 10x read discount. The extended
1-hour TTL keeps the prefix warm across those gaps.

Tunable via the RAMBO_CACHE_TTL env var: "1h" (default) or "5m".
"""

from __future__ import annotations

import os

# Beta header required by the Anthropic API to honor the 1-hour TTL.
EXTENDED_TTL_BETA = "extended-cache-ttl-2025-04-11"

_VALID = {"5m", "1h"}


def cache_ttl() -> str:
    ttl = os.environ.get("RAMBO_CACHE_TTL", "1h").strip().lower()
    return ttl if ttl in _VALID else "1h"


def cache_control() -> dict:
    """The cache_control block to attach to a cached content block.

    For the 5-minute default we omit `ttl` entirely (keeps the marker minimal
    and avoids requiring the beta header). For 1h we set the explicit ttl."""
    ttl = cache_ttl()
    if ttl == "5m":
        return {"type": "ephemeral"}
    return {"type": "ephemeral", "ttl": ttl}


def uses_extended_ttl() -> bool:
    return cache_ttl() == "1h"


def beta_headers() -> dict:
    """default_headers for the Anthropic client when extended TTL is active."""
    return {"anthropic-beta": EXTENDED_TTL_BETA} if uses_extended_ttl() else {}
