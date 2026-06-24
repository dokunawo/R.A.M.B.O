# Design: Persistent Dispatch Memory + Fast/Deep Model Split

**Date:** 2026-06-24
**Status:** Approved (design), pending implementation plan

## Background

Inspired by patterns observed in an external "JARVIS" voice-assistant project, two
genuine gaps were identified in R.A.M.B.O:

1. **No persistent dispatch memory.** `agent_tracker.py` holds per-agent stats,
   activity, and learnings in module-level dicts that are **wiped on every restart**
   (capped at 20 activities / 50 learnings). Nothing durably records the goals
   R.A.M.B.O has dispatched, their status, or outcomes.

2. **No model tiering.** `model_config.py` exposes a single `default_model()`
   (Sonnet) used for *both* the quick routing decision *and* the user-facing voice
   and agent reasoning. The fast routing classification pays Sonnet latency/cost
   unnecessarily.

A third candidate — porting JARVIS's inline `[ACTION:X]` tag dispatch — was
**explicitly dropped**: R.A.M.B.O's `SmartRouter` already performs structured
LLM dispatch (tool-call → typed `RouteStep` list / clarify), which is strictly
better than regex-parsing tags out of prose.

## Goals

- Add a durable, restart-surviving record of dispatched goals (status, summary,
  timestamps).
- Feed that record back into the router and the voice so R.A.M.B.O is aware of what
  it is "currently working on" and "recently completed".
- Introduce a fast model tier for the routing decision while keeping the deep model
  for voice and spawned agents.

## Non-Goals

- No changes to `agent_tracker.py` (it remains the live per-agent UI stats source;
  DispatchRepo is the complementary durable goal log).
- No AppleScript, inline action tags, or file-polling completion detection ported
  from JARVIS.
- No third "heavy"/Opus tier (deferred; two tiers only).

## Part A — Fast/Deep Model Split

### Changes

`model_config.py` gains a second tier alongside the existing `default_model()`:

```python
DEFAULT_MODEL = "claude-sonnet-4-6"      # deep (unchanged)
FAST_MODEL    = "claude-haiku-4-5"       # fast (new)

def default_model() -> str:
    return os.environ.get("RAMBO_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

def fast_model() -> str:
    return os.environ.get("RAMBO_FAST_MODEL", FAST_MODEL).strip() or FAST_MODEL
```

### Tier mapping

| Call site | Tier | Model | Change |
|-----------|------|-------|--------|
| `SmartRouter.route()` (routing/clarify) | fast | `fast_model()` | `orchestrator.py` constructs `SmartRouter(self.llm, model=model_config.fast_model())` |
| `Orchestrator._speak()` (voice) | deep | `default_model()` | none |
| Spawned factory agents | deep | `default_model()` | none |

`SmartRouter.__init__` already accepts an optional `model` param defaulting to
`default_model()`, so the only wiring change is the one constructor call at
`orchestrator/orchestrator.py:72`.

### Observability

`record_usage()` already logs `model` per call, so the split is automatically
visible in the usage dashboard (per-model cost breakdown). No extra work.

## Part B — DispatchRepo

### New file: `rambo-backend/dispatch_repo.py`

Mirrors `usage_repo.py` conventions exactly: `aiosqlite`, DB at
`data/dispatch.db`, async `init_db()` creating the schema idempotently.

Schema:

```sql
CREATE TABLE IF NOT EXISTS dispatches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    goal         TEXT    NOT NULL,
    plan         TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'working',   -- working | completed | failed
    summary      TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dispatch_status     ON dispatches(status);
CREATE INDEX IF NOT EXISTS idx_dispatch_updated_at ON dispatches(updated_at DESC);
```

### API

- `async register(goal: str, plan: str = "") -> int` — insert a `working` row,
  return its id.
- `async update_status(dispatch_id: int, status: str, summary: str = "")` — set
  status/summary/updated_at; set `completed_at` when status in
  (`completed`, `failed`).
- `async get_active() -> list[dict]` — rows with status `working`, newest first.
- `async get_recent(limit: int = 5) -> list[dict]` — last N, newest first.
- `async format_for_prompt() -> str` — returns a context block:

  ```
  CURRENTLY WORKING ON:
    - [working] <goal> (<elapsed>s ago)
  RECENTLY COMPLETED:
    - <goal>: <summary>
  ```

  Returns `""` when there is nothing to report (so callers can inject nothing).

### Wiring (`main.py`)

Same pattern as `UsageRepo` / `FactoryRepo`:

```python
_dispatch_repo = DispatchRepo()

@app.on_event("startup")
async def _init_dispatch_db():
    await _dispatch_repo.init_db()
    rambo.set_dispatch_repo(_dispatch_repo)
```

`Orchestrator` gains `self.dispatch_repo = None` in `__init__` and a
`set_dispatch_repo(repo)` setter (mirroring `set_factory`).

### Orchestrator integration (`handle()`)

On a `dispatch` decision (not `clarify`):

1. `dispatch_id = await register(goal, plan_text)` **before** running steps.
2. Run the ordered steps as today.
3. After `_speak()` produces the summary,
   `await update_status(dispatch_id, "completed", summary)`.
4. On exception during step execution, `update_status(..., "failed", error)`.

All registry calls are **best-effort**: wrapped so a registry failure never breaks
the conversation turn (same discipline as `record_usage`). If `self.dispatch_repo`
is `None` (e.g. tests, no DB), all calls are no-ops.

### Context injection (the feedback loop)

`format_for_prompt()` output is threaded into two places, each guarded against an
empty string:

1. **Router** — prepended to the routing user message so the router knows what is
   in flight / just finished when deciding the next dispatch.
2. **`_speak()`** — added to the execution report so the voice can naturally
   reference recent work.

## Testing (TDD)

Against existing `rambo-backend/tests/` (pytest, async).

- `test_dispatch_repo.py` (mirrors `test_usage_repo.py`):
  - temp DB → `init_db()` creates schema.
  - `register()` returns an id and creates a `working` row.
  - `update_status(..., completed, summary)` sets status, summary, `completed_at`.
  - `get_active()` / `get_recent()` ordering and filtering.
  - `format_for_prompt()` includes active + completed sections; returns `""` when
    empty.
- Orchestrator test: a `dispatch` turn writes exactly one row that ends
  `completed`. Registry-absent (`dispatch_repo=None`) path is a clean no-op.
- `model_config` test: `fast_model()` honors `RAMBO_FAST_MODEL` and falls back to
  `FAST_MODEL`.

## Risk / Rollback

- Additive only; no existing call sites change behavior except the router's model
  id. Setting `RAMBO_FAST_MODEL` equal to `RAMBO_MODEL` reverts the split.
- DispatchRepo is fully isolated; if `set_dispatch_repo` is never called the
  orchestrator behaves exactly as today.
