# R.A.M.B.O — PROJECT ROADMAP
**Responsive Autonomous Multi-Brain Operator**
Created: 06/24/2026 at 14:26 (supersedes ROADMAP 06/23/2026 06:30)

---

## Session: 06/24/2026 — Real voice, connected agent backends, persistence

The system went from "voice loop with stub agents" to a genuinely connected
operator: a neural voice, durable memory, live web search, real email, and a
recurring morning brief. Everything below is shipped, tested, and on `main`.

### Borrowed-pattern groundwork (06/24/2026)
| Feature | Status |
|---|---|
| **Persistent dispatch memory** — `DispatchRepo` (SQLite `data/dispatch.db`), logs every routed goal; `format_for_prompt()` feeds "currently working on / recently completed" back into router + voice | Done |
| **Fast/deep model split** — `model_config.fast_model()` (Haiku) for routing; Sonnet for voice + agents. Env `RAMBO_FAST_MODEL` | Done |

### Voice overhaul (06/24/2026)
| Feature | Status |
|---|---|
| **ElevenLabs neural voice** — `tts.py` (`ElevenLabsTTS`), per-segment synthesis attached to `speak_segment` WS messages; browser-voice fallback when unavailable | Done |
| Frontend Web-Audio playback + AnalyserNode → orb pulses to R.A.M.B.O's own voice | Done |
| **`/console` now speaks via ElevenLabs** (was browser `speechSynthesis`); dropped the "is there anything else?" suffix | Done |
| **Wake word → "Operator"** (browser STT misheard "Rambo" badly); fuzzy variants | Done |
| **Reliable mic control** — hard-off button (persisted) + soft "stop listening" voice pause that stays wake-gated and resumes on the wake word | Done |
| Recognizer **watchdog** auto-recovers from STT degradation (no more mic re-click) | Done |
| Cross-instance speak **dedup** + audio-context unlock → fixed the ElevenLabs-then-browser double voice | Done |

### UI / HUD (06/24/2026)
| Feature | Status |
|---|---|
| Version bump **MK III → MK V** (single `RAMBO_VERSION` constant) | Done |
| **ElevenLabs voice-credit tracker** chip (`/usage/tts`) — remaining + used/limit, REAL/LIVE source; real balance via ElevenLabs subscription API | Done |
| Cost chips (API + VOICE) moved **top-right**, stacked; added to every agent page | Done |
| **Clear-all-responses** — button + "clear everything" voice command, all pages | Done |
| **Sound on by default** — auto-enable on first interaction; ⚙ **Settings panel** with Sound On/Off toggle | Done |
| **Command-center voice trigger** — "Operator, command center" navigates to `/console`, all pages | Done |
| Removed the orb→agent dispatch beam + the constant ambient console hum | Done |

### Agent backends — connected (06/24/2026)
| Agent | Backend | Status |
|---|---|---|
| **Seeker** | Anthropic native `web_search` skill (uses `ANTHROPIC_API_KEY`, no extra key) + Open-Meteo weather | **LIVE** |
| **Keeper** | Real SQLite `KeeperRepo` (`data/keeper.db`); spoken "remember X is Y" / "what is my X" persist + recall across restarts | **CONNECTED** |
| **Link** | Google OAuth (calendar/drive); `get_credentials()` now surfaces failures; `integration_status()` reports CONNECTED/DEGRADED/OFFLINE | **CONNECTED** |
| **Echo** | SMTP email (`echo_messaging.py`, env-gated) + `notify` skill; "email me X" sends a real email | **CONNECTED** (Gmail) |
| `GET /agents/health` · `GET /integrations/status` — per-agent LIVE/CONNECTED/OFFLINE | Done |
| Routing policy forces **memory → keeper** and **messaging → echo** (was non-deterministic) | Done |
| Removed dead `memory/sqlite_store.py` in-memory dict stub | Done |

### Recurring morning brief (06/24/2026)
| Feature | Status |
|---|---|
| Daily scheduler (`morning_brief.py`) at `MORNING_BRIEF_TIME` (default 07:00 `America/Detroit`) | Done |
| Brief = date + today's Google calendar + doctrine priorities (when `north-star.md` exists) | Done |
| Displays on screen as an Architect response card (activity WS) **and** emails via Echo | Done |
| `POST /brief/run` — trigger on demand | Done |

---

## What's Next

### Short Term
- **Echo channels** — add push/SMS alongside email if desired (Twilio).
- **Keeper recall in context** — inject stored memories into the prompt for cross-session recall beyond keyword match.
- **Cleanup** — retire the remaining stub `execute()` agents (Architect/Engineer/Analyst/Link) or give them real handlers; remove the no-op `_web_search` factory placeholder.

### Mid Term
- **Self-coding agent** — RAMBO writes/reviews/modifies its own code via Managed Agents (sandboxed branch→PR). Plan in `docs/PLAN_self-coding-agent.md` (operator-owned, in progress).
- **Alembic migrations** — as the SQLite schemas (usage/dispatch/tts/keeper) evolve.
- **Morning-brief enrichment** — weather (needs a stored home location), unread mail summary (Gmail scope already granted), Keeper highlights.

### Long Term
- Cloud-hosted personal digital twin that learns the operator and runs open-ended research (the north-star vision).

---

## Endpoints added this session
`POST /keeper` · `GET /keeper` · `GET /keeper/{key}` · `GET /keeper/confirm` ·
`GET /usage/tts` · `GET /agents/health` · `GET /integrations/status` · `POST /brief/run`

## New env vars
`RAMBO_FAST_MODEL` · `ELEVENLABS_API_KEY` · `ELEVENLABS_VOICE_ID` · `ELEVENLABS_MODEL` ·
`ELEVENLABS_MONTHLY_LIMIT` · `SMTP_HOST/PORT/USER/PASS/FROM` · `ECHO_DEFAULT_TO` ·
`MORNING_BRIEF_TIME` · `MORNING_BRIEF_TZ`
