"""
Plain sqlite3 connection helper — no ORM, keeps things simple for the MVP.
"""
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DATABASE_PATH", "data/app.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """New connection per call — avoids cross-thread issues with BackgroundTasks."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the jobs table if it doesn't exist. Call once on app startup."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size_bytes INTEGER,
                status TEXT NOT NULL DEFAULT 'uploaded',
                extractor_used TEXT,
                table_count INTEGER,
                tables TEXT,
                error TEXT,
                processing_time_seconds REAL,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()