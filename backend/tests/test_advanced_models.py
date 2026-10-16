import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

from backend.services.thermal_rc import simulate_room_thermodynamics, compare_consolidation_thermal_impact
from backend.services.fdd import run_afdd_diagnostic_scan, FDD_RULE_LIBRARY
from backend.services.mandv import calculate_ashrae14_compliance, get_default_campus_mv_report
from backend.services.carbon_intensity import calculate_marginal_carbon_savings, get_default_campus_marginal_carbon
from backend.services.ontology import build_brick_schema_graph, export_brick_turtle_summary
from backend.services.consolidation.pareto import generate_pareto_frontier

client = TestClient(app)

def test_thermal_rc_simulation():
    """Verify 2R2C lumped parameter physics simulation yields realistic temperatures."""
    occ = [0]*7 + [25]*11 + [0]*6
    hvac = [False]*7 + [True]*11 + [False]*6
    res = simulate_room_thermodynamics("202", occ, hvac, setpoint_c=24.0)
    
    assert res["room_id"] == "202"
    assert res["total_electrical_kwh"] > 0.0
    assert 20.0 <= res["peak_indoor_temp_c"] <= 32.0
    assert len(res["hourly_simulation"]) == 24
    
    # Check that PMV and PPD are computed per ASHRAE 55
    sample_hour = res["hourly_simulation"][12]
    assert -3.0 <= sample_hour["pmv"] <= 3.0
    assert 5.0 <= sample_hour["ppd_pct"] <= 100.0


def test_thermal_rc_consolidation_compare():
    """Verify RoomWise unpowered consolidation maintains safe floating temperature."""
    cmp = compare_consolidation_thermal_impact("202")
    assert cmp["room_id"] == "202"
    assert cmp["energy_saved_kwh"] > 0.0
    assert cmp["floating_temperature_max_c"] < 35.0  # Safely bounded
    assert "ZERO" in cmp["condensation_risk"]


def test_fdd_diagnostic_scan():
    """Verify ISO 52120 / NIST APAR automated fault detection engine."""
    scan = run_afdd_diagnostic_scan()
    assert scan["status"] in ["healthy", "degraded"]
    assert "active_faults" in scan
    assert len(FDD_RULE_LIBRARY) >= 7
    assert any(f["rule_id"] == "FDD-02" for f in scan["active_faults"])


def test_mandv_ashrae14_compliance():
    """Verify ASHRAE Guideline 14 & IPMVP Option C statistical compliance."""
    report = get_default_campus_mv_report()
    metrics = report["metrics"]
    
    assert metrics["r_squared"] >= 0.75
    assert metrics["cv_rmse_pct"] <= 25.0
    assert abs(metrics["nmbe_pct"]) <= 10.0
    assert report["compliance_status"]["overall_ashrae_guideline_14_compliant"] is True
    assert report["verified_savings"]["net_savings_kwh"] > 0.0


def test_dynamic_marginal_carbon():
    """Verify dynamic marginal grid carbon (MOER) vs flat CEA factor."""
    carbon = get_default_campus_marginal_carbon()
    assert carbon["status"] == "success"
    assert carbon["marginal_carbon_saved_kg"] > 0.0
    assert carbon["cleanest_hour"] in [11, 12, 13]  # Daytime solar peak
    assert carbon["dirtiest_hour"] in [18, 19, 20]  # Evening coal peak
    assert len(carbon["hourly_marginal_profile"]) == 24


def test_brick_schema_ontology():
    """Verify Brick Schema v1.3 JSON-LD graph creation and Turtle output."""
    graph = build_brick_schema_graph()
    assert graph["graph_schema"] == "Brick Schema v1.3"
    assert graph["total_entities"] > 20
    assert "@graph" in graph
    
    ttl = export_brick_turtle_summary()
    assert "@prefix brick:" in ttl
    assert "verdant:Block_A a brick:Building" in ttl


def test_pareto_frontier_consolidation():
    """Verify multi-objective Pareto optimization across operating regimes."""
    pareto = generate_pareto_frontier(day="Monday")
    assert pareto["status"] == "success"
    frontier = pareto["pareto_frontier"]
    assert len(frontier) == 3
    
    regimes = [f["regime"] for f in frontier]
    assert "Ultra-Conservative" in regimes
    assert "Balanced (Recommended)" in regimes
    assert "Aggressive Decarbonization" in regimes


def test_advanced_endpoints():
    """Verify all new advanced API routes respond HTTP 200 via TestClient."""
    endpoints = [
        "/thermal-rc/room/202",
        "/thermal-rc/compare/202",
        "/fdd/diagnostics",
        "/fdd/rules",
        "/mandv/compliance",
        "/carbon/marginal-profile",
        "/ontology/brick",
        "/ontology/turtle",
        "/consolidation/pareto"
    ]
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with status {res.status_code}"
