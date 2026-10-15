import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.db import get_db, init_db
from backend.services.risk import (
    evaluate_reading_risk, scan_facility_risks, execute_containment_action,
    dismiss_alert, get_all_alerts, update_alert_config, trigger_simulated_incident
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    update_alert_config(auto_execute=False, overcrowding_threshold_pct=100.0, peak_demand_threshold_kw=95.0)
    yield

def test_overcrowding_alert_trigger():
    # Room 202 capacity is 60
    # Overcrowding count of 75 (125% capacity)
    alert = evaluate_reading_risk(room_id="202", count=75, provenance="ACTUAL")
    assert alert is not None
    assert alert["risk_type"] == "overcrowding"
    assert alert["severity"] == "CRITICAL"
    assert alert["room_id"] == "202"
    assert alert["status"] == "ACTIVE"
    assert alert["action_type"] == "LOCK_AND_DISPATCH"
    assert "Lock Room 202" in alert["action_title"]

def test_execute_containment_action():
    # Trigger overcrowding
    alert = evaluate_reading_risk(room_id="202", count=70, provenance="ACTUAL")
    alert_id = alert["id"]
    
    # Execute containment action
    result = execute_containment_action(alert_id, actor="facility_director")
    assert result["status"] == "ACTIONED"
    assert result["action_status"] == "EXECUTED"
    assert result["executed_at"] is not None
    assert "facility_director" in result["execution_log"]
    assert "locked" in result["execution_log"].lower()

    # Verify audit log was recorded
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_log WHERE entity_id = ? ORDER BY id DESC LIMIT 1", (alert_id,))
        audit = cursor.fetchone()
        assert audit is not None
        assert audit["user_action"] == "CONTAINMENT_ACTION_EXECUTED"

def test_dismiss_alert():
    alert = evaluate_reading_risk(room_id="202", count=68, provenance="ACTUAL")
    alert_id = alert["id"]
    
    dismissed = dismiss_alert(alert_id, reason="False alarm cleared by steward")
    assert dismissed["status"] == "DISMISSED"
    assert dismissed["action_status"] == "DISMISSED"

def test_autonomous_auto_execute_policy():
    # Enable autonomous mode
    update_alert_config(auto_execute=True)
    
    # Trigger incident
    alert = trigger_simulated_incident("overcrowding", room_id="202", custom_metric=80)
    assert alert is not None
    # In auto-execute mode, alert should be instantly ACTIONED by AUTONOMOUS_POLICY
    assert alert["status"] == "ACTIONED"
    assert alert["action_status"] == "EXECUTED"
    assert alert["auto_executed"] is True
    assert "AUTONOMOUS_POLICY" in alert["execution_log"]

def test_alerts_api_endpoints():
    # 1. GET /alerts
    res = client.get("/alerts")
    assert res.status_code == 200
    data = res.json()
    assert "alerts" in data
    assert "summary" in data

    # 2. POST /alerts/scan
    res = client.post("/alerts/scan")
    assert res.status_code == 200
    scan_data = res.json()
    assert scan_data["status"] == "success"

    # 3. POST /alerts/simulate
    sim_res = client.post("/alerts/simulate", json={"incident_type": "peak_overload", "custom_metric": 105.0})
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    alert_id = sim_data["simulated_alert"]["id"]
    assert "ALT-" in alert_id

    # 4. POST /alerts/{id}/execute
    exec_res = client.post(f"/alerts/{alert_id}/execute", json={"actor": "admin", "notes": "Tested in test suite"})
    assert exec_res.status_code == 200
    assert exec_res.json()["alert"]["status"] == "ACTIONED"

    # 5. GET /alerts/config & POST /alerts/config
    cfg_get = client.get("/alerts/config")
    assert cfg_get.status_code == 200
    
    cfg_post = client.post("/alerts/config", json={"auto_execute": False, "peak_demand_threshold_kw": 92.0})
    assert cfg_post.status_code == 200
    assert cfg_post.json()["config"]["peak_demand_threshold_kw"] == 92.0
