import json
from pathlib import Path
from typing import List, Dict, Any

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "factors.json"

def load_factors() -> Dict[str, Any]:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_tod_rate(hour: int) -> float:
    """Returns Time-of-Day tariff (₹/kWh) for the given hour of day (0-23)."""
    factors = load_factors()
    tod = factors.get("tod_tariffs", {})
    
    if hour in tod.get("peak", {}).get("hours", [18, 19, 20, 21]):
        return tod["peak"]["rate"]
    elif hour in tod.get("off_peak", {}).get("hours", [22, 23, 0, 1, 2, 3, 4, 5]):
        return tod["off_peak"]["rate"]
    else:
        return tod.get("normal", {}).get("rate", 8.00)

def calculate_tod_energy_cost(hourly_kwh: List[float]) -> Dict[str, Any]:
    """
    Calculates 24-hour electricity bill under Time-of-Day (ToD) tariffs 
    and Maximum Demand Charge (MDC) kVA penalty.
    """
    factors = load_factors()
    contracted_kva = factors.get("contracted_demand_kva", 95.0)
    mdc_rate = factors.get("demand_charge_inr_per_kva", 350.0)
    pf = factors.get("power_factor", 0.95)
    
    off_peak_kwh = 0.0
    normal_kwh = 0.0
    peak_kwh = 0.0
    
    hourly_costs = []
    
    for h in range(len(hourly_kwh)):
        kw = hourly_kwh[h]
        rate = get_tod_rate(h)
        cost = kw * rate
        hourly_costs.append(round(cost, 2))
        
        if rate == 12.50:
            peak_kwh += kw
        elif rate == 5.50:
            off_peak_kwh += kw
        else:
            normal_kwh += kw
            
    total_kwh = sum(hourly_kwh)
    total_energy_charge = (off_peak_kwh * 5.50) + (normal_kwh * 8.00) + (peak_kwh * 12.50)
    
    # Peak demand calculation
    peak_kw = max(hourly_kwh) if hourly_kwh else 0.0
    peak_kva = peak_kw / pf if pf > 0 else peak_kw
    
    # Excess demand charge if peak exceeds contracted threshold
    excess_kva = max(0.0, peak_kva - contracted_kva)
    demand_penalty_inr = excess_kva * mdc_rate
    
    total_bill_inr = total_energy_charge + demand_penalty_inr
    
    # Compare against standard flat tariff (₹8.0/kWh)
    flat_cost_inr = total_kwh * 8.00
    
    return {
        "total_kwh": round(total_kwh, 1),
        "peak_kw": round(peak_kw, 1),
        "peak_kva": round(peak_kva, 1),
        "contracted_kva": round(contracted_kva, 1),
        "excess_kva": round(excess_kva, 1),
        "tod_breakdown": {
            "off_peak_kwh": round(off_peak_kwh, 1),
            "off_peak_cost": round(off_peak_kwh * 5.50, 1),
            "normal_kwh": round(normal_kwh, 1),
            "normal_cost": round(normal_kwh * 8.00, 1),
            "peak_surge_kwh": round(peak_kwh, 1),
            "peak_surge_cost": round(peak_kwh * 12.50, 1)
        },
        "energy_charge_inr": round(total_energy_charge),
        "demand_penalty_inr": round(demand_penalty_inr),
        "total_bill_inr": round(total_bill_inr),
        "flat_tariff_cost_inr": round(flat_cost_inr),
        "tod_variance_pct": round(((total_bill_inr - flat_cost_inr) / flat_cost_inr * 100), 1) if flat_cost_inr > 0 else 0.0,
        "hourly_rates": [get_tod_rate(h) for h in range(24)],
        "hourly_costs": hourly_costs
    }

def compare_tod_scenarios(baseline_hourly: List[float], optimized_hourly: List[float]) -> Dict[str, Any]:
    """Compares baseline vs optimized energy usage with dynamic ToD tariffs."""
    base = calculate_tod_energy_cost(baseline_hourly)
    opt = calculate_tod_energy_cost(optimized_hourly)
    
    kwh_saved = max(0.0, base["total_kwh"] - opt["total_kwh"])
    pct_saved = (kwh_saved / base["total_kwh"] * 100) if base["total_kwh"] > 0 else 0.0
    bill_saved_inr = max(0.0, base["total_bill_inr"] - opt["total_bill_inr"])
    penalty_avoided_inr = max(0.0, base["demand_penalty_inr"] - opt["demand_penalty_inr"])
    
    factors = load_factors()
    grid_ef = factors.get("grid_emission_factor_kg_co2_per_kwh", 0.70)
    co2_saved_kg = kwh_saved * grid_ef
    
    return {
        "baseline": base,
        "optimized": opt,
        "impact": {
            "kwh_saved": round(kwh_saved, 1),
            "savings_pct": round(pct_saved, 1),
            "total_savings_inr": round(bill_saved_inr),
            "demand_penalty_avoided_inr": round(penalty_avoided_inr),
            "co2_saved_kg": round(co2_saved_kg, 1),
            "trees_equivalent": round(co2_saved_kg / 21.8, 1) # ~21.8 kg CO2 absorbed per tree/year
        }
    }
