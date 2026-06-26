# R.A.M.B.O — Operator Guide

A plain-English manual: what each part does, what each port is for, how to start /
stop / reload things, and how to use the main features. Keep this handy.

---

## 1. The 30-second mental model

R.A.M.B.O runs as **three Docker containers**:

| Container | Port | What it is |
|---|---|---|
| `rambo-backend` | **8000** | The brain — FastAPI (Python). All the logic, agents, voice, memory, and the new self-coding lane. Everything talks to it. |
| `rambo-frontend` | **3000** | The **production** UI (built once, served fast). Use this for the "real" kiosk display. |
| `rambo-frontend-dev` | **3001** | The **development** UI (hot-reloads on every code save). Use this while changing the frontend. |

So: **open `http://localhost:3000`** for the normal experience, or **`http://localhost:3001`** if you're actively editing the React code and want changes to appear instantly. Both talk to the same backend on **8000**.

> **Why two frontends?** 3000 is the polished, fast version. 3001 is the "live editing" version that rebuilds itself when you save a file. They're otherwise identical.

---

## 2. Starting, stopping, and reloading

All commands run from the project root: `C:\Users\dokun\PycharmProjects\R.A.M.B.O`.

### The easy way (PowerShell scripts)
| Script | Does |
|---|---|
| `.\rambo-startup.ps1` | Full boot: waits for Docker, brings the stack up, waits for the frontend, opens the browser. (Register at login for one-and-done boot.) |
| `.\start-dev.ps1` | Bring the stack up for development. |
| `.\start-prod.ps1` | Bring the stack up in production mode. |
| `.\rambo-control-panel.ps1` | Interactive 7-step boot / health-scan / rebuild / browser-launch control panel. |

