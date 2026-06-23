# R.A.M.B.O — PROJECT ROADMAP
**Responsive Autonomous Multi-Brain Operator**
Created: 06/23/2026 at 06:30 (supersedes ROADMAP 06/22/2026 13:39)

---

## What's Shipped (as of 06/23/2026 06:30 ET)

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
| Bloom postprocessing (`intensity 0.6`, `radius 0.5`, `threshold 0.7`, `mipmapBlur`) | Done |

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
| **Per-agent detail pages** — 10 agents, each with avatar, color, stats, objectives, side panels | Done |
| **Sentinel** agent page — live approval queue (review/approve/deny) | Done |
| **Steward** agent page — budget planner table with category breakdown | Done |
| **Round Table** (`/council`) — all 10 agents orbiting the orb as clickable nodes with status dots | Done |
| **Learning Log** (`/learning`) — system-wide learning entries from agent operations | Done |
| **SYSTEMS nav** — section under Agent Roster linking to Learning Log + Round Table | Done |
| Backend: `agent_tracker.py` (per-agent stats, activity, learnings), `sentinel_queue.py` (UUID-tracked approvals) | Done |
| Backend: `GET /agents/{key}/detail`, `GET /learning/log` endpoints | Done |

### Voice System (06/22/2026)
| Feature | Status |
|---|---|
| Wake word "Rambo" activates listening, STT fills command input, auto-executes on silence | Done |
| TTS reads responses aloud with natural voice (rate 1.0, pitch 1.05, prefers natural/female) | Done |
| Conversational follow-up flow ("Is there anything else?" → stays listening) | Done |
| Mic + volume controls on every page (Agent, Learning Log, Round Table, Splash) | Done |
| Percentage-based volume control with voice commands | Done |

### Constellation & Animations (06/22/2026)
| Feature | Status |
|---|---|
| Agent Constellation — 10 orbiting nodes in 3D with status-driven glow and canvas-texture labels | Done |
| Dispatch beams — dynamic cylinders from orb center to agent nodes during task processing | Done |
| Processing helix — 3 tilted golden rings spinning around orb during active work | Done |
| Performance mode — auto-adapts to battery, tab visibility, `prefers-reduced-motion` | Done |

---

## Session: 06/23/2026 — UI polish, shared HUD, flicker fix

### ~05:30 ET — Activity feed repositioned + text readability + agent page navigation
| Change | Details |
|---|---|
| Activity feed relocated | Moved from bottom-center (overlapping "TAP OR SAY RAMBO") to fixed bottom-right | 
| Command input relocated | Moved to fixed bottom-left, no longer overlapping the orb |
| Removed splash footer | Eliminated the `<footer>` wrapper that caused scrolling on the splash screen |
| Agent page text readability | Boosted opacity on dim text: `.ap-agent-role` 0.5→0.75, `.ap-agent-desc` 0.55→0.8, `.ap-obj-text` 0.7→0.85, `.ap-param-key` 0.4→0.65, `.ap-qs-name` 0.5→0.7. Added dark `text-shadow` for contrast against the bright orb |
| Agent page nav expanded | Added Learning Log and Round Table buttons to the quick-switch bar with a gold divider |

### ~05:45 ET — Learning Log complete redesign
| Change | Details |
|---|---|
| Layout overhaul | Removed scrollable center content; now `height: 100vh; overflow: hidden` (single screen, no scroll) |
| Side panel architecture | Left panel: System Identity + Operational Learning stats. Right panel: Recent Learnings list |
| SVG branch connections | Bezier curves connecting orb outer ring to both side panels with animated pulse dots |
| Glass-morph panels | Matching agent page aesthetic: `backdrop-filter: blur(14px)`, semi-transparent borders |
| Route fix | Fixed mismatch: AgentPage navigated to `/learning-log` but route was `/learning` |

### ~06:00 ET — Flicker mitigation (3 fixes)
| Change | Details |
|---|---|
| `Vector2` hoisting | Replaced per-render `new Vector2()` allocations in ChromaticAberration with a hoisted `CHROMA_OFFSET` constant across all 4 page components |
| Animation removal | Removed infinite `responseFloat`/`apResponseFloat` CSS animations on `backdrop-filter` panels (GPU recomposite every frame) |
| GPU hints | Added `will-change: contents` on orb canvas containers, `powerPreference: 'high-performance'` and `stencil: false` on all WebGL contexts |

### ~06:15 ET — Shared HUD system + ChromaticAberration removal + nav bar on Learning Log
| Change | Details |
|---|---|
| **SharedHUD module** | Created `SharedHUD.js` + `SharedHUD.css` — extracted reusable `StatBars`, `ActivityFeed`, `CommandInput` components and `useSystemStats`/`useActivityFeed` hooks |
| **CPU/RAM/DSK stat bars** | Restored on every page (top-left under "BY DANIEL") — previously lost when footer was removed |
| **LIVE command input** | Added to every agent page, Learning Log, and Round Table (bottom-left) |
| **Activity feed** | Added to every agent page, Learning Log, and Round Table (bottom-right) |
| **ChromaticAberration removed** | Stripped from all 4 pages (SplashScreen, AgentPage, LearningLog, RoundTable) as a flicker test — the RGB color fringing effect was a suspected source of persistent screen flickers |
| **Agent nav bar on Learning Log** | Added the full quick-switch agent navigation bar to the Learning Log page with "Log" highlighted as active |

---

## What's Next

### Short Term (this week)
| Feature | Priority |
|---|---|
| Evaluate flicker results — if ChromaticAberration removal fixes flickers, keep it removed; if not, investigate further | High |
| Personality layer API key integration — wire up LLM for genuine agent responses | High |
| Operator greeting sequence — personalized boot message | Medium |
| Shutdown / logout sequence | Medium |
| Task history panel — scrollable log of past executions with timestamps | Medium |

### Mid Term (next 2 weeks)
| Feature | Priority |
|---|---|
| Color presets / theme switcher | Medium |
| Modular HUD panel system (drag, resize, dock) | Medium |
| Mission dashboard — aggregated stats across all agents | Medium |
| Data stream visualizer — live data flowing through agent pipeline | Low |
| Mobile responsive layout | Medium |

### Long Term
| Feature | Priority |
|---|---|
| Secure login / operator authentication | High |
| CLI companion tool (`rambo` command) | Medium |
| Plugin system for custom agents | Medium |
| Multi-operator support | Low |
| Real-time collaboration view | Low |

---

## Files Changed This Session (06/23/2026)

| File | Action |
|---|---|
| `rambo-frontend/src/components/SharedHUD.js` | **Created** — shared stat bars, activity feed, command input components + hooks |
| `rambo-frontend/src/components/SharedHUD.css` | **Created** — styles for the shared HUD components |
| `rambo-frontend/src/components/SplashScreen.js` | Modified — removed ChromaticAberration, added StatBars import |
| `rambo-frontend/src/components/SplashScreen.css` | Modified — activity feed bottom-right, command input bottom-left, removed footer, animation cleanup |
| `rambo-frontend/src/components/AgentPage.js` | Modified — removed ChromaticAberration, added shared HUD components, boosted text opacity, nav bar expanded |
| `rambo-frontend/src/components/AgentPage.css` | Modified — text readability improvements, removed float animations, added nav divider |
| `rambo-frontend/src/components/LearningLog.js` | Modified — complete redesign with side panels, SVG branches, shared HUD, agent nav bar |
| `rambo-frontend/src/components/LearningLog.css` | Modified — complete rewrite for side-panel layout |
| `rambo-frontend/src/components/RoundTable.js` | Modified — removed ChromaticAberration, added shared HUD components |
