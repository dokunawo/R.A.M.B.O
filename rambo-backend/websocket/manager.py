class ConnectionManager:
    def __init__(self):
        self.active = []

    async def connect(self, websocket):
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket):
        if websocket in self.active:
            self.active.remove(websocket)

    # kept as aliases for older callers
    def add(self, websocket):
        self.active.append(websocket)

    def remove(self, websocket):
        self.disconnect(websocket)

    async def broadcast(self, message: str):
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(ws)

    async def broadcast_json(self, data: dict):
        import json
        text = json.dumps(data)
        await self.broadcast(text)
