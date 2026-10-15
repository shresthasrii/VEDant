import sqlite3
import json
import os
from pathlib import Path
from contextlib import contextmanager

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "verdant.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
