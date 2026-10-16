from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from backend.services.tariff import (
    load_factors, calculate_tod_energy_cost, compare_tod_scenarios
)
from backend.services.weather import get_microclimate_forecast
from backend.services.iaq import get_facility_iaq_overview, calculate_room_iaq
from backend.services.fleet import get_fleet_status, toggle_sensor_fault
from backend.services.sandbox import get_sandbox_status, run_stress_drill
from backend.services.copilot import ask_copilot
from backend.services.twin import simulate_twin_scenario

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

router = APIRouter(prefix="", tags=["intelligence"])

class CopilotChatRequest(BaseModel):
    query: Optional[str] = None
    prompt: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None

class DrillRequest(BaseModel):
    drill_type: str # 'HEATWAVE', 'GRID_CURTAILMENT', 'EXAM_SURGE', 'RESET'

# ── Baseline Intelligence Endpoints ──────────────────────────────────────────

@router.get("/tariff")
@router.get("/intelligence/tariff")
def get_tariff_analysis() -> Dict[str, Any]:
    """Returns Time-of-Day (ToD) tariff structure, rate slabs, and scenario comparisons."""
    sim = simulate_twin_scenario()
    base_h = sim["baseline"]["hourly_kw"]
    opt_h = sim["optimized"]["hourly_kw"]
    return compare_tod_scenarios(base_h, opt_h)

@router.get("/weather")
@router.get("/intelligence/weather")
def get_weather() -> Dict[str, Any]:
    """Returns campus microclimate forecast, ambient temperature curve, and thermal mass pre-cooling advisory."""
    return get_microclimate_forecast()

@router.get("/iaq")
@router.get("/intelligence/iaq")
def get_iaq(hour: int = Query(15)) -> Dict[str, Any]:
    """Returns ASHRAE 55 thermal comfort PMV/PPD metrics and room CO2 concentrations."""
    return get_facility_iaq_overview(hour=hour)

@router.get("/iaq/{room_id}")
@router.get("/intelligence/iaq/{room_id}")
def get_room_iaq(room_id: str, count: int = Query(25), setpoint_c: float = Query(25.0)) -> Dict[str, Any]:
    """Calculates specific room IAQ, CO2 ppm, and ASHRAE 55 compliance."""
    result = calculate_room_iaq(room_id, count, setpoint_c=setpoint_c)
    if not result:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
    return result

@router.get("/fleet")
@router.get("/intelligence/fleet")
def get_fleet() -> Dict[str, Any]:
    """Returns health, protocol, latency, and packet loss diagnostics for all 12 building sensors."""
    return get_fleet_status()

@router.post("/fleet/{room_id}/toggle-fault")
@router.post("/intelligence/fleet/{room_id}/toggle-fault")
def toggle_fleet_sensor(room_id: str) -> Dict[str, Any]:
    """Toggles sensor fault status to test automated timetable fallback."""
    try:
        return toggle_sensor_fault(room_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/sandbox")
@router.get("/intelligence/sandbox")
def get_sandbox() -> Dict[str, Any]:
    """Returns current active stress-test drill and boundary metrics."""
    return get_sandbox_status()

ALLOWED_DRILLS = {"HEATWAVE", "GRID_CURTAILMENT", "EXAM_SURGE", "RESET"}

@router.post("/sandbox/drill")
@router.post("/intelligence/sandbox/drill")
def execute_drill(req: DrillRequest) -> Dict[str, Any]:
    """Executes a campus stress-test drill (HEATWAVE, GRID_CURTAILMENT, EXAM_SURGE, RESET)."""
    dtype = (req.drill_type or "").strip().upper()
    if dtype not in ALLOWED_DRILLS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid drill_type '{req.drill_type}'. Allowed types: {sorted(list(ALLOWED_DRILLS))}"
        )
    return run_stress_drill(dtype)

