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

### Voice Latency Optimization (06/23/2026)
| Feature | Status |
|---|---|
| Streaming LLM responses — `messages.stream()` replaces blocking `messages.create()` in `_speak()` | Done |
| Per-sentence splitting — regex sentence splitter with abbreviation handling (`_split_sentence()`) | Done |
| Hold-one-ahead pattern — flags `is_final` on last segment without extra round-trip | Done |
| `speak_segment` WebSocket events — `base_turn_id`, `seq`, `is_final` broadcast to client | Done |
| Client segment queue — `pumpQueue()` chains `speechSynthesis.speak()` per sentence | Done |
| VAD silence timer reduced 1500ms → 1000ms | Done |
| 800ms artificial command delay removed | Done |
| 7 streaming tests + full suite (22/22 → 61/61 passing) | Done |

### Cost Dashboard (06/23/2026)
| Feature | Status |
|---|---|
| **Phase 1** — Pricing module: `MODEL_PRICING` table, `compute_cost()` with longest-prefix matching | Done |
| **Phase 2** — Storage: `usage` SQLite table via `aiosqlite`, `UsageRepo` with `record()` + `usage_since()` | Done |
| **Phase 3** — Capture: `record_usage()` best-effort helper wired into `_speak()` streaming path, catch-all wrapper | Done |
| **Phase 4** — Aggregation: `GET /usage` endpoint, MTD/today/per-model/daily/cache-savings/MoM, 60s cache | Done |
| **Phase 5** — UI: `CostIndicator` component mirroring `StatBars`, click-to-expand panel on all 4 pages | Done |
| 34 new tests (pricing: 11, repo: 7, capture: 6, dashboard: 10) — 95/95 total passing | Done |

### Self-Knowledge System (06/23/2026)
| Feature | Status |
|---|---|
| **Phase 1** — Doc scaffold (`context/self/rambo.md`) + block parser with AUTO markers | Done |
| **Phase 2** — 5 introspecting generators (capabilities, subagents, integrations, voice, recent activity) reading from live registries | Done |
| **Phase 3** — Drift checker scanning hand-written sections for stale file/symbol refs + CLI (`--render`, `--refresh`, `--check`, `--check --strict`) + allowlist | Done |
| **Phase 4** — Pre-commit hook auto-refreshes self-knowledge doc + idempotent installer script | Done |
| **Phase 5** — Slim summary (~291 tokens) injected into system prompt via `build_system_prompt()`, controlled by `RAMBO_SELF_KNOWLEDGE` env var (slim/full/off) | Done |

### Factory — Sub-Agent Spawner (06/23/2026)
| Feature | Status |
|---|---|
| **Tier 0** — SQLite tables (`spawn_tasks`, `spawned_agents`, `research_reports`) with state-machine transitions, daily cap (5/day), reserved slugs (13), slug uniqueness; `ToolRegistry` with `factory_allowed` gating + 5 starter tools | Done |
| **Tier 1** — Research subagent: `web_search` loop, forced `emit_skills_report` on final iteration, 24h cache, Pydantic-validated `SkillsReport` | Done |
| **Tier 2** — Spec markdown writer (`agent-specs/<slug>.md`) + system-prompt generator with prompt-injection sanitization + revision support | Done |
| **Tier 3** — `SpawnPipeline` state machine (PENDING → AWAITING_APPROVAL), always lands terminal, reserved/duplicate slug + injection guards | Done |
| **Tier 4** — Approval gate: approve creates agent + notifies registry; reject-with-feedback re-runs prompt gen (capped 3 rounds); `GET /factory/pending` page-load hydration | Done |
| **Tier 5** — `ConfigDrivenAgent` (one generic tool-use loop, zero per-agent code) + `RegistryWatcher` (30s poll + immediate refresh on approve) registering `dispatch_to_<slug>` | Done |
| **Frontend** — `FactoryDock` + `useFactoryPending` in SharedHUD, approve/reject/revise cards keyed by task_id, mounted on **all pages** (Splash, Agent, Learning Log, Round Table) | Done |
| **Dispatch** — `Orchestrator._dispatch_spawned()` matches a goal to a spawned agent by slug/name and runs its `ConfigDrivenAgent`; wired before core orchestration in `handle()` | Done |
| API: `POST /factory/spawn`, `GET /factory/pending`, `GET /factory/task/{id}`, approve/reject/agents endpoints; strong refs on in-flight pipeline tasks | Done |
| 59 backend tests (repo: 14, registry: 6, research: 6, spec: 7, pipeline: 5, approval: 8, config/watcher: 8, dispatch: 5) — 154/154 total passing | Done |

