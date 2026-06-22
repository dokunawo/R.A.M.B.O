from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.orchestrator import Orchestrator
from websocket.manager import ConnectionManager
import sentinel_queue

app = FastAPI()
rambo = Orchestrator()
manager = ConnectionManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Command(BaseModel):
    goal: str

class SentinelDecision(BaseModel):
    id: str
    decision: str  # "APPROVE" or "DENY"


@app.get("/agents/status")
async def get_agent_status():
    return rambo.get_status()


@app.post("/rambo/execute")
async def execute_command(cmd: Command):
    result = await rambo.handle(cmd.goal)
    return {"response": result}


@app.get("/sentinel/approvals")
async def get_approvals():
    return sentinel_queue.list_approvals()


@app.post("/sentinel/decision")
async def post_decision(decision: SentinelDecision):
    updated = sentinel_queue.decide(decision.id, decision.decision)
    return {"updated": updated}


@app.websocket("/ws/activity")
async def activity_ws(ws: WebSocket):
    await manager.connect(ws)
    await manager.broadcast("Client connected to R.A.M.B.O activity feed.")
    try:
        while True:
            await ws.receive_text()
    except:
        manager.disconnect(ws)
