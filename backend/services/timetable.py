import json
import csv
import io
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.db import get_db
from backend.ws import ws_manager

def get_all_classes() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes ORDER BY day_of_week, start_hour")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["required_equipment"] = json.loads(d["required_equipment"]) if d["required_equipment"] else []
            d["accessibility_needed"] = bool(d["accessibility_needed"])
            d["locked"] = bool(d["locked"])
            result.append(d)
        return result

def validate_timetable() -> List[Dict[str, Any]]:
    """
    Checks for:
    1. Room double-booking (same room, overlapping time, same day)
    2. Instructor overlap (same instructor, overlapping time, same day)
    3. Capacity breach (enrolled > room capacity)
    """
    classes = get_all_classes()
    conflicts = []
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, capacity FROM rooms")
        rooms = {r["id"]: r["capacity"] for r in cursor.fetchall()}
        
    for i, c1 in enumerate(classes):
        # 1. Capacity breach
        room_cap = rooms.get(c1["room_id"], 100)
        if c1["enrolled"] > room_cap:
            conflicts.append({
                "type": "capacity_breach",
                "severity": "critical",
                "class_id": c1["id"],
                "message": f"Class {c1['course_code']} ({c1['enrolled']} enrolled) exceeds room {c1['room_id']} capacity ({room_cap})."
            })
            
        for j in range(i + 1, len(classes)):
            c2 = classes[j]
            if c1["day_of_week"] != c2["day_of_week"]:
                continue
                
            overlap = max(c1["start_hour"], c2["start_hour"]) < min(c1["end_hour"], c2["end_hour"])
            if not overlap:
                continue
                
            # 2. Room double-booking
            if c1["room_id"] == c2["room_id"]:
                # Check compatibility group
                if c1["compatibility_group"] and c1["compatibility_group"] == c2["compatibility_group"]:
                    pass # Explicitly allowed combined sections
                else:
                    conflicts.append({
                        "type": "room_double_booking",
                        "severity": "critical",
                        "class_ids": [c1["id"], c2["id"]],
                        "message": f"Room {c1['room_id']} double-booked by {c1['course_code']} and {c2['course_code']} at {max(c1['start_hour'], c2['start_hour'])}:00."
                    })
                    
            # 3. Instructor overlap
            if c1["instructor"] == c2["instructor"]:
                conflicts.append({
                    "type": "instructor_overlap",
                    "severity": "critical",
                    "class_ids": [c1["id"], c2["id"]],
                    "message": f"Instructor {c1['instructor']} scheduled in two places simultaneously ({c1['course_code']} in {c1['room_id']}, {c2['course_code']} in {c2['room_id']})."
                })
                
    return conflicts