---

## What's Next

### Short Term (this week)
| Feature | Priority |
|---|---|
| Live voice testing — configure `ANTHROPIC_API_KEY` and measure new latency floor | High |
| VAD tuning — adjust silence timer after measuring streaming latency | High |
| Evaluate flicker results — if ChromaticAberration removal fixes flickers, keep it removed; if not, investigate further | Medium |
| Operator greeting sequence — personalized boot message | Medium |
| Shutdown / logout sequence | Medium |
| Task history panel — scrollable log of past executions with timestamps | Medium |

### Mid Term (next 2 weeks)
| Feature | Priority |
|---|---|
| Sub-agent independent LLM calls — give each agent its own `messages.stream()` with per-agent `source` label for cost tracking (`ConfigDrivenAgent` now does this for Factory-spawned agents; extend to the 10 hand-rolled specialists) | High |
| Factory follow-ups — ~~mount `FactoryDock` on all pages~~ ✓, ~~wire dispatch into orchestrator~~ ✓; remaining: surface tool-wishlist as a build backlog, capture `record_usage(source=...)` inside `ConfigDrivenAgent`, multi-task spawn matching when a goal names two agents | Medium |
| **Factory dispatch matching — KNOWN ISSUE** — `Orchestrator._dispatch_spawned()` is first-match-wins by slug/name substring. An agent named with a common word (e.g. "build", "find", "search") will silently intercept unrelated goals that happen to contain that word. Fix: require explicit invocation (e.g. `@slug` prefix or "ask <name> to…" pattern), word-boundary matching instead of substring, and/or score-and-rank when multiple agents match. Watch once real agents exist. | High |
| Alembic migration framework — versioned schema management as DB tables grow (now 2 DBs: `usage.db`, `factory.db`) | Medium |
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
| `rambo-frontend/src/components/useVoiceReactivity.js` | Modified — segment queue, `speakSegment()`, `pumpQueue()`, `handleSpeakSegment()`, VAD 1500→1000ms |
| `rambo-frontend/src/components/VoiceControls.jsx` | Modified — WebSocket for `speak_segment` events, removed 800ms delay, `setFollowUpRef` pattern |
| `rambo-backend/orchestrator/orchestrator.py` | Modified — streaming `_speak()`, `_split_sentence()`, `_emit_segment()`, hold-one-ahead |
| `rambo-backend/websocket/manager.py` | Modified — added `broadcast_json()` |
| `rambo-backend/personality.py` | Modified — `load_self_knowledge()`, slim/full/off modes, injected into `build_system_prompt()` |
| `rambo-backend/self_knowledge/` | **Created** — parser, renderer, drift checker, CLI, 5 generators |
| `rambo-backend/context/self/rambo.md` | **Created** — self-knowledge document with AUTO blocks |
| `rambo-backend/tests/test_streaming.py` | **Created** — 7 streaming tests |
| `rambo-backend/tests/test_self_knowledge_*.py` | **Created** — 30 tests (parser, generators, drift, prompt) |
| `scripts/install-self-knowledge-hook.sh` | **Created** — idempotent pre-commit hook installer |
| `rambo-backend/pricing.py` | **Created** — MODEL_PRICING table + compute_cost() with longest-prefix matching |
| `rambo-backend/usage_repo.py` | **Created** — UsageRepo class, SQLite usage table, record + aggregation |
| `rambo-backend/usage_capture.py` | **Created** — record_usage() best-effort helper with catch-all |
| `rambo-backend/usage_dashboard.py` | **Created** — get_dashboard() aggregation with 60s cache |
| `rambo-backend/main.py` | Modified — startup DB init, GET /usage endpoint |
| `rambo-backend/tests/test_pricing.py` | **Created** — 11 tests |
| `rambo-backend/tests/test_usage_repo.py` | **Created** — 7 tests |
| `rambo-backend/tests/test_usage_capture.py` | **Created** — 6 tests |
| `rambo-backend/tests/test_usage_dashboard.py` | **Created** — 10 tests |
| `rambo-frontend/src/components/SharedHUD.js` | Modified — CostIndicator + useCostDashboard |
| `rambo-frontend/src/components/SharedHUD.css` | Modified — cost indicator + expand panel styles |
