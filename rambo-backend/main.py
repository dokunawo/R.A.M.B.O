import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Optional

# Load .env BEFORE importing anything that reads os.environ (the orchestrator
# checks ANTHROPIC_API_KEY at import time).
from env_setup import load_env
load_env()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.orchestrator import Orchestrator
import sentinel_queue
import agent_tracker
from usage_repo import UsageRepo
from dispatch_repo import DispatchRepo
from tts import ElevenLabsTTS
from tts_usage_repo import TTSUsageRepo
from tts_dashboard import get_tts_dashboard
from keeper_repo import KeeperRepo
from conversation_repo import ConversationRepo
from transcript_repo import TranscriptRepo
from morning_brief import brief_scheduler, run_brief
from reflection import reflection_scheduler, run_reflection
from calendar_watch import calendar_watch_scheduler, check_once as calendar_check_once
import seeker_watch
import proactive_nudges
from usage_capture import set_usage_repo
from usage_dashboard import get_dashboard
from embed_dashboard import get_embed_dashboard
from factory.repo import FactoryRepo, State
from factory.tool_registry import build_default_registry
from factory.pipeline import SpawnPipeline
from factory.approval import handle_approve, handle_reject
from factory.registry_watcher import RegistryWatcher
from dev_agent.repo import DevRepo
from dev_agent import session as dev_session
from dev_agent.builds_repo import BuildsRepo
from dev_agent import builds as builds_mod
from spotify_repo import SpotifyRepo
from spotify_client import SpotifyClient, SCOPES
import spotify_client as spotify_mod
from fastapi.responses import RedirectResponse, HTMLResponse

try:
    import psutil
except ImportError:
    psutil = None

try:
    from google_auth import is_authenticated, run_auth_flow
    _HAS_GAUTH = True
except ImportError:
    _HAS_GAUTH = False

app = FastAPI()
rambo = Orchestrator()
_usage_repo = UsageRepo()
_dispatch_repo = DispatchRepo()
_tts_usage_repo = TTSUsageRepo()
_keeper_repo = KeeperRepo()
_conversation_repo = ConversationRepo()
_transcript_repo = TranscriptRepo()
_factory_repo = FactoryRepo()
_tool_registry = build_default_registry()
_pipeline: SpawnPipeline | None = None
_watcher: RegistryWatcher | None = None
_dev_repo = DevRepo()
_builds_repo = BuildsRepo()
_open_queue: list[str] = []   # host paths the desktop helper should open + clear
_IN_FLIGHT: set[asyncio.Task] = set()
_spotify_repo = SpotifyRepo()
_spotify = SpotifyClient(_spotify_repo)
_spotify_states: set[str] = set()

# MLB betting data-ingestion endpoints (POST /ingest/run, GET /ingest/health).
# Data-only by construction — imports no bet-placement capability. Mounted
# defensively: if the optional ingestion deps (apify-client, rapidfuzz) aren't in
# this image yet, the app still boots without these routes (rebuild to enable).
try:
    from api.ingest import router as _ingest_router
    app.include_router(_ingest_router)
except Exception as _ingest_err:  # pragma: no cover
    print(f"[rambo] ingest router not mounted: {_ingest_err}")

try:
    from api.betting import router as _betting_router
    app.include_router(_betting_router)
except Exception as _betting_err:  # pragma: no cover
    print(f"[rambo] betting router not mounted: {_betting_err}")

# Frontend readiness handshake for the AHK boot gesture: the UI POSTs /ui/ready
# once it has loaded (screen-share auto-start listener armed), and the helper
# polls /ui/ready and only clicks to start screen share then — never on a blank,
# not-yet-loaded page. monotonic() so it's immune to wall-clock changes; 0.0 at
# process start means "not ready" until the current frontend checks in.
_ui_ready_at: float = 0.0


@app.on_event("startup")
async def _init_usage_db():
    await _usage_repo.init_db()
    set_usage_repo(_usage_repo)


@app.on_event("startup")
async def _init_dispatch_db():
    await _dispatch_repo.init_db()
    rambo.set_dispatch_repo(_dispatch_repo)


@app.on_event("startup")
async def _init_spotify_db():
    await _spotify_repo.init_db()
    rambo.set_spotify(_spotify)


@app.on_event("startup")
async def _init_tts():
    await _tts_usage_repo.init_db()
    rambo.set_tts_usage_repo(_tts_usage_repo)
    if os.environ.get("ELEVENLABS_API_KEY"):
        rambo.set_tts(ElevenLabsTTS.from_env())


@app.on_event("startup")
async def _init_keeper():
    await _keeper_repo.init_db()
    rambo.set_keeper_repo(_keeper_repo)


@app.on_event("startup")
async def _init_conversation():
    await _conversation_repo.init_db()
    await rambo.set_conversation_repo(_conversation_repo)


@app.on_event("startup")
async def _init_transcript():
    await _transcript_repo.init_db()
    rambo.set_transcript_repo(_transcript_repo)


_brief_task = None
_reflection_task = None
_calendar_watch_task = None


@app.on_event("startup")
async def _start_morning_brief():
    global _brief_task
    _brief_task = asyncio.create_task(brief_scheduler(rambo))