### The direct way (Docker Compose)
| Goal | Command |
|---|---|
| See what's running | `docker compose ps` |
| Start everything | `docker compose up -d` |
| Stop everything | `docker compose down` |
| **Restart the backend** (pick up `.py` you changed when auto-reload didn't) | `docker compose restart rambo-backend` |
| **Recreate the backend** (after editing `docker-compose.yml` — mounts/env) | `docker compose up -d rambo-backend` |
| **Rebuild the backend image** (after editing `requirements.txt` or the Dockerfile) | `docker compose build rambo-backend` then `docker compose up -d rambo-backend` |
| Rebuild the production frontend (3000) after frontend code changes | `docker compose build rambo-frontend` then `docker compose up -d rambo-frontend` |
| Watch backend logs live | `docker compose logs -f rambo-backend` |

### When do I need to reload? (this trips everyone up)
- **Backend Python edit** (`rambo-backend/*.py`) → **auto-reloads.** Uvicorn runs with `--reload` watching `/app`. Just save; the server restarts itself in ~1s. (If it didn't catch it: `docker compose restart rambo-backend`.)
- **Backend dependency change** (`requirements.txt`) → **rebuild the image** (it's baked in, not live-mounted): `docker compose build rambo-backend && docker compose up -d rambo-backend`.
- **`docker-compose.yml` change** (ports, mounts, env vars) → **recreate**: `docker compose up -d rambo-backend` (a plain `restart` won't apply mount/env changes).
- **Frontend edit while on 3001 (dev)** → **auto-reloads.** Save and the page recompiles.
- **Frontend edit you want on 3000 (prod)** → **rebuild**: `docker compose build rambo-frontend && docker compose up -d rambo-frontend`.

> **"unhealthy" but it works?** The backend's Docker healthcheck can read *unhealthy* even when the API responds fine (a healthcheck quirk). Test the truth with: `curl http://localhost:8000/` — a `200` means it's up regardless of the health label.

---

## 3. The keys it needs (`rambo-backend/.env`)

| Variable | Unlocks | Required? |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Everything intelligent** — the personality voice, the router, the agents, the self-coding lane. The master key. | **Yes** (set) |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | The neural spoken voice (falls back to the browser voice without it). | Optional |
| `VOYAGE_API_KEY` | The semantic embeddings layer (smarter routing/memory). | Optional |
| Google OAuth (`credentials.json` / `token.json`) | Calendar + Drive (the Link agent) and the morning brief. | Optional |
| `SMTP_*` / `ECHO_DEFAULT_TO` | Real email sending (the Echo agent). | Optional |

After changing `.env`, **restart the backend** so it re-reads them: `docker compose restart rambo-backend`.

---

## 4. What each feature does + how to use it

### Voice + the orb
- **Wake word: "Operator"** (not "Rambo" — the browser kept mishearing it). Say "Operator", then your command.
- The glowing **cosmic orb** is the interface centerpiece; it pulses to RAMBO's own voice.
- Handy voice commands: **"command center"** (opens the console), **"clear everything"** (clears responses), **"stop listening"** (pauses the mic; resumes when you say the wake word again), **"remember X is Y"**, **"email me X"**.
- Mic control: a **hard-off button** (stays off across refreshes) and the soft "stop listening" pause.

### The agents (who does what)
RAMBO routes your request to the right capability automatically:
- **Seeker** — live web search + weather.
- **Keeper** — durable memory. "Remember my X is Y" / "what is my X" persist across restarts.
- **Link** — Google calendar/drive (needs Google auth).
- **Echo** — sends real email (needs SMTP).
- **Sentinel** — a security gate; risky actions get held for your approval.
- Plus the **Factory** (below) and the **self-coding lane** (section 5).

### Morning brief
A daily scheduler composes a brief (date + today's calendar + priorities) and both shows it on screen and emails it. Trigger on demand: `POST /brief/run`. Schedule via `MORNING_BRIEF_TIME` / `MORNING_BRIEF_TZ`.

### Cost + voice-credit tracking
Top-right chips show **API token cost** and **ElevenLabs voice credits** in real time. Click to expand for a per-model breakdown.

### Factory (RAMBO builds *helper agents*)
Ask RAMBO to spawn a specialist agent; it researches the role, drafts a system prompt, and **stages it for your approval** in the **Factory dock** (left side). You approve/reject; approved agents become callable with no restart. *This is different from the self-coding lane — the Factory makes new agents; the self-coding lane edits RAMBO's actual source code.*

### Approval docks (left side of the screen)
Small collapsible panels that hold things waiting for your decision:
- **FACTORY** — proposed new agents.
- **CONFIRM** — risky tool actions paused for approval.
- **HANDOFF** — proposed agent-to-agent handoffs.
- **CODE REVIEW** — proposed self-code changes (section 5).

---

## 5. The self-coding lane (newest + most powerful) — how to use it

This lets RAMBO **read, write, test, and review changes to its own source code** — but it **never edits the running app directly.** Everything happens on an isolated, throwaway git branch, and **nothing reaches `main` until you approve it.**

### How it works, step by step
1. **You ask** for a code change (e.g. "RAMBO, add an endpoint that returns the current time") — by voice/console, or directly: `POST http://localhost:8000/dev/propose` with `{"goal": "..."}`.
2. **RAMBO drafts it** in an isolated git **worktree** (a separate copy on a `rambo/dev-*` branch). It follows engineering playbooks: writes a **test**, runs it and watches it **fail**, writes the code, runs the test again and watches it **pass**.
3. **It analyzes the change** and gives a recommendation: **MERGE** (safe), **ASK CLAUDE** (wants a second opinion), or **HOLD** (not ready).
4. **You review it** in the **CODE REVIEW dock** (left side): open the card to see the **diff**, what it affects, and the recommendation. Then click:
   - **MERGE** → applies it to `main` locally.
   - **SEND TO CLAUDE** → writes the change to `rambo-backend/data/escalations/` for you to review in a Claude Code session.
   - **REJECT** → throws the branch away.
5. **After a merge:** if the change touched backend code, uvicorn auto-reloads it. (Otherwise restart the backend to make it live.)

### The safety guarantees (why this is safe)
- The agent's file tools are **physically confined** to the throwaway worktree — it can't touch the live code.
- It **only commits the files it actually changed** (no accidental extras).
- A merge is **blocked** if it would clobber files you have uncommitted edits in.
- **You** are the only one who merges. RAMBO never merges itself.

### Useful endpoints (for testing without the UI)
| Endpoint | Does |
|---|---|
| `POST /dev/propose` `{"goal": "..."}` | Start a self-coding draft. Returns a change id. |
| `GET /dev/pending` | List changes waiting for review. |
| `GET /dev/change/{id}` | The full diff + impact + recommendation. |
| `POST /dev/merge/{id}` | Merge it into `main` (local). |
| `POST /dev/reject/{id}` | Discard it. |
| `POST /dev/escalate/{id}` | Save it for a Claude review. |

### Dev-lane settings (env vars, optional)
- `RAMBO_DEV_PLAYBOOKS` — which engineering disciplines to load: unset = all (TDD, debugging, verification), `off` = none, or a comma-list of names.
- `RAMBO_REPO_ROOT` / `RAMBO_WORKTREE_DIR` — where the repo and worktrees live (preset for the container; leave as-is).
- `RAMBO_TEST_CMD` / `RAMBO_TEST_CWD` — how the agent runs tests (default `python -m pytest -q` from `rambo-backend`).

---

## 6. Running the tests

From `rambo-backend/`: `python -m pytest -q`  (320+ tests). The self-coding lane itself uses this same command internally to verify its own changes.

---

## 7. Quick troubleshooting

| Symptom | Fix |
|---|---|
| UI loads but nothing responds | Backend down — `docker compose ps`; if needed `docker compose up -d rambo-backend`. Test with `curl http://localhost:8000/`. |
| Backend shows "unhealthy" | Often a false alarm — if `curl http://localhost:8000/` returns 200, it's fine. |
| Changed a `.py` but nothing happened | Usually auto-reloads; if not, `docker compose restart rambo-backend`. |
| Added a Python package, import still fails | Rebuild the image: `docker compose build rambo-backend && docker compose up -d rambo-backend`. |
| Frontend edit not showing | On 3001 it should auto-reload; for 3000 rebuild the prod frontend. |
| Voice not talking (only text) | Check `ANTHROPIC_API_KEY` (and `ELEVENLABS_*` for the neural voice) in `.env`, then restart the backend. |
| Self-coding "merge" refused | You have uncommitted edits in a file the change touches — commit/stash them, or it's safely blocked by design. |
| Dev lane says "pytest not installed" | The backend image needs a rebuild: `docker compose build rambo-backend && docker compose up -d rambo-backend`. |

---

## 8. Where to read more
- **`README.md`** — the feature overview.
- **`ROADMAP_R.A.M.B.O_*.md`** — dated logs of what shipped each day (newest = most current).
- **`HANDOFF.md`** — the running context handoff (state, decisions, gotchas).
- **`docs/PLAN_self-coding-agent.md`** — the design of the self-coding lane.
