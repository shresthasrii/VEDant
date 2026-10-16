import json
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from backend.db import get_db
from backend.schemas import RoomStatus, RoomBase

router = APIRouter(prefix="/rooms", tags=["rooms"])

@router.get("", response_model=List[RoomStatus])
def get_rooms(floor: Optional[int] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM rooms"
        params = []
        if floor and floor > 0:
            query += " WHERE floor = ?"
            params.append(floor)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # ── Single batch query for all latest occupancy readings (avoids N+1) ──
        cursor.execute("""
        SELECT o.room_id, o.count, o.smoothed_count, o.status, o.source, o.provenance
        FROM occupancy_readings o
        INNER JOIN (
            SELECT room_id, MAX(id) AS max_id
            FROM occupancy_readings
            GROUP BY room_id
        ) latest ON o.room_id = latest.room_id AND o.id = latest.max_id
        """)
        occ_map = {row["room_id"]: row for row in cursor.fetchall()}

        result = []
        for r in rows:
            rid = r["id"]
            occ = occ_map.get(rid)
            
            c = occ["count"] if occ else 0
            sc = occ["smoothed_count"] if occ else 0.0
            st = occ["status"] if occ else "unoccupied"
            src = occ["source"] if occ else "simulated"
            prov = occ["provenance"] if occ else "SIMULATED"
            
            cap = r["capacity"]
            u = (sc / cap) if (cap and sc is not None) else None
            
            # Demand calculation
            kw = r["hvac_kw"] + r["lighting_kw"] + r["plug_kw"]
            
            result.append(RoomStatus(
                id=r["id"],
                name=r["name"],
                floor=r["floor"],
                type=r["type"],
                capacity=cap,
                hvac_kw=r["hvac_kw"],
                lighting_kw=r["lighting_kw"],
                plug_kw=r["plug_kw"],
                accessible=bool(r["accessible"]),
                equipment=json.loads(r["equipment"]) if r["equipment"] else [],
                sensor_offline=bool(r["sensor_offline"]),
                pos_3d=json.loads(r["pos_3d"]) if r["pos_3d"] else None,
                current_occupancy=c,
                smoothed_occupancy=sc,
                utilization_rate=u,
                status=st,
                source=src,
                provenance=prov,
                demand_kw=round(kw, 2)
            ))
        return result

@router.get("/{room_id}")
def get_room(room_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        r = cursor.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
            
        cursor.execute("""
        SELECT hour, count, status FROM occupancy_readings
        WHERE room_id = ? AND source = 'simulated'
        ORDER BY hour ASC
        """, (room_id,))
        hourly = [dict(h) for h in cursor.fetchall()]
        
        d = dict(r)
        d["equipment"] = json.loads(d["equipment"]) if d["equipment"] else []
        d["accessible"] = bool(d["accessible"])
        d["sensor_offline"] = bool(d["sensor_offline"])
        d["pos_3d"] = json.loads(d["pos_3d"]) if d["pos_3d"] else None
        d["hourly_occupancy"] = hourly
        return d
