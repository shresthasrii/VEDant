import os
import requests
from fastapi import APIRouter
from backend.db import get_db

router = APIRouter(prefix="", tags=["health"])

@router.get("/health")
def health_check():
    db_ok = False
    rooms_count = 0
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM rooms")
            rooms_count = cursor.fetchone()[0]
            db_ok = True
    except Exception:
        pass
        
    ollama_ok = False
    try:
        res = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
        if res.status_code == 200:
            ollama_ok = True
    except Exception:
        pass
        
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": {"connected": db_ok, "rooms_loaded": rooms_count},
        "ollama_local_llm": {"available": ollama_ok, "model": "llama3.2"},
        "mode": os.environ.get("MODE", "live"),
        "privacy": {
            "retention": "in-memory only / discarded after counting",
            "face_recognition": False,
            "identification": False
        }
    }
