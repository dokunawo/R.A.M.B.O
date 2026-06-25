"""Embedding-based roster pre-filter for the SmartRouter.

The roster (core modes + skills + Factory-spawned agents) grows unbounded as the
Factory spawns specialists. Shipping the whole list to the router every turn
wastes input tokens and dilutes routing accuracy. This index embeds each roster
line once (cached by content hash) and, given a goal, returns only the top-K most
semantically relevant lines plus the structural escape hatches.

Resilience: if embeddings are unavailable (no VOYAGE_API_KEY, API failure), every
method degrades to returning the full roster unchanged — identical to pre-embedding
behavior.
"""

from __future__ import annotations

import logging
import os
import re

import embeddings

logger = logging.getLogger(__name__)

# Structural targets that must never be filtered out — they are the router's
# escape hatches (answer-in-conversation / full pipeline).
_ALWAYS_KEEP = {"converse", "orchestrate"}

_TARGET_RE = re.compile(r"^-\s*(\S+)\s")


def _default_topk() -> int:
    raw = os.environ.get("RAMBO_ROUTE_TOPK", "6").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def _target_of(line: str) -> str:
    m = _TARGET_RE.match(line)
    return m.group(1) if m else ""


class RosterIndex:
    """Caches roster-line embeddings and ranks them against a goal."""

    def __init__(self):
        # description-text → embedding vector. Keyed by the full line so a changed
        # description (new content) misses the cache and is re-embedded.
        self._cache: dict[str, list[float]] = {}

    async def _ensure_embedded(self, lines: list[str]) -> None:
        missing = [ln for ln in lines if ln not in self._cache]
        if not missing:
            return
        vectors = await embeddings.embed(missing, input_type="document")
        if vectors is None:
            return
        for ln, vec in zip(missing, vectors):
            self._cache[ln] = vec

    async def shortlist(
        self,
        goal: str,
        roster_lines: list[str],
        top_k: int | None = None,
    ) -> list[str]:
        """Return the top-K relevant roster lines (+ always-keep), preserving the
        original order. Falls back to the full roster when embeddings are off."""
        if not embeddings.is_available() or len(roster_lines) <= (top_k or _default_topk()):
            return roster_lines

        await self._ensure_embedded(roster_lines)
        goal_vec = await embeddings.embed_one(goal, input_type="query")
        if goal_vec is None:
            return roster_lines

        k = top_k or _default_topk()
        scored: list[tuple[float, str]] = []
        for ln in roster_lines:
            vec = self._cache.get(ln)
            if vec is None:
                # Couldn't embed this line — keep it rather than risk dropping a
                # valid target.
                scored.append((float("inf"), ln))
                continue
            scored.append((embeddings.cosine(goal_vec, vec), ln))

        ranked = sorted(scored, key=lambda s: s[0], reverse=True)
        keep: set[str] = {ln for _score, ln in ranked[:k]}
        # Always retain the structural escape hatches.
        keep.update(ln for ln in roster_lines if _target_of(ln) in _ALWAYS_KEEP)

        shortlisted = [ln for ln in roster_lines if ln in keep]
        logger.debug(
            "Roster shortlisted %d → %d lines for goal=%r",
            len(roster_lines), len(shortlisted), goal[:60],
        )
        return shortlisted
