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
| system_update | seeker | match, give me an update, an update, catch me up, system status, status report… |
| resolve_push | seeker | match, push, approve, confirm, deny, cancel… |
| git_push | seeker | match, push to github, push to git, push the repo, push the code, push my changes… |
| delete_build | seeker | match, build, delete, remove, get rid of, throw away… |
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
Last 14 days — 191 commits:

- `fc90ed9 feat(builds): auto-generate run.bat/run.sh launchers so builds run without IDLE (12 minutes ago)`
- `e1f3a1a docs: build naming, build deletion, quieter hand-offs (guide/README/roadmap) (23 minutes ago)`
- `66a571d feat(builds): short build names, delete capability, Engineer-only handoff mentions (25 minutes ago)`
- `305ed00 docs: boot briefing + "catch me up" in operator guide, README, roadmap (49 minutes ago)`
- `102d999 feat(briefing): boot briefing card + on-demand "catch me up" update (51 minutes ago)`
- `93589ae docs: operator guide + README + roadmap for Player Watch, Moneyline Board, daily run, startup lock (2 hours ago)`
- `b44e708 feat(ev): Player Watch is slate-wide with our leans pinned at top (2 hours ago)`
- `1d67c70 fix(startup): single-instance lock so RAMBO never opens two Chrome windows (2 hours ago)`
- `a2d0d6b test(ev): honesty omit-when-absent coverage + import cleanup (2 hours ago)`
- `cfe3eab chore: gitignore generated CMC daily docs + Office temp files (3 hours ago)`
- `bd9fcaa feat(cmc): add Player Watch + Moneyline Board to the daily script + doc (3 hours ago)`
- `d2393ca feat(ev): /betting/player-watch + /betting/moneyline-board endpoints (3 hours ago)`
- `ea16e0b feat(ev): moneyline_board (full slate) builder + prompt (3 hours ago)`
- `7528670 feat(ev): player_watch (top-11 HR board) builder + prompt (3 hours ago)`
- `ed64a57 feat(ev): MlbRepo player_bats + player_name getters (3 hours ago)`
- `e522c67 docs(ev): clarify build_slip docstring + ml sort-sentinel comments (3 hours ago)`
- `b2d1f38 feat(ev): ml daily-edge + slip ordered by game time (3 hours ago)`
- `c860d9b feat(ev): shared evaluate_game + Pick game_pk/game_datetime (3 hours ago)`
- `1f4032e feat(ev): capture games.game_datetime + order moneyline slate by first pitch (3 hours ago)`
- `3bffa8b docs: implementation plan for Player Watch + Moneyline Board (3 hours ago)`
- … and 171 more
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
