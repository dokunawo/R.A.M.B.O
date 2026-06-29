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
Last 14 days — 233 commits:

- `4782c70 Apply 6 minor code review fixes: explicit None checks for ERA (0.00 ERA), defensive empty-X guard in logreg.fit, docstring for coefficients standardization note, backtest verdict dict safety, remove redundant TestClient import, and last_fit_date assertion. (24 minutes ago)`
- `070e6e2 chore(betting): record learned-model May backtest vs baseline (3 hours ago)`
- `a1e5993 feat(betting): model param on /backtest + side-by-side compare CLI (3 hours ago)`
- `baba5b1 refactor(betting): walkforward.run takes a pluggable predictor (3 hours ago)`
- `99e03ee feat(betting): Anchored + LogReg predictors (3 hours ago)`
- `1db8f5c feat(betting): point-in-time features + training-set builder (3 hours ago)`
- `88d6727 feat(betting): pure-Python logistic regression (zero deps) (3 hours ago)`
- `ff8e1c6 docs(betting): implementation plan for learned moneyline model (3 hours ago)`
- `5343cf4 docs(betting): spec learned moneyline model (3 hours ago)`
- `6478758 Fix walkforward boundary string normalization and remove unused imports (13 hours ago)`
- `872843d Fix The Odds API historical endpoint timestamp normalization (13 hours ago)`
- `2384d3c feat(betting): /betting/backtest endpoint + walkforward CLI (13 hours ago)`
- `ece5335 feat(betting): walk-forward moneyline backtest harness (13 hours ago)`
- `177ec49 feat(betting): two-snapshot historical odds backfill (13 hours ago)`
- `a5065d5 feat(betting): historical moneyline fetch via The Odds API (13 hours ago)`
- `9131a92 feat(betting): evaluate_game_asof — point-in-time moneyline eval (13 hours ago)`
- `d339260 Fix pitcher_era_asof season filter leak (14 hours ago)`
- `c28e0be feat(betting): point-in-time team_runs_asof + pitcher_era_asof (14 hours ago)`
- `b8f6964 docs(betting): implementation plan for walk-forward backtest (14 hours ago)`
- `ceb2cc7 docs(betting): grade ROI at early + closing line side by side (14 hours ago)`
- … and 213 more
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
