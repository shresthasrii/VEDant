import json
import csv
import io
from typing import List, Dict, Any
from backend.db import get_db

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
