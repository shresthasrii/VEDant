import os
import time
import threading
import requests
from fastapi import APIRouter
from backend.db import get_db
from backend.services.llm import get_llm_config

router = APIRouter(prefix="", tags=["health"])

# ── Ollama cache: avoid blocking every /health call ──────────────────────────
_ollama_cache = {"ok": False, "checked_at": 0.0}
_ollama_lock  = threading.Lock()
_OLLAMA_TTL   = 30.0   # re-probe at most every 30 s

def _probe_ollama() -> bool:
    try:
        res = requests.get("http://127.0.0.1:11434/api/tags", timeout=0.5)
        return res.status_code == 200
    except Exception:
        return False

def _get_ollama_status() -> bool:
    now = time.monotonic()
    with _ollama_lock:
        if now - _ollama_cache["checked_at"] < _OLLAMA_TTL:
            return _ollama_cache["ok"]
        # Launch a background probe; return cached value immediately
        def _update():
            result = _probe_ollama()
            with _ollama_lock:
                _ollama_cache["ok"] = result
                _ollama_cache["checked_at"] = time.monotonic()
        threading.Thread(target=_update, daemon=True).start()
        # If first call ever, wait briefly for the initial result
        if _ollama_cache["checked_at"] == 0.0:
            time.sleep(0.55)
            return _ollama_cache["ok"]
        return _ollama_cache["ok"]

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

    ollama_ok = _get_ollama_status()
    llm_cfg = get_llm_config()

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": "1.0.0",
        "database": {"connected": db_ok, "rooms_loaded": rooms_count},
        "groq_cloud_llm": {"available": llm_cfg["has_api_key"], "model": llm_cfg["model"], "provider": "Groq LPU Cloud"},
        "ollama_local_llm": {"available": ollama_ok, "model": "llama3.2"},
        "mode": os.environ.get("MODE", "live"),
        "privacy": {
            "retention": "in-memory only / discarded after counting",
            "face_recognition": False,
            "identification": False
        }
    }
