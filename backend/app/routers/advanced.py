from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional

from backend.services.thermal_rc import (
    simulate_room_thermodynamics, compare_consolidation_thermal_impact, DEFAULT_THERMAL_PROPERTIES
)
from backend.services.fdd import run_afdd_diagnostic_scan, FDD_RULE_LIBRARY
from backend.services.mandv import get_default_campus_mv_report, calculate_ashrae14_compliance
from backend.services.carbon_intensity import get_default_campus_marginal_carbon, HOURLY_MOER_PROFILE
from backend.services.ontology import build_brick_schema_graph, export_brick_turtle_summary
from backend.services.consolidation.pareto import generate_pareto_frontier

router = APIRouter(prefix="", tags=["advanced_modeling"])

# ── 1. Physics-Informed 2R2C Thermal RC Model Endpoints ──────────────────────

@router.get("/thermal-rc/room/{room_id}")
@router.get("/intelligence/thermal-rc/room/{room_id}")
def get_thermal_rc_room(
    room_id: str,
    setpoint_c: float = Query(24.0, ge=18.0, le=28.0),
    precool_hours: int = Query(0, ge=0, le=4)
) -> Dict[str, Any]:
    """
    Simulates 2R2C lumped parameter thermodynamic heat transfer:
    indoor air temp, thermal mass inertia, heat gains, and cooling power.
    """
    if room_id not in DEFAULT_THERMAL_PROPERTIES:
        raise HTTPException(status_code=404, detail=f"Room {room_id} thermal properties not found.")
        
    occupancy = [0,0,0,0,0,0,0, 10,25,35,40,35,20, 25,25,20, 10,5,0,0,0,0,0,0]
    hvac_state = [False]*7 + [True]*11 + [False]*6
    
    return simulate_room_thermodynamics(
        room_id=room_id,
        occupancy_hourly=occupancy,
        hvac_state_hourly=hvac_state,
        setpoint_c=setpoint_c,
        precool_hours=precool_hours
    )


@router.get("/thermal-rc/compare/{room_id}")
@router.get("/intelligence/thermal-rc/compare/{room_id}")
def compare_thermal_consolidation(room_id: str = "202") -> Dict[str, Any]:
    """
    Compares thermodynamic profile of active baseline vs unpowered floating room under RoomWise™.
    Verifies temperature remains safely bounded below dew point with zero condensation risk.
    """
    return compare_consolidation_thermal_impact(room_id=room_id)


# ── 2. Automated Fault Detection & Diagnostics (AFDD) ─────────────────────────

@router.get("/fdd/diagnostics")
@router.get("/intelligence/fdd/diagnostics")
def get_fdd_diagnostics() -> Dict[str, Any]:
    """
    Runs ISO 52120 / NIST APAR / ASHRAE 36 thermodynamic fault detection scan.
    Identifies active equipment faults, waste rates (kW), and financial penalties (₹/month).
    """
    return run_afdd_diagnostic_scan()


@router.get("/fdd/rules")
@router.get("/intelligence/fdd/rules")
def get_fdd_rules() -> Dict[str, Any]:
    """Returns the standardized ISO 52120 / NIST APAR rule library."""
    return {"total_rules": len(FDD_RULE_LIBRARY), "rules": FDD_RULE_LIBRARY}


# ── 3. Measurement & Verification (M&V) ASHRAE Guideline 14 ───────────────────

@router.get("/mandv/compliance")
@router.get("/intelligence/mandv/compliance")
def get_mandv_compliance() -> Dict[str, Any]:
    """
    Evaluates whole-facility energy savings against ASHRAE Guideline 14-2014 & IPMVP Option C.
    Computes R², CV(RMSE) <= 15%, NMBE <= ±5%, and fractional savings uncertainty at 90% CI.
    """
    return get_default_campus_mv_report()


# ── 4. Dynamic Marginal Operating Emission Rate (MOER) Carbon ────────────────

@router.get("/carbon/marginal-profile")
@router.get("/intelligence/carbon/marginal-profile")
def get_marginal_carbon_profile() -> Dict[str, Any]:
    """
    Returns 24-hour dynamic marginal grid carbon intensity (kg CO2 / kWh),
    quantifying additional avoided carbon emissions from peak-shaving over flat CEA models.
    """
    return get_default_campus_marginal_carbon()


# ── 5. Semantic Building Ontology (Brick Schema v1.3) ─────────────────────────

@router.get("/ontology/brick")
@router.get("/intelligence/ontology/brick")
def get_brick_schema() -> Dict[str, Any]:
    """
    Generates a Brick Schema v1.3 JSON-LD semantic graph of Block A digital twin.
    Interoperable with Autodesk Tandem, Microsoft Azure Digital Twins, and OpenBlue.
    """
    return build_brick_schema_graph()


@router.get("/ontology/turtle")
@router.get("/intelligence/ontology/turtle")
def get_brick_turtle() -> Dict[str, Any]:
    """Returns Brick Schema Turtle RDF serialization snippet."""
    return {"format": "turtle", "ttl": export_brick_turtle_summary().strip()}


# ── 6. Multi-Objective Pareto Consolidation Optimization ─────────────────────

@router.get("/consolidation/pareto")
@router.get("/intelligence/consolidation/pareto")
def get_consolidation_pareto(day: str = Query("Monday")) -> Dict[str, Any]:
    """
    Computes Pareto-optimal frontier balancing Energy Savings vs Disruption Score vs Capacity Safety.
    Presents Conservative, Balanced, and Aggressive operational regimes.
    """
    return generate_pareto_frontier(day=day)
