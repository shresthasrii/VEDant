import json
import time
import random
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path
from backend.db import get_db

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# ── 30-second TTL simulation cache ───────────────────────────────────────────
_sim_cache: Dict[str, Any] = {}
_SIM_TTL = 30.0  # seconds

def _cache_key(**kwargs) -> str:
    return hashlib.md5(json.dumps(kwargs, sort_keys=True, default=str).encode()).hexdigest()


def get_factors() -> Dict[str, Any]:
    with open(CONFIG_DIR / "factors.json", "r", encoding="utf-8") as f:
        return json.load(f)

def simulate_twin_scenario(
    hvac_end: int = 18,
    lighting_end: int = 18,
    setpoint_c: float = 25.0,
    peak_target_kw: float = 99.0,
    occupancy_aware_hvac: bool = False,
    occupancy_aware_lighting: bool = False,
    selected_rooms: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Digital twin simulation of building energy demand across 24 hours.
    Calculates hourly HVAC, Lighting, and Plug load demand per room.
    Results are cached for 30 seconds keyed on input parameters.
    """
    # ── Check TTL cache first ─────────────────────────────────────────────────
    ck = _cache_key(
        hvac_end=hvac_end, lighting_end=lighting_end, setpoint_c=setpoint_c,
        peak_target_kw=peak_target_kw, occupancy_aware_hvac=occupancy_aware_hvac,
        occupancy_aware_lighting=occupancy_aware_lighting,
        selected_rooms=sorted(selected_rooms) if selected_rooms else None
    )
    now = time.monotonic()
    cached = _sim_cache.get(ck)
    if cached and (now - cached["_ts"]) < _SIM_TTL:
        return cached["data"]

    factors = get_factors()
    tariff = factors["tariff_inr_per_kwh"]
    grid_ef = factors["grid_emission_factor_kg_co2_per_kwh"]
    sp_sens = factors["hvac_sensitivity_per_deg_c"]
    vent_floor = factors["hvac_min_ventilation_floor"]

    with get_db() as conn:

        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms")
        rooms = [dict(r) for r in cursor.fetchall()]
        
        # Hourly occupancy for all rooms
        cursor.execute("SELECT room_id, hour, count FROM occupancy_readings WHERE source = 'simulated' ORDER BY hour")
        occ_rows = cursor.fetchall()
        
    occ_map: Dict[str, Dict[int, Optional[int]]] = {r["id"]: {} for r in rooms}
    for row in occ_rows:
        occ_map[row["room_id"]][row["hour"]] = row["count"]
        
    # Baseline simulation
    # Base params: hvac_end=19, lighting_end=19, setpoint=24, peak=99
    hourly_base: List[float] = [0.0] * 24
    hourly_opt: List[float] = [0.0] * 24
    
    hvac_base: List[float] = [0.0] * 24
    light_base: List[float] = [0.0] * 24
    plug_base: List[float] = [0.0] * 24
    
    hvac_opt: List[float] = [0.0] * 24
    light_opt: List[float] = [0.0] * 24
    plug_opt: List[float] = [0.0] * 24
    
    room_details: Dict[str, Dict[str, Any]] = {}
    
    for r in rooms:
        rid = r["id"]
        cap = r["capacity"]
        rh = r["hvac_kw"]
        rl = r["lighting_kw"]
        rp = r["plug_kw"]
        
        r_hvac_base = []
        r_light_base = []
        r_plug_base = []
        
        r_hvac_opt = []
        r_light_opt = []
        r_plug_opt = []
        
        is_selected = (not selected_rooms) or (rid in selected_rooms)
        
        for h in range(24):
            c = occ_map[rid].get(h)
            u = 0.5 if c is None else (c / cap)
            
            # --- BASELINE ---
            iH_base = (7 <= h < 19)
            iL_base = (7 <= h < 19)
            
            hv_b = (rh * (0.85 + 0.15 * u)) if iH_base else (rh * 0.10)
            lt_b = rl if iL_base else (rl * 0.05)
            pl_b = rp * (0.25 + 0.75 * u if (7 <= h < 19) else 0.20)
            
            r_hvac_base.append(hv_b)
            r_light_base.append(lt_b)
            r_plug_base.append(pl_b)
            
            hourly_base[h] += (hv_b + lt_b + pl_b)
            hvac_base[h] += hv_b
            light_base[h] += lt_b
            plug_base[h] += pl_b
            
            # --- OPTIMIZED ---
            iH_opt = (7 <= h < hvac_end)
            iL_opt = (7 <= h < lighting_end)
            
            hv_o = (rh * (0.85 + 0.15 * u)) if iH_opt else (rh * 0.10)
            lt_o = rl if iL_opt else (rl * 0.05)
            
            if is_selected and iH_opt and occupancy_aware_hvac and (c is not None):
                # Demand control scaling down to ventilation floor (35%)
                hv_o = rh * (vent_floor + (1.0 - vent_floor) * min(1.0, u * 1.5))
                
            if is_selected and iL_opt and occupancy_aware_lighting and (c is not None):
                lt_o = rl * (0.10 if c == 0 else (0.40 if u < 0.15 else 1.0))
                
            # Setpoint effect: approx 6% per degree C
            hv_o = hv_o * (1.0 - sp_sens * (setpoint_c - 24.0))
            pl_o = pl_b # plug loads unchanged
            
            r_hvac_opt.append(hv_o)
            r_light_opt.append(lt_o)
            r_plug_opt.append(pl_o)
            
            hourly_opt[h] += (hv_o + lt_o + pl_o)
            hvac_opt[h] += hv_o
            light_opt[h] += lt_o
            plug_opt[h] += pl_o
            
        room_details[rid] = {
            "name": r["name"],
            "floor": r["floor"],
            "capacity": cap,
            "baseline": {"hvac": r_hvac_base, "lighting": r_light_base, "plug": r_plug_base},
            "optimized": {"hvac": r_hvac_opt, "lighting": r_light_opt, "plug": r_plug_opt}
        }
        
    # Peak target shaving
    for h in range(24):
        if hourly_opt[h] > peak_target_kw:
            excess = hourly_opt[h] - peak_target_kw
            hvac_total = hvac_opt[h]
            if hvac_total > 0:
                k = max(0.70, 1.0 - excess / hvac_total)
                diff = hvac_opt[h] * (1.0 - k)
                hvac_opt[h] *= k
                hourly_opt[h] -= diff
                
    total_base_kwh = sum(hourly_base)
    total_opt_kwh = sum(hourly_opt)
    r_total_base = round(total_base_kwh, 1)
    r_total_opt = round(total_opt_kwh, 1)
    r_savings = max(0.0, round(r_total_base - r_total_opt, 1))
    savings_pct = (r_savings / r_total_base * 100.0) if r_total_base > 0 else 0.0
    
    # Monte Carlo uncertainty ranges
    mc_savings = [
        max(0.0, (total_base_kwh * random.uniform(0.92, 1.08)) - (total_opt_kwh * random.uniform(0.92, 1.08)))
        for _ in range(50)
    ]
    mc_savings.sort()
    p10 = mc_savings[5]
    p90 = mc_savings[44]
    
    result = {
        "baseline": {
            "total_kwh": r_total_base,
            "peak_kw": round(max(hourly_base), 1),
            "cost_inr": round(r_total_base * tariff),
            "emissions_kg_co2": round(r_total_base * grid_ef, 1),
            "hourly_kw": [round(x, 2) for x in hourly_base],
            "by_system": {
                "hvac_kwh": round(sum(hvac_base), 1),
                "lighting_kwh": round(sum(light_base), 1),
                "plug_kwh": round(sum(plug_base), 1)
            }
        },
        "optimized": {
            "total_kwh": r_total_opt,
            "peak_kw": round(max(hourly_opt), 1),
            "cost_inr": round(r_total_opt * tariff),
            "emissions_kg_co2": round(r_total_opt * grid_ef, 1),
            "hourly_kw": [round(x, 2) for x in hourly_opt],
            "by_system": {
                "hvac_kwh": round(sum(hvac_opt), 1),
                "lighting_kwh": round(sum(light_opt), 1),
                "plug_kwh": round(sum(plug_opt), 1)
            }
        },
        "impact": {
            "savings_kwh": r_savings,
            "savings_pct": round(savings_pct, 1),
            "cost_saved_inr": round(r_savings * tariff),
            "co2_saved_kg": round(r_savings * grid_ef, 1),
            "p10_kwh": round(p10, 1),
            "p90_kwh": round(p90, 1)
        },
        "rooms": room_details,
        "assumptions": [
            f"Electricity tariff ₹{tariff:.1f}/kWh (configurable placeholder).",
            f"Grid emission factor {grid_ef:.2f} kg CO₂/kWh (flagged: verify latest CEA baseline).",
            "~6% HVAC energy per °C setpoint adjustment from 24°C nominal.",
            "Occupancy-aware HVAC maintains 35% minimum ventilation floor for IAQ comfort.",
            "Plug loads modeled as unaffected."
        ],
        "provenance": "ESTIMATED"
    }
    # ── Store in TTL cache ────────────────────────────────────────────────────
    _sim_cache[ck] = {"data": result, "_ts": time.monotonic()}
    return result


