# VERDANT · Green Building Intelligence
> **Tagline**: *See the building. Understand the energy. Optimize the future.*

[![Tests](https://img.shields.io/badge/tests-13%20passed%2C%20100%25-brightgreen)]()
[![Backend](https://img.shields.io/badge/FastAPI-Python%203.10%2B-blue)]()
[![Model](https://img.shields.io/badge/Local%20LLM-Ollama%20llama3.2-orange)]()
[![Architecture](https://img.shields.io/badge/Digital%20Twin-3D%20Isometric%20%2B%202D%20Fallback-purple)]()

---

## 🏛️ Executive Summary

**VERDANT** is an AI-powered smart energy optimization and green building digital twin platform designed specifically for academic institutions and educational campuses. It solves two hackathon challenges simultaneously:
- **PS03**: Sustainable Energy Monitoring and Optimization
- **PS04**: Green Building Digital Twin

Its signature feature, **RoomWise™**, moves beyond traditional setback thermostats: instead of merely turning down AC in sparse rooms, it finds mathematically feasible class-to-room consolidations so that **entire rooms (and their chillers, lights, and projectors) remain completely powered OFF all day**.

---

## 📋 PS03 & PS04 Requirement-Traceability Matrix

| Requirement Area | Specification | Implementation in VERDANT |
| :--- | :--- | :--- |
| **PS03: CV Monitoring** | Real-time person counting without biometrics | `cv/worker.py` (Ultralytics YOLO person-detection, class 0 only, zero face recognition, zero frame persistence). |
| **PS03: Energy Analytics** | kW demand vs kWh consumption, breakdown by system | `GET /energy` with HVAC, Lighting, and Plug load decomposition. |
| **PS03: Optimization** | Schedule consolidation with constraints | `RoomWise™` engine (`backend/services/consolidation/solver.py`) with 7 hard constraints. |
| **PS04: Digital Twin** | Interactive 3D building model with floor isolation | Isometric 3D SVG digital twin with orbit, zoom, floor isolation, layer toggles (`occ`, `en`, `eff`, `alert`), and `?mode=2d` blueprint fallback. |
| **PS04: Multi-Scenario** | Compare baseline vs optimized vs approved | `POST /simulate` multi-parameter simulator with P10–P90 Monte Carlo ranges. |
| **PS04: Generative AI** | Grounded explanation with zero fabricated metrics | `backend/services/advisor.py` using local `Ollama llama3.2` with deterministic template fallback and automated number verification. |
| **Ground Rule: Provenance** | Badges on every single metric | Provenance tags (`ACTUAL`, `SIMULATED`, `ESTIMATED`) displayed on all UI figures and API responses. |
| **Ground Rule: Safety** | Advisory-only, no live actuator tampering | All optimization outputs marked `pending_approval`. User approvals write to simulated twin state and audit log. |

---

## ⚡ Quickstart (One Command Launch)

### Prerequisites
- Python 3.10+
- Modern Web Browser (Chrome / Edge / Firefox)
- Optional: Local Ollama with `llama3.2` running on port 11434 (automatically integrated)

### 1. Launch the Complete System
Run the launch script from the root directory:

**Windows (PowerShell)**:
```powershell
.\start.ps1
```

Or run directly with Python:
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Access the Application
- **VERDANT Web Application**: [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **2D Blueprint Fallback Mode**: [http://localhost:8000/?mode=2d](http://localhost:8000/?mode=2d)

---

## 👁️ Computer Vision Worker (`cv/worker.py`)

The CV worker runs locally on your machine:
```bash
# Synthetic demo stream (no webcam required):
python cv/worker.py --room 202 --source synthetic

# Using physical webcam:
python cv/worker.py --room 202 --source 0

# Using RTSP / IP Camera stream:
python cv/worker.py --room 202 --source rtsp://192.168.1.100:554/stream1
```

### 🔒 Privacy by Design
1. **No Identification**: Recognizes only general person bounding boxes (COCO class 0).
2. **Zero Storage**: Video frames are processed in memory and immediately discarded.
3. **Data Emitted**: Only `{room_id, timestamp, count, confidence}` is posted to `/ingest/occupancy`.

---

## 🧪 Running the Test Suite

Execute the 12 comprehensive unit and integration tests:
```bash
python -m pytest backend/tests -v
```

Tests cover:
- Energy and emissions math (`kWh * 8.0 = cost`, `kWh * 0.70 = emissions`)
- Zero and missing data handling (offline sensors like Room 303)
- All 7 RoomWise consolidation constraints (capacity, equipment, accessibility, instructor, locked rooms, compatibility groups, slot non-overlap)
- GenAI Advisor number validation
- Main REST API routes

---

## 🎯 Signature Demo Walkthrough (For Hackathon Judges)

1. **Observe Underutilization**:
   - Open **Building Overview** or **Occupancy Intelligence**. Notice that **Seminar Hall (202)** and **Classroom 301** have low average occupancy during typical weekdays.
2. **Navigate to RoomWise™ Engine**:
   - Click **RoomWise™ Engine** on the navigation bar.
   - The solver identifies that relocating *HU102 (Technical Communication)* from Seminar Hall 202 into Classroom 201 allows the entire 4.5 kW HVAC unit of Seminar Hall 202 to remain completely powered off.
   - Every checked constraint (capacity + 10% margin, equipment match, accessibility, instructor travel) is clearly listed.
3. **Explore the Digital Twin**:
   - Open **Digital Twin**. Orbit in 3D around Block A or switch between Occupancy, Energy, and Alerts layers.
4. **Consult the AI Energy Advisor**:
   - Click **Ask AI Advisor to Analyze Plan**.
   - The advisor (powered by local `llama3.2`) provides an evidence-based summary with zero fabricated numbers and drafts a faculty relocation notice ready for approval.
5. **Approve Plan**:
   - Click **Approve & Apply Plan**.
   - The timetable and digital twin update to reflect the consolidated schedule, and the approval is permanently committed to the audit log.
