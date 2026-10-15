from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from backend.db import get_db
from backend.schemas import OccupancyIngest
from backend.services.occupancy import ingest_reading
from backend.ws import ws_manager

router = APIRouter(prefix="", tags=["occupancy"])

@router.get("/occupancy")
def get_occupancy(
    room_id: Optional[str] = Query(None, alias="room"),
    from_hour: int = Query(0, alias="from"),
    to_hour: int = Query(23, alias="to")
) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM occupancy_readings WHERE hour >= ? AND hour <= ?"
        params = [from_hour, to_hour]
        if room_id:
            query += " AND room_id = ?"
            params.append(room_id)
        query += " ORDER BY id DESC LIMIT 500"
        
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        
        # Summary statistics
        valid_counts = [r["count"] for r in rows if r["count"] is not None]
        avg_count = sum(valid_counts) / len(valid_counts) if valid_counts else 0.0
        
        return {
            "readings": rows,
            "count": len(rows),
            "average_occupancy": round(avg_count, 1),
            "reporting_rooms": len(set(r["room_id"] for r in rows if r["count"] is not None)),
            "provenance": "SIMULATED / ACTUAL"
        }

@router.post("/ingest/occupancy")
async def ingest_occupancy(data: OccupancyIngest):
    """Endpoint for the local YOLO computer vision worker."""
    result = ingest_reading(
        room_id=data.room_id,
        count=data.count,
        source=data.source,
        confidence=data.confidence,
        timestamp=data.timestamp
    )
    
    # Queue patch to WebSocket clients (at 4 Hz rate limit)
    ws_manager.queue_patch({
        "type": "room_occupancy_update",
        "data": result
    })
    
    return {
        "status": "success",
        "processed": result
    }
