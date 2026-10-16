"""
Anomaly Detection Service
Compares to: Siemens Navigator, Honeywell Forge

Detects statistical outliers in energy and occupancy readings using:
- Z-score (>2.5 sigma = anomaly)
- IQR fence (>Q3 + 1.5*IQR = high outlier)
- Rate-of-change spike detection (>40% jump in 1 hour)
"""
import math
import statistics
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.db import get_db


def _zscore(values: List[float]) -> List[float]:
    if len(values) < 3:
        return [0.0] * len(values)
    mu = statistics.mean(values)
    sd = statistics.stdev(values)
    if sd == 0:
        return [0.0] * len(values)
    return [(v - mu) / sd for v in values]


def _iqr_bounds(values: List[float]):
    sv = sorted(values)
    n = len(sv)
    q1 = sv[n // 4]
    q3 = sv[(3 * n) // 4]
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def detect_energy_anomalies() -> Dict[str, Any]:
    """Analyse last 24h hourly energy readings for outliers per room."""
    anomalies = []

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT room_id FROM energy_readings")
        room_ids = [r["room_id"] for r in cursor.fetchall()]

        for room_id in room_ids:
            cursor.execute("""
                SELECT hour, total_kw FROM energy_readings
                WHERE room_id = ? ORDER BY hour ASC
            """, (room_id,))
            rows = cursor.fetchall()
            if len(rows) < 4:
                continue

            hours = [r["hour"] for r in rows]
            kws   = [r["total_kw"] for r in rows]
            zs    = _zscore(kws)
            lo, hi = _iqr_bounds(kws)

            for i, (h, kw, z) in enumerate(zip(hours, kws, zs)):
                flags = []
                severity = "LOW"

                if abs(z) > 2.5:
                    flags.append(f"Z-score={z:.2f} (>{2.5}σ)")
                    severity = "HIGH" if abs(z) > 3.5 else "MEDIUM"

                if kw > hi:
                    flags.append(f"IQR upper fence breach ({kw:.1f} > {hi:.1f} kW)")
                    severity = "HIGH" if kw > hi * 1.3 else max(severity, "MEDIUM")

                if i > 0 and kws[i - 1] > 0:
                    roc = (kw - kws[i - 1]) / kws[i - 1]
                    if roc > 0.40:
                        flags.append(f"Rate-of-change spike +{roc*100:.0f}% in 1h")
                        severity = max(severity, "MEDIUM")

                if flags:
                    anomalies.append({
                        "room_id":  room_id,
                        "hour":     h,
                        "metric":   "energy_kw",
                        "value":    round(kw, 2),
                        "z_score":  round(z, 3),
                        "severity": severity,
                        "flags":    flags
                    })

    return {
        "anomaly_count": len(anomalies),
        "anomalies": sorted(anomalies, key=lambda x: x["severity"], reverse=True),
        "method": "Z-score (>2.5σ) + IQR fence + Rate-of-change",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def detect_occupancy_anomalies() -> Dict[str, Any]:
    """Detect unusual occupancy patterns (ghost occupancy, over-capacity spikes)."""
    anomalies = []

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.room_id, o.hour, o.count, r.capacity
            FROM occupancy_readings o
            JOIN rooms r ON o.room_id = r.id
            WHERE o.source = 'simulated'
            ORDER BY o.room_id, o.hour
        """)
        rows = cursor.fetchall()

    by_room: Dict[str, List] = {}
    for r in rows:
        by_room.setdefault(r["room_id"], []).append(r)

    for room_id, readings in by_room.items():
        cap = readings[0]["capacity"]
        counts = [r["count"] or 0 for r in readings]
        zs = _zscore([float(c) for c in counts])

        for i, (r, z) in enumerate(zip(readings, zs)):
            c = r["count"] or 0
            flags = []
            severity = "LOW"

            # Ghost occupancy: people in room at 2-4 AM
            if r["hour"] in (2, 3, 4) and c > 0:
                flags.append(f"Ghost occupancy: {c} people at {r['hour']}:00")
                severity = "MEDIUM"

            # Over-capacity
            if cap and c > cap:
                pct = (c - cap) / cap * 100
                flags.append(f"Over-capacity by {pct:.0f}% ({c}/{cap})")
                severity = "HIGH"

            # Statistical spike
            if abs(z) > 2.8:
                flags.append(f"Occupancy spike Z={z:.2f}")
                severity = max(severity, "MEDIUM")

            if flags:
                anomalies.append({
                    "room_id":  room_id,
                    "hour":     r["hour"],
                    "metric":   "occupancy",
                    "value":    c,
                    "capacity": cap,
                    "z_score":  round(z, 3),
                    "severity": severity,
                    "flags":    flags
                })

    return {
        "anomaly_count": len(anomalies),
        "anomalies": sorted(anomalies, key=lambda x: x["severity"], reverse=True),
        "method": "Z-score + ghost-hours + over-capacity check",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def get_anomaly_summary() -> Dict[str, Any]:
    energy_res = detect_energy_anomalies()
    occ_res    = detect_occupancy_anomalies()
    total      = energy_res["anomaly_count"] + occ_res["anomaly_count"]
    high_count = sum(1 for a in energy_res["anomalies"] + occ_res["anomalies"] if a["severity"] == "HIGH")

    return {
        "total_anomalies":  total,
        "high_severity":    high_count,
        "energy_anomalies": energy_res,
        "occupancy_anomalies": occ_res,
        "health_score": max(0, 100 - high_count * 10 - (total - high_count) * 3)
    }