@app.on_event("startup")
async def _start_reflection():
    global _reflection_task
    _reflection_task = asyncio.create_task(reflection_scheduler(rambo))


@app.on_event("startup")
async def _start_calendar_watch():
    global _calendar_watch_task
    _calendar_watch_task = asyncio.create_task(calendar_watch_scheduler(rambo))


_seeker_watch_task = None
_proactive_task = None


@app.on_event("startup")
async def _start_seeker_watch():
    global _seeker_watch_task
    _seeker_watch_task = asyncio.create_task(seeker_watch.seeker_watch_scheduler(rambo))


@app.on_event("startup")
async def _start_proactive_nudges():
    global _proactive_task
    _proactive_task = asyncio.create_task(proactive_nudges.proactive_scheduler(rambo))


@app.on_event("startup")
async def _init_factory():
    global _pipeline, _watcher
    await _factory_repo.init_db()
    if rambo.llm:
        _pipeline = SpawnPipeline(
            repo=_factory_repo,
            tool_registry=_tool_registry,
            llm_client=rambo.llm,
        )
        _watcher = RegistryWatcher(
            repo=_factory_repo,
            tool_registry=_tool_registry,
            llm_client=rambo.llm,
        )
        _watcher.start()
        rambo.set_factory(_factory_repo, _tool_registry)


@app.on_event("startup")
async def _init_dev_agent():
    await _dev_repo.init_db()
    rambo.set_dev_agent(_dev_repo)


@app.on_event("startup")
async def _init_builds():
    await _builds_repo.init_db()
    rambo.set_builds(_builds_repo)
    builds_mod.set_repo(_builds_repo)   # lets the delete-build skill reach the dock DB


@app.on_event("startup")
async def _init_system_briefing():
    import system_briefing
    system_briefing.set_orchestrator(rambo)

manager = rambo.ws

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Command(BaseModel):
    goal: str
    lat: float | None = None
    lon: float | None = None
    image: str | None = None  # base64 JPEG of the screen (on-demand vision)


class SentinelDecision(BaseModel):
    id: str
    decision: str


@app.get("/")
async def root():
    return {"status": "online", "service": "R.A.M.B.O"}


@app.get("/agents/status")
async def get_agent_status():
    return rambo.get_status()


@app.get("/agents/{agent_key}/detail")
async def get_agent_detail(agent_key: str):
    return rambo.detail_for(agent_key)


@app.get("/system/stats")
async def system_stats():
    if psutil is None:
        return {"available": False}
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return {
        "available": True,
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_used_gb": round(vm.used / 1e9, 1),
        "ram_total_gb": round(vm.total / 1e9, 1),
        "ram_percent": vm.percent,
        "disk_used_gb": round(du.used / 1e9, 1),
        "disk_total_gb": round(du.total / 1e9, 1),
        "disk_percent": du.percent,
    }


@app.post("/rambo/execute")
async def execute_command(cmd: Command):
    proactive_nudges.mark_active()   # operator is active → resets idle nudges
    ctx = {"lat": cmd.lat, "lon": cmd.lon, "image": cmd.image}
    return await rambo.handle(cmd.goal, ctx)


@app.get("/greeting")
async def operator_greeting():
    """A Jarvis-style boot greeting (name + time + what needs you). The frontend
    fetches this when the console loads and speaks it in the ElevenLabs voice."""
    from greeting import generate_greeting
    proactive_nudges.mark_active()
    return {"greeting": await generate_greeting(rambo)}


@app.get("/farewell")
async def operator_farewell():
    """Spoken sign-off for the shutdown sequence (cinematic only — no process is
    stopped). The frontend fetches this when the operator powers down to standby."""
    from greeting import generate_farewell
    return {"farewell": await generate_farewell(rambo)}


@app.get("/tasks/history")
async def tasks_history(limit: int = 50):
    """Task-history panel feed: dispatched tasks (agent_tracker, in-memory) +
    dev-lane self-changes across all statuses (DevRepo)."""
    return {"tasks": agent_tracker.get_all_recent(limit),
            "changes": await _dev_repo.list_recent(limit)}


@app.get("/briefing/boot")
async def briefing_boot():
    """Boot briefing: a full on-screen card (recent changes, suggested targets,
    weather, what's pending, system status) + a short spoken summary. The frontend
    fetches this once per boot, after the greeting. Read-only; stamps last-boot
    AFTER gathering so 'since last boot' reflects the previous session."""
    from system_briefing import gather_briefing, render_full, render_concise, _write_last_boot
    proactive_nudges.mark_active()
    data = await gather_briefing(rambo)
    card, spoken = render_full(data), render_concise(data)
    try:
        await rambo._response("architect", card)   # on-screen card (morning-brief channel)
    except Exception:
        pass
    _write_last_boot(datetime.now(timezone.utc).isoformat())
    return {"card": card, "spoken": spoken}


class TtsSay(BaseModel):
    text: str


