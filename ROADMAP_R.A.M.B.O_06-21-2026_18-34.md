# R.A.M.B.O — PROJECT ROADMAP
**Responsive Autonomous Multi-Brain Operator**
Created: 06/21/2026 at 18:34

---

## What We Shipped Today (06/21/2026)

These are fully implemented and running:

| Feature | Status |
|---|---|
| PowerShell control panel (`rambo-control-panel.ps1`) — rebuilt from scratch with 7 steps, typewriter animations, centered boot bar, health scan, force-rebuild, browser launcher | ✅ Done |
| `start-dev.ps1` / `start-prod.ps1` — Docker Compose orchestration with sound engine | ✅ Done |
| Dev mode as default in control panel | ✅ Done |
| `Open Browser` auto-starts containers if down before opening URL | ✅ Done |
| Renamed `brains/` → `agents/` throughout backend | ✅ Done |
| FastAPI `/agents/status` endpoint + live status broadcasting via WebSocket | ✅ Done |
| CORS configured for localhost:3000 and localhost:3001 | ✅ Done |
| Plasma nucleus shader (`ramboPlasmaFragmentShader`) — fbm noise, gold→white gradient, bloom-reactive | ✅ Done |
| Billboarded PlasmaCore mesh — always faces camera, stable anchor outside parallax group | ✅ Done |
| Breathing sync — particles and plasma pulse at same `BREATH_FREQ = 1.8` | ✅ Done |
| Group-level cursor parallax — dust cloud and equatorial ring tilt with mouse | ✅ Done |
| Equatorial ring — single clean rotating ring replacing 6 armillary rings | ✅ Done |
| Removed spokes (`SHOW_SPOKES = false`) | ✅ Done |
| Bloom postprocessing via `@react-three/postprocessing` — `intensity=1.4`, `radius=0.8`, `mipmapBlur` | ✅ Done |
| Agent status panel (right side of splash) — overseer block + 10 agents, live color-coded status polling | ✅ Done |
| Left panel aligned to 20px matching topbar | ✅ Done |
| MK XVII removed from orb center title (moved to topbar only) | ✅ Done |
| **Three-phase splash screen sequence** | ✅ Done |
| — Phase 1: Transmission screen — dot grid, HUD corner brackets, R.A.M.B.O SVG targeting emblem, progress bar, ~4.2s auto-advance | ✅ Done |
| — Phase 2: Mission briefing — 3-column layout (agent roster + descriptions \| live clock + boot log \| system parameters), ~5.8s auto-advance | ✅ Done |
| — Phase 3: Plasma orb splash screen (existing) with agent panel, stats, dock | ✅ Done |
| Phase transitions — fade through black with CSS animations | ✅ Done |

---

## Short Term (Now → July 2026)

### 🌌 Living Cosmic Interface — Tier-by-Tier Build

The orb is being rebuilt as a multi-layered living cosmic interface. Each tier builds on the previous.

| Tier | Name | Status | Description |
|------|------|--------|-------------|
| **1** | The Orb Itself | ✅ Done (2026-06-22) | Wireframe icosahedron (detail 18), simplex noise displacement, fresnel rim glow, billboarded glow halo, slow tumble + mouse parallax. Gold color. Deployed across all pages. |
| **2** | The Cosmos | 🔲 Next | Deep-space nebula background: twinkling stars, nebula clouds (layered noise), distant glowing node web, colored glow pooled behind the orb. Separate background renderer. |
| **3** | The Voice | 🔲 Planned | 5 conversational states (idle/listening/processing/speaking/error) with real microphone audio reactivity (Web Audio API). Asymmetric audio smoothing, synthetic fallback. |
| **4** | The Constellation | 🔲 Planned | 10 sub-agents orbiting the orb as a floating constellation. Avatar sprites, labels that track camera and fade by depth, status-driven glow. |
| **5** | Dispatch & Docking | 🔲 Planned | Dispatch beams from orb to agent, working pulse, docking near roster rows, processing rings ("helix" effect). |
| **6** | Wire to Reality | 🔲 Planned | Connect to real WebSocket events, performance mode, reduced motion support, battery/focus handling. |

