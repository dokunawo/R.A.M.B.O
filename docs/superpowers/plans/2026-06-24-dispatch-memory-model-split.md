# Persistent Dispatch Memory + Fast/Deep Model Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable SQLite record of dispatched goals that feeds back into routing and voice, plus a fast model tier for the routing decision.

**Architecture:** A new async `aiosqlite` repo (`DispatchRepo`) mirrors the existing `UsageRepo`, is wired into `main.py` startup, and is called best-effort from `Orchestrator.handle()`. `model_config` gains a `fast_model()` tier used only by `SmartRouter`. Both features are additive and failure-isolated.

**Tech Stack:** Python, FastAPI, aiosqlite, anthropic, pytest + pytest-asyncio.

## Global Constraints

- DB files live in `rambo-backend/data/` (e.g. `data/dispatch.db`), created via `init_db()` with `parent.mkdir(parents=True, exist_ok=True)`.
- Timestamps are `datetime.now(timezone.utc).isoformat()` strings (match `usage_repo.py`).
- Deep model id (unchanged): `claude-sonnet-4-6` via `model_config.default_model()` / env `RAMBO_MODEL`.
- Fast model id (new): `claude-haiku-4-5` via `model_config.fast_model()` / env `RAMBO_FAST_MODEL`.
- All registry calls from the orchestrator are best-effort: wrapped so a failure never breaks the conversation turn; a `None` repo means no-op.
- Tests use `pytest`, `pytest_asyncio`, `@pytest.mark.asyncio`, and the `tmp_path` fixture with a `db_path=` constructor argument (match `tests/test_usage_repo.py`).
- All work happens on branch `feature/dispatch-memory-model-split`. Run commands from `rambo-backend/`.

---

### Task 1: Fast model tier in `model_config`

**Files:**
- Modify: `rambo-backend/model_config.py`
- Test: `rambo-backend/tests/test_model_config.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `model_config.fast_model() -> str` (env `RAMBO_FAST_MODEL`, default `claude-haiku-4-5`); existing `default_model()` unchanged.

- [ ] **Step 1: Write the failing tests**

Create `rambo-backend/tests/test_model_config.py`:

```python
import importlib
import model_config


def test_fast_model_default(monkeypatch):
    monkeypatch.delenv("RAMBO_FAST_MODEL", raising=False)
    importlib.reload(model_config)
    assert model_config.fast_model() == "claude-haiku-4-5"


def test_fast_model_env_override(monkeypatch):
    monkeypatch.setenv("RAMBO_FAST_MODEL", "claude-haiku-x")
    assert model_config.fast_model() == "claude-haiku-x"


def test_fast_model_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv("RAMBO_FAST_MODEL", "   ")
    assert model_config.fast_model() == "claude-haiku-4-5"


def test_default_model_unchanged(monkeypatch):
    monkeypatch.delenv("RAMBO_MODEL", raising=False)
    assert model_config.default_model() == "claude-sonnet-4-6"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && python -m pytest tests/test_model_config.py -v`
Expected: FAIL with `AttributeError: module 'model_config' has no attribute 'fast_model'`

- [ ] **Step 3: Add the fast tier**

In `rambo-backend/model_config.py`, after the `DEFAULT_MODEL` line add `FAST_MODEL` and after `default_model()` add `fast_model()`:

```python
DEFAULT_MODEL = "claude-sonnet-4-6"
FAST_MODEL = "claude-haiku-4-5"


