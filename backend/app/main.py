import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

from backend.db import init_db, get_db
from backend.seed.generator import seed_all
from backend.ws import ws_manager
from backend.services.replay import replay_manager

from backend.app.routers import rooms, occupancy, timetable, consolidation, energy, advisor, export, health, alerts, intelligence, advanced

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure DB and seeds
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM rooms")
        count = cursor.fetchone()[0]
        if count == 0:
            seed_all()
            
    # Start WebSocket batched flusher (4 Hz rate limit)
    flush_task = asyncio.create_task(ws_manager.flush_batches_loop())
    yield
    flush_task.cancel()

app = FastAPI(
    title="VERDANT API",
    description="Green Building Digital Twin & AI Energy Optimization Platform (PS03 & PS04)",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for all local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include Routers
app.include_router(rooms.router)
app.include_router(occupancy.router)
app.include_router(timetable.router)
app.include_router(consolidation.router)
app.include_router(energy.router)
app.include_router(advisor.router)
app.include_router(export.router)
app.include_router(health.router)
app.include_router(alerts.router)
app.include_router(intelligence.router)
app.include_router(advanced.router)

# WebSocket Endpoint (/ws)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot on connect
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rooms")
            rooms_list = [dict(r) for r in cursor.fetchall()]
            
            cursor.execute("SELECT * FROM occupancy_readings ORDER BY id DESC LIMIT 50")
            latest_occ = [dict(o) for o in cursor.fetchall()]

            cursor.execute("SELECT * FROM risk_alerts WHERE status = 'ACTIVE'")
            active_alerts = [dict(a) for a in cursor.fetchall()]
            
        await websocket.send_json({
            "type": "initial_snapshot",
            "rooms": rooms_list,
            "recent_readings": latest_occ,
            "active_alerts": active_alerts,
            "server_time": "2026-10-15T14:15:00"
        })
        
        while True:
            data = await websocket.receive_text()
            # Handle client commands if needed (ping/pong)
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

def get_frontend_index_path() -> Optional[Path]:
    candidates = [
        FRONTEND_DIR / "index.html",
        Path(__file__).resolve().parent.parent.parent / "public" / "index.html",
        Path(__file__).resolve().parent.parent.parent / "index.html",
        Path.cwd() / "frontend" / "index.html",
        Path.cwd() / "public" / "index.html",
        Path.cwd() / "index.html",
        Path("/var/task/frontend/index.html"),
        Path("/var/task/public/index.html"),
        Path("/var/task/index.html"),
        Path(__file__).resolve().parent.parent / "frontend" / "index.html",
        Path(__file__).resolve().parent / "index.html"
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None

@app.get("/", response_class=FileResponse)
@app.get("/index.html", response_class=FileResponse)
async def serve_index():
    path = get_frontend_index_path()
    if path and path.exists():
        return FileResponse(str(path), media_type="text/html")
    # Inline fallback if files were somehow unbundled
    return HTMLResponse("<h1>VERDANT</h1><p>Starting up green building digital twin...</p>", status_code=200)

# Mount frontend directory for single-command serving
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend_static")
