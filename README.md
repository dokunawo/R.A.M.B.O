<div align="center">

# R.A.M.B.O

### Responsive Autonomous Multi-Brain Operator

**A multi-agent AI orchestration system with a living, cinematic command-center interface.**

`MK III` · React + Three.js front end · FastAPI multi-agent back end · Dockerized

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

- **🧠 Multi-agent orchestration** — 10 specialized agents coordinated by an Overseer.
- **🛡️ Sentinel security gate** — risky actions (engineer / steward / link) are reviewed and can be blocked or held for manual approval.
- **🔌 Live status feed** — REST polling (`/agents/status`) + WebSocket broadcasts (`/ws/activity`) keep the UI in sync in real time.
- **🌌 Living plasma orb** — custom GLSL shaders (fbm noise, breathing pulse, additive bloom) render the Overseer as a living nucleus.
- **🎬 Three-phase splash sequence** — scripted boot experience with sequential scans, mission briefing, and a live console.
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

> **R.A.M.B.O** itself sits above the roster as the **Overseer**.

**Status states:** `online` · `working` · `idle` · `offline` — each color-coded in the UI.

---

## The Splash Sequence

The front end boots through **two** scripted phases:

| Phase | Name | What it shows |
|-------|---------------------|------------------------------------------------------------------|
| **1** | **Transmission** | The living orb (particles + plasma core + bloom), R.A.M.B.O title, operator line, a **"BOOTING UP"** status, a single scan bar (0→100%, no loop), and the boot log typing in beneath it. When the log finishes it shows **"NOW BOOTING UP"** and transitions. |
| **2** | **Live Console** | Full plasma orb with bloom + interconnecting network-web overlay, R.A.M.B.O title stack, dock, and system stat bars. **Left:** Agent Roster table (names, roles, descriptions, live status). **Right:** System Parameters table. |

Phases auto-advance on a timeline (no click-to-skip). Both share the gold/amber neon scheme on near-black.

---

## Tech Stack

**Front End**
- React 19 + React Scripts (CRA)
- `@react-three/fiber` + `three` (WebGL orb)
- `@react-three/postprocessing` (Bloom)
- Custom GLSL shaders (plasma, particles)
- `react-router-dom`

**Back End**
- FastAPI + Uvicorn
- Pydantic
- SQLite (memory store)
- WebSocket connection manager

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
│   ├── agents/                 # 10 specialized agents
│   │   ├── architect.py  engineer.py  seeker.py  analyst.py
│   │   ├── sentinel.py   steward.py   link.py    keeper.py
│   │   └── echo.py       pilot.py
│   ├── router/                 # choose_brain task routing
│   ├── models/                 # Task model, router, sqlite store
│   ├── memory/                 # SQLite persistence
│   ├── websocket/              # ConnectionManager (broadcast)
│   ├── sentinel_queue.py       # manual approval queue
│   ├── requirements.txt
│   ├── Dockerfile  Dockerfile.dev
│
├── rambo-frontend/
│   ├── src/
│   │   ├── App.js
│   │   └── components/
│   │       ├── SplashScreen.js      # three-phase sequence + console
│   │       ├── SplashScreen.css
│   │       ├── RamboOrb3D.jsx        # particle cloud + plasma core
│   │       ├── RamboOrbShaders.js    # GLSL shaders
│   │       ├── HudLayout.js/.css
│   │       └── BrainFeed.js
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
| `GET` | `/agents/status` | — | Overseer + all agent statuses |
| `POST` | `/rambo/execute` | `{ "goal": "..." }` | Run a goal through the full orchestration |
| `GET` | `/sentinel/approvals`| — | List tasks awaiting manual approval |
| `POST` | `/sentinel/decision` | `{ "id": "...", "decision": "APPROVE" \| "DENY" }` | Approve or deny a held task |
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
| `rambo-backend/main.py` | CORS allowed origins | `localhost:3000`, `localhost:3001` |
| `docker-compose.yml` | Dev frontend host port | `3001 → 3000` |
| `docker-compose.yml` | Prod frontend host port | `3000 → 80` |
| `SplashScreen.js` | Backend URL (status polling) | `http://localhost:8000` |
| `SplashScreen.js` | Timezone (briefing clock) | `America/Detroit` |
| `RamboOrb3D.jsx` | `PARTICLE_COUNT`, `BREATH_FREQ` | `4000`, `1.8` |

---

## Visual System

- **Color scheme:** gold / amber neon (`--accent: #e8b15a`, `--accent-glow: #ffd98a`) on near-black (`#08090b`).
- **Plasma core:** billboarded quad with 6-octave fbm noise; breathes in sync with the particle cloud at `BREATH_FREQ = 1.8`.
- **Particles:** 4,000-point spherical shell with additive blending and cursor parallax.
- **Postprocessing:** Bloom (`intensity 1.4`, `radius 0.8`, `mipmapBlur`).
- **Status colors:** `online #00ff88` · `working #e8b15a` · `idle #4a5568` · `offline #2a3040`.

---

## Roadmap

See [`ROADMAP_R.A.M.B.O_06-21-2026_18-34.md`](ROADMAP_R.A.M.B.O_06-21-2026_18-34.md) for the full plan. Highlights:

- **Short term:** chromatic aberration, boot typing animation, accessibility pass, mobile LOD tuning.
- **Mid term:** audio (ambient hum + boot chimes), interactive controls, AI personality presets, unit tests.
- **Long term:** multi-orb network mode, real-time data integration, video export, reusable component library.

---

## Changelog

Running log of splash-screen / UI changes, newest first. Each entry is labeled by area.

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
