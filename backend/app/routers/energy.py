from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from backend.services.twin import simulate_twin_scenario
from backend.db import get_db

router = APIRouter(prefix="", tags=["energy"])

class SimulateRequest(BaseModel):
    hvac_end: int = 18
    lighting_end: int = 18
    setpoint_c: float = 25.0
    peak_target_kw: float = 99.0
    occupancy_aware_hvac: bool = False
    occupancy_aware_lighting: bool = False
    selected_rooms: Optional[List[str]] = None

@router.get("/energy")
def get_energy(
    floor: Optional[int] = Query(0),
    room_id: Optional[str] = Query(None, alias="room"),
    system: Optional[str] = Query("all"), # 'all', 'hvac', 'lighting', 'plug'
    scenario: Optional[str] = Query("baseline") # 'baseline', 'optimized'
) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT e.*, r.name as room_name, r.floor FROM energy_readings e JOIN rooms r ON e.room_id = r.id WHERE e.scenario = ?"
        params = [scenario]
        
        if floor and floor > 0:
            query += " AND r.floor = ?"
            params.append(floor)
        if room_id:
            query += " AND r.id = ?"
            params.append(room_id)
            
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        
        # Aggregate by hour
        hourly_totals = [0.0] * 24
        for r in rows:
            h = r["hour"]
            if system == "hvac":
                hourly_totals[h] += r["hvac_kw"]
            elif system == "lighting":
                hourly_totals[h] += r["lighting_kw"]
            elif system == "plug":
                hourly_totals[h] += r["plug_kw"]
            else:
                hourly_totals[h] += r["total_kw"]
                
        total_kwh = sum(hourly_totals)
        return {
            "scenario": scenario,
            "floor": floor,
            "room_id": room_id,
            "system": system,
            "hourly_kw": [round(x, 2) for x in hourly_totals],
            "total_kwh": round(total_kwh, 1),
            "peak_kw": round(max(hourly_totals) if hourly_totals else 0.0, 1),
            "cost_inr": round(total_kwh * 8.0),
            "emissions_kg_co2": round(total_kwh * 0.7, 1),
            "provenance": "ESTIMATED"
        }

@router.post("/simulate")
def run_simulation(req: SimulateRequest) -> Dict[str, Any]:
    sim_result = simulate_twin_scenario(
        hvac_end=req.hvac_end,
        lighting_end=req.lighting_end,
        setpoint_c=req.setpoint_c,
        peak_target_kw=req.peak_target_kw,
        occupancy_aware_hvac=req.occupancy_aware_hvac,
        occupancy_aware_lighting=req.occupancy_aware_lighting,
        selected_rooms=req.selected_rooms
    )
    return sim_result
