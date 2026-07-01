from datetime import date, datetime
from todos_skill import (
    detect_intent, extract_priority, extract_recurrence, extract_due,
    clean_task_text, extract_target_phrase, find_match,
)


# ── intent ──────────────────────────────────────────────────────────
def test_detect_intent_add():
    for g in ("add a task to call the vet", "new task: buy milk",
              "remind me to email Sarah", "i need to fix the sink",
              "put buy milk on my list", "put call mom on my to-do list"):
        assert detect_intent(g) == "add", g


def test_detect_intent_list():
    for g in ("what's on my list", "my tasks", "what do i need to do",
              "show me my to-do list"):
        assert detect_intent(g) == "list", g


def test_detect_intent_complete():
    for g in ("mark call the vet as done", "complete buy milk",
              "finished the sink", "check off call mom", "i did the laundry"):
        assert detect_intent(g) == "complete", g


def test_detect_intent_delete():
    for g in ("remove the call the vet task", "delete the buy milk task",
              "drop call mom from my list"):
        assert detect_intent(g) == "delete", g


def test_detect_intent_none_for_unrelated():
    assert detect_intent("what's the weather") is None
    assert detect_intent("what's on my calendar") is None


# ── priority ────────────────────────────────────────────────────────
def test_extract_priority_high():
    assert extract_priority("call the vet, urgent") == "high"
    assert extract_priority("important: renew passport") == "high"


def test_extract_priority_low():
    assert extract_priority("clean the garage whenever") == "low"


def test_extract_priority_default_normal():
    assert extract_priority("call the vet") == "normal"


# ── recurrence ──────────────────────────────────────────────────────
def test_extract_recurrence_daily():
    assert extract_recurrence("water the plants daily") == "daily"
    assert extract_recurrence("check email every day") == "daily"


def test_extract_recurrence_weekdays():
    assert extract_recurrence("stand-up every weekday") == "weekdays"


def test_extract_recurrence_weekly_named_day():
    assert extract_recurrence("trash out every monday") == "weekly:monday"


def test_extract_recurrence_bare_weekly_uses_now():
    now = date(2026, 7, 1)  # a Wednesday
    assert extract_recurrence("team sync weekly", now=now) == "weekly:wednesday"


def test_extract_recurrence_monthly():
    assert extract_recurrence("pay rent monthly") == "monthly"
    assert extract_recurrence("review budget every month") == "monthly"


def test_extract_recurrence_none():
    assert extract_recurrence("call the vet") is None


# ── due (wraps resolve_temporal) ──────────────────────────────────────
def test_extract_due_tomorrow():
    now = datetime(2026, 7, 1, 9, 0, 0)
    due, phrase = extract_due("call the vet tomorrow", now=now)
    assert due == "2026-07-02"
    assert phrase == "tomorrow"


def test_extract_due_none_when_no_date_phrase():
    due, phrase = extract_due("call the vet")
    assert due is None and phrase is None


# ── clean_task_text ─────────────────────────────────────────────────
def test_clean_task_text_strips_add_trigger_and_due_phrase():
    text = clean_task_text("add", "add a task to call the vet tomorrow",
                           due_phrase="tomorrow")
    assert text == "call the vet"


def test_clean_task_text_strips_put_on_my_list_wrapper():
    text = clean_task_text("add", "put buy milk on my to-do list")
    assert text == "buy milk"


def test_clean_task_text_strips_priority_phrase():
    text = clean_task_text("add", "call the vet, urgent", priority_phrase="urgent")
    assert text == "call the vet"


# ── extract_target_phrase ─────────────────────────────────────────────
def test_extract_target_phrase_mark_as_done_wrap():
    assert extract_target_phrase("complete", "mark call the vet as done") == "call the vet"


def test_extract_target_phrase_mark_done_no_as():
    assert extract_target_phrase("complete", "mark buy milk done") == "buy milk"


def test_extract_target_phrase_short_name_not_swallowed_by_trigger():
    # Regression case: a one-word task name ("call") must survive extraction even
    # though the word itself could also satisfy the trigger regex's wildcard.
    assert extract_target_phrase("complete", "mark call as done") == "call"


