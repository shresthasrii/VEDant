import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from backend.db import get_db
from backend.schemas import OptimizeRequest, PlanResponse
from backend.services.consolidation.solver import run_roomwise_optimization

router = APIRouter(prefix="", tags=["consolidation"])

@router.post("/optimize", response_model=PlanResponse)
def optimize_consolidation(req: OptimizeRequest):
    plan = run_roomwise_optimization(
        day=req.day,
        capacity_margin=req.capacity_margin,
        disruption_penalty=req.disruption_penalty,
        solver_type=req.solver
    )
    return plan

@router.get("/plans")
def list_plans():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans ORDER BY created_at DESC")
        plans = [dict(p) for p in cursor.fetchall()]
        return {"plans": plans, "count": len(plans)}

@router.get("/plans/{plan_id}")
def get_plan(plan_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        p = cursor.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
            
        cursor.execute("SELECT * FROM plan_moves WHERE plan_id = ?", (plan_id,))
        moves = []
        for m in cursor.fetchall():
            md = dict(m)
            md["reasons"] = json.loads(md["reasons"]) if md["reasons"] else []
            md["checks_passed"] = json.loads(md["checks"]) if md["checks"] else []
            moves.append(md)
            
        d = dict(p)
        d["moves"] = moves
        return d

@router.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: str):
    """
    Approves the recommended consolidation plan.
    Updates the simulated approved timetable, sets plan status to approved,
    and records in the audit log.
    NOTE: As per ground rules, this updates the simulation only, never real equipment.
    """
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        plan = cursor.fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
            
        # Update plan status
        cursor.execute("UPDATE plans SET status = 'approved' WHERE id = ?", (plan_id,))
        cursor.execute("UPDATE plan_moves SET status = 'approved' WHERE plan_id = ?", (plan_id,))
        
        # Apply moves to classes table
        cursor.execute("SELECT class_id, to_room_id FROM plan_moves WHERE plan_id = ?", (plan_id,))
        moves = cursor.fetchall()
        for m in moves:
            cursor.execute("UPDATE classes SET room_id = ? WHERE id = ?", (m["to_room_id"], m["class_id"]))
            
        # Record Audit Log
        cursor.execute("""
        INSERT INTO audit_log (timestamp, user_action, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?, ?)
        """, (now, "APPROVE_PLAN", "plan", plan_id, json.dumps({
            "moves_count": len(moves),
            "savings_kwh": plan["savings_kwh"],
            "disclaimer": "Simulated approved state updated. No real equipment control."
        })))
        
    return {
        "status": "approved",
        "plan_id": plan_id,
        "message": "Plan successfully approved. Timetable and digital twin updated."
    }

@router.post("/plans/{plan_id}/reject")
def reject_plan(plan_id: str):
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE plans SET status = 'rejected' WHERE id = ?", (plan_id,))
        cursor.execute("UPDATE plan_moves SET status = 'rejected' WHERE plan_id = ?", (plan_id,))
        
        cursor.execute("""
        INSERT INTO audit_log (timestamp, user_action, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?, ?)
        """, (now, "REJECT_PLAN", "plan", plan_id, json.dumps({"note": "Rejected by facility administrator"})))
        
    return {
        "status": "rejected",
        "plan_id": plan_id,
        "message": "Plan rejected. No changes made to timetable."
    }
