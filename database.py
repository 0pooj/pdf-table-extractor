"""
SQLite connection helper — optimised for FastAPI BackgroundTasks concurrency.

Improvements over v0.2:
  - WAL (Write-Ahead Logging) mode enabled for better concurrent read/write.
  - Busy timeout set to 5 s to avoid "database is locked" errors.
  - DB path resolved at runtime (not at import time) to support containerised
    environments where the working directory may not be writable at import.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _get_db_path() -> str:
    path = os.getenv("DATABASE_PATH", "data/app.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    """
    Open a new SQLite connection per call.
    WAL mode + 5 s busy timeout make concurrent BackgroundTask writes safe.
    """
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    """Create tables and indices if they don't exist. Called once on startup."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id                      TEXT PRIMARY KEY,
                filename                TEXT NOT NULL,
                file_size_bytes         INTEGER,
                status                  TEXT NOT NULL DEFAULT 'uploaded',
                extractor_used          TEXT,
                table_count             INTEGER,
                tables                  TEXT,
                error                   TEXT,
                processing_time_seconds REAL,
                created_at              TEXT,
                started_at              TEXT,
                finished_at             TEXT
            )
            """
        )
        # Index on status for fast polling queries
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status)"
        )
        conn.commit()
    finally:
        conn.close()
