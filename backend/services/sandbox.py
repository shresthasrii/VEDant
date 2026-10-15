from datetime import datetime
from typing import Dict, Any, Optional
from backend.db import get_db
from backend.ws import ws_manager
from backend.services.risk import create_alert, execute_containment_action

_current_drill: Dict[str, Any] = {
    "active": False,
    "drill_type": "NORMAL",
    "title": "Nominal Weekday Baseline",
    "description": "Standard campus operational timetable and environmental conditions.",
    "started_at": None,
    "stress_metrics": {}
}

def get_sandbox_status() -> Dict[str, Any]:
    res = dict(_current_drill)
    res["active_drill"] = res.get("drill_type", "NORMAL")
    return res

def run_stress_drill(drill_type: str) -> Dict[str, Any]:
    """
    Executes a high-stakes campus stress drill:
    - HEATWAVE: +6°C surge, solar radiation spike, checks peak shaving
    - GRID_CURTAILMENT: Emergency utility notice to shed 20 kW in 10 minutes
    - EXAM_SURGE: 140% student attendance surge testing capacity bounds
    - RESET: Returns campus to nominal operating parameters
    """
    now = datetime.now().isoformat()
    drill_type = drill_type.upper()
    
    if drill_type == "HEATWAVE":
        _current_drill["active"] = True
        _current_drill["drill_type"] = "HEATWAVE"
        _current_drill["title"] = "Extreme Heatwave Surge Drill (+6°C Ambient)"
        _current_drill["description"] = (
            "Outdoor temperature surged to 42.8°C with 920 W/m² solar irradiance. "
            "Unconstrained HVAC demand spikes to 114.5 kW (exceeding 95 kW substation limit). "
            "Testing automated peak shaving and pre-cooling failsafe."
        )
        _current_drill["started_at"] = now
        _current_drill["stress_metrics"] = {
            "ambient_temp_c": 42.8,
            "unconstrained_peak_kw": 114.5,
            "peak_shaved_kw": 94.2,
            "substation_trip_prevented": True,
            "iaq_ventilation_maintained": "35% comfort floor intact"
        }
        
        # Trigger containment alert
        create_alert(
            risk_type="peak_overload",
            severity="CRITICAL",
            title="HEATWAVE DRILL: Substation Peak Draw 114.5 kW",
            description="Ambient temperature surge (42.8°C) drove chiller load past transformer ceiling.",
            room_id=None,
            metric_value=114.5,
            threshold_value=95.0,
            action_type="SHED_PEAK_LOAD",
            action_title="Execute Fast Peak-Shaving Containment",
            action_details="Shed non-critical HVAC stages and dim corridor lighting by 40% across unoccupied zones.",
            provenance="SIMULATED"
        )
        
    elif drill_type == "GRID_CURTAILMENT":
        _current_drill["active"] = True
        _current_drill["drill_type"] = "GRID_CURTAILMENT"
        _current_drill["title"] = "Utility Grid Curtailment Notice (Fast 20 kW Drop)"
        _current_drill["description"] = (
            "Electric utility (BESCOM) issued an emergency demand-response notice: "
            "Campus must shed 20.0 kW within 10 minutes to support grid stability. "
            "Testing dynamic load stepping across secondary zones."
        )
        _current_drill["started_at"] = now
        _current_drill["stress_metrics"] = {
            "curtailment_target_kw": 20.0,
            "actual_shed_kw": 22.4,
            "time_to_shed_seconds": 45,
            "critical_loads_interrupted": 0,
            "incentive_earned_inr": 3600
        }
        
        create_alert(
            risk_type="peak_overload",
            severity="HIGH",
            title="GRID CURTAILMENT: Emergency 20 kW Demand Response",
            description="Utility curtailment notice active. Automated load shedding engaged.",
            room_id=None,
            metric_value=20.0,
            threshold_value=20.0,
            action_type="SHED_PEAK_LOAD",
            action_title="Execute Emergency Demand Response Containment",
            action_details="Step down HVAC in unassigned rooms and dim common areas immediately.",
            provenance="SIMULATED"
        )
        
    elif drill_type == "EXAM_SURGE":
        _current_drill["active"] = True
        _current_drill["drill_type"] = "EXAM_SURGE"
        _current_drill["title"] = "Campus Exam Week Crowd Surge (140% Density)"
        _current_drill["description"] = (
            "Final exam day crowd surge: Student attendance increases by 40% across all lecture spaces. "
            "Testing RoomWise capacity margins, crowd flow, and structural fire egress limits."
        )
        _current_drill["started_at"] = now
        _current_drill["stress_metrics"] = {
            "attendance_multiplier": 1.40,
            "hall_101_occupants": 78,
            "hall_202_occupants": 74,
            "capacity_violations": 1,
            "automated_containment": "Room 202 ad-hoc bookings locked; safety stewards dispatched"
        }
        
        create_alert(
            risk_type="overcrowding",
            severity="CRITICAL",
            title="EXAM SURGE: Room 202 Overcrowding Hazard (74/60 Seats)",
            description="Exam crowd surge exceeded structural capacity. Immediate stewarding required.",
            room_id="202",
            metric_value=74.0,
            threshold_value=60.0,
            action_type="LOCK_AND_DISPATCH",
            action_title="Lock Room 202 & Dispatch Crowd Stewards",
            action_details="Lock room bookings, dispatch stewards to doors, boost ventilation to 100%.",
            provenance="SIMULATED"
        )
        
    else:  # RESET
        _current_drill["active"] = False
        _current_drill["drill_type"] = "NORMAL"
        _current_drill["title"] = "Nominal Weekday Baseline"
        _current_drill["description"] = "Campus returned to standard operational profile."
        _current_drill["started_at"] = None
        _current_drill["stress_metrics"] = {}
        
    with get_db() as conn:
        conn.cursor().execute("""
            INSERT INTO audit_log (timestamp, user_action, entity_type, entity_id, details)
            VALUES (?, 'CAMPUS_STRESS_DRILL_TRIGGERED', 'sandbox', ?, ?)
        """, (now, drill_type, _current_drill["title"]))
        
    ws_manager.broadcast_sync({
        "type": "sandbox_drill_update",
        "drill": _current_drill
    })
    
    return get_sandbox_status()
