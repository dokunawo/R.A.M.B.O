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
Last 14 days — 99 commits:

- `b3194fd feat: sound on by default + Settings panel with Sound toggle (9 minutes ago)`
- `cff3b2b feat: clear-all-responses action (button + voice) on all pages (20 minutes ago)`
- `36477a6 fix: never surface ask-frequency / repeat-count to the operator (2 hours ago)`
- `3112cec feat: voice UX overhaul — Operator wake word, reliable mic stop/pause, agent-page cost chips (2 hours ago)`
- `06a22e7 feat: ElevenLabs voice-credit tracker chip (top-right, below API cost) (4 hours ago)`
- `4edbecb docs: design for ElevenLabs voice-credit tracker (4 hours ago)`
- `16a9c57 feat: bump R.A.M.B.O version III -> V via single RAMBO_VERSION constant (4 hours ago)`
- `89b0c63 fix: console plays ElevenLabs voice, pin R.A.M.B.O name, remove dispatch beams (4 hours ago)`
- `825e783 feat: add converse target + prefer action over clarifying (5 hours ago)`
- `f53d45a docs: document ELEVENLABS_* env vars in .env.example (6 hours ago)`
- `396c256 feat: play ElevenLabs segment audio and pulse orb to RAMBO voice (6 hours ago)`
- `7aaa70b feat: initialize ElevenLabs TTS on startup when API key present (6 hours ago)`
- `585da0c feat: attach ElevenLabs segment audio to speak_segment (best-effort) (6 hours ago)`
- `5097876 feat: add ElevenLabsTTS best-effort client (6 hours ago)`
- `2afd7e6 docs: implementation plan for ElevenLabs neural voice (6 hours ago)`
- `e0a94ac docs: design for ElevenLabs neural voice (6 hours ago)`
- `ef630e5 fix: dedicated completed-rows query + elapsed annotation in dispatch context (7 hours ago)`
- `feb1e11 fix: make dispatch-repo helpers resilient to missing attribute (streaming regression) (7 hours ago)`
- `3c93d04 feat: initialize DispatchRepo on startup and attach to orchestrator (7 hours ago)`
- `7b53f24 feat: inject dispatch context into router and voice (7 hours ago)`
- … and 79 more
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
