"""
Occupancy Forecasting Service
Compares to: Spacewell, Density.io, Honeywell Forge

Uses exponential smoothing (Holt's method) to forecast occupancy:
- Next hour forecast per room
- Next 24-hour forecast per room
- Confidence intervals

Also produces a building-level occupancy heatmap forecast.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.db import get_db


def _holt_smoothing(
    series: List[float],
    alpha: float = 0.4,  # level smoothing
    beta:  float = 0.2,  # trend smoothing
) -> List[float]:
    """Holt's double exponential smoothing for trend-bearing series."""
    if not series:
        return []
    if len(series) == 1:
        return series[:]

    L = series[0]
    T = series[1] - series[0]
    smoothed = [L]

    for i in range(1, len(series)):
        L_prev, T_prev = L, T
        L = alpha * series[i] + (1 - alpha) * (L_prev + T_prev)
        T = beta * (L - L_prev) + (1 - beta) * T_prev
        smoothed.append(L)

    return smoothed


def _forecast_next(series: List[float], steps: int = 1,
                   alpha: float = 0.4, beta: float = 0.2) -> List[float]:
    """Forecast `steps` steps ahead using Holt's method."""
    if len(series) < 2:
        last = series[-1] if series else 0.0
        return [max(0.0, last)] * steps

    L = series[0]
    T = series[1] - series[0]
    for i in range(1, len(series)):
        L_prev, T_prev = L, T
        L = alpha * series[i] + (1 - alpha) * (L_prev + T_prev)
        T = beta * (L - L_prev) + (1 - beta) * T_prev

    return [max(0.0, round(L + T * h, 1)) for h in range(1, steps + 1)]


def forecast_room(room_id: str) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT capacity FROM rooms WHERE id = ?", (room_id,))
        row = cursor.fetchone()
        capacity = row["capacity"] if row else 30

        cursor.execute("""
            SELECT hour, count FROM occupancy_readings
            WHERE room_id = ? AND source = 'simulated'
            ORDER BY hour ASC
        """, (room_id,))
        readings = cursor.fetchall()

    if not readings:
        return {"room_id": room_id, "error": "no data"}

    counts = [float(r["count"] or 0) for r in readings]
    hours  = [r["hour"] for r in readings]

    smoothed = _holt_smoothing(counts)
    next_1h  = _forecast_next(counts, steps=1)[0]
    next_24h = _forecast_next(counts, steps=24)

    # Confidence interval: ±15% (simplified)
    ci_lo = [max(0.0, round(v * 0.85, 1)) for v in next_24h]
    ci_hi = [min(float(capacity), round(v * 1.15, 1)) for v in next_24h]

    # Peak forecast hour
    peak_h = next_24h.index(max(next_24h))
    utilizations = [min(1.0, v / capacity) if capacity else 0.0 for v in next_24h]

    return {
        "room_id":        room_id,
        "capacity":       capacity,
        "historical":     [{"hour": h, "count": int(c)} for h, c in zip(hours, counts)],
        "smoothed":       [round(s, 1) for s in smoothed],
        "next_1h":        round(next_1h, 1),
        "forecast_24h":   [round(v, 1) for v in next_24h],
        "ci_low":         ci_lo,
        "ci_high":        ci_hi,
        "peak_hour":      peak_h,
        "peak_count":     round(max(next_24h), 1),
        "utilizations":   [round(u, 3) for u in utilizations],
        "method":         "Holt double-exponential smoothing (α=0.4, β=0.2)"
    }


def get_campus_forecast() -> Dict[str, Any]:
    """Aggregate building-level occupancy forecast."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, floor FROM rooms ORDER BY floor, id")
        rooms = [dict(r) for r in cursor.fetchall()]

    forecasts = {}
    total_next_1h  = 0.0
    total_capacity = 0
    heatmap: List[Dict] = []

    for r in rooms:
        fc = forecast_room(r["id"])
        if "error" not in fc:
            forecasts[r["id"]] = fc
            total_next_1h  += fc["next_1h"]
            total_capacity += fc["capacity"]
            heatmap.append({
                "room_id":   r["id"],
                "room_name": r["name"],
                "floor":     r["floor"],
                "next_1h":   fc["next_1h"],
                "capacity":  fc["capacity"],
                "utilization": round(fc["next_1h"] / fc["capacity"], 3) if fc["capacity"] else 0.0,
                "status":    "HIGH" if fc["next_1h"] >= fc["capacity"] * 0.85 else
                             ("MEDIUM" if fc["next_1h"] >= fc["capacity"] * 0.50 else "LOW")
            })

    heatmap.sort(key=lambda x: x["utilization"], reverse=True)

    return {
        "campus_next_1h_headcount": round(total_next_1h, 0),
        "campus_capacity":          total_capacity,
        "campus_utilization_pct":   round(total_next_1h / total_capacity * 100, 1) if total_capacity else 0,
        "heatmap":                  heatmap,
        "room_forecasts":           forecasts,
        "generated_at":             datetime.now(timezone.utc).isoformat()
    }