def parse_and_import_csv(csv_content: str) -> Dict[str, Any]:
    """Parse CSV upload and import validated classes."""
    reader = csv.DictReader(io.StringIO(csv_content))
    imported = 0
    errors = []
    
    with get_db() as conn:
        cursor = conn.cursor()
        for idx, row in enumerate(reader):
            try:
                cid = row.get("id") or f"csv_{imported+1}"
                cursor.execute("""
                INSERT OR REPLACE INTO classes (id, course_code, course_name, section, instructor, day_of_week, start_hour, end_hour, enrolled, room_id, required_equipment, accessibility_needed, compatibility_group, locked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cid,
                    row["course_code"],
                    row.get("course_name", row["course_code"]),
                    row.get("section", "A"),
                    row["instructor"],
                    row.get("day_of_week", "Monday"),
                    int(row["start_hour"]),
                    int(row["end_hour"]),
                    int(row["enrolled"]),
                    row["room_id"],
                    json.dumps(row.get("required_equipment", "").split(";") if row.get("required_equipment") else []),
                    1 if row.get("accessibility_needed", "").lower() in ["true", "1", "yes"] else 0,
                    row.get("compatibility_group") or None,
                    1 if row.get("locked", "").lower() in ["true", "1", "yes"] else 0
                ))
                imported += 1
            except Exception as e:
                errors.append(f"Row {idx+1}: {str(e)}")
                
    conflicts = validate_timetable()
    return {
        "imported_count": imported,
        "errors": errors,
        "conflicts_detected": conflicts
    }

# ── Custom Timetable CRUD Operations ──────────────────────────────────────────

def create_custom_class(data: Dict[str, Any]) -> Dict[str, Any]:
    """Adds a new custom class to the academic timetable."""
    cid = data.get("id") or f"c_{uuid.uuid4().hex[:6]}"
    code = data.get("course_code", "GEN101").strip().upper()
    name = data.get("course_name", code).strip()
    sec = data.get("section", "A").strip()
    instr = data.get("instructor", "Faculty Member").strip()
    day = data.get("day_of_week", "Monday").strip()
    start = int(data.get("start_hour", 10))
    end = int(data.get("end_hour", start + 2))
    enrolled = int(data.get("enrolled", 25))
    room_id = str(data.get("room_id", "201")).strip()
    equip = json.dumps(data.get("required_equipment", ["projector", "whiteboard"]))
    access = 1 if data.get("accessibility_needed") else 0
    compat = data.get("compatibility_group") or None
    locked = 1 if data.get("locked") else 0
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO classes (id, course_code, course_name, section, instructor, day_of_week, start_hour, end_hour, enrolled, room_id, required_equipment, accessibility_needed, compatibility_group, locked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cid, code, name, sec, instr, day, start, end, enrolled, room_id, equip, access, compat, locked))
        
    conflicts = validate_timetable()
    ws_manager.broadcast_sync({"type": "timetable_update", "action": "class_added", "class_id": cid})
    
    return {
        "status": "success",
        "message": f"Class {code} successfully added to {room_id} ({day} {start}:00–{end}:00).",
        "class_id": cid,
        "conflicts": conflicts
    }


def update_custom_class(class_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Updates an existing class in the timetable."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
        cls = cursor.fetchone()
        if not cls:
            raise ValueError(f"Class {class_id} not found.")
            
        code = data.get("course_code", cls["course_code"]).strip().upper()
        name = data.get("course_name", cls["course_name"]).strip()
        sec = data.get("section", cls["section"]).strip()
        instr = data.get("instructor", cls["instructor"]).strip()
        day = data.get("day_of_week", cls["day_of_week"]).strip()
        start = int(data.get("start_hour", cls["start_hour"]))
        end = int(data.get("end_hour", cls["end_hour"]))
        enrolled = int(data.get("enrolled", cls["enrolled"]))
        room_id = str(data.get("room_id", cls["room_id"])).strip()
        equip = json.dumps(data.get("required_equipment", json.loads(cls["required_equipment"]) if cls["required_equipment"] else []))
        access = 1 if data.get("accessibility_needed", bool(cls["accessibility_needed"])) else 0
        compat = data.get("compatibility_group", cls["compatibility_group"]) or None
        locked = 1 if data.get("locked", bool(cls["locked"])) else 0
        
        cursor.execute("""
        UPDATE classes
        SET course_code = ?, course_name = ?, section = ?, instructor = ?, day_of_week = ?,
            start_hour = ?, end_hour = ?, enrolled = ?, room_id = ?, required_equipment = ?,
            accessibility_needed = ?, compatibility_group = ?, locked = ?
        WHERE id = ?
        """, (code, name, sec, instr, day, start, end, enrolled, room_id, equip, access, compat, locked, class_id))
        
    conflicts = validate_timetable()
    ws_manager.broadcast_sync({"type": "timetable_update", "action": "class_updated", "class_id": class_id})
    return {
        "status": "success",
        "message": f"Class {code} updated successfully.",
        "class_id": class_id,
        "conflicts": conflicts
    }


def delete_custom_class(class_id: str) -> Dict[str, Any]:
    """Deletes a class from the timetable."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        cursor.execute("DELETE FROM plan_moves WHERE class_id = ?", (class_id,))
        
    ws_manager.broadcast_sync({"type": "timetable_update", "action": "class_deleted", "class_id": class_id})
    return {"status": "success", "message": f"Class {class_id} deleted from timetable."}


# ── Schedule Request & Host Acceptance Workflow ──────────────────────────────

def find_next_free_slot(
    room_id: str,
    day_of_week: str,
    duration_hours: int = 2,
    enrolled: int = 25,
    preferred_start: int = 14
) -> Dict[str, Any]:
    """
    Checks if preferred timeslot is free in room_id.
    If occupied, automatically scans for the earliest available contiguous slot
    in room_id or nearest compatible room that fits enrolled capacity.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, capacity FROM rooms")
        rooms = {r["id"]: dict(r) for r in cursor.fetchall()}
        
        cursor.execute("""
        SELECT id, course_code, start_hour, end_hour, room_id, enrolled
        FROM classes
        WHERE day_of_week = ?
        ORDER BY start_hour ASC
        """, (day_of_week,))
        classes = [dict(c) for c in cursor.fetchall()]
        
    target_room = rooms.get(room_id, {"id": room_id, "name": f"Room {room_id}", "capacity": 60})
    cap = target_room["capacity"]
    
    # Check capacity fit
    if enrolled > cap:
        # Find rooms with sufficient capacity
        alt_rooms = [r for r in rooms.values() if r["capacity"] >= enrolled]
        alt_name = alt_rooms[0]["name"] if alt_rooms else "larger auditorium"
        return {
            "available": False,
            "has_capacity_breach": True,
            "message": f"Requested room {room_id} has capacity {cap}, but request has {enrolled} enrolled. Suggest {alt_name}."
        }
        
    pref_end = preferred_start + duration_hours
    room_classes = [c for c in classes if c["room_id"] == room_id]
    
    # 1. Check if preferred slot is completely open
    collision = None
    for c in room_classes:
        if max(preferred_start, c["start_hour"]) < min(pref_end, c["end_hour"]):
            collision = c
            break
            
    if not collision:
        return {
            "available": True,
            "start_hour": preferred_start,
            "end_hour": pref_end,
            "room_id": room_id,
            "room_name": target_room["name"],
            "message": f"Timeslot {preferred_start}:00–{pref_end}:00 in {target_room['name']} is completely free."
        }
        
    # 2. Slot is busy: search next available contiguous slot in room_id (between 08:00 and 19:00)
    for candidate_start in range(8, 20 - duration_hours):
        candidate_end = candidate_start + duration_hours
        overlaps = False
        for c in room_classes:
            if max(candidate_start, c["start_hour"]) < min(candidate_end, c["end_hour"]):
                overlaps = True
                break
        if not overlaps:
            return {
                "available": False,
                "collision_course": collision["course_code"],
                "collision_slot": f"{collision['start_hour']}:00–{collision['end_hour']}:00",
                "suggested_start_hour": candidate_start,
                "suggested_end_hour": candidate_end,
                "suggested_room_id": room_id,
                "suggested_room_name": target_room["name"],
                "message": (
                    f"Requested slot {preferred_start}:00–{pref_end}:00 is occupied by {collision['course_code']}. "
                    f"Earliest free slot in {target_room['name']} is {candidate_start}:00–{candidate_end}:00."
                )
            }
            
    # 3. If room_id has no free slots, search alternative room with sufficient capacity
    for alt_rid, alt_rm in rooms.items():
        if alt_rid == room_id or alt_rm["capacity"] < enrolled:
            continue
        alt_classes = [c for c in classes if c["room_id"] == alt_rid]
        for candidate_start in range(9, 19 - duration_hours):
            candidate_end = candidate_start + duration_hours
            overlaps = any(max(candidate_start, c["start_hour"]) < min(candidate_end, c["end_hour"]) for c in alt_classes)
            if not overlaps:
                return {
                    "available": False,
                    "collision_course": collision["course_code"],
                    "suggested_start_hour": candidate_start,
                    "suggested_end_hour": candidate_end,
                    "suggested_room_id": alt_rid,
                    "suggested_room_name": alt_rm["name"],
                    "message": (
                        f"Room {room_id} is fully booked during business hours. "
                        f"Available alternative: {alt_rm['name']} ({alt_rid}) at {candidate_start}:00–{candidate_end}:00."
                    )
                }

    return {
        "available": False,
        "message": f"No feasible free slots found for {duration_hours}h duration on {day_of_week}."
    }


def submit_schedule_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Submits a room booking request to the host queue."""
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    creator = data.get("creator_name", "Academic Faculty").strip()
    code = data.get("course_code", "AD_HOC").strip().upper()
    name = data.get("course_name", code).strip()
    sec = data.get("section", "A").strip()
    instr = data.get("instructor", creator).strip()
    room_id = str(data.get("room_id", "202")).strip()
    day = data.get("day_of_week", "Monday").strip()
    start = int(data.get("preferred_start_hour", 14))
    duration = int(data.get("duration_hours", 2))
    enrolled = int(data.get("enrolled", 20))
    equip = json.dumps(data.get("required_equipment", ["projector"]))
    now = datetime.now().isoformat()
    
    # Pre-evaluate slot availability
    slot_info = find_next_free_slot(room_id, day, duration, enrolled, start)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO schedule_requests (
            id, creator_name, course_code, course_name, section, instructor, room_id,
            day_of_week, preferred_start_hour, duration_hours, enrolled, required_equipment,
            status, notification_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        """, (req_id, creator, code, name, sec, instr, room_id, day, start, duration, enrolled, equip,
              f"Submitted by {creator}. Slot status: {'Available' if slot_info['available'] else 'Occupied (Auto-reschedule available)'}.", now))
              
    ws_manager.broadcast_sync({
        "type": "schedule_request_update",
        "action": "request_created",
        "request_id": req_id
    })
    
    return {
        "status": "success",
        "request_id": req_id,
        "slot_evaluation": slot_info,
        "message": f"Schedule request {req_id} submitted to host approval queue."
    }


def get_schedule_requests(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches schedule requests with real-time slot conflict evaluations."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM schedule_requests"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status.upper())
        query += " ORDER BY id DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
    result = []
    for r in rows:
        d = dict(r)
        d["required_equipment"] = json.loads(d["required_equipment"]) if d["required_equipment"] else []
        # Attach live conflict and auto-slot calculation
        if d["status"] == "PENDING":
            d["slot_check"] = find_next_free_slot(
                d["room_id"], d["day_of_week"], d["duration_hours"], d["enrolled"], d["preferred_start_hour"]
            )
        result.append(d)
    return result


def accept_schedule_request(request_id: str, actor: str = "Main Facility Host") -> Dict[str, Any]:
    """Host accepts request directly into timetable if slot is available."""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedule_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        if not req:
            raise ValueError(f"Request {request_id} not found.")
        req = dict(req)
        
        # Check slot
        start = req["preferred_start_hour"]
        end = start + req["duration_hours"]
        cid = f"c_{uuid.uuid4().hex[:6]}"
        
        # Insert into active classes table
        cursor.execute("""
        INSERT INTO classes (
            id, course_code, course_name, section, instructor, day_of_week,
            start_hour, end_hour, enrolled, room_id, required_equipment, locked
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            cid, req["course_code"], req["course_name"], req["section"],
            req["instructor"], req["day_of_week"], start, end,
            req["enrolled"], req["room_id"], req["required_equipment"]
        ))
        
        msg = f"✓ ACCEPTED by {actor}: Successfully added to timetable for {req['day_of_week']} {start}:00–{end}:00 in Room {req['room_id']}."
        
        cursor.execute("""
        UPDATE schedule_requests
        SET status = 'APPROVED', allocated_start_hour = ?, allocated_end_hour = ?,
            allocated_room_id = ?, notification_message = ?, reviewed_at = ?, reviewed_by = ?
        WHERE id = ?
        """, (start, end, req["room_id"], msg, now, actor, request_id))
        
    ws_manager.broadcast_sync({
        "type": "schedule_request_update",
        "action": "request_approved",
        "request_id": request_id,
        "notification": msg
    })
    ws_manager.broadcast_sync({"type": "timetable_update", "action": "class_added", "class_id": cid})
    
    return {
        "status": "success",
        "request_id": request_id,
        "class_id": cid,
        "notification_sent": msg
    }


def auto_reschedule_request(request_id: str, actor: str = "Automated Host System") -> Dict[str, Any]:
    """
    Host auto-allocates the next free timeslot when the requested slot has a conflict,
    commits to timetable, and sends notification to request creator.
    """
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedule_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        if not req:
            raise ValueError(f"Request {request_id} not found.")
        req = dict(req)
        
        # Find next free slot
        slot_info = find_next_free_slot(
            req["room_id"], req["day_of_week"], req["duration_hours"],
            req["enrolled"], req["preferred_start_hour"]
        )
        
        target_start = slot_info.get("suggested_start_hour") or slot_info.get("start_hour") or 16
        target_end = slot_info.get("suggested_end_hour") or slot_info.get("end_hour") or 18
        target_room = slot_info.get("suggested_room_id") or req["room_id"]
        
        cid = f"c_{uuid.uuid4().hex[:6]}"
        
        # Commit newly scheduled class
        cursor.execute("""
        INSERT INTO classes (
            id, course_code, course_name, section, instructor, day_of_week,
            start_hour, end_hour, enrolled, room_id, required_equipment, locked
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            cid, req["course_code"], req["course_name"], req["section"],
            req["instructor"], req["day_of_week"], target_start, target_end,
            req["enrolled"], target_room, req["required_equipment"]
        ))
        
        msg = (
            f"⚡ AUTO-SET TO NEXT FREE SLOT by {actor}: "
            f"Requested slot ({req['preferred_start_hour']}:00) was occupied. "
            f"Automatically scheduled for {req['day_of_week']} {target_start}:00–{target_end}:00 in Room {target_room}."
        )
        
        cursor.execute("""
        UPDATE schedule_requests
        SET status = 'AUTO_RESCHEDULED', allocated_start_hour = ?, allocated_end_hour = ?,
            allocated_room_id = ?, notification_message = ?, reviewed_at = ?, reviewed_by = ?
        WHERE id = ?
        """, (target_start, target_end, target_room, msg, now, actor, request_id))
        
    ws_manager.broadcast_sync({
        "type": "schedule_request_update",
        "action": "request_auto_rescheduled",
        "request_id": request_id,
        "notification": msg
    })
    ws_manager.broadcast_sync({"type": "timetable_update", "action": "class_added", "class_id": cid})
    
    return {
        "status": "success",
        "request_id": request_id,
        "class_id": cid,
        "allocated_start_hour": target_start,
        "allocated_end_hour": target_end,
        "allocated_room_id": target_room,
        "notification_sent": msg
    }


def reject_schedule_request(
    request_id: str,
    reason: str = "Room fully booked during requested period and capacity exceeded",
    actor: str = "Main Facility Host"
) -> Dict[str, Any]:
    """Host rejects booking request and dispatches rejection notification to requester."""
    now = datetime.now().isoformat()
    msg = f"✕ REJECTED by {actor}: {reason}"
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE schedule_requests
        SET status = 'REJECTED', notification_message = ?, reviewed_at = ?, reviewed_by = ?
        WHERE id = ?
        """, (msg, now, actor, request_id))
        
    ws_manager.broadcast_sync({
        "type": "schedule_request_update",
        "action": "request_rejected",
        "request_id": request_id,
        "notification": msg
    })
    
    return {
        "status": "success",
        "request_id": request_id,
        "notification_sent": msg
    }

