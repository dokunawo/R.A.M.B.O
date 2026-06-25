"""Tests for KeeperRepo confidence scoring (embeddings off → substring path)."""

import asyncio

import aiosqlite
import pytest

from keeper_repo import KeeperRepo


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def repo(tmp_path):
    r = KeeperRepo(db_path=tmp_path / "keeper.db")
    _run(r.init_db())
    return r


def test_write_defaults_to_verified(repo):
    _run(repo.write("dog_name", "Rex", tags="keeper"))
    row = _run(repo.read("dog_name"))
    assert row["confidence"] == "verified"


def test_write_hint(repo):
    _run(repo.write("fav_color", "blue", confidence="hint"))
    row = _run(repo.read("fav_color"))
    assert row["confidence"] == "hint"


def test_invalid_confidence_coerced_to_hint(repo):
    _run(repo.write("x", "y", confidence="bogus"))
    assert _run(repo.read("x"))["confidence"] == "hint"


def test_query_returns_confidence(repo):
    _run(repo.write("city", "Detroit"))
    hits = _run(repo.query("city"))
    assert hits and hits[0]["confidence"] == "verified"


def test_confirm_returns_confidence(repo):
    _run(repo.write("a", "1"))
    info = _run(repo.confirm())
    assert info["recent"][0]["confidence"] == "verified"


def test_legacy_rows_migrated_to_verified(tmp_path):
    # Simulate a pre-confidence DB: create the old schema by hand, insert a row,
    # then open via KeeperRepo and confirm the migration backfilled 'verified'.
    db_path = tmp_path / "legacy.db"

    async def seed():
        async with aiosqlite.connect(db_path) as db:
            await db.executescript(
                "CREATE TABLE memories ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " key TEXT NOT NULL UNIQUE, value TEXT NOT NULL DEFAULT '',"
                " tags TEXT NOT NULL DEFAULT '',"
                " created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
            )
            await db.execute(
                "INSERT INTO memories (key, value, created_at, updated_at) "
                "VALUES ('old', 'fact', '2020', '2020')"
            )
            await db.commit()

    _run(seed())
    r = KeeperRepo(db_path=db_path)
    _run(r.init_db())
    assert _run(r.read("old"))["confidence"] == "verified"
