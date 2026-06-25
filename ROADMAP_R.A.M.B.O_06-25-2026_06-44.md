# R.A.M.B.O — PROJECT ROADMAP
**Responsive Autonomous Multi-Brain Operator**
Created: 06/25/2026 at 06:44 (supersedes ROADMAP 06/24/2026 14:26)

---

## Session: 06/25/2026 — The self-coding lane (RAMBO edits its own code)

RAMBO can now do what Claude Code does — read its own codebase, write and review
changes (with tests it actually runs red→green), and modify its own system — but
**never edits the running process directly.** Every self-change happens on an
isolated git worktree, is reviewed by the operator (diff + impact + recommendation),
and only lands on `main` on an explicit merge. Architecture: **Hybrid** — the
existing factory still spawns helper agents; a new git-isolated `dev_agent/` lane
handles self-code-modification. Everything below is shipped, tested (full suite
**320 pass**), and verified live in the container.

### The dev lane — core (`rambo-backend/dev_agent/`)
| Component | What it does | Status |
|---|---|---|
| `git_workspace.py` | Creates a worktree off HEAD on a throwaway `rambo/dev-*` branch; commits **only the agent's touched paths** (never `git add -A`); diff; merge; discard. Merge guard blocks only on real file overlap with local WIP. Commits/merges use `--no-verify` so repo hooks don't inject unrelated files. | Done |
| `coding_agent.py` | Worktree-confined tool loop (`read_file`/`list_files`/`write_file`/`edit_file`/`run_tests`) — physically cannot read or write outside the worktree. | Done |
| `impact.py` | After the draft, an LLM pass reports what the change affects + a **recommendation: merge / escalate-to-Claude / hold**. | Done |
| `session.py` | Drivers: `draft_change` (worktree→agent→commit→diff→impact→pending_review), `merge_change`, `reject_change`, `escalate_change` (writes a review artifact to `data/escalations/`). | Done |
| `repo.py` | `code_changes` SQLite table (`data/dev_changes.db`) tracking each proposed change through its lifecycle. | Done |

### Review surface + wiring
| Feature | Status |
|---|---|
| `/dev/*` endpoints (propose, pending, change, merge, reject, escalate) | Done |
| Orchestrator **`dev` routable target** + `_run_dev_session` — streams `dev_progress`, registers a pending review, speaks a summary; **never auto-merges** | Done |
| Frontend **`CodeReviewDock`** (SharedHUD.js) — per-change card with recommendation badge; expandable **diff**, impact summary, and **Merge / Send to Claude / Reject** actions | Done |

### Phase 4 — engineering playbooks (codes like Claude-with-superpowers)
| Feature | Status |
|---|---|
| `dev_agent/playbooks/` — TDD, systematic-debugging, verification-before-completion (distilled from superpowers, adapted to the local agent; Claude-Code-harness skills omitted) | Done |
| Injected into the agent's system prompt; selectable via `RAMBO_DEV_PLAYBOOKS` (all / `off` / CSV subset) | Done |
| **Closed-loop TDD** — `run_tests` tool runs **pytest only** on a worktree-confined path (180s timeout). Verified: agent writes test → runs RED → writes impl → runs GREEN (`[False, True]`) | Done |

### Fixes / hardening (06/25/2026)
| Fix | Status |
|---|---|
| **Container git access** — `docker-compose.yml` now mounts `./:/repo:rw` (was `:ro`); `RAMBO_REPO_ROOT=/repo`, `RAMBO_WORKTREE_DIR=/tmp/rambo-worktrees`. Dev lane works in-container. | Done |
| **Pre-commit-hook pollution** — the `[self-knowledge-hook]` was injecting `context/self/rambo.md` into every dev-lane commit; fixed with `--no-verify`. | Done |
| `pytest` + `pytest-asyncio` added to `requirements.txt`; backend image rebuilt so `run_tests` works on a fresh container. | Done |

---

## What's Next

### Short Term
- **Voice/self-review polish (Phase 5)** — "RAMBO, review the auth module" voice trigger; point the agent at its own open changes.
- **Full-suite run_tests** — option to run the whole suite, not just one file, before a merge.

### Mid Term
- **Alembic migrations** — as the SQLite schemas (usage/dispatch/tts/keeper/dev_changes) evolve.
- **Echo channels** — push/SMS alongside email (Twilio).

### Long Term
- Cloud-hosted personal digital twin that learns the operator and runs open-ended research (the north-star vision).

---

## Endpoints added this session
`POST /dev/propose` · `GET /dev/pending` · `GET /dev/change/{id}` ·
`POST /dev/merge/{id}` · `POST /dev/reject/{id}` · `POST /dev/escalate/{id}`

## New env vars
`RAMBO_REPO_ROOT` · `RAMBO_WORKTREE_DIR` · `RAMBO_DEV_PLAYBOOKS` ·
`RAMBO_TEST_CMD` · `RAMBO_TEST_CWD`
