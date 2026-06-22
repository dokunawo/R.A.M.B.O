from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.orchestrator import Orchestrator
import sentinel_queue
import agent_tracker

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
