import pytest
import pytest_asyncio
import aiosqlite
from datetime import date
from todos_repo import TodosRepo, next_due


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "test_todos.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_exists(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='todos'")
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = TodosRepo(db_path=tmp_path / "t.db")
    await r.init_db()
    await r.init_db()
    row = await r.add("smoke test")
    assert row["id"] == 1


@pytest.mark.asyncio
async def test_add_defaults(repo):
    row = await repo.add("call the vet")
    assert row["text"] == "call the vet"
    assert row["priority"] == "normal"
    assert row["status"] == "open"
    assert row["due_date"] is None
    assert row["recurrence"] is None
    assert row["source"] == "voice"
    assert row["id"] == 1


@pytest.mark.asyncio
async def test_add_recurring_without_due_defaults_due_to_today(repo):
    row = await repo.add("water plants", recurrence="daily")
    assert row["due_date"] == date.today().isoformat()


@pytest.mark.asyncio
async def test_list_open_orders_by_priority_then_due_then_created(repo):
    await repo.add("low prio", priority="low")
    await repo.add("high prio no due", priority="high")
    await repo.add("high prio due later", priority="high", due="2026-08-01")
    await repo.add("high prio due sooner", priority="high", due="2026-07-01")
    rows = await repo.list_open()
    texts = [r["text"] for r in rows]
    assert texts == [
        "high prio due sooner", "high prio due later", "high prio no due", "low prio",
    ]


@pytest.mark.asyncio
async def test_list_open_excludes_done(repo):
    row = await repo.add("finish this")
    await repo.complete(row["id"])
    assert await repo.list_open() == []


@pytest.mark.asyncio
async def test_get_returns_none_for_missing(repo):
    assert await repo.get(999) is None


@pytest.mark.asyncio
async def test_complete_marks_done_and_stamps_completed_at(repo):
    row = await repo.add("one-off task")
    done = await repo.complete(row["id"])
    assert done["status"] == "done"
    assert done["completed_at"] is not None
    assert await repo.get(row["id"]) == done


@pytest.mark.asyncio
async def test_complete_missing_returns_none(repo):
    assert await repo.complete(999) is None


@pytest.mark.asyncio
async def test_complete_recurring_inserts_next_occurrence(repo):
    row = await repo.add("daily standup", recurrence="daily", due="2026-07-01")
    await repo.complete(row["id"])
    open_rows = await repo.list_open()
    assert len(open_rows) == 1
    assert open_rows[0]["text"] == "daily standup"
    assert open_rows[0]["due_date"] == "2026-07-02"
    assert open_rows[0]["recurrence"] == "daily"


@pytest.mark.asyncio
async def test_complete_recurring_weekly_named_day(repo):
    # 2026-07-01 is a Wednesday; weekly:friday should roll to 2026-07-03
    row = await repo.add("team sync", recurrence="weekly:friday", due="2026-07-01")
    await repo.complete(row["id"])
    open_rows = await repo.list_open()
    assert len(open_rows) == 1
    assert open_rows[0]["due_date"] == "2026-07-03"
    assert open_rows[0]["recurrence"] == "weekly:friday"


@pytest.mark.asyncio
async def test_complete_recurring_monthly(repo):
    row = await repo.add("pay rent", recurrence="monthly", due="2026-01-31")
    await repo.complete(row["id"])
    open_rows = await repo.list_open()
    assert len(open_rows) == 1
    assert open_rows[0]["due_date"] == "2026-02-28"  # clamped, 2026 not a leap year
    assert open_rows[0]["recurrence"] == "monthly"


@pytest.mark.asyncio
async def test_delete_removes_task(repo):
    row = await repo.add("to be deleted")
    assert await repo.delete(row["id"]) is True
    assert await repo.get(row["id"]) is None


@pytest.mark.asyncio
async def test_delete_missing_returns_false(repo):
    assert await repo.delete(999) is False


@pytest.mark.asyncio
async def test_due_on_or_before(repo):
    await repo.add("future", due="2026-08-01")
    await repo.add("today", due="2026-07-01")
    await repo.add("overdue", due="2026-06-01")
    await repo.add("no due date")
    rows = await repo.due_on_or_before("2026-07-01")
    texts = {r["text"] for r in rows}
    assert texts == {"today", "overdue"}


# ── next_due (pure, no DB) ──────────────────────────────────────────
def test_next_due_daily():
    assert next_due("2026-07-01", "daily") == "2026-07-02"


def test_next_due_weekdays_skips_weekend():
    # 2026-07-03 is a Friday
    assert next_due("2026-07-03", "weekdays") == "2026-07-06"  # Monday


def test_next_due_weekly_specific_day():
    # 2026-07-01 is a Wednesday; next Friday is 2026-07-03
    assert next_due("2026-07-01", "weekly:friday") == "2026-07-03"


def test_next_due_monthly_clamps_short_month():
    # Jan 31 -> Feb has only 28 days in 2026 (not a leap year)
    assert next_due("2026-01-31", "monthly") == "2026-02-28"


def test_next_due_monthly_normal():
    assert next_due("2026-06-15", "monthly") == "2026-07-15"
