import pytest
from backend.services.consolidation.solver import can_assign, run_roomwise_optimization, load_constraints

def test_consolidation_constraints():
    constraints = load_constraints()
    margin = 0.10
    
    # Target room: Classroom 201 (capacity 50, accessible, projector/whiteboard)
    target_room = {
        "id": "201",
        "name": "Classroom 201",
        "floor": 2,
        "capacity": 50,
        "accessible": True,
        "equipment": ["projector", "whiteboard"]
    }
    
    # 1. Capacity Constraint test
    # Class with 48 enrolled: 48 * 1.10 = 52.8 > 50 -> must fail
    big_class = {
        "id": "test_big",
        "course_code": "BIG101",
        "start_hour": 10,
        "end_hour": 12,
        "enrolled": 48,
        "effective_attendance": 48,
        "required_equipment": ["projector"],
        "accessibility_needed": False,
        "instructor": "Dr. Big",
        "locked": False
    }
    feasible, passed, failed = can_assign(big_class, target_room, {}, margin, constraints)
    assert not feasible
    assert any("Capacity breached" in f for f in failed)
    
    # 2. Equipment Constraint test
    # Class requiring computers in a general classroom without computers -> must fail
    lab_class = {
        "id": "test_lab",
        "course_code": "LAB101",
        "start_hour": 10,
        "end_hour": 12,
        "enrolled": 20,
        "effective_attendance": 20,
        "required_equipment": ["computers"],
        "accessibility_needed": False,
        "instructor": "Dr. Lab",
        "locked": False
    }
    feasible, passed, failed = can_assign(lab_class, target_room, {}, margin, constraints)
    assert not feasible
    assert any("Missing required equipment" in f for f in failed)
    
    # 3. Accessibility Constraint test
    inaccessible_room = dict(target_room)
    inaccessible_room["accessible"] = False
    acc_class = {
        "id": "test_acc",
        "course_code": "ACC101",
        "start_hour": 10,
        "end_hour": 12,
        "enrolled": 20,
        "effective_attendance": 20,
        "required_equipment": ["projector"],
        "accessibility_needed": True,
        "instructor": "Dr. Access",
        "locked": False
    }
    feasible, passed, failed = can_assign(acc_class, inaccessible_room, {}, margin, constraints)
    assert not feasible
    assert any("Accessibility requirement violated" in f for f in failed)
    
    # 4. Locked class constraint test
    locked_class = {
        "id": "test_lock",
        "course_code": "LCK101",
        "room_id": "101",
        "start_hour": 10,
        "end_hour": 12,
        "enrolled": 20,
        "effective_attendance": 20,
        "locked": True
    }
    feasible, passed, failed = can_assign(locked_class, target_room, {}, margin, constraints)
    assert not feasible
    assert any("is locked" in f for f in failed)
    
    # 5. Slot non-overlap constraint test (no double booking)
    existing_schedule = {
        "201": [{
            "id": "existing_c1",
            "course_code": "EX101",
            "start_hour": 10,
            "end_hour": 12,
            "instructor": "Dr. Other"
        }]
    }
    overlapping_class = {
        "id": "test_overlap",
        "course_code": "OV101",
        "start_hour": 11,
        "end_hour": 13,
        "enrolled": 20,
        "effective_attendance": 20,
        "required_equipment": ["projector"],
        "instructor": "Dr. New",
        "locked": False
    }
    feasible, passed, failed = can_assign(overlapping_class, target_room, existing_schedule, margin, constraints)
    assert not feasible
    assert any("Slot collision" in f for f in failed)
    
    # 6. Compatibility-group sharing test (sections allowed to share if explicitly marked)
    compatible_class = {
        "id": "test_compat",
        "course_code": "CS101B",
        "start_hour": 10,
        "end_hour": 12,
        "enrolled": 15,
        "effective_attendance": 15,
        "required_equipment": ["projector"],
        "instructor": "Dr. Other",
        "compatibility_group": "CS101_GRP",
        "locked": False
    }
    existing_schedule_compat = {
        "201": [{
            "id": "existing_c1",
            "course_code": "CS101A",
            "start_hour": 10,
            "end_hour": 12,
            "instructor": "Dr. Other",
            "compatibility_group": "CS101_GRP"
        }]
    }
    feasible, passed, failed = can_assign(compatible_class, target_room, existing_schedule_compat, margin, constraints)
    assert feasible
    assert any("compatibility constraint passed" in p for p in passed)

def test_roomwise_optimization_run():
    plan = run_roomwise_optimization(day="Monday", capacity_margin=0.10, solver_type="heuristic")
    assert "id" in plan
    assert plan["status"] == "pending_approval"
    assert plan["baseline_kwh"] > 0
    assert plan["optimized_kwh"] <= plan["baseline_kwh"]
    assert plan["savings_kwh"] >= 0
    assert plan["robustness_score"] >= 0
    # Provenance badge
    assert plan["provenance"] == "ESTIMATED"

def test_compare_heuristic_and_exact_solvers():
    h_plan = run_roomwise_optimization(day="Monday", capacity_margin=0.10, solver_type="heuristic")
    e_plan = run_roomwise_optimization(day="Monday", capacity_margin=0.10, solver_type="exact")
    
    # Both must find non-negative savings
    assert h_plan["savings_kwh"] >= 0
    assert e_plan["savings_kwh"] >= 0
    
    # Exact solver discovers global optimal schedule (savings >= heuristic savings)
    assert e_plan["savings_kwh"] >= h_plan["savings_kwh"]
    
    # Verify that all moves generated by both solvers strictly respect constraints
    for m in h_plan["moves"]:
        assert len(m["checks_passed"]) > 0
    for m in e_plan["moves"]:
        assert len(m["checks_passed"]) > 0
