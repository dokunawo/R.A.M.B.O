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
Last 14 days — 53 commits:

- `6179eed Auto-load rambo-backend/.env on startup (6 minutes ago)`
- `4bdd746 Tier 5 — handoff system (propose, don't chain) (17 minutes ago)`
- `6fe3149 Tier 4 — tool-level human-in-the-loop confirmation gates (20 minutes ago)`
- `c685b5b Extended 1h cache TTL to survive sparse traffic (4 hours ago)`
- `ce3bc5c Add prompt caching across the sub-agent team (4 hours ago)`
- `96bc0c3 Tier 1 smart routing (LLM router) + close Tier 3 failure-isolation hole (4 hours ago)`
- `13ee09b Note Factory dispatch substring-match risk as known issue in roadmap (4 hours ago)`
- `4db7acf Wire spawned-agent dispatch into orchestrator + mount FactoryDock everywhere (4 hours ago)`
- `1d0eeae Add Factory approval UI + document Factory in roadmap/README (4 hours ago)`
- `df21089 Add Factory sub-agent spawner (5-tier config-driven agent system) (6 hours ago)`
- `dd3e1b7 Cost dashboard: live LLM token usage and cost tracking (7 hours ago)`
- `d0f7518 Voice streaming, self-knowledge system, roadmap and README updates (7 hours ago)`
- `cf495c9 Shared HUD on all pages, Learning Log redesign, remove ChromaticAberration (9 hours ago)`
- `1ba1078 Fix mic button overlap, neon glass response popups (9 hours ago)`
- `fa0a3f5 Add percentage-based volume control with voice commands (10 hours ago)`
- `45c08fb Replace SplashScreen custom mic/sound buttons with VoiceControls component (10 hours ago)`
- `e105a20 Bottom-center mic button, response card polish, glass on splash controls (10 hours ago)`
- `521d5cf Apply glass-morphism across all UI panels (10 hours ago)`
- `ea349c4 Add glass-morphism and teal CSS variables to :root (10 hours ago)`
- `adb6f94 Add Trillion UI adaptation implementation plan (10 hours ago)`
- … and 33 more
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
