from fastapi import FastAPI, WebSocket
from orchestrator.orchestrator import Orchestrator

app = FastAPI()
orc = Orchestrator()

@app.get("/")
def root():
    return {"status": "R.A.M.B.O backend running"}

@app.post("/run")
async def run(goal: str):
    return await orc.handle(goal)

# -------------------------
# REAL WEBSOCKET ENDPOINT
# -------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    orc.ws.add(websocket)

    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except:
        orc.ws.remove(websocket)
