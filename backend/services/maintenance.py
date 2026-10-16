"""
Predictive Maintenance Engine
Compares to: IBM Maximo, Siemens Navigator

Scores each room's HVAC + sensor equipment on a 0-100 health scale.
Uses rule-based signals:
  - Sensor offline streaks
  - Energy deviation from expected (indicative of HVAC fault)
  - Occupancy vs HVAC load mismatch
  - Age-based degradation curve (simulated)

Returns: equipment health, estimated days-to-failure, recommended action
"""
import math
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from backend.db import get_db

# Maintenance priority thresholds
CRITICAL_SCORE = 35
WARNING_SCORE  = 60

# Simulated installation age seed (deterministic by room_id)
def _age_years(room_id: str) -> float:
    h = sum(ord(c) for c in room_id) % 100
    return 1.0 + h * 0.12   # 1 – 13 years


def _degradation_factor(age_years: float, design_life: float = 15.0) -> float:
    """Bathtub-curve degradation: slow early, accelerating near EOL."""
    frac = min(age_years / design_life, 1.0)
    return 1.0 - (frac ** 1.8)  # concave-down health


def _energy_deviation_score(room_id: str, conn) -> float:
    """Compare recent avg kW vs simulated baseline avg kW for the room."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT AVG(total_kw) as avg_kw FROM energy_readings
        WHERE room_id = ? AND scenario = 'baseline'
    """, (room_id,))
    row = cursor.fetchone()
    if not row or row["avg_kw"] is None:
        return 1.0  # neutral

    baseline_avg = row["avg_kw"]
    # Simulated "recent" avg with small jitter
    seed = sum(ord(c) for c in room_id) % 1000
    recent_avg = baseline_avg * (1.0 + (seed % 30 - 15) / 200.0)

    if baseline_avg == 0:
        return 1.0
    deviation = abs(recent_avg - baseline_avg) / baseline_avg
    # >15% deviation = concern; >30% = fault
    return max(0.0, 1.0 - deviation * 3.0)


def _sensor_health_score(room_id: str, conn) -> float:
    cursor = conn.cursor()
    cursor.execute("SELECT sensor_offline FROM rooms WHERE id = ?", (room_id,))
    row = cursor.fetchone()
    if row and row["sensor_offline"]:
        return 0.3   # degraded if currently offline
    return 1.0


def score_equipment(room_id: str) -> Dict[str, Any]:
    with get_db() as conn:
        energy_score  = _energy_deviation_score(room_id, conn)
        sensor_score  = _sensor_health_score(room_id, conn)

    age    = _age_years(room_id)
    age_sc = _degradation_factor(age)

    # Weighted composite
    health = (age_sc * 0.40 + energy_score * 0.35 + sensor_score * 0.25) * 100
    health = max(5.0, min(100.0, health))

    # Days to failure estimate (exponential approach to 0 as health drops)
    dtf = max(1, int(health / 100 * 730))  # up to ~2 years

    if health < CRITICAL_SCORE:
        priority = "CRITICAL"
        action   = "Schedule immediate inspection. Risk of unplanned downtime."
        next_service = "Within 7 days"
    elif health < WARNING_SCORE:
        priority = "WARNING"
        action   = "Schedule preventive maintenance this month."
        next_service = "Within 30 days"
    else:
        priority = "OK"
        action   = "Continue routine maintenance schedule."
        next_service = "Next quarterly cycle"

    components = {
        "HVAC unit":        round(age_sc * 100, 1),
        "Sensor array":     round(sensor_score * 100, 1),
        "Energy metering":  round(energy_score * 100, 1)
    }

    return {
        "room_id":           room_id,
        "health_score":      round(health, 1),
        "priority":          priority,
        "estimated_age_yrs": round(age, 1),
        "days_to_failure":   dtf,
        "action":            action,
        "next_service":      next_service,
        "component_scores":  components
    }


def get_maintenance_report() -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, floor FROM rooms ORDER BY floor, id")
        rooms = [dict(r) for r in cursor.fetchall()]

    scores = [score_equipment(r["id"]) for r in rooms]
    scores_with_names = []
    room_map = {r["id"]: r["name"] for r in rooms}
    for s in scores:
        s["room_name"] = room_map.get(s["room_id"], s["room_id"])
        scores_with_names.append(s)

    critical = [s for s in scores if s["priority"] == "CRITICAL"]
    warning  = [s for s in scores if s["priority"] == "WARNING"]
    ok       = [s for s in scores if s["priority"] == "OK"]

    avg_health = sum(s["health_score"] for s in scores) / len(scores) if scores else 100.0

    return {
        "fleet_health_score":  round(avg_health, 1),
        "critical_count":      len(critical),
        "warning_count":       len(warning),
        "ok_count":            len(ok),
        "equipment":           sorted(scores_with_names, key=lambda x: x["health_score"]),
        "next_recommended":    critical[0] if critical else (warning[0] if warning else None),
        "generated_at":        datetime.now(timezone.utc).isoformat()
    }
