import io
import csv
from fastapi import APIRouter, HTTPException, Response
from backend.db import get_db

router = APIRouter(prefix="/export", tags=["export"])

@router.get("/{report}.csv")
def export_csv(report: str):
    output = io.StringIO()
    writer = csv.writer(output)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        if report in ["timetable", "schedule"]:
            cursor.execute("SELECT id, course_code, course_name, section, instructor, day_of_week, start_hour, end_hour, enrolled, room_id FROM classes")
            rows = cursor.fetchall()
            writer.writerow(["ID", "Course Code", "Course Name", "Section", "Instructor", "Day", "Start Hour", "End Hour", "Enrolled", "Room ID"])
            for r in rows:
                writer.writerow(list(r))
                
        elif report in ["energy", "energy_report"]:
            cursor.execute("SELECT e.room_id, r.name, e.hour, e.hvac_kw, e.lighting_kw, e.plug_kw, e.total_kw, e.scenario FROM energy_readings e JOIN rooms r ON e.room_id = r.id")
            rows = cursor.fetchall()
            writer.writerow(["Room ID", "Room Name", "Hour", "HVAC kW", "Lighting kW", "Plug kW", "Total kW", "Scenario"])
            for r in rows:
                writer.writerow(list(r))
                
        elif report in ["occupancy", "occupancy_report"]:
            cursor.execute("SELECT o.room_id, r.name, o.timestamp, o.hour, o.count, o.smoothed_count, o.source, o.status, o.provenance FROM occupancy_readings o JOIN rooms r ON o.room_id = r.id")
            rows = cursor.fetchall()
            writer.writerow(["Room ID", "Room Name", "Timestamp", "Hour", "Count", "Smoothed Count", "Source", "Status", "Provenance"])
            for r in rows:
                writer.writerow(list(r))
                
        elif report in ["audit", "audit_log"]:
            cursor.execute("SELECT id, timestamp, user_action, entity_type, entity_id, details FROM audit_log ORDER BY id DESC")
            rows = cursor.fetchall()
            writer.writerow(["ID", "Timestamp", "Action", "Entity Type", "Entity ID", "Details"])
            for r in rows:
                writer.writerow(list(r))
        else:
            raise HTTPException(status_code=400, detail=f"Unknown report type: '{report}'. Available: timetable, energy, occupancy, audit")
            
    content = output.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=verdant_{report}.csv"}
    )
