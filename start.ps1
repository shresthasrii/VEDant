# VERDANT - One Command Launcher
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";$env:LOCALAPPDATA\Programs\Ollama"
$env:PYTHONPATH = "."

Write-Host "==========================================================" -ForegroundColor DarkGreen
Write-Host "  VERDANT · Green Building Intelligence" -ForegroundColor Green
Write-Host "  See the building. Understand the energy. Optimize the future." -ForegroundColor DarkGray
Write-Host "==========================================================" -ForegroundColor DarkGreen

# Check if Ollama is running
$ollamaProc = Get-Process ollama -ErrorAction SilentlyContinue
if (-not $ollamaProc) {
    Write-Host "[1/3] Starting local Ollama service in background..." -ForegroundColor Cyan
    Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
} else {
    Write-Host "[1/3] Local Ollama service is already running." -ForegroundColor Cyan
}

# Run seed check
Write-Host "[2/3] Verifying database and room models..." -ForegroundColor Cyan
python -m backend.seed.generator

# Launch FastAPI Application
Write-Host "[3/3] Starting VERDANT Web Platform on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
