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
| strikeout_watch | seeker | match, strikeout watch, strikeout board, strikeout parlay, strikeout pick, strikeout candidate… |
| hits_tb_watch | seeker | match, hits watch, total bases, total base, hits and total, hits board… |
| resolve_git | seeker | match, push, merge, approve, confirm, deny… |
| git_push | seeker | match, push to github, push to git, push the repo, push the code, push my changes… |
| pr_merge | seeker | match, merge, re, (?:pr|pull\s*request)\s*#?\s*\d+, re |
| git_merge | seeker | match, merge, into, branch |
| delete_build | seeker | match, build, delete, remove, get rid of, throw away… |
| code_review | engineer | match |
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
Last 14 days — 210 commits:

- `0857edf feat(cmc): wire line-shop, prop-shop + CLV into the daily run (71 minutes ago)`
- `8fb2ebb feat(betting): player-prop line shopping — Pick6 vs sportsbook (Odds API props) (81 minutes ago)`
- `14c4c61 feat(betting): backtest groundwork — results backfill + eval harness (2 hours ago)`
- `1d11a02 feat(betting): CLV tracking — grade moneyline leans against the closing line (2 hours ago)`
- `f4683e2 feat(betting): moneyline line shopping across all books (no new feed) (2 hours ago)`
- `aa94085 feat(hud): push feedback works for voice-staged/approved pushes too (2 hours ago)`
- `0be0b91 feat(hud): push-approval feedback — 'Staged' → 'Pushed ✓' then auto-clears (2 hours ago)`
- `c1ad60d feat(betting): prop→game linking + team confirmation; harden Pick6 MLB filter (3 hours ago)`
- `baf4ac6 feat(ui): cinematic shutdown/standby sequence + tabbed task-history panel (3 hours ago)`
- `76d71bd feat(dev-lane): full-suite test gate before a self-change merge (4 hours ago)`
- `d4331e1 feat(skills): voice self-review — "Operator, review the auth module" (5 hours ago)`
- `58177b5 feat(briefing): spoken briefing reads every section, not just a terse summary (5 hours ago)`
- `69fed12 feat(ui): boot briefing fires after Phase 2 cascade, as one spoken sequence (5 hours ago)`
- `c59b003 feat(ui): /boards page — all four parlay boards on one screen (8 hours ago)`
- `759d304 feat(ev): Hits & Total Bases Watch — P(1+ hit)/P(2+ TB) board for hits parlays (9 hours ago)`
- `5dadebe feat(ev): Strikeout Watch — top-11 starters by P(8+/9+/10+ K) for alt-K parlays (9 hours ago)`
- `5ac5d75 feat(ui): GIT dock — stage push / branch merge / PR merge from the rail (16 hours ago)`
- `8ffe00a feat(git): operator-approved merges — local branch + GitHub PR (20 hours ago)`
- `824b59b feat(git): operator-approved GitHub push (commit + push behind a confirm gate) (20 hours ago)`
- `fc90ed9 feat(builds): auto-generate run.bat/run.sh launchers so builds run without IDLE (20 hours ago)`
- … and 190 more
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