def test_extract_target_phrase_complete_prefix_forms():
    assert extract_target_phrase("complete", "complete buy milk") == "buy milk"
    assert extract_target_phrase("complete", "finished the sink") == "sink"
    assert extract_target_phrase("complete", "check off call mom") == "call mom"
    assert extract_target_phrase("complete", "i did the laundry") == "laundry"


def test_extract_target_phrase_delete_strips_task_suffix():
    assert extract_target_phrase("delete", "remove the call the vet task") == "call the vet"
    assert extract_target_phrase("delete", "delete the old idea task") == "old idea"


def test_extract_target_phrase_delete_strips_list_suffix():
    assert extract_target_phrase("delete", "drop call mom from my list") == "call mom"


# ── find_match ──────────────────────────────────────────────────────
def _tasks():
    return [
        {"id": 1, "text": "call the vet"},
        {"id": 2, "text": "buy milk"},
        {"id": 3, "text": "call mom about the trip"},
    ]


def test_find_match_single_substring_hit():
    match, candidates = find_match("vet", _tasks())
    assert match["id"] == 1 and candidates == []


def test_find_match_no_hit():
    match, candidates = find_match("clean the garage", _tasks())
    assert match is None and candidates == []


def test_find_match_ambiguous_multiple_substring_hits():
    match, candidates = find_match("call", _tasks())
    assert match is None
    assert {c["id"] for c in candidates} == {1, 3}


import pytest
import pytest_asyncio
import todos_skill
from todos_repo import TodosRepo


@pytest_asyncio.fixture
async def wired_repo(tmp_path):
    r = TodosRepo(db_path=tmp_path / "skill_todos.db")
    await r.init_db()
    todos_skill.set_repo(r)
    yield r
    todos_skill.set_repo(None)


@pytest.mark.asyncio
async def test_skill_add_reports_fields(wired_repo):
    out = await todos_skill.todos_skill(
        "add a task to call the vet tomorrow, urgent", {})
    assert "call the vet" in out.lower()
    assert "high" in out.lower() or "urgent" in out.lower()
    rows = await wired_repo.list_open()
    assert len(rows) == 1
    assert rows[0]["text"] == "call the vet"
    assert rows[0]["priority"] == "high"
    assert rows[0]["due_date"] is not None


@pytest.mark.asyncio
async def test_skill_list_empty(wired_repo):
    out = await todos_skill.todos_skill("what's on my list", {})
    assert "nothing" in out.lower()


@pytest.mark.asyncio
async def test_skill_list_shows_open_tasks(wired_repo):
    await wired_repo.add("call the vet")
    await wired_repo.add("buy milk")
    out = await todos_skill.todos_skill("what's on my list", {})
    assert "call the vet" in out.lower()
    assert "buy milk" in out.lower()


@pytest.mark.asyncio
async def test_skill_complete_single_match(wired_repo):
    await wired_repo.add("call the vet")
    out = await todos_skill.todos_skill("mark call the vet as done", {})
    assert "done" in out.lower() or "call the vet" in out.lower()
    assert await wired_repo.list_open() == []


@pytest.mark.asyncio
async def test_skill_complete_no_match(wired_repo):
    out = await todos_skill.todos_skill("mark clean the garage as done", {})
    assert "don't see" in out.lower() or "not" in out.lower()


@pytest.mark.asyncio
async def test_skill_complete_ambiguous_asks(wired_repo):
    await wired_repo.add("call the vet")
    await wired_repo.add("call mom about the trip")
    out = await todos_skill.todos_skill("mark call as done", {})
    assert "which" in out.lower()
    assert len(await wired_repo.list_open()) == 2  # nothing completed on ambiguity


@pytest.mark.asyncio
async def test_skill_delete_removes_task(wired_repo):
    await wired_repo.add("old idea")
    out = await todos_skill.todos_skill("delete the old idea task", {})
    assert "removed" in out.lower() or "old idea" in out.lower()
    assert await wired_repo.list_open() == []


@pytest.mark.asyncio
async def test_skill_no_repo_configured_is_graceful():
    todos_skill.set_repo(None)
    out = await todos_skill.todos_skill("what's on my list", {})
    assert isinstance(out, str) and out  # never raises, always says something
