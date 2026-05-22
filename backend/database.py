import os
import json
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Load .env file automatically if present
load_dotenv()

# Load Supabase/PostgreSQL connection string from environment
DATABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Neither SUPABASE_URL nor DATABASE_URL environment variable is set for production database connection.")

# Initialize a simple connection pool (min 1, max 10 connections)
DB_POOL = pool.SimpleConnectionPool(1, 10, dsn=DATABASE_URL)

def get_db_connection():
    """Acquire a connection from the pool. Caller should close it after use to return to pool."""
    conn = DB_POOL.getconn()
    conn.autocommit = False
    return conn

def release_db_connection(conn):
    """Return connection to the pool."""
    DB_POOL.putconn(conn)

def init_db():
    """Create required tables if they do not exist. No mock data seeding in production."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Create dynamic_tracks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dynamic_tracks (
        id SERIAL PRIMARY KEY,
        slug TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Create ocean_hackathons table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ocean_hackathons (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        organizer TEXT,
        description_summary TEXT,
        track_slug TEXT,
        registration_url TEXT UNIQUE NOT NULL,
        start_date DATE,
        end_date DATE,
        registration_deadline DATE,
        prize_pool TEXT,
        tags JSONB, -- Store tags as JSON array
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (track_slug) REFERENCES dynamic_tracks(slug) ON DELETE SET NULL
    );
    """)
    conn.commit()
    cursor.close()
    release_db_connection(conn)
    print("[+] Production PostgreSQL schema ensured.")

# No seed_db function – production starts empty.

if __name__ == "__main__":
    init_db()