### ✅ Completed (Short Term)
- [x] Chromatic aberration postprocessing (2026-06-22)
- [x] Boot typing animation for transcript (2026-06-22)
- [x] Phase 2 staggered agent row animations (2026-06-22)
- [x] ARIA labels on command input + connection indicator (2026-06-22)
- [x] `prefers-reduced-motion` support (2026-06-22)
- [x] Color contrast audit — `idle`/`offline` lightened (2026-06-22)
- [x] Mobile LOD: particle count, bloom mipmapBlur, DPR cap (2026-06-22)
- [x] Functional command console + live WebSocket feed (2026-06-22)
- [x] Real system stats via `/system/stats` (2026-06-22)
- [x] Boot chime + ambient hum (Web Audio) (2026-06-22)
- [x] Per-agent detail pages with stats, objectives, activity (2026-06-22)
- [x] Sentinel approval queue UI (2026-06-22)
- [x] Steward budget planner (2026-06-22)
- [x] Learning Log page (2026-06-22)
- [x] Round Table / Council View with orbiting agents (2026-06-22)
- [x] Response minimize/dismiss controls (2026-06-22)
- [x] SYSTEMS nav section (Learning Log + Round Table links) (2026-06-22)
- [x] `skipIntro` — Command Center button skips Phase 1 (2026-06-22)
- [x] Unified CosmicOrb across all pages (2026-06-22)
- [x] Fixed black square artifacts on orb (2026-06-22)

**Owner:** Daniel (design decisions), Claude (implementation)

---

## Mid Term (July → September 2026)

### Audio
- [x] **Boot chime** — ✅ synthesized tone on Phase 1 → Phase 2 transition (2026-06-22)
- [x] **Ambient hum** — ✅ low-frequency pad during console (2026-06-22)
- [x] Mute toggle (bottom-right) — ✅ (2026-06-22)
- [ ] Voice reactivity — real microphone input driving orb animation (part of Tier 3)

### Interactive Controls
- [ ] Pause/resume orb animation (spacebar or dock button)
- [ ] Color preset switcher — "Gold" (current), "Cyan", "Red Alert", "Offline" — swaps CSS variables and shader uniforms
- [ ] Speed control — noise strength and rotation speed as adjustable props

### Agent Depth
- [x] Clickable agents → per-agent detail pages — ✅ (2026-06-22)
- [x] Agent stats + activity feed on detail pages — ✅ (2026-06-22)
- [x] `WORKING` status pulse animation — ✅ (2026-06-22)
- [ ] Agent history log — last 5 actions per agent, expandable in roster

### AI Personalities / Presets
- [ ] Define preset schema: `{ name, accentColor, particleColor, breathFreq, bloomIntensity }`
- [ ] 3 built-in presets: "R.A.M.B.O Gold" (current), "Sentinel Red", "Ghost Mode"
- [ ] Preset picker accessible from dock

**Owner:** Daniel (preset aesthetics), Claude (implementation)

---

## Long Term (September 2026 → June 2027)

### Multi-Orb Network Mode
- [ ] Render multiple smaller orbs connected by animated lines (one per agent)
- [ ] Overseer orb at center, agent orbs orbit it
- [ ] Status-driven color and scale of each agent orb

### Real-Time Data Integration
- [ ] WebSocket feed already in place (`/ws/activity`) — surface live messages as scrolling log in Phase 3
- [ ] Feed token counts, latency, and cost metrics from backend to stat panel
- [ ] Replace static stat values (CPU/RAM/GPU) with real system metrics (backend endpoint serving `psutil` data)

### Exportable Visualizations
- [ ] Video capture of orb via `MediaRecorder` on Canvas stream
- [ ] Export Phase 1 emblem as SVG download
- [ ] Shareable config URL (color preset + agent layout encoded in query params)

### Packaging
- [ ] Extract `RamboOrb3D` + shaders into standalone npm package (`@rambo/orb`)
- [ ] Storybook for UI components (SplashScreen phases, AgentStatusPanel, StatBar)
- [ ] Unit tests for `useAgentStatus` hook and phase transition logic (Jest + React Testing Library)

**Owner:** Future contributor or Daniel when scope expands

---

## Copilot Brain-Dump → Prioritized Backlog (added 06/22/2026)

Source: Daniel's saved Copilot notes, **re-scoped to what R.A.M.B.O actually is**
(a Dockerized FastAPI multi-agent orchestrator + a React/Three.js console). Many
Copilot items already exist here — listed first so we don't rebuild them.

### ✅ Already shipped (Copilot asked for these — we have them)
- **Operator Console** → the command console (input → `POST /rambo/execute`).
- **AI Brain Activity Feed** → live WebSocket activity feed + per-agent response panels.
- **Live System Telemetry** → real CPU/RAM/DSK stat bars (`/system/stats`).
- **The "brains"** → Pilot, Sentinel, Analyst, Archivist (Keeper), Navigator (Architect), Echo, Seeker, Steward, Link all exist as agents with status + activity pulses.
- **Ambient Reactor Hum** → synthesized Web-Audio hum on the console.
- **Real-Time pulses showing which brain is thinking** → live `working`/`idle` dots.

