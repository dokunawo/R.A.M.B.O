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
| web_search | seeker | match, search the web, web search, search online, look online, look up… |
| codebase | seeker | match, what changed, what did we change, what did we just, recent changes, recent commits… |
| notify | echo | match, email me, notify me, send me an email, send an email, email this… |
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
Last 14 days — 120 commits:

- `ee769d3 Voice always-on, reliable screen-share auto-start, intro sound fix (24 minutes ago)`
- `24d4ffa Remove start-dev.ps1 — dev frontend retired from everyday use (53 minutes ago)`
- `e3c9403 Spotify control, screen-vision UX, startup + dev/prod fixes (57 minutes ago)`
- `1ea1d61 Self-coding lane: closed-loop TDD, playbooks, container git access (9 hours ago)`
- `5bebcad Spotify: paginate Liked Songs, fix next/prev pause, context-aware play (#6) (9 hours ago)`
- `2b264b5 Add Spotify integration, screen vision, and HUD polish (#5) (10 hours ago)`
- `f6da9f6 docs: reflect consolidated agent roster in README (10 hours ago)`
- `268dbf9 Add smarter-memory bundle: temporal resolution, confidence scoring, hybrid recall, nightly reflection (11 hours ago)`
- `b8d3f1e Fix stale roster test: assert consolidated mode name, not old shell agent (#4) (13 hours ago)`
- `cd9fe40 Voyage embeddings layer: semantic routing, dispatch digestion, Keeper knowledge graph (#3) (14 hours ago)`
- `55a3a2f Add codebase skill: R.A.M.B.O can read its own repo (15 hours ago)`
- `ef7df1b Consolidate remaining UI surfaces to 3-mode lineup (15 hours ago)`
- `34a640e Consolidate agent fleet into 3 routable modes + services (15 hours ago)`
- `a515392 chore: add self-coding-agent plan + phase1 harness, update HANDOFF (25 hours ago)`
- `78e8835 docs: 06-24 roadmap + README update (voice, agent backends, morning brief) (25 hours ago)`
- `99a5b7b feat: recurring morning brief (on-screen card + email) (25 hours ago)`
- `e6206ec fix: route email/notify intents to Echo (notify skill), not converse (25 hours ago)`
- `0f9cf33 feat: connect agent backends — Seeker web search, Echo email, integration health (25 hours ago)`
- `7851539 feat: wire Keeper agent to real storage + remove dead dict stub (26 hours ago)`
- `56c5881 feat: real SQLite persistence for Keeper (write/read/query/confirm + REST) (26 hours ago)`
- … and 100 more
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
