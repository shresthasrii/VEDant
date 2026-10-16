import urllib.request
import urllib.error
import urllib.parse
import json
import time
import sys
import concurrent.futures
from typing import Dict, Any, List, Tuple

BASE = "http://127.0.0.1:8000"

def log_test(category: str, name: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"[{status}] {category:<20} | {name:<35} | {detail}")

def test_rest_endpoints() -> Tuple[int, int]:
    print("\n" + "="*80)
    print("STAGE 1: COMPREHENSIVE ENDPOINT VERIFICATION")
    print("="*80)
    
    endpoints = [
        ("GET", "/health", 200, ["status", "version"]),
        ("GET", "/rooms", 200, None), # list
        ("GET", "/rooms/101", 200, ["id", "name", "capacity", "hvac_kw"]),
        ("GET", "/timetable", 200, ["classes", "total_classes"]),
        ("GET", "/energy", 200, ["scenario", "hourly_kw"]),
        ("GET", "/occupancy", 200, ["readings"]),
        ("GET", "/tariff", 200, ["baseline", "optimized", "impact"]),
        ("GET", "/weather", 200, ["location", "current_temperature_c"]),
        ("GET", "/iaq", 200, ["standard", "compliance_pct", "building_avg_co2_ppm"]),
        ("GET", "/iaq/202", 200, ["room_id", "occupants", "co2_ppm"]),
        ("GET", "/fleet", 200, ["fleet_size", "online_count", "fleet_health_score_pct"]),
        ("GET", "/alerts", 200, ["alerts", "summary"]),
        ("POST", "/optimize", 200, ["id", "savings_kwh", "moves"], {"day": "Monday", "capacity_margin": 0.1}),
        ("POST", "/simulate", 200, ["baseline", "optimized", "impact"], {"hvac_setpoint": 24.0, "lighting_dim": True}),
        ("POST", "/advisor/explain", 200, ["summary", "key_findings", "faculty_notice_draft"], {}),
        ("GET", "/sandbox", 200, ["active", "drill_type", "title"]),
        ("POST", "/sandbox/drill", 200, ["active", "drill_type"], {"drill_type": "RESET"}),
        ("GET", "/solar", 200, ["system", "hourly", "daily"]),
        ("GET", "/anomalies", 200, ["energy", "occupancy"]),
        ("GET", "/anomalies/summary", 200, ["total_anomalies", "health_score"]),
        ("GET", "/maintenance", 200, ["fleet_health_score", "equipment"]),
        ("GET", "/forecast", 200, ["campus_next_1h_headcount", "room_forecasts"]),
        ("GET", "/esg-carbon", 200, ["summary", "scope_1", "scope_2", "scope_3"]),
        ("GET", "/benchmarking", 200, ["eui", "certifications", "national_standing"]),
        ("GET", "/comfort-matrix", 200, ["building_ieq_index", "rating"]),
        ("GET", "/budget", 200, ["budget_period", "mtd_actuals", "variance"]),
        ("GET", "/smart-schedule", 200, ["timetable_efficiency_score", "top_recommendations"]),
        ("POST", "/copilot/chat", 200, ["reply", "mode"], {"prompt": "What is our current substation peak load?"}),
        ("GET", "/export/audit-report", 200, None),
    ]
    
    passed_count = 0
    failed_count = 0
    
    for item in endpoints:
        method = item[0]
        path = item[1]
        expected_status = item[2]
        required_keys = item[3]
        payload = item[4] if len(item) > 4 else None
        
        url = f"{BASE}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                body = resp.read()
                if resp.status == expected_status:
                    if required_keys:
                        data_json = json.loads(body.decode("utf-8"))
                        missing = [k for k in required_keys if k not in data_json]
                        if not missing:
                            log_test("ENDPOINT", f"{method} {path}", True, f"{elapsed_ms:.1f}ms | HTTP {resp.status}")
                            passed_count += 1
                        else:
                            log_test("ENDPOINT", f"{method} {path}", False, f"Missing keys: {missing}")
                            failed_count += 1
                    else:
                        log_test("ENDPOINT", f"{method} {path}", True, f"{elapsed_ms:.1f}ms | HTTP {resp.status} Valid Payload")
                        passed_count += 1
                else:
                    log_test("ENDPOINT", f"{method} {path}", False, f"Expected {expected_status}, got {resp.status}")
                    failed_count += 1
        except urllib.error.HTTPError as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if e.code == expected_status:
                log_test("ENDPOINT", f"{method} {path}", True, f"{elapsed_ms:.1f}ms | Expected HTTP {e.code}")
                passed_count += 1
            else:
                log_test("ENDPOINT", f"{method} {path}", False, f"HTTP Error {e.code}: {e.read().decode('utf-8')[:80]}")
                failed_count += 1
        except Exception as e:
            log_test("ENDPOINT", f"{method} {path}", False, f"Exception: {str(e)[:80]}")
            failed_count += 1
            
    return passed_count, failed_count

