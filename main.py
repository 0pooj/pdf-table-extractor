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
from paths import BASE_DIR, UPLOAD_DIR, EXPORT_DIR, STATIC_UI_PATH, TRANSLATIONS_PATH
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from logger import logger
from database import init_db, create_job, update_job_status, get_job
from excel_export import export_to_excel
from parsers.auto_classifier import AutoClassifier

app = FastAPI(title="Engineering PDF Extractor")

# Constants
UPLOAD_DIR = str(UPLOAD_DIR)
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
    with open(str(STATIC_UI_PATH), "r") as f:
        return f.read()

@app.get("/translations")
async def get_translations():
    with open("/home/ubuntu/pdf-table-extractor/translations.json", "r") as f:
        import json
        return json.load(f)

@app.post("/upload")
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extractor: str = "auto"
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    job_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{job_id}.pdf")
    
    # Fast streaming write
    import shutil
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Fast page count check using fitz on the saved file
    import fitz
    try:
        doc = fitz.open(file_path)
        page_count = len(doc)
        doc.close()
        if page_count > MAX_PAGES:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"File too large ({page_count} pages). Max {MAX_PAGES} allowed.")
    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {e}")

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
        doc_data = await asyncio.to_thread(_extract_logic, file_path, extractor_mode)
        
        # Export to Excel (now takes the whole ParsedDocument)
        export_to_excel(doc_data, output_path)
        update_job_status(job_id, "completed", finished_at=now_iso(), extractor_used=doc_data.doc_type)
        
    except Exception as e:
        logger.exception(f"Extraction failed for {job_id}: {e}")
        update_job_status(job_id, "failed", error=str(e))

def _extract_logic(pdf_path: str, mode: str):
    from parsers.boq_parser import BOQParser
    from parsers.datasheet_parser import DatasheetParser
    from parsers.catalog_parser import CatalogParser
    from parsers.specsheet_parser import SpecSheetParser
    from parsers.generic_parser import GenericParser
    from parsers.ocr_parser import OCRParser

    parsers = {
        "boq": BOQParser(),
        "datasheet": DatasheetParser(),
        "catalog": CatalogParser(),
        "specsheet": SpecSheetParser(),
        "generic": GenericParser(),
        "ocr": OCRParser()
    }
    
    selected_parser = parsers.get(mode, BOQParser())
    return selected_parser.parse(pdf_path)
