"""Application configuration.

Reads environment variables from backend/.env (if present) or the process env.
Default database is a local SQLite file so the demo runs with zero setup;
set DATABASE_URL to a PostgreSQL/Supabase connection string to switch.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # backend/.env
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover - python-dotenv is in requirements anyway
    pass

# --- Database ---------------------------------------------------------------
# Default: local SQLite file (zero setup). For Postgres/Supabase set:
#   DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parent.parent / 'airline_agent.db'}"
)

# Hosted Postgres providers (Supabase pooler, Render, Neon...) hand out
# postgresql:// URLs; we ship the psycopg driver, so add the +psycopg scheme
# automatically unless the caller already picked a dialect.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# --- LLM --------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# --- CORS -------------------------------------------------------------------
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

# When True the API refuses write actions (rebooking / refund / compensation)
# unless the rules engine approves them. Kept as a constant: this behaviour is
# not configurable per the assignment - tools must re-verify from the DB.
RECHECK_POLICY_IN_TOOLS = True
