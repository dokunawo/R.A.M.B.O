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
Last 14 days — 285 commits:

- `e678187 feat(betting): tier-aware latest_props (standard default, per-tier dedup) (4 minutes ago)`
- `32ce83d docs(betting): correct tier spec — snapshot_key must include odds_type (5 minutes ago)`
- `560541e feat(betting): ingest all PrizePicks tiers (goblin/standard/demon) (10 minutes ago)`
- `b8b6837 feat(betting): add prop_lines.odds_type column; _insert_prop writes it (16 minutes ago)`
- `0d83704 docs(betting): PrizePicks demon/goblin tier board implementation plan (20 minutes ago)`
- `23f3d1a docs(betting): PrizePicks demon/goblin tier board design spec (23 minutes ago)`
- `6f6e97c feat(betting): auto-fallback to paid PrizePicks actor when free pull empty (43 minutes ago)`
- `59cc3f2 feat(betting): wire prizepicks_paid source; verify normalizer flow-through (47 minutes ago)`
- `2afa030 feat(betting): fetch_mlb_props_paid — spend-guarded run + never-raise (51 minutes ago)`
- `ecfc127 feat(betting): defensive adapter for paid PrizePicks actor items (55 minutes ago)`
- `e96985b feat(betting): env-driven paid PrizePicks Apify actor config (58 minutes ago)`
- `2284651 docs(betting): PrizePicks paid Apify fallback implementation plan (60 minutes ago)`
- `0ca00f5 docs(betting): PrizePicks paid Apify fallback design spec (63 minutes ago)`
- `ad0a464 fix(betting): default best-leg book to "" not "FanDuel" to avoid mislabel (87 minutes ago)`
- `b27056c test(phase3): force web-search fallback in news/finance skill tests (2 hours ago)`
- `06b91fd fix(betting): guard post_alt_k_parlay against board failures and empty sizes (2 hours ago)`
- `06d27a5 feat(betting): /alt-k-board + /alt-k/parlay endpoints (2 hours ago)`
- `065e0d6 feat(betting): alt-K parlay auto-suggest + manual assembly (2 hours ago)`
- `08d24d6 feat(betting): alt-K slate board (ranked starters + priced thresholds) (2 hours ago)`
- `07d4729 feat(betting): join k_model ladder to alt-K odds (FanDuel + best book) (2 hours ago)`
- … and 265 more
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