@app.post("/tts/say")
async def tts_say(req: TtsSay):
    """Synthesize an arbitrary short string to ElevenLabs audio (base64 MP3) so
    the frontend's local voice acks use the ElevenLabs voice too, never the
    robotic browser voice. Returns {"audio": null} if synthesis is unavailable —
    the caller then stays silent rather than falling back to the browser voice."""
    audio = await rambo._segment_audio(req.text)
    return {"audio": audio}


@app.get("/sentinel/approvals")
async def get_approvals():
    return sentinel_queue.list_approvals()


@app.post("/sentinel/decision")
async def post_decision(decision: SentinelDecision):
    updated = sentinel_queue.decide(decision.id, decision.decision)
    return {"updated": updated}


@app.get("/google/status")
async def google_status():
    if not _HAS_GAUTH:
        return {"authenticated": False, "reason": "Google libraries not installed"}
    return {"authenticated": is_authenticated()}


@app.post("/google/auth")
async def google_auth():
    if not _HAS_GAUTH:
        return {"error": "Google libraries not installed"}
    try:
        run_auth_flow()
        return {"authenticated": True}
    except Exception as e:
        return {"error": str(e)}


@app.get("/usage")
async def usage_dashboard():
    return await get_dashboard(_usage_repo)


@app.get("/usage/tts")
async def tts_usage_dashboard():
    return await get_tts_dashboard(_tts_usage_repo, os.environ.get("ELEVENLABS_API_KEY"))


@app.get("/usage/embed")
async def embed_usage_dashboard():
    return await get_embed_dashboard(_usage_repo)


# ── UI readiness (for the AHK screen-share boot gesture) ─────────────
@app.post("/ui/ready")
async def ui_ready_set():
    """The frontend calls this once it has loaded and armed its screen-share
    auto-start listener, so the AHK helper knows it's safe to click."""
    global _ui_ready_at
    _ui_ready_at = time.monotonic()
    return {"ok": True}


@app.get("/ui/ready")
async def ui_ready_get():
    """True only if the frontend checked in recently — so the helper never acts
    on a stale signal from a previous page load/session."""
    return {"ready": (time.monotonic() - _ui_ready_at) < 60}


# ── Spotify (in-app player via Web Playback SDK) ─────────────────────
class SpotifyControl(BaseModel):
    device_id: str | None = None
    context_uri: str | None = None
    uris: list[str] | None = None
    offset: dict | None = None
    play: bool = True


class SpotifyDevice(BaseModel):
    device_id: str


@app.post("/spotify/device")
async def spotify_device(d: SpotifyDevice):
    """The browser registers its Web Playback SDK device id so voice commands can
    target the R.A.M.B.O player even before anything is playing."""
    rambo.set_spotify_device(d.device_id)
    return {"ok": True}


@app.get("/spotify/status")
async def spotify_status():
    return {
        "configured": spotify_mod.is_configured(),
        "connected": await _spotify.is_connected(),
        "needs_reconnect": await _spotify.needs_reconnect(),
    }


@app.get("/spotify/login")
async def spotify_login():
    if not spotify_mod.is_configured():
        return {"error": "Spotify not configured — set SPOTIFY_CLIENT_ID/SECRET in .env"}
    import secrets
    state = secrets.token_urlsafe(16)
    _spotify_states.add(state)
    return RedirectResponse(_spotify.authorize_url(state))


@app.get("/spotify/callback")
async def spotify_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    def _page(msg: str, ok: bool) -> HTMLResponse:
        color = "#48e0c0" if ok else "#e05a5a"
        return HTMLResponse(
            f"<html><body style='background:#0c0f14;color:{color};font-family:monospace;"
            f"display:flex;align-items:center;justify-content:center;height:100vh;'>"
            f"<div style='text-align:center'><h2>{msg}</h2>"
            f"<p style='color:#9fd8cf'>You can close this tab.</p></div>"
            f"<script>setTimeout(()=>window.close(),1500)</script></body></html>"
        )
    if error:
        return _page(f"Spotify auth failed: {error}", False)
    if not state or state not in _spotify_states:
        return _page("Spotify auth failed: invalid state", False)
    _spotify_states.discard(state)
    if not code or not await _spotify.exchange_code(code):
        return _page("Spotify auth failed: could not get tokens", False)
    return _page("✓ Spotify connected to R.A.M.B.O", True)


@app.get("/spotify/token")
async def spotify_token():
    tok = await _spotify.access_token()
    if not tok:
        return {"error": "not_connected"}
    return {"access_token": tok}


@app.post("/spotify/disconnect")
async def spotify_disconnect():
    await _spotify_repo.clear()
    return {"ok": True}


@app.get("/spotify/now-playing")
async def spotify_now_playing():
    return await _spotify.now_playing()


@app.get("/spotify/playlists")
async def spotify_playlists():
    return await _spotify.playlists()


@app.get("/spotify/playlist-tracks")
async def spotify_playlist_tracks(playlist_id: str):
    return await _spotify.playlist_tracks(playlist_id)


@app.get("/spotify/liked")
async def spotify_liked():
    return await _spotify.liked()


@app.post("/spotify/play-liked")
async def spotify_play_liked(ctrl: SpotifyControl):
    return await _spotify.play_liked(device_id=ctrl.device_id)


