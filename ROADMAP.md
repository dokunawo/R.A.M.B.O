# R.A.M.B.O — PROJECT ROADMAP

**Responsive Autonomous Multi-Brain Operator**
Consolidated 06/27/2026 · supersedes all dated `ROADMAP_*` files (06/21 → 06/26).

A multi-agent AI orchestrator (FastAPI back end + React 19 / Three.js cosmic console)
that routes operator goals across specialist agents, speaks back in a neural voice,
remembers across sessions, edits its own code on isolated git worktrees, and runs a
data-only MLB betting edge engine. Current build: **MK V**.

---

## Status snapshot (what's live)

- **Cosmic console** — unified `CosmicOrb` (wireframe icosahedron, simplex-noise
  displacement, fresnel glow, bloom) across all pages; deep-space cosmos background;
  3-phase splash; dispatch beams + processing helix; performance/reduced-motion modes.
- **Voice** — wake word "Operator", Web-Speech STT, **ElevenLabs neural TTS** (browser
  fallback), streaming per-sentence playback, orb pulses to its own voice, watchdog +
  dedup + half-duplex echo control.
- **Orchestration** — LLM `SmartRouter` over the live roster (core agents + skills +
  spawned manifests); least-privilege bounded sub-agents; failure isolation;
  confirmation gates; handoff system; live manifest hot-reload.
- **Connected agents** — Seeker (Anthropic `web_search` + Open-Meteo) LIVE; Keeper
  (SQLite memory) CONNECTED; Link (Google OAuth) CONNECTED; Echo (SMTP email) CONNECTED.
- **Self-knowledge** — auto-generated `context/self/rambo.md`, drift checker, pre-commit
  refresh, slim summary injected into the system prompt.
- **Cost tracking** — pricing module + `usage.db` + `/usage` dashboard + API/VOICE cost
  chips; 1h-TTL prompt caching across every agent loop.
- **Factory** — sub-agent spawner (research → spec → prompt → approval → `ConfigDrivenAgent`).
- **Self-coding lane** — `dev_agent/` drafts code changes on a git worktree, runs TDD
  red→green, reports impact, and lands on `main` only on explicit operator merge.
