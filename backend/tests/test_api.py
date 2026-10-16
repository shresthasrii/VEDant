import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data

def test_rooms_endpoint():
    res = client.get("/rooms")
    assert res.status_code == 200
    rooms = res.json()
    assert len(rooms) >= 12
    # Verify provenance tag on each room
    assert all("provenance" in r for r in rooms)

def test_timetable_endpoint():
    res = client.get("/timetable")
    assert res.status_code == 200
    data = res.json()
    assert "classes" in data
    assert "conflicts" in data

def test_optimize_endpoint():
    res = client.post("/optimize", json={"day": "Monday", "capacity_margin": 0.10, "disruption_penalty": 2.0})
    assert res.status_code == 200
    plan = res.json()
    assert "id" in plan
    assert plan["status"] == "pending_approval"
    assert "savings_kwh" in plan

def test_energy_endpoint():
    res = client.get("/energy?scenario=baseline")
    assert res.status_code == 200
    data = res.json()
    assert "total_kwh" in data
    assert "hourly_kw" in data
    assert len(data["hourly_kw"]) == 24

def test_export_endpoint():
    res = client.get("/export/timetable.csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]

def test_occupancy_ingest_and_hold_persistence():
    # 1. Ingest reading with hold: True
    post_res = client.post("/ingest/occupancy", json={
        "room_id": "202",
        "count": 4,
        "confidence": 0.98,
        "source": "camera",
        "hour": 15,
        "hold": True
    })
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["status"] == "success"
    assert data["held"] is True

    # 2. Verify hold state endpoint
    hold_res = client.get("/occupancy/hold-state?room=202")
    assert hold_res.status_code == 200
    h_data = hold_res.json()
    assert h_data["held"] is True
    assert h_data["count"] == 4

    # 3. Verify continuous 24-hour telemetry returns held count across daytime hours
    t24_res = client.get("/occupancy/24h?room=202")
    assert t24_res.status_code == 200
    t24 = t24_res.json()
    assert t24["is_held"] is True
    assert t24["held_count"] == 4
    timeline = t24["hourly_timeline"]
    assert len(timeline) == 24
    for hr in range(9, 19):
        assert timeline[hr]["count"] == 4
        assert timeline[hr]["provenance"] == "ACTUAL"

    # 4. Explicitly release hold
    rel_res = client.post("/occupancy/hold/release?room=202")
    assert rel_res.status_code == 200
    assert rel_res.json()["released"] is True
    assert rel_res.json()["held"] is False

    # 5. Verify hold state is now released
    hold_after = client.get("/occupancy/hold-state?room=202")
    assert hold_after.status_code == 200
    assert hold_after.json()["held"] is False
