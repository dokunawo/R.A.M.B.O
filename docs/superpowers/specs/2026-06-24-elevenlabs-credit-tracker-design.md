# Design: ElevenLabs Voice-Credit Tracker + Cost Chips Moved Top-Right

**Date:** 2026-06-24
**Status:** Approved (design), pending implementation plan

## Background

R.A.M.B.O now speaks with an ElevenLabs neural voice. The HUD already has an
API-cost chip (`CostIndicator` + `useCostDashboard`, backed by `/usage`) showing
Anthropic spend. The operator wants a parallel chip for ElevenLabs **voice
credits**, placed directly below the API chip, with both chips moved from the
crowded top-left to the top-right (under the Council-view / date / time row).

Constraint: the operator's ElevenLabs API key currently has only the **Text to
Speech** permission, not **User: Read**, so the subscription/balance endpoint
returns 401. The chosen approach is **Both**: always track usage locally, and
additionally show the real ElevenLabs balance when the User:Read permission is
present, falling back to local otherwise.

## Goals

- Track ElevenLabs character usage locally (month-to-date) and display credits
  remaining plus used/limit.
- When User:Read is granted, show the real ElevenLabs balance; otherwise fall
  back to the local count — gracefully, with no errors.
- Move the API chip and the new voice chip into a vertical stack, top-right,
  under the topbar row.

## Non-Goals

- No change to how synthesis itself works (that is the existing `tts.py`).
- No historical charts for voice usage — a single month-to-date counter only.
- No automatic plan/tier detection beyond reading the subscription endpoint when
  permitted.

## Architecture

### Backend

**New `rambo-backend/tts_usage_repo.py`** — mirrors `usage_repo.py` (async
`aiosqlite`, `data/tts_usage.db`, idempotent `init_db`):

```sql
CREATE TABLE IF NOT EXISTS tts_usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    characters INTEGER NOT NULL DEFAULT 0,
    model      TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tts_usage_created_at ON tts_usage(created_at);
```

API:
- `async record(characters: int, model: str = "") -> None`
- `async characters_since(start: str, end: str | None = None) -> int` — SUM of
  `characters` in the window (0 when empty).

**Recording the usage** — `TTSUsageRepo` is injected into the orchestrator via a
new `set_tts_usage_repo(repo)` setter (same pattern as `set_dispatch_repo` /
`set_tts`). In `_segment_audio`, after `data = await tts.synthesize(text)`
succeeds (truthy), best-effort `await repo.record(len(text), model)`; read the
repo via `getattr(self, "tts_usage_repo", None)` and swallow all errors so a turn
never breaks. No record on failure/None.

**Real balance** — add to `tts.py`:
`async def get_subscription(api_key: str | None) -> dict | None`. GETs
`https://api.elevenlabs.io/v1/user/subscription` with header `xi-api-key`. On
HTTP 200 returns `{"used": character_count, "limit": character_limit}`; on
missing key, non-200 (e.g. 401 when User:Read absent), or any exception returns
`None`. Best-effort, never raises.

**`/usage/tts` endpoint** (FastAPI, `main.py`) returns:

```json
{
  "local": { "used": <mtd chars>, "limit": <env limit>, "remaining": <limit-used> },
  "real":  { "used": <int>, "limit": <int>, "remaining": <int> } | null,
  "source": "real" | "local",
  "reset_date": "<ISO date of next month start>"
}
```

- `limit` from env `ELEVENLABS_MONTHLY_LIMIT` (default `10000`, the free tier).
- `used`/month-to-date computed from `characters_since(month_start)` (UTC,
  mirroring `usage_dashboard.py`'s month boundary).
- `real` populated from `get_subscription` when available; `source` is `"real"`
  if `real` is non-null else `"local"`.
- Best-effort: the endpoint never 500s; on any backend hiccup it returns the
  local block with `real: null`.

### Frontend

**`useElevenLabsUsage()`** in `SharedHUD.js` — mirrors `useCostDashboard`: polls
`${API}/usage/tts` on mount, every 60s, and on tab re-focus; returns the JSON or
`null`.

**`VoiceCostIndicator({ data })`** in `SharedHUD.js` — mirrors `CostIndicator`:
- Chooses the display block: `data.real ?? data.local`.
- Face: tag `VOICE`, primary number = `remaining` formatted compactly
  (e.g. `1.6k`), plus `used/limit` (e.g. `8.4k/10k`) in a smaller span. A tiny
  source tag reads `REAL` when `data.source === "real"` else `LIVE`.
- Expandable panel (same `hud-cost-*` classes): rows for Remaining, Used, Limit,
  Resets (reset_date), and Source.
- Returns `null` while `data` is null.
- A `formatK(n)` helper renders thousands as `1.6k`, small numbers as-is.

**Layout** — introduce a `hud-cost-stack` wrapper positioned top-right (under the
topbar). Render `<CostIndicator>` then `<VoiceCostIndicator>` inside it in
`SplashScreen.js` (replacing the current standalone `<CostIndicator>` placement).
The existing `hud-cost-wrap` chips keep their internal styles; the stack handles
position (absolute, top-right, below the topbar row) and vertical spacing. CSS
lives wherever `hud-cost-*` is currently defined (SharedHUD.css / App.css).

## Data Flow

```
synth success in _segment_audio
   └─ tts_usage_repo.record(len(text), model)        [best-effort]

HUD poll → GET /usage/tts
   ├─ local: characters_since(month_start) vs ELEVENLABS_MONTHLY_LIMIT
   └─ real:  get_subscription(key)  (null if no User:Read permission)
        └─ VoiceCostIndicator shows real ?? local, tagged REAL/LIVE
```

## Error Handling

| Condition | Result |
|-----------|--------|
| No `ELEVENLABS_API_KEY` | no synth happens; chip shows local (0 used) |
| User:Read not granted (401 on subscription) | `real: null`, `source: "local"`, chip shows local count |
| Subscription network error | `real: null`, falls back to local |
| `tts_usage_repo` absent/None | recording is a no-op; chip shows 0 used |
| `/usage/tts` backend error | returns local block, `real: null`; never 500 |

## Testing

**Backend (pytest):**
- `tts_usage_repo`: schema/columns; `record` then `characters_since` sums
  correctly; window filtering (a row before `start` is excluded); empty → 0;
  `init_db` idempotent.
- `get_subscription`: returns `None` with no key; on mocked httpx 200 returns
  `{"used","limit"}` from `character_count`/`character_limit`; on mocked 401 and
  on exception returns `None`.
- Orchestrator: a successful `_segment_audio` (stub tts returning bytes) records
  `len(text)` to a stub repo; a `None`-returning tts records nothing; missing
  repo is a no-op (and `__new__`-built orchestrator does not raise).
- `/usage/tts`: with a seeded repo returns the documented shape and correct
  `source`; with `real` available `source == "real"`.

**Frontend:** verified in the browser — the VOICE chip renders under the API chip
top-right, shows remaining + used/limit, the panel expands, and the number moves
after R.A.M.B.O speaks.

## Risk / Rollback

- Fully additive. The new endpoint, repo, and chip are independent; if
  `tts_usage_repo` is never wired the orchestrator behaves exactly as today and
  the chip simply shows 0 used / full remaining.
- The subscription call is best-effort and off by default (no permission), so it
  cannot break the HUD.
- Moving the chips is a CSS/placement change; reverting restores the old
  top-left position.