@app.get("/spotify/search")
async def spotify_search(q: str):
    return await _spotify.search(q)


@app.post("/spotify/play")
async def spotify_play(ctrl: SpotifyControl):
    return await _spotify.play(device_id=ctrl.device_id, context_uri=ctrl.context_uri,
                               uris=ctrl.uris, offset=ctrl.offset)


@app.post("/spotify/pause")
async def spotify_pause(ctrl: SpotifyControl):
    return await _spotify.pause(device_id=ctrl.device_id)


@app.post("/spotify/toggle")
async def spotify_toggle(ctrl: SpotifyControl | None = None):
    """Single play/pause toggle for the OS media-key helper (rambo-mediakeys.ahk),
    which can't track play state itself. Body is optional so a bare POST works."""
    return await _spotify.toggle(device_id=ctrl.device_id if ctrl else None)


@app.post("/spotify/next")
async def spotify_next(ctrl: SpotifyControl):
    return await _spotify.next(device_id=ctrl.device_id)


@app.post("/spotify/previous")
async def spotify_previous(ctrl: SpotifyControl):
    return await _spotify.previous(device_id=ctrl.device_id)


@app.post("/spotify/transfer")
async def spotify_transfer(ctrl: SpotifyControl):
    if not ctrl.device_id:
        return {"error": "device_id required"}
    return await _spotify.transfer(ctrl.device_id, play=ctrl.play)


@app.get("/spotify/devices")
async def spotify_devices():
    return await _spotify.devices()


class SpotifyShuffle(BaseModel):
    state: bool
    device_id: str | None = None


@app.post("/spotify/shuffle")
async def spotify_shuffle(s: SpotifyShuffle):
    return await _spotify.shuffle(s.state, device_id=s.device_id)


class SpotifyVolume(BaseModel):
    percent: int
    device_id: str | None = None


@app.post("/spotify/volume")
async def spotify_volume(v: SpotifyVolume):
    return await _spotify.volume(v.percent, device_id=v.device_id)


# ── Keeper memory store ──────────────────────────────────────────────
class KeeperWrite(BaseModel):
    key: str
    value: str
    tags: str = ""


@app.post("/keeper")
async def keeper_write(entry: KeeperWrite):
    rid = await _keeper_repo.write(entry.key, entry.value, entry.tags)
    return {"id": rid, "key": entry.key, "stored": True}


# ── Conversation history ─────────────────────────────────────────
@app.get("/history")
async def get_history(limit: int = 50):
    """Recent conversation turns (oldest first). Persisted, so survives restarts."""
    return {"turns": await _conversation_repo.recent(limit)}


@app.delete("/history")
async def clear_history():
    await _conversation_repo.clear()
    rambo.conversation.clear()
    return {"cleared": True}


# ── Q&A transcript (clean, copy-pasteable history) ───────────────
@app.get("/transcript")
async def get_transcript(limit: int = 100):
    """Recent question→answer pairs (oldest first). Persisted across restarts."""
    return {"entries": await _transcript_repo.recent(limit)}


@app.delete("/transcript")
async def clear_transcript():
    await _transcript_repo.clear()
    return {"cleared": True}


# ── Operator profile (living memory) ─────────────────────────────
@app.post("/profile/refresh")
async def profile_refresh():
    """Rebuild the synthesized operator profile from accumulated reflection
    insights. This is what _build_operator_context injects into every reply."""
    from reflection import refresh_operator_profile
    profile = await refresh_operator_profile(rambo)
    if profile is None:
        return {"refreshed": False, "reason": "no insights yet or LLM/keeper unavailable"}
    return {"refreshed": True, "profile": profile}


@app.get("/keeper/confirm")
async def keeper_confirm():
    return await _keeper_repo.confirm()


@app.delete("/keeper/{key}")
async def keeper_delete(key: str):
    deleted = await _keeper_repo.delete(key)
    return {"key": key, "deleted": deleted}


@app.get("/keeper")
async def keeper_query(search: str = "", limit: int = 50):
    return {"entries": await _keeper_repo.query(search, limit)}


@app.get("/keeper/{key}")
async def keeper_read(key: str):
    entry = await _keeper_repo.read(key)
    return entry or {"error": "not found", "key": key}


# ── Proactive calendar watch (Phase 2) ───────────────────────────
@app.post("/calendar/watch/check")
async def calendar_watch_check():
    """Run one proactive calendar check now (nudges approaching events). Useful
    for testing without waiting for the poll interval."""
    fired = await calendar_check_once(rambo)
    return {"nudged": [{"summary": e.get("summary"),
                        "minutes_until": e.get("minutes_until")} for e in fired]}


# ── Seeker watch topics (Phase 2) ────────────────────────────────
class WatchTopic(BaseModel):
    topic: str


@app.get("/watch")
async def watch_list():
    return {"topics": await seeker_watch.list_topics(_keeper_repo)}


@app.post("/watch")
async def watch_add(t: WatchTopic):
    slug = await seeker_watch.add_topic(_keeper_repo, t.topic)
    return {"slug": slug, "topic": t.topic.strip()}


