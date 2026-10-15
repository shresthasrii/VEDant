import json
import asyncio
from typing import List, Dict, Any
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._batch_queue: List[Dict[str, Any]] = []
        self._flush_task = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

    def queue_patch(self, patch: Dict[str, Any]):
        self._batch_queue.append(patch)

    async def flush_batches_loop(self):
        """Batched patches sent at most 4 Hz (every 250ms)."""
        while True:
            await asyncio.sleep(0.25)
            if self._batch_queue and self.active_connections:
                batch = list(self._batch_queue)
                self._batch_queue.clear()
                await self.broadcast({
                    "type": "batch_patch",
                    "patches": batch
                })

ws_manager = ConnectionManager()
