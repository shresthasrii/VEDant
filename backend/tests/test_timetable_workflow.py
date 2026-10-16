import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.services.timetable import get_all_classes, get_schedule_requests

client = TestClient(app)

def test_custom_class_crud():
    # 1. Add custom class
    res = client.post("/timetable/class", json={
        "id": "test_c99",
        "course_code": "CS999",
        "course_name": "Advanced Quantum Computing",
        "section": "Q1",
        "instructor": "Dr. Turing",
        "day_of_week": "Monday",
        "start_hour": 8,
        "end_hour": 10,
        "enrolled": 30,
        "room_id": "201"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # Verify in timetable
    classes = get_all_classes()
    assert any(c["id"] == "test_c99" for c in classes)
    
    # 2. Edit custom class
    edit_res = client.put("/timetable/class/test_c99", json={
        "course_code": "CS999",
        "course_name": "Advanced Quantum Computing Updated",
        "section": "Q2",
        "instructor": "Dr. Turing",
        "day_of_week": "Monday",
        "start_hour": 8,
        "end_hour": 10,
        "enrolled": 35,
        "room_id": "201"
    })
    assert edit_res.status_code == 200
    classes = get_all_classes()
    updated = next(c for c in classes if c["id"] == "test_c99")
    assert updated["enrolled"] == 35
    assert updated["section"] == "Q2"
    
    # 3. Delete custom class
    del_res = client.delete("/timetable/class/test_c99")
    assert del_res.status_code == 200
    classes = get_all_classes()
    assert not any(c["id"] == "test_c99" for c in classes)


def test_schedule_request_direct_accept():
    # Submit request for 08:00–10:00 in Room 102 (which is free before 10:00)
    req_res = client.post("/timetable/requests", json={
        "creator_name": "Prof. Charles (AI Lab)",
        "course_code": "AI401",
        "course_name": "Neural Networks Lab",
        "section": "N1",
        "instructor": "Prof. Charles",
        "room_id": "102",
        "day_of_week": "Monday",
        "preferred_start_hour": 8,
        "duration_hours": 2,
        "enrolled": 25
    })
    assert req_res.status_code == 200
    data = req_res.json()
    req_id = data["request_id"]
    assert req_id is not None
    assert data["slot_evaluation"]["available"] is True
    
    # Host accepts request
    acc_res = client.post(f"/timetable/requests/{req_id}/accept?actor=Facility%20Dean")
    assert acc_res.status_code == 200
    acc_data = acc_res.json()
    assert "✓ ACCEPTED" in acc_data["notification_sent"]
    
    # Verify in classes table
    classes = get_all_classes()
    assert any(c["course_code"] == "AI401" for c in classes)
    
    # Clean up created class
    client.delete(f"/timetable/class/{acc_data['class_id']}")


def test_schedule_request_auto_reschedule():
    # Room 202 is occupied between 14:00 and 16:00 by HU102
    req_res = client.post("/timetable/requests", json={
        "creator_name": "Dr. Anita (Robotics)",
        "course_code": "ROBO201",
        "course_name": "Kinematics Seminar",
        "section": "K1",
        "instructor": "Dr. Anita",
        "room_id": "202",
        "day_of_week": "Monday",
        "preferred_start_hour": 14, # Collides with HU102
        "duration_hours": 2,
        "enrolled": 20
    })
    assert req_res.status_code == 200
    data = req_res.json()
    req_id = data["request_id"]
    assert data["slot_evaluation"]["available"] is False
    assert "HU102" in data["slot_evaluation"].get("collision_course", "") or data["slot_evaluation"].get("suggested_start_hour") is not None
    
    # Host triggers auto-reschedule to next free slot
    auto_res = client.post(f"/timetable/requests/{req_id}/auto-reschedule?actor=Automated%20Host")
    assert auto_res.status_code == 200
    auto_data = auto_res.json()
    assert "⚡ AUTO-SET TO NEXT FREE SLOT" in auto_data["notification_sent"]
    assert auto_data["allocated_start_hour"] != 14  # Shifted away from conflict
    
    # Verify in classes
    classes = get_all_classes()
    assert any(c["course_code"] == "ROBO201" for c in classes)
    
    # Clean up
    client.delete(f"/timetable/class/{auto_data['class_id']}")


def test_schedule_request_reject():
    req_res = client.post("/timetable/requests", json={
        "creator_name": "Guest Lecturer",
        "course_code": "GUEST99",
        "course_name": "Industry Talk",
        "section": "G1",
        "instructor": "Guest",
        "room_id": "202",
        "day_of_week": "Monday",
        "preferred_start_hour": 15,
        "duration_hours": 3,
        "enrolled": 55
    })
    assert req_res.status_code == 200
    req_id = req_res.json()["request_id"]
    
    # Host rejects
    rej_res = client.post(f"/timetable/requests/{req_id}/reject?actor=Academic%20Dean", json={
        "reason": "Lecture hall booked for campus examination"
    })
    assert rej_res.status_code == 200
    assert "✕ REJECTED" in rej_res.json()["notification_sent"]
    
    # Verify in requests
    reqs = get_schedule_requests(status="REJECTED")
    rejected_item = next(r for r in reqs if r["id"] == req_id)
    assert rejected_item["status"] == "REJECTED"
    assert "examination" in rejected_item["notification_message"].lower()
