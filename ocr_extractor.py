"""
OCR Fallback Extractor — for scanned / image-based PDFs.

Pipeline:
  1. PyMuPDF renders each page to a high-res PIL Image (200 DPI).
  2. Tesseract OCR extracts text (supports Arabic + English).
  3. pdfplumber-style heuristics parse markdown-like tables from the OCR output.
  4. As a last resort, pytesseract's TSV output is used to reconstruct
     tables from bounding-box data (column clustering).

This is intentionally the LAST fallback — only invoked when both
pdfplumber and PyMuPDF find zero tables.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from logger import logger
from pymupdf_extractor import render_page_to_image


# Tesseract language string — Arabic + English
_TESS_LANG = "ara+eng"


class OcrFallbackExtractor:
    """
    Tesseract-based extractor for scanned BOQ / Datasheet PDFs.
    Uses PyMuPDF to render pages and Tesseract to read text.
    """

    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        import fitz

        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()

        tables: list[dict[str, Any]] = []

        for page_num in range(page_count):
            logger.info(f"[OCR] Processing page {page_num + 1}/{page_count}")
            page_tables = self._process_page(pdf_path, page_num)
            tables.extend(page_tables)

        logger.info(f"[OCR] Extracted {len(tables)} tables via Tesseract")
        return tables

    # ── private ───────────────────────────────────────────────────────────────

    def _process_page(self, pdf_path: str, page_num: int) -> list[dict[str, Any]]:
        try:
            image = render_page_to_image(pdf_path, page_num, dpi=200)
        except Exception as exc:
            logger.warning(f"[OCR] Cannot render page {page_num + 1}: {exc}")
            return []

        # Strategy A: parse text output for markdown-style tables
        text_tables = self._extract_via_text(image, page_num + 1)
        if text_tables:
            return text_tables

        # Strategy B: use TSV bounding-box data for column reconstruction
        return self._extract_via_tsv(image, page_num + 1)

    def _extract_via_text(self, image, page_num: int) -> list[dict[str, Any]]:
        """Run Tesseract in text mode and parse table-like structures."""
        try:
            import pytesseract
            text = pytesseract.image_to_string(image, lang=_TESS_LANG)
        except Exception as exc:
            logger.warning(f"[OCR/text] Tesseract failed on page {page_num}: {exc}")
            return []

        return _parse_text_tables(text, page_num)

    def _extract_via_tsv(self, image, page_num: int) -> list[dict[str, Any]]:
        """
        Use Tesseract TSV output to cluster words into columns by x-coordinate,
        then reconstruct rows. Useful for BOQ tables without visible borders.
        """
        try:
            import pytesseract
            tsv_df = pytesseract.image_to_data(
                image, lang=_TESS_LANG, output_type=pytesseract.Output.DATAFRAME
            )
        except Exception as exc:
            logger.warning(f"[OCR/tsv] Tesseract TSV failed on page {page_num}: {exc}")
            return []

        return _reconstruct_from_tsv(tsv_df, page_num)


# ── text-based table parser ────────────────────────────────────────────────────

def _parse_text_tables(text: str, page_num: int) -> list[dict[str, Any]]:
    """
    Detect table-like blocks in OCR text output.
    A 'table block' is a sequence of lines where each line contains
    at least 2 tab-separated or multi-space-separated tokens.
    """
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        tokens = re.split(r"\t| {2,}", line.strip())
        tokens = [t.strip() for t in tokens if t.strip()]
        if len(tokens) >= 2:
            current_block.append(line)
        else:
            if len(current_block) >= 3:
                blocks.append(current_block)
            current_block = []

    if len(current_block) >= 3:
        blocks.append(current_block)

    results: list[dict[str, Any]] = []
    for block_idx, block in enumerate(blocks):
        df = _block_to_df(block)
        if df is None:
            continue
        results.append({
            "title": f"Table (p.{page_num})",
            "page": page_num,
            "dataframe": df,
            "headers": [str(c) for c in df.columns],
            "rows": df.fillna("").astype(str).values.tolist(),
        })

    return results


def _block_to_df(lines: list[str]) -> pd.DataFrame | None:
    """Convert a list of text lines into a DataFrame."""
    rows = []
    for line in lines:
        tokens = re.split(r"\t| {2,}", line.strip())
        tokens = [t.strip() for t in tokens if t.strip()]
        if tokens:
            rows.append(tokens)

    if len(rows) < 2:
        return None

    # Normalise column count
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    headers = rows[0]
    data = rows[1:]

    # Deduplicate headers
    seen: dict[str, int] = {}
    unique: list[str] = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique.append(h)

    df = pd.DataFrame(data, columns=unique)
    df = df[~df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1)]
    return df.reset_index(drop=True) if not df.empty else None


# ── TSV-based column reconstruction ───────────────────────────────────────────

def _reconstruct_from_tsv(tsv: pd.DataFrame, page_num: int) -> list[dict[str, Any]]:
    """
    Cluster Tesseract word bounding boxes into columns using x-coordinate
    binning, then group into rows by line_num. Works well for BOQ tables
    that lack drawn borders.
    """
    try:
        # Keep only confident words
        words = tsv[tsv["conf"] > 30].copy()
        words = words[words["text"].str.strip().astype(bool)]

        if words.empty:
            return []

        # Bin x-coordinates into columns (tolerance = 20px)
        x_centers = (words["left"] + words["width"] / 2).round(0)
        col_bins = _cluster_1d(x_centers.tolist(), tolerance=20)
        words["col_idx"] = [col_bins[x] for x in x_centers.tolist()]

        # Group by block_num + line_num to form rows
        rows_dict: dict[tuple, dict[int, str]] = {}
        for _, w in words.iterrows():
            key = (int(w["block_num"]), int(w["line_num"]))
            col = int(w["col_idx"])
            rows_dict.setdefault(key, {})[col] = (
                rows_dict.get(key, {}).get(col, "") + " " + str(w["text"])
            ).strip()

        if not rows_dict:
            return []

        num_cols = max(max(cols.keys()) for cols in rows_dict.values()) + 1
        matrix = [
            [rows_dict[k].get(c, "") for c in range(num_cols)]
            for k in sorted(rows_dict.keys())
        ]

        if len(matrix) < 2:
            return []

        headers = matrix[0]
        data = matrix[1:]

        # Deduplicate headers
        seen: dict[str, int] = {}
        unique: list[str] = []
        for h in headers:
            label = h if h else f"Col_{len(unique) + 1}"
            if label in seen:
                seen[label] += 1
                unique.append(f"{label}_{seen[label]}")
            else:
                seen[label] = 0
                unique.append(label)

        df = pd.DataFrame(data, columns=unique)
        df = df[~df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1)]
        df = df.reset_index(drop=True)

        if df.empty:
            return []

        return [{
            "title": f"Table (p.{page_num})",
            "page": page_num,
            "dataframe": df,
            "headers": unique,
            "rows": df.fillna("").astype(str).values.tolist(),
        }]

    except Exception as exc:
        logger.warning(f"[OCR/tsv] Reconstruction failed on page {page_num}: {exc}")
        return []


def _cluster_1d(values: list[float], tolerance: int = 20) -> dict[float, int]:
    """
    Assign each value to a cluster index based on proximity.
    Returns a mapping {original_value: cluster_index}.
    """
    sorted_vals = sorted(set(values))
    clusters: list[list[float]] = []

    for v in sorted_vals:
        placed = False
        for cluster in clusters:
            if abs(v - cluster[0]) <= tolerance:
                cluster.append(v)
                placed = True
                break
        if not placed:
            clusters.append([v])

    val_to_cluster: dict[float, int] = {}
    for idx, cluster in enumerate(clusters):
        for v in cluster:
            val_to_cluster[v] = idx

    return val_to_cluster
