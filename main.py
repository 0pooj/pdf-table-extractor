from __future__ import annotations

import os
import uuid
import time
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from database import init_db
from models import (
    create_job,
    get_job,
    update_job_status,
    save_tables,
    now_iso,
)
from logger import logger

from extractors.docling_extractor import DoclingExtractor
from extractors.marker_extractor import MarkerExtractor
from exports.excel_export import export_to_excel


app = FastAPI(title="Engineering PDF Table Extractor", version="0.2.0")
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <body style="font-family:Arial;max-width:600px;margin:50px auto">
        <h1>Engineering PDF Table Extractor</h1>

        <input type="file">

        <button>
            Extract Tables
        </button>
    </body>
    </html>
    """

_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

UPLOAD_DIR = Path("uploads")
EXPORT_DIR = Path("exports/output")
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Database initialized")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


@app.post("/upload")
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max allowed size is {MAX_FILE_SIZE_MB}MB.",
        )

    job_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{job_id}.pdf"

    written = 0

    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break

                written += len(chunk)

                if written > MAX_FILE_SIZE:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max allowed size is {MAX_FILE_SIZE_MB}MB.",
                    )

                f.write(chunk)

    finally:
        await file.close()

    create_job(job_id=job_id, filename=file.filename, file_size_bytes=written)

    logger.info(f"[{job_id}] Uploaded file: {file.filename} | size={written} bytes")

    return {
        "job_id": job_id,
        "filename": file.filename,
        "file_size_bytes": written,
    }


@app.post("/extract/{job_id}")
async def extract_tables(job_id: str, background_tasks: BackgroundTasks):
    job = get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job["status"] == "processing":
        return {"job_id": job_id, "status": "processing"}

    update_job_status(job_id, "processing", started_at=now_iso())

    logger.info(f"[{job_id}] Extraction queued")

    background_tasks.add_task(_run_extraction, job_id)

    return {"job_id": job_id, "status": "processing"}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job


@app.get("/download/{job_id}")
def download_excel(job_id: str):
    job = get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Extraction not complete yet.")

    excel_path = EXPORT_DIR / f"{job_id}.xlsx"

    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel file not found.")

    original_name = Path(job["filename"]).stem

    return FileResponse(
        path=str(excel_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{original_name}_tables.xlsx",
    )


async def _run_extraction(job_id: str):
    started = time.perf_counter()
    extractor_used = None

    try:
        logger.info(f"[{job_id}] Extraction started")

        pdf_path = UPLOAD_DIR / f"{job_id}.pdf"

        if not pdf_path.exists():
            raise FileNotFoundError("Uploaded PDF not found.")

        try:
            extractor_used = "docling"
            extractor = DoclingExtractor()
            tables = extractor.extract(str(pdf_path))
        except Exception as docling_error:
            logger.warning(f"[{job_id}] Docling failed: {docling_error}")

            extractor_used = "marker"
            extractor = MarkerExtractor()
            tables = extractor.extract(str(pdf_path))

        for table in tables:
            table["confidence"] = estimate_table_confidence(table["dataframe"])

        excel_path = EXPORT_DIR / f"{job_id}.xlsx"
        export_to_excel(tables, str(excel_path))

        save_tables(job_id, tables)

        processing_time = round(time.perf_counter() - started, 3)

        update_job_status(
            job_id,
            "done",
            table_count=len(tables),
            extractor_used=extractor_used,
            processing_time_seconds=processing_time,
            finished_at=now_iso(),
        )

        logger.info(
            f"[{job_id}] Extraction done | extractor={extractor_used} | "
            f"tables={len(tables)} | time={processing_time}s"
        )

    except Exception as error:
        processing_time = round(time.perf_counter() - started, 3)

        update_job_status(
            job_id,
            "error",
            error=str(error),
            extractor_used=extractor_used,
            processing_time_seconds=processing_time,
            finished_at=now_iso(),
        )

        logger.exception(f"[{job_id}] Extraction failed: {error}")


def estimate_table_confidence(df) -> float:
    if df is None or df.empty:
        return 0.0

    rows = len(df)
    cols = len(df.columns)
    score = 100.0

    if rows < 2:
        score -= 30

    if cols < 2:
        score -= 30

    total_cells = rows * cols
    empty_cells = df.isna().sum().sum()

    if total_cells > 0:
        empty_ratio = empty_cells / total_cells
        score -= empty_ratio * 40

    duplicate_headers = len(df.columns) - len(set(map(str, df.columns)))
    score -= duplicate_headers * 5

    return round(max(0.0, min(100.0, score)), 1)olumns)

    score = 100.0

    if rows < 2:
        score -= 30

    if cols < 2:
        score -= 30

    total_cells = rows * cols
    empty_cells = df.isna().sum().sum()

    if total_cells > 0:
        empty_ratio = empty_cells / total_cells
        score -= empty_ratio * 40

    duplicate_headers = len(df.columns) - len(set(map(str, df.columns)))
    score -= duplicate_headers * 5

    return round(max(0.0, min(100.0, score)), 1)