@app.delete("/watch/{slug}")
async def watch_remove(slug: str):
    return {"slug": slug, "removed": await seeker_watch.remove_topic(_keeper_repo, slug)}


@app.post("/seeker/crawl")
async def seeker_crawl_now():
    """Crawl all watch topics now and surface anything new."""
    surfaced = await seeker_watch.crawl_once(rambo)
    return {"surfaced": [s["topic"] for s in surfaced]}


# ── Deadlines (Phase 2) ──────────────────────────────────────────
class DeadlineIn(BaseModel):
    text: str
    when: str   # natural ("next Friday") or ISO ("2026-07-01")


@app.get("/deadline")
async def deadline_list():
    return {"deadlines": await proactive_nudges.list_deadlines(_keeper_repo)}


@app.post("/deadline")
async def deadline_add(d: DeadlineIn):
    return await proactive_nudges.add_deadline(_keeper_repo, d.text, d.when)


@app.delete("/deadline/{slug}")
async def deadline_remove(slug: str):
    return {"slug": slug, "removed": await proactive_nudges.remove_deadline(_keeper_repo, slug)}


# ── Agent / integration health ───────────────────────────────────────
@app.get("/integrations/status")
async def integrations_status():
    from google_auth import integration_status
    from echo_messaging import status as echo_status
    return {
        "google": integration_status(),
        "echo": echo_status(),
        "elevenlabs": {"status": "CONNECTED" if os.environ.get("ELEVENLABS_API_KEY") else "OFFLINE"},
        "anthropic": {"status": "CONNECTED" if os.environ.get("ANTHROPIC_API_KEY") else "OFFLINE"},
    }


@app.post("/brief/run")
async def brief_run():
    """Generate the morning brief now — displays it on screen and emails it."""
    brief = await run_brief(rambo)
    return {"delivered": True, "brief": brief}


@app.post("/reflection/run")
async def reflection_run():
    """Run nightly reflection now — consolidates today's activity into Keeper."""
    insights = await run_reflection(rambo)
    return {"stored": len(insights), "insights": insights}


@app.get("/agents/health")
async def agents_health():
    from google_auth import integration_status
    from echo_messaging import status as echo_status

    seeker = {
        "agent": "seeker",
        "backend": "Anthropic web_search + Open-Meteo (weather)",
        "status": "LIVE" if os.environ.get("ANTHROPIC_API_KEY") else "DEGRADED",
    }
    try:
        info = await _keeper_repo.confirm()
        keeper = {"agent": "keeper", "backend": "SQLite (data/keeper.db)",
                  "status": "CONNECTED", "entries": info["count"]}
    except Exception as e:
        keeper = {"agent": "keeper", "backend": "SQLite", "status": "DEGRADED", "reason": str(e)}

    return {"agents": [seeker, keeper, integration_status(), echo_status()]}


@app.get("/learning/log")
async def get_learning_log():
    return agent_tracker.get_learnings()


@app.websocket("/ws/activity")
async def activity_ws(ws: WebSocket):
    await manager.connect(ws)
    await manager.broadcast("Connected to R.A.M.B.O activity feed.")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


# ── Factory endpoints ────────────────────────────────────────────


class SpawnRequest(BaseModel):
    name_hint: str
    role_description: str
    special_requirements: str = ""


class RejectRequest(BaseModel):
    feedback: Optional[str] = None


@app.post("/factory/spawn")
async def factory_spawn(req: SpawnRequest):
    if _pipeline is None:
        return {"error": "LLM client not configured — cannot run Factory"}
    import uuid
    task_id = uuid.uuid4().hex
    await _factory_repo.create_task(
        task_id=task_id,
        name_hint=req.name_hint,
        role_description=req.role_description,
        special_requirements=req.special_requirements,
    )
    task = asyncio.create_task(_pipeline.run(task_id=task_id))
    _IN_FLIGHT.add(task)
    task.add_done_callback(_IN_FLIGHT.discard)
    return {"task_id": task_id, "status": "pending"}


@app.get("/factory/pending")
async def factory_pending():
    return await _factory_repo.list_by_status(State.AWAITING_APPROVAL)


@app.get("/factory/task/{task_id}")
async def factory_task(task_id: str):
    task = await _factory_repo.get_task(task_id)
    if task is None:
        return {"error": "not found"}
    return task


@app.post("/factory/approve/{task_id}")
async def factory_approve(task_id: str):
    async def _notify(slug: str):
        if _watcher:
            await _watcher.refresh()
    return await handle_approve(
        task_id=task_id, repo=_factory_repo, notify_registry=_notify,
    )


@app.post("/factory/reject/{task_id}")
async def factory_reject(task_id: str, req: RejectRequest):
    return await handle_reject(
        task_id=task_id,
        repo=_factory_repo,
        feedback=req.feedback,
        pipeline=_pipeline,
    )


@app.get("/factory/agents")
async def factory_agents():
    return await _factory_repo.list_active_agents()


# ── Tier 4: tool confirmation gate ───────────────────────────────

# ── Self-coding (dev agent) endpoints ────────────────────────────


class ProposeRequest(BaseModel):
    goal: str


