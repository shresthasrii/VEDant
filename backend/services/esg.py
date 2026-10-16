"""
ESG Carbon Scope 1, 2, and 3 Accounting Service
In compliance with GHG Protocol Corporate Standard & ISO 14064.

Scope Breakdown:
- Scope 1 (Direct Emissions):
    * Emergency Diesel Generator (DG) testing & standby consumption (diesel fuel factor: 2.68 kg CO2/L)
    * HVAC fugitive refrigerant loss (R-410A GWP 2088, R-32 GWP 675, annualized 2.5% loss rate)
- Scope 2 (Indirect Emissions - Electricity):
    * Location-based method: Central Electricity Authority (CEA 2023) grid emission factor (0.82 kg CO2/kWh)
    * Market-based method: Credits on-site Rooftop Solar PV generation and green energy tariffs
- Scope 3 (Value Chain Indirect Emissions):
    * Category 7 (Student & Faculty Commuting): Estimated from daily headcount, modal split (bus, EV, two-wheeler)
    * Category 5 (Waste generated in operations): 0.18 kg waste/person/day * 0.45 kg CO2/kg landfill factor
    * Water supply pumping & municipal treatment: 0.38 kWh/m3 equivalent
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from backend.db import get_db

# ── Emission Factors (CEA, IPCC AR6, GHG Protocol) ───────────────────────────
GRID_EF_KG_CO2_PER_KWH = 0.82       # CEA India Baseline Database v19
DIESEL_KG_CO2_PER_LITER = 2.68      # IPCC default for mobile/stationary diesel
REFRIGERANT_LEAK_KG_CO2_ANNUAL = 380.0 # ~0.18 kg R-410A fugitive loss across split/VRF units
WASTE_KG_PER_STUDENT_DAY = 0.18     # UNEP campus benchmark
WASTE_EMISSION_FACTOR = 0.45        # kg CO2e per kg organic/mixed landfill waste
COMMUTE_KG_CO2_PER_PERSON_DAY = 0.85 # Average Indian urban campus hybrid transit footprint
WATER_CONSUMPTION_L_PER_STUDENT = 25.0 # Liters/student/day
WATER_PUMPING_KWH_PER_M3 = 0.42     # Energy intensity of campus booster & borehole pumps


def calculate_campus_ghg_inventory(hourly_kwh_grid: List[float], solar_generated_kwh: float = 0.0) -> Dict[str, Any]:
    """
    Computes annualized and daily GHG Protocol carbon footprint across Scopes 1, 2, and 3.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(capacity) as total_cap FROM rooms")
        total_capacity = cursor.fetchone()["total_cap"] or 360
        
        cursor.execute("SELECT AVG(count) as avg_occ FROM occupancy_readings WHERE source = 'simulated'")
        row = cursor.fetchone()
        avg_headcount = row["avg_occ"] if row and row["avg_occ"] else total_capacity * 0.45

    # 1. SCOPE 1 (Direct)
    # 2 hours/month DG running for maintenance testing @ 12 L/hour = 288 L/yr -> ~0.8 L/day
    dg_fuel_liters_daily = 0.80
    dg_emissions_daily = dg_fuel_liters_daily * DIESEL_KG_CO2_PER_LITER
    refrigerant_daily = REFRIGERANT_LEAK_KG_CO2_ANNUAL / 365.0
    scope_1_daily_kg = round(dg_emissions_daily + refrigerant_daily, 2)
    scope_1_annual_tonnes = round((scope_1_daily_kg * 365.0) / 1000.0, 2)

    # 2. SCOPE 2 (Purchased Electricity)
    daily_grid_kwh = sum(hourly_kwh_grid)
    # Location-based: all grid intake
    scope_2_location_daily_kg = round(daily_grid_kwh * GRID_EF_KG_CO2_PER_KWH, 2)
    # Market-based: net grid after subtracting renewable self-consumption
    net_grid_kwh = max(0.0, daily_grid_kwh - solar_generated_kwh)
    scope_2_market_daily_kg = round(net_grid_kwh * GRID_EF_KG_CO2_PER_KWH, 2)
    scope_2_annual_tonnes = round((scope_2_market_daily_kg * 365.0) / 1000.0, 2)

    # 3. SCOPE 3 (Value Chain)
    commute_daily_kg = round(avg_headcount * COMMUTE_KG_CO2_PER_PERSON_DAY, 2)
    waste_daily_kg = round(avg_headcount * WASTE_KG_PER_STUDENT_DAY * WASTE_EMISSION_FACTOR, 2)
    water_m3_daily = (avg_headcount * WATER_CONSUMPTION_L_PER_STUDENT) / 1000.0
    water_pumping_co2_kg = round(water_m3_daily * WATER_PUMPING_KWH_PER_M3 * GRID_EF_KG_CO2_PER_KWH, 2)
    
    scope_3_daily_kg = round(commute_daily_kg + waste_daily_kg + water_pumping_co2_kg, 2)
    scope_3_annual_tonnes = round((scope_3_daily_kg * 365.0) / 1000.0, 2)

    total_daily_kg = round(scope_1_daily_kg + scope_2_market_daily_kg + scope_3_daily_kg, 2)
    total_annual_tonnes = round(scope_1_annual_tonnes + scope_2_annual_tonnes + scope_3_annual_tonnes, 2)

    # Net Zero Progress & Benchmark Trajectory (2026 Target: 15% reduction, 2030 Net-Zero Target)
    baseline_2024_annual_tonnes = 420.0
    reduction_pct = round(((baseline_2024_annual_tonnes - total_annual_tonnes) / baseline_2024_annual_tonnes) * 100.0, 1)

    return {
        "standard": "GHG Protocol Corporate Standard (ISO 14064-1)",
        "reporting_period": "Daily & Annualized Run-Rate",
        "summary": {
            "total_daily_co2e_kg": total_daily_kg,
            "total_annual_co2e_tonnes": total_annual_tonnes,
            "net_zero_progress_pct": max(0.0, reduction_pct),
            "carbon_intensity_kg_per_student_day": round(total_daily_kg / max(1.0, avg_headcount), 2)
        },
        "scope_1": {
            "title": "Scope 1 (Direct Campus Emissions)",
            "daily_kg_co2e": scope_1_daily_kg,
            "annual_tonnes_co2e": scope_1_annual_tonnes,
            "breakdown": {
                "diesel_generators_kg": round(dg_emissions_daily, 2),
                "fugitive_refrigerants_kg": round(refrigerant_daily, 2)
            },
            "audit_note": "Includes standby diesel generator testing and VRF/split AC refrigerant fugitive loss."
        },
        "scope_2": {
            "title": "Scope 2 (Indirect Purchased Electricity)",
            "daily_kg_co2e": scope_2_market_daily_kg,
            "location_based_daily_kg": scope_2_location_daily_kg,
            "market_based_daily_kg": scope_2_market_daily_kg,
            "solar_offset_daily_kg": round(solar_generated_kwh * GRID_EF_KG_CO2_PER_KWH, 2),
            "annual_tonnes_co2e": scope_2_annual_tonnes,
            "grid_emission_factor_kg_per_kwh": GRID_EF_KG_CO2_PER_KWH,
            "audit_note": "Calculated via Central Electricity Authority (CEA v19) regional grid emission factor."
        },
        "scope_3": {
            "title": "Scope 3 (Campus Value Chain Indirect)",
            "daily_kg_co2e": scope_3_daily_kg,
            "annual_tonnes_co2e": scope_3_annual_tonnes,
            "breakdown": {
                "student_faculty_commuting_kg": commute_daily_kg,
                "solid_waste_landfill_kg": waste_daily_kg,
                "water_supply_pumping_kg": water_pumping_co2_kg
            },
            "audit_note": "Estimated using daily campus occupancy, urban transit modal distribution, and water/waste factors."
        },
        "decarbonization_milestones": [
            {"year": 2024, "target_tonnes": 420.0, "status": "BASELINE COMPLETED"},
            {"year": 2026, "target_tonnes": 330.0, "current_runrate": total_annual_tonnes, "status": "ON TRACK" if total_annual_tonnes <= 340.0 else "NEEDS ACCELERATION"},
            {"year": 2028, "target_tonnes": 210.0, "status": "PLANNED (SOLAR EXPANSION)"},
            {"year": 2030, "target_tonnes": 0.0, "status": "NET-ZERO ACADEMIC CAMPUS"}
        ],
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
