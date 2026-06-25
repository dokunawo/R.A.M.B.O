"""Voyage AI embedding client — the single place embeddings are produced.

Anthropic has no embeddings API; Voyage is its recommended partner. We use the
cheap, fast `voyage-4-lite` model over raw httpx (already a dependency) to keep
the stack slim — no torch/numpy.

NOTE: keep one model for Keeper's life. Stored memory vectors live in a single
model's space; switching models silently breaks recall until everything is
re-embedded. Routing embeddings are recomputed live, so they're unaffected.

Resilience mirrors the rest of R.A.M.B.O: if VOYAGE_API_KEY is missing or the
call fails, `embed()` returns None and callers fall back to their pre-embedding
behavior (full roster / substring query). Embeddings are an optimization, never
a hard dependency.
"""

from __future__ import annotations

import logging
import math
import os

import httpx

import usage_capture

logger = logging.getLogger(__name__)

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
DEFAULT_MODEL = "voyage-4-lite"


def embed_model() -> str:
    return os.environ.get("RAMBO_EMBED_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def is_available() -> bool:
    return bool(os.environ.get("VOYAGE_API_KEY", "").strip())


class _Usage:
    """Minimal shim so record_usage() can read token counts off Voyage's reply."""

    def __init__(self, total_tokens: int):
        # Voyage bills a single token count; book it as input tokens.
        self.input_tokens = total_tokens
        self.output_tokens = 0
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0


async def embed(texts: list[str], input_type: str = "document") -> list[list[float]] | None:
    """Embed a batch of texts. `input_type` is "document" or "query".

    Returns a list of vectors (one per input), or None to signal callers to fall
    back. Never raises into the calling path.
    """
    key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if not key or not texts:
        return None

    model = embed_model()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _VOYAGE_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={"input": texts, "model": model, "input_type": input_type},
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:
        logger.exception("Voyage embedding call failed — falling back")
        return None

    try:
        # Preserve request order via each item's index.
        items = sorted(payload["data"], key=lambda d: d.get("index", 0))
        vectors = [item["embedding"] for item in items]
    except Exception:
        logger.exception("Unexpected Voyage response shape — falling back")
        return None

    total_tokens = (payload.get("usage") or {}).get("total_tokens", 0) or 0
    if total_tokens:
        await usage_capture.record_usage(model, _Usage(total_tokens), source="embedding")

    return vectors


async def embed_one(text: str, input_type: str = "document") -> list[float] | None:
    """Convenience wrapper for a single text."""
    vectors = await embed([text], input_type=input_type)
    return vectors[0] if vectors else None


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors (pure Python)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
