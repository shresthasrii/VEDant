from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any
from backend.db import get_db
from backend.schemas import OccupancyIngest
from backend.services.occupancy import ingest_reading, get_held_state, release_room_hold
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM rooms WHERE id = ?", (data.room_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Room '{data.room_id}' not found in building directory.")

    result = ingest_reading(
        room_id=data.room_id,
        count=data.count,
        source=data.source,
        confidence=data.confidence,
        timestamp=data.timestamp,
        hour=data.hour,
        hold=data.hold,
        release_hold=bool(data.release_hold)
    )
    
    # Queue patch to WebSocket clients (at 4 Hz rate limit) only if not an ignored unheld overwrite
    if not result.get("blocked_overwrite"):
        ws_manager.queue_patch({
            "type": "room_occupancy_update",
            "data": result
        })
    
    return {
        "status": "success",
        "processed": result,
        "held": result.get("held", False),
        "held_state": result.get("held_state")
    }

@router.get("/occupancy/hold-state")
def get_room_hold_state(room_id: Optional[str] = Query(None, alias="room")) -> Dict[str, Any]:
    """Retrieve active camera latch/hold state for a room or all rooms."""
    return get_held_state(room_id)

@router.post("/occupancy/hold/release")
async def release_hold(room_id: str = Query("202", alias="room")) -> Dict[str, Any]:
    """Explicitly release an active camera hold on a room."""
    released = release_room_hold(room_id)
    ws_manager.queue_patch({
        "type": "room_occupancy_update",
        "data": {
            "room_id": room_id,
            "held": False,
            "release": True
        }
    })
    return {"room_id": room_id, "released": released, "held": False}

@router.get("/occupancy/24h")
def get_occupancy_24h(room_id: str = Query("202", alias="room")) -> Dict[str, Any]:
    """Returns continuous 24-hour recorded telemetry for the specified room."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, capacity FROM rooms WHERE id = ?", (room_id,))
        rm = cursor.fetchone()
        room_name = rm["name"] if rm else f"Room {room_id}"
        capacity = rm["capacity"] if rm else 50
        
        cursor.execute("""
        SELECT r.hour, 
               r.count, 
               r.smoothed_count as smoothed, 
               r.status, 
               r.provenance, 
               r.timestamp as last_timestamp, 
               total_tbl.total_samples
        FROM occupancy_readings r
        JOIN (
            SELECT hour, MAX(id) as max_id, COUNT(*) as total_samples
            FROM occupancy_readings
            WHERE room_id = ?
            GROUP BY hour
        ) total_tbl ON r.id = total_tbl.max_id
        ORDER BY r.hour ASC
        """, (room_id,))
        rows = cursor.fetchall()
        
        hourly_records = []
        hour_map = {r["hour"]: r for r in rows}
        
        held_info = get_held_state(room_id)
        is_held = bool(held_info.get("held", False))
        held_count = held_info.get("count")
        
        for h in range(24):
            # If room is locked/held, reflect held headcount across daytime hours (09:00 - 18:00)
            if is_held and 9 <= h <= 18 and held_count is not None:
                hourly_records.append({
                    "hour": h,
                    "time_slot": f"{h:02d}:00",
                    "count": held_count,
                    "smoothed_count": float(held_count),
                    "status": "occupied" if held_count > 0 else "unoccupied",
                    "provenance": "ACTUAL",
                    "samples": hour_map[h]["total_samples"] if h in hour_map else 1,
                    "last_recorded": held_info.get("timestamp")
                })
            elif h in hour_map:
                r = hour_map[h]
                cnt = int(round(r["count"])) if r["count"] is not None else 0
                hourly_records.append({
                    "hour": h,
                    "time_slot": f"{h:02d}:00",
                    "count": cnt,
                    "smoothed_count": round(r["smoothed"] if r["smoothed"] is not None else cnt, 1),
                    "status": r["status"] or ("occupied" if cnt > 0 else "unoccupied"),
                    "provenance": r["provenance"] or "ACTUAL",
                    "samples": r["total_samples"],
                    "last_recorded": r["last_timestamp"]
                })
            else:
                hourly_records.append({
                    "hour": h,
                    "time_slot": f"{h:02d}:00",
                    "count": 0,
                    "smoothed_count": 0.0,
                    "status": "unoccupied",
                    "provenance": "SIMULATED",
                    "samples": 0,
                    "last_recorded": None
                })
                
        return {
            "room_id": room_id,
            "room_name": room_name,
            "capacity": capacity,
            "recording_window": "24 Hours Continuous Telemetry",
            "retention_policy": "30 days rolling in SQLite (zero images stored)",
            "hourly_timeline": hourly_records,
            "total_samples_logged": sum(r["samples"] for r in hourly_records),
            "export_url": "/export/occupancy.csv",
            "is_held": is_held,
            "held_count": held_count if is_held else None,
            "held_state": held_info
        }
