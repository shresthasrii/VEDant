import pytest
from backend.services.advisor import generate_template_explanation, explain_plan

def test_advisor_template_explanation():
    context = {
        "baseline_kwh": 500.0,
        "optimized_kwh": 410.0,
        "savings_kwh": 90.0,
        "savings_pct": 18.0,
        "empty_rooms_freed": ["Seminar Hall 202"],
        "moves": [{
            "id": "m1",
            "course_code": "HU102",
            "course_name": "Technical Communication",
            "from_room_name": "Seminar Hall 202",
            "to_room_name": "Classroom 201",
            "start_hour": 14,
            "attendance": 22
        }]
    }
    res = generate_template_explanation(context)
    assert res["mode"] == "template explanation (no LLM)"
    assert "90.0" in res["summary"] or "90" in res["summary"]
    assert "18.0" in res["summary"] or "18" in res["summary"]
    assert "faculty_notice_draft" in res
    assert "provenance" in res

def test_advisor_explain_plan():
    context = {
        "baseline_kwh": 480.0,
        "optimized_kwh": 395.0,
        "savings_kwh": 85.0,
        "savings_pct": 17.7,
        "empty_rooms_freed": ["Seminar Hall 202"],
        "moves": []
    }
    res = explain_plan(context)
    assert res is not None
    assert "summary" in res
    assert "key_findings" in res
