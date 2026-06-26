"""Finnhub finance data — live quotes + symbol resolution.

Returns None whenever it can't produce a structured answer (no key, no resolvable
symbol, API error) so the caller can fall back to the web-search backend. Gated
on FINNHUB_API_KEY.
"""
from __future__ import annotations

import os
import re

try:
    import httpx
except ImportError:
    httpx = None

_BASE = "https://finnhub.io/api/v1"
# Common phrasing words to strip when resolving a company name → symbol.
_STOP = re.compile(
    r"\b(how'?s|how is|what'?s|whats|the|stock|stocks|price|share|shares|doing|"
    r"today|quote|for|of|on|is|market|trading|at|right now|now)\b", re.IGNORECASE)


def _key() -> str:
    return os.environ.get("FINNHUB_API_KEY", "")


def is_configured() -> bool:
    return bool(_key())


def _extract_ticker(query: str) -> str | None:
    """A standalone 1-5 uppercase token is almost certainly a ticker (NVDA, AAPL)."""
    for tok in re.findall(r"\b[A-Z]{1,5}\b", query):
        if tok not in ("A", "I", "S&P", "USA"):
            return tok
    return None


async def _search_symbol(client, query: str, key: str) -> str | None:
    cleaned = _STOP.sub(" ", query)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    try:
        r = await client.get(f"{_BASE}/search", params={"q": cleaned, "token": key})
        results = r.json().get("result", [])
    except Exception:
        return None
    # Prefer a plain US common-stock symbol (no dots/exchange suffixes).
    for item in results:
        sym = item.get("symbol", "")
        if sym and "." not in sym and item.get("type", "Common Stock") == "Common Stock":
            return sym
    return results[0].get("symbol") if results else None


async def finance_lookup(query: str) -> str | None:
    if httpx is None:
        return None
    key = _key()
    if not key:
        return None
    symbol = _extract_ticker(query)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if not symbol:
                symbol = await _search_symbol(client, query, key)
            if not symbol:
                return None  # e.g. market-wide question → let caller web-search it
            q = (await client.get(f"{_BASE}/quote",
                                  params={"symbol": symbol, "token": key})).json()
    except Exception:
        return None

    price = q.get("c")
    if not price:  # 0 or None → no data for this symbol
        return None
    change, pct = q.get("d"), q.get("dp")
    arrow = "▲" if (change or 0) >= 0 else "▼"
    sign = "+" if (change or 0) >= 0 else ""
    parts = [f"{symbol}: ${price:,.2f} {arrow} {sign}{change:,.2f} ({sign}{pct:.2f}%) today"]
    if q.get("h") and q.get("l"):
        parts.append(f"  range ${q['l']:,.2f}–${q['h']:,.2f}, prev close ${q.get('pc', 0):,.2f}")
    return "\n".join(parts)
