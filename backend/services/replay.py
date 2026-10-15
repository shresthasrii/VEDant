import time
import asyncio
from typing import Dict, Any, List
from backend.db import get_db
from backend.services.occupancy import ingest_reading

class ReplaySimulator:
    def __init__(self, time_warp: float = 10.0): # 1 day simulated in ~2.4 minutes at 10x
        self.time_warp = time_warp
        self.is_running = False
        self.current_sim_hour = 8
        self._task = None

    async def start(self, ws_broadcast_fn):
        self.is_running = True
        while self.is_running:
            self.current_sim_hour = (self.current_sim_hour + 1) % 24
            
            # Fetch simulated occupancy for this hour
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT room_id, count FROM occupancy_readings 
                WHERE hour = ? AND source = 'simulated'
                """, (self.current_sim_hour,))
                readings = cursor.fetchall()
                
            updates = []
            for r in readings:
                rid = r["room_id"]
                cnt = r["count"]
                if cnt is not None:
                    # Small variation
                    res = ingest_reading(rid, cnt, source="simulated", timestamp=f"2026-10-15T{self.current_sim_hour:02d}:00:00")
                    updates.append(res)
                    
            if ws_broadcast_fn:
                await ws_broadcast_fn({
                    "type": "replay_tick",
                    "hour": self.current_sim_hour,
                    "updates": updates
                })
                
            await asyncio.sleep(60.0 / self.time_warp)

    def stop(self):
        self.is_running = False

replay_manager = ReplaySimulator()
