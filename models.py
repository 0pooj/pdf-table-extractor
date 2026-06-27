"""
Data-access layer — all SQL lives here, main.py stays clean.

Changes from v0.2:
  - get_job() no longer strips the 'id' field (frontend needs it).
  - list_jobs() added for optional job history endpoint.
  - save_tables() stores full row data (not just 5-row preview) as JSON,
    capped at MAX_PREVIEW_ROWS to keep the DB row size reasonable.
    The full data lives in the Excel file; DB stores enough for API responses.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from database import get_connection

# Whitelist prevents SQL-injection via dynamic UPDATE keys
_ALLOWED_UPDATE_FIELDS = {
    "started_at",
    "finished_at",
    "table_count",
    "extractor_used",
    "processing_time_seconds",
    "error",
}

MAX_PREVIEW_ROWS = 20   # rows stored in DB per table for /status response


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── create ─────────────────────────────────────────────────────────────────────
def create_job(job_id: str, filename: str, file_size_bytes: int | None = None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO jobs (id, filename, file_size_bytes, status, created_at)
               VALUES (?, ?, ?, 'uploaded', ?)""",
            (job_id, filename, file_size_bytes, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


# ── read ───────────────────────────────────────────────────────────────────────
def get_job(job_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    job = dict(row)

    if job.get("tables"):
        try:
            job["tables"] = json.loads(job["tables"])
        except json.JSONDecodeError:
            job["tables"] = []

    # Keep 'id' in response — frontend needs it for polling
    # Only strip None values for optional fields
    return {k: v for k, v in job.items() if v is not None or k in ("status", "filename", "id")}


def list_jobs(limit: int = 50) -> list[dict]:
    """Return the most recent `limit` jobs (newest first)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, filename, status, table_count, extractor_used, "
            "processing_time_seconds, created_at, finished_at "
            "FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {k: v for k, v in dict(r).items() if v is not None}
        for r in rows
    ]


# ── update ─────────────────────────────────────────────────────────────────────
def update_job_status(job_id: str, status: str, **fields) -> None:
    set_clauses = ["status = ?"]
    values: list = [status]

    for key, value in fields.items():
        if key in _ALLOWED_UPDATE_FIELDS:
            set_clauses.append(f"{key} = ?")
            values.append(value)

    values.append(job_id)

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?", values
        )
        conn.commit()
    finally:
        conn.close()


# ── save tables ────────────────────────────────────────────────────────────────
def save_tables(job_id: str, tables: list) -> None:
    """
    Persist a lightweight preview of each table as JSON.
    Stores up to MAX_PREVIEW_ROWS data rows per table so the /status
    endpoint can return useful data without loading the Excel file.
    """
    previews = []
    for i, t in enumerate(tables):
        df = t["dataframe"]
        preview_rows = df.head(MAX_PREVIEW_ROWS).fillna("").values.tolist()
        previews.append({
            "index": i,
            "title": t.get("title", f"Table {i + 1}"),
            "rows": len(df),
            "cols": len(df.columns),
            "preview": preview_rows,
            "headers": [str(c) for c in df.columns],
            "page": t.get("page"),
            "confidence": t.get("confidence"),
            "extractor_used": t.get("extractor_used"),
        })

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE jobs SET tables = ? WHERE id = ?",
            (json.dumps(previews, ensure_ascii=False), job_id),
        )
        conn.commit()
    finally:
        conn.close()
