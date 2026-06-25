# R.A.M.B.O — Context Handoff

## 1. Mission

R.A.M.B.O (Responsive Autonomous Multi-Brain Operator) is a cinematic multi-agent AI orchestration system. React 19 frontend with a WebGL cosmic orb interface, FastAPI backend whose 10 original agents are now consolidated into **3 routable modes (Planner/Executor/Researcher) + Keeper/Sentinel/Pilot services** (the UI may still show the legacy roster names), voice control via Web Speech API, Spotify in-app playback, screen vision, and Google service integrations. The operator (Daniel) uses it as a personal ops hub for two businesses: armed security and photography. The system is functional end-to-end — the current phase is expanding integrations, polishing the UI, and wiring up the Anthropic API for personality-driven responses.

## 2. Current State

### Working and verified
- **Cosmic orb renders on all pages** — wireframe icosahedron (detail 18), GLSL simplex noise displacement, fresnel rim glow, billboarded halo, additive blending. Bloom threshold 0.7, intensity 0.6, radius 0.5, smoothing 0.95. `toneMapped: false` on orb materials.
- **Voice system** — wake word "Rambo" via continuous SpeechRecognition, singleton pattern (one instance per tab), auto-starts on page mount. TTS readback with natural voice (pitch 1.05, rate 1.0). Conversational follow-up ("Is there anything else?"). Works on all pages.
- **Backend skills** — weather (Open-Meteo, no key), Google Calendar (read + create events), Google Drive (list + search files), Chief of Staff (doctrine-anchored daily briefs from `north-star.md`).
- **Agent pages** — left panel (roster-style profile + objectives), right panel (parameters-style stats), response branches connected to orb via bezier SVG curves, bottom quick-switch bar for all 10 agents.
- **Phase 2 main console** — full orb + agent roster + system parameters + command input + WebSocket activity feed + stat bars.
- **Round Table** — 10 agents orbiting orb as clickable nodes, AgentConstellation in 3D.
- **Tier 5/6** — dispatch beams, processing helix, WebSocket-driven animations, performance mode (battery/visibility/prefers-reduced-motion).
- **Git state**: on `main`, latest commit `d60d48d` (self-coding lane merge). Working tree has **uncommitted** Spotify/startup fixes from the 2026-06-25 session (see §2a).

## 2a. Session 2026-06-25 — Spotify control + startup fixes (UNCOMMITTED)

All verified working on dev (:3001) and prod (:3000) rebuilt. Files touched:
`rambo-backend/spotify_client.py`, `rambo-backend/main.py`,
`rambo-frontend/src/components/spotifyEngine.js`, `docker-compose.yml`,
`rambo-startup.ps1`, plus new `rambo-mediakeys.ahk`, `docs/spotify-extended-quota.md`.

- **Click-the-wrong-song bug → FIXED.** `SpotifyClient.play()` now forces shuffle
  OFF whenever a specific track is selected (`uris` or `offset` present) — with
  shuffle on, Spotify ignored the start position and began on a random track.
- **Play/pause BUTTON → FIXED.** `spotifyEngine.js` replaced the flaky SDK
  `togglePlay()` with explicit `resume()`/`pause()` off tracked state, with a
  backend Web-API fallback.
- **Hardware media keys → solved at OS level, NOT in-browser.** The Web Playback
  SDK plays audio in a cross-origin iframe that owns the OS media session, so
  Chrome won't deliver the play/pause key to our page (confirmed: top-frame
  `mediaSession.playbackState` stayed `none`; a silent-audio anchor did not win
  the session). Solution: new `/spotify/toggle` endpoint + `rambo-mediakeys.ahk`
  (AutoHotkey v2) maps play/pause/next/prev → backend. Auto-launched by the
  startup script. **Requires AutoHotkey v2 installed** (now is).
