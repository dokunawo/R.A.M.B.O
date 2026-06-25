# R.A.M.B.O — Self-Coding Agent Plan
**Responsive Autonomous Multi-Brain Operator**
Created: 06/24/2026 ET

> Goal: give R.A.M.B.O the ability to do what Claude Code does — read its own
> codebase, write and review code, and propose changes to its own system — in
> its own AGENT.md voice, **without ever letting it edit the running process
> directly.** All self-modification happens on a branch in a sandboxed clone and
> lands as a pull request the operator (Daniel) reviews and merges.

---

## Core architecture

| Layer | How |
|---|---|
| Brain / agent loop | **Managed Agents** (Anthropic runs the loop *and* hosts a per-session sandbox container) |
| Voice / character | Existing `rambo-backend/AGENT.md` → the agent's `system` prompt |
| Skill behaviors | Selected `SKILL.md` playbooks uploaded via the Skills API, attached to the agent (max 20) |
| Hands | Built-in `agent_toolset` (`bash`, `read`, `write`, `edit`, `glob`, `grep`, `web_fetch`, `web_search`) |
| Self-modification (safe) | RAMBO repo mounted in a throwaway container → agent edits a clone → pushes a branch → opens a PR → **Daniel merges**. Never touches `main` or the running process. |
| Engine | `claude-opus-4-8` (current most-capable Opus; the default) |

**Hard constraints (do not relax without explicit decision):**
- Everything requires `ANTHROPIC_API_KEY`. No key → none of this works.
- The agent never edits the running RAMBO. Mounted clone + branch + PR only.
- Voice chat stays the simple router. Only the new `dev`/`build` lane gets the agent loop. **Two lanes, one orchestrator.**

---

## Recommended procedure (read first)

Two things flagged before committing, baked into the sequencing below:

1. **Phases 0–1 are a cheap viability gate. Do them first, regardless of
   whether the rest gets green-lit.** They are small, high-information, and they
   de-risk the only scary assumption (sandboxed self-editing + PR loop). Decide
   on Phases 2–5 *after* Phase 1 proves the loop on the real repo.
2. **Phase 3 is the real engineering** (orchestrator changes, event streaming,
   the two-lane split). Budget most of the time there — not on the setup phases.

---

## Phase 0 — Unblock the engine  *(prerequisite — gate)*  ✅ DONE (06/24/2026)
Nothing below works without this.
- [x] `ANTHROPIC_API_KEY` already set in `rambo-backend/.env` (real key, sk-ant-, 108 chars).
- [x] Smoke-test passed: live call to `claude-opus-4-8` returned cleanly (21 in / 9 out tokens). `anthropic` 0.111.0, Python 3.14.6.
- [x] **Free win VERIFIED (06/24):** ran the `_speak` personality path in-process
      with the real key — RAMBO replied in its retuned conversational voice
      ("I'm R.A.M.B.O — I run a team of ten specialist agents…"). Prompt caching
      active on the system blocks. Backend runs in **Docker** (compose), frontend
      is a **separate container** — a backend restart never touches the kiosk.

> Note (06/24): the codebase already has a `factory/` (`/factory/spawn`,
> `/factory/approve`, `tool_registry.py`, `config_agent.py`, `research.py`) — a
> partial agent-spawn/approve flow the original handoff never mentioned. **Check
> whether Phase 3 can build on the factory instead of greenfield.**
- **Decision point:** token spend starts here. The agent loop costs far more than
  the personality layer. Set a budget expectation now.

## Phase 1 — Prove the agent loop in isolation  *(gate — do NOT wire into RAMBO yet)*
Throwaway script, outside the RAMBO app:
- [ ] Create a Managed Agent (system prompt = `AGENT.md`, built-in toolset on).
- [ ] Create an environment (sandbox config).
- [ ] Start a session, mount the RAMBO GitHub repo, give one trivial task
      ("add a comment to the README, open a PR").
- [ ] Watch it edit a clone → push a branch → open a PR → Daniel merges.
- **Why first:** confirms sandbox + PR loop works end-to-end on the real repo
  with real credentials, where a mistake can't hurt anything.
- **Decision point:** Managed Agents (hosted sandbox) vs. self-hosted loop.
  Start with Managed Agents — sandbox + PR safety are free. Move compute
  in-house later only if needed.

**Harness built (06/24):** `scripts/phase1_agent_harness.py` — throwaway, outside
the app. SDK 0.111.0 confirmed to expose `beta.agents/sessions/environments`.
`--dry-run` passes. Two stages: **1a** (sandbox-only proof, no secrets) runs by
default; **1b** (repo mount + PR) is gated behind `--repo` + `--github-token`
because it needs a GitHub PAT and a vault credential for the GitHub MCP server.
A live run BILLS and creates a persistent `environment` + `agent` (reused in
Phase 2).

