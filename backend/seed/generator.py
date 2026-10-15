import json
import sqlite3
import math
from pathlib import Path
from backend.db import get_db, init_db

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def seed_all():
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Seed Building & Rooms
        with open(CONFIG_DIR / "building.json", "r", encoding="utf-8") as f:
            bdata = json.load(f)
            
        b = bdata["building"]
        cursor.execute("""
        INSERT OR REPLACE INTO buildings (id, name, floors_count, total_spaces, description)
        VALUES (?, ?, ?, ?, ?)
        """, (b["id"], b["name"], b["floors_count"], b["total_spaces"], b["description"]))
        
        for r in bdata["rooms"]:
            cursor.execute("""
            INSERT OR REPLACE INTO rooms (id, name, floor, type, capacity, hvac_kw, lighting_kw, plug_kw, accessible, equipment, sensor_offline, pos_3d)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["id"], r["name"], r["floor"], r["type"], r["capacity"],
                r["rated_kw"]["hvac"], r["rated_kw"]["lighting"], r["rated_kw"]["plug"],
                1 if r["accessible"] else 0,
                json.dumps(r["equipment"]),
                1 if r.get("sensor_offline", False) else 0,
                json.dumps(r["pos_3d"])
            ))
            
        # 2. Seed Timetable (Weekly Schedule)
        # Realistic schedule: includes an underutilized room (202 and 301) that can be consolidated
        classes_data = [
            # Monday
            ("c1", "CS101", "Introduction to Computing", "A", "Dr. Rao", "Monday", 9, 11, 42, "101", ["projector", "whiteboard"], 1, "CS101_GRP", 0),
            ("c2", "CS101", "Introduction to Computing", "B", "Dr. Rao", "Monday", 11, 13, 38, "101", ["projector", "whiteboard"], 1, "CS101_GRP", 0),
            ("c3", "CS204", "Data Structures Lab", "L1", "Prof. Sharma", "Monday", 10, 13, 28, "102", ["computers", "projector"], 1, None, 0),
            ("c4", "EE210", "Digital Circuits Lab", "E1", "Dr. Patel", "Monday", 14, 17, 24, "203", ["oscilloscopes", "soldering_stations"], 0, None, 0),
            ("c5", "MA201", "Discrete Mathematics", "M1", "Dr. Gupta", "Monday", 10, 12, 35, "201", ["projector", "whiteboard"], 1, None, 0),
            ("c6", "DS301", "UI/UX Design Studio", "D1", "Prof. Sen", "Monday", 14, 16, 25, "302", ["drafting_tables", "screens"], 0, None, 0),
            
            # Opportunities for consolidation:
            # Seminar Hall 202 has only ONE small class from 14:00 to 16:00 with 22 students!
            # It could easily move to Classroom 201 (which is empty after 12:00 and on the same floor),
            # allowing Seminar Hall 202 (4.5 kW HVAC + 1.0 kW lighting) to remain completely OFF!
            ("c7", "HU102", "Technical Communication", "H1", "Dr. Irene", "Monday", 14, 16, 22, "202", ["projector", "whiteboard"], 1, None, 0),
            
            # Classroom 301 has only ONE class from 11:00 to 13:00 with 18 students.
            # Could move to Classroom 201 or Lecture Hall A!
            ("c8", "ENV201", "Green Architecture Seminar", "G1", "Prof. Das", "Monday", 11, 13, 18, "301", ["projector", "whiteboard"], 0, None, 0),
            
            # Faculty meeting in Faculty Room (locked)
            ("c9", "FAC01", "Faculty Board Meeting", "SEC", "Dean Office", "Monday", 15, 17, 12, "204", ["desks"], 1, None, 1),
            
            # Reading Room peer study session
            ("c10", "LIB01", "Open Study & Mentorship", "GEN", "Library Staff", "Monday", 13, 16, 35, "103", ["study_desks"], 1, None, 1)
        ]
        
        cursor.execute("DELETE FROM classes")
        for c in classes_data:
            cursor.execute("""
            INSERT INTO classes (id, course_code, course_name, section, instructor, day_of_week, start_hour, end_hour, enrolled, room_id, required_equipment, accessibility_needed, compatibility_group, locked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], json.dumps(c[10]), c[11], c[12], c[13]))
            
        # 3. Seed Occupancy Readings (24 Hours for a Typical Weekday)
        # Profiles matching the UI pattern
        MID = {
            'A': '15998469862', # High occupancy
            'U': '12431111110', # Underutilized (e.g. 202, 302)
            'O': '37888888850', # Office
            'T': '26887578750', # Lab
            'L': '13445665431'  # Lounge / Reading
        }
        
        room_profiles = {
            '101': ('A', 80, False),
            '102': ('T', 40, False),
            '103': ('L', 60, False),
            '104': ('O', 12, False),
            '201': ('A', 50, False),
            '202': ('U', 60, False), # Seminar Hall - Underutilized!
            '203': ('T', 30, False),
            '204': ('O', 14, False),
            '301': ('A', 50, False),
            '302': ('U', 35, False),
            '303': ('O', 16, True),  # Sensor offline!
            '304': ('L', 40, False)
        }
        
        cursor.execute("DELETE FROM occupancy_readings")
        cursor.execute("DELETE FROM energy_readings")
        
        for rid, (pr, cap, is_offline) in room_profiles.items():
            pattern = '0000000' + MID[pr] + '000000'
            for h in range(24):
                if is_offline:
                    count = None
                    smoothed = None
                    status = "offline"
                    provenance = "SIMULATED"
                else:
                    d = int(pattern[h])
                    jitter = ((int(rid) * 31 + h * 17) % 5 - 2) * (0.5 if cap < 20 else 1) if d else 0
                    count = max(0, min(cap, round(cap * d / 9.0 * 0.92 + jitter)))
                    smoothed = float(count)
                    u = count / cap
                    if u >= 0.8:
                        status = "high_utilization"
                    elif count > 0:
                        status = "occupied"
                    else:
                        status = "unoccupied"
                    provenance = "SIMULATED"
                    
                cursor.execute("""
                INSERT INTO occupancy_readings (room_id, timestamp, hour, count, smoothed_count, source, confidence, status, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (rid, f"2026-10-15T{h:02d}:00:00", h, count, smoothed, "simulated", 1.0 if not is_offline else 0.0, status, provenance))
                
                # Baseline energy calculation
                # Rated kw from bdata
                rm_cfg = next(x for x in bdata["rooms"] if x["id"] == rid)
                rk = rm_cfg["rated_kw"]
                
                u_eff = 0.5 if count is None else (count / cap)
                in_schedule = (7 <= h < 19)
                
                # Baseline: fixed schedule 07:00-19:00
                hvac = (rk["hvac"] * (0.85 + 0.15 * u_eff)) if in_schedule else (rk["hvac"] * 0.10)
                light = rk["lighting"] if in_schedule else (rk["lighting"] * 0.05)
                plug = rk["plug"] * (0.25 + 0.75 * u_eff if (7 <= h < 19) else 0.20)
                total = hvac + light + plug
                
                cursor.execute("""
                INSERT INTO energy_readings (room_id, hour, hvac_kw, lighting_kw, plug_kw, total_kw, scenario, provenance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (rid, h, round(hvac, 2), round(light, 2), round(plug, 2), round(total, 2), "baseline", "ESTIMATED"))

        print("Database successfully seeded with building, rooms, timetable, occupancy, and baseline energy!")

if __name__ == "__main__":
    seed_all()