@router.post("/copilot/chat")
@router.post("/intelligence/copilot/chat")
def chat_with_copilot(req: CopilotChatRequest) -> Dict[str, Any]:
    """Interactive natural language assistant for facility directors powered by local GPU Ollama & Bidirectional NLP Dispatch."""
    q = (req.query or req.prompt or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return ask_copilot(q, history=req.history)


# ── New Enterprise Intelligence Endpoints ─────────────────────────────────────

@router.get("/solar")
@router.get("/intelligence/solar")
def get_solar_status(cloud_factor: float = Query(0.85)) -> Dict[str, Any]:
    """Returns rooftop solar PV generation, 50 kWh BESS dispatch, and net-metering financials."""
    sim = simulate_twin_scenario()
    opt_hourly = sim["optimized"]["hourly_kw"]
    return get_solar_profile(opt_hourly, cloud_factor=cloud_factor)

@router.get("/anomalies")
@router.get("/intelligence/anomalies")
def get_anomalies() -> Dict[str, Any]:
    """Detects energy spikes (Z-score > 2.5σ), IQR fence breaches, and ghost occupancy."""
    return {
        "energy": detect_energy_anomalies(),
        "occupancy": detect_occupancy_anomalies()
    }

@router.get("/anomalies/summary")
@router.get("/intelligence/anomalies/summary")
def get_anomalies_summary_route() -> Dict[str, Any]:
    """Provides high-level health score and anomaly counts for dashboard radar."""
    return get_anomaly_summary()

@router.get("/maintenance")
@router.get("/intelligence/maintenance")
def get_maintenance() -> Dict[str, Any]:
    """Returns predictive maintenance degradation scores and days-to-failure for all 12 zones."""
    return get_maintenance_report()

@router.get("/maintenance/{room_id}")
@router.get("/intelligence/maintenance/{room_id}")
def get_room_maintenance(room_id: str) -> Dict[str, Any]:
    """Returns specific room equipment degradation and recommended maintenance action."""
    return score_equipment(room_id)

@router.get("/forecast")
@router.get("/intelligence/forecast")
def get_forecast() -> Dict[str, Any]:
    """Campus-wide next-hour and 24-hour occupancy forecast via Holt's exponential smoothing."""
    return get_campus_forecast()

@router.get("/forecast/{room_id}")
@router.get("/intelligence/forecast/{room_id}")
def get_room_forecast(room_id: str) -> Dict[str, Any]:
    """Room-level 24-hour occupancy forecast with 85% confidence interval bands."""
    res = forecast_room(room_id)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res

@router.get("/esg-carbon")
@router.get("/intelligence/esg-carbon")
def get_esg_carbon() -> Dict[str, Any]:
    """GHG Protocol Scope 1, Scope 2 (market/location-based), and Scope 3 carbon audit."""
    sim = simulate_twin_scenario()
    opt_hourly = sim["optimized"]["hourly_kw"]
    solar_data = get_solar_profile(opt_hourly)
    solar_kwh = solar_data["daily"]["pv_generated_kwh"]
    return calculate_campus_ghg_inventory(opt_hourly, solar_generated_kwh=solar_kwh)

@router.get("/benchmarking")
@router.get("/intelligence/benchmarking")
def get_benchmarks() -> Dict[str, Any]:
    """Computes Energy Use Intensity (EUI), BEE 5-Star rating, and ECBC 2017 classification."""
    sim = simulate_twin_scenario()
    base_kwh = sim["baseline"]["total_kwh"]
    opt_kwh = sim["optimized"]["total_kwh"]
    peak_kw = sim["optimized"]["peak_kw"]
    return calculate_building_benchmarks(base_kwh, opt_kwh, peak_kw)

@router.get("/comfort-matrix")
@router.get("/intelligence/comfort-matrix")
def get_comfort_matrix(hour: int = Query(14)) -> Dict[str, Any]:
    """Unified 0-100 Indoor Environmental Quality (IEQ) combining thermal, CO2, lux, and acoustic scores."""
    return get_building_ieq_matrix(hour=hour)

@router.get("/budget")
@router.get("/intelligence/budget")
def get_energy_budget(day: int = Query(16), month: int = Query(10), year: int = Query(2026)) -> Dict[str, Any]:
    """Monthly utility budget allocation, MTD actual spend, and EOM burn-rate projection."""
    return calculate_energy_budget_status(current_day=day, month=month, year=year)

@router.get("/smart-schedule")
@router.get("/intelligence/smart-schedule")
def get_smart_schedule() -> Dict[str, Any]:
    """Evaluates class timetable against ToD tariff slabs and suggests moves to reduce peak power bills."""
    return evaluate_smart_schedule()
