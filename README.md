<div align="center">

# R.A.M.B.O

### Responsive Autonomous Multi-Brain Operator

**A multi-agent AI orchestration system with a living, cinematic command-center interface.**

`MK III` · React 19 + Three.js front end · FastAPI multi-agent back end · Dockerized

</div>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [The Agent Roster](#the-agent-roster)
- [The Splash Sequence](#the-splash-sequence)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Quick Start (Docker)](#quick-start-docker)
  - [PowerShell Control Panel](#powershell-control-panel)
  - [Manual / Local Dev](#manual--local-dev)
- [Ports & Endpoints](#ports--endpoints)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Visual System](#visual-system)
- [Roadmap](#roadmap)
- [Changelog](#changelog)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**R.A.M.B.O** (Responsive Autonomous Multi-Brain Operator) is a full-stack
multi-agent system. A central **Overseer** decomposes a goal into tasks,
routes each task to the most suitable specialized **agent**, runs a security
review through a **Sentinel** gate, and synthesizes a final answer — all while
broadcasting live status over WebSocket to a cinematic, sci-fi command-center
front end built around a living plasma orb.

The interface is designed to feel like a piece of fictional hardware booting
up: a three-phase splash sequence (transmission → mission briefing → live
console) carries the user from cold-start into a real-time view of every
agent's status.

---

## Key Features

- **🧠 Multi-agent orchestration** — ten specialist shells **consolidated into 3 routable modes** (Planner / Executor / Researcher) + Keeper/Sentinel/Pilot services, coordinated by an Overseer. See [The Agent Roster](#the-agent-roster).
- **🛡️ Sentinel security gate** — risky actions (engineer / steward / link) are reviewed and can be blocked or held for manual approval.
- **🔌 Live status feed** — REST polling (`/agents/status`) + WebSocket broadcasts (`/ws/activity`) keep the UI in sync in real time.
- **🌌 Cosmic wireframe orb** — custom GLSL shaders (simplex noise displacement, fresnel rim glow, wireframe icosahedron) render the Overseer as a living wireframe nucleus with a billboarded glow halo. Bloom postprocessing for cinematic glow.
- **📊 Persistent HUD** — CPU/RAM/DSK system metrics, LIVE command input, and real-time activity feed visible on every page.
- **🗣️ Voice command system** — wake word **"Operator"** activates listening (browser STT misheard "Rambo"), speech-to-text fills the command input, streaming LLM responses with per-sentence segment emission for low-latency speech. **Reliable mic control** — hard-off button (persisted across refreshes) + soft "stop listening" voice pause that resumes hands-free on the wake word — plus a recognizer watchdog that auto-recovers from STT degradation. Voice commands: "clear everything", "command center", "stop listening", "remember …", "email me …".
- **🔊 ElevenLabs neural voice** — responses are synthesized server-side by ElevenLabs (`tts.py`) and streamed over the activity WebSocket; the orb pulses to R.A.M.B.O's own voice via a Web-Audio AnalyserNode. Degrades cleanly to the browser voice when no key is set. Live **voice-credit tracker** (`/usage/tts`) shows remaining/used against your ElevenLabs balance.
- **🧬 Self-knowledge system** — auto-generated doc from live code registries, refreshed on every commit via pre-commit hook, drift checker catches stale references, slim summary injected into the agent's system prompt.
- **🎭 Personality engine** — cold professional voice powered by Claude, with tonal checkpoints and voice cues to prevent filler language.
- **💰 Cost dashboard** — live tracking of LLM API token usage and cost per call, with always-visible indicator, click-to-expand panel (per-model breakdown, daily trend, cache savings), and `GET /usage` endpoint. Best-effort recording that never breaks conversation flow.
- **🔌 Connected agent backends** — Seeker does **live web search** (Anthropic's native `web_search`, no extra key); Keeper has **durable SQLite memory** (spoken "remember X is Y" / "what is my X" persist and recall across restarts); Link runs **Google OAuth** (calendar/drive); Echo sends **real email** via SMTP. Per-agent health at `GET /agents/health` (LIVE / CONNECTED / OFFLINE) and `GET /integrations/status`.
- **🗓️ Recurring morning brief** — a daily scheduler composes a brief (date + today's Google calendar + doctrine priorities) and both **displays it on screen** as an Architect card and **emails it** via Echo. `POST /brief/run` to trigger on demand; `MORNING_BRIEF_TIME` / `MORNING_BRIEF_TZ` to schedule.
- **⚙️ Settings + sound** — sound on by default (auto-enables on first interaction), with a ⚙ settings popover (Sound On/Off toggle) on every page. Two-tier model split — Haiku for fast routing, Sonnet for voice/agents.
- **🏭 Factory sub-agent spawner** — a meta-agent that mints other agents on demand: it researches a role (web search → structured Skills Report), drafts a spec + system prompt, stages a manifest for human approval, then registers it as a hot-reloadable `dispatch_to_<slug>` agent — no restart, no bespoke class per agent. Every spawned agent is pure config (`ConfigDrivenAgent` runs one generic tool-use loop). Includes a daily spawn cap, reserved-slug guard, prompt-injection sanitization, 3-round revision loop, and a `FactoryDock` approval surface with page-load hydration via `GET /factory/pending`.
- **🛠️ Self-coding lane** — RAMBO can read its own codebase and **write, test, and review changes to its own source** on command — without ever editing the running process. Each self-change happens on an isolated git **worktree** (a throwaway branch, never `main`): the agent drafts the change following engineering playbooks (TDD, systematic debugging, verification), **runs the tests it writes red→green** via a sandboxed `run_tests` tool, then produces a **diff + impact analysis + a recommendation** (merge / escalate-to-Claude / hold). The operator reviews it in the **`CodeReviewDock`** and merges locally on approval — nothing reaches `main` until you say so. Routable `dev` target; `/dev/*` endpoints; the high-risk capability stays isolated from the live process by construction.
- **🧭 Smart orchestration layer** — an LLM router picks the right agent on purpose (decomposes multi-step requests, asks one clarifying question when ambiguous); least-privilege per-agent tool allowlists with bounded loops; failure isolated at every boundary; **human-in-the-loop gates** — tool-level confirmation for risky actions (`ConfirmationDock`) and propose-don't-chain agent handoffs (`HandoffDock`).
- **⚡ Prompt caching** — shared sub-agent loop, conversation history, router, and research all cache their stable prefixes (extended 1h TTL for sparse traffic); verified live with cache-reads far exceeding full-price input.
- **🚀 Seamless startup** — `rambo-startup.ps1` waits for Docker, brings the stack up, waits for the frontend, and opens the browser; register it with Task Scheduler at login for a one-and-done boot.
- **🌠 Agent Constellation** — 10 agent nodes orbiting the orb in 3D with status-driven glow, dispatch beams, and processing helix rings.
- **⚡ Performance adaptive** — auto-detects battery level, tab visibility, and `prefers-reduced-motion` to scale rendering quality.
- **🎬 Two-phase splash sequence** — scripted boot experience with sequential scans, then a live console.
- **🐳 Fully Dockerized** — backend, production frontend, and hot-reload dev frontend orchestrated with Docker Compose.
- **🎛️ PowerShell control panel** — boot animations, health scans, force-rebuild, and one-key browser launch.

---

## Architecture

```
                         ┌──────────────────────────────┐
                         │        Front End (React)      │
                         │   Splash Sequence + Orb (R3F) │
                         └───────────────┬──────────────┘
                  REST /agents/status    │   WS /ws/activity
                                         ▼
                         ┌──────────────────────────────┐
                         │       FastAPI  (main.py)      │
                         └───────────────┬──────────────┘
                                         ▼
                         ┌──────────────────────────────┐
                         │        Orchestrator           │
                         │  plan → queue → route → run   │
                         └───────────────┬──────────────┘
              ┌──────────────────────────┼──────────────────────────┐
              ▼                          ▼                          ▼
        ┌───────────┐             ┌───────────┐              ┌───────────┐
        │ Architect │  ...        │ Sentinel  │  ...         │   Echo    │
        │  (plan)   │             │ (review)  │              │ (respond) │
        └───────────┘             └───────────┘              └───────────┘
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                        SQLite store          Sentinel queue
```

**Request lifecycle**

1. `POST /rambo/execute` with a `goal`.
2. **Architect** creates a step plan.
3. **Pilot** builds a task queue from the plan.
4. Each task is routed (`choose_brain`) to the best agent.
5. Tasks for **engineer / steward / link** pass through the **Sentinel** review gate (`APPROVE` / `REVIEW` / `DENY`).
6. **Echo** summarizes all results into a final response.
7. Every step broadcasts `STATUS:<agent>:<state>` and a human-readable log line over WebSocket.

---

## The Agent Roster

The roster was **consolidated**: the original ten specialist agents collapsed into
**three routable modes** plus **three standalone services**. The ten shells still
exist internally (the dispatch pipeline runs them), but the routing surface — what
the LLM router actually targets — is now six entries, not ten. This kept the
cinematic ten-node identity while making routing decisions sharper and cheaper.

### Before — the original ten (MK I–IV)

| Agent | Role | Responsibility |
|-----------|----------------------|----------------------------------------------------|
| **Architect** | Strategic Planning | Decomposes goals into executable task hierarchies |
| **Engineer** | Code Execution | Generates and executes technical implementations |
| **Seeker** | Intelligence | Researches and retrieves critical information |
| **Analyst** | Data Analysis | Processes patterns and extracts actionable insights |
| **Sentinel** | Security | Reviews all actions for risk and threat assessment |
| **Steward** | Resource Management | Optimizes and manages operational system resources |
| **Link** | Integration | Interfaces with external APIs and data services |
| **Keeper** | Memory | Persists knowledge across operational cycles |
| **Echo** | Communication | Synthesizes and delivers final responses |
| **Pilot** | Task Coordination | Manages the execution queue and agent deployment |

### After — three modes + three services

| Routable target | Type | Owns | Folds in (original shells) |
|-----------------|------|------|----------------------------|
| **Planner** | Mode | Planning, decomposition, specs, and summarizing results | Architect + Echo |
| **Executor** | Mode | Building/implementing code, integrations, budgeting & resource actions | Engineer + Steward + Link |
| **Researcher** | Mode | Searching, finding, looking things up, analyzing/evaluating data | Seeker + Analyst |
| **Keeper** | Service | Storing, recalling, and managing files/memory | Keeper |
| **Sentinel** | Service *(internal)* | Reviews risky actions; not a routable target | Sentinel |
| **Pilot** | Service *(internal)* | Builds the task queue; not a routable target | Pilot |

> The mapping is defined in `orchestrator/orchestrator.py` (`CORE_OWNERSHIP`,
> `_MODE_AGENTS`, `DISPLAY_GROUPS`). The **SmartRouter** (`orchestrator/routing.py`)
> routes over the three modes + Keeper; Sentinel and Pilot run inside the pipeline
> rather than being dispatched to directly.

> **R.A.M.B.O** itself sits above the roster as the **Overseer**.

**Status states:** `online` · `working` · `idle` · `offline` — each color-coded in the UI.
Each consolidated entry aggregates the live status of its underlying shell agents.

**Live agent backends** (as of 06/24/2026 — check `GET /agents/health`):

| Agent | Backend | Status |
|-------|---------|--------|
| **Seeker** | Anthropic native `web_search` + Open-Meteo weather | 🟢 LIVE |
| **Keeper** | SQLite (`data/keeper.db`) — persistent memory, write/read/query/confirm | 🟢 CONNECTED |
| **Link** | Google OAuth (calendar / drive) | 🟢 CONNECTED |
| **Echo** | SMTP email (`echo_messaging.py`) + `notify` skill | 🟢 CONNECTED |

Other agents (Architect, Engineer, Analyst, Steward, Sentinel, Pilot) coordinate planning, review, and queueing; capabilities are delivered through the **skills** layer and the **Factory** spawner.

---

## The Splash Sequence

The front end boots through **two** scripted phases:

| Phase | Name | What it shows |
|-------|---------------------|------------------------------------------------------------------|
| **1** | **Transmission** | The wireframe icosahedron orb (CosmicOrb + bloom + chromatic aberration), R.A.M.B.O title, operator line, a **"BOOTING UP"** status, a single scan bar (0→100%, no loop), and the boot log typing in beneath it. When the log finishes it shows **"NOW BOOTING UP"** and transitions. |
| **2** | **Live Console** | Full wireframe orb with bloom + EM pulse network overlay, R.A.M.B.O title stack, LIVE command input (bottom-left), activity feed (bottom-right), CPU/RAM/DSK stat bars (top-left under BY DANIEL). **Left:** Agent Roster + SYSTEMS nav (Learning Log, Round Table). **Right:** System Parameters. |

Phases auto-advance on a timeline (no click-to-skip). Both share the gold/amber neon scheme on near-black.

---

## Tech Stack

**Front End**
- React 19 + React Scripts (CRA)
- `@react-three/fiber` + `three` (WebGL orb)
- `@react-three/postprocessing` (Bloom)
- Custom GLSL shaders (simplex noise, wireframe icosahedron, fresnel glow)
- `react-router-dom` v7 (SPA routing)

**Back End**
- FastAPI + Uvicorn
- Anthropic Claude SDK (streaming LLM for voice responses)
- Pydantic
- SQLite (memory store)
- WebSocket connection manager
- Self-knowledge system (auto-generated from code registries)

**Infra / Tooling**
- Docker + Docker Compose
- Nginx (production frontend serving)
- PowerShell control panel & sound engine

---

## Project Structure

```
R.A.M.B.O/
├── docker-compose.yml          # backend + prod frontend + dev frontend
├── rambo-control-panel.ps1     # interactive control panel
├── start-dev.ps1               # boot backend + hot-reload dev frontend
├── start-prod.ps1              # boot backend + Nginx prod frontend
│
├── rambo-backend/
│   ├── main.py                 # FastAPI app + routes
│   ├── orchestrator/
│   │   └── orchestrator.py     # plan → queue → route → run → summarize
│   ├── agents/                 # 10 specialist shells (→ 3 routable modes + 3 services)
│   │   ├── architect.py  engineer.py  seeker.py  analyst.py
│   │   ├── sentinel.py   steward.py   link.py    keeper.py
│   │   └── echo.py       pilot.py
│   ├── router/                 # choose_brain task routing
│   ├── models/                 # Task model, router, sqlite store
│   ├── memory/                 # SQLite persistence
│   ├── websocket/              # ConnectionManager (broadcast)
│   ├── personality.py          # system prompt assembly + voice cues
│   ├── skills.py               # skill registry (weather, calendar, drive, chief-of-staff)
│   ├── self_knowledge/         # self-knowledge system
│   │   ├── parser.py           # AUTO block parser (parse/serialize/render)
│   │   ├── renderer.py         # wires generators to blocks
│   │   ├── drift.py            # drift checker for stale references
│   │   ├── cli.py              # CLI: --render, --refresh, --check, --check --strict
│   │   └── generators/         # one per AUTO block (capabilities, subagents, integrations, voice, recent_activity)
│   ├── context/self/rambo.md   # self-knowledge document (auto-refreshed)
│   ├── sentinel_queue.py       # UUID-tracked approval queue
│   ├── agent_tracker.py        # per-agent stats, activity, learnings
│   ├── requirements.txt
│   ├── Dockerfile  Dockerfile.dev
│
├── rambo-frontend/
│   ├── src/
│   │   ├── App.js / App.css          # root component + global CSS vars
│   │   ├── index.js                  # BrowserRouter + all routes
│   │   └── components/
│   │       ├── SplashScreen.js/css   # Phase 1 (boot) + Phase 2 (console)
│   │       ├── CosmicOrb.jsx         # wireframe icosahedron orb (Tier 1)
│   │       ├── CosmicOrbShaders.js   # GLSL: simplex noise + fresnel glow
│   │       ├── RamboOrb3D.jsx        # legacy particle cloud (retained)
│   │       ├── SharedHUD.js/css       # persistent HUD: stat bars, command input, activity feed
│   │       ├── AgentPage.js/css      # per-agent detail pages
│   │       ├── RoundTable.js/css     # council view — orbiting agents
│   │       └── LearningLog.js/css    # system learning log (side-panel layout)
│   ├── public/
│   ├── package.json
│   ├── Dockerfile  Dockerfile.dev
│
├── sounds/                     # control panel / boot audio
└── sound_generator/            # PowerShell sound generation
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Compose v2)
- For manual dev: **Node.js 18+** and **Python 3.11+**
- Windows users: PowerShell 5.1+ for the control panel (optional)

### Quick Start (Docker)

```bash
# from the project root
docker compose up --build rambo-backend rambo-frontend-dev
```

Then open **http://localhost:3001** (dev) — the splash sequence will boot.

For the production build instead:

```bash
docker compose up --build rambo-backend rambo-frontend
# open http://localhost:3000
```

### PowerShell Control Panel

On Windows, the control panel wraps the common workflows with boot animations,
health checks, and a one-key browser launch:

```powershell
.\rambo-control-panel.ps1      # interactive menu (defaults to Dev mode)

.\start-dev.ps1                # backend + hot-reload dev frontend (3001)
.\start-prod.ps1               # backend + Nginx prod frontend (3000)
```

The control panel's **Open Browser** action auto-starts the containers if they
are down before opening the URL.

### Manual / Local Dev

**Back end:**

```bash
cd rambo-backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Front end:**

```bash
cd rambo-frontend
npm install
npm start          # serves on http://localhost:3000
```

> When running the frontend outside Docker on port 3000, the backend CORS
> already allows both `localhost:3000` and `localhost:3001`.

---

## Ports & Endpoints

| Service | Container | URL | Notes |
|------------------------|----------------------|--------------------------|-----------------------------|
| Backend (FastAPI) | `rambo-backend` | http://localhost:8000 | REST + WebSocket |
| Frontend (production) | `rambo-frontend` | http://localhost:3000 | Nginx static build |
| Frontend (dev) | `rambo-frontend-dev` | http://localhost:3001 | Hot reload (volume mounted) |

---

## API Reference

| Method | Path | Body | Description |
|--------|----------------------|--------------------------------|----------------------------------------------|
| `GET` | `/` | — | Health check (`{status: "online"}`) |
| `GET` | `/agents/status` | — | Overseer + all agent statuses |
| `GET` | `/system/stats` | — | Live CPU / RAM / disk metrics (`psutil`) |
| `POST` | `/rambo/execute` | `{ "goal": "..." }` | Run a goal through the full orchestration |
| `GET` | `/agents/{key}/detail`| — | Per-agent stats, activity, budget (Steward) |
| `GET` | `/sentinel/approvals`| — | List tasks awaiting manual approval |
| `POST` | `/sentinel/decision` | `{ "id": "...", "decision": "APPROVE" \| "DENY" }` | Approve or deny a held task |
| `GET` | `/learning/log` | — | System-wide learning entries |
| `GET` | `/usage` | — | Cost dashboard (MTD/today/per-model/daily/cache savings) |
| `GET` | `/usage/tts` | — | ElevenLabs voice-credit usage (local + real balance) |
| `POST` | `/keeper` | `{ "key": "...", "value": "...", "tags": "" }` | Keeper: write/upsert a memory entry |
| `GET` | `/keeper` | `?search=&limit=` | Keeper: query entries |
| `GET` | `/keeper/{key}` | — | Keeper: read one entry |
| `GET` | `/keeper/confirm` | — | Keeper: count + recent entries |
| `GET` | `/agents/health` | — | Per-agent backend status (LIVE / CONNECTED / OFFLINE) |
| `GET` | `/integrations/status` | — | Google / Echo / ElevenLabs / Anthropic status |
| `POST` | `/brief/run` | — | Generate the morning brief now (on-screen + email) |
| `GET` | `/greeting` | — | Jarvis-style boot greeting (spoken) |
| `GET` | `/briefing/boot` | — | Boot briefing: on-screen card + spoken summary (recent changes since last boot, suggested targets, weather, pending, health) |
| `POST` | `/builds/create` | `{ "name": "...", "goal": "..." }` | Build a standalone app (short auto-named folder) |
| `GET` | `/builds` | — | List builds in the dock |
| `DELETE` | `/builds/{slug}` | — | Delete a build (folder + dock record) |
| `GET` | `/git/status` | — | Repo push preview (branch, commits ahead, tracked changes) |
| `POST` | `/git/push` | `{ "message"? }` | Stage a commit+push for approval (Confirm dock or voice) |
| `POST` | `/git/merge` | `{ "source", "target"? }` | Stage a local branch merge for approval |
| `POST` | `/git/merge-pr` | `{ "number", "method"? }` | Stage a GitHub PR merge for approval |
| `GET` | `/google/status` | — | Google OAuth auth state |
| `POST` | `/factory/spawn` | `{ "name_hint": "...", "role_description": "...", "special_requirements": "" }` | Stage a new sub-agent build |
| `GET` | `/factory/pending` | — | All tasks awaiting approval (page-load hydration) |
| `GET` | `/factory/task/{id}` | — | Single spawn-task status + proposed manifest |
| `POST` | `/factory/approve/{id}` | — | Approve a proposed agent → registers `dispatch_to_<slug>` |
| `POST` | `/factory/reject/{id}` | `{ "feedback": "..." \| null }` | Reject (feedback = revise, blank = kill) |
| `GET` | `/factory/agents` | — | List active spawned agents |
| `POST` | `/betting/prep` | `?date=` | Pull + normalize the full MLB slate (data-only; paid Apify) |
| `GET` | `/betting/daily-edge` | `?market=&date=&threshold=` | Ranked picks for one market (+EV only by default) |
| `GET` | `/betting/slip` | `?market=&date=` | Fixed-size slip roster + a ChatGPT image prompt |
| `GET` | `/betting/player-watch` | `?date=` | Top-11 HR board (our leans pinned) + prompt |
| `GET` | `/betting/moneyline-board` | `?date=` | Every game in game-time order (book odds + model %) + prompt |
| `GET` | `/betting/strikeout-watch` | `?date=` | Top-11 probable starters by P(8+/9+/10+ K) + prompt |
| `GET` | `/betting/hits-tb-watch` | `?date=` | Top-11 hitters by P(2+ TB) / P(1+ hit) + prompt |
| `WS` | `/ws/activity` | — | Live activity + `STATUS:<agent>:<state>` feed |

**Example — run a goal:**

```bash
curl -X POST http://localhost:8000/rambo/execute \
  -H "Content-Type: application/json" \
  -d '{"goal": "Build a HUD dashboard for system metrics"}'
```

**Example — status payload:**

```json
{
  "overseer": { "name": "R.A.M.B.O", "role": "Overseer", "status": "online" },
  "agents": [
    { "name": "Architect", "status": "idle" },
    { "name": "Engineer",  "status": "working" }
  ]
}
```

---

## Configuration

| Where | Setting | Default |
|------------------------------|----------------------------------|------------------------|
| `rambo-backend/.env` | `ANTHROPIC_API_KEY` (required for live LLM) — gitignored, auto-loaded on startup | _(none)_ |
| `rambo-backend/.env` | `RAMBO_MODEL` — deep LLM model (voice/agents) | `claude-sonnet-4-6` |
| `rambo-backend/.env` | `RAMBO_FAST_MODEL` — fast LLM model (routing) | `claude-haiku-4-5` |
| `rambo-backend/.env` | `RAMBO_CACHE_TTL` — prompt cache TTL (`1h`/`5m`) | `1h` |
| `rambo-backend/.env` | `ELEVENLABS_API_KEY` — neural voice (optional; falls back to browser voice) | _(none)_ |
| `rambo-backend/.env` | `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL` | _(preset)_ / `eleven_turbo_v2_5` |
| `rambo-backend/.env` | `ELEVENLABS_MONTHLY_LIMIT` — voice-credit limit for the HUD | `10000` |
| `rambo-backend/.env` | `SMTP_HOST/PORT/USER/PASS/FROM`, `ECHO_DEFAULT_TO` — Echo email (optional) | _(none)_ |
| `rambo-backend/.env` | `MORNING_BRIEF_TIME` / `MORNING_BRIEF_TZ` — daily brief schedule | `07:00` / `America/Detroit` |
| `rambo-backend/credentials.json` + `token.json` | Google OAuth (calendar/drive) | _(via `/google/auth`)_ |
| `rambo-backend/main.py` | CORS allowed origins | `localhost:3000`, `localhost:3001` |
| `docker-compose.yml` | Dev frontend host port | `3001 → 3000` |
| `docker-compose.yml` | Prod frontend host port | `3000 → 80` |
| `SplashScreen.js` | Backend URL (status polling) | `http://localhost:8000` |
| `SplashScreen.js` | Timezone (briefing clock) | `America/Detroit` |
| `CosmicOrb.jsx` | `ORB_RADIUS`, `DETAIL` | `1.6`, `18` |
| `CosmicOrbShaders.js` | Noise scale, strength, fresnel power | `1.2`, `0.12`, `1.8` |

---

## Visual System

- **Color scheme:** gold / amber neon (`--accent: #e8b15a`, `--accent-glow: #ffd98a`) on near-black (`#08090b`).
- **Cosmic orb:** wireframe icosahedron (detail 18) with 3D simplex noise displacement, fresnel rim glow, slow two-axis tumble, and mouse parallax. Gold color with a billboarded glow halo (additive blending).
- **GLSL shaders:** layered noise displacement (3 octaves + global breath), fresnel-based rim glow (configurable power/bias), radial gradient glow sprite.
- **Postprocessing:** Bloom (`intensity 0.6`, `radius 0.5`, `threshold 0.7`, `mipmapBlur`). ChromaticAberration removed (06/23/2026) to eliminate screen flickers.
- **Agent Constellation:** 10 orbiting nodes with billboarded glow sprites, canvas-texture labels, tilted orbit ring, status-driven pulse.
- **Dispatch beams:** Dynamic cylinder beams from orb center to orbiting agent nodes during task processing.
- **Processing helix:** 3 tilted golden rings spinning around the orb during active work.
- **Voice:** Wake word **"Operator"**, Web Speech API STT, **ElevenLabs** neural TTS (browser-voice fallback), the orb pulses to R.A.M.B.O's voice, conversational follow-up flow.
- **Performance mode:** Auto-adapts to battery level, tab visibility, `prefers-reduced-motion`.
- **Status colors:** `online #00ff88` · `working #e8b15a` · `idle #8fa0b5` · `offline #5a6575`.

---

## Roadmap

See [`ROADMAP.md`](ROADMAP.md) — the single consolidated roadmap (supersedes all the
dated `ROADMAP_*` files). Highlights:

- **Live now:** cosmic console (6-tier orb), ElevenLabs neural voice, LLM SmartRouter +
  6-tier orchestration, connected agents (Seeker/Keeper/Link/Echo), cost dashboard + prompt
  caching, Factory sub-agent spawner, the **self-coding lane** (RAMBO edits its own code on
  isolated git worktrees, operator-merged), recurring morning brief, and the **MLB betting
  edge engine** (data-only ingestion + 5-market EV brain + the Chances Make Champions card).
- **Short term:** voice/self-review polish, full-suite dev-lane tests, operator greeting +
  shutdown, Echo push/SMS, Keeper recall-in-context.
- **Mid term:** Alembic migrations, persist HITL queues to SQLite, theme presets + modular
  HUD, mobile layout, betting line-shopping/CLV.
- **Long term:** secure login, CLI companion, native wake word + AEC, plugin system,
  cloud-hosted personal digital twin (north-star vision).

---

## Changelog

Running log of splash-screen / UI changes, newest first. Each entry is labeled by area.

### 2026-06-28 — Hits & Total Bases Watch (hits/TB parlay board)
- **[Hits & TB Watch]** New `GET /betting/hits-tb-watch` + `hits_tb_watch` skill ("hits and total bases", "total bases board", "hits parlay") — ranks the day's lineup hitters by **P(2+ total bases)**, each also showing **P(1+ hit)** and projected hits/TB, for hits/total-base SGPs. Same Poisson engine (`build_count_features_core`, group=hitting, vs-hand split + last-15) over `MlbRepo.lineup_batters`. Wired into `cmc-daily.ps1`. 2 tests. Completes the parlay-board set: **Player Watch** (HR), **Strikeout Watch** (K), **Hits & Total Bases** (hits/TB).

### 2026-06-28 — Strikeout Watch (alt-K parlay board)
- **[Strikeout Watch]** New `GET /betting/strikeout-watch` + `strikeout_watch` skill ("strikeout watch", "who's striking out", "strikeout parlay") — ranks the day's **top 11 probable starters by P(9+ strikeouts)**, each with P(8+/9+/10+) and a projected K total, for building alt-strikeout parlays. Poisson on per-start K rate + last-15 (`build_count_features_core` prop-less path, `MlbRepo.probable_starters`); openers/relievers filtered (`RAMBO_K_MIN_STARTS`, default 5) and projections clamped so a low-start reliever can't post a fake 30-K line. Wired into `cmc-daily.ps1`. 2 tests.

### 2026-06-27 — Operator-approved merges (local branch + GitHub PR)
- **[Merge]** Same gated, voice-approvable pattern as push. **Local branch merge** ("merge feature-x into main" → `git_merge` skill / `POST /git/merge`): `--no-ff`, requires a clean tree, aborts cleanly on conflict. **GitHub PR merge** ("merge PR #12" → `pr_merge` skill / `POST /git/merge-pr`): via the GitHub API; needs the PAT's `Pull requests: write`. Approve/deny either with "approve the merge" / "deny the merge" (generalized `resolve_git` skill + router rule). Shared `git_remote.execute_git_confirmation` dispatch; 9 more guardrail tests (conflict abort, dirty refuse, PR 403/405 handling, owner/repo parsing).

### 2026-06-27 — Operator-approved GitHub push
- **[Git push]** RAMBO can commit + push its own repo, **gated behind per-push approval** (Confirm dock or voice: "approve the push" / "deny the push"). New `dev_agent/git_remote.py` (never force-pushes, commits only tracked changes, **secret-scans** the diff, https-github-only, token scrubbed from output); `GET /git/status`, `POST /git/push` (stages a confirmation); `git_push` + `resolve_push` skills + router rule. Needs a fine-grained `RAMBO_GITHUB_TOKEN` (repo-scoped, Contents: read/write); disabled until set. 6 guardrail tests.

### 2026-06-27 — One-click run launchers for builds
- **[Launchers]** Every standalone build now gets a **`run.bat`** (+ `run.sh`) at its root, auto-generated deterministically after the build (points at the detected entry, cd's to its folder, keeps the console open). Double-click to run — no IDLE. (Builder is a Linux container, so a true Windows `.exe` isn't produced there; the launcher is the equivalent.) Backfilled the existing `arithmetic-calculator` build.

### 2026-06-27 — Build names, build deletion, quieter hand-offs
- **[Build names]** Standalone builds now get a **summarized short folder name** (LLM via fast-model + heuristic fallback): "build me a calculator app…" → `calculator`, "build a snake game simulator" → `snake-game` (was `build-a-calculator-app-from-scratch-and-place-it`). Applied in the build lane + `/builds/create`.
- **[Delete builds]** RAMBO can delete builds it made: `builds.delete_build` (folder rmtree + dock record), `DELETE /builds/{slug}`, a `delete_build` skill + router rule ("delete/remove the X build"), and a ✕ button on each Builds-dock card.
- **[Quieter hand-offs]** `_announce_handoff` now speaks/logs only for the **Engineer** (build + dev/self-edit); every other target is dispatched silently — no more "handing this to X."

### 2026-06-27 — Boot briefing + on-demand "catch me up"
- **[Boot briefing]** New `GET /briefing/boot` — at startup RAMBO renders an Architect **card** (recent changes **since last boot**, suggested roadmap targets from ROADMAP/HANDOFF, weather, pending approvals, uncommitted-changes warning, today's calendar, north-star, system health + cost) and speaks a short summary after the greeting. Shared composer `system_briefing.py`; "since last boot" persisted in `data/boot_state.json` (read-only otherwise).
- **[Catch me up]** New `system_update` skill — "give me an update / catch me up / system status / sitrep / where are we" → a concise spoken status. SmartRouter policy rule 17 + roster description so it dispatches instead of clarifying; ordered before `codebase` so file-specific "what changed in X" still routes to `codebase`.
- Reuses existing parts (git reader, weather, greeting clock, pending-parts, calendar, chief-of-staff, usage dashboard); best-effort sections; 14 tests.

### 2026-06-27 — Player Watch + Moneyline Board, daily script, single-instance boot
- **[Player Watch]** New `GET /betting/player-watch` — the slate's **top 11 HR threats**. Our DK Pick6 HR plays ("leans", tagged `[CMC LEAN]`) are pinned first; the rest fill from confirmed lineups by model HR%. New prop-less scorer `features.build_hr_features_core` + `MlbRepo.lineup_batters`; `prep` now pulls hitting stats for **every** lineup batter (free statsapi) so the whole slate can be ranked.
- **[Moneyline Board]** New `GET /betting/moneyline-board` — **every** game in **game-time order** with both book odds, model win % per side, and our lean (or "no lean"), for mix-and-match. Shared `moneyline_model.evaluate_game` (also used by the `ml` market); new `games.game_datetime` column (migration `009`) captured from the schedule, and the existing `ml` output re-ordered by first pitch.
- **[Daily script]** `cmc-daily.ps1` — one command pulls the slate, prints all 5 slips + Player Watch + Moneyline Board prompts, and writes a Consolas-9 `CMC_Daily_<date>.docx` to the repo root (`-SkipPrep` regenerates free; `-Date`, `-Open`). UTF-8-safe fetch.
- **[Startup]** `rambo-startup.ps1` gains a **single-instance lock** (global mutex) so the login Task Scheduler job and the desktop shortcut can't race into two Chrome windows; stale-Chrome cleanup hardened; the desktop shortcut dropped `-Fresh` for a fast open.
- **[Honesty]** Player Watch fills empty visual slots (no pitch-mix/BvP) with real Statcast power + form; optional fields omitted when absent, never faked. 360+ tests pass.

### 2026-06-26/27 — MLB betting edge engine + Chances Make Champions card
- **[Ingestion]** Data-only MLB layer: free `statsapi.mlb.com` (roster/schedule/stats/team stats) + paid Apify (odds, DK Pick6 props) → spend-capped landing → normalize → typed tables → read-only `MlbRepo`. Sentinel boundary by construction (no bet-placement imports).
- **[EV brain]** 5 markets in `brains/ev/` (`REGISTRY`): Home Runs, H+R+RBI, Stolen Bases, Strikeouts (DK Pick6, `P×mult−1`), and Moneyline (pitcher-adjusted run model **market-anchored** to the de-vigged book → honest *leans*, not fake +EV). Per-slate Haiku explainer; 37 tests. `GET /betting/daily-edge?market=&date=&threshold=`.
- **[Honest finding]** Single Pick6 legs are structurally −EV and a heuristic can't beat a sharp moneyline — so the tool leads with −EV avoidance + honest leans rather than manufactured edges.
- **[CMC card]** Web dashboard at `/edge` (moneyline leans lead, props as honest −EV skips) + **downloadable cinematic poster** at `/card/:market` — `html-to-image` PNG export with real MLB headshots, brush fonts (Road Rage / Permanent Marker), procedural smoke/gold/grunge textures (`public/cmc/`, `scripts/gen_cmc_textures.py`), and an auto-detected branded `plate.png` slot for ChatGPT-made art.

### 2026-06-25 — Self-coding lane (RAMBO edits its own code)
- **Dev lane:** new git-isolated `dev_agent/` — RAMBO drafts self-code changes on a throwaway worktree branch (never the running process), produces a **diff + impact + recommendation (merge/escalate/hold)**, and merges locally only on operator approval. Routable `dev` target; `/dev/propose|pending|change|merge|reject|escalate` endpoints; **`CodeReviewDock`** review UI.
- **Closed-loop TDD:** engineering playbooks (TDD / systematic-debugging / verification) injected into the coding agent + a sandboxed **`run_tests`** tool — the agent writes a test, watches it fail, implements, watches it pass.
- **Infra:** writable `/repo` mount + `RAMBO_REPO_ROOT`/`RAMBO_WORKTREE_DIR` so the lane runs in-container; commits use `--no-verify` so the self-knowledge pre-commit hook doesn't pollute review diffs; `pytest` added to the image. New env: `RAMBO_REPO_ROOT`, `RAMBO_WORKTREE_DIR`, `RAMBO_DEV_PLAYBOOKS`, `RAMBO_TEST_CMD`, `RAMBO_TEST_CWD`.

### 2026-06-24 — Real voice, connected agent backends, persistence
- **Voice:** ElevenLabs neural TTS streamed over WS (orb pulses to it; browser-voice fallback); `/console` speaks via ElevenLabs. Wake word → **"Operator"** with fuzzy matching + recognizer watchdog. Reliable mic: hard-off button (persisted) + soft "stop listening" voice pause that resumes on the wake word. Fixed the ElevenLabs-then-browser double voice.
- **Agent backends:** Seeker live web search (Anthropic native), Keeper SQLite persistence (`KeeperRepo`) with spoken remember/recall, Link/Google auth surfacing, Echo SMTP email + `notify` skill. New `/keeper*`, `/usage/tts`, `/agents/health`, `/integrations/status`, `/brief/run`. Routing forces memory→keeper and messaging→echo. Removed dead `memory/sqlite_store.py` stub.
- **Morning brief:** daily scheduler → on-screen Architect card + email.
- **UI/HUD:** version MK V, ElevenLabs credit tracker, cost chips moved top-right + on agent pages, clear-all-responses (button + voice), sound-on-launch + ⚙ settings panel, command-center voice trigger, removed orb dispatch beam + ambient hum.
- **Infra:** persistent dispatch memory (`DispatchRepo`) + fast/deep model split (`RAMBO_FAST_MODEL`).

### 2026-06-23 — Orchestration tiers 4–5, prompt caching, go-live fixes, seamless startup

- **[Orchestration]** Completed the 6-tier model: Tier 1 smart LLM router (`orchestrator/routing.py`), Tier 3 failure isolation hole closed, **Tier 4 tool confirmation gates** (`requires_confirmation` + `factory/confirmations.py` + `/confirmations` endpoints), **Tier 5 handoff system** (`factory/handoff.py`, `propose_handoff` tool, `/handoffs` endpoints — propose-don't-chain).
- **[Frontend]** `ConfirmationDock` + `HandoffDock` (and `FactoryDock`) on all four pages; **mic button redesigned** (glass + gold-ring glow) with a visible red **MIC BLOCKED** state instead of silent failure.
- **[Prompt caching]** Cached the shared sub-agent loop, main conversation history, research loop, and router; `cache_config.py` with extended **1h TTL** for sparse traffic (`RAMBO_CACHE_TTL`). Verified live: cache_read ≫ full-price input.
- **[Go-live fixes]** `.env` auto-load (`env_setup.py`); model id centralized to `claude-sonnet-4-6` (`model_config.py`) after the old one started 404ing; fixed an unawaited `get_final_message()` that silently broke every real turn.
- **[Infra]** Nginx **SPA fallback** (`nginx.conf`) so prod deep links/refreshes don't 404; **`rambo-startup.ps1`** for seamless boot (wait for Docker → compose up → wait for frontend → open browser).

### 2026-06-23 — Factory sub-agent spawner (5 tiers + approval UI)

- **[Factory backend]** New `factory/` package: `repo.py` (3 SQLite tables + state machine), `tool_registry.py` (`ToolRegistry` with `factory_allowed` gating, 5 starter tools), `research.py` (Tier 1 web-search loop with forced structured emit + 24h cache), `spec_writer.py` + `sanitize.py` (Tier 2 spec markdown + prompt gen with injection guards), `pipeline.py` (Tier 3 state machine), `approval.py` (Tier 4 approve/reject/revise), `config_agent.py` + `registry_watcher.py` (Tier 5 generic runtime + 30s hot-reload).
- **[Factory API]** `POST /factory/spawn`, `GET /factory/pending` (page-load hydration), `GET /factory/task/{id}`, `POST /factory/approve/{id}`, `POST /factory/reject/{id}`, `GET /factory/agents`. Strong refs held on in-flight pipeline tasks to prevent GC.
- **[FactoryDock]** New `useFactoryPending` hook + `FactoryDock` component in SharedHUD — collapsible dock listing pending agents as cards keyed by task_id, each with Approve / Reject / Revise (with feedback) actions. Mounted on Round Table.
- **[Safety]** Daily spawn cap (5/day), 13 reserved slugs, slug-uniqueness guard, prompt-injection sanitization, 3-round revision cap, full audit trail via `created_by_task_id`.
- **[Tests]** 54 new backend tests, 149/149 total passing. Frontend production build clean.

### 2026-06-23 06:30 ET — Shared HUD, Learning Log redesign, flicker fix, ChromaticAberration removal

- **[SharedHUD]** Created `SharedHUD.js/css` — extracted reusable `StatBars` (CPU/RAM/DSK), `ActivityFeed`, `CommandInput` components and `useSystemStats`/`useActivityFeed` hooks. All four are now present on every page (Splash, Agent, Learning Log, Round Table).
- **[Stat bars restored]** CPU/RAM/DSK metric bars added to top-left under "BY DANIEL" on all pages. Previously lost when the splash footer was removed.
- **[Learning Log redesign]** Complete rewrite: removed scrollable center layout, now `height: 100vh; overflow: hidden`. Left panel (System Identity + Operational Learning), right panel (Recent Learnings). SVG bezier branch lines connecting orb edge to panels. Agent quick-switch nav bar added.
- **[Text readability]** Boosted dim text opacity on agent pages (role, description, objectives, param keys) with dark text-shadow for contrast against the bright orb.
- **[Activity feed]** Relocated from bottom-center to fixed bottom-right to stop overlapping "TAP OR SAY RAMBO" mic hint.
- **[Command input]** Relocated to fixed bottom-left, no longer overlapping the orb.
- **[ChromaticAberration removed]** Stripped from all 4 pages as a flicker test. The RGB color fringing effect was a suspected source of persistent screen flickers.
- **[Flicker mitigations]** Hoisted per-render `new Vector2()` allocations to stable constants. Removed infinite float animations on `backdrop-filter` panels. Added `will-change: contents` on orb canvases, `powerPreference: 'high-performance'` and `stencil: false` on all WebGL contexts.
- **[Route fix]** Fixed Learning Log route mismatch: AgentPage navigated to `/learning-log` but route was `/learning`.

### 2026-06-22 19:30 ET — Tiers 5+6, agent page redesign, voice on all pages

- **[Tier 5 · Dispatch & Docking]** Dynamic dispatch beams from orb center to orbiting agent nodes (cylinder geometry, additive blending, tracks orbit position). Processing helix: 3 tilted golden rings spin around orb during active work.
- **[Tier 6 · Wire to Reality]** All dispatch animations driven by real WebSocket STATUS events and agent log lines. Performance mode auto-detects battery (<20%), tab visibility, `prefers-reduced-motion`.
- **[Agent pages · redesign]** Stripped all middle UI (info cards, stat cards, objectives, activity feed, budget planner, sentinel queue). Orb is now fully visible full-screen. Floating status badge shows agent state.
- **[Voice · all pages]** Mic + volume controls on every page (Agent, Learning Log, Round Table). Voice commands execute against the backend and results shown in a Command Log panel (bottom-left). Auto-start mic in IDLE mode.
- **[Voice · natural]** TTS tuned for natural speech (rate 1.0, pitch 1.05, prefers natural/female voices).
- **[Constellation · Round Table]** Agent Constellation added to Round Table canvas.
- **[Neon]** Date/time/council view pulse with neon gold glow animation on all pages. Round Table subtitle text changed to neon white.
- **[Alignment]** Agent page titles absolutely centered in topbar.

### 2026-06-22 17:00 ET — Tiers 3+4, wake word, TTS, constellation, neon styling

- **[Tier 3 · Voice]** Wake word "Rambo" activates listening. Speech-to-text fills command input, auto-executes on silence (1.5s). TTS reads response aloud. Conversational follow-up: after responding, asks "Is there anything else?" and stays in LISTENING mode.
- **[Tier 4 · Constellation]** 10 agent nodes orbiting the orb in 3D. Billboarded glow sprites with agent colors, canvas-texture labels, tilted orbit ring, connection lines. Status-driven pulse.
- **[Audio]** Hum volume reduced 70% (gain 0.02→0.006, LFO 0.006→0.001).
- **[Fix]** Cortisol→Echo in constellation. Auto-start mic on Phase 2 load.
- **[Neon]** Agent titles in agent color with neon glow. Gold neon council/date/time on all pages. White visible orb center labels.

### 2026-06-22 14:15 ET — Tier 2 cosmos, orb consistency, bloom/flicker fix

- **[Tier 2 · Cosmos]** Twinkling starfield (500 pts), FBM nebula clouds (warm amber→cool violet), distant node web (24 pulsing nodes + connections), warm glow pool behind orb.
- **[Orb fix]** Root cause of orb missing on sub-pages: `useRef({ current: 0 })` → `useRef(0)`. Three.js crashed silently on object-typed uniform.
- **[Bloom]** Threshold raised 0.15→0.55, intensity reduced 1.4→0.8, radius 0.8→0.6 to eliminate wash-out and black flickers.

### 2026-06-22 — Cosmic wireframe orb (Tier 1), unified orb across all pages

- **[Orb · CosmicOrb]** Replaced the particle cloud `RamboOrb3D` with a new **wireframe icosahedron** (`CosmicOrb.jsx`) across **all pages**: Phase 1 boot, Phase 2 console, Agent pages, Round Table, and Learning Log. The new orb uses IcosahedronGeometry (detail 18), 3D simplex noise vertex displacement (3 octaves + breathing), fresnel rim glow (gold `#e8b15a`), wireframe mode with additive blending, and slow two-axis tumble with mouse parallax.
- **[Orb · GlowHalo]** Soft glow halo rendered as a **billboarded plane sprite** (always faces camera) with a radial gradient shader and additive blending. Eliminates the black-square artifacts caused by the previous 3D mesh shell approach.
- **[Orb · Shaders]** New `CosmicOrbShaders.js` with compact 3D simplex noise (Ashima/Gustavson), layered noise displacement vertex shader, and fresnel-based fragment shaders for both the wireframe and the glow.
- **[Fix · black squares]** Fixed persistent black square artifacts that appeared on the orb and across the screen. Root cause: the `GlowShell` was a low-detail icosahedron with `BackSide` rendering that created visible dark face patches. Replaced with a depth-test-free billboarded plane with purely additive blending.

### 2026-06-22 — Response controls, Round Table, SYSTEMS nav, Phase 2 backgrounds

- **[Phase 2 · responses]** Inline response panels now have **minimize** (▬) and **dismiss** (✕) buttons. Clicking inside a response no longer navigates to the agent page. Responses stay until dismissed or replaced by a new execution.
- **[Phase 2 · SYSTEMS nav]** Added a **SYSTEMS** section header below Agent Roster with links to **Learning Log** and **Round Table**.
- **[Navigation · Command Center]** The "← COMMAND CENTER" button on all sub-pages now navigates to `/console` which loads Phase 2 directly (skips the Phase 1 boot intro). New `skipIntro` prop on SplashScreen.
- **[Navigation · Council View]** Renamed to accent-gold color scheme, now links to the new **Round Table** page at `/council`.
- **[Round Table]** New `/council` page — full-screen Phase 2 orb with all 10 agents orbiting around it as clickable nodes. Each node shows the agent's avatar, color, name label, and live status dot. Connection lines radiate from the core to each agent. Click any node to enter that agent's detail page.
- **[Agent pages · background]** All agent detail pages now use the **full-screen Phase 2 orb** (with Bloom + ChromaticAberration + mouse parallax) as the background instead of a static gradient.
- **[Learning Log · background]** Same full-screen orb background treatment. Council View link color updated to accent gold.

### 2026-06-22 — Per-agent detail pages + learning log + Sentinel approvals + Steward budget

- **[Frontend · routing]** Added React Router — `SplashScreen` at `/`, per-agent pages at `/agent/:key`, learning log at `/learning`.
- **[Frontend · AgentPage]** Each of the 10 agents now has a dedicated page: R.A.M.B.O plasma orb hero with agent avatar overlay, unique agent color, 3 stat cards (tasks completed, pending, success rate), core objectives with progress bars, and recent activity feed.
- **[Frontend · Sentinel]** Sentinel page includes a live **approval queue** — review, approve, or deny pending agent operations directly from the UI.
- **[Frontend · Steward]** Steward page includes a **budget planner** table with categories, budgeted/spent/remaining columns, and visual progress bars.
- **[Frontend · LearningLog]** New `/learning` page showing a running record of patterns, corrections, and adaptations captured across all agent operations.
- **[Frontend · navigation]** Clicking any agent in the Phase 2 roster now navigates to that agent's detail page (was a no-op placeholder).
- **[Backend · agent_tracker]** New `agent_tracker.py` module tracks per-agent task stats, recent activity, and learning entries in memory. Wired into the orchestrator for both skill and pipeline execution paths.
- **[Backend · endpoints]** New `GET /agents/{key}/detail` (per-agent stats + activity + budget for Steward), `GET /learning/log` (system-wide learning entries).
- **[Backend · sentinel_queue]** Upgraded from stub to functional queue with UUID-tracked approvals, pending/decided states, and history.

### 2026-06-22 — Full-screen Phase 1 orb + neon clock

- **[Phase 1 · orb]** Promoted the orb to a **full-screen** canvas, identical in size and look to the Phase 2 orb (same camera + bloom). Removed the contained `RamboEmblem` box.
- **[Phase 1 · layout]** All loading text (title, operator, system label, standby, BOOTING UP, scan bar, boot log) is now **housed centered over the orb** via `.tx-content-overlay`.
- **[Phase 2 · clock]** Top-right clock is now **neon gold** (`.neon-clock`) and **shows seconds** (`HH:MM:SS`), ticking every second.

### 2026-06-22 — Functional console: live backend, real stats, a11y, mobile, audio

- **[Backend · WS fix]** Fixed the activity feed: the orchestrator and the `/ws/activity` endpoint now share **one** `ConnectionManager` (previously two separate instances, so broadcasts never reached clients). Added a real `connect()` (with `await websocket.accept()`) / `disconnect()`.
- **[Backend · stats]** New `GET /system/stats` (CPU / RAM / disk via `psutil`) and a `GET /` health route (also fixes the Docker healthcheck). Added `psutil` + `websockets` to requirements.
- **[Frontend · functional]** New **command console** (replaces the decorative dock): a directive input wired to `POST /rambo/execute` and a live activity feed wired to the `/ws/activity` WebSocket (auto-reconnect). Type a goal → agent status dots flip to **working** in real time (live `STATUS:<name>:<state>` overrides) → log lines stream in. A `● LIVE / ○ OFFLINE` indicator shows backend connectivity.
- **[Frontend · real stats]** Stat bars now show real CPU / RAM / DISK from `/system/stats` (was hardcoded CPU/RAM/GPU/VRAM/DSK); em-dash when the backend is unreachable.
- **[A11y]** `prefers-reduced-motion` honored — typewriters reveal instantly, animations/transitions disabled via media query. ARIA labels on the command input + connection indicator. Lightened the `idle`/`offline` status colors for readable contrast.
- **[Mobile]** `PARTICLE_COUNT` 4000→1800 under 768px, Bloom `mipmapBlur` off on mobile, canvas `dpr` capped at 1.5.
- **[Audio]** Boot chime on the Phase 1→2 transition + a low ambient hum (synthesized via Web Audio, no asset files). Audio context resumes on first user gesture (browser autoplay policy).

### 2026-06-22 — Response branches from its agent (draggable) + clickable agents

- **[Phase 2 · result branch]** The response now **branches out from the agent that produced it** — a connector line runs from that agent's roster row to a panel showing the answer (tree-style). Backend `/rambo/execute` now returns `{response, agent}` so the UI knows which agent to anchor to.
- **[Phase 2 · draggable]** The response panel is **draggable** (grab the header) and closes via ✕ / Esc.
- **[Phase 2 · clickable agents]** Every agent row is now clickable (hover highlight + cursor) with an `onAgentClick` hook — placeholder for the future per-agent pages/phases.

### 2026-06-22 — Real skills (weather), result popup, location, WORKING pulse

- **[Backend · skills]** New scalable **skill layer** (`skills.py`): a registry of matchers + async runners that can call real services. First skill: **weather** via Open-Meteo (no API key) — "what's the weather in Detroit" geocodes the city (or uses the operator's location) and returns live conditions. Orchestrator checks skills first; the matched agent flips WORKING → runs → IDLE.
- **[Backend · location]** `POST /rambo/execute` now accepts `lat`/`lon`; passed to skills as context.
- **[Frontend · location]** Console requests browser geolocation (once, with permission) and sends it with each directive.
- **[Frontend · result popup]** Executing a directive now opens a **pop-up window** with the response (Esc / click-away / ✕ to close).
- **[Frontend · WORKING pulse]** Agent status dots now **pulse** while `working`, so the IDLE → WORKING → IDLE flip is clearly visible.
- **[Note]** Agents remain rule-based stubs; genuinely open-ended "self-learning" answers need a real LLM wired into the orchestrator (a follow-up — needs an API key as an env var).

### 2026-06-22 — EM pulses replace the lines

- **[Phase 2 · web]** Removed the radiating filament lines (too busy). Replaced with **small circular EM pulses** — scattered glowing synapse dots that emit expanding ripple rings (HTML/CSS so they stay perfectly round on any aspect), like cells firing bioelectric signals.

### 2026-06-22 — Fix Task crash, agent responses, contacting, neuron web

- **[Backend · fix]** Fixed `TypeError: Task.__init__() got an unexpected keyword argument 'id'` — the `Task` model now accepts `id`, `assigned_to`, `status`, `metadata` (Pilot was passing them). `POST /rambo/execute` no longer 500s.
- **[Backend · messaging]** Orchestrator now broadcasts structured JSON: `{t:"contact",agent}` (+ a "Contacting X agent to finish the job." log line) when a task is routed, and `{t:"response",agent,text}` with each agent's output (and Echo's final summary).
- **[Phase 2 · responses]** Each agent's reply now opens a **response panel that extends from that agent** in the roster (connector arm + bordered body with the text). "Contacting X agent…" shows in the live feed.
- **[Phase 2 · neuron web]** Reworked the orb web into a **brain-neuron net**: branching dendrites, depth (near/foreground neurons are thicker, brighter, bloom more — fake 3D), and several filaments now **extend past the screen edges**. EM surges + pulsing retained.

### 2026-06-22 — Lightspeed warp intro, typing fix, gold transition

- **[Phase 1 · warp]** Removed the vortex; replaced with a **lightspeed particle warp** — a canvas of gold star streaks accelerating outward from the centre (hyperspace-style), in the project's gold scheme. Fades out when the timeline clears it.
- **[Phase 1 · timing]** The transition now holds ~1.9s after **"CONNECTION ESTABLISHED"** shows, so it's fully readable before advancing (was cut off).
- **[Phase 1 · typing]** Removed the boot-log slide-in animation — boot lines now type in char-by-char (matching Phase 2) instead of sliding.
- **[Transition]** Added an on-theme **gold flash** during the Phase 1→2 transition (instead of a plain fade-through-black).

### 2026-06-22 — Vortex v4 (fiery spiral), audio-synced Phase 1, pulsing web

- **[Phase 1 · vortex v4]** Recolored the vortex to a fiery red/orange/magenta spiral with a hot white core (per the new reference). It now **spins continuously** (no fixed end) and fades out when the timeline clears it.
- **[Phase 1 · audio sync]** The whole Phase 1 (vortex → boot → completion) is now driven by the intro sound's length: attempts autoplay, **retries on the first user gesture** (so the sound is actually heard), and falls back after 4.5s so it never gets stuck. Beats are scheduled as fractions of the clip so the sequence ends as the audio ends.
- **[Phase 1 · labels]** Brought back **"> NOW BOOTING UP"** above **"> CONNECTION ESTABLISHED"** — both show at the end.
- **[Phase 1 · audio]** Removed the keyboard key-click sound from Phase 1's boot log (Phase 2 typing still clicks).
- **[Phase 2 · orb web]** Filaments now **pulsate** (breathing opacity) and carry **electromagnetic surges** — a bright dash travels outward along each line (`stroke-dashoffset`), with pulsing nodes. Each line/node has randomized timing for an organic, living feel.

- **[Phase 2 · orb web]** Added an SVG **filament web** radiating from the orb out across the screen (procedural, seeded). ~12 anchored lines connect to the UI zones — top-left brand, top-right clock, Agent Roster (left), System Parameters (right), and the command line (bottom) — plus ~24 decorative filaments in all directions, each ending in a glowing node. Layered above the orb but below the panels/text, so the plasma sphere is untouched and lines read as connecting into each panel. Fades in with the console.

### 2026-06-22 — Vortex v3 (magenta nebula), 11s gated Phase 1 intro

- **[Phase 1 · vortex v3]** Replaced the spoke wormhole with a **soft magenta nebula swirl** (blurred conic "arms" rotating around a glowing white-pink core on deep purple), matching the reference image. Duration is driven by the new intro sound (~11s).
- **[Audio · intro]** Swapped the intro sound to `intro.mp3` (futuristic HUD), used for the vortex. Removed `void-portal.mp3`.
- **[Phase 1 · gated sequence]** Restructured: **vortex (11s) → upper text fades in → then** the %bar + boot log type in (char-by-char, Phase-2 style, with key clicks). Nothing below the upper text starts until the vortex finishes.
- **[Phase 1 · label]** The completion line is now **"> CONNECTION ESTABLISHED"** (was "ACCESS APPROVED"); the access-approved voice was dropped from the flow (file kept for future use).

### 2026-06-22 — New access voice, synth keystrokes, true typing, vortex v2

- **[Audio · access]** Swapped in the new `access-approved.mp3`; transition to Phase 2 waits for the clip to finish (length read at runtime).
- **[Audio · keystrokes]** Removed the keyboard-loop mp3. Replaced with a **synthesized per-keystroke click** (`playKeyClick`, a short band-passed noise burst, throttled) fired once per character typed (and per boot-log line).
- **[Typing · feel]** Text now reads as *typed*, not slid: removed the row slide-in transform, added a blinking caret to every typing field (roster names, param keys, center title), and roles/descriptions/values now appear only **after** their name/key finishes typing.
- **[Phase 1 · vortex v2]** Reworked the intro into a swirling wormhole — three counter-rotating spiral arms that spin up from the center and zoom outward, then fade to reveal the screen (duration still matched to the portal sfx). *(Couldn't view the referenced YouTube short directly — this is an interpretation; easy to tune.)*

### 2026-06-22 — "Access approved" gate before Phase 2

- **[Phase 1 · access]** After the boot sequence completes, an **"Access approved"** robot-voice clip (`public/sounds/access-approved.mp3`) plays, and the transition to Phase 2 now waits for the clip to finish (length read at runtime). A green pulsing **"> ACCESS APPROVED"** line shows on screen alongside it so the beat lands even when audio is muted/locked.

### 2026-06-22 — Real sound files, vortex intro, sound toggle, agent reset

- **[Audio · files]** Added two sound files under `public/sounds/`: `void-portal.mp3` (Phase 1 intro) and `keyboard-typing.mp3` (typewriter loop). Engine now manages HTMLAudio files alongside the synth hum, with a persisted mute flag.
- **[Phase 1 · vortex]** New intro: a vortex that opens from the center outward (expanding disc + spinning gold sweep), with its duration **matched to the void-portal sound's length** (read at runtime). The portal sfx plays with it.
- **[Typewriter · sound]** The keyboard-typing loop plays during the typewriter cascades — Phase 1 boot log and the Phase 2 reveal — and stops when each finishes.
- **[Phase 2 · agent reset]** When the feed shows a completion (`[Agent] Finished:` / `Response ready`), that agent's dot returns to **Idle** (front-end safety on top of the backend's `STATUS:…:idle` broadcast).
- **[Audio · toggle]** Added a 🔊/🔇 **sound toggle** (bottom-right). Clicking it both flips mute (persisted) and serves as the user gesture that unlocks audio.

### 2026-06-22 — Audio: smoother, quieter, gesture-aware start

- **[Audio · mix]** Global master gain at 0.5 (~50%). Hum reworked into a warm low pad (A2 + E3 sines through a lowpass with a slow ~12s swell LFO) instead of the buzzy static drone, at a much lower base gain (~0.02). Chime softened to a gentle G–C–E triad with slow attack/long tail.
- **[Audio · start]** Instead of firing the chime at the gesture-less auto-transition (where the browser blocks it and it's lost), audio now starts at the FIRST moment it's both unlocked by a user gesture AND on the console. Listens for pointerdown/keydown/touchstart/click. (True zero-interaction autoplay is not possible — browsers require a user gesture to start an AudioContext.)

### 2026-06-22 — Fix compile error (dead orb code)

- **[Build fix]** Removed leftover dead code in `RamboOrb3D.jsx` that broke the build: `RamboOrbSpokes` referenced an undefined `SPOKE_COUNT` (`no-undef` error), plus unused `EquatorialRing`, `SHOW_RINGS`/`SHOW_SPOKES`, and their geometry builders. Also fixed a `react/jsx-no-comment-textnodes` warning (the `//` placeholder in the command feed).

### 2026-06-22 — Tightened intro pacing

- **[Pacing]** Dialed the reveal back down after it dragged: `CHAR_SPEED` 26→20, `SECTION_GAP` 560→340, `INITIAL_DELAY` 1550→1100, `ITEM_GAP` 80→70. Also shortened the `glitch-in` settle from 1.4s→1.0s so the shorter initial delay still lands after the panels settle. Roster now starts ~2.1s in (was ~3s), and the whole cascade is ~25% faster per character — still slower than the original 15ms.

### 2026-06-22 — Typewriter pacing + settle timing + topbar

- **[Pacing]** Slower per-character speed (15→26ms) and a longer pause between sections (560ms vs 80ms between rows within a section).
- **[Settle fix]** The cascade now waits `INITIAL_DELAY` (1550ms) so the panels' `glitch-in` slide-into-place finishes *before* any typing starts — fixes the "panel shifts, then types" overlap.
- **[Topbar]** The top-left brand mark and top-right clock now type in too, as the first section of the cascade. The clock snapshots a fresh time when it starts typing, then hands off to the live ticking value; the SYSTEM/LOGS tabs fade in after the brand finishes.

### 2026-06-22 — Sequenced typewriter reveal across the console

- **[Phase 2 · sequence]** Replaced the parallel row stagger with a single **top-down typewriter cascade**: Agent Roster (headline → each agent, top-down) → System Parameters (each row, top-down) → center orb title (PROJECT label → R.A.M.B.O → operator subtitle). One shared timeline (`buildReveal`) computes each item's start from the cumulative length of everything before it.
- **[Mechanics]** Added `useDelayedTypewriter` (waits, then types char-by-char) and `useRevealAt` (fades a row in at its turn). Roster agent **names** and parameter **keys** type out; roles/descriptions/values fade in alongside. Live status values are not retyped when they change.
- **[Center title]** R.A.M.B.O title stack now types in last (removed its glitch-in so the typewriter is the entrance).

### 2026-06-22 — Roadmap: postprocessing + entrance animations

- **[Orb · postprocessing]** Added **chromatic aberration** (`ChromaticAberration`, offset `0.0012`) alongside Bloom on both orb composers — subtle color fringe on orb edges.
- **[Phase 2 · headline]** Added a **typewriter** reveal on the "System Online" headline (30ms/char, fires on the phase transition) with a blinking green caret.
- **[Phase 2 · roster]** Agent rows now **slide in staggered** (40ms offset per row) when the console appears.
- **[Roadmap note]** "Phase 1 emblem spin-up (`.tx-emblem-svg`)" is **obsolete** — the emblem SVG was removed when Phase 1 switched to the live orb, so there is no tick ring to spin up. The orb's particle rotation + phase fade-in already cover the entrance feel.

### 2026-06-22 — Organic orb + panel polish

- **[Orb · particles]** Softened the hard circular edge. Particle distribution changed from a thin shell (0.72R→1.0R) to a volumetric body (0.45R→1.0R) plus a sparse cubed-falloff tail (~1.45R). Affects both phases (shared orb).
- **[Orb · shader]** Added a radial alpha fade (`smoothstep(1.7, 2.7)`) so the outer cloud dissolves into wisps, and a tangential swirl + radial breath so it churns like plasma instead of a rigid shell.
- **[Phase 2 · labels]** Underlined the **AGENT ROSTER** and **SYSTEM PARAMETERS** table headers.
- **[Phase 2 · cleanup]** Removed the dashed network-web overlay (lines + node dots) entirely.

### 2026-06-22 — Phase 1 orb square fix

- **[Phase 1 · orb]** Removed the visible square around the Phase 1 orb. It was the WebGL canvas edge clipping the orb's radial glow. Fixed with a radial `mask-image` on `.tx-plasma-big` that fades the canvas edges to transparent (box bumped 480→520px for fade room).

### 2026-06-22 — Splash consolidated to 2 phases + Phase 1 orb

- **[Phase count]** Reduced from 3 phases to 2. Deleted the standalone Mission Briefing (old Phase 2); its panels were folded into the live console. Phase state is now `transmission → main`.
- **[Phase 1 · orb]** Replaced the flat plasma billboard with the **exact orb from Phase 2** (`RamboOrb3D` — particles + plasma core + bloom), contained in the emblem slot, **without** the network-web overlay.
- **[Phase 1 · boot log]** Moved the 8-line boot log under the scan bar; it types in line-by-line.
- **[Phase 1 · status]** Added a pulsing **"● BOOTING UP"** indicator (relabeled from "ONLINE").
- **[Phase 1 · sequence]** Single scan bar fills 0→100% once (loop bug fixed at the source — stable `useCallback` advance + ref'd callback). After the log's last line, a highlighted **"> NOW BOOTING UP"** appears, then it transitions.
- **[Phase 1 · roster]** Removed the agent roster from Phase 1 entirely.
- **[Phase 2 · left]** Added the **Agent Roster** table — names, roles, descriptions, and live ONLINE/IDLE status — framed as a bordered table, with bumped font sizes for 80%-zoom readability.
- **[Phase 2 · right]** Added the **System Parameters** table (replacing the old status panel), rendered as a bordered key/value table.
- **[Phase 1 · text]** Bumped all Phase-1 text +2px; operator line promoted from SVG micro-text to readable HTML.
- **[Cleanup]** Removed `BriefingScreen`, `AgentStatusPanel`, `MiniPlasma`/`MiniPlasmaScene`, `useLiveClock`, and now-unused imports (`THREE`, `useFrame`, `useMemo`, plasma shaders).

### 2026-06-21 — Initial three-phase splash + repo

- **[Repo]** Initialized git, README, `.gitignore`, `LICENSE`, `.gitattributes`; pushed to GitHub (private).
- **[Backend]** Renamed `brains/` → `agents/`; added `/agents/status` + live WebSocket status broadcasts.
- **[Orb]** Plasma nucleus shader, billboarded core, synced breathing, cursor parallax, single equatorial ring, bloom.

---

## Troubleshooting

| Symptom | Fix |
|------------------------------------------------|-----------------------------------------------------------|
| Dev container ignores constant-level edits | Webpack HMR limitation in Docker — full restart via `.\start-dev.ps1`. |
| Agents all show `OFFLINE` | Backend not reachable — confirm `rambo-backend` is up on `:8000`. |
| Port already in use | Use the control panel's **Kill-Port**, or `docker compose down`. |
| Both frontends fighting for a port | Run only one mode at a time; the start scripts stop the other container first. |
| CORS errors in console | Ensure you're on `:3000` or `:3001` (both are allow-listed). |

---

## Contributing

1. Fork & branch from `main`.
2. Keep the gold/neon visual language consistent.
3. Run both frontends through the splash sequence before opening a PR.
4. Describe agent/orchestration changes clearly — they affect the live status contract.

---

## License

Released under the [MIT License](LICENSE).

<div align="center">

**R.A.M.B.O — Responsive Autonomous Multi-Brain Operator**
Built by **Daniel**

</div>