- **Playlist track listings → Spotify limitation, not a bug.** `/playlists/{id}/tracks`
  403s for ALL playlists (incl. own) because the app is in Dev Mode. Needs
  Extended Quota Mode — steps in `docs/spotify-extended-quota.md`. Playback via ▶
  (context_uri) still works; Liked Songs lists fine (`/me/tracks` isn't restricted).
- **Dev server wasn't recompiling → FIXED.** CRA 5 / webpack 5 watches via
  watchpack, not chokidar; on Docker/Windows it needs `WATCHPACK_POLLING=true`
  (added to compose) or edits silently never reach the :3001 bundle. Also set
  `WDS_SOCKET_PORT=3001` so HMR stops failing against :3000. **This is why early
  fixes "didn't work" — the running dev build was stale.**
- **Startup blank "screen" tab → FIXED.** Root cause: `--auto-select-desktop-capture-source=Entire screen`
  has a space and was unquoted, so PowerShell split it and Chrome opened the bare
  `screen` token as a URL. Now quoted. Also: kill leftover RAMBO-profile Chrome
  before relaunch + suppress session restore.
- **Note:** backend compose command uses `--reload`, so .py edits DO auto-reload
  (the old "no auto-reload" note was wrong). Prod frontend (:3000) must be rebuilt
  (`docker compose up -d --build rambo-frontend`) to pick up frontend changes.

### Half-built
- **Personality engine** — `personality.py`, `conversation.py`, `AGENT.md` all exist and are wired into the orchestrator's `_speak()` method. Falls back gracefully to raw results when no API key is set. **Not yet live** because Daniel hasn't set `ANTHROPIC_API_KEY`.
- **Google OAuth** — `credentials.json` and `token.json` exist locally in `rambo-backend/`. Auth flow completed successfully. Calendar and Drive skills should work but **Daniel hasn't tested them through the R.A.M.B.O UI yet** (only the auth flow was verified).

### Blocked
- **Anthropic API** — personality voice won't activate until Daniel gets an API key from console.anthropic.com and sets `ANTHROPIC_API_KEY` env var. The fallback returns raw agent results in the meantime.
- **Gmail integration** — not built yet. Was discussed but deprioritized. The Google OAuth token already includes `gmail.readonly` scope, so only the skill code is needed.
- **Spotify integration** — not built. Requires separate OAuth app at developer.spotify.com.

### Next action
**Active initiative: self-coding agent.** See `docs/PLAN_self-coding-agent.md` — plan to give RAMBO the ability to read/write/review its own code in its AGENT.md voice via Managed Agents, with self-modification sandboxed behind a branch→PR→Daniel-merges loop. **Self-coding lane BUILT (Hybrid, 06/25).** New `rambo-backend/dev_agent/` lets RAMBO edit its OWN code on an isolated local git worktree → diff + impact + recommendation (merge/escalate/hold) → operator merges locally. Endpoints `/dev/*`; routable `dev` target in the orchestrator; `CodeReviewDock` in the frontend (SharedHUD.js). Factory (helper-agent spawning) unchanged. Full suite 307 pass; pipeline verified in-process. Plan: `docs/PLAN_self-coding-agent.md`. **To exercise it live: restart the backend container** (uvicorn no auto-reload — the running one is 4h old and lacks `/dev/*`); merge also requires a clean working tree (currently dirty with uncommitted work). Phase 0 (API key) + Phase 1a (agent loop) were done 06/24.

Other pending threads: visual polish on the branch panels, Gmail/Spotify integration, testing calendar/drive skills through the voice interface.

## 3. Decisions Made (and Why)

- **Decision:** Singleton SpeechRecognition instance (global, not per-component)
  - **Alternatives:** Per-page instances (original approach)
  - **Reason:** Browser allows only one active SpeechRecognition per tab. Per-page instances caused silent failures on navigation — old instance's async `stop()` raced with new `start()`.
  - **Reversibility:** Load-bearing. Do not change.

- **Decision:** No tool_use in the LLM conversation loop
  - **Alternatives:** Claude tool_use for mid-conversation actions
  - **Reason:** The agents already ARE the tools. Skills match first, orchestrator runs them, LLM just voices the response. Adding tool_use now adds complexity to voice cue logic for no benefit.
  - **Reversibility:** Easy to add later if needed.

- **Decision:** Personality voice cue injected into API payload only, never stored in conversation history
  - **Alternatives:** Storing the cue in history
  - **Reason:** Prevents the cue from accumulating in context and influencing future turns. `conversation.py` returns deep copies so the cue can't leak.
  - **Reversibility:** Structural — changing this would require reworking ConversationManager.

- **Decision:** Bloom threshold at 0.7 (raised progressively from 0.15)
  - **Alternatives:** Lower thresholds (caused black flicker artifacts)
  - **Reason:** Semi-transparent wireframe fragments between additive lines were being amplified by Bloom into dark flashes. Higher threshold + lower wireframe opacity (0.45) + `toneMapped: false` eliminated the artifacts.
  - **Reversibility:** Can be tuned, but going below 0.55 will bring flickers back.

- **Decision:** Agent page info as Phase 2-style side panels, not center cards
  - **Alternatives:** Original center-positioned info cards (blocked the orb)
  - **Reason:** Daniel explicitly asked to remove middle content and make the orb fully visible. Then clarified he wanted the info restyled as side panels matching Phase 2's roster/parameters aesthetic, not deleted entirely.
  - **Reversibility:** Easy — it's just JSX and CSS.

- **Decision:** Response panels as tree branches from orb, not flat CommandLog
  - **Alternatives:** Bottom-left fixed CommandLog (was the original)
  - **Reason:** Daniel requested responses attach to the orb's outer wave with a tree-like structure. Bezier SVG curves connect orb edge to draggable response panels.
  - **Reversibility:** Easy to revert to CommandLog if tree layout doesn't work visually.

- **Decision:** Chief of Staff skill reads `north-star.md` from backend dir or `~/.claude/`
  - **Alternatives:** Only reading from working directory
  - **Reason:** Docker volume mount maps `rambo-backend/` to `/app`, so the backend copy works. The `~/.claude/` fallback lets Claude Code sessions also use it.
  - **Reversibility:** Easy to add more paths.

## 4. Architecture & Key Files

### Frontend (`rambo-frontend/src/components/`)

| File | Purpose |
|------|---------|
| `SplashScreen.js` / `.css` | Main UI — Phase 1 (boot) + Phase 2 (console). ~1250 lines. Command input, agent roster, system params, ResultBranch. |
| `AgentPage.js` / `.css` | Per-agent detail pages. Left/right panels, response tree branches, quick-switch bar. AGENT_META has all 10 agents' metadata. |
| `CosmicOrb.jsx` | The orb — wireframe icosahedron + glow halo. `toneMapped: false` on both materials. |
| `CosmicOrbShaders.js` | GLSL vertex/fragment shaders — 3D simplex noise, fresnel, audio reactivity uniforms. |
| `CosmicBackground.jsx` | Starfield, nebula clouds, distant node web, warm glow pool. |
| `AgentConstellation.jsx` | 10 agent nodes orbiting the orb in 3D. Canvas-texture labels. Used on Phase 2 + Round Table. |
| `useVoiceReactivity.js` | Voice system — wake word, STT, TTS, audio level analysis. **Singleton SpeechRecognition.** |
| `VoiceControls.jsx` | `usePageVoice()` hook (auto-starts mic, executes commands against backend), `VoiceControls` component (mic/volume buttons), `CommandLog` component. |
| `DispatchBeam.jsx` | Tier 5 — cylinder beams from orb to agent positions. |
| `ProcessingHelix.jsx` | Tier 5 — spinning golden rings during active processing. |
| `usePerformanceMode.js` | Tier 6 — adaptive DPR/bloom based on battery, visibility, reduced-motion. |
| `audioEngine.js` | Boot chime + ambient hum. Hum gain 0.006, LFO 0.001. |
| `RoundTable.js` / `.css` | Council page — orbiting agent nodes + constellation. |
| `LearningLog.js` / `.css` | Learning log page — displays system learnings from backend. |

### Backend (`rambo-backend/`)

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app — endpoints for execute, agents, system stats, sentinel, learning, Google auth. |
| `orchestrator/orchestrator.py` | Core orchestrator — skills check → plan → execute → `_speak()`. Falls back to raw results if no Anthropic key. |
| `skills.py` | Skill registry — weather, calendar, drive, chief-of-staff. Matcher + async runner per skill. |
| `personality.py` | Three-layer voice engine — `load_personality()`, `build_system_prompt()`, `append_voice_cue()`. |
| `conversation.py` | `ConversationManager` — stores messages, returns deep copies for API calls. |
| `AGENT.md` | Personality file — cold professional voice, 12 examples, 12 banned phrases, warmth floor rules. |
| `google_auth.py` | OAuth2 token management — `get_credentials()`, `run_auth_flow()`, `is_authenticated()`. |
| `google_calendar.py` | Calendar skill — list events (today/tomorrow/week), create events from natural language. |
| `google_drive.py` | Drive skill — list recent files, search by name. |
| `chief_of_staff.py` | Daily revenue brief from `north-star.md` doctrine. |
| `auth_setup.py` | One-time script to run OAuth browser flow on host machine. |
| `north-star.md` | Daniel's business doctrine — armed security + photography, $10K target. **Gitignored.** |
| `credentials.json` | Google OAuth client secret. **Gitignored.** |
| `token.json` | Google OAuth access/refresh token. **Gitignored.** |
| `agent_tracker.py` | Per-agent stats, activity, learnings tracking. |
| `sentinel_queue.py` | UUID-tracked approval queue for Sentinel agent. |
| `agents/` | 10 agent modules (architect, engineer, seeker, analyst, sentinel, steward, link, keeper, echo, pilot). Currently deterministic stubs. |

### Legacy files (not used)
- `RamboOrb3D.jsx` / `RamboOrbShaders.js` — old orb, replaced by `CosmicOrb.jsx` + `CosmicOrbShaders.js`.
- `HudLayout.js` / `.css` — old layout, replaced by Phase 2 redesign.
- `BrainFeed.js` — old activity feed, not used.

## 5. Gotchas & Hard-Won Knowledge

- **Black flicker artifacts** — caused by Bloom amplifying dark fragments between additive wireframe lines. Required progressive tuning: threshold 0.15→0.4→0.55→0.7, wireframe opacity 0.55→0.45, and `toneMapped: false` on both ShaderMaterials. Going below threshold 0.55 brings them back.
- **SpeechRecognition singleton** — browsers only allow ONE active instance per tab. Creating a new one per page causes silent failures. The fix uses a global singleton with owner ID tracking and 100ms restart delay on `onend`.
- **Google OAuth in Docker** — the OAuth browser flow can't run inside the container. Must run `python auth_setup.py` on the host machine first. The Docker volume mount (`./rambo-backend:/app`) then shares the resulting `token.json` into the container.
- **PowerShell commit messages** — parentheses and special characters in commit messages get parsed by PowerShell and break `git commit -m`. Always use Bash with heredoc for commit messages, never PowerShell.
- **Daniel views at 80% Chrome zoom** — UI sizing was tuned for this. Typography in Phase 2 roster/params panels was bumped specifically for 80% readability.
- **Daniel's timezone is America/Detroit** — Google Calendar events use this timezone. The clock on all pages uses the browser's local time.
- **`premultipliedAlpha: false`** — must be set on every `<Canvas>` gl prop. Without it, the additive blending on the orb creates washed-out artifacts.

## 6. Conventions In Play

- **Frontend**: React 19 + CRA (not Vite). `@react-three/fiber` for WebGL. All 3D components use Three.js directly via hooks, no Drei helpers.
- **CSS**: One CSS file per component, class-name prefixed (`ap-` for AgentPage, `rt-` for RoundTable, `ll-` for LearningLog). CSS vars `--accent` (#e8b15a), `--accent-glow` (#ffd98a), `--mono` (JetBrains Mono). No CSS-in-JS.
- **Backend**: FastAPI, no ORM. SQLite via `sqlite_store.py` for memory. Skills pattern: matcher function + async runner, registered in `SKILLS` list.
- **Git**: Descriptive multi-line commit messages. `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` on every commit. Use Bash heredoc, not PowerShell, for commit messages.
- **No unit tests on frontend** — we're prototyping. Backend has `tests/test_personality.py` (15 tests, all pass).
- **Voice**: "Rambo" is the wake word. TTS prefers natural/female English voices. Pitch 1.05, rate 1.0.
- **Color scheme**: gold #e8b15a is the primary accent. Each agent has a unique color defined in AGENT_META. Dark backgrounds rgba(8,9,11,X).

## 7. Open Questions

- Has Daniel tested Calendar/Drive skills through the voice interface? They were wired up but he moved on to UI work before testing.
- Does Daniel want Gmail and Spotify integrations next? Both were discussed. Gmail just needs a skill module (OAuth scope already included). Spotify needs a separate OAuth app.
- Is the response tree branch layout visually right? It was just committed — Daniel hasn't confirmed the look yet.
- Does Daniel want the personality voice activated? He needs an Anthropic API key. He said "skip this for now" but may circle back.
- Should the north-star.md be editable through the R.A.M.B.O UI? Currently it's a static file.

## 8. Do Not Touch

- **CosmicOrb.jsx / CosmicOrbShaders.js** — Bloom and shader settings were tuned through 6+ iterations to eliminate flicker artifacts. Do not lower bloom threshold below 0.55 or remove `toneMapped: false`.
- **useVoiceReactivity.js singleton pattern** — the global `stopGlobalRecognition()` / owner ID pattern is load-bearing. Do not create per-component SpeechRecognition instances.
- **SplashScreen.js** — ~1250 lines, very complex. Phase 1 + Phase 2 + all the typewriter/cascade logic. Changes here are high-risk for regressions.
- **`.gitignore` secrets entries** — `credentials.json`, `token.json`, `north-star.md`, `*.env` must stay gitignored.
- **AGENT.md personality file** — Daniel approved the cold professional voice with warmth floor. Don't soften or restructure it.
- **Bloom settings across all pages** — threshold 0.7, intensity 0.6, radius 0.5, smoothing 0.95. These are identical on AgentPage, LearningLog, RoundTable, and SplashScreen (x2 instances). Keep them in sync.

## 9. Resume Command

> Read HANDOFF.md. The project is R.A.M.B.O at `C:\Users\dokun\PycharmProjects\R.A.M.B.O`. Check `git log --oneline -5` and `git status` to confirm state. Wait for Daniel's direction — he was testing UI changes (response tree branches on agent pages, quick-switch bar) and may want visual adjustments, new integrations (Gmail, Spotify), or other features. Do not modify bloom/shader settings, the voice singleton pattern, or the personality file without being asked. Daniel views at 80% Chrome zoom, timezone America/Detroit.
