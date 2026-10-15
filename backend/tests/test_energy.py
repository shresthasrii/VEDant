import pytest
from backend.services.twin import simulate_twin_scenario

def test_energy_baseline_and_optimized():
    result = simulate_twin_scenario(hvac_end=18, lighting_end=18, setpoint_c=25.0)
    assert "baseline" in result
    assert "optimized" in result
    assert "impact" in result
    
    baseline = result["baseline"]
    optimized = result["optimized"]
    impact = result["impact"]
    
    # Baseline total should be greater than optimized when conservation measures active
    assert baseline["total_kwh"] > 0
    assert optimized["total_kwh"] > 0
    assert baseline["total_kwh"] >= optimized["total_kwh"]
    
    # Cost & Emission calculation checks
    # tariff = 8.0 INR/kWh, grid_ef = 0.7 kg CO2/kWh
    assert round(baseline["total_kwh"] * 8.0) == baseline["cost_inr"]
    assert round(baseline["total_kwh"] * 0.7, 1) == baseline["emissions_kg_co2"]
    
    # Savings checks
    assert impact["savings_kwh"] >= 0
    assert impact["p10_kwh"] <= impact["p90_kwh"]

def test_zero_missing_data_handling():
    # Room with offline sensor (e.g. 303) should not crash the simulation
    result = simulate_twin_scenario(occupancy_aware_hvac=True, occupancy_aware_lighting=True)
    assert result["optimized"]["total_kwh"] > 0
    assert "303" in result["rooms"]
