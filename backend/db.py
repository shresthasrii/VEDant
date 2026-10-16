import sqlite3
import json
import os
import shutil
from pathlib import Path
from contextlib import contextmanager

IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

if IS_VERCEL:
    # On Vercel serverless functions, root filesystem is read-only.
    # We copy the bundled, seeded database to /tmp so writes, holds, and WAL journals succeed.
    TMP_DIR = Path("/tmp/verdant_data")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = TMP_DIR / "verdant.db"
    SOURCE_DB = Path(__file__).resolve().parent.parent / "data" / "verdant.db"
    if not DB_PATH.exists() and SOURCE_DB.exists():
        try:
            shutil.copy2(SOURCE_DB, DB_PATH)
        except Exception:
            pass
else:
    DB_DIR = Path(__file__).resolve().parent.parent / "data"
    DB_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = DB_DIR / "verdant.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size=-64000;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Buildings
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS buildings (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            floors_count INTEGER,
            total_spaces INTEGER,
            description TEXT
        )
        """)
        
        # Rooms
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            floor INTEGER NOT NULL,
            type TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            hvac_kw REAL NOT NULL,
            lighting_kw REAL NOT NULL,
            plug_kw REAL NOT NULL,
            accessible INTEGER NOT NULL DEFAULT 1,
            equipment TEXT, -- JSON array
            sensor_offline INTEGER NOT NULL DEFAULT 0,
            pos_3d TEXT     -- JSON object
        )
        """)
        
        # Classes / Timetable
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            section TEXT NOT NULL,
            instructor TEXT NOT NULL,
            day_of_week TEXT NOT NULL,
            start_hour INTEGER NOT NULL,
            end_hour INTEGER NOT NULL,
            enrolled INTEGER NOT NULL,
            room_id TEXT NOT NULL,
            required_equipment TEXT, -- JSON array
            accessibility_needed INTEGER NOT NULL DEFAULT 0,
            compatibility_group TEXT,
            locked INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """)
        
        # Occupancy Readings (with Provenance)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS occupancy_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            hour INTEGER NOT NULL,
            count INTEGER,
            smoothed_count REAL,
            source TEXT NOT NULL, -- 'camera' | 'simulated' | 'unknown'
            confidence REAL NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL, -- 'occupied' | 'unoccupied' | 'high_utilization' | 'offline'
            provenance TEXT NOT NULL DEFAULT 'SIMULATED', -- 'ACTUAL' | 'SIMULATED' | 'ESTIMATED'
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """)

        # Active Room Headcount Holds (Latching)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_holds (
            room_id TEXT PRIMARY KEY,
            count INTEGER NOT NULL,
            smoothed_count REAL NOT NULL,
            hour INTEGER NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            source TEXT NOT NULL DEFAULT 'camera',
            timestamp TEXT NOT NULL,
            held INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """)
        
        # Energy Readings (Hourly breakdown per scenario)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS energy_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT NOT NULL,
            hour INTEGER NOT NULL,
            hvac_kw REAL NOT NULL,
            lighting_kw REAL NOT NULL,
            plug_kw REAL NOT NULL,
            total_kw REAL NOT NULL,
            scenario TEXT NOT NULL, -- 'baseline' | 'optimized' | 'approved'
            provenance TEXT NOT NULL DEFAULT 'ESTIMATED',
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """)
        
        # Plans (RoomWise Optimization results)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            solver TEXT NOT NULL, -- 'heuristic' | 'cp_sat'
            params TEXT, -- JSON object
            status TEXT NOT NULL DEFAULT 'pending_approval', -- 'pending_approval' | 'approved' | 'rejected'
            baseline_kwh REAL NOT NULL,
            optimized_kwh REAL NOT NULL,
            savings_kwh REAL NOT NULL,
            savings_pct REAL NOT NULL,
            p10_savings_kwh REAL NOT NULL,
            p90_savings_kwh REAL NOT NULL,
            robustness_score REAL NOT NULL,
            provenance TEXT NOT NULL DEFAULT 'ESTIMATED'
        )
        """)
        
        # Plan Moves
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_moves (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            class_id TEXT NOT NULL,
            from_room_id TEXT NOT NULL,
            to_room_id TEXT NOT NULL,
            reasons TEXT, -- JSON array
            checks TEXT,   -- JSON object
            status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'approved' | 'rejected'
            FOREIGN KEY(plan_id) REFERENCES plans(id),
            FOREIGN KEY(class_id) REFERENCES classes(id)
        )
        """)
        
        # Recommendations
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id TEXT PRIMARY KEY,
            room_id TEXT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            finding TEXT NOT NULL,
            evidence TEXT NOT NULL,
            suggested_action TEXT NOT NULL,
            impact_kwh REAL NOT NULL,
            impact_pct REAL NOT NULL,
            impact_inr REAL NOT NULL,
            impact_co2 REAL NOT NULL,
            confidence TEXT NOT NULL,
            assumptions TEXT NOT NULL,
            set_params TEXT, -- JSON
            status TEXT NOT NULL DEFAULT 'new' -- 'new' | 'simulated' | 'reviewed' | 'dismissed'
        )
        """)
        
        # Audit Log
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            details TEXT
        )
        """)
        
        # Risk Alerts & Automated Actions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_alerts (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            risk_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            room_id TEXT,
            metric_value REAL,
            threshold_value REAL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            provenance TEXT NOT NULL DEFAULT 'ACTUAL',
            action_type TEXT NOT NULL,
            action_title TEXT NOT NULL,
            action_details TEXT NOT NULL,
            auto_executed INTEGER NOT NULL DEFAULT 0,
            action_status TEXT NOT NULL DEFAULT 'PENDING',
            executed_at TEXT,
            execution_log TEXT
        )
        """)

        # Schedule Requests & Timetable Workflows
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule_requests (
            id TEXT PRIMARY KEY,
            creator_name TEXT NOT NULL,
            course_code TEXT NOT NULL,
            course_name TEXT NOT NULL,
            section TEXT NOT NULL DEFAULT 'A',
            instructor TEXT NOT NULL,
            room_id TEXT NOT NULL,
            day_of_week TEXT NOT NULL DEFAULT 'Monday',
            preferred_start_hour INTEGER NOT NULL,
            duration_hours INTEGER NOT NULL DEFAULT 2,
            enrolled INTEGER NOT NULL DEFAULT 20,
            required_equipment TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            allocated_start_hour INTEGER,
            allocated_end_hour INTEGER,
            allocated_room_id TEXT,
            notification_message TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by TEXT,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        )
        """)

        # ── Performance indexes ───────────────────────────────────────────────
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_occ_room_id   ON occupancy_readings(room_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_occ_room_hour ON occupancy_readings(room_id, hour);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status  ON risk_alerts(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_energy_room_hour ON energy_readings(room_id, hour);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_classes_room_day ON classes(room_id, day_of_week);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON schedule_requests(status);")

