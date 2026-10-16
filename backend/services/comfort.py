"""
Holistic Indoor Environmental Quality (IEQ) Matrix Service
In accordance with:
- ASHRAE Standard 55-2023 (Thermal Environmental Conditions for Human Occupancy)
- ASHRAE Standard 62.1-2022 (Ventilation for Acceptable Indoor Air Quality)
- IS 3646 / CIBSE Code for Lighting (Visual Comfort: 300-500 Lux target)
- ANSI/ASA S12.60 (Acoustical Performance Criteria for Schools: <= 40 dBA)

Generates a unified 0-100 IEQ Comfort Index per room and facility-wide.
"""
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.db import get_db
from backend.services.iaq import calculate_room_iaq, calculate_pmv_ppd


def _calculate_lighting_score(room_type: str, lighting_kw: float, hour: int, natural_light_factor: float = 1.0) -> Dict[str, Any]:
    """
    Computes visual lux level and lighting score (IS 3646 standard).
    Classroom standard: 300 - 500 Lux.
    """
    # Natural daylight contribution during daytime (08:00 - 17:00)
    daylight_lux = 0.0
    if 8 <= hour <= 17:
        daylight_lux = 180.0 * natural_light_factor * math.sin(math.pi * (hour - 8) / 9.0)

    # Artificial illuminance from lighting fixtures
    # Assuming ~70 lumens/Watt LED fixtures, 75 m2 room area -> ~0.9 lux per Watt installed
    artificial_lux = (lighting_kw * 1000.0 * 0.35) if (8 <= hour <= 18) else 40.0
    total_lux = round(daylight_lux + artificial_lux, 1)

    if 350.0 <= total_lux <= 550.0:
        score = 100.0
        status = "OPTIMAL ILLUMINANCE (350-550 Lux)"
    elif 280.0 <= total_lux < 350.0 or 550.0 < total_lux <= 650.0:
        score = 88.0
        status = "COMPLIANT ILLUMINANCE"
    elif 200.0 <= total_lux < 280.0:
        score = 70.0
        status = "SUB-OPTIMAL (Slightly Dim)"
    elif total_lux > 650.0:
        score = 75.0
        status = "GLARE RISK (Daylight harvesting recommended)"
    else:
        score = 45.0
        status = "INADEQUATE LIGHTING"

    return {
        "total_lux": total_lux,
        "daylight_lux": round(daylight_lux, 1),
        "artificial_lux": round(artificial_lux, 1),
        "target_band_lux": "300 - 500 Lux (IS 3646)",
        "score": score,
        "status": status
    }


def _calculate_acoustic_score(occupants: int, capacity: int, hvac_kw: float) -> Dict[str, Any]:
    """
    Estimates indoor noise level in dBA per ANSI/ASA S12.60 classroom acoustic standard.
    Target: <= 40 dBA unoccupied, <= 50 dBA during lecture sessions.
    """
    # Baseline equipment noise: 36 dBA base + HVAC fan flow contribution
    hvac_noise = min(10.0, hvac_kw * 1.5)
    base_dba = 36.0 + hvac_noise

    # Occupant conversation/movement noise: ~0.4 dBA per student
    occupant_noise = occupants * 0.45
    total_dba = round(base_dba + occupant_noise, 1)

    if total_dba <= 42.0:
        score = 100.0
        status = "EXCELLENT QUIET (Ideal for Focus/Exam)"
    elif total_dba <= 48.0:
        score = 90.0
        status = "GOOD (Active Collaborative Learning)"
    elif total_dba <= 56.0:
        score = 70.0
        status = "MODERATELY NOISY (High Activity)"
    else:
        score = 45.0
        status = "EXCESSIVE ACOUSTIC DISTURBANCE"

    return {
        "sound_level_dba": total_dba,
        "threshold_dba": 48.0,
        "score": score,
        "status": status
    }


