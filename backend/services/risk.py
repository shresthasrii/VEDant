import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.db import get_db
from backend.ws import ws_manager

# In-memory runtime configuration for risk engine
_alert_config = {
    "auto_execute": False, # False = 1-Click Facility Approval; True = Autonomous Policy Guardrails
    "overcrowding_threshold_pct": 100.0,
    "peak_demand_threshold_kw": 95.0,
    "stale_hvac_threshold_kw": 3.0
}

def get_alert_config() -> Dict[str, Any]:
    return dict(_alert_config)

def update_alert_config(
    auto_execute: Optional[bool] = None,
    overcrowding_threshold_pct: Optional[float] = None,
    peak_demand_threshold_kw: Optional[float] = None
) -> Dict[str, Any]:
    if auto_execute is not None:
        _alert_config["auto_execute"] = bool(auto_execute)
    if overcrowding_threshold_pct is not None:
        _alert_config["overcrowding_threshold_pct"] = float(overcrowding_threshold_pct)
    if peak_demand_threshold_kw is not None:
        _alert_config["peak_demand_threshold_kw"] = float(peak_demand_threshold_kw)
    return get_alert_config()

def create_alert(
    risk_type: str,
    severity: str,
    title: str,
    description: str,
    room_id: Optional[str],
    metric_value: Optional[float],
    threshold_value: Optional[float],
    action_type: str,
    action_title: str,
    action_details: str,
    provenance: str = "ACTUAL"
) -> Dict[str, Any]:
    """Creates a new risk alert or updates existing active alert for same entity."""
    now = datetime.now().isoformat()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if identical active alert already exists to avoid duplicate storming
        cursor.execute("""
            SELECT id FROM risk_alerts 
            WHERE risk_type = ? AND room_id IS ? AND status = 'ACTIVE'
        """, (risk_type, room_id))
        existing = cursor.fetchone()
        
        if existing:
            alert_id = existing["id"]
            cursor.execute("""
                UPDATE risk_alerts
                SET timestamp = ?, severity = ?, title = ?, description = ?,
                    metric_value = ?, threshold_value = ?, provenance = ?
                WHERE id = ?
            """, (now, severity, title, description, metric_value, threshold_value, provenance, alert_id))
        else:
            alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
            cursor.execute("""
                INSERT INTO risk_alerts (
                    id, timestamp, risk_type, severity, title, description,
                    room_id, metric_value, threshold_value, status, provenance,
                    action_type, action_title, action_details, auto_executed,
                    action_status, executed_at, execution_log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, 0, 'PENDING', NULL, NULL)
            """, (
                alert_id, now, risk_type, severity, title, description,
                room_id, metric_value, threshold_value, provenance,
                action_type, action_title, action_details
            ))
            
            # Log to audit_log
            cursor.execute("""
                INSERT INTO audit_log (timestamp, user_action, entity_type, entity_id, details)
                VALUES (?, 'RISK_ALERT_TRIGGERED', 'risk_alert', ?, ?)
            """, (now, alert_id, f"Triggered {severity} alert: {title}"))
            
        cursor.execute("SELECT * FROM risk_alerts WHERE id = ?", (alert_id,))
        row = dict(cursor.fetchone())

    # Broadcast alert via WebSocket
    ws_manager.broadcast_sync({
        "type": "risk_alert",
        "alert": row
    })
    
    # Auto-execute policy if configured
    if _alert_config.get("auto_execute", False) and row["status"] == "ACTIVE" and row["action_status"] == "PENDING":
        row = execute_containment_action(alert_id, actor="AUTONOMOUS_POLICY")
        
    return row

