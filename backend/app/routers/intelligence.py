from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional

from backend.services.tariff import (
    load_factors, calculate_tod_energy_cost, compare_tod_scenarios
)
from backend.services.weather import get_microclimate_forecast
from backend.services.iaq import get_facility_iaq_overview, calculate_room_iaq
from backend.services.fleet import get_fleet_status, toggle_sensor_fault
from backend.services.sandbox import get_sandbox_status, run_stress_drill
from backend.services.copilot import ask_copilot
from backend.services.twin import simulate_twin_scenario

router = APIRouter(prefix="", tags=["intelligence"])

class CopilotChatRequest(BaseModel):
    query: Optional[str] = None
    prompt: Optional[str] = None

class DrillRequest(BaseModel):
    drill_type: str # 'HEATWAVE', 'GRID_CURTAILMENT', 'EXAM_SURGE', 'RESET'

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

@router.post("/sandbox/drill")
@router.post("/intelligence/sandbox/drill")
def execute_drill(req: DrillRequest) -> Dict[str, Any]:
    """Executes a campus stress-test drill (HEATWAVE, GRID_CURTAILMENT, EXAM_SURGE, RESET)."""
    return run_stress_drill(req.drill_type)

@router.post("/copilot/chat")
@router.post("/intelligence/copilot/chat")
def chat_with_copilot(req: CopilotChatRequest) -> Dict[str, Any]:
    """Interactive natural language assistant for facility directors powered by local GPU Ollama."""
    q = (req.query or req.prompt or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return ask_copilot(q)
