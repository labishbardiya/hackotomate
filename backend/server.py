"""
server.py – Production FastAPI application

Endpoints:
  GET  /api/hackathons          – List all hackathons (optional ?track= filter)
  GET  /api/tracks              – List all dynamic tracks
  GET  /api/pipeline/run        – Stream ingestion pipeline (x-admin-key header required)
  POST /api/pipeline/reset      – Drop & recreate tables (x-admin-key header required)

Background task:
  Periodic pipeline runs every 24 h via asyncio.create_task on startup.

Security:
  All mutating / privileged endpoints check the x-admin-key request header
  against the ADMIN_SECRET_KEY environment variable.
  No JWT, no login paths, no credential tables.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Prepend parent directory to sys.path so 'backend.xxx' imports resolve when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.database import get_db_connection, init_db, release_db_connection
from backend.pipeline import run_pipeline_generator

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OCEAN // HACKATHON_SERVER",
    description="Autonomous Event Aggregator & Dynamic Classification Engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Security helper
# ---------------------------------------------------------------------------

def _require_admin(request: Request) -> None:
    """Raise 403 if ADMIN_SECRET_KEY is set and the request header doesn't match."""
    admin_secret = os.getenv("ADMIN_SECRET_KEY")
    if not admin_secret:
        return  # No key configured → open (single-user local mode)
    provided = request.headers.get("x-admin-key", "")
    if provided != admin_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing x-admin-key header.",
        )


# ---------------------------------------------------------------------------
# Startup – schema init + 24-hour background pipeline
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    """Initialize PostgreSQL schema and schedule the 24-hour auto-pipeline."""
    init_db()
    asyncio.create_task(_periodic_pipeline())
    print("[+] Server startup complete. 24-hour pipeline scheduler armed.")


async def _periodic_pipeline() -> None:
    """Background task: run the full discovery pipeline every 24 hours."""
    while True:
        await asyncio.sleep(24 * 60 * 60)
        print("[*] Periodic pipeline triggered (24h scheduler).")
        try:
            async for line in run_pipeline_generator():
                # Log to stdout; not streamed to any client
                print(line, end="")
        except Exception as e:
            print(f"[-] Periodic pipeline error: {e}")


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/hackathons")
def get_hackathons(track: str = None) -> list:
    """Return hackathons from Supabase PostgreSQL. Supports ?track= slug filter."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if track and track != "all":
            cursor.execute(
                """
                SELECT h.id, h.name, h.organizer, h.description_summary,
                       h.track_slug, h.registration_url, h.start_date, h.end_date,
                       h.registration_deadline, h.prize_pool, h.tags, h.created_at,
                       t.display_name AS track_name
                FROM ocean_hackathons h
                LEFT JOIN dynamic_tracks t ON h.track_slug = t.slug
                WHERE h.track_slug = %s
                ORDER BY h.start_date ASC;
                """,
                (track,),
            )
        else:
            cursor.execute(
                """
                SELECT h.id, h.name, h.organizer, h.description_summary,
                       h.track_slug, h.registration_url, h.start_date, h.end_date,
                       h.registration_deadline, h.prize_pool, h.tags, h.created_at,
                       t.display_name AS track_name
                FROM ocean_hackathons h
                LEFT JOIN dynamic_tracks t ON h.track_slug = t.slug
                ORDER BY h.start_date ASC;
                """
            )

        cols = [desc[0] for desc in cursor.description]
        hackathons = []
        for row in cursor.fetchall():
            h = dict(zip(cols, row))
            # tags is stored as JSONB – may already be a list or a JSON string
            raw_tags = h.get("tags")
            if isinstance(raw_tags, list):
                h["tags"] = raw_tags
            elif isinstance(raw_tags, str):
                try:
                    h["tags"] = json.loads(raw_tags)
                except Exception:
                    h["tags"] = []
            else:
                h["tags"] = []
            # Serialize date/datetime fields to ISO strings for JSON
            for date_field in ("start_date", "end_date", "registration_deadline", "created_at"):
                if h.get(date_field) and hasattr(h[date_field], "isoformat"):
                    h[date_field] = h[date_field].isoformat()
            hackathons.append(h)
        return hackathons
    finally:
        release_db_connection(conn)


@app.get("/api/tracks")
def get_tracks() -> list:
    """Return all dynamically created taxonomy tracks."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, slug, display_name, summary, created_at FROM dynamic_tracks ORDER BY display_name ASC;")
        cols = [desc[0] for desc in cursor.description]
        tracks = []
        for row in cursor.fetchall():
            t = dict(zip(cols, row))
            if t.get("created_at") and hasattr(t["created_at"], "isoformat"):
                t["created_at"] = t["created_at"].isoformat()
            tracks.append(t)
        return tracks
    finally:
        release_db_connection(conn)


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------

@app.get("/api/pipeline/run")
async def run_pipeline(request: Request, url: str = None):
    """
    Stream the ingestion pipeline log line-by-line.
    Secured via x-admin-key header check against ADMIN_SECRET_KEY env var.
    """
    _require_admin(request)
    return StreamingResponse(
        run_pipeline_generator(url),
        media_type="text/plain",
    )


@app.post("/api/pipeline/reset")
def reset_database(request: Request) -> dict:
    """
    Drop and recreate the ocean_hackathons and dynamic_tracks tables.
    Production admin operation – requires x-admin-key header.
    """
    _require_admin(request)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS ocean_hackathons CASCADE;")
        cursor.execute("DROP TABLE IF EXISTS dynamic_tracks CASCADE;")
        conn.commit()
    finally:
        release_db_connection(conn)
    init_db()
    return {"status": "success", "message": "Tables dropped and recreated. Database is now empty."}


# ---------------------------------------------------------------------------
# Static frontend – mounted last so API routes take priority
# ---------------------------------------------------------------------------

_frontend_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)

if os.path.exists(_frontend_path):
    print(f"[+] Mounting frontend static files: {_frontend_path}")
    app.mount("/", StaticFiles(directory=_frontend_path, html=True), name="static")
else:
    print(f"[!] Frontend directory not found: {_frontend_path}")


# ---------------------------------------------------------------------------
# Direct run entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000, reload=False)
