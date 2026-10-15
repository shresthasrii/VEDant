"""
VERDANT Computer Vision Worker (cv/worker.py)
Privacy Guarantee:
- Pretrained person detection ONLY (YOLO person class: class 0).
- NO face recognition or identity matching.
- Frames are processed in memory and immediately discarded.
- Transmits ONLY {room_id, timestamp, count, confidence} to the backend.
- Supports: Webcam (index 0), RTSP / IP camera URL, video clip file, or synthetic live streamer.
"""

import os
import sys
import time
import json
import argparse
import random
from datetime import datetime

try:
    import requests
except ImportError:
    print("[Error] 'requests' package required. Run: pip install requests")
    sys.exit(1)

def run_worker(room_id: str, source: str, backend_url: str, fps: float = 1.0):
    print(f"==================================================")
    print(f"VERDANT CV Occupancy Worker")
    print(f"Target Room: {room_id}")
    print(f"Video Source: {source}")
    print(f"Backend Ingest: {backend_url}")
    print(f"Privacy: Processed locally, counts only, 0 frames saved.")
    print(f"==================================================")
    
    # Try importing Ultralytics YOLO & OpenCV if available
    yolo_model = None
    cv2 = None
    use_yolo = False
    
    if source.isdigit() or source.startswith("rtsp://") or source.startswith("http://") or os.path.exists(source):
        try:
            import cv2 as _cv2
            from ultralytics import YOLO
            cv2 = _cv2
            print("[CV Worker] Loading YOLO model (yolo26n.pt / yolo11n.pt)...")
            try:
                yolo_model = YOLO("yolo26n.pt")
            except Exception:
                yolo_model = YOLO("yolo11n.pt")
            use_yolo = True
            print("[CV Worker] YOLO person-detection model loaded successfully!")
        except Exception as e:
            print(f"[CV Worker Note] Ultralytics/OpenCV not active ({e}). Using robust synthetic camera feed.")
            use_yolo = False

    cap = None
    if use_yolo and cv2:
        src_val = int(source) if source.isdigit() else source
        cap = cv2.VideoCapture(src_val)
        if not cap.isOpened():
            print(f"[CV Worker Warning] Could not open camera {source}. Switching to synthetic feed.")
            use_yolo = False

    while True:
        ts = datetime.now().isoformat()
        count = 0
        conf = 0.95
        
        if use_yolo and cap and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                # Loop video if file
                if not source.isdigit():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    time.sleep(1.0)
                    continue
                    
            # Run YOLO person detection (class 0 only)
            results = yolo_model(frame, classes=[0], verbose=False)
            boxes = results[0].boxes
            count = len(boxes)
            conf = float(boxes.conf.mean()) if count > 0 else 1.0
            del frame  # Privacy: Discard raw frame immediately
        else:
            # Synthetic camera stream (simulating student movement)
            hour = datetime.now().hour
            base_occupants = 24 if (9 <= hour < 17) else 4
            jitter = random.randint(-2, 3)
            count = max(0, base_occupants + jitter)
            conf = round(random.uniform(0.92, 0.99), 2)

        payload = {
            "room_id": room_id,
            "timestamp": ts,
            "count": count,
            "confidence": conf,
            "source": "camera" if use_yolo else "simulated"
        }
        
        try:
            res = requests.post(f"{backend_url}/ingest/occupancy", json=payload, timeout=3.0)
            if res.status_code == 200:
                print(f"[{ts[11:19]}] Ingested: Room {room_id} -> {count} people (conf: {conf:.2f}, src: {payload['source']})")
            else:
                print(f"[Warning] Ingest returned {res.status_code}")
        except Exception as e:
            print(f"[Error connecting to backend] {e}")

        time.sleep(1.0 / max(0.1, fps))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VERDANT Person-Count Worker")
    parser.add_argument("--room", default="202", help="Room ID to count for (default: 202)")
    parser.add_argument("--source", default="synthetic", help="Webcam index (0), RTSP/HTTP URL, video clip file, or 'synthetic'")
    parser.add_argument("--backend", default="http://127.0.0.1:8000", help="VERDANT backend base URL")
    parser.add_argument("--fps", type=float, default=1.0, help="Inference frequency (default: 1 count/sec)")
    args = parser.parse_args()
    
    run_worker(args.room, args.source, args.backend, args.fps)
