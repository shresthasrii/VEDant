from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any

from backend.schemas import (
    AlertsResponse, AlertsSummary, RiskAlertItem,
    ExecuteActionRequest, DismissAlertRequest, AlertConfigRequest, SimulateIncidentRequest
)
from backend.services.risk import (
    get_all_alerts, get_alerts_summary, scan_facility_risks,
    execute_containment_action, dismiss_alert, get_alert_config,
    update_alert_config, trigger_simulated_incident
)

router = APIRouter(prefix="", tags=["alerts"])

@router.get("/alerts")
def get_alerts(active_only: bool = Query(False)) -> Dict[str, Any]:
    """Returns all risk alerts and facility safety status."""
    alerts = get_all_alerts(active_only=active_only)
    summary = get_alerts_summary()
    return {
        "alerts": alerts,
        "summary": summary
    }

@router.post("/alerts/scan")
def run_scan() -> Dict[str, Any]:
    """Scans all rooms, timetable, sensors, and power demand for active risks."""
    active_alerts = scan_facility_risks()
    summary = get_alerts_summary()
    return {
        "status": "success",
        "alerts_scanned": len(active_alerts),
        "alerts": active_alerts,
        "summary": summary
    }

@router.post("/alerts/{alert_id}/execute")
def execute_alert_action(alert_id: str, req: Optional[ExecuteActionRequest] = None) -> Dict[str, Any]:
    """Executes the pre-staged automated containment action for a given alert."""
    actor = req.actor if req else "facility_manager"
    notes = req.notes if req else None
    try:
        updated = execute_containment_action(alert_id, actor=actor, notes=notes)
        return {
            "status": "success",
            "message": "Automated containment action executed successfully.",
            "alert": updated
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute containment action: {str(e)}")

@router.post("/alerts/{alert_id}/dismiss")
def dismiss_risk_alert(alert_id: str, req: Optional[DismissAlertRequest] = None) -> Dict[str, Any]:
    """Dismisses an active alert."""
    reason = req.reason if req and req.reason else "Dismissed by facility manager"
    try:
        updated = dismiss_alert(alert_id, reason=reason)
        return {
            "status": "success",
            "message": "Alert dismissed.",
            "alert": updated
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/alerts/config")
def get_config() -> Dict[str, Any]:
    """Returns risk threshold configuration and auto-execute policy mode."""
    return get_alert_config()

@router.post("/alerts/config")
def set_config(req: AlertConfigRequest) -> Dict[str, Any]:
    """Updates risk threshold configuration or auto-execute policy mode."""
    updated = update_alert_config(
        auto_execute=req.auto_execute,
        overcrowding_threshold_pct=req.overcrowding_threshold_pct,
        peak_demand_threshold_kw=req.peak_demand_threshold_kw
    )
    return {
        "status": "success",
        "config": updated
    }

@router.post("/alerts/simulate")
def simulate_incident(req: SimulateIncidentRequest) -> Dict[str, Any]:
    """Simulates a high-risk incident on demand for testing and evaluation."""
    try:
        alert = trigger_simulated_incident(
            incident_type=req.incident_type,
            room_id=req.room_id or "202",
            custom_metric=req.custom_metric
        )
        return {
            "status": "success",
            "incident_type": req.incident_type,
            "simulated_alert": alert
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
