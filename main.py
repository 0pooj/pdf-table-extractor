"""
Engineering PDF Table Extractor — v1.0.0
Plugin-based Architecture with Specialized Parsers.
"""
from __future__ import annotations
import asyncio
import os
import uuid
from datetime import datetime
from typing import Any
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from logger import logger
from database import init_db, create_job, update_job_status, get_job
from excel_export import export_to_excel
from parsers.auto_classifier import AutoClassifier

app = FastAPI(title="Engineering PDF Extractor")

# Constants
UPLOAD_DIR = "/home/ubuntu/pdf-table-extractor/uploads"
OUTPUT_DIR = "/home/ubuntu/pdf-table-extractor/outputs"
MAX_FILE_SIZE = 50 * 1024 * 1024 # 50MB
MAX_PAGES = 100

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.on_event("startup")
async def startup():
    init_db()

def now_iso():
    return datetime.utcnow().isoformat()

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("/home/ubuntu/pdf-table-extractor/static_ui.html", "r") as f:
        return f.read()

@app.post("/upload")
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extractor: str = "auto"
):
    import fitz
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Page count check
    content = await file.read()
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        if len(doc) > MAX_PAGES:
            raise HTTPException(status_code=400, detail=f"File too large ({len(doc)} pages). Max {MAX_PAGES} pages allowed.")
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {e}")

    job_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}.pdf")
    
    with open(file_path, "wb") as f:
        f.write(content)

    create_job(job_id, file.filename, "pending", created_at=now_iso())
    background_tasks.add_task(_run_extraction, job_id, extractor)
    
    return {"job_id": job_id, "status": "pending"}

@app.get("/status/{job_id}")
async def status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job

@app.get("/download/{job_id}")
async def download(job_id: str):
    job = get_job(job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=404, detail="File not ready.")
    
    file_path = os.path.join(OUTPUT_DIR, f"{job_id}.xlsx")
    return FileResponse(
        file_path, 
        filename=f"Extracted_{job['filename']}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

async def _run_extraction(job_id: str, extractor_mode: str):
    update_job_status(job_id, "processing", started_at=now_iso())
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}.pdf")
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}.xlsx")
    
    try:
        # Run extraction in a thread to keep FastAPI responsive
        tables, parser_name = await asyncio.to_thread(_extract_logic, file_path, extractor_mode)
        
        if not tables:
            update_job_status(job_id, "failed", error="No tables found in document.")
            return

        # Export to Excel
        export_to_excel(tables, output_path)
        update_job_status(job_id, "completed", finished_at=now_iso(), extractor_used=parser_name)
        
    except Exception as e:
        logger.exception(f"Extraction failed for {job_id}: {e}")
        update_job_status(job_id, "failed", error=str(e))

def _extract_logic(pdf_path: str, mode: str):
    classifier = AutoClassifier()
    return classifier.classify_and_extract(pdf_path, mode)
