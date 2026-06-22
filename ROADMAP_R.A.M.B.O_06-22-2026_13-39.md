# R.A.M.B.O — PROJECT ROADMAP
**Responsive Autonomous Multi-Brain Operator**
Created: 06/22/2026 at 13:39 (supersedes ROADMAP 06/21/2026 18:34)

---

## What's Shipped (as of 06/22/2026 13:39 ET)

### Infrastructure (06/21/2026)
| Feature | Status |
|---|---|
| PowerShell control panel (`rambo-control-panel.ps1`) — 7-step boot, typewriter animations, health scan, force-rebuild, browser launcher | Done |
| `start-dev.ps1` / `start-prod.ps1` — Docker Compose orchestration with sound engine | Done |
| Renamed `brains/` → `agents/` throughout backend | Done |
| FastAPI `/agents/status` + live WebSocket status broadcasts | Done |
| CORS configured for localhost:3000 and localhost:3001 | Done |

### The Cosmic Orb (06/22/2026)
| Feature | Status |
|---|---|
| **CosmicOrb** — wireframe icosahedron (detail 18), 3D simplex noise displacement, fresnel rim glow, billboarded glow halo, gold `#e8b15a`, slow two-axis tumble + mouse parallax | Done |
| Custom GLSL shaders (`CosmicOrbShaders.js`) — Ashima/Gustavson simplex noise, 3-octave layered displacement, configurable fresnel power/bias | Done |
| Unified CosmicOrb across **all pages** (Phase 1, Phase 2, Agent pages, Round Table, Learning Log) | Done |
| Black square artifact fix — replaced 3D BackSide mesh glow shell with depth-test-free billboarded sprite | Done |
| Black flicker fix — raised Bloom `luminanceThreshold` 0.15→0.4, added `premultipliedAlpha: false` across all Canvas instances | Done (06/22/2026 13:39) |
| Bloom postprocessing (`intensity 1.4`, `radius 0.8`, `mipmapBlur`) + ChromaticAberration (offset `0.0012`) | Done |

### Splash Sequence (06/22/2026)
| Feature | Status |
|---|---|
| 2-phase splash: Phase 1 (transmission/boot) → Phase 2 (live console) | Done |
| Phase 1: wireframe orb, R.A.M.B.O title, scan bar (0→100%), boot log typewriter, "NOW BOOTING UP" → transition | Done |
| Phase 2: full orb + EM pulse web, Agent Roster + SYSTEMS nav, System Parameters, command console, stat bars | Done |
| `skipIntro` routing — Command Center button loads Phase 2 directly, **no typing cascade** | Done (06/22/2026 13:39) |
| Sequenced typewriter cascade (topbar → roster → params → center) — first boot only | Done |
| Gold flash transition between phases | Done |
| Lightspeed warp intro, magenta nebula vortex (audio-synced) | Done |

### Console & Backend (06/22/2026)
| Feature | Status |
|---|---|
| Functional command input → `POST /rambo/execute` + live WebSocket activity feed | Done |
| Real system stats → `/system/stats` (psutil: CPU/RAM/DSK) | Done |
| Skill layer (`skills.py`) with weather skill (Open-Meteo, no API key) | Done |
| Response panels branching from originating agent with minimize/dismiss controls | Done |
| Boot chime + ambient hum (Web Audio, synthesized) + mute toggle | Done |
| Browser geolocation passed to skills | Done |

### Pages & Navigation (06/22/2026)
| Feature | Status |
|---|---|
| React Router v7 — routes: `/`, `/console`, `/agent/:agentKey`, `/learning`, `/council` | Done |
| **Per-agent detail pages** — 10 agents, each with avatar, color, stats (tasks/pending/success rate), objectives + progress bars, activity feed | Done |
| **Sentinel** agent page — live approval queue (review/approve/deny) | Done |
| **Steward** agent page — budget planner table with category breakdown | Done |
| **Round Table** (`/council`) — all 10 agents orbiting the orb as clickable nodes with status dots | Done |
| **Learning Log** (`/learning`) — system-wide learning entries from agent operations | Done |
| **SYSTEMS nav** — section under Agent Roster linking to Learning Log + Round Table | Done |
| Backend: `agent_tracker.py` (per-agent stats, activity, learnings), `sentinel_queue.py` (UUID-tracked approvals) | Done |
| Backend: `GET /agents/{key}/detail`, `GET /learning/log` endpoints | Done |

