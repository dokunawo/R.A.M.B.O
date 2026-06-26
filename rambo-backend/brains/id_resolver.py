"""
R.A.M.B.O. MLB Betting Agent — ID Resolver Brain (Step 4)
brains/id_resolver.py

The ONLY place cross-feed player IDs get reconciled. Given a player from an
outside source (DraftKings Pick6, a sportsbook, Baseball Reference...), it links
that source's id to the canonical MLBAM id in `players` via `player_aliases`.

Hard rule: it never links silently on a weak match. Anything below the
auto-link threshold is quarantined in `player_review` for your sign-off.

Match tiers (highest confidence first):
  1. Already aliased        -> source_player_id seen before, return existing link.
  2. Direct id hint         -> source carries an MLBAM id -> link at 1.0.
  3. Exact name + team       -> normalized name match AND team match -> auto-link.
  4. Strong fuzzy + team     -> score >= auto_threshold AND team match -> auto-link.
  5. Strong fuzzy, no team   -> score >= auto_threshold, team unknown -> review.
  6. Weak / no match         -> review with best candidate + score (nullable).

Dependency: rapidfuzz  (pip install rapidfuzz)
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz, process

# Suffixes and punctuation stripped during name normalization.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation/suffixes, handle 'Last, First',
    collapse whitespace. 'Acuña Jr., Ronald' -> 'ronald acuna'."""
    if not name:
        return ""
    # "Last, First" -> "First Last"
    if "," in name:
        last, _, first = name.partition(",")
        name = f"{first.strip()} {last.strip()}"
    # Strip accents
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.lower()
    name = _PUNCT_RE.sub(" ", name)
    tokens = [t for t in _WS_RE.sub(" ", name).strip().split(" ") if t and t not in _SUFFIXES]
    return " ".join(tokens)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ResolveResult:
    source: str
    source_player_id: str
    status: str                     # 'linked' | 'review'
    mlb_id: Optional[int] = None    # set when linked
    confidence: float = 0.0
    candidate_mlb_id: Optional[int] = None   # best guess when status='review'
    candidate_score: Optional[float] = None