@app.post("/dev/propose")
async def dev_propose(req: ProposeRequest):
    if rambo.llm is None:
        return {"error": "LLM client not configured — cannot run the dev agent"}
    import uuid
    change_id = uuid.uuid4().hex[:12]
    await _dev_repo.create(change_id, req.goal)

    async def _drive():
        def _emit(**kw):
            asyncio.create_task(manager.broadcast_json({"t": "dev_progress", "id": change_id, **kw}))
        await dev_session.draft_change(
            llm=rambo.llm, repo=_dev_repo, change_id=change_id, goal=req.goal,
            personality_text=rambo.personality_text, on_event=_emit,
        )

    task = asyncio.create_task(_drive())
    _IN_FLIGHT.add(task)
    task.add_done_callback(_IN_FLIGHT.discard)
    return {"id": change_id, "status": "drafting"}


@app.get("/dev/pending")
async def dev_pending():
    return await _dev_repo.list_pending()


@app.get("/dev/change/{change_id}")
async def dev_change(change_id: str):
    row = await _dev_repo.get(change_id)
    if row is None:
        return {"error": "not found"}
    return row


@app.post("/dev/merge/{change_id}")
async def dev_merge(change_id: str):
    result = await dev_session.merge_change(_dev_repo, change_id)
    if result.get("status") == "merged":
        await manager.broadcast(f"[R.A.M.B.O] Merged self-change {change_id}. Restart to take it live.")
    return result


@app.post("/dev/reject/{change_id}")
async def dev_reject(change_id: str):
    return await dev_session.reject_change(_dev_repo, change_id)


@app.post("/dev/escalate/{change_id}")
async def dev_escalate(change_id: str):
    return await dev_session.escalate_change(_dev_repo, change_id)


# ── Standalone builds (Engineer builds an app into builds/<slug>/) ───


class BuildRequest(BaseModel):
    name: str
    goal: str


@app.post("/builds/create")
async def builds_create(req: BuildRequest):
    if rambo.llm is None:
        return {"error": "LLM client not configured — cannot build"}
    # Short human name (the caller often passes the whole goal as the name).
    name = await builds_mod.summarize_build_name(rambo.llm, req.name or req.goal)
    slug = base = builds_mod.slugify(name)
    i = 2
    while await _builds_repo.slug_taken(slug):
        slug = f"{base}-{i}"
        i += 1
    import uuid
    await _builds_repo.create(uuid.uuid4().hex[:12], slug, name, req.goal)

    async def _drive():
        def _emit(**kw):
            asyncio.create_task(manager.broadcast_json({"t": "build_progress", "slug": slug, **kw}))
        await builds_mod.build_app(
            llm=rambo.llm, repo=_builds_repo, slug=slug, name=name, goal=req.goal,
            personality_text=rambo.personality_text, on_event=_emit,
        )

    task = asyncio.create_task(_drive())
    _IN_FLIGHT.add(task)
    task.add_done_callback(_IN_FLIGHT.discard)
    return {"slug": slug, "status": "building"}


@app.get("/builds")
async def builds_list():
    return await _builds_repo.list_all()


@app.get("/builds/{slug}")
async def builds_get(slug: str):
    row = await _builds_repo.get_by_slug(slug)
    if row is None:
        return {"error": "not found"}
    return row


@app.post("/builds/{slug}/test")
async def builds_test(slug: str):
    """Run the built project's tests (pytest) and return pass/fail + output."""
    return await builds_mod.run_tests(slug)


@app.post("/builds/{slug}/run")
async def builds_run(slug: str):
    """Run the built project's entry point and return its output."""
    return await builds_mod.run_app(slug)


@app.delete("/builds/{slug}")
async def builds_delete(slug: str):
    """Delete a build: its folder under builds/<slug>/ AND its dock record."""
    return await builds_mod.delete_build(slug)


# ── Desktop-open bridge (host AHK helper polls and opens in VS Code/Explorer) ──


class OpenRequest(BaseModel):
    path: str


@app.post("/desktop/open")
async def desktop_open(req: OpenRequest):
    """Queue a path for the host helper to open. Only paths inside the operator's
    repo are accepted, so the bridge can never open arbitrary locations."""
    if not builds_mod.is_safe_host_path(req.path):
        return {"error": "path is outside the RAMBO repo — refused"}
    _open_queue.append(req.path)
    return {"queued": req.path}


@app.get("/desktop/open-queue")
async def desktop_open_queue():
    """Return + clear pending open requests (the host helper polls this)."""
    pending = list(_open_queue)
    _open_queue.clear()
    return {"open": pending}


@app.post("/desktop/open-change/{change_id}")
async def desktop_open_change(change_id: str):
    """Open the RAMBO repo (where a merged self-change lives) on the desktop."""
    row = await _dev_repo.get(change_id)
    if row is None:
        return {"error": "not found"}
    from dev_agent import git_workspace as gw
    host = builds_mod.to_host_path(gw.resolve_repo_root())
    _open_queue.append(host)
    return {"queued": host}


from factory import confirmations as _confirmations


@app.get("/confirmations")
async def list_confirmations():
    return _confirmations.list_pending()