**Stage 1a PASSED live (06/24):** agent ran in a real sandbox container, called
`write` then `read`, reported back in RAMBO's voice. Loop + sandbox proven.
Persistent IDs for Phase 2 (reuse, do NOT re-create):
- `AGENT_ID = agent_01NUjSeyRBwjzaysnAvhTCyG`
- `ENV_ID   = env_013pRb2HF6GiQ4UoLt24dL9K`

**Stage 1b DEFERRED (06/24) — operator chose to skip for now.** The repo→branch→PR
proof (the sandboxed-self-edit safety mechanism) is not yet run. To resume: set
`GITHUB_TOKEN` env var (fine-grained PAT scoped to dokunawo/R.A.M.B.O, Contents +
Pull requests = read/write) then `python scripts/phase1_agent_harness.py --repo
https://github.com/dokunawo/R.A.M.B.O`. Do this before Phase 3 — that's when RAMBO
starts proposing changes to itself and the guardrail must be proven. The PR step
also needs a GitHub MCP vault credential (push will work without it; PR open won't).

> ⛔ **STOP / GO checkpoint.** Stage 1a = **GO** (loop viable). Full GO to Phase 2
> wants Stage 1b green too (proves the sandboxed self-edit → PR loop, the actual
> safety mechanism). Run 1b before committing to orchestrator surgery.

## Phase 2 — Persist the agent, set the safety rails
- [ ] **Hoist agent creation out of the request path.** Create the agent once,
      store `agent_id` (env var or small config row). Reference by ID per task —
      never re-create. (Documented #1 anti-pattern.)
- [ ] Permission policies: `always_ask` on `bash` and destructive tools;
      `always_allow` on read-only (`read`, `grep`, `glob`). Human-in-the-loop gate.
- [ ] Lock the self-modification contract in the agent's system prompt **and**
      enforce via mounted-repo-only sandbox: branch → push → PR → Daniel merges.
      Never `main`, never the live process.

## Phase 3 — Wire into the orchestrator  *(the real work — budget the most time here)*

> ✅ **BUILT as the HYBRID architecture (06/25).** Implemented as a git-isolated
> `rambo-backend/dev_agent/` lane (worktree → coding agent → diff + impact +
> recommendation → operator merge), NOT a `skills.py` skill. Files:
> `dev_agent/{git_workspace,coding_agent,impact,session,repo}.py`, `/dev/*`
> endpoints in `main.py`, `dev` target + `_run_dev_session` in `orchestrator.py`,
> `CodeReviewDock` in `rambo-frontend/src/components/SharedHUD.js`. Full detail
> in the approved plan: `C:\Users\dokun\.claude\plans\which-option-do-you-rosy-pretzel.md`.
> Tests: 307 pass (incl. `test_git_workspace.py`, `test_dev_repo.py`). Live UI
> needs a backend restart (uvicorn no auto-reload). The sub-bullets below were
> the original generic sketch; the Hybrid plan superseded them.

- [ ] New skill/intent in `rambo-backend/skills.py` (e.g. `dev` / `build`) that
      matches "RAMBO, fix the X bug" / "add a Y endpoint."
- [ ] On match, `orchestrator.py` **starts a Managed Agents session** instead of
      running a deterministic stub; streams events; surfaces progress.
- [ ] **Reverse the old "no tool_use" decision — for this lane only.** Voice chat
      stays the simple router (right call for voice). Coding gets the agent loop.
- [ ] Wire the agent event stream (`agent.message` / `tool_use` events) to the
      existing WebSocket activity feed (Phase 2 console / dispatch beams). This is
      where it starts *looking* like RAMBO doing the work.

## Phase 4 — Import skill behaviors
RAMBO codes like *Claude-with-superpowers*, not generic Claude:
- [ ] Upload 2–3 high-leverage `SKILL.md` playbooks via the Skills API:
      `systematic-debugging`, `test-driven-development`,
      `verification-before-completion`.
- [ ] Attach to the agent (max 20).
- [ ] **Skip Claude-Code-specific skills** (worktrees, the Skill tool, MCP
      plumbing) — they assume Claude Code's harness, not RAMBO's.

## Phase 5 — Close the loop on voice + review
- [ ] Voice trigger: "RAMBO, review the auth module" → kicks a session → speaks a
      summary in its AGENT.md voice when done.
- [ ] Self-review: point it at its own open PRs (reviews a diff in a sandbox;
      still cannot merge itself).
- [ ] Tune personality so the coding voice and conversational voice feel like one
      character.

---

## Critical-path summary
- **Phase 0 is the gate.** No key, no anything.
- **Phase 1 de-risks the scary part** (sandboxed self-edit + PR) cheaply.
- **Phase 3 is where the real engineering lives.**
- Phases 4–5 are integration you already have the UI plumbing for.

## Open decisions (resolve as you reach them)
- Managed Agents vs. self-hosted loop (default: Managed Agents — revisit only if
  compute must be local).
- Token budget ceiling for agent sessions.
- Which skills beyond the initial three.
- Where `agent_id` lives (env var vs. config/DB).
