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

The front end boots through three scripted phases before reaching the live console:

| Phase | Name | What it shows |
|-------|---------------------|------------------------------------------------------------------|
| **1** | **Transmission** | HUD emblem with a living plasma core; three sequential scans each filling to 100%; agent roster revealed in batches as scans complete. |
| **2** | **Mission Briefing** | Symmetric 3-column layout — agent roster + descriptions (left), Overseer + live clock + boot log (center), system parameters (right). Progress bar fills only after the boot log finishes. |
| **3** | **Live Console** | Full plasma orb with bloom, R.A.M.B.O title stack, live agent status panel, system stat bars, dock, and an interconnecting network-web overlay. |

Each phase auto-advances and can be skipped with a click. All three share the gold/amber neon color scheme.

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
