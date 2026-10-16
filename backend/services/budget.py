"""
Energy Budget Tracker & Cost Burn-Rate Forecasting Engine
Compares to: Schneider EcoStruxure Resource Advisor, Energy Star Portfolio Manager

Tracks monthly kWh allocation and electricity expenditure limits:
- Monthly & Fiscal Year budget tracking
- Month-To-Date (MTD) actual burn vs planned allocation
- Run-rate projection to End-Of-Month (EOM)
- Variance analysis and pacing alerts (Under Budget / On Track / At Risk / Overrun)
- Cost saving reinvestment allocation for green campus initiatives
"""
from datetime import datetime, timezone
import calendar
from typing import Dict, Any, List
from backend.services.twin import simulate_twin_scenario

# ── Campus Facility Monthly Budget Targets ───────────────────────────────────
MONTHLY_BUDGET_KWH = 28500.0    # 28,500 kWh/month allowance
MONTHLY_BUDGET_INR = 228000.0   # ₹2,28,000 monthly utility ceiling (~₹8.00/kWh effective)
ANNUAL_BUDGET_INR = MONTHLY_BUDGET_INR * 12.0


def calculate_energy_budget_status(current_day: int = 16, month: int = 10, year: int = 2026) -> Dict[str, Any]:
    """
    Computes MTD burn rate, pacing velocity, EOM projection, and variance vs monthly allocation.
    """
    _, days_in_month = calendar.monthrange(year, month)
    fraction_elapsed = min(1.0, max(0.01, current_day / float(days_in_month)))

    # Get daily consumption from twin simulation
    sim = simulate_twin_scenario()
    daily_base_kwh = sim["baseline"]["total_kwh"]
    daily_opt_kwh = sim["optimized"]["total_kwh"]
    daily_tariff_rate = sim["baseline"]["cost_inr"] / max(1.0, daily_base_kwh)

    # 1. Baseline Run-Rate (Unoptimized)
    mtd_base_kwh = daily_base_kwh * current_day
    mtd_base_inr = mtd_base_kwh * daily_tariff_rate
    projected_eom_base_kwh = daily_base_kwh * days_in_month
    projected_eom_base_inr = projected_eom_base_kwh * daily_tariff_rate

    # 2. VERDANT Optimized Run-Rate
    mtd_opt_kwh = daily_opt_kwh * current_day
    mtd_opt_inr = mtd_opt_kwh * daily_tariff_rate
    projected_eom_opt_kwh = daily_opt_kwh * days_in_month
    projected_eom_opt_inr = projected_eom_opt_kwh * daily_tariff_rate

    # Pacing: Expected budget spend up to today
    planned_mtd_kwh = MONTHLY_BUDGET_KWH * fraction_elapsed
    planned_mtd_inr = MONTHLY_BUDGET_INR * fraction_elapsed

    # Burn rate velocities
    opt_pacing_pct = round((mtd_opt_kwh / planned_mtd_kwh) * 100.0, 1) if planned_mtd_kwh else 100.0
    base_pacing_pct = round((mtd_base_kwh / planned_mtd_kwh) * 100.0, 1) if planned_mtd_kwh else 100.0

    # Variance vs Monthly Budget
    budget_variance_kwh = round(MONTHLY_BUDGET_KWH - projected_eom_opt_kwh, 1)
    budget_variance_inr = round(MONTHLY_BUDGET_INR - projected_eom_opt_inr, 0)
    surplus_pct = round((budget_variance_inr / MONTHLY_BUDGET_INR) * 100.0, 1)

    # Status Assessment
    if projected_eom_opt_inr <= MONTHLY_BUDGET_INR * 0.90:
        budget_status = "EXCELLENT SURPLUS (Under Budget)"
        status_badge = "SURPLUS"
    elif projected_eom_opt_inr <= MONTHLY_BUDGET_INR:
        budget_status = "ON TRACK (Within Budget Cap)"
        status_badge = "ON_TRACK"
    elif projected_eom_opt_inr <= MONTHLY_BUDGET_INR * 1.05:
        budget_status = "MODERATE RISK (Approaching Budget Cap)"
        status_badge = "WARNING"
    else:
        budget_status = "BUDGET OVERRUN ALERT (Exceeding Allocation)"
        status_badge = "OVERRUN"

    return {
        "budget_period": f"{calendar.month_name[month]} {year}",
        "days_in_month": days_in_month,
        "day_of_month": current_day,
        "month_progress_pct": round(fraction_elapsed * 100.0, 1),
        "monthly_targets": {
            "budget_kwh": MONTHLY_BUDGET_KWH,
            "budget_inr": MONTHLY_BUDGET_INR,
            "planned_mtd_inr": round(planned_mtd_inr, 0)
        },
        "mtd_actuals": {
            "optimized_kwh": round(mtd_opt_kwh, 1),
            "optimized_inr": round(mtd_opt_inr, 0),
            "baseline_kwh": round(mtd_base_kwh, 1),
            "baseline_inr": round(mtd_base_inr, 0),
            "pacing_pct": opt_pacing_pct,
            "baseline_pacing_pct": base_pacing_pct
        },
        "eom_projections": {
            "projected_eom_kwh": round(projected_eom_opt_kwh, 1),
            "projected_eom_inr": round(projected_eom_opt_inr, 0),
            "unoptimized_eom_inr": round(projected_eom_base_inr, 0),
            "eom_savings_inr": round(projected_eom_base_inr - projected_eom_opt_inr, 0)
        },
        "variance": {
            "surplus_deficit_inr": budget_variance_inr,
            "surplus_deficit_kwh": budget_variance_kwh,
            "surplus_pct": surplus_pct,
            "status": budget_status,
            "badge": status_badge
        },
        "green_fund_allocation": {
            "reinvestment_surplus_inr": max(0, int(budget_variance_inr * 0.40)),
            "purpose": "40% of utility bill savings designated for campus solar PV & sensor upgrades."
        },
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
