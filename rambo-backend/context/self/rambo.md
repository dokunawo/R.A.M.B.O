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
| news | seeker | match, news, headline, headlines, what's happening, whats happening… |
| finance | seeker | match, stock, stocks, share price, stock price, market… |
| gmail | echo | match, email, emails, inbox, gmail, unread… |
| smart-home | link | match, turn on, turn off, switch on, switch off, the lights… |
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
Last 14 days — 128 commits:

- `b5f2d5c Jarvis roadmap (Phases 1-4) + proactive watch, domain skills, presence, Spotify fix (9 minutes ago)`
- `b70019d UI: dock rail accordion (one open at a time) + tuned spacing (8 hours ago)`
- `752260e UI: stack left docks in a rail (no overlap) + split volume controls (8 hours ago)`
- `cdec321 Builds: Run / Run-tests buttons + fix brittle reflection test date (9 hours ago)`
- `3d2bb53 Agent status for Spotify/spawned lanes + boot Chrome at 80% zoom (9 hours ago)`
- `1ff262d Engineer builds: standalone build lane, desktop-open, progress bar, volume (16 hours ago)`
- `1a7c41e Gate screen-share boot click on a frontend-ready handshake (17 hours ago)`
- `f3b2045 Front-load the media-key helper in startup so keys work from login (17 hours ago)`
- `ee769d3 Voice always-on, reliable screen-share auto-start, intro sound fix (17 hours ago)`
- `24d4ffa Remove start-dev.ps1 — dev frontend retired from everyday use (18 hours ago)`
- `e3c9403 Spotify control, screen-vision UX, startup + dev/prod fixes (18 hours ago)`
- `1ea1d61 Self-coding lane: closed-loop TDD, playbooks, container git access (26 hours ago)`
- `5bebcad Spotify: paginate Liked Songs, fix next/prev pause, context-aware play (#6) (26 hours ago)`
- `2b264b5 Add Spotify integration, screen vision, and HUD polish (#5) (27 hours ago)`
- `f6da9f6 docs: reflect consolidated agent roster in README (27 hours ago)`
- `268dbf9 Add smarter-memory bundle: temporal resolution, confidence scoring, hybrid recall, nightly reflection (28 hours ago)`
- `b8d3f1e Fix stale roster test: assert consolidated mode name, not old shell agent (#4) (30 hours ago)`
- `cd9fe40 Voyage embeddings layer: semantic routing, dispatch digestion, Keeper knowledge graph (#3) (31 hours ago)`
- `55a3a2f Add codebase skill: R.A.M.B.O can read its own repo (32 hours ago)`
- `ef7df1b Consolidate remaining UI surfaces to 3-mode lineup (32 hours ago)`
- … and 108 more
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