def default_model() -> str:
    return os.environ.get("RAMBO_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def fast_model() -> str:
    return os.environ.get("RAMBO_FAST_MODEL", FAST_MODEL).strip() or FAST_MODEL
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && python -m pytest tests/test_model_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/model_config.py rambo-backend/tests/test_model_config.py
git commit -m "feat: add fast_model tier to model_config"
```

---

### Task 2: Route on the fast model

**Files:**
- Modify: `rambo-backend/orchestrator/orchestrator.py:72`
- Test: `rambo-backend/tests/test_router_model.py` (create)

**Interfaces:**
- Consumes: `model_config.fast_model()` (Task 1); `SmartRouter(llm_client, model=...)` (existing, `orchestrator/routing.py:110`).
- Produces: nothing new; `SmartRouter` instance now carries the fast model id on `_model`.

- [ ] **Step 1: Write the failing test**

Create `rambo-backend/tests/test_router_model.py`:

```python
import model_config
from orchestrator.routing import SmartRouter


def test_router_uses_fast_model_when_passed():
    router = SmartRouter(llm_client=None, model=model_config.fast_model())
    assert router._model == "claude-haiku-4-5"


def test_router_defaults_to_deep_when_unspecified():
    router = SmartRouter(llm_client=None)
    assert router._model == model_config.default_model()
```

- [ ] **Step 2: Run test to verify it passes for default, then change wiring**

Run: `cd rambo-backend && python -m pytest tests/test_router_model.py::test_router_defaults_to_deep_when_unspecified -v`
Expected: PASS (existing behavior). The first test already passes too because it constructs the router directly — it documents the contract Task 2 wires up in the orchestrator.

- [ ] **Step 3: Wire the orchestrator to pass the fast model**

In `rambo-backend/orchestrator/orchestrator.py`, change the router construction (currently `self.router = SmartRouter(self.llm)` near line 72):

```python
        # Tier 1 — smart routing brain (fast model: routing is a quick decision).
        self.router = SmartRouter(self.llm, model=model_config.fast_model())
```

`model_config` is already imported at the top of `orchestrator.py`.

- [ ] **Step 4: Run the full suite to confirm nothing broke**

Run: `cd rambo-backend && python -m pytest tests/test_router_model.py tests/test_model_config.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/orchestrator/orchestrator.py rambo-backend/tests/test_router_model.py
git commit -m "feat: route on the fast model tier"
```

---

### Task 3: `DispatchRepo` — schema, register, update, queries

**Files:**
- Create: `rambo-backend/dispatch_repo.py`
- Test: `rambo-backend/tests/test_dispatch_repo.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `DispatchRepo(db_path: str | Path | None = None)` with `_db_path`.
  - `async init_db() -> None`
  - `async register(goal: str, plan: str = "") -> int`
  - `async update_status(dispatch_id: int, status: str, summary: str = "") -> None`
  - `async get_active() -> list[dict]`
  - `async get_recent(limit: int = 5) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Create `rambo-backend/tests/test_dispatch_repo.py`:

```python
import pytest
import pytest_asyncio
import aiosqlite
from dispatch_repo import DispatchRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    r = DispatchRepo(db_path=tmp_path / "test_dispatch.db")
    await r.init_db()
    return r


@pytest.mark.asyncio
async def test_table_and_columns(repo):
    async with aiosqlite.connect(repo._db_path) as db:
        rows = await db.execute_fetchall("PRAGMA table_info(dispatches)")
        cols = {r[1] for r in rows}
    assert cols == {
        "id", "goal", "plan", "status", "summary",
        "created_at", "updated_at", "completed_at",
    }


@pytest.mark.asyncio
async def test_register_creates_working_row(repo):
    did = await repo.register("build a landing page", "architect; engineer")
    assert isinstance(did, int)
    active = await repo.get_active()
    assert len(active) == 1
    assert active[0]["goal"] == "build a landing page"
    assert active[0]["status"] == "working"
    assert active[0]["completed_at"] is None


@pytest.mark.asyncio
async def test_update_status_completes_row(repo):
    did = await repo.register("research X")
    await repo.update_status(did, "completed", "Found 3 sources")
    assert await repo.get_active() == []
    recent = await repo.get_recent()
    assert recent[0]["status"] == "completed"
    assert recent[0]["summary"] == "Found 3 sources"
    assert recent[0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_failed_status_sets_completed_at(repo):
    did = await repo.register("do thing")
    await repo.update_status(did, "failed", "boom")
    recent = await repo.get_recent()
    assert recent[0]["status"] == "failed"
    assert recent[0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_get_recent_orders_newest_first_and_limits(repo):
    for i in range(7):
        await repo.register(f"goal {i}")
    recent = await repo.get_recent(limit=5)
    assert len(recent) == 5
    assert recent[0]["goal"] == "goal 6"


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_path):
    r = DispatchRepo(db_path=tmp_path / "d.db")
    await r.init_db()
    await r.init_db()
    await r.register("g")
    assert len(await r.get_active()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && python -m pytest tests/test_dispatch_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dispatch_repo'`

- [ ] **Step 3: Implement `DispatchRepo`**

Create `rambo-backend/dispatch_repo.py`:

```python
from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent / "data" / "dispatch.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS dispatches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    goal         TEXT    NOT NULL,
    plan         TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'working',
    summary      TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dispatch_status     ON dispatches(status);
CREATE INDEX IF NOT EXISTS idx_dispatch_updated_at ON dispatches(updated_at DESC);
"""

_DONE = ("completed", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DispatchRepo:
    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB

    async def init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)

    async def register(self, goal: str, plan: str = "") -> int:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "INSERT INTO dispatches (goal, plan, status, created_at, updated_at) "
                "VALUES (?, ?, 'working', ?, ?)",
                (goal, plan, now, now),
            )
            await db.commit()
            return cur.lastrowid

    async def update_status(self, dispatch_id: int, status: str, summary: str = "") -> None:
        now = _now()
        completed_at = now if status in _DONE else None
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE dispatches SET status=?, summary=?, updated_at=?, completed_at=? "
                "WHERE id=?",
                (status, summary, now, completed_at, dispatch_id),
            )
            await db.commit()

    async def get_active(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM dispatches WHERE status='working' ORDER BY updated_at DESC"
            )
            return [dict(r) for r in rows]

    async def get_recent(self, limit: int = 5) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM dispatches ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && python -m pytest tests/test_dispatch_repo.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/dispatch_repo.py rambo-backend/tests/test_dispatch_repo.py
git commit -m "feat: add DispatchRepo persistence (schema, register, update, queries)"
```

---

### Task 4: `format_for_prompt()` context block

**Files:**
- Modify: `rambo-backend/dispatch_repo.py`
- Test: `rambo-backend/tests/test_dispatch_repo.py` (add tests)

**Interfaces:**
- Consumes: `get_active()`, `get_recent()` (Task 3).
- Produces: `async format_for_prompt() -> str` — returns `""` when nothing to report; otherwise a block with `CURRENTLY WORKING ON:` and/or `RECENTLY COMPLETED:` sections.

- [ ] **Step 1: Write the failing tests**

Append to `rambo-backend/tests/test_dispatch_repo.py`:

```python
@pytest.mark.asyncio
async def test_format_for_prompt_empty(repo):
    assert await repo.format_for_prompt() == ""


@pytest.mark.asyncio
async def test_format_for_prompt_active(repo):
    await repo.register("build the dashboard")
    out = await repo.format_for_prompt()
    assert "CURRENTLY WORKING ON:" in out
    assert "build the dashboard" in out


@pytest.mark.asyncio
async def test_format_for_prompt_completed(repo):
    did = await repo.register("research pricing")
    await repo.update_status(did, "completed", "Compared 3 vendors")
    out = await repo.format_for_prompt()
    assert "RECENTLY COMPLETED:" in out
    assert "Compared 3 vendors" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rambo-backend && python -m pytest tests/test_dispatch_repo.py -k format -v`
Expected: FAIL with `AttributeError: 'DispatchRepo' object has no attribute 'format_for_prompt'`

- [ ] **Step 3: Implement `format_for_prompt`**

Add this method to `DispatchRepo` in `rambo-backend/dispatch_repo.py`, and add `import time`-free elapsed via timestamps using `datetime`:

```python
    async def format_for_prompt(self) -> str:
        active = await self.get_active()
        recent = await self.get_recent(3)
        completed = [r for r in recent if r["status"] in _DONE]

        parts: list[str] = []
        if active:
            lines = [f"  - [working] {r['goal']}" for r in active]
            parts.append("CURRENTLY WORKING ON:\n" + "\n".join(lines))
        if completed:
            lines = []
            for r in completed[:2]:
                tail = f": {r['summary']}" if r["summary"] else ""
                lines.append(f"  - {r['goal']}{tail}")
            parts.append("RECENTLY COMPLETED:\n" + "\n".join(lines))
        return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rambo-backend && python -m pytest tests/test_dispatch_repo.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/dispatch_repo.py rambo-backend/tests/test_dispatch_repo.py
git commit -m "feat: add DispatchRepo.format_for_prompt context block"
```

---

### Task 5: Orchestrator setter + best-effort dispatch logging

**Files:**
- Modify: `rambo-backend/orchestrator/orchestrator.py` (`__init__`, new `set_dispatch_repo`, `handle`)
- Test: `rambo-backend/tests/test_orchestrator_dispatch_log.py` (create)

**Interfaces:**
- Consumes: `DispatchRepo.register/update_status` (Tasks 3-4).
- Produces: `Orchestrator.set_dispatch_repo(repo)`; `self.dispatch_repo` attribute (default `None`).

- [ ] **Step 1: Write the failing test**

Create `rambo-backend/tests/test_orchestrator_dispatch_log.py`:

```python
import pytest
import pytest_asyncio
from orchestrator.orchestrator import Orchestrator
from orchestrator.routing import RoutingDecision, RouteStep
from dispatch_repo import DispatchRepo


@pytest_asyncio.fixture
async def orch(tmp_path):
    o = Orchestrator()
    repo = DispatchRepo(db_path=tmp_path / "d.db")
    await repo.init_db()
    o.set_dispatch_repo(repo)
    return o, repo


@pytest.mark.asyncio
async def test_dispatch_turn_logs_completed_row(orch, monkeypatch):
    o, repo = orch

    async def fake_route(goal, roster_lines, valid_targets):
        return RoutingDecision(mode="dispatch", steps=[RouteStep(target="seeker", task="look up X")])
    monkeypatch.setattr(o.router, "route", fake_route)

    async def fake_run_target(target, task, ctx):
        return "did the thing"
    monkeypatch.setattr(o, "_run_target", fake_run_target)

    async def fake_speak(goal, plan, results):
        return "All done."
    monkeypatch.setattr(o, "_speak", fake_speak)

    await o.handle("find X")

    recent = await repo.get_recent()
    assert len(recent) == 1
    assert recent[0]["status"] == "completed"
    assert await repo.get_active() == []


@pytest.mark.asyncio
async def test_no_repo_is_noop(monkeypatch):
    o = Orchestrator()  # dispatch_repo defaults to None

    async def fake_route(goal, roster_lines, valid_targets):
        return RoutingDecision(mode="dispatch", steps=[RouteStep(target="seeker", task="t")])
    monkeypatch.setattr(o.router, "route", fake_route)

    async def fake_run_target(target, task, ctx):
        return "ok"
    monkeypatch.setattr(o, "_run_target", fake_run_target)

    async def fake_speak(goal, plan, results):
        return "done"
    monkeypatch.setattr(o, "_speak", fake_speak)

    result = await o.handle("do it")  # must not raise
    assert result["agent"] == "rambo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_orchestrator_dispatch_log.py -v`
Expected: FAIL with `AttributeError: 'Orchestrator' object has no attribute 'set_dispatch_repo'`

- [ ] **Step 3: Add the attribute, setter, and best-effort logging**

In `rambo-backend/orchestrator/orchestrator.py` `__init__`, beside the factory wiring (`self.factory_repo = None`), add:

```python
        self.dispatch_repo = None
```

Add the setter next to `set_factory`:

```python
    def set_dispatch_repo(self, dispatch_repo):
        """Give the orchestrator a durable dispatch log (best-effort)."""
        self.dispatch_repo = dispatch_repo
```

Add a private best-effort helper (anywhere among the helpers):

```python
    async def _register_dispatch(self, goal: str, plan: list[str]) -> int | None:
        if not self.dispatch_repo:
            return None
        try:
            return await self.dispatch_repo.register(goal, "; ".join(plan))
        except Exception:
            return None

    async def _close_dispatch(self, dispatch_id, status: str, summary: str):
        if not self.dispatch_repo or dispatch_id is None:
            return
        try:
            await self.dispatch_repo.update_status(dispatch_id, status, summary[:500])
        except Exception:
            pass
```

In `handle()`, replace the dispatch block (currently builds `plan`/`results`, then `_speak`) with registration + close. The new body of the dispatch branch:

```python
        # dispatch: run each ordered step through the right target.
        plan, results = [], []
        for step in decision.steps:
            plan.append(f"{step.target}: {step.task}")

        dispatch_id = await self._register_dispatch(goal, plan)
        try:
            for step in decision.steps:
                res = await self._run_target(step.target, step.task, ctx)
                results.append(res)
            summary = await self._speak(goal, plan, results)
            await self._close_dispatch(dispatch_id, "completed", summary)
            return {"response": summary, "agent": "rambo"}
        except Exception as e:
            await self._close_dispatch(dispatch_id, "failed", str(e))
            raise
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd rambo-backend && python -m pytest tests/test_orchestrator_dispatch_log.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/orchestrator/orchestrator.py rambo-backend/tests/test_orchestrator_dispatch_log.py
git commit -m "feat: log dispatches to DispatchRepo from orchestrator (best-effort)"
```

---

### Task 6: Inject dispatch context into router and voice

**Files:**
- Modify: `rambo-backend/orchestrator/orchestrator.py` (`handle`, `_speak`)
- Test: `rambo-backend/tests/test_dispatch_context_injection.py` (create)

**Interfaces:**
- Consumes: `DispatchRepo.format_for_prompt()` (Task 4).
- Produces: nothing new; `handle()` passes a context string into routing, `_speak()` includes it in the execution report.

- [ ] **Step 1: Write the failing test**

Create `rambo-backend/tests/test_dispatch_context_injection.py`:

```python
import pytest
import pytest_asyncio
from orchestrator.orchestrator import Orchestrator
from dispatch_repo import DispatchRepo


@pytest_asyncio.fixture
async def orch(tmp_path):
    o = Orchestrator()
    repo = DispatchRepo(db_path=tmp_path / "d.db")
    await repo.init_db()
    o.set_dispatch_repo(repo)
    return o, repo


@pytest.mark.asyncio
async def test_dispatch_context_returns_block_when_present(orch):
    o, repo = orch
    did = await repo.register("earlier goal")
    await repo.update_status(did, "completed", "done earlier")
    ctx_block = await o._dispatch_context()
    assert "RECENTLY COMPLETED" in ctx_block


@pytest.mark.asyncio
async def test_dispatch_context_empty_without_repo():
    o = Orchestrator()
    assert await o._dispatch_context() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd rambo-backend && python -m pytest tests/test_dispatch_context_injection.py -v`
Expected: FAIL with `AttributeError: 'Orchestrator' object has no attribute '_dispatch_context'`

- [ ] **Step 3: Add `_dispatch_context` and wire it into routing + `_speak`**

Add the helper to `orchestrator.py`:

```python
    async def _dispatch_context(self) -> str:
        if not self.dispatch_repo:
            return ""
        try:
            return await self.dispatch_repo.format_for_prompt()
        except Exception:
            return ""
```

In `handle()`, fetch the context once and fold it into the goal handed to the router (the router takes a single `goal` string):

```python
        roster_lines, valid_targets = await self._build_roster()
        dispatch_ctx = await self._dispatch_context()
        routed_goal = f"{dispatch_ctx}\n\n{goal}" if dispatch_ctx else goal
        decision = await self.router.route(routed_goal, roster_lines, valid_targets)
```

Keep the rest of `handle()` using the original `goal` for registration and `_speak`.

In `_speak()`, prepend the same context to the execution report. After the existing `execution_report = (...)` assignment, add:

```python
        dispatch_ctx = await self._dispatch_context()
        if dispatch_ctx:
            execution_report = f"{dispatch_ctx}\n\n{execution_report}"
```

- [ ] **Step 4: Run the test + full suite to verify**

Run: `cd rambo-backend && python -m pytest tests/test_dispatch_context_injection.py tests/test_orchestrator_dispatch_log.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/orchestrator/orchestrator.py rambo-backend/tests/test_dispatch_context_injection.py
git commit -m "feat: inject dispatch context into router and voice"
```

---

### Task 7: Wire `DispatchRepo` into app startup

**Files:**
- Modify: `rambo-backend/main.py`

**Interfaces:**
- Consumes: `DispatchRepo` (Task 3), `Orchestrator.set_dispatch_repo` (Task 5).
- Produces: a live, initialized `DispatchRepo` attached to the running orchestrator.

- [ ] **Step 1: Add the import and module-level repo**

In `rambo-backend/main.py`, near the other repo imports (`from usage_repo import UsageRepo`) add:

```python
from dispatch_repo import DispatchRepo
```

Near `_usage_repo = UsageRepo()` add:

```python
_dispatch_repo = DispatchRepo()
```

- [ ] **Step 2: Add the startup hook**

After the existing `_init_usage_db` startup function, add:

```python
@app.on_event("startup")
async def _init_dispatch_db():
    await _dispatch_repo.init_db()
    rambo.set_dispatch_repo(_dispatch_repo)
```

- [ ] **Step 3: Verify the app imports and starts cleanly**

Run: `cd rambo-backend && python -c "import main; print('ok')"`
Expected: prints `ok` with no import error.

- [ ] **Step 4: Run the full test suite**

Run: `cd rambo-backend && python -m pytest -q`
Expected: PASS (all existing + new tests green)

- [ ] **Step 5: Commit**

```bash
git add rambo-backend/main.py
git commit -m "feat: initialize DispatchRepo on startup and attach to orchestrator"
```

---

## Self-Review

**Spec coverage:**
- Part A model split → Tasks 1 (tier) + 2 (router wiring). Voice/agents unchanged (verified: only `orchestrator.py:72` touched). ✓
- Part B schema/register/update/queries → Task 3. ✓
- `format_for_prompt` → Task 4. ✓
- Orchestrator best-effort integration + None no-op → Task 5. ✓
- Context injection into router + voice → Task 6. ✓
- main.py wiring (usage/factory pattern) → Task 7. ✓
- Tests mirror `test_usage_repo.py` → Tasks 3, 4. ✓
- Non-goals (no agent_tracker change, no tags/AppleScript) → respected; no task touches `agent_tracker.py`. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**Type consistency:** `register(goal, plan="") -> int`, `update_status(id, status, summary="")`, `get_active()`, `get_recent(limit=5)`, `format_for_prompt() -> str`, `set_dispatch_repo(repo)`, `_dispatch_context() -> str`, `_register_dispatch`/`_close_dispatch` — names identical across Tasks 3–7. ✓
