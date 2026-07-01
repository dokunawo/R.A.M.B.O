from skills import match_skill, SKILLS
from orchestrator.orchestrator import Orchestrator


def test_todos_registered_in_skills():
    assert any(s["name"] == "todos" for s in SKILLS)


def test_todos_matcher_routes_add_list_complete_delete():
    for g in ("add a task to call the vet", "what's on my list",
              "mark call the vet as done", "delete the old idea task"):
        s = match_skill(g)
        assert s is not None and s["name"] == "todos", g


def test_calendar_still_wins_its_own_phrasing():
    s = match_skill("what's on my calendar today")
    assert s is not None and s["name"] == "calendar"


def test_watchlist_still_owns_is_due_phrasing():
    # Documents the boundary from the plan: "is due"/"are due" phrasing is caught
    # by the orchestrator's watchlist fast-path BEFORE skill matching ever runs, so
    # it will never reach the todos skill regardless of how todos' matcher evolves.
    assert Orchestrator._WATCHLIST_RE.search("what tasks are due today")
