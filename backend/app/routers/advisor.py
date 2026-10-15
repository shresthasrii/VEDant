import json
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from backend.schemas import AdvisorExplainRequest, AdvisorResponse
from backend.services.advisor import explain_plan
from backend.services.consolidation.solver import run_roomwise_optimization
from backend.db import get_db

router = APIRouter(prefix="/advisor", tags=["advisor"])

@router.post("/explain", response_model=AdvisorResponse)
def get_advisor_explanation(req: AdvisorExplainRequest):
    # Fetch plan context
    with get_db() as conn:
        cursor = conn.cursor()
        if req.plan_id:
            cursor.execute("SELECT * FROM plans WHERE id = ?", (req.plan_id,))
            plan_row = cursor.fetchone()
        else:
            cursor.execute("SELECT * FROM plans ORDER BY created_at DESC LIMIT 1")
            plan_row = cursor.fetchone()
            
    if not plan_row:
        # Run default optimization to create one
        plan_dict = run_roomwise_optimization()
    else:
        plan_dict = dict(plan_row)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM plan_moves WHERE plan_id = ?", (plan_dict["id"],))
            moves = []
            for m in cursor.fetchall():
                md = dict(m)
                md["reasons"] = json.loads(md["reasons"]) if md["reasons"] else []
                md["checks_passed"] = json.loads(md["checks"]) if md["checks"] else []
                moves.append(md)
            plan_dict["moves"] = moves
            plan_dict["empty_rooms_freed"] = ["Seminar Hall 202"]
            
    explanation = explain_plan(plan_dict)
    return AdvisorResponse(**explanation)
