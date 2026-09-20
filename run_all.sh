#!/usr/bin/env bash
# ============================================================
#  SkyLine Assist - ONE-COMMAND RUN (macOS / Linux)
#  Usage:  ./run_all.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo "[1/5] Checking prerequisites..."
command -v python3 >/dev/null || { echo "ERROR: python3 not found"; exit 1; }
command -v node >/dev/null || { echo "ERROR: node not found"; exit 1; }

echo "[2/5] Setting up Python backend..."
if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install --upgrade pip --quiet
  backend/.venv/bin/pip install -r backend/requirements.txt --quiet
fi

if [ ! -f "backend/.env" ]; then
  cp backend/.env.example backend/.env
  echo "Created backend/.env - add your GEMINI_API_KEY for the full LLM agent (offline fallback works without it)."
fi

echo "[3/5] Installing frontend dependencies..."
if [ ! -d "frontend/node_modules" ]; then
  (cd frontend && npm install)
fi

echo "[4/5] Starting backend on http://localhost:8000 ..."
(cd backend && ./.venv/bin/python -m uvicorn main:app --port 8000 &> /tmp/skyline_api.log &)

echo "[5/5] Starting frontend on http://localhost:3000 ..."
(cd frontend && npm run dev &> /tmp/skyline_web.log &)

sleep 6
echo "============================================================"
echo " SkyLine Assist is running:"
echo "   Chat:   http://localhost:3000"
echo "   Audit:  http://localhost:3000/audit"
echo "   API:    http://localhost:8000/docs"
echo " Logs: /tmp/skyline_api.log and /tmp/skyline_web.log"
echo " Stop with:  pkill -f 'uvicorn main:app' ; pkill -f 'next dev'"
echo "============================================================"
