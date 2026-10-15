import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.services.tariff import calculate_tod_energy_cost, compare_tod_scenarios
from backend.services.weather import get_microclimate_forecast
from backend.services.iaq import get_facility_iaq_overview, calculate_room_iaq
from backend.services.fleet import get_fleet_status, toggle_sensor_fault
from backend.services.sandbox import run_stress_drill, get_sandbox_status
from backend.services.reporting import generate_executive_audit_report_html
from backend.services.copilot import ask_copilot

client = TestClient(app)

def test_tod_tariff_calculation():
    # 24 hours of 50 kW flat
    flat_kw = [50.0] * 24
    res = calculate_tod_energy_cost(flat_kw)
    assert res["total_kwh"] == 1200.0
    assert "tod_breakdown" in res
    assert res["tod_breakdown"]["off_peak_cost"] > 0
    assert res["tod_breakdown"]["peak_surge_cost"] > 0
    assert res["total_bill_inr"] > 0

def test_tod_scenario_comparison():
    base = [80.0] * 24
    opt = [60.0] * 24
    comp = compare_tod_scenarios(base, opt)
    assert comp["impact"]["kwh_saved"] == 480.0
    assert comp["impact"]["total_savings_inr"] > 0
    assert comp["impact"]["co2_saved_kg"] > 0

def test_microclimate_forecast():
    w = get_microclimate_forecast()
    assert "current_temperature_c" in w
    assert len(w["hourly"]) == 24
    assert w["max_temperature_c"] >= w["min_temperature_c"]
    assert "precooling_window" in w

def test_ashrae55_and_iaq():
    room_iaq = calculate_room_iaq("202", count=25, setpoint_c=24.5)
    assert room_iaq["room_id"] == "202"
    assert room_iaq["co2_ppm"] >= 415
    assert room_iaq["thermal_comfort"]["compliant"] is True
    
    fac = get_facility_iaq_overview()
    assert fac["compliance_pct"] > 50.0
    assert len(fac["rooms"]) == 12

def test_sensor_fleet_matrix():
    fleet = get_fleet_status()
    assert fleet["fleet_size"] == 12
    assert fleet["online_count"] >= 10
    assert any(s["room_id"] == "202" and "Camera" in s["sensor_type"] for s in fleet["sensors"])

def test_stress_drill_sandbox():
    drill = run_stress_drill("HEATWAVE")
    assert drill["active"] is True
    assert drill["drill_type"] == "HEATWAVE"
    assert "ambient_temp_c" in drill["stress_metrics"]
    
    reset = run_stress_drill("RESET")
    assert reset["active"] is False
    assert reset["drill_type"] == "NORMAL"

def test_executive_report_html_generation():
    html = generate_executive_audit_report_html()
    assert "<html" in html
    assert "Executive Energy Audit & ESG Report" in html
    assert "RoomWise" in html
    assert "Director of Facilities" in html

def test_copilot_chat():
    res = ask_copilot("Why was Technical Communication moved from Room 202 to 201?")
    assert "answer" in res
    assert "202" in res["answer"] or "201" in res["answer"]
    assert len(res["answer"]) > 20

def test_intelligence_api_endpoints():
    # 1. GET /tariff
    res = client.get("/tariff")
    assert res.status_code == 200
    assert "baseline" in res.json()

    # 2. GET /weather
    res = client.get("/weather")
    assert res.status_code == 200
    assert "current_temperature_c" in res.json()

    # 3. GET /iaq
    res = client.get("/iaq")
    assert res.status_code == 200
    assert "rooms" in res.json()

    # 4. GET /fleet
    res = client.get("/fleet")
    assert res.status_code == 200
    assert res.json()["fleet_size"] == 12

    # 5. POST /copilot/chat
    res = client.post("/copilot/chat", json={"query": "What is the peak tariff rate?"})
    assert res.status_code == 200
    assert "answer" in res.json()

    # 6. GET /export/audit-report
    res = client.get("/export/audit-report")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
