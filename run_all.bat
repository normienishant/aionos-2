@echo off
REM ============================================================
REM  SkyLine Assist - ONE-COMMAND RUN (Windows)
REM  Usage:  run_all.bat
REM  Starts backend (FastAPI :8000) + frontend (Next.js :3000)
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo [1/5] Checking prerequisites...
where python >nul 2>&1 || (echo ERROR: Python not found. Install Python 3.11+ first. & pause & exit /b 1)
where node >nul 2>&1 || (echo ERROR: Node.js not found. Install Node 18+ first. & pause & exit /b 1)

echo [2/5] Setting up Python backend...
if not exist "backend\.venv" (
  python -m venv backend\.venv
  call backend\.venv\Scripts\activate.bat
  python -m pip install --upgrade pip --quiet
  pip install -r backend\requirements.txt --quiet
) else (
  call backend\.venv\Scripts\activate.bat
)

if not exist "backend\.env" (
  copy backend\.env.example backend\.env >nul
  echo.
  echo   Created backend\.env - add your GEMINI_API_KEY to it for the full LLM agent.
  echo   Without a key the demo still runs in offline fallback mode.
  echo.
)

echo [3/5] Installing frontend dependencies...
if not exist "frontend\node_modules" (
  pushd frontend && call npm install && popd
)

echo [4/5] Seeding database and starting backend on http://localhost:8000 ...
start "SkyLine API (keep this window open)" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\activate.bat && python -m uvicorn main:app --port 8000"

echo [5/5] Starting frontend on http://localhost:3000 ...
start "SkyLine Web (keep this window open)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

timeout /t 6 >nul
start http://localhost:3000

echo.
echo ============================================================
echo  SkyLine Assist is starting:
echo    Chat:   http://localhost:3000
echo    Audit:  http://localhost:3000/audit
echo    API:    http://localhost:8000/docs
echo  Two windows opened - keep them open while demoing.
echo  Press any key to close THIS launcher (servers keep running).
echo ============================================================
pause >nul
