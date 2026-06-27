# Engineering PDF Table Extractor

A fast, lightweight, and professional API for extracting complex tables from Engineering PDFs, specifically designed for **Bill of Quantities (BOQ)** and **Datasheets**.

## Architecture: The Multi-Tier Extraction Pipeline

Unlike traditional extractors that rely on heavy AI models, this project uses a tiered approach to maximise speed and accuracy while keeping resource usage (RAM/CPU) to an absolute minimum:

1. **Tier 1: `pdfplumber` (The BOQ Specialist)**
   - Used for digitally-created PDFs with drawn table borders.
   - Analytically reconstructs tables by detecting horizontal and vertical lines.
   - Extremely fast, requires no GPU.
   - **Smart Stitching:** Automatically merges multi-page BOQ tables by detecting repeated header signatures.

2. **Tier 2: `PyMuPDF` / `fitz` (The Datasheet Specialist)**
   - Used for complex layouts (multi-column text + tables without borders).
   - The fastest PDF parser available (written in C).
   - Safely isolates tables from surrounding technical prose.

3. **Tier 3: `Tesseract OCR` (The Scanned Fallback)**
   - Used only when the PDF is a scanned image.
   - Renders pages to high-res images using PyMuPDF, then applies OCR (supports both Arabic and English).
   - Reconstructs columns using x-coordinate bounding-box clustering.

## Professional Excel Export

Extracted tables are exported to a beautifully formatted `.xlsx` file:
- **Summary Sheet:** Lists all extracted tables with their page numbers, dimensions, and an estimated confidence score.
- **Individual Sheets:** Each table gets its own sheet with bold, coloured headers, frozen panes, and auto-fitted column widths.
- **Data Typing:** Numeric cells are correctly cast to floats/integers so they can be immediately used in Excel formulas.

## API Endpoints

- `POST /upload` - Upload a PDF and receive a `job_id`.
- `POST /extract/{job_id}` - Start the background extraction process.
- `GET /status/{job_id}` - Poll for progress and view table previews.
- `GET /download/{job_id}` - Download the final formatted Excel file.

## Setup & Run

### Prerequisites
You need Python 3.10+ and Tesseract installed on your system.
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-ara
```

### Installation
```bash
git clone https://github.com/0pooj/pdf-table-extractor.git
cd pdf-table-extractor
pip install -r requirements.txt
```

### Running the Server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```
Visit `http://localhost:8000` to use the built-in web interface.
