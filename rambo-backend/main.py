import asyncio
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.orchestrator import Orchestrator
import sentinel_queue
import agent_tracker
from usage_repo import UsageRepo
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
