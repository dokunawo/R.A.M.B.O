# R.A.M.B.O — Responsive Autonomous Multi-Brain Operator

## Identity

R.A.M.B.O is a multi-agent orchestrator that coordinates ten specialist
agents to handle user goals through voice and text. It speaks with a cold,
professional tone — precise, clipped, zero filler. Results first, commentary
after. It is not an assistant; it is an operator.

R.A.M.B.O's long-term trajectory is to become a cloud-based personal digital
twin: one that studies the operator, learns their patterns, and acts on their
behalf across diverse domains — from scheduling and file management to
open-ended research.

## Core Principles

- **Mission first.** Answer the question before adding commentary.
- **Brevity by default.** One or two sentences unless detail was asked for.
- **No filler.** Banned openers: "Great question", "Let me", "Based on",
  "Happy to help", "Of course", "Absolutely", "Certainly".
- **Respect the operator.** Acknowledge sharp calls. Never mock, never belittle.
  Dry is fine, cruel is not.
- **Fail loud.** If a task fails, say so plainly. Do not paper over errors.
- **One source of truth.** Capabilities described here are generated from code.
  If it's not in the registry, R.A.M.B.O doesn't claim it.

## Capabilities at a Glance

<!-- AUTO-START: capabilities -->
| Skill | Routed To | Match Keywords |
| --- | --- | --- |
| weather | seeker | match, weather, temperature, forecast, how hot, how cold |
| calendar | pilot | match, calendar, schedule, event, meeting, appointment… |
| drive | keeper | match, drive, my files, my documents, google doc, find file… |
| chief-of-staff | architect | match, plan my day, morning brief, what should i work on, what should i focus, priorities… |
<!-- AUTO-END: capabilities -->

## Sub-agents

<!-- AUTO-START: subagents -->
| Agent | Role | Status |
| --- | --- | --- |
| Analyst | Analyzes data and produces insights | keyword-matched |
| Architect | Plans goals, breaks them into tasks, assigns to agents | keyword-matched |
| Echo | Summarizes results and polishes output | keyword-matched |
| Engineer | Implements solutions — APIs, components, data models | keyword-matched |
| Keeper | Persists data to memory and storage | keyword-matched |
| Link | Manages external integrations and connections | keyword-matched |
| Pilot | Builds and manages task queues from plans | keyword-matched |
| Seeker | Researches and retrieves information | keyword-matched |
| Sentinel | Reviews tasks for safety, blocks destructive actions | keyword-matched |
| Steward | Handles financial logic and resource management | keyword-matched |
<!-- AUTO-END: subagents -->

## Integrations

<!-- AUTO-START: integrations -->
| Service | Purpose | Status | Config |
| --- | --- | --- | --- |
| Anthropic Claude | Voice layer — LLM for generating spoken responses | configured | `ANTHROPIC_API_KEY` env var |
| Open-Meteo | Weather data — geocoding + forecast (no API key needed) | active | none (free API) |
| Google Calendar | Read/write calendar events | available | `credentials.json` + OAuth token |
| Google Drive | Search and access files in Drive | available | `credentials.json` + OAuth token |
<!-- AUTO-END: integrations -->

## Voice / Streaming Loop

<!-- AUTO-START: voice -->
| Layer | Location | Detail |
| --- | --- | --- |
| LLM streaming | `orchestrator/orchestrator.py:_speak()` | Streaming Anthropic call, per-sentence splitting |
| Transport | `websocket/manager.py` | WebSocket at `/ws/activity` with `broadcast_json` |
| STT | `useVoiceReactivity.js` | Browser-native `SpeechRecognition` |
| TTS | `useVoiceReactivity.js` | Browser-native `speechSynthesis`, segment queue |
| VAD | `useVoiceReactivity.js` | Silence timer (1000ms) triggers final transcript |
<!-- AUTO-END: voice -->

## Recent Activity

<!-- AUTO-START: recent_activity -->
Last 14 days — 70 commits:

- `effbe39 Startup: skip Chrome first-run, auto-grant mic (wake word) + geolocation in the RAMBO profile (13 minutes ago)`
- `ba84f6b Startup: launch RAMBO in a dedicated Chrome profile so fullscreen works even when Chrome is already open (31 minutes ago)`
- `c542188 Remove dead SoundToggle component and its orphaned styles/imports (34 minutes ago)`
- `9f2e0a9 Startup: launch Chrome in a dedicated new window, fullscreen (F11-style) (38 minutes ago)`
- `08b67d0 Long-press the volume button = full reset to unmuted max volume (41 minutes ago)`
- `9103eee Boot always starts unmuted at max volume via ?boot=1 flag (manual refresh preserved) (49 minutes ago)`
- `6d9190f Add SoundGate: one-click 'enable sound' pill when browser autoplay is blocked (53 minutes ago)`
- `816be93 Startup: launch Chrome with autoplay allowed so the intro sound plays on boot (61 minutes ago)`
- `0cec625 Roadmap: note true AEC/barge-in voice follow-up (65 minutes ago)`
- `63c6ce2 Voice: half-duplex echo suppression so TTS output isn't transcribed as a command (76 minutes ago)`
- `fd93ab8 Default startup to prod frontend (:3000); add -Dev switch for hot-reload (:3001) (81 minutes ago)`
- `2816c24 Update roadmap and README: orchestration tiers 4-5, caching, go-live fixes, startup, mic redesign (86 minutes ago)`
- `90e223e Add nginx SPA fallback (fix deep-link/refresh 404s) + red blocked-mic ring (2 hours ago)`
- `845155b Redesign mic button (glass + gold glow) and surface a visible mic-blocked state (2 hours ago)`
- `934c999 Add rambo-startup.ps1: seamless boot (wait for Docker, compose up, wait for frontend, open browser) (2 hours ago)`
- `0da4e4b Fix two bugs blocking live model calls; centralize model id (2 hours ago)`
- `db6070c Frontend docks for confirmation gate (Tier 4) and handoffs (Tier 5) (3 hours ago)`
- `6179eed Auto-load rambo-backend/.env on startup (3 hours ago)`
- `4bdd746 Tier 5 — handoff system (propose, don't chain) (3 hours ago)`
- `6fe3149 Tier 4 — tool-level human-in-the-loop confirmation gates (3 hours ago)`
- … and 50 more
<!-- AUTO-END: recent_activity -->

## Open Questions / Unknowns

- How should R.A.M.B.O persist learned user preferences across sessions?
- What is the right boundary between "skill" and "agent" as capabilities grow?
- When agents become LLM-powered, how do they negotiate conflicting plans?

## Pointers

- [AGENT.md](../../AGENT.md) — personality definition and tonal rules
- [north-star.md](../../north-star.md) — project vision and roadmap
- [skills.py](../../skills.py) — skill registry (add new real-world capabilities here)
- [orchestrator.py](../../orchestrator/orchestrator.py) — agent registry and voice pipeline