### 🥇 Tier 1 — Do next (operator-focused; high impact, fits scope)
- [ ] **HUD boot transition** — splash console → a persistent, dockable HUD workspace (cinematic wipe). *Unlocks everything "modular HUD" below.*
- [ ] **Operator greeting** — "Welcome back, Daniel." after CONNECTION ESTABLISHED.
- [ ] **Shutdown sequence** — collapsing orb, fading grid, power-down sound (power button / hotkey).
- [ ] **Persistent memory + Task history panel** — surface the existing SQLite/Keeper store: a panel listing past goals, the agents used, and Echo's summary. Backend: `GET /history`.
- [ ] **Command palette** — `Ctrl/⌘+K` quick launcher for directives, presets, and actions.
- [ ] **Mobile-friendly HUD** — responsive console layout (stacks panels under ~860px).
- [ ] **Skip control for Phase 1** — any key/click fast-forwards the intro on repeat views.

### 🥈 Tier 2 — Soon (depth + polish)
- [ ] **Real-time notifications** — toast alerts for errors/warnings/agent insights (drive off the WS feed; Sentinel surfaces threats).
- [ ] **Modular HUD panels** — draggable / resizable / dockable roster, params, feed, telemetry.
- [ ] **Brain glitch on switch** — distortion flash when the active agent changes.
- [ ] **Color presets / "AI personalities"** — Gold (current), Sentinel Red, Ghost — swap CSS vars + shader uniforms (already in Mid-Term above).
- [ ] **Mission dashboard** — current goal, sub-tasks, progress, timers, logs (extends Task Orchestrator).
- [ ] **Data stream visualizer** — subtle scrolling matrix/telemetry strip + holographic scanline overlay.

### 🥉 Tier 3 — Later (needs new infra or external services)
- [ ] **Voice activation** — "R.A.M.B.O, execute…" (Web Speech API; gesture-gated like audio).
- [ ] **Secure operator login** — PIN / passphrase with a biometric-style unlock animation.
- [ ] **Encrypted local storage** — vault for sensitive notes (Web Crypto).
- [ ] **File / clipboard / screenshot interpreters** — operator tools; require a real LLM backend (agents are currently rule-based stubs).
- [ ] **R.A.M.B.O CLI tool** — `rambo "<goal>"` hitting `/rambo/execute` from the terminal.

### 🌌 Tier 4 — "God mode" (long-horizon, optional)
- [ ] Plugin system, public API layer, automation/rules engine, cloud sync, mobile companion app.

### 🎁 Quick wins (cheap, standalone — grab anytime)
- [ ] Custom Windows icon for the `.ps1` shortcuts.
- [ ] R.A.M.B.O splash sound pack (curated SFX set).

> **Honest scope note:** the agents are currently deterministic rule-based stubs.
> Anything that needs *real* understanding (File Analyzer, voice intent, AI
> insights) implies wiring an actual LLM into the orchestrator — a meaningful
> backend project on its own. Flagged on the relevant items above.

> **Recommended direction:** *operator-focused* — Tier 1 turns R.A.M.B.O from a
> stunning demo into a daily driver. Suggested order: **HUD boot transition →
> task history/memory → command palette → notifications → shutdown sequence.**

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Performance on low-end devices | High | LOD (particle count reduction), disable bloom mipmapBlur on mobile, `devicePixelRatio` cap |
| Shader compatibility (WebGL 1 devices) | Medium | Detect WebGL support, fall back to CSS-only animated gradient orb |
| Backend offline on splash load | Low | Already handled — all agents default to OFFLINE, UI is graceful |
| Docker port conflicts | Medium | `Kill-Port` tool in control panel, `docker compose stop` before mode switch |
| HMR not picking up constant-level changes in dev container | Low | Known issue — `.\start-dev.ps1` full rebuild resolves it |

---

## Stack Reference

| Layer | Tech |
|---|---|
| Frontend | React 19, @react-three/fiber, @react-three/postprocessing, Three.js, react-router-dom v7 |
| Shaders | GLSL (3D simplex noise, wireframe icosahedron displacement, fresnel glow) |
| Backend | FastAPI (Python), WebSocket via `ConnectionManager` |
| Orchestrator | `Orchestrator` class, 10 agents in `agents/` folder |
| Dev environment | Docker Compose — `rambo-frontend-dev` (port 3001, hot-reload), `rambo-backend` (port 8000) |
| Prod environment | Docker Compose — `rambo-frontend` (port 3000, Nginx), `rambo-backend` (port 8000) |
| Control panel | PowerShell (`rambo-control-panel.ps1`), dev mode default |

---

## Tasks & Owners

| Task | Owner | Timeline |
|---|---|---|
| UI design, shader tuning, presets | Daniel | Ongoing |
| Postprocessing, audio, animations, API | Claude | On request |
| Testing, packaging, Storybook | Future contributor | Long term |

---

*Next session priority: Cosmic Interface Tier 2 (deep-space nebula background) → Tier 3 (voice reactivity + conversational states)*
