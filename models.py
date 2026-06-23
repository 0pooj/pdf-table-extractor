"""
Data access functions used by main.py. Replaces the old jobs = {} dict.
"""
import json
from datetime import datetime, timezone

from database import get_connection

# Whitelist: only these fields can be updated via update_job_status(**fields)
_ALLOWED_UPDATE_FIELDS = {
    "started_at",
    "finished_at",
    "table_count",
    "extractor_used",
    "processing_time_seconds",
    "error",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(job_id: str, filename: str, file_size_bytes: int | None = None):
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


def get_job(job_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    job = dict(row)
    job.pop("id", None)

    if job.get("tables"):
        job["tables"] = json.loads(job["tables"])

    # Drop None values so the response shape matches the old in-memory dict
    # (e.g. "error" key absent unless an error actually happened).
    return {k: v for k, v in job.items() if v is not None or k in ("status", "filename")}


def update_job_status(job_id: str, status: str, **fields):
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


def save_tables(job_id: str, tables: list):
    """tables: list of dicts containing a pandas DataFrame under 'dataframe'
    (same shape produced by the extractors). Stores a lightweight preview as JSON.
    """
    previews = []
    for i, t in enumerate(tables):
        df = t["dataframe"]
        previews.append(
            {
                "index": i,
                "title": t.get("title", f"Table {i + 1}"),
                "rows": len(df),
                "cols": len(df.columns),
                "preview": df.head(5).fillna("").values.tolist(),
                "headers": [str(c) for c in df.columns],
                "page": t.get("page"),
                "confidence": t.get("confidence"),
            }
        )

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE jobs SET tables = ? WHERE id = ?",
            (json.dumps(previews), job_id),
        )
        conn.commit()
    finally:
        conn.close()