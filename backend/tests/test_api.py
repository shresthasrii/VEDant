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
