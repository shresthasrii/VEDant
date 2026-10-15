@echo off
set PYTHONPATH=.
echo ==========================================================
echo   VERDANT - Green Building Intelligence
echo   See the building. Understand the energy. Optimize the future.
echo ==========================================================
python -m backend.seed.generator
echo Starting VERDANT on http://localhost:8000 ...
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
pause
