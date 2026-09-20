# ---------- Stage 1: build the Next.js static site ----------
FROM node:20-alpine AS frontend-build

WORKDIR /app
# Install first so Docker layer-caches node_modules across code changes.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY frontend/ .
# EXPORT=1 -> next.config.mjs switches to output:"export" and writes out/
RUN EXPORT=1 npm run build

# ---------- Stage 2: FastAPI serves API + static site ----------
FROM python:3.11-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# Compiled static site from stage 1 -> served by FastAPI at /
COPY --from=frontend-build /app/out ./frontend/out

EXPOSE 8000
# Render injects $PORT; shell form so the variable expands at runtime.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
