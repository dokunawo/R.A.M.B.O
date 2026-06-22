class ConnectionManager:
    def __init__(self):
        self.active = []

    def add(self, websocket):
        self.active.append(websocket)

    def remove(self, websocket):
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: str):
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except:
                self.remove(ws)