def test_edge_cases() -> Tuple[int, int]:
    print("\n" + "="*80)
    print("STAGE 2: EDGE-CASE, BOUNDARY & EXCEPTION TESTING")
    print("="*80)
    
    edge_cases = [
        # (method, path, body, expected_status, test_name)
        ("GET", "/rooms/999", None, 404, "Non-existent room returns 404"),
        ("GET", "/iaq/999", None, 404, "Non-existent IAQ room returns 404"),
        ("POST", "/copilot/chat", {"query": ""}, 400, "Empty Copilot query returns 400"),
        ("POST", "/copilot/chat", {}, 400, "Missing Copilot query returns 400"),
        ("POST", "/sandbox/drill", {"drill_type": "INVALID_DRILL"}, 400, "Invalid drill type handled with 400"),
        ("POST", "/fleet/999/toggle-fault", None, 404, "Non-existent sensor toggle returns 404"),
        ("POST", "/alerts/alert_nonexistent_xyz/execute", None, 404, "Execute invalid alert returns 404"),
        ("POST", "/alerts/alert_nonexistent_xyz/dismiss", None, 404, "Dismiss invalid alert returns 404"),
        ("POST", "/ingest/occupancy", {"room_id": "202", "count": 25, "source": "camera", "confidence": 0.95}, 200, "Valid camera ingestion succeeds"),
        ("POST", "/ingest/occupancy", {"room_id": "999", "count": 10}, 404, "Ingest to non-existent room returns 404"),
        ("POST", "/ingest/occupancy", {"room_id": "202", "count": -5}, 422, "Negative occupant count rejected (422)"),
    ]
    
    passed_count = 0
    failed_count = 0
    
    for method, path, payload, exp_status, test_name in edge_cases:
        url = f"{BASE}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == exp_status:
                    log_test("EDGE CASE", test_name, True, f"HTTP {resp.status} as expected")
                    passed_count += 1
                else:
                    log_test("EDGE CASE", test_name, False, f"Expected {exp_status}, got HTTP {resp.status}")
                    failed_count += 1
        except urllib.error.HTTPError as e:
            if e.code == exp_status:
                log_test("EDGE CASE", test_name, True, f"HTTP {e.code} as expected")
                passed_count += 1
            else:
                log_test("EDGE CASE", test_name, False, f"Expected HTTP {exp_status}, got HTTP {e.code} ({e.read().decode('utf-8')[:60]})")
                failed_count += 1
        except Exception as e:
            log_test("EDGE CASE", test_name, False, f"Exception: {str(e)[:60]}")
            failed_count += 1
            
    return passed_count, failed_count

def test_concurrency_and_load(concurrency=15, total_requests=60) -> Tuple[int, int]:
    print("\n" + "="*80)
    print(f"STAGE 3: HIGH CONCURRENCY LOAD TEST ({concurrency} workers, {total_requests} requests)")
    print("="*80)
    
    test_urls = [
        f"{BASE}/energy",
        f"{BASE}/rooms",
        f"{BASE}/tariff",
        f"{BASE}/weather",
        f"{BASE}/solar",
        f"{BASE}/comfort-matrix",
        f"{BASE}/benchmarking",
        f"{BASE}/maintenance"
    ]
    
    def fetch_url(url):
        t0 = time.perf_counter()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            _ = r.read()
            return r.status, (time.perf_counter() - t0) * 1000.0

    urls_to_run = [test_urls[i % len(test_urls)] for i in range(total_requests)]
    
    t_start = time.perf_counter()
    successes = 0
    failures = 0
    latencies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(fetch_url, u): u for u in urls_to_run}
        for future in concurrent.futures.as_completed(futures):
            try:
                status, lat = future.result()
                if status == 200:
                    successes += 1
                    latencies.append(lat)
                else:
                    failures += 1
            except Exception as e:
                failures += 1
                
    total_time = time.perf_counter() - t_start
    rps = total_requests / total_time if total_time > 0 else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    min_lat = min(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0
    
    passed = failures == 0
    log_test("CONCURRENCY", f"{total_requests} reqs @ {concurrency} threads", passed, 
             f"Success: {successes}/{total_requests} | {rps:.1f} req/s | Avg: {avg_lat:.1f}ms (Min: {min_lat:.1f}ms, Max: {max_lat:.1f}ms)")
    
    return successes, failures

def test_database_integrity() -> bool:
    print("\n" + "="*80)
    print("STAGE 4: SQLITE DATABASE INTEGRITY & INDEXING AUDIT")
    print("="*80)
    
    import sqlite3
    conn = sqlite3.connect("data/verdant.db")
    cursor = conn.cursor()
    
    # Check integrity
    cursor.execute("PRAGMA integrity_check;")
    res = cursor.fetchone()[0]
    log_test("DATABASE", "PRAGMA integrity_check", res == "ok", f"Result: {res}")
    
    # Check WAL mode
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0].lower()
    log_test("DATABASE", "PRAGMA journal_mode (WAL)", mode == "wal", f"Mode: {mode.upper()}")
    
    # Check table row counts
    tables = ["rooms", "classes", "energy_readings", "occupancy_readings", "plans", "risk_alerts"]
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {t};")
        cnt = cursor.fetchone()[0]
        log_test("DATABASE", f"Table '{t}' record count", cnt > 0, f"{cnt:,} records")
        
    conn.close()
    return res == "ok"

if __name__ == "__main__":
    t_total_start = time.perf_counter()
    p1, f1 = test_rest_endpoints()
    p2, f2 = test_edge_cases()
    p3, f3 = test_concurrency_and_load(15, 60)
    db_ok = test_database_integrity()
    
    t_elapsed = time.perf_counter() - t_total_start
    print("\n" + "="*80)
    print(f"DEEP DIVE AUDIT SUMMARY (Completed in {t_elapsed:.2f}s)")
    print(f"Total Endpoint Tests:     {p1} Passed, {f1} Failed")
    print(f"Total Edge-Case Tests:    {p2} Passed, {f2} Failed")
    print(f"Concurrency Load Tests:   {p3} Passed, {f3} Failed")
    print(f"Database Integrity Check: {'PASSED' if db_ok else 'FAILED'}")
    print("="*80)
    
    sys.exit(f1 + f2 + (0 if db_ok else 1))