### Accessibility & Performance (06/22/2026)
| Feature | Status |
|---|---|
| `prefers-reduced-motion` — typewriters reveal instantly, animations disabled | Done |
| ARIA labels on command input + connection indicator | Done |
| Color contrast — `idle`/`offline` status colors lightened | Done |
| Mobile LOD: particle count 4000→1800, bloom mipmapBlur off, DPR capped at 1.5 | Done |

---

## Living Cosmic Interface — Tier-by-Tier Build

The orb is being rebuilt as a multi-layered living cosmic interface. Each tier builds on the previous. **Don't start a tier until the previous one renders correctly.**

| Tier | Name | Status | Description |
|------|------|--------|-------------|
| **1** | The Orb Itself | **Done** (06/22/2026) | Wireframe icosahedron, simplex noise, fresnel glow, billboarded halo, gold, tumble + parallax. |
| **2** | The Cosmos | **Done** (06/22/2026 14:15) | Twinkling starfield (500 pts), FBM nebula clouds (warm amber→cool violet), distant node web (24 pulsing nodes + connections), warm glow pool behind orb. All layers use billboarded quads with circular radial fade. |
| **3** | The Voice | **Done** (06/22/2026 14:15) | Mic capture via Web Audio API, FFT analysis, asymmetric smoothing (fast attack/slow decay). 5 states: idle/listening/processing/speaking/error. Audio drives orb displacement (3x boost) + glow brightness. Mic toggle button in Phase 2 UI. |
| **4** | The Constellation | Planned | 10 sub-agents orbiting as floating constellation. Avatar sprites, depth-fading labels, status-driven glow. |
| **5** | Dispatch & Docking | Planned | Dispatch beams from orb to agent, working pulse, docking near roster rows, processing rings ("helix"). |
| **6** | Wire to Reality | Planned | Real WebSocket events, performance mode, reduced motion, battery/focus handling. |

---

## Short Term (Now → July 2026)

### Up Next
- [ ] **Cosmic Interface Tier 2** — deep-space nebula background
- [ ] **Cosmic Interface Tier 3** — voice reactivity + conversational states
- [ ] **Operator greeting** — "Welcome back, Daniel." after CONNECTION ESTABLISHED
- [ ] **Shutdown sequence** — collapsing orb, fading grid, power-down sound

### Backlog
- [ ] **HUD boot transition** — splash console → persistent, dockable HUD workspace (cinematic wipe)
- [ ] **Persistent memory + Task history panel** — surface SQLite/Keeper store: `GET /history`
- [ ] **Command palette** — `Ctrl/Cmd+K` quick launcher for directives, presets, actions
- [ ] **Mobile-friendly HUD** — responsive console layout (stacks panels under ~860px)
- [ ] Agent history log — last 5 actions per agent, expandable in roster

**Owner:** Daniel (design decisions), Claude (implementation)

---

## Mid Term (July → September 2026)

### Interactive Controls
- [ ] Pause/resume orb animation (spacebar or dock button)
- [ ] Color preset switcher — "Gold" (current), "Cyan", "Red Alert", "Offline" — swaps CSS vars + shader uniforms
- [ ] Speed control — noise strength and rotation speed as adjustable props
- [ ] 3 built-in presets: "R.A.M.B.O Gold", "Sentinel Red", "Ghost Mode"

### Polish
- [ ] Real-time toast notifications — errors/warnings/agent insights from WS feed
- [ ] Modular HUD panels — draggable / resizable / dockable
- [ ] Brain glitch on agent switch — distortion flash
- [ ] Mission dashboard — current goal, sub-tasks, progress, timers, logs
- [ ] Data stream visualizer — scrolling matrix/telemetry strip + holographic scanline

**Owner:** Daniel (preset aesthetics), Claude (implementation)

---

## Long Term (September 2026 → June 2027)

### Voice & Security
- [ ] **Voice activation** — "R.A.M.B.O, execute..." (Web Speech API; gesture-gated)
- [ ] **Secure operator login** — PIN / passphrase with biometric-style unlock animation
- [ ] **Encrypted local storage** — vault for sensitive notes (Web Crypto)