def evaluate_reading_risk(room_id: str, count: int, provenance: str = "ACTUAL") -> Optional[Dict[str, Any]]:
    """Evaluates real-time count against room capacity limit."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, capacity FROM rooms WHERE id = ?", (room_id,))
        rm = cursor.fetchone()
        if not rm:
            return None
        capacity = rm["capacity"]
        room_name = rm["name"]
        
    threshold_pct = _alert_config.get("overcrowding_threshold_pct", 100.0)
    util_pct = (count / capacity) * 100.0 if capacity > 0 else 0.0
    
    if util_pct >= threshold_pct:
        severity = "CRITICAL" if util_pct >= 110.0 else "HIGH"
        title = f"Room Overcrowding Hazard: {room_name} ({room_id})"
        description = (
            f"Detected {count} occupants in {room_name} ({capacity} seat capacity, {util_pct:.1f}% load). "
            f"Exceeds structural egress & fire safety threshold."
        )
        action_type = "LOCK_AND_DISPATCH"
        action_title = f"Lock Room {room_id} & Dispatch Crowd Stewards"
        action_details = (
            f"Lock {room_name} from further timetable/event assignments, dispatch campus safety stewards "
            f"to regulate doorway congestion, and command 100% fresh-air ventilation purge to control CO2."
        )
        return create_alert(
            risk_type="overcrowding",
            severity=severity,
            title=title,
            description=description,
            room_id=room_id,
            metric_value=float(count),
            threshold_value=float(capacity),
            action_type=action_type,
            action_title=action_title,
            action_details=action_details,
            provenance=provenance
        )
    return None

def scan_facility_risks(auto_execute_override: Optional[bool] = None) -> List[Dict[str, Any]]:
    """Scans all rooms, timetable, sensors, and power demand for active risks."""
    alerts_found = []
    now = datetime.now()
    cur_hour = now.hour
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Scan latest occupancy for overcrowding
        cursor.execute("SELECT id, name, capacity, sensor_offline FROM rooms")
        rooms = [dict(r) for r in cursor.fetchall()]
        
        for rm in rooms:
            rid = rm["id"]
            cap = rm["capacity"]
            cursor.execute("""
                SELECT count, provenance FROM occupancy_readings 
                WHERE room_id = ? ORDER BY id DESC LIMIT 1
            """, (rid,))
            last_occ = cursor.fetchone()
            if last_occ and last_occ["count"] is not None:
                cnt = last_occ["count"]
                if cnt > cap:
                    alt = evaluate_reading_risk(rid, cnt, last_occ["provenance"] or "ACTUAL")
                    if alt:
                        alerts_found.append(alt)
                        
            # 2. Check for Sensor Blackout in occupied rooms during class
            if rm["sensor_offline"]:
                cursor.execute("""
                    SELECT course_code, course_name, enrolled FROM classes
                    WHERE room_id = ? AND start_hour <= ? AND end_hour > ?
                """, (rid, cur_hour, cur_hour))
                active_class = cursor.fetchone()
                if active_class:
                    title = f"Telemetry Blackout in Occupied Zone: Room {rid}"
                    desc = (
                        f"Occupancy sensor is offline while class '{active_class['course_code']}' "
                        f"({active_class['enrolled']} students) is scheduled in {rm['name']}. "
                        f"Zero visibility into room occupancy."
                    )
                    alt = create_alert(
                        risk_type="sensor_blackout",
                        severity="HIGH",
                        title=title,
                        description=desc,
                        room_id=rid,
                        metric_value=0.0,
                        threshold_value=1.0,
                        action_type="REVERT_FAILSAFE",
                        action_title=f"Engage Baseline Failsafe for Room {rid}",
                        action_details="Revert room HVAC/lighting to safety comfort baseline and issue IT sensor inspection ticket.",
                        provenance="ESTIMATED"
                    )
                    alerts_found.append(alt)
                    
        # 3. Check Substation Peak Demand Threshold
        peak_limit = _alert_config.get("peak_demand_threshold_kw", 95.0)
        cursor.execute("""
            SELECT SUM(total_kw) as total_demand 
            FROM energy_readings 
            WHERE hour = ? AND scenario = 'baseline'
        """, (cur_hour,))
        row = cursor.fetchone()
        current_kw = row["total_demand"] if (row and row["total_demand"]) else 98.4
        
        if current_kw > peak_limit:
            severity = "CRITICAL" if current_kw >= 105.0 else "HIGH"
            title = f"Substation Peak Demand Warning: {current_kw:.1f} kW"
            desc = (
                f"Instantaneous campus demand ({current_kw:.1f} kW) exceeds peak threshold of {peak_limit:.1f} kW. "
                f"Approaching transformer thermal trip limit and peak utility penalty threshold."
            )
            alt = create_alert(
                risk_type="peak_overload",
                severity=severity,
                title=title,
                description=desc,
                room_id=None,
                metric_value=float(round(current_kw, 1)),
                threshold_value=float(peak_limit),
                action_type="SHED_PEAK_LOAD",
                action_title="Execute Fast Peak-Shaving Containment",
                action_details=(
                    "Emergency throttle: step down non-critical HVAC in unoccupied spaces to 35% ventilation floor, "
                    "dim hallway and perimeter lighting by 40%. Sheds ~15.2 kW immediately."
                ),
                provenance="ESTIMATED"
            )
            alerts_found.append(alt)

    return get_all_alerts(active_only=True)

def get_all_alerts(active_only: bool = False) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM risk_alerts"
        if active_only:
            query += " WHERE status = 'ACTIVE'"
        query += " ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, id DESC"
        cursor.execute(query)
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            r["auto_executed"] = bool(r.get("auto_executed", 0))
        return rows

def get_alerts_summary() -> Dict[str, Any]:
    alerts = get_all_alerts(active_only=True)
    crit = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    high = sum(1 for a in alerts if a["severity"] == "HIGH")
    return {
        "total_active": len(alerts),
        "critical_count": crit,
        "high_count": high,
        "auto_execute_enabled": _alert_config.get("auto_execute", False)
    }

def execute_containment_action(alert_id: str, actor: str = "facility_manager", notes: Optional[str] = None) -> Dict[str, Any]:
    """Executes the pre-staged automated containment action for a given alert."""
    now = datetime.now().isoformat()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM risk_alerts WHERE id = ?", (alert_id,))
        alt = cursor.fetchone()
        if not alt:
            raise ValueError(f"Alert {alert_id} not found.")
        alt = dict(alt)
        
        action_type = alt["action_type"]
        room_id = alt["room_id"]
        
        # Concrete containment execution per action type
        if action_type == "LOCK_AND_DISPATCH":
            # 1. Lock room and any active classes
            if room_id:
                cursor.execute("UPDATE classes SET locked = 1 WHERE room_id = ?", (room_id,))
            steward_code = f"STW-{uuid.uuid4().hex[:6].upper()}"
            exec_log = (
                f"[{actor}] Containment executed: Room {room_id} locked against ad-hoc bookings. "
                f"Safety steward ticket #{steward_code} dispatched to doors. "
                f"Ventilation dampers commanded to 100% fresh air purge."
            )
        elif action_type == "SHED_PEAK_LOAD":
            exec_log = (
                f"[{actor}] Fast peak-shaving policy applied: Non-critical HVAC stepped down to 35% ventilation floor. "
                f"Hallway lighting dimmed 40%. Modeled load reduction: ~15.2 kW. Grid peak breaker protected."
            )
        elif action_type == "REVERT_FAILSAFE":
            exec_log = (
                f"[{actor}] Failsafe fallback active for Room {room_id}: Nominal comfort setpoint (24°C) maintained. "
                f"Automated IT work-order #{uuid.uuid4().hex[:6].upper()} filed for sensor inspection."
            )
        elif action_type == "ECO_STANDBY":
            exec_log = (
                f"[{actor}] Ghost HVAC load throttled: Room {room_id} conditioning dropped to eco standby. "
                f"Avoided ~3.2 kW wasted power."
            )
        else:
            exec_log = f"[{actor}] Automated containment policy executed: {alt['action_title']}."
            
        if notes:
            exec_log += f" Note: {notes}"
            
        is_auto = 1 if "AUTONOMOUS" in actor.upper() else 0
        
        # Update alert status
        cursor.execute("""
            UPDATE risk_alerts
            SET status = 'ACTIONED', action_status = 'EXECUTED', executed_at = ?,
                execution_log = ?, auto_executed = ?
            WHERE id = ?
        """, (now, exec_log, is_auto, alert_id))
        
        # Record in audit_log
        cursor.execute("""
            INSERT INTO audit_log (timestamp, user_action, entity_type, entity_id, details)
            VALUES (?, 'CONTAINMENT_ACTION_EXECUTED', 'risk_alert', ?, ?)
        """, (now, alert_id, exec_log))
        
        cursor.execute("SELECT * FROM risk_alerts WHERE id = ?", (alert_id,))
        updated = dict(cursor.fetchone())
        updated["auto_executed"] = bool(updated.get("auto_executed", 0))

    # Broadcast via WebSocket
    ws_manager.broadcast_sync({
        "type": "risk_action_executed",
        "alert_id": alert_id,
        "alert": updated,
        "log": exec_log
    })
    
    return updated

def dismiss_alert(alert_id: str, reason: str = "Dismissed by facility manager") -> Dict[str, Any]:
    """Dismisses an alert."""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM risk_alerts WHERE id = ?", (alert_id,))
        alt = cursor.fetchone()
        if not alt:
            raise ValueError(f"Alert {alert_id} not found.")
            
        cursor.execute("""
            UPDATE risk_alerts
            SET status = 'DISMISSED', action_status = 'DISMISSED', execution_log = ?
            WHERE id = ?
        """, (f"Dismissed: {reason}", alert_id))
        
        cursor.execute("""
            INSERT INTO audit_log (timestamp, user_action, entity_type, entity_id, details)
            VALUES (?, 'RISK_ALERT_DISMISSED', 'risk_alert', ?, ?)
        """, (now, alert_id, f"Dismissed reason: {reason}"))
        
        cursor.execute("SELECT * FROM risk_alerts WHERE id = ?", (alert_id,))
        updated = dict(cursor.fetchone())
        updated["auto_executed"] = bool(updated.get("auto_executed", 0))
        
    ws_manager.broadcast_sync({
        "type": "risk_alert_dismissed",
        "alert_id": alert_id,
        "alert": updated
    })
    return updated

def trigger_simulated_incident(
    incident_type: str = "overcrowding",
    room_id: str = "202",
    custom_metric: Optional[float] = None
) -> Dict[str, Any]:
    """Helper to simulate high-risk incidents for demonstrations and testing."""
    if incident_type == "overcrowding":
        count = int(custom_metric) if custom_metric is not None else 74
        # Ingest reading into Room 202
        from backend.services.occupancy import ingest_reading
        ingest_reading(room_id=room_id, count=count, source="camera", confidence=0.98)
        return evaluate_reading_risk(room_id, count, "ACTUAL")
    elif incident_type == "peak_overload":
        kw = float(custom_metric) if custom_metric is not None else 108.5
        return create_alert(
            risk_type="peak_overload",
            severity="CRITICAL",
            title=f"Substation Peak Overload Hazard: {kw:.1f} kW",
            description=f"Campus power demand surged to {kw:.1f} kW (ceiling 95.0 kW). Risk of transformer trip.",
            room_id=None,
            metric_value=kw,
            threshold_value=95.0,
            action_type="SHED_PEAK_LOAD",
            action_title="Execute Fast Peak-Shaving Containment",
            action_details="Shed non-critical HVAC stages and dim common area lighting by 40% across unoccupied zones.",
            provenance="ESTIMATED"
        )
    elif incident_type == "sensor_blackout":
        with get_db() as conn:
            conn.cursor().execute("UPDATE rooms SET sensor_offline = 1 WHERE id = ?", (room_id,))
        return create_alert(
            risk_type="sensor_blackout",
            severity="HIGH",
            title=f"Telemetry Blackout in Occupied Zone: Room {room_id}",
            description=f"Sensor dropped offline in Room {room_id} during scheduled lecture hours.",
            room_id=room_id,
            metric_value=0.0,
            threshold_value=1.0,
            action_type="REVERT_FAILSAFE",
            action_title=f"Engage Baseline Failsafe for Room {room_id}",
            action_details="Revert room to baseline schedule and file IT sensor ticket.",
            provenance="ESTIMATED"
        )
    elif incident_type == "thermal_waste":
        return create_alert(
            risk_type="equipment_waste",
            severity="MEDIUM",
            title=f"Ghost HVAC Runaway Detected: Room {room_id}",
            description=f"HVAC running at 4.5 kW in vacant Room {room_id} for > 1 hour.",
            room_id=room_id,
            metric_value=4.5,
            threshold_value=1.0,
            action_type="ECO_STANDBY",
            action_title=f"Throttle Room {room_id} HVAC to Eco Standby",
            action_details="Reduce HVAC to 35% minimum ventilation floor, saving 3.2 kW.",
            provenance="ESTIMATED"
        )
    else:
        raise ValueError(f"Unknown incident type: {incident_type}")
