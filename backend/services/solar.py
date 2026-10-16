"""
Solar PV + Net-Energy Metering Module
Compares to: Johnson Controls OpenBlue, Schneider EcoStruxure

Models rooftop solar photovoltaic production for the campus building:
- Hourly GHI-based PV output (W/m²  → kWh)
- Net metering: export credit when production > demand
- Battery storage (BESS) dispatch optimization
- Carbon avoided calculation

Parameters based on a typical 100 kWp rooftop installation (IEC 61724).
"""
import math
from datetime import datetime, timezone
from typing import Dict, Any, List

# ── PV System Parameters ──────────────────────────────────────────────────────
PV_CAPACITY_KWP     = 100.0   # installed capacity (kWp)
PANEL_EFFICIENCY    = 0.185   # 18.5% (monocrystalline)
SYSTEM_LOSSES       = 0.20    # wiring + inverter + soiling + shading
BESS_CAPACITY_KWH   = 50.0    # battery storage
BESS_EFFICIENCY     = 0.92    # round-trip
EXPORT_TARIFF_INR   = 3.50    # ₹ per kWh exported (net metering)
IMPORT_TARIFF_INR   = 8.00    # ₹ per kWh imported (peak)
GRID_EF_KG_CO2      = 0.82    # kg CO₂ per kWh (CEA 2023)

# Hourly GHI profile (W/m²) — Hyderabad annual average clear-sky day
# 0–5: dark, 6-7: dawn, 8-16: peak, 17-18: dusk, 19+: dark
_GHI_PROFILE = [
    0, 0, 0, 0, 0, 0,            # 00-05
    45, 150,                      # 06-07
    320, 520, 680, 800, 850,      # 08-12
    840, 780, 680, 540, 350,      # 13-17
    160, 40, 0, 0, 0, 0           # 18-23
]

assert len(_GHI_PROFILE) == 24, "GHI profile must have 24 values"


def _pv_output_kwh(hour: int, cloud_factor: float = 1.0) -> float:
    """kWh produced in hour `h` by the PV system."""
    ghi = _GHI_PROFILE[hour] * cloud_factor
    # PV power (kW) = GHI * area * efficiency * (1-losses)
    # area derived from capacity: area = kWp / (1000 W/m² * eta)
    area_m2 = PV_CAPACITY_KWP * 1000 / (1000 * PANEL_EFFICIENCY)
    kw = (ghi * area_m2 * PANEL_EFFICIENCY * (1.0 - SYSTEM_LOSSES)) / 1000.0
    return max(0.0, kw)  # kWh = kW × 1h


def get_solar_profile(demand_kwh_per_hour: List[float], cloud_factor: float = 0.85) -> Dict[str, Any]:
    """
    Given hourly building demand, calculate:
    - PV production
    - Net demand (demand - PV)
    - BESS dispatch
    - Export credits
    """
    pv = [_pv_output_kwh(h, cloud_factor) for h in range(24)]

    net_demand  = []
    bess_state  = 0.0   # kWh stored
    bess_charge = []
    bess_discharge = []
    export_kwh  = []
    grid_import = []

    for h in range(24):
        demand = demand_kwh_per_hour[h] if h < len(demand_kwh_per_hour) else 0.0
        surplus = pv[h] - demand

        if surplus > 0:
            # Charge BESS first, then export
            charge_room = min(surplus, BESS_CAPACITY_KWH - bess_state)
            bess_state += charge_room * BESS_EFFICIENCY
            exported = surplus - charge_room
            bess_charge.append(round(charge_room, 2))
            bess_discharge.append(0.0)
            export_kwh.append(round(exported, 2))
            grid_import.append(0.0)
            net_demand.append(round(-exported, 2))  # negative = exporting
        else:
            # Discharge BESS, then import from grid
            shortfall = -surplus
            discharge = min(shortfall, bess_state * BESS_EFFICIENCY)
            bess_state -= discharge / BESS_EFFICIENCY
            from_grid = shortfall - discharge
            bess_charge.append(0.0)
            bess_discharge.append(round(discharge, 2))
            export_kwh.append(0.0)
            grid_import.append(round(from_grid, 2))
            net_demand.append(round(from_grid, 2))

    total_pv        = round(sum(pv), 1)
    total_export    = round(sum(export_kwh), 1)
    total_import    = round(sum(grid_import), 1)
    total_demand    = round(sum(demand_kwh_per_hour), 1)
    self_sufficiency = round((total_demand - total_import) / total_demand * 100, 1) if total_demand else 0.0
    co2_avoided     = round(total_pv * GRID_EF_KG_CO2, 1)
    export_revenue  = round(total_export * EXPORT_TARIFF_INR, 0)
    import_cost     = round(total_import * IMPORT_TARIFF_INR, 0)
    net_bill        = round(import_cost - export_revenue, 0)

    return {
        "system": {
            "capacity_kwp":     PV_CAPACITY_KWP,
            "bess_capacity_kwh": BESS_CAPACITY_KWH,
            "panel_efficiency": PANEL_EFFICIENCY,
            "cloud_factor":     cloud_factor
        },
        "hourly": {
            "pv_kwh":        [round(v, 2) for v in pv],
            "demand_kwh":    [round(v, 2) for v in demand_kwh_per_hour],
            "net_demand":    [round(v, 2) for v in net_demand],
            "grid_import":   grid_import,
            "export_kwh":    export_kwh,
            "bess_charge":   bess_charge,
            "bess_discharge": bess_discharge
        },
        "daily": {
            "pv_generated_kwh":     total_pv,
            "grid_import_kwh":      total_import,
            "export_kwh":           total_export,
            "self_sufficiency_pct": self_sufficiency,
            "co2_avoided_kg":       co2_avoided,
            "export_revenue_inr":   int(export_revenue),
            "grid_import_cost_inr": int(import_cost),
            "net_energy_bill_inr":  int(net_bill),
            "solar_fraction_pct":   round(total_pv / (total_pv + total_import) * 100, 1) if (total_pv + total_import) > 0 else 0.0
        },
        "equivalences": {
            "trees_equivalent":     round(co2_avoided / 21.8, 1),
            "cars_off_road_days":   round(co2_avoided / 4.6, 1)
        },
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
