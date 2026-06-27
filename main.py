"""
Engineering PDF Table Extractor — v0.6.0
FastAPI application entry point with modern UI and extractor selection.

Extraction pipeline:
  1. BOQ Parser   — coordinate-based text reconstruction (for fragmented BOQs)
  2. pdfplumber   — digital PDFs with drawn table borders
  3. PyMuPDF      — digital PDFs with complex layouts (Datasheet)
  4. OCR Fallback — scanned / image-based PDFs (Tesseract ara+eng)
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from database import init_db
from logger import logger
from models import create_job, get_job, now_iso, save_tables, update_job_status
from excel_export import export_to_excel

# ── configuration ──────────────────────────────────────────────────────────────
_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_PAGES = 100

FILE_TTL_HOURS = int(os.getenv("FILE_TTL_HOURS", "24"))

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
EXPORT_DIR = Path(os.getenv("EXPORT_DIR", "exports/output"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# ── lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised — PDF Table Extractor v0.4.0 ready")
    yield
    logger.info("Shutting down")


# ── app ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Engineering PDF Table Extractor",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── modern UI ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home():
    ui_path = Path(__file__).parent / "static_ui.html"
    if ui_path.exists():
        return ui_path.read_text(encoding="utf-8")
    # Fallback if file not found
    return """<!DOCTYPE html><html><body><h1>Error</h1><p>UI file not found</p></body></html>"""


# ── health ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "version": "0.4.0"}


# ── upload ─────────────────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    extractor: str = "auto",
):
    import fitz
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if extractor not in ("auto", "pdfplumber", "pymupdf", "ocr", "boq"):
        raise HTTPException(status_code=400, detail="Invalid extractor option.")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {MAX_FILE_SIZE_MB} MB.",
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
                        detail=f"File too large. Max size is {MAX_FILE_SIZE_MB} MB.",
                    )
                f.write(chunk)
    finally:
        await file.close()

    # Verify page count
    try:
        doc = fitz.open(dest)
        page_count = len(doc)
        doc.close()
        if page_count > MAX_PAGES:
            dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"الملف كبير جداً ({page_count} صفحة). الحد الأقصى المسموح به هو {MAX_PAGES} صفحة.",
            )
    except Exception as e:
        if isinstance(e, HTTPException): raise
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="تعذر قراءة ملف PDF أو الملف تالف.")

    create_job(job_id=job_id, filename=file.filename, file_size_bytes=written)
    logger.info(
        f"[{job_id}] Uploaded: {file.filename} ({written:,} bytes) | extractor={extractor}"
    )

    return {
        "job_id": job_id,
        "filename": file.filename,
        "file_size_bytes": written,
        "extractor": extractor,
    }


# ── extract ────────────────────────────────────────────────────────────────────
@app.post("/extract/{job_id}")
async def extract_tables(
    job_id: str,
    background_tasks: BackgroundTasks,
    extractor: str = "auto",
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] == "processing":
        return {"job_id": job_id, "status": "processing"}

    if extractor not in ("auto", "pdfplumber", "pymupdf", "ocr", "boq"):
        extractor = "auto"

    update_job_status(job_id, "processing", started_at=now_iso())
    logger.info(f"[{job_id}] Extraction queued | extractor={extractor}")
    background_tasks.add_task(_run_extraction, job_id, extractor)
    return {"job_id": job_id, "status": "processing"}


# ── status ─────────────────────────────────────────────────────────────────────
@app.get("/status/{job_id}")
def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# ── download ───────────────────────────────────────────────────────────────────
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


# ── background extraction task ─────────────────────────────────────────────────
async def _run_extraction(job_id: str, extractor_mode: str = "auto") -> None:
    """
    Runs in a FastAPI BackgroundTask.
    CPU-bound extractor calls are offloaded to a thread pool via
    asyncio.to_thread() so the event loop is never blocked.
    """
    started = time.perf_counter()
    extractor_used: str | None = None

    try:
        logger.info(f"[{job_id}] Extraction started | mode={extractor_mode}")
        pdf_path = str(UPLOAD_DIR / f"{job_id}.pdf")

        if not Path(pdf_path).exists():
            raise FileNotFoundError("Uploaded PDF not found.")

        tables, extractor_used = await asyncio.to_thread(
            _extract_with_fallback, pdf_path, extractor_mode
        )

        for table in tables:
            table["confidence"] = _estimate_confidence(table["dataframe"])
            table["extractor_used"] = extractor_used

        excel_path = str(EXPORT_DIR / f"{job_id}.xlsx")
        await asyncio.to_thread(export_to_excel, tables, excel_path)

        save_tables(job_id, tables)

        elapsed = round(time.perf_counter() - started, 3)
        update_job_status(
            job_id,
            "done",
            table_count=len(tables),
            extractor_used=extractor_used,
            processing_time_seconds=elapsed,
            finished_at=now_iso(),
        )
        logger.info(
            f"[{job_id}] Done | extractor={extractor_used} | "
            f"tables={len(tables)} | time={elapsed}s"
        )

    except Exception as error:
        elapsed = round(time.perf_counter() - started, 3)
        update_job_status(
            job_id,
            "error",
            error=str(error),
            extractor_used=extractor_used,
            processing_time_seconds=elapsed,
            finished_at=now_iso(),
        )
        logger.exception(f"[{job_id}] Extraction failed: {error}")


# ── extraction pipeline ────────────────────────────────────────────────────────
def _extract_with_fallback(pdf_path: str, mode: str = "auto") -> tuple[list, str]:
    """
    Synchronous extraction pipeline — called inside a thread.
    Returns (tables, extractor_name).
    
    Modes:
      - "auto": Try all in order (BOQ Parser → pdfplumber → PyMuPDF → OCR)
      - "boq": Use coordinate-based BOQ Parser
      - "pdfplumber": Use only pdfplumber
      - "pymupdf": Use only PyMuPDF
      - "ocr": Use only OCR
    """
    # ── Stage 1: BOQ Layout Parser (For fragmented text BOQs) ──────────────
    if mode in ("auto", "boq"):
        try:
            from boq_layout_parser import BOQLayoutParser
            tables = BOQLayoutParser().extract(pdf_path)
            if tables:
                return tables, "boq_parser"
            if mode == "boq": return [], "boq_parser"
        except Exception as exc:
            logger.warning(f"[pipeline] BOQ Parser failed: {exc}")
            if mode == "boq": raise

    # ── Stage 2: pdfplumber (BOQ — line-based tables) ──────────────────────
    if mode in ("auto", "pdfplumber"):
        try:
            from pdfplumber_extractor import PdfPlumberExtractor
            tables = PdfPlumberExtractor().extract(pdf_path)
            if tables:
                return tables, "pdfplumber"
            if mode == "pdfplumber": return [], "pdfplumber"
        except Exception as exc:
            logger.warning(f"[pipeline] pdfplumber failed: {exc}")
            if mode == "pdfplumber": raise

    # ── Stage 3: PyMuPDF (Datasheet — complex layouts) ─────────────────────
    if mode in ("auto", "pymupdf"):
        try:
            from pymupdf_extractor import PyMuPDFExtractor
            tables = PyMuPDFExtractor().extract(pdf_path)
            if tables:
                return tables, "pymupdf"
            if mode == "pymupdf": return [], "pymupdf"
        except Exception as exc:
            logger.warning(f"[pipeline] PyMuPDF failed: {exc}")
            if mode == "pymupdf": raise

    # ── Stage 3: OCR Fallback (scanned PDFs) ───────────────────────────────
    try:
        from ocr_extractor import OcrFallbackExtractor

        tables = OcrFallbackExtractor().extract(pdf_path)
        if tables:
            logger.info(f"[pipeline] OCR found {len(tables)} table(s)")
            return tables, "ocr_tesseract"
        logger.warning("[pipeline] OCR: no tables found in document")
        return [], "ocr_tesseract"
    except Exception as exc:
        logger.error(f"[pipeline] OCR failed: {exc}")
        raise RuntimeError(
            "All extraction engines failed. "
            "The PDF may be encrypted, corrupted, or contain no extractable tables."
        ) from exc


# ── confidence estimator ───────────────────────────────────────────────────────
def _estimate_confidence(df) -> float:
    """
    Heuristic confidence score (0–100) based on table structure quality.
    Penalises: too few rows/cols, high empty-cell ratio, duplicate headers.
    """
    if df is None or df.empty:
        return 0.0

    rows, cols = len(df), len(df.columns)
    score = 100.0

    if rows < 2:
        score -= 30
    if cols < 2:
        score -= 30

    total = rows * cols
    if total > 0:
        empty_ratio = df.isna().sum().sum() / total
        score -= empty_ratio * 40

    dup_headers = len(df.columns) - len(set(map(str, df.columns)))
    score -= dup_headers * 5

    return round(max(0.0, min(100.0, score)), 1)
