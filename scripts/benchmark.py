import urllib.request
import time
import json
import statistics
import sys

BASE = "http://127.0.0.1:8000"

ENDPOINTS = [
    ("GET", "/health", None),
    ("GET", "/rooms", None),
    ("GET", "/timetable", None),
    ("GET", "/energy", None),
    ("GET", "/tariff", None),
    ("GET", "/weather", None),
    ("GET", "/iaq", None),
    ("GET", "/fleet", None),
    ("GET", "/alerts", None),
    ("POST", "/optimize", {"day": "Monday"}),
    ("GET", "/solar", None),
    ("GET", "/anomalies", None),
    ("GET", "/anomalies/summary", None),
    ("GET", "/maintenance", None),
    ("GET", "/forecast", None),
    ("GET", "/esg-carbon", None),
    ("GET", "/benchmarking", None),
    ("GET", "/comfort-matrix", None),
    ("GET", "/budget", None),
    ("GET", "/smart-schedule", None),
    ("POST", "/copilot/chat", {"query": "What is our current EUI rating?"}),
    ("GET", "/export/audit-report", None),
]

def run_benchmark(n_runs=5):
    print("=" * 86, flush=True)
    print(f"VERDANT ENTERPRISE API LATENCY & EFFICIENCY BENCHMARK ({n_runs} runs per endpoint)", flush=True)
    print("=" * 86, flush=True)
    print(f"{'Endpoint':<34} | {'Avg (ms)':<9} | {'Median':<9} | {'Min':<8} | {'Max':<8} | {'Status'}", flush=True)
    print("-" * 86, flush=True)
    
    total_samples = []
    
    for method, path, body in ENDPOINTS:
        url = f"{BASE}{path}"
        headers = {}
        data = None
        if body:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            
        latencies = []
        statuses = []
        
        for _ in range(n_runs):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    _ = resp.read()
                    statuses.append(resp.status)
            except Exception as e:
                statuses.append(str(e)[:15])
            lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)
            
        avg_lat = statistics.mean(latencies)
        med_lat = statistics.median(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        status_str = f"HTTP {statuses[0]}" if isinstance(statuses[0], int) else statuses[0]
        
        total_samples.extend(latencies)
        print(f"{method} {path:<30} | {avg_lat:7.2f} ms | {med_lat:7.2f} ms | {min_lat:6.2f} ms | {max_lat:6.2f} ms | {status_str}", flush=True)
        
    print("-" * 86, flush=True)
    print(f"Overall Median: {statistics.median(total_samples):.2f} ms | Overall Mean: {statistics.mean(total_samples):.2f} ms", flush=True)
    print("=" * 86, flush=True)

if __name__ == "__main__":
    run_benchmark(5)
