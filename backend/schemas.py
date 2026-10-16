from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from enum import Enum

class Provenance(str, Enum):
    ACTUAL = "ACTUAL"
    SIMULATED = "SIMULATED"
    ESTIMATED = "ESTIMATED"

class RoomBase(BaseModel):
    id: str
    name: str
    floor: int
    type: str
    capacity: int
    hvac_kw: float
    lighting_kw: float
    plug_kw: float
    accessible: bool = True
    equipment: List[str] = []
    sensor_offline: bool = False
    pos_3d: Optional[Dict[str, float]] = None

class RoomStatus(RoomBase):
    current_occupancy: Optional[int] = None
    smoothed_occupancy: Optional[float] = None
    utilization_rate: Optional[float] = None
    status: str = "unoccupied" # 'occupied', 'unoccupied', 'high_utilization', 'offline'
    source: str = "simulated"
    provenance: Provenance = Provenance.SIMULATED
    demand_kw: float = 0.0

class ClassItem(BaseModel):
    id: str
    course_code: str
    course_name: str
    section: str
    instructor: str
    day_of_week: str
    start_hour: int
    end_hour: int
    enrolled: int
    room_id: str
    required_equipment: List[str] = []
    accessibility_needed: bool = False
    compatibility_group: Optional[str] = None
    locked: bool = False

class OccupancyIngest(BaseModel):
    room_id: str
    timestamp: Optional[str] = None
    count: int = Field(..., ge=0, description="Person headcount must be non-negative")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    source: str = "camera" # 'camera' or 'simulated'

class EnergyBreakdown(BaseModel):
    hvac_kw: float
    lighting_kw: float
    plug_kw: float
    total_kw: float
    provenance: Provenance = Provenance.ESTIMATED

class OptimizeRequest(BaseModel):
    day: str = "Monday"
    capacity_margin: float = 0.10
    disruption_penalty: float = 2.0
    solver: str = "heuristic" # 'heuristic' or 'cp_sat'

class PlanMoveItem(BaseModel):
    id: str
    class_id: str
    course_code: str
    course_name: str
    from_room_id: str
    from_room_name: str
    to_room_id: str
    to_room_name: str
    start_hour: int
    end_hour: int
    attendance: int
    reasons: List[str]
    checks_passed: List[str]
    status: str = "pending"

class PlanResponse(BaseModel):
    id: str
    created_at: str
    solver: str
    status: str
    baseline_kwh: float
    optimized_kwh: float
    savings_kwh: float
    savings_pct: float
    p10_savings_kwh: float
    p90_savings_kwh: float
    robustness_score: float
    moves: List[PlanMoveItem]
    empty_rooms_freed: List[str]
    assumptions: List[str]
    provenance: Provenance = Provenance.ESTIMATED

class AdvisorExplainRequest(BaseModel):
    plan_id: Optional[str] = None
    room_id: Optional[str] = None
    question: Optional[str] = None
    context_type: str = "plan" # 'plan', 'room', 'general'

class AdvisorResponse(BaseModel):
    mode: str # 'LLM (Ollama llama3.2)' or 'template explanation (no LLM)'
    summary: str
    key_findings: List[str]
    reasons_per_move: Dict[str, str] = {}
    constraints_verified: List[str] = []
    modeled_savings: Dict[str, Any] = {}
    faculty_notice_draft: Optional[str] = None
    provenance: Provenance = Provenance.ESTIMATED

class RiskAlertItem(BaseModel):
    id: str
    timestamp: str
    risk_type: str
    severity: str
    title: str
    description: str
    room_id: Optional[str] = None
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None
    status: str = "ACTIVE"
    provenance: Provenance = Provenance.ACTUAL
    action_type: str
    action_title: str
    action_details: str
    auto_executed: bool = False
    action_status: str = "PENDING"
    executed_at: Optional[str] = None
    execution_log: Optional[str] = None

class AlertsSummary(BaseModel):
    total_active: int
    critical_count: int
    high_count: int
    auto_execute_enabled: bool

class AlertsResponse(BaseModel):
    alerts: List[RiskAlertItem]
    summary: AlertsSummary

class ExecuteActionRequest(BaseModel):
    actor: str = "facility_manager"
    notes: Optional[str] = None

class DismissAlertRequest(BaseModel):
    reason: Optional[str] = "Dismissed by facility manager"

class AlertConfigRequest(BaseModel):
    auto_execute: Optional[bool] = None
    overcrowding_threshold_pct: Optional[float] = None
    peak_demand_threshold_kw: Optional[float] = None

class SimulateIncidentRequest(BaseModel):
    incident_type: str = "overcrowding"
    room_id: Optional[str] = "202"
    custom_metric: Optional[float] = None
