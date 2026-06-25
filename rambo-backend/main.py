import asyncio
import os
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
from morning_brief import brief_scheduler, run_brief
from reflection import reflection_scheduler, run_reflection
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
_factory_repo = FactoryRepo()
_tool_registry = build_default_registry()
_pipeline: SpawnPipeline | None = None
_watcher: RegistryWatcher | None = None
_dev_repo = DevRepo()
_IN_FLIGHT: set[asyncio.Task] = set()
_spotify_repo = SpotifyRepo()
_spotify = SpotifyClient(_spotify_repo)
_spotify_states: set[str] = set()


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


_brief_task = None
_reflection_task = None


@app.on_event("startup")
async def _start_morning_brief():
    global _brief_task
    _brief_task = asyncio.create_task(brief_scheduler(rambo))


@app.on_event("startup")
async def _start_reflection():
    global _reflection_task
    _reflection_task = asyncio.create_task(reflection_scheduler(rambo))


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
    ctx = {"lat": cmd.lat, "lon": cmd.lon, "image": cmd.image}
    return await rambo.handle(cmd.goal, ctx)


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


# ── Spotify (in-app player via Web Playback SDK) ─────────────────────
class SpotifyControl(BaseModel):
    device_id: str | None = None
    context_uri: str | None = None
    uris: list[str] | None = None
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
    return await _spotify.play(device_id=ctrl.device_id, context_uri=ctrl.context_uri, uris=ctrl.uris)


@app.post("/spotify/pause")
async def spotify_pause(ctrl: SpotifyControl):
    return await _spotify.pause(device_id=ctrl.device_id)


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


# ── Keeper memory store ──────────────────────────────────────────────
class KeeperWrite(BaseModel):
    key: str
    value: str
    tags: str = ""


@app.post("/keeper")
async def keeper_write(entry: KeeperWrite):
    rid = await _keeper_repo.write(entry.key, entry.value, entry.tags)
    return {"id": rid, "key": entry.key, "stored": True}


@app.get("/keeper/confirm")
async def keeper_confirm():
    return await _keeper_repo.confirm()


@app.get("/keeper")
async def keeper_query(search: str = "", limit: int = 50):
    return {"entries": await _keeper_repo.query(search, limit)}


@app.get("/keeper/{key}")
async def keeper_read(key: str):
    entry = await _keeper_repo.read(key)
    return entry or {"error": "not found", "key": key}


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


from factory import confirmations as _confirmations


@app.get("/confirmations")
async def list_confirmations():
    return _confirmations.list_pending()


@app.post("/confirmations/{confirmation_id}/approve")
async def approve_confirmation(confirmation_id: str):
    rec = _confirmations.get(confirmation_id)
    if rec is None or rec["status"] != "pending":
        return {"error": "not found or already resolved"}
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
