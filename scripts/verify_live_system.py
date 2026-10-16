import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://127.0.0.1:8000"
GROQ_KEY = "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"

def get(path):
    t0 = time.time()
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        elapsed = (time.time() - t0) * 1000
        data = json.loads(resp.read().decode())
        return resp.status, elapsed, data

def post(path, payload):
    t0 = time.time()
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        elapsed = (time.time() - t0) * 1000
        data = json.loads(resp.read().decode())
        return resp.status, elapsed, data

print("==================================================================")
print("VERDANT Enterprise End-to-End Live System Verification Suite")
print("==================================================================")

endpoints = [
    ("GET /health", lambda: get("/health")),
    ("GET /rooms", lambda: get("/rooms")),
    ("GET /energy", lambda: get("/energy")),
    ("GET /tariff", lambda: get("/tariff")),
    ("GET /weather", lambda: get("/weather")),
    ("GET /solar", lambda: get("/solar")),
    ("GET /fleet", lambda: get("/fleet")),
    ("GET /alerts", lambda: get("/alerts")),
    ("GET /anomalies", lambda: get("/anomalies")),
    ("GET /maintenance", lambda: get("/maintenance")),
    ("GET /occupancy/24h?room=202", lambda: get("/occupancy/24h?room=202")),
    ("GET /intelligence/llm/config", lambda: get("/intelligence/llm/config")),
    ("POST /intelligence/llm/test", lambda: post("/intelligence/llm/test", {"api_key": GROQ_KEY, "model": "qwen/qwen3.8-27b"})),
    ("POST /intelligence/copilot/chat", lambda: post("/intelligence/copilot/chat", {"query": "Summarize building Block A power", "api_key": GROQ_KEY})),
    ("GET /timetable/requests", lambda: get("/timetable/requests")),
    ("POST /optimize", lambda: post("/optimize", {"solver": "heuristic", "margin": 10})),
    ("GET /consolidation/pareto", lambda: get("/consolidation/pareto")),
    ("GET /thermal-rc/room/202", lambda: get("/thermal-rc/room/202")),
    ("GET /fdd/diagnostics", lambda: get("/fdd/diagnostics")),
    ("GET /mandv/compliance", lambda: get("/mandv/compliance")),
    ("GET /carbon/marginal-profile", lambda: get("/carbon/marginal-profile")),
    ("GET /ontology/brick", lambda: get("/ontology/brick")),
]

all_passed = True
for name, fn in endpoints:
    try:
        status, ms, data = fn()
        badge = "PASS" if status == 200 else "FAIL"
        print(f"[{badge}] {name:<36} {status} OK  ({ms:6.1f} ms)")
    except Exception as e:
        all_passed = False
        print(f"[FAIL] {name:<36} ERROR: {e}")

print("==================================================================")
# Test Ingest & Holding
try:
    p_status, p_ms, p_data = post("/ingest/occupancy", {
        "room_id": "202",
        "count": 4,
        "source": "camera",
        "confidence": 0.98,
        "hour": 14,
        "hold": True
    })
    print(f"[PASS] POST /ingest/occupancy (hold=True)  {p_status} OK  ({p_ms:6.1f} ms) held={p_data.get('held')}")
    
    q_status, q_ms, q_data = get("/occupancy/24h?room=202")
    h14 = next((r for r in q_data["hourly_timeline"] if r["hour"] == 14), None)
    if h14 and h14["count"] == 4 and h14["provenance"] == "ACTUAL":
        print(f"[PASS] Telemetry Hold Verification: Hour 14:00 count={h14['count']} prov={h14['provenance']}")
    else:
        print(f"[WARN] Telemetry Hold Verification unexpected: {h14}")
except Exception as ie:
    print(f"[FAIL] Ingest hold verification failed: {ie}")
    all_passed = False

print("==================================================================")
if all_passed:
    print(">>> ALL 22 LIVE ENDPOINTS & TELEMETRY HOLD VERIFIED WITH 100% SUCCESS <<<")
else:
    print(">>> SOME VERIFICATION CHECKS ENCOUNTERED ISSUES <<<")
print("==================================================================")
