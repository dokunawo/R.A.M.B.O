import pytest
import pytest_asyncio
import todos_skill
from todos_repo import TodosRepo
from chief_of_staff import chief_of_staff_skill

_DOC = """---
type: north-star
target: "$10K/mo"
product: Ops
last_reviewed: 2026-06-01
review_cadence_days: 90
filter: [sales, margin]
---

## Objective
Grow revenue.

## Operating Rules
- Say no to low-margin work.
"""


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "cos_todos.db")
    await r.init_db()
    todos_skill.set_repo(r)
    yield r
    todos_skill.set_repo(None)


@pytest.mark.asyncio
async def test_brief_includes_open_tasks_section(tmp_path, repo, monkeypatch):
    doc = tmp_path / "north-star.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setattr("chief_of_staff.NORTH_STAR_PATHS", [doc])
    await repo.add("call the vet", priority="high")
    out = await chief_of_staff_skill("daily brief", {})
    assert "OPEN TASKS" in out
    assert "call the vet" in out


@pytest.mark.asyncio
async def test_brief_omits_section_when_no_open_tasks(tmp_path, repo, monkeypatch):
    doc = tmp_path / "north-star.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setattr("chief_of_staff.NORTH_STAR_PATHS", [doc])
    out = await chief_of_staff_skill("daily brief", {})
    assert "OPEN TASKS" not in out


@pytest.mark.asyncio
async def test_brief_survives_repo_unconfigured(tmp_path, monkeypatch):
    todos_skill.set_repo(None)
    doc = tmp_path / "north-star.md"
    doc.write_text(_DOC, encoding="utf-8")
    monkeypatch.setattr("chief_of_staff.NORTH_STAR_PATHS", [doc])
    out = await chief_of_staff_skill("daily brief", {})
    assert "OPEN TASKS" not in out
    assert "Daily Revenue Brief" in out
