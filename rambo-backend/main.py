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
from usage_capture import set_usage_repo
from usage_dashboard import get_dashboard
from factory.repo import FactoryRepo, State
from factory.tool_registry import build_default_registry
from factory.pipeline import SpawnPipeline
from factory.approval import handle_approve, handle_reject
from factory.registry_watcher import RegistryWatcher

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
_factory_repo = FactoryRepo()
_tool_registry = build_default_registry()
_pipeline: SpawnPipeline | None = None
_watcher: RegistryWatcher | None = None
_IN_FLIGHT: set[asyncio.Task] = set()


@app.on_event("startup")
async def _init_usage_db():
    await _usage_repo.init_db()
    set_usage_repo(_usage_repo)


@app.on_event("startup")
async def _init_dispatch_db():
    await _dispatch_repo.init_db()
    rambo.set_dispatch_repo(_dispatch_repo)


@app.on_event("startup")
async def _init_tts():
    await _tts_usage_repo.init_db()
    rambo.set_tts_usage_repo(_tts_usage_repo)
    if os.environ.get("ELEVENLABS_API_KEY"):
        rambo.set_tts(ElevenLabsTTS.from_env())


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
    return agent_tracker.get_detail(agent_key)


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
    ctx = {"lat": cmd.lat, "lon": cmd.lon}
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