@app.post("/confirmations/{confirmation_id}/approve")
async def approve_confirmation(confirmation_id: str):
    rec = _confirmations.get(confirmation_id)
    if rec is None or rec["status"] != "pending":
        return {"error": "not found or already resolved"}
    # Git actions (push / local merge / PR merge) are gated through this same
    # confirmation queue but aren't spawned-agent tools — execute directly.
    if rec["tool_name"].startswith("git_"):
        from dev_agent import git_remote
        _confirmations.resolve(confirmation_id, "approved")
        try:
            res = await git_remote.execute_git_confirmation(rec)
            await manager.broadcast(f"[R.A.M.B.O] {rec['tool_name']} approved.")
            return {"status": "done", "action": rec["tool_name"], "result": res}
        except Exception as e:
            return {"status": "error", "action": rec["tool_name"], "error": str(e)}
    tool = _tool_registry.get(rec["tool_name"])
    if tool is None:
        return {"error": f"tool '{rec['tool_name']}' no longer registered"}
    _confirmations.resolve(confirmation_id, "approved")
    try:
        result = await tool.execute(**rec["tool_input"])
        return {"status": "executed", "tool": rec["tool_name"], "result": result}
    except Exception as e:
        return {"status": "error", "tool": rec["tool_name"], "error": str(e)}


@app.post("/confirmations/{confirmation_id}/reject")
async def reject_confirmation(confirmation_id: str):
    rec = _confirmations.resolve(confirmation_id, "rejected")
    if rec is None:
        return {"error": "not found or already resolved"}
    return {"status": "rejected", "id": confirmation_id}


# ── Git remote: commit + push (operator-confirmed, never auto) ───────


@app.get("/git/status")
async def git_status():
    from dev_agent import git_remote
    try:
        return await git_remote.push_preview()
    except Exception as e:
        return {"error": str(e)}


class GitPushRequest(BaseModel):
    message: str | None = None


@app.post("/git/push")
async def git_push_request(req: GitPushRequest):
    """Stage a push for the operator to approve — does NOT push yet. Creates a
    pending confirmation (approve in the Confirm dock or by voice)."""
    from dev_agent import git_remote
    try:
        preview = await git_remote.push_preview()
    except Exception as e:
        return {"error": str(e)}
    if not preview.get("token_configured"):
        return {"error": "no GitHub token configured — add RAMBO_GITHUB_TOKEN "
                         "(a fine-grained PAT) to rambo-backend/.env first."}
    msg = req.message or f"Update {preview['branch']} via R.A.M.B.O"
    entry = _confirmations.request_confirmation(
        "git_push", {"branch": preview["branch"], "message": msg}, agent_slug="operator")
    return {"status": "confirmation_required", "id": entry["id"], "preview": preview}


class GitMergeRequest(BaseModel):
    source: str
    target: str | None = None


@app.post("/git/merge")
async def git_merge_request(req: GitMergeRequest):
    """Stage a LOCAL branch merge for approval (does NOT merge yet)."""
    from dev_agent import git_remote
    try:
        preview = await git_remote.merge_preview(req.source, req.target)
    except Exception as e:
        return {"error": str(e)}
    if not preview["source_exists"]:
        return {"error": f"branch not found: {req.source}"}
    entry = _confirmations.request_confirmation(
        "git_merge_local", {"source": preview["source"], "target": preview["target"]},
        agent_slug="operator")
    return {"status": "confirmation_required", "id": entry["id"], "preview": preview}


class GitMergePRRequest(BaseModel):
    number: int
    method: str | None = "merge"


@app.post("/git/merge-pr")
async def git_merge_pr_request(req: GitMergePRRequest):
    """Stage a GitHub PR merge for approval (does NOT merge yet)."""
    entry = _confirmations.request_confirmation(
        "git_merge_pr", {"number": req.number, "method": req.method or "merge"},
        agent_slug="operator")
    return {"status": "confirmation_required", "id": entry["id"],
            "preview": {"pr": req.number, "method": req.method or "merge"}}


# ── Tier 5: handoff system (propose, don't chain) ────────────────

from factory import handoff as _handoff


@app.get("/handoffs")
async def list_handoffs():
    return _handoff.list_pending()


@app.post("/handoffs/{handoff_id}/accept")
async def accept_handoff(handoff_id: str):
    rec = _handoff.get(handoff_id)
    if rec is None or rec["status"] != "pending":
        return {"error": "not found or already resolved"}
    _handoff.resolve(handoff_id, "accepted")
    # The human approved this edge — NOW dispatch the target with the task.
    result = await rambo._run_target(rec["target_agent"], rec["task"], {})
    return {"status": "dispatched", "target": rec["target_agent"], "result": result}


@app.post("/handoffs/{handoff_id}/reject")
async def reject_handoff(handoff_id: str):
    rec = _handoff.resolve(handoff_id, "rejected")
    if rec is None:
        return {"error": "not found or already resolved"}
    return {"status": "rejected", "id": handoff_id}


