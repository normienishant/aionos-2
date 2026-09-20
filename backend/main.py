"""FastAPI entrypoint.

Run:  uvicorn main:app --reload --port 8000     (from backend/)
Auto-seeds the database on startup if empty.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
def root():
    return {"service": "SkyLine Assist API", "docs": "/docs"}
