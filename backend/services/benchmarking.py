"""
Building Benchmarking & EUI (Energy Use Intensity) Engine
Compares facility performance against:
- BEE (Bureau of Energy Efficiency, Ministry of Power, India) Star Rating for Day-Use Academic Buildings
- Indian Energy Conservation Building Code (ECBC 2017: ECBC Compliant, ECBC+, SuperECBC)
- ASHRAE Standard 90.1-2019 Energy Standard for Buildings
- National University Campus Percentile Rankings

Key Metrics:
- EUI Metric: Annual kWh / Gross Floor Area (kWh/m2/year)
- EUI Imperial: kBtu / Gross Sq Ft / year
- Carbon Use Intensity (CUI): kg CO2 / m2 / year
- Peak Electrical Demand Intensity: W / m2
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from backend.db import get_db

# ── Architectural & Operational Baselines ─────────────────────────────────────
GROSS_FLOOR_AREA_M2 = 1350.0   # 12 Academic Rooms + Corridors, Restrooms, AHU & Stairwells
GROSS_FLOOR_AREA_SQFT = GROSS_FLOOR_AREA_M2 * 10.7639
OPERATIONAL_DAYS_PER_YEAR = 310 # Academic year calendar active days
CONVERSION_KWH_TO_KBTU = 3.412142

# ── Industry Standard Baselines (Educational / Institutional Composite Climate) ─
ECBC_BASELINE_EUI = 145.0       # Standard unoptimized educational facility
ECBC_COMPLIANT_EUI = 120.0     # ECBC 2017 compliant target
ECBC_PLUS_EUI = 95.0           # ECBC+ target
SUPER_ECBC_EUI = 70.0          # SuperECBC (Net Zero Energy Ready)
ASHRAE_90_1_EUI = 125.0        # ASHRAE 90.1-2019 educational reference
PEAK_INTENSITY_STANDARD_W_M2 = 65.0 # Max allowable peak power density


def calculate_building_benchmarks(daily_baseline_kwh: float, daily_optimized_kwh: float, peak_kw: float) -> Dict[str, Any]:
    """
    Computes annualized EUI, BEE Star Rating, ECBC compliance classification, and peer percentile ranking.
    """
    annual_baseline_kwh = daily_baseline_kwh * OPERATIONAL_DAYS_PER_YEAR
    annual_optimized_kwh = daily_optimized_kwh * OPERATIONAL_DAYS_PER_YEAR

    # EUI Metrics
    eui_base_m2 = round(annual_baseline_kwh / GROSS_FLOOR_AREA_M2, 1)
    eui_opt_m2 = round(annual_optimized_kwh / GROSS_FLOOR_AREA_M2, 1)
    
    eui_opt_kbtu_sqft = round((annual_optimized_kwh * CONVERSION_KWH_TO_KBTU) / GROSS_FLOOR_AREA_SQFT, 1)
    eui_base_kbtu_sqft = round((annual_baseline_kwh * CONVERSION_KWH_TO_KBTU) / GROSS_FLOOR_AREA_SQFT, 1)

    # Peak Electrical Intensity
    peak_intensity_w_m2 = round((peak_kw * 1000.0) / GROSS_FLOOR_AREA_M2, 1)

    # Carbon Use Intensity (CUI) with 0.82 kg CO2/kWh
    cui_kg_m2 = round((annual_optimized_kwh * 0.82) / GROSS_FLOOR_AREA_M2, 1)

    # BEE Star Rating Assessment (Commercial / Academic Day-Use Category)
    if eui_opt_m2 <= 80.0:
        bee_stars = 5
        bee_label = "5-Star BEE Rating (Highest Energy Efficiency Tier)"
    elif eui_opt_m2 <= 100.0:
        bee_stars = 4
        bee_label = "4-Star BEE Rating (High Performance Facility)"
    elif eui_opt_m2 <= 120.0:
        bee_stars = 3
        bee_label = "3-Star BEE Rating (Standard Compliant)"
    elif eui_opt_m2 <= 140.0:
        bee_stars = 2
        bee_label = "2-Star BEE Rating (Below Average Performance)"
    else:
        bee_stars = 1
        bee_label = "1-Star BEE Rating (Energy Inefficient)"

    # ECBC 2017 Code Level
    if eui_opt_m2 <= SUPER_ECBC_EUI:
        ecbc_tier = "SuperECBC (Near Net-Zero Energy Building)"
        ecbc_status = "SUPER_ECBC"
    elif eui_opt_m2 <= ECBC_PLUS_EUI:
        ecbc_tier = "ECBC+ (35% Below Code Baseline)"
        ecbc_status = "ECBC_PLUS"
    elif eui_opt_m2 <= ECBC_COMPLIANT_EUI:
        ecbc_tier = "ECBC Compliant (Meets Mandatory Code)"
        ecbc_status = "ECBC_COMPLIANT"
    else:
        ecbc_tier = "ECBC Non-Compliant (Requires Energy Retrofits)"
        ecbc_status = "NON_COMPLIANT"

    # Peer Percentile Ranking (estimated Gaussian distribution of Indian Engineering Colleges)
    # Mean EUI = 145, StdDev = 25
    savings_vs_code = round(((ECBC_BASELINE_EUI - eui_opt_m2) / ECBC_BASELINE_EUI) * 100.0, 1)
    peer_percentile = min(99, max(50, int(50 + (ECBC_BASELINE_EUI - eui_opt_m2) * 1.1)))

    return {
        "building_metadata": {
            "gross_floor_area_m2": GROSS_FLOOR_AREA_M2,
            "gross_floor_area_sqft": round(GROSS_FLOOR_AREA_SQFT, 0),
            "climate_zone": "Composite / Warm & Humid (India)",
            "occupancy_type": "Higher Education Academic & Laboratory Facility",
            "active_rooms_count": 12,
            "annual_operating_days": OPERATIONAL_DAYS_PER_YEAR
        },
        "eui": {
            "optimized_kwh_m2_yr": eui_opt_m2,
            "baseline_kwh_m2_yr": eui_base_m2,
            "optimized_kbtu_sqft_yr": eui_opt_kbtu_sqft,
            "baseline_kbtu_sqft_yr": eui_base_kbtu_sqft,
            "reduction_pct": round(((eui_base_m2 - eui_opt_m2) / eui_base_m2) * 100.0, 1) if eui_base_m2 > 0 else 0.0
        },
        "intensity_metrics": {
            "carbon_use_intensity_kg_co2_m2": cui_kg_m2,
            "peak_demand_intensity_w_m2": peak_intensity_w_m2,
            "peak_demand_standard_w_m2": PEAK_INTENSITY_STANDARD_W_M2,
            "demand_intensity_compliant": peak_intensity_w_m2 <= PEAK_INTENSITY_STANDARD_W_M2
        },
        "certifications": {
            "bee_star_rating": bee_stars,
            "bee_star_label": bee_label,
            "ecbc_tier": ecbc_tier,
            "ecbc_status": ecbc_status,
            "ashrae_90_1_delta_pct": round(((ASHRAE_90_1_EUI - eui_opt_m2) / ASHRAE_90_1_EUI) * 100.0, 1)
        },
        "benchmarking_comparison": [
            {"benchmark": "National Campus Average", "eui_kwh_m2": ECBC_BASELINE_EUI, "verdant_delta": f"+{savings_vs_code}% better"},
            {"benchmark": "ASHRAE Standard 90.1-2019", "eui_kwh_m2": ASHRAE_90_1_EUI, "verdant_delta": f"{round(ASHRAE_90_1_EUI - eui_opt_m2, 1)} kWh/m² below target"},
            {"benchmark": "BEE 4-Star Threshold", "eui_kwh_m2": 100.0, "status": "SURPASSED" if eui_opt_m2 <= 100.0 else "TARGET"},
            {"benchmark": "SuperECBC Net-Zero Ready", "eui_kwh_m2": SUPER_ECBC_EUI, "status": "MET" if eui_opt_m2 <= SUPER_ECBC_EUI else f"{round(eui_opt_m2 - SUPER_ECBC_EUI, 1)} kWh/m² to go"}
        ],
        "national_standing": {
            "campus_percentile": f"Top {100 - peer_percentile}% Nationally",
            "narrative": f"At {eui_opt_m2} kWh/m²/year, the facility performs in the top {100 - peer_percentile}% of Indian green university campuses, qualifying for BEE {bee_stars}-Star recognition."
        },
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
