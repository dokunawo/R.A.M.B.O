"""The Guardian Open Platform — general/world news headlines.

Returns None when it can't answer (no key, API error) so the caller can fall
back to the web-search backend. Gated on GUARDIAN_API_KEY (free key, regular
email — https://open-platform.theguardian.com/access/).
"""
from __future__ import annotations

import os
import re

try:
    import httpx
except ImportError:
    httpx = None

_BASE = "https://content.guardianapis.com/search"
# Strip request framing to leave the actual topic ("" → top headlines).
_STOP = re.compile(
    r"\b(news|headline|headlines|any|on|about|what'?s|whats|going on|with|the|"
    r"today|latest|current|events|happening|tell me|give me|show me)\b",
    re.IGNORECASE)


def _key() -> str:
    return os.environ.get("GUARDIAN_API_KEY", "")


def is_configured() -> bool:
    return bool(_key())


def _topic(query: str) -> str:
    cleaned = _STOP.sub(" ", query)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


async def news_lookup(query: str) -> str | None:
    if httpx is None:
        return None
    key = _key()
    if not key:
        return None
    params = {
        "api-key": key,
        "page-size": 5,
        "show-fields": "trailText",
    }
    topic = _topic(query)
    if topic:
        # Relevance-ranked but kept fresh: best matches from the last ~10 days.
        from datetime import date, timedelta
        # Phrase-match multi-word topics so "artificial intelligence" doesn't also
        # match "director of national intelligence". Guardian treats a quoted q as
        # an exact phrase.
        params["q"] = f'"{topic}"' if " " in topic else topic
        params["order-by"] = "relevance"
        params["from-date"] = (date.today() - timedelta(days=10)).isoformat()
    else:
        params["order-by"] = "newest"   # top stories → newest first
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = (await client.get(_BASE, params=params)).json()
        results = data.get("response", {}).get("results", [])
    except Exception:
        return None
    if not results:
        return None

    label = f'on "{topic}"' if topic else "top stories"
    lines = [f"News — {label} (The Guardian):"]
    for a in results:
        title = a.get("webTitle", "(untitled)")
        section = a.get("sectionName", "")
        trail = re.sub(r"<[^>]+>", "", (a.get("fields", {}) or {}).get("trailText", "")).strip()
        lines.append(f"  • {title}" + (f" [{section}]" if section else ""))
        if trail:
            lines.append(f"    {trail[:120]}")
    return "\n".join(lines)