# ── Dock clear / dismiss actions ─────────────────────────────────
# Two operations per left-rail dock:
#   • clear   → NON-destructive. Records a summary to Keeper (so it's recallable
#               via "what was recently done") but leaves the pending items alone.
#               The UI hides them locally; they remain in the backend queue.
#   • dismiss → destructive. Rejects/removes the pending items AND records the
#               same Keeper summary.

async def _remember_cleared(dock: str, title: str, lines: list[str]) -> None:
    """Best-effort: store a dock summary in Keeper so it's recallable."""
    if not lines:
        return
    stamp = time.strftime("%Y-%m-%d %H:%M")
    key = f"cleared-{dock}-{time.strftime('%Y%m%d-%H%M%S')}"
    value = f"Cleared the {title} panel on {stamp}:\n" + "\n".join(f"- {ln}" for ln in lines)
    try:
        await _keeper_repo.write(key, value, tags=f"activity,dock,{dock}")
    except Exception:
        pass


# Each gather returns (items, summary_lines) for a dock's current pending set.
async def _factory_gather():
    items = await _factory_repo.list_by_status(State.AWAITING_APPROVAL)
    lines = []
    for t in items:
        m = t.get("proposed_manifest") or {}
        name = m.get("name") or t.get("name_hint") or "agent"
        spec = m.get("specialty") or t.get("role_description") or ""
        lines.append(f"{name}: {spec}".strip(": ").strip())
    return items, lines


def _confirm_gather():
    items = _confirmations.list_pending()
    lines = [f"{c.get('tool_name')} ({c.get('agent_slug') or 'rambo'})" for c in items]
    return items, lines


def _handoff_gather():
    items = _handoff.list_pending()
    lines = [f"→ {h.get('target_agent')}: {h.get('task') or h.get('reason') or ''}".strip()
             for h in items]
    return items, lines


async def _builds_gather():
    items = await _builds_repo.list_all()
    lines = [f"{b.get('name') or b.get('slug')} ({b.get('status')})" for b in items]
    return items, lines


async def _dev_gather():
    items = await _dev_repo.list_pending()
    lines = []
    for c in items:
        impact = c.get("impact") or {}
        goal = (c.get("goal") or "").strip()
        summary = impact.get("summary") or ""
        lines.append(f"{goal} — {summary}".strip(" —"))
    return items, lines


# ── Factory ──
@app.post("/factory/clear")
async def factory_clear():
    items, lines = await _factory_gather()
    await _remember_cleared("factory", "Factory (pending agents)", lines)
    return {"remembered": len(items)}


@app.post("/factory/dismiss")
async def factory_dismiss():
    items, lines = await _factory_gather()
    for t in items:
        try:
            await handle_reject(task_id=t["id"], repo=_factory_repo,
                                feedback=None, pipeline=_pipeline)
        except Exception:
            pass
    await _remember_cleared("factory", "Factory (pending agents)", lines)
    return {"dismissed": len(items)}


# ── Confirmations ──
@app.post("/confirmations/clear")
async def confirmations_clear():
    items, lines = _confirm_gather()
    await _remember_cleared("confirm", "Confirm (actions awaiting approval)", lines)
    return {"remembered": len(items)}


@app.post("/confirmations/dismiss")
async def confirmations_dismiss():
    items, lines = _confirm_gather()
    for c in items:
        try:
            _confirmations.resolve(c["id"], "rejected")
        except Exception:
            pass
    await _remember_cleared("confirm", "Confirm (actions awaiting approval)", lines)
    return {"dismissed": len(items)}


# ── Handoffs ──
@app.post("/handoffs/clear")
async def handoffs_clear():
    items, lines = _handoff_gather()
    await _remember_cleared("handoff", "Handoff (proposed handoffs)", lines)
    return {"remembered": len(items)}


@app.post("/handoffs/dismiss")
async def handoffs_dismiss():
    items, lines = _handoff_gather()
    for h in items:
        try:
            _handoff.resolve(h["id"], "rejected")
        except Exception:
            pass
    await _remember_cleared("handoff", "Handoff (proposed handoffs)", lines)
    return {"dismissed": len(items)}


# ── Code Review (dev self-changes) ──
@app.post("/dev/clear")
async def dev_clear():
    items, lines = await _dev_gather()
    await _remember_cleared("codereview", "Code Review (proposed self-changes)", lines)
    return {"remembered": len(items)}


@app.post("/dev/dismiss")
async def dev_dismiss():
    items, lines = await _dev_gather()
    for c in items:
        try:
            await dev_session.reject_change(_dev_repo, c["id"])
        except Exception:
            pass
    await _remember_cleared("codereview", "Code Review (proposed self-changes)", lines)
    return {"dismissed": len(items)}


# ── Builds (built projects) ──
@app.post("/builds/clear")
async def builds_clear():
    items, lines = await _builds_gather()
    await _remember_cleared("builds", "Builds (built projects)", lines)
    return {"remembered": len(items)}


@app.post("/builds/dismiss")
async def builds_dismiss():
    """Remove build dock entries (DB records) — the project folders on disk are
    kept. Non-destructive to the actual built files."""
    items, lines = await _builds_gather()
    n = await _builds_repo.delete_all()
    await _remember_cleared("builds", "Builds (built projects)", lines)
    return {"dismissed": n}
