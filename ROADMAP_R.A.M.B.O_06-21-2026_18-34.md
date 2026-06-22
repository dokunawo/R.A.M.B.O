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

These are the highest-impact remaining items. Most can be slotted into any session.

### Visuals & UX
- [ ] **Chromatic aberration postprocessing** — add `ChromaticAberration` from `@react-three/postprocessing` alongside existing Bloom (`intensity` ~0.003, subtle fringe on orb edges)
- [ ] **Boot typing animation for transcript** — typewriter effect on Phase 3 "System Online" / body copy, 30ms/char delay, triggers on phase transition
- [ ] **Phase 2 staggered agent row animations** — each row slides in with a 40ms offset (CSS `animation-delay`)
- [ ] **Phase 1 emblem spin-up** — SVG outer tick ring slowly rotates in on mount (CSS `@keyframes` on the `.tx-emblem-svg`)

### Accessibility
- [ ] ARIA labels on dock buttons (`aria-label="Power"`, etc.)
- [ ] `prefers-reduced-motion` media query — disable `glitch-in` animation and phase transitions for users with motion sensitivity
- [ ] Color contrast audit — agent status text against dark background (especially `idle` gray `#4a5568`)

### Mobile Performance
- [ ] Reduce `PARTICLE_COUNT` from 4000 → 1800 when `window.innerWidth < 768`
- [ ] Disable `mipmapBlur` on Bloom for mobile (expensive)
- [ ] Cap `devicePixelRatio` at 1.5 on mobile

**Owner:** Daniel (design decisions), Claude (implementation)

---

## Mid Term (July → September 2026)

### Audio
- [ ] **Boot chime** — short synthesized tone on Phase 1 → Phase 2 transition (Web Audio API oscillator, no file needed)
- [ ] **Ambient hum** — low-frequency oscillator running during Phase 3, volume tied to breathing rhythm
- [ ] Mute button in dock (replace placeholder icon)

### Interactive Controls
- [ ] Pause/resume orb animation (spacebar or dock button)
- [ ] Color preset switcher — "Gold" (current), "Cyan", "Red Alert", "Offline" — swaps CSS variables and shader uniforms
- [ ] Speed control — `BREATH_FREQ` and rotation speed as adjustable props passed from a settings panel

### Agent Depth
- [ ] Clickable agents in Phase 2 briefing panel — expand to show current task description (if backend provides it)
- [ ] Agent history log — last 5 actions per agent, visible in an expandable row in Phase 3 panel
- [ ] `WORKING` status pulse animation — agent dot pulses when status is `working`

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
| Frontend | React 18, @react-three/fiber, @react-three/postprocessing, Three.js |
| Shaders | GLSL (fbm noise, vertex displacement, bloom-reactive plasma) |
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

*Next session priority: Chromatic aberration → boot typing animation → mobile LOD tuning*
