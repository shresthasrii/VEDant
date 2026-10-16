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

# Enterprise enhancements
from backend.services.solar import get_solar_profile
from backend.services.anomaly import detect_energy_anomalies, detect_occupancy_anomalies, get_anomaly_summary
from backend.services.maintenance import get_maintenance_report, score_equipment
from backend.services.forecast import get_campus_forecast, forecast_room
from backend.services.esg import calculate_campus_ghg_inventory
from backend.services.benchmarking import calculate_building_benchmarks
from backend.services.comfort import get_building_ieq_matrix, calculate_room_ieq
from backend.services.budget import calculate_energy_budget_status
from backend.services.scheduling import evaluate_smart_schedule

client = TestClient(app)

def test_tod_tariff_calculation():
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
    assert "BEE EUI Rating" in html

def test_copilot_chat():
    res = ask_copilot("Why was Technical Communication moved from Room 202 to 201?")
    assert "answer" in res
    assert "202" in res["answer"] or "201" in res["answer"]
    assert len(res["answer"]) > 20

def test_solar_pv_and_bess():
    demand = [25.0] * 24
    res = get_solar_profile(demand, cloud_factor=0.85)
    assert "system" in res
    assert res["system"]["capacity_kwp"] == 100.0
    assert res["daily"]["pv_generated_kwh"] > 100.0
    assert "self_sufficiency_pct" in res["daily"]
    assert len(res["hourly"]["pv_kwh"]) == 24

def test_anomaly_detection_engine():
    res = get_anomaly_summary()
    assert "total_anomalies" in res
    assert "health_score" in res
    assert res["health_score"] >= 0 and res["health_score"] <= 100
    assert "energy_anomalies" in res
    assert "occupancy_anomalies" in res

def test_predictive_maintenance_scoring():
    rep = get_maintenance_report()
    assert "fleet_health_score" in rep
    assert len(rep["equipment"]) == 12
    assert rep["fleet_health_score"] > 0
    single = score_equipment("202")
    assert single["room_id"] == "202"
    assert "health_score" in single
    assert "days_to_failure" in single

def test_occupancy_forecasting_holt():
    fc = get_campus_forecast()
    assert "campus_next_1h_headcount" in fc
    assert len(fc["heatmap"]) == 12
    assert "room_forecasts" in fc
    r202 = forecast_room("202")
    assert "forecast_24h" in r202
    assert len(r202["forecast_24h"]) == 24
    assert len(r202["ci_low"]) == 24

def test_esg_carbon_scope_accounting():
    grid_hourly = [30.0] * 24
    res = calculate_campus_ghg_inventory(grid_hourly, solar_generated_kwh=350.0)
    assert "scope_1" in res
    assert "scope_2" in res
    assert "scope_3" in res
    assert res["summary"]["total_daily_co2e_kg"] > 0
    assert res["summary"]["total_annual_co2e_tonnes"] > 0

def test_building_benchmarking_eui():
    res = calculate_building_benchmarks(daily_baseline_kwh=520.0, daily_optimized_kwh=430.0, peak_kw=68.0)
    assert res["eui"]["optimized_kwh_m2_yr"] > 0
    assert res["certifications"]["bee_star_rating"] in (1, 2, 3, 4, 5)
    assert "SuperECBC" in res["certifications"]["ecbc_tier"] or "ECBC" in res["certifications"]["ecbc_tier"]

def test_holistic_ieq_comfort_matrix():
    mat = get_building_ieq_matrix(hour=14)
    assert mat["building_ieq_index"] > 50.0
    assert len(mat["rooms"]) == 12
    r202 = calculate_room_ieq("202", hour=14)
    assert "composite_ieq_score" in str(r202)
    assert "sub_scores" in r202
    assert "thermal_comfort" in r202["sub_scores"]
    assert "indoor_air_quality" in r202["sub_scores"]

def test_energy_budget_tracker():
    b = calculate_energy_budget_status(current_day=16, month=10, year=2026)
    assert b["days_in_month"] == 31
    assert "mtd_actuals" in b
    assert "eom_projections" in b
    assert "variance" in b

def test_smart_scheduling_advisor():
    s = evaluate_smart_schedule()
    assert "timetable_efficiency_score" in s
    assert s["timetable_efficiency_score"] > 0
    assert "top_recommendations" in s
    assert "session_distribution" in s

def test_copilot_bidirectional_action_dispatch():
    # Test drill action dispatch
    drill_cmd = ask_copilot("trigger heatwave drill")
    assert "action_dispatched" in drill_cmd
    assert drill_cmd["action_dispatched"]["drill_type"] == "HEATWAVE"

    # Reset
    reset_cmd = ask_copilot("reset drill")
    assert "action_dispatched" in reset_cmd
    assert reset_cmd["action_dispatched"]["drill_type"] == "NORMAL"

def test_all_enterprise_api_endpoints():
    # 1. Solar
    res = client.get("/solar")
    assert res.status_code == 200
    assert "system" in res.json()

    # 2. Anomalies
    res = client.get("/anomalies")
    assert res.status_code == 200
    res_sum = client.get("/anomalies/summary")
    assert res_sum.status_code == 200

    # 3. Maintenance
    res = client.get("/maintenance")
    assert res.status_code == 200
    assert "fleet_health_score" in res.json()

    # 4. Forecast
    res = client.get("/forecast")
    assert res.status_code == 200
    assert "campus_next_1h_headcount" in res.json()

    # 5. ESG Carbon
    res = client.get("/esg-carbon")
    assert res.status_code == 200
    assert "scope_1" in res.json()

    # 6. Benchmarking
    res = client.get("/benchmarking")
    assert res.status_code == 200
    assert "eui" in res.json()

    # 7. Comfort Matrix
    res = client.get("/comfort-matrix")
    assert res.status_code == 200
    assert "building_ieq_index" in res.json()

    # 8. Budget
    res = client.get("/budget")
    assert res.status_code == 200
    assert "mtd_actuals" in res.json()

    # 9. Smart Schedule
    res = client.get("/smart-schedule")
    assert res.status_code == 200
    assert "timetable_efficiency_score" in res.json()

def test_copilot_room_telemetry_query():
    r202 = ask_copilot("Tell me about Room 202")
    assert "202" in r202["answer"]
    assert "Headcount" in r202["answer"] or "occupancy" in r202["answer"].lower()
    assert "Demand" in r202["answer"] or "kW" in r202["answer"]

    r101 = ask_copilot("Status of Room 101")
    assert "101" in r101["answer"]

def test_copilot_course_lookup_query():
    res = ask_copilot("When is course CS101?")
    assert "CS101" in res["answer"]
    assert "Instructor" in res["answer"] or "Enrolled" in res["answer"]

def test_copilot_esg_and_budget_queries():
    esg_res = ask_copilot("What are our Scope 1 and Scope 2 emissions?")
    assert "Scope 1" in esg_res["answer"]
    assert "Scope 2" in esg_res["answer"]

    bud_res = ask_copilot("Are we within budget this month?")
    assert "budget" in bud_res["answer"].lower() or "pacing" in bud_res["answer"].lower()

def test_copilot_sensor_action_dispatch():
    # Toggle fault
    res = ask_copilot("fault sensor 202")
    assert "action_dispatched" in res
    assert res["action_dispatched"]["action"] == "TOGGLE_FAULT"

    # Restore sensor
    heal = ask_copilot("repair sensor 202")
    assert "action_dispatched" in heal
    assert heal["action_dispatched"]["action"] == "RESTORE_SENSOR"

