"""Tests for KeeperRepo hybrid recall (embeddings off → keyword+recency+confidence).

VOYAGE is assumed unavailable in CI, so embed_one returns None and recall exercises
the BM25 + recency + confidence blend.
"""

import asyncio

import pytest

from keeper_repo import KeeperRepo, _bm25_scores, _recency_score, _tokenize
from datetime import datetime, timezone, timedelta


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def repo(tmp_path):
    r = KeeperRepo(db_path=tmp_path / "keeper.db")
    _run(r.init_db())
    return r


def test_tokenize_drops_stopwords_and_stems():
    assert _tokenize("What are my dogs") == ["dog"]


def test_bm25_ranks_keyword_match_first():
    rows = [
        {"key": "car", "value": "a red Toyota", "tags": ""},
        {"key": "dog", "value": "the dog is named Rex", "tags": ""},
    ]
    scores = _bm25_scores(_tokenize("what is my dog named"), rows)
    assert scores[1] > scores[0]


def test_recency_decays():
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    fresh = _recency_score(now.isoformat(), now)
    old = _recency_score((now - timedelta(days=60)).isoformat(), now)
    assert fresh > old
    assert 0.0 <= old < fresh <= 1.0


def test_recall_finds_keyword_hit(repo):
    _run(repo.write("dog_name", "Rex"))
    _run(repo.write("car_make", "Toyota"))
    hits = _run(repo.recall("what is my dog called", limit=5))
    assert hits
    assert hits[0]["key"] == "dog_name"


def test_recall_excludes_unrelated(repo):
    _run(repo.write("dog_name", "Rex"))
    _run(repo.write("car_make", "Toyota"))
    hits = _run(repo.recall("dog", limit=5))
    keys = {h["key"] for h in hits}
    assert "dog_name" in keys
    assert "car_make" not in keys  # no lexical/semantic signal → excluded


def test_recall_empty_store(repo):
    assert _run(repo.recall("anything")) == []


def test_recall_confidence_breaks_ties(repo):
    # Two equally-matching memories written close together; verified should edge
    # out the hint via the confidence term.
    _run(repo.write("fact_a", "alpha signal", confidence="hint"))
    _run(repo.write("fact_b", "alpha signal", confidence="verified"))
    hits = _run(repo.recall("alpha signal", limit=2))
    assert hits[0]["confidence"] == "verified"