class IdResolver:
    def __init__(
        self,
        conn: sqlite3.Connection,
        auto_threshold: float = 92.0,
        review_threshold: float = 80.0,
    ) -> None:
        self.conn = conn
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold
        self._index: list[tuple[int, str, Optional[int]]] = []  # (mlb_id, norm_name, team_id)
        self._norm_to_mlb: dict[str, list[tuple[int, Optional[int]]]] = {}
        self._load_player_index()

    def _load_player_index(self) -> None:
        """Cache canonical players in memory for fast matching."""
        rows = self.conn.execute(
            "SELECT mlb_id, full_name, current_team_id FROM players"
        ).fetchall()
        self._index = [(r[0], normalize_name(r[1]), r[2]) for r in rows]
        self._norm_to_mlb.clear()
        for mlb_id, norm, team in self._index:
            self._norm_to_mlb.setdefault(norm, []).append((mlb_id, team))

    # -- public API ----------------------------------------------------------

    def resolve(
        self,
        source: str,
        source_player_id: str,
        source_name: str,
        source_team_id: Optional[int] = None,
        mlb_id_hint: Optional[int] = None,
        raw_ingest_id: Optional[int] = None,
    ) -> ResolveResult:
        # Tier 1: already aliased
        existing = self.conn.execute(
            "SELECT mlb_id FROM player_aliases WHERE source=? AND source_player_id=?",
            (source, source_player_id),
        ).fetchone()
        if existing:
            return ResolveResult(source, source_player_id, "linked",
                                 mlb_id=existing[0], confidence=1.0)

        # Tier 2: direct MLBAM id hint
        if mlb_id_hint is not None and self._player_exists(mlb_id_hint):
            self._link(source, source_player_id, mlb_id_hint, source_name, 1.0)
            return ResolveResult(source, source_player_id, "linked",
                                 mlb_id=mlb_id_hint, confidence=1.0)

        norm = normalize_name(source_name)

        # Tier 3: exact normalized name
        exact = self._norm_to_mlb.get(norm, [])
        if len(exact) == 1:
            mlb_id, team = exact[0]
            if source_team_id is None or team is None or team == source_team_id:
                self._link(source, source_player_id, mlb_id, source_name, 0.99)
                return ResolveResult(source, source_player_id, "linked",
                                     mlb_id=mlb_id, confidence=0.99)
        elif len(exact) > 1 and source_team_id is not None:
            # Ambiguous name (e.g. two players named the same) — break tie on team.
            for mlb_id, team in exact:
                if team == source_team_id:
                    self._link(source, source_player_id, mlb_id, source_name, 0.97)
                    return ResolveResult(source, source_player_id, "linked",
                                         mlb_id=mlb_id, confidence=0.97)

        # Tier 4/5: fuzzy
        cand_mlb, score = self._best_candidate(norm, source_team_id)
        if cand_mlb is not None and score >= self.auto_threshold:
            team = self._team_of(cand_mlb)
            if source_team_id is not None and team == source_team_id:
                self._link(source, source_player_id, cand_mlb, source_name, score / 100.0)
                return ResolveResult(source, source_player_id, "linked",
                                     mlb_id=cand_mlb, confidence=score / 100.0)
            # Strong name but team unconfirmed -> human eyes.
            self._queue_review(source, source_player_id, source_name,
                               cand_mlb, score, raw_ingest_id)
            return ResolveResult(source, source_player_id, "review",
                                 candidate_mlb_id=cand_mlb, candidate_score=score)

        # Tier 6: weak / no match -> review (candidate only if above review floor)
        keep_cand = cand_mlb if (score and score >= self.review_threshold) else None
        keep_score = score if keep_cand is not None else None
        self._queue_review(source, source_player_id, source_name,
                           keep_cand, keep_score, raw_ingest_id)
        return ResolveResult(source, source_player_id, "review",
                             candidate_mlb_id=keep_cand, candidate_score=keep_score)

    def run_unresolved_props(self) -> dict[str, int]:
        """Batch pass: resolve every prop_lines row still missing an mlb_id.
        Updates prop_lines.mlb_id in place when a link is found."""
        rows = self.conn.execute(
            """SELECT DISTINCT book, player_name_raw, game_pk
               FROM prop_lines WHERE mlb_id IS NULL AND player_name_raw IS NOT NULL"""
        ).fetchall()
        linked = review = 0
        for book, name_raw, game_pk in rows:
            team = self._team_for_game_side(game_pk)  # may be None
            res = self.resolve(book, name_raw, name_raw, source_team_id=team)
            if res.status == "linked":
                self.conn.execute(
                    "UPDATE prop_lines SET mlb_id=? WHERE book=? AND player_name_raw=? AND mlb_id IS NULL",
                    (res.mlb_id, book, name_raw),
                )
                linked += 1
            else:
                review += 1
        self.conn.commit()
        return {"linked": linked, "review": review}

    # -- internals -----------------------------------------------------------

    def _best_candidate(self, norm: str, team_id: Optional[int]):
        if not norm or not self._index:
            return None, 0.0
        # Prefer same-team candidates when team is known; fall back to all.
        pool = [(m, n) for (m, n, t) in self._index if team_id is None or t == team_id]
        if not pool:
            pool = [(m, n) for (m, n, _) in self._index]
        choices = {m: n for m, n in pool}
        match = process.extractOne(norm, choices, scorer=fuzz.WRatio)
        if match is None:
            return None, 0.0
        _matched_name, score, mlb_id = match
        return mlb_id, float(score)

    def _link(self, source, source_player_id, mlb_id, source_name, confidence):
        self.conn.execute(
            """INSERT INTO player_aliases
                 (mlb_id, source, source_player_id, source_name, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(source, source_player_id) DO UPDATE SET
                 mlb_id=excluded.mlb_id, confidence=excluded.confidence""",
            (mlb_id, source, source_player_id, source_name, confidence, _now()),
        )
        self.conn.commit()

    def _queue_review(self, source, source_player_id, source_name,
                      candidate_mlb_id, candidate_score, raw_ingest_id):
        self.conn.execute(
            """INSERT INTO player_review
                 (source, source_player_id, source_name, candidate_mlb_id,
                  candidate_score, raw_ingest_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
               ON CONFLICT(source, source_player_id) DO UPDATE SET
                 candidate_mlb_id=excluded.candidate_mlb_id,
                 candidate_score=excluded.candidate_score""",
            (source, source_player_id, source_name, candidate_mlb_id,
             candidate_score, raw_ingest_id, _now()),
        )
        self.conn.commit()

    def _player_exists(self, mlb_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM players WHERE mlb_id=?", (mlb_id,)
        ).fetchone() is not None

    def _team_of(self, mlb_id: int) -> Optional[int]:
        row = self.conn.execute(
            "SELECT current_team_id FROM players WHERE mlb_id=?", (mlb_id,)
        ).fetchone()
        return row[0] if row else None

    def _team_for_game_side(self, game_pk: Optional[int]) -> Optional[int]:
        # Props rarely tell you which side a player is on; without a roster join
        # we can't infer team safely, so return None and let name carry it.
        return None