### Data & Export
- [ ] Feed token counts, latency, cost metrics from backend to stat panel
- [ ] Video capture of orb via `MediaRecorder` on Canvas stream
- [ ] Shareable config URL (color preset + agent layout encoded in query params)

### Packaging
- [ ] Extract `CosmicOrb` + shaders into standalone npm package (`@rambo/orb`)
- [ ] Storybook for UI components
- [ ] Unit tests for hooks and phase transition logic (Jest + RTL)
- [ ] **R.A.M.B.O CLI tool** — `rambo "<goal>"` from the terminal

### God Mode (long-horizon, optional)
- [ ] Plugin system, public API layer, automation/rules engine, cloud sync, mobile companion app

**Owner:** Future contributor or Daniel when scope expands

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Performance on low-end devices | High | LOD (particle count reduction), disable bloom mipmapBlur on mobile, `devicePixelRatio` cap |
| Shader compatibility (WebGL 1 devices) | Medium | Detect WebGL support, fall back to CSS-only animated gradient orb |
| Backend offline on splash load | Low | Already handled — all agents default to OFFLINE, UI is graceful |
| Docker port conflicts | Medium | `Kill-Port` tool in control panel, `docker compose stop` before mode switch |

---

## Stack Reference

| Layer | Tech |
|---|---|
| Frontend | React 19, @react-three/fiber, @react-three/postprocessing, Three.js, react-router-dom v7 |
| Shaders | GLSL (3D simplex noise, wireframe icosahedron displacement, fresnel glow) |
| Backend | FastAPI (Python), WebSocket via `ConnectionManager`, psutil for system metrics |
| Orchestrator | `Orchestrator` class, 10 agents in `agents/`, skill layer (`skills.py`) |
| Tracking | `agent_tracker.py` (stats/activity/learnings), `sentinel_queue.py` (UUID approvals) |
| Dev environment | Docker Compose — `rambo-frontend-dev` (port 3001, hot-reload), `rambo-backend` (port 8000) |
| Prod environment | Docker Compose — `rambo-frontend` (port 3000, Nginx), `rambo-backend` (port 8000) |
| Control panel | PowerShell (`rambo-control-panel.ps1`), dev mode default |

---

## Tasks & Owners

| Task | Owner | Timeline |
|---|---|---|
| UI design, shader tuning, presets | Daniel | Ongoing |
| Cosmic Interface tiers, postprocessing, audio, API | Claude | On request |
| Testing, packaging, Storybook | Future contributor | Long term |

---

> **Honest scope note:** the agents are currently deterministic rule-based stubs.
> Anything that needs *real* understanding (File Analyzer, voice intent, AI
> insights) implies wiring an actual LLM into the orchestrator — a meaningful
> backend project on its own.

> **Recommended next steps:** Cosmic Interface Tier 2 (nebula background) → Tier 3
> (voice reactivity) → operator greeting → shutdown sequence.

---

## Change Log

| Date | Time (ET) | Changes |
|------|-----------|---------|
| 06/22/2026 | 16:30 | Fixed orb missing on sub-pages (fallbackRef bug — nested object instead of number). Added speech-to-text via Web Speech API (SpeechRecognition) — spoken words fill command input live, auto-execute on silence. SYSTEMS nav restyled to match Agent Roster gold accent scheme. |
| 06/22/2026 | 14:15 | Tier 2 (cosmic background) + Tier 3 (voice reactivity) shipped. Fixed amber square on nebula/glow quads. |
| 06/22/2026 | 13:39 | Created new roadmap. Fixed black flickers (Bloom threshold + premultipliedAlpha). Skip typing cascade on Command Center click. All shipped items consolidated. |
| 06/22/2026 | ~12:00 | CosmicOrb (Tier 1) built and deployed across all pages. Black square fix (billboarded sprite). Per-agent pages, Round Table, Learning Log, SYSTEMS nav, response controls, skipIntro routing, agent_tracker, sentinel_queue. |
| 06/21/2026 | 18:34 | Original roadmap created. Initial three-phase splash, PowerShell control panel, Docker orchestration, plasma orb with particles. |