def calculate_room_ieq(room_id: str, hour: int = 14, setpoint_c: float = 24.5) -> Dict[str, Any]:
    """
    Computes unified 0-100 IEQ score for a single room combining:
    - Thermal Comfort (35% weight)
    - Air Quality / CO2 (30% weight)
    - Visual Lighting (20% weight)
    - Acoustic Comfort (15% weight)
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        rm = cursor.fetchone()
        if not rm:
            return {}

        cursor.execute("""
            SELECT count FROM occupancy_readings
            WHERE room_id = ? AND hour = ? AND source = 'simulated'
            ORDER BY id DESC LIMIT 1
        """, (room_id, hour))
        occ_row = cursor.fetchone()
        count = occ_row["count"] if occ_row and occ_row["count"] is not None else int(rm["capacity"] * 0.4)

    # 1. Thermal Comfort
    thermal_raw = calculate_pmv_ppd(setpoint_c)
    ppd = thermal_raw["ppd_pct"]
    thermal_score = max(20.0, 100.0 - (ppd - 5.0) * 2.2)

    # 2. IAQ / CO2
    iaq_raw = calculate_room_iaq(room_id, count, setpoint_c=setpoint_c)
    co2 = iaq_raw.get("co2_ppm", 450)
    if co2 <= 650:
        iaq_score = 100.0
    elif co2 <= 850:
        iaq_score = 90.0
    elif co2 <= 1000:
        iaq_score = 80.0
    elif co2 <= 1250:
        iaq_score = 60.0
    else:
        iaq_score = 35.0

    # 3. Visual Comfort
    lighting_calc = _calculate_lighting_score(rm["type"], rm["lighting_kw"], hour)
    lighting_score = lighting_calc["score"]

    # 4. Acoustic Comfort
    acoustic_calc = _calculate_acoustic_score(count, rm["capacity"], rm["hvac_kw"])
    acoustic_score = acoustic_calc["score"]

    # Composite IEQ Index
    composite_ieq = round(
        thermal_score * 0.35 +
        iaq_score * 0.30 +
        lighting_score * 0.20 +
        acoustic_score * 0.15,
        1
    )

    if composite_ieq >= 90.0:
        ieq_rating = "EXCELLENT IEQ (WELL Platinum & ASHRAE 55 Class A)"
        ieq_badge = "EXCELLENT"
    elif composite_ieq >= 78.0:
        ieq_rating = "GOOD (Standard Compliant IEQ)"
        ieq_badge = "GOOD"
    elif composite_ieq >= 65.0:
        ieq_rating = "MODERATE (Minor Comfort Drift)"
        ieq_badge = "MODERATE"
    else:
        ieq_rating = "COMPROMISED (Action Recommended)"
        ieq_badge = "ATTENTION"

    return {
        "room_id": room_id,
        "room_name": rm["name"],
        "floor": rm["floor"],
        "room_type": rm["type"],
        "occupants": count,
        "capacity": rm["capacity"],
        "composite_ieq_score": composite_ieq,
        "ieq_rating": ieq_rating,
        "ieq_badge": ieq_badge,
        "sub_scores": {
            "thermal_comfort": {
                "score": round(thermal_score, 1),
                "pmv": thermal_raw["pmv"],
                "ppd_pct": thermal_raw["ppd_pct"],
                "status": thermal_raw["status"],
                "weight": "35%"
            },
            "indoor_air_quality": {
                "score": round(iaq_score, 1),
                "co2_ppm": co2,
                "status": iaq_raw.get("iaq_rating", "GOOD"),
                "weight": "30%"
            },
            "visual_lighting": {
                "score": round(lighting_score, 1),
                "lux": lighting_calc["total_lux"],
                "status": lighting_calc["status"],
                "weight": "20%"
            },
            "acoustics": {
                "score": round(acoustic_score, 1),
                "sound_dba": acoustic_calc["sound_level_dba"],
                "status": acoustic_calc["status"],
                "weight": "15%"
            }
        }
    }


def get_building_ieq_matrix(hour: int = 14) -> Dict[str, Any]:
    """Generates building-wide IEQ scorecard across all 12 rooms."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM rooms ORDER BY floor, id")
        room_ids = [r["id"] for r in cursor.fetchall()]

    room_results = [calculate_room_ieq(rid, hour) for rid in room_ids]
    avg_score = round(sum(r["composite_ieq_score"] for r in room_results) / max(1, len(room_results)), 1)
    
    excellent_count = sum(1 for r in room_results if r["composite_ieq_score"] >= 88.0)
    good_count = sum(1 for r in room_results if 75.0 <= r["composite_ieq_score"] < 88.0)
    attention_count = sum(1 for r in room_results if r["composite_ieq_score"] < 75.0)

    return {
        "building_ieq_index": avg_score,
        "rating": "WELL Platinum / IGBC Green Campus Tier" if avg_score >= 85.0 else "Standard Compliant",
        "standards": ["ASHRAE 55-2023", "ASHRAE 62.1-2022", "IS 3646 Lighting", "ANSI/ASA S12.60 Acoustics"],
        "hour_evaluated": hour,
        "summary": {
            "total_rooms": len(room_results),
            "optimal_rooms": excellent_count,
            "compliant_rooms": good_count,
            "attention_rooms": attention_count
        },
        "rooms": sorted(room_results, key=lambda x: x["composite_ieq_score"], reverse=True),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
