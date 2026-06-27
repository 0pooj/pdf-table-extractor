"""
PyMuPDF (fitz) extractor — optimised for Datasheets with multi-column layouts.

Why PyMuPDF for Datasheets?
- Written in C → fastest PDF parser available.
- page.find_tables() (added in PyMuPDF ≥ 1.23) reconstructs tables from
  drawn lines AND text alignment, handling mixed layouts.
- Understands multi-column text flow, so spec tables next to prose text
  are captured without mixing the two.
- Also used as the OCR pre-processor: renders pages to images for Tesseract.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from logger import logger


class PyMuPDFExtractor:
    """
    Secondary extractor for Datasheets and complex engineering PDFs.
    Uses PyMuPDF's built-in table finder which handles:
      - Multi-column page layouts
      - Tables with or without visible borders
      - Mixed text + table pages
    """

    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        import fitz  # PyMuPDF

        tables: list[dict[str, Any]] = []

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            logger.error(f"[PyMuPDF] Cannot open PDF: {exc}")
            raise

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_tables = self._extract_page(page, page_num + 1)
            tables.extend(page_tables)

        doc.close()
        logger.info(f"[PyMuPDF] Extracted {len(tables)} tables")
        return tables

    # ── private ───────────────────────────────────────────────────────────────

    def _extract_page(self, page, page_num: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        try:
            tab_finder = page.find_tables()
            found_tables = tab_finder.tables
        except Exception as exc:
            logger.warning(f"[PyMuPDF] page {page_num} find_tables failed: {exc}")
            return results

        for idx, table in enumerate(found_tables):
            try:
                df = _fitz_table_to_df(table)
                if df is None:
                    continue

                title = _extract_caption(page, table, idx)
                results.append({
                    "title": title or f"Table (p.{page_num})",
                    "page": page_num,
                    "dataframe": df,
                    "headers": [str(c) for c in df.columns],
                    "rows": df.fillna("").astype(str).values.tolist(),
                })
            except Exception as exc:
                logger.warning(f"[PyMuPDF] Skipping table {idx} on page {page_num}: {exc}")

        return results


# ── helpers ────────────────────────────────────────────────────────────────────

def _fitz_table_to_df(table) -> pd.DataFrame | None:
    """Convert a fitz.table object to a cleaned pandas DataFrame."""
    raw = table.extract()  # list[list[str | None]]
    if not raw or len(raw) < 2:
        return None

    # Normalise
    cleaned = [
        [str(cell).strip() if cell is not None else "" for cell in row]
        for row in raw
    ]

    headers = cleaned[0]
    data_rows = cleaned[1:]

    # Deduplicate headers
    seen: dict[str, int] = {}
    unique_headers: list[str] = []
    for h in headers:
        label = h if h else f"Col_{len(unique_headers) + 1}"
        if label in seen:
            seen[label] += 1
            unique_headers.append(f"{label}_{seen[label]}")
        else:
            seen[label] = 0
            unique_headers.append(label)

    n = len(unique_headers)
    data_rows = [r[:n] + [""] * max(0, n - len(r)) for r in data_rows]

    df = pd.DataFrame(data_rows, columns=unique_headers)
    df = df[~df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1)]
    df = df.reset_index(drop=True)

    return df if not df.empty else None


def _extract_caption(page, table, idx: int) -> str | None:
    """
    Look for a text block immediately above the table bounding box.
    fitz table bbox: (x0, y0, x1, y1) in page coordinates.
    """
    try:
        x0, y0, x1, y1 = table.bbox
        # Search in a 40-point band above the table
        clip = (x0, max(0, y0 - 40), x1, y0)
        text = page.get_text("text", clip=clip).strip()
        # Keep only the last line (most likely to be the caption)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


# ── OCR helper (used by OcrFallbackExtractor) ─────────────────────────────────

def render_page_to_image(pdf_path: str, page_num: int, dpi: int = 200):
    """
    Render a single PDF page to a PIL Image using PyMuPDF.
    Used by OcrFallbackExtractor to feed pages to Tesseract.
    """
    import fitz
    from PIL import Image
    import io

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    doc.close()

    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))
