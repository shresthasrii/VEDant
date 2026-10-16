from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from backend.services.timetable import (
    get_all_classes, validate_timetable, parse_and_import_csv,
    create_custom_class, update_custom_class, delete_custom_class,
    find_next_free_slot, submit_schedule_request, get_schedule_requests,
    accept_schedule_request, auto_reschedule_request, reject_schedule_request
)

router = APIRouter(prefix="/timetable", tags=["timetable"])

class CustomClassRequest(BaseModel):
    id: Optional[str] = None
    course_code: str
    course_name: Optional[str] = None
    section: Optional[str] = "A"
    instructor: str
    day_of_week: Optional[str] = "Monday"
    start_hour: int = Field(..., ge=0, le=23)
    end_hour: int = Field(..., ge=1, le=24)
    enrolled: int = Field(..., ge=1)
    room_id: str
    required_equipment: Optional[List[str]] = ["projector", "whiteboard"]
    accessibility_needed: Optional[bool] = False
    compatibility_group: Optional[str] = None
    locked: Optional[bool] = False

class ScheduleBookingRequest(BaseModel):
    creator_name: str
    course_code: str
    course_name: str
    section: Optional[str] = "A"
    instructor: str
    room_id: str
    day_of_week: Optional[str] = "Monday"
    preferred_start_hour: int = Field(14, ge=8, le=19)
    duration_hours: int = Field(2, ge=1, le=6)
    enrolled: int = Field(20, ge=1)
    required_equipment: Optional[List[str]] = ["projector"]

class RejectRequestPayload(BaseModel):
    reason: Optional[str] = "Room unavailable during requested slot and capacity exceeded"

# ── Baseline Timetable Endpoints ──────────────────────────────────────────────

@router.get("")
def get_timetable() -> Dict[str, Any]:
    classes = get_all_classes()
    conflicts = validate_timetable()
    return {
        "classes": classes,
        "total_classes": len(classes),
        "conflicts": conflicts,
        "provenance": "SIMULATED"
    }

@router.post("")
async def upload_timetable_csv(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
        
    contents = await file.read()
    text = contents.decode("utf-8")
    result = parse_and_import_csv(text)
    return result

# ── Custom Timetable Class CRUD ───────────────────────────────────────────────

@router.post("/class")
def add_custom_class(req: CustomClassRequest) -> Dict[str, Any]:
    """Adds a new custom class sequence to the timetable."""
    try:
        return create_custom_class(req.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/class/{class_id}")
def edit_custom_class(class_id: str, req: CustomClassRequest) -> Dict[str, Any]:
    """Edits an existing class sequence in the timetable."""
    try:
        return update_custom_class(class_id, req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/class/{class_id}")
def remove_custom_class(class_id: str) -> Dict[str, Any]:
    """Deletes a class sequence from the timetable."""
    try:
        return delete_custom_class(class_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── Slot Availability & Auto-Search ───────────────────────────────────────────

@router.get("/check-slot")
def check_room_slot(
    room_id: str = Query("202"),
    day_of_week: str = Query("Monday"),
    start_hour: int = Query(14),
    duration_hours: int = Query(2),
    enrolled: int = Query(20)
) -> Dict[str, Any]:
    """Checks if a room slot is free or returns the next available free slot."""
    return find_next_free_slot(
        room_id=room_id,
        day_of_week=day_of_week,
        duration_hours=duration_hours,
        enrolled=enrolled,
        preferred_start=start_hour
    )

# ── Schedule Request & Host Review Queue ─────────────────────────────────────

@router.post("/requests")
def create_booking_request(req: ScheduleBookingRequest) -> Dict[str, Any]:
    """Creator submits a schedule booking request to the host queue."""
    try:
        return submit_schedule_request(req.model_dump())
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/requests")
def list_booking_requests(status: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Host or requesters list booking requests with live conflict evaluations."""
    requests = get_schedule_requests(status=status)
    return {
        "total_requests": len(requests),
        "pending_count": sum(1 for r in requests if r["status"] == "PENDING"),
        "approved_count": sum(1 for r in requests if r["status"] in ["APPROVED", "AUTO_RESCHEDULED"]),
        "requests": requests
    }

@router.post("/requests/{request_id}/accept")
def host_accept_request(request_id: str, actor: str = Query("Main Facility Host")) -> Dict[str, Any]:
    """Main Host accepts request if slot is open, committing to timetable."""
    try:
        return accept_schedule_request(request_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/requests/{request_id}/auto-reschedule")
def host_auto_reschedule_request(request_id: str, actor: str = Query("Main Facility Host")) -> Dict[str, Any]:
    """Main Host auto-allocates next available free slot and commits to timetable."""
    try:
        return auto_reschedule_request(request_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/requests/{request_id}/reject")
def host_reject_request(
    request_id: str,
    payload: RejectRequestPayload,
    actor: str = Query("Main Facility Host")
) -> Dict[str, Any]:
    """Main Host rejects request and sends rejection notice to requester."""
    try:
        return reject_schedule_request(request_id, reason=payload.reason, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