- **Morning brief** — daily scheduler (date + calendar + doctrine) shown on screen + emailed.
- **MLB betting edge engine** — data-only ingestion + EV brain (5 markets) + CMC card. See
  the [Betting Agent](#betting-agent--chances-make-champions) section.

Test suite: **320 pass** (core) + **~45** (EV brain + Player Watch / Moneyline Board). Stack:
React 19 / R3F / Three.js front end; FastAPI back end; SQLite (usage / dispatch / factory /
keeper / dev_changes / mlb_ingest); Docker Compose (`rambo-backend` :8000, prod `:3000`, dev
hot-reload `:3001`); PowerShell control panel + `cmc-daily.ps1` (daily betting run).
`rambo-startup.ps1` is single-instance (a global mutex stops the boot task + desktop shortcut
from ever opening two Chrome windows).

---

## Shipped — by session

### 06/21/2026 — Foundation
PowerShell control panel (`rambo-control-panel.ps1`, 7-step boot); `start-dev/prod.ps1`
Docker orchestration; `brains/` → `agents/` rename; `/agents/status` + WebSocket status;
CORS; plasma nucleus shader; 3-phase splash (transmission → briefing → plasma orb);
agent status panel.

### 06/22/2026 — The cosmic interface (6 tiers) + voice + console
- **CosmicOrb** (Tier 1): wireframe icosahedron, GLSL simplex noise, fresnel glow,
  billboarded halo, gold; unified across every page; black-square/flicker fixes; bloom.
- **Cosmos** (Tier 2): starfield + FBM nebula + node web + glow pool.
- **Voice** (Tier 3): wake word, STT → command input, TTS readback, conversational follow-up.
- **Constellation** (Tier 4): 10 orbiting agent nodes, depth-faded labels, status glow.
- **Dispatch & docking** (Tier 5): beams orb→agent, processing helix.
- **Wire to reality** (Tier 6): all animation driven by real WS events; performance mode.
- Console → `POST /rambo/execute` + live WS feed; `/system/stats` (psutil); skills layer
  (weather); per-agent detail pages; Sentinel approval queue; Steward budget; Round Table
  (`/council`); Learning Log (`/learning`); React Router v7; boot chime + ambient hum.

### 06/23/2026 — Operator-grade backend
- **SharedHUD** module (stat bars / activity feed / command input on every page);
  flicker mitigation (Vector2 hoisting, animation removal, GPU hints); ChromaticAberration removed.
- **Voice latency**: streaming `messages.stream()`, per-sentence split, hold-one-ahead,
  VAD 1500→1000ms (7 tests).
- **Cost dashboard**: pricing module, `usage` table, capture, `/usage` aggregation, UI chips (34 tests).
- **Self-knowledge system**: doc scaffold + 5 generators + drift checker + pre-commit hook + slim prompt inject.
- **Factory** (sub-agent spawner): research → spec → prompt → approval gate →
  `ConfigDrivenAgent` + `RegistryWatcher` hot-reload; `FactoryDock` UI (59 tests).
- **Orchestration layer** (all 6 tiers): SmartRouter, least-privilege, failure isolation,
  confirmation gates, handoff system, hot-reload.
- **Prompt caching** across all agent loops + 1h extended TTL.
- **Go-live**: `.env` auto-load, model-id fix (`claude-sonnet-4-6`), await bug fix, live
  end-to-end verified with caching; Nginx SPA fallback; `rambo-startup.ps1`. (181→ tests.)

### 06/24/2026 — Real voice + connected agent backends + persistence
- Persistent dispatch memory (`DispatchRepo`); fast/deep model split (Haiku routing).
- **ElevenLabs neural voice** (`tts.py`) with browser fallback; orb pulses to its own voice;
  wake word → "Operator"; reliable mic control + watchdog + speak dedup.
- MK III → **MK V**; voice-credit tracker chip; cost chips top-right; settings panel.
- **Connected agents**: Seeker (web_search) LIVE, Keeper (SQLite) CONNECTED, Link (Google
  OAuth) CONNECTED, Echo (SMTP) CONNECTED; `/agents/health` + `/integrations/status`.
- **Recurring morning brief** (`morning_brief.py`) — calendar + doctrine, on-screen + emailed.

### 06/25/2026 — The self-coding lane
- `dev_agent/`: `git_workspace.py` (worktree off HEAD, commits only touched paths),
  `coding_agent.py` (worktree-confined tool loop), `impact.py` (merge/escalate/hold rec),
  `session.py` drivers, `repo.py` (`dev_changes.db`).
- `/dev/*` endpoints; orchestrator `dev` target (never auto-merges); `CodeReviewDock` UI
  (diff + impact + Merge / Send to Claude / Reject).
- Engineering playbooks (TDD, systematic-debugging, verification) injected into the agent;
  closed-loop TDD verified red→green. Container `./:/repo:rw` mount. (Full suite **320 pass**.)

### 06/26–06/27/2026 — MLB betting edge engine (Chances Make Champions)
See the dedicated section below. Data-only ingestion (free statsapi + paid Apify odds/Pick6),
EV brain across 5 markets, and the CMC Daily Edge card + downloadable poster.

---

## Betting Agent — Chances Make Champions

**Honest, free-data, +EV MLB tool** integrated into the RAMBO backend. Brand: "Chances
Make Champions" (CMC); ~$10 flat units; data-only (Sentinel boundary — no bet placement).

### Shipped
- **Ingestion (data-only):** free `statsapi.mlb.com` (roster / schedule / stats / team stats)
  + paid Apify (odds `seemuapps/sports-odds-scraper`, DK Pick6 props
  `zen-studio/draftkings-pick6-player-props`) → spend-capped landing → `raw_ingest` →
  per-source normalize → typed tables → read-only `MlbRepo`. STRICT tables, idempotent
  raw, append-only line snapshots, JSON stats. Verified live.
- **EV brain — 5 markets** (`brains/ev/`, market-pluggable `REGISTRY`):
  - **Home Runs / H+R+RBI / Stolen Bases / Strikeouts** — DK Pick6 props. Pick6 EV =
    `P × multiplier − 1`; HR via `1 − (1 − rate)^4.2` (handedness + park), counts via Poisson.
  - **Moneyline** — pitcher-adjusted run model **market-anchored** to the de-vigged book
    (book = prior, clamp to realistic single-game range) → small honest **leans**, not
    fake +EV. Team-stats ingestion + starter ERA.
  - Per-slate Haiku explainer (honest, market-aware; only explains genuine plays).
- **Player Watch board** (`GET /betting/player-watch`): the slate's **top 11 HR threats** —
  our DK Pick6 HR plays ("leans", tagged `[CMC LEAN]`) pinned first, the rest filled from
  confirmed lineups by model HR%. Prop-less scorer `features.build_hr_features_core` +
  `MlbRepo.lineup_batters`; `prep` now pulls hitting stats for every lineup batter.
- **Moneyline Board** (`GET /betting/moneyline-board`): **every** game in **game-time order**
  (book odds + model % per side + lean / no-lean) for mix-and-match. Shared
  `moneyline_model.evaluate_game`; `games.game_datetime` (migration `009`); `ml` output
  re-ordered by first pitch.
- **Key finding (durable):** single DK Pick6 legs are structurally −EV (multipliers carry
  the house margin); a naive heuristic can't beat a sharp moneyline. The tool's value is
  **−EV avoidance + honest leans + line shopping**, not pretending to beat the book.
- **CMC cards + daily run:** web dashboard at `/edge` (moneyline leans lead, props as honest
  −EV skips) + **downloadable poster** at `/card/:market` (`html-to-image` PNG, real
  headshots, procedural textures in `public/cmc/`, branded `plate.png`). One-command daily
  workflow `cmc-daily.ps1` (pull slate → print every slip/board prompt → write
  `CMC_Daily_<date>.docx`). EV brain + boards: ~45 tests.

### Next (betting)
- Prop → game link + team confirmation; Pick6 MLB-only filter on paid pulls.
- Line shopping across books (needs multi-book odds); confidence/CLV tracking.
- True first-pitch ordering is live; consider TZ-localized display times.
- A genuinely backtested predictive moneyline model (the only path to validated edge).

---

## Forward plan

### Short term
- Voice/self-review polish — "Operator, review the auth module" points the dev agent at open changes.
- Full-suite `run_tests` option before a dev-lane merge.
- Operator greeting **+ boot briefing DONE** (`/briefing/boot` card + spoken; "catch me up" skill); shutdown/logout sequence + task-history panel still open.
- Echo channels (push/SMS via Twilio); Keeper recall injected into prompt context.
- Retire remaining stub `execute()` agents or give them real handlers.

### Mid term
- **Alembic migrations** as the SQLite schemas evolve (usage / dispatch / tts / keeper /
  dev_changes / mlb_ingest).
- Persist human-in-the-loop queues (confirmations / handoffs / Sentinel) to SQLite.
- Color presets / theme switcher; modular draggable HUD panels; mission dashboard.
- Morning-brief enrichment (weather w/ stored home, unread-mail summary, Keeper highlights).
- Mobile-responsive HUD.

### Long term
- Secure operator login / authentication; CLI companion (`rambo "<goal>"`).
- Native always-on wake word + true acoustic echo cancellation (barge-in).
- Plugin system; packaging (`@rambo/orb`, Storybook, hook/transition unit tests).
- **North star:** a cloud-hosted personal digital twin that learns the operator and runs
  open-ended research.

---

## Reference

### Endpoints (accumulated)
Core: `POST /rambo/execute` · `GET /agents/status` · `GET /agents/{key}/detail` ·
`GET /agents/health` · `GET /integrations/status` · `GET /system/stats` · `GET /usage` ·
`GET /usage/tts` · `GET /learning/log` · `POST /brief/run` · `GET /greeting` · `GET /briefing/boot`
Memory: `POST|GET /keeper` · `GET /keeper/{key}` · `GET /keeper/confirm`
Factory: `POST /factory/spawn` · `GET /factory/pending` · `GET /factory/task/{id}` (+approve/reject)
Confirm/Handoff: `GET /confirmations` · `GET /handoffs` (+approve/accept/reject)
Dev lane: `POST /dev/propose` · `GET /dev/pending` · `GET /dev/change/{id}` ·
`POST /dev/merge|reject|escalate/{id}`
Builds: `POST /builds/create` · `GET /builds` · `GET /builds/{slug}` ·
`POST /builds/{slug}/test|run` · `DELETE /builds/{slug}` (short auto-named folders; deletable by ✕ or voice)
Git: `GET /git/status` · `POST /git/push` · `POST /git/merge` (local branch) ·
`POST /git/merge-pr` (GitHub PR) — all operator-approved via Confirm dock or voice
("approve the push/merge"); needs `RAMBO_GITHUB_TOKEN` (PR merge also needs Pull requests: write)
Betting: `POST /ingest/run` · `POST /betting/prep` · `GET /betting/daily-edge?market=&date=&threshold=` ·
`GET /betting/slip?market=&date=` · `GET /betting/player-watch?date=` · `GET /betting/moneyline-board?date=` ·
`GET /betting/strikeout-watch?date=` (top-11 starters by P(8+/9+/10+ K) for alt-K parlays)

### Notable env vars
`ANTHROPIC_API_KEY` · `RAMBO_MODEL` · `RAMBO_FAST_MODEL` · `RAMBO_CACHE_TTL` ·
`RAMBO_SELF_KNOWLEDGE` · `ELEVENLABS_API_KEY|VOICE_ID|MODEL|MONTHLY_LIMIT` ·
`SMTP_HOST|PORT|USER|PASS|FROM` · `ECHO_DEFAULT_TO` · `MORNING_BRIEF_TIME|TZ` ·
`RAMBO_REPO_ROOT` · `RAMBO_WORKTREE_DIR` · `RAMBO_DEV_PLAYBOOKS` ·
`APIFY_TOKEN` · `RAMBO_DB_PATH` · `RAMBO_MIGRATIONS_DIR`

### Risks & mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Performance on low-end devices | High | LOD particle reduction, bloom off on mobile, DPR cap, performance mode |
| WebGL 1 compatibility | Medium | Detect support, CSS gradient orb fallback |
| Backend offline on load | Low | Agents default OFFLINE, UI graceful |
| Docker port conflicts | Medium | `Kill-Port` in control panel, `compose stop` before switch |
| In-memory HITL queues reset on restart | Medium | Planned move to SQLite |
| Paid Apify overspend | Medium | `max_total_charge_usd` hard cap + `max_items` |

### Owners
| Area | Owner |
|---|---|
| Design, shaders, presets, brand art | Daniel |
| Implementation, backend, agents, tests | Claude |
| Packaging, Storybook, unit tests | Future contributor |
