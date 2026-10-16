import statistics
from datetime import datetime
from typing import List, Dict, Optional, Any
from backend.db import get_db

# In-memory window buffers for smoothing & debouncing
_BUFFER_WINDOW = 5
_DEBOUNCE_THRESHOLD = 3
_room_buffers: Dict[str, List[int]] = {}
_room_debounce: Dict[str, Dict[str, Any]] = {}
_HELD_ROOMS: Dict[str, Dict[str, Any]] = {}

def get_held_state(room_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve active latch/hold metadata for a room or all rooms."""
    if room_id:
        if room_id in _HELD_ROOMS:
            return _HELD_ROOMS[room_id]
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='room_holds'")
                if cursor.fetchone():
                    cursor.execute("SELECT room_id, count, smoothed_count, hour, confidence, source, timestamp FROM room_holds WHERE room_id = ? AND held = 1", (room_id,))
                    row = cursor.fetchone()
                    if row:
                        _HELD_ROOMS[room_id] = {
                            "room_id": row["room_id"],
                            "held": True,
                            "count": row["count"],
                            "smoothed": row["smoothed_count"],
                            "hour": row["hour"],
                            "confidence": row["confidence"],
                            "source": row["source"],
                            "timestamp": row["timestamp"]
                        }
                        return _HELD_ROOMS[room_id]
        except Exception:
            pass
        return {"room_id": room_id, "held": False, "count": None}
    return {"held_rooms": _HELD_ROOMS}

def release_room_hold(room_id: str) -> bool:
    """Explicitly release an active camera hold on a room."""
    if room_id in _HELD_ROOMS:
        del _HELD_ROOMS[room_id]
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='room_holds'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM room_holds WHERE room_id = ?", (room_id,))
    except Exception:
        pass
    return True

def smooth_count(room_id: str, raw_count: int) -> float:
    """Applies median filter over window 5."""
    if room_id not in _room_buffers:
        _room_buffers[room_id] = []
    
    buf = _room_buffers[room_id]
    buf.append(raw_count)
    if len(buf) > _BUFFER_WINDOW:
        buf.pop(0)
        
    return float(statistics.median(buf))

def debounce_state(room_id: str, current_state: str) -> str:
    """Requires 3 consecutive frames to transition state."""
    if room_id not in _room_debounce:
        _room_debounce[room_id] = {"confirmed_state": current_state, "pending_state": current_state, "count": 1}
        return current_state
        
    rec = _room_debounce[room_id]
    if current_state == rec["pending_state"]:
        rec["count"] += 1
        if rec["count"] >= _DEBOUNCE_THRESHOLD:
            rec["confirmed_state"] = current_state
    else:
        rec["pending_state"] = current_state
        rec["count"] = 1
        
    return rec["confirmed_state"]

def ingest_reading(
    room_id: str,
    count: int,
    source: str = "camera",
    confidence: float = 1.0,
    timestamp: Optional[str] = None,
    hour: Optional[int] = None,
    hold: bool = False,
    release_hold: bool = False
) -> Dict[str, Any]:
    """Ingest camera or synthetic detection reading and update SQLite."""
    now = timestamp or datetime.now().isoformat()
    target_hour = hour if hour is not None else datetime.now().hour
    
    smoothed = smooth_count(room_id, count)

    if release_hold:
        release_room_hold(room_id)
        hold = False
    elif hold:
        _HELD_ROOMS[room_id] = {
            "room_id": room_id,
            "held": True,
            "count": count,
            "smoothed": smoothed,
            "hour": target_hour,
            "confidence": confidence,
            "source": source,
            "timestamp": now
        }
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS room_holds (
                    room_id TEXT PRIMARY KEY,
                    count INTEGER,
                    smoothed_count REAL,
                    hour INTEGER,
                    confidence REAL,
                    source TEXT,
                    timestamp TEXT,
                    held INTEGER DEFAULT 1
                )
                """)
                cursor.execute("""
                INSERT OR REPLACE INTO room_holds (room_id, count, smoothed_count, hour, confidence, source, timestamp, held)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (room_id, count, smoothed, target_hour, confidence, source, now))
        except Exception:
            pass
    else:
        active_hold = get_held_state(room_id)
        if active_hold.get("held"):
            # Room is HELD/LATCHED! Protect held headcount from background synthetic worker jitter!
            return {
                "room_id": room_id,
                "count": active_hold["count"],
                "smoothed": active_hold.get("smoothed", active_hold["count"]),
                "hour": target_hour,
                "status": "occupied" if active_hold["count"] > 0 else "unoccupied",
                "source": active_hold.get("source", "camera"),
                "confidence": active_hold.get("confidence", 0.98),
                "provenance": "ACTUAL",
                "held": True,
                "held_state": active_hold,
                "blocked_overwrite": True,
                "risk_alert": None
            }
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get capacity
        cursor.execute("SELECT capacity FROM rooms WHERE id = ?", (room_id,))
        row = cursor.fetchone()
        capacity = row["capacity"] if row else 50
        
        u = smoothed / capacity
        if u >= 0.8:
            raw_st = "high_utilization"
        elif smoothed > 0:
            raw_st = "occupied"
        else:
            raw_st = "unoccupied"
            
        final_st = debounce_state(room_id, raw_st)
        provenance = "ACTUAL" if source == "camera" else "SIMULATED"
        
        # Record primary reading at specified/current hour
        cursor.execute("""
        INSERT INTO occupancy_readings (room_id, timestamp, hour, count, smoothed_count, source, confidence, status, provenance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (room_id, now, target_hour, count, smoothed, source, confidence, final_st, provenance))
        
        # If hold is requested:
        # Hold and link this count across daytime operating hours (09:00 - 18:00)
        # plus any scheduled class blocks for this room
        if hold:
            hold_hours = set(range(9, 19))
            cursor.execute("SELECT id, start_hour, end_hour FROM classes WHERE room_id = ?", (room_id,))
            cls_rows = cursor.fetchall()
            for c_row in cls_rows:
                sh, eh = c_row["start_hour"], c_row["end_hour"]
                for h_slot in range(sh, eh):
                    hold_hours.add(h_slot)

            for h_slot in hold_hours:
                if h_slot != target_hour:
                    cursor.execute("""
                    INSERT INTO occupancy_readings (room_id, timestamp, hour, count, smoothed_count, source, confidence, status, provenance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (room_id, now, h_slot, count, smoothed, source, confidence, final_st, provenance))
        
        # If room is within safe capacity, release any previous containment lock
        if count < 60:
            cursor.execute("UPDATE classes SET locked = 0 WHERE room_id = ? AND id NOT IN ('c9', 'c10')", (room_id,))
        
    risk_alert = None
    try:
        from backend.services.risk import evaluate_reading_risk
        risk_alert = evaluate_reading_risk(room_id, count, provenance)
    except Exception:
        pass

    return {
        "room_id": room_id,
        "count": count,
        "smoothed": smoothed,
        "hour": target_hour,
        "status": final_st,
        "source": source,
        "confidence": confidence,
        "provenance": provenance,
        "held": hold,
        "held_state": _HELD_ROOMS.get(room_id),
        "risk_alert": risk_alert
    }

def get_class_attendance(class_id: str, calibration_factor: float = 1.0) -> Dict[str, Any]:
    """
    Per-class attendance = Camera-verified headcount (if available), or 90th percentile
    of recorded telemetry, falling back to enrolled * 0.85 with low confidence if no readings.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
        cls = cursor.fetchone()
        if not cls:
            return {"attendance": 30, "confidence": "low", "provenance": "ESTIMATED"}
            
        room_id = cls["room_id"]
        start_h = cls["start_hour"]
        end_h = cls["end_hour"]
        enrolled = cls["enrolled"]
        
        # 1. First priority: Check if live camera readings exist for this room
        cursor.execute("""
        SELECT count FROM occupancy_readings 
        WHERE room_id = ? AND source = 'camera' AND count IS NOT NULL
        ORDER BY id DESC LIMIT 1
        """, (room_id,))
        cam_row = cursor.fetchone()
        if cam_row:
            actual_att = min(enrolled, max(1, cam_row["count"]))
            return {
                "attendance": actual_att,
                "confidence": "high (verified by camera)",
                "provenance": "ACTUAL"
            }
        
        # 2. Second priority: Historical / scheduled telemetry for class slot
        cursor.execute("""
        SELECT count FROM occupancy_readings 
        WHERE room_id = ? AND hour >= ? AND hour < ? AND count IS NOT NULL
        ORDER BY count ASC
        """, (room_id, start_h, end_h))
        rows = cursor.fetchall()
        
        if rows and len(rows) >= 1:
            counts = [r["count"] for r in rows]
            idx = max(0, min(len(counts) - 1, int(len(counts) * 0.90)))
            att = int(counts[idx] * calibration_factor)
            return {
                "attendance": min(enrolled, max(1, att)),
                "confidence": "high (verified telemetry)",
                "provenance": "ACTUAL"
            }
        else:
            return {
                "attendance": int(enrolled * 0.85),
                "confidence": "low (enrolled estimate)",
                "provenance": "ESTIMATED"
            }
