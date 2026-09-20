"""FastAPI entrypoint.

Run:  uvicorn main:app --reload --port 8000     (from backend/)
Auto-seeds the database on startup if empty.

Single-service deploy: if ../frontend/out/ exists (built with EXPORT=1), the
compiled Next.js static site is served from this same app — one container,
one origin, no CORS, no proxy. In dev the out/ folder simply doesn't exist
and everything works exactly as before.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import DATABASE_URL, FRONTEND_ORIGIN
from app.database import Base, SessionLocal, engine
from app.routes import router
from app.seed import run_seed

app = FastAPI(
    title="SkyLine Assist - Airline Disruption Agent",
    version="1.0.0",
    description="Agentic customer-service AI with a deterministic rules engine and full audit trail.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_seed(verbose=True)
    finally:
        db.close()
    print(f"API ready. DB: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")


@app.get("/api/health")
def health():
    """Cheap liveness probe for keep-alive pingers and uptime checks."""
    return {"ok": True}


@app.get("/")
def root():
    if _STATIC_DIR.is_dir():
        return FileResponse(_STATIC_DIR / "index.html")
    return {"service": "SkyLine Assist API", "docs": "/docs"}


# --- Single-service static hosting -------------------------------------------
# ../frontend/out exists only when the frontend was built with EXPORT=1
# (Docker deploy). Registered LAST so every API route above matches first.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "out"

if _STATIC_DIR.is_dir():
    app.mount("/_next", StaticFiles(directory=_STATIC_DIR / "_next"), name="next-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_static(full_path: str):
        # Explicit page file, e.g. favicon.ico / images.
        candidate = (_STATIC_DIR / full_path).resolve()
        if candidate.is_file() and _STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        # Pretty paths: /audit -> out/audit/index.html (trailingSlash export).
        pretty = (_STATIC_DIR / full_path / "index.html").resolve()
        if pretty.is_file() and _STATIC_DIR in pretty.parents:
            return FileResponse(pretty)
        return FileResponse(_STATIC_DIR / "index.html")  # SPA fallback
