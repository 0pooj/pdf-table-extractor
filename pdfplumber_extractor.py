"""
pdfplumber-based table extractor — optimised for BOQ (Bill of Quantities).

Why pdfplumber for BOQ?
- Analyses lines/curves drawn in the PDF to reconstruct table cells precisely.
- No AI models → zero GPU requirement, minimal RAM, very fast.
- Handles multi-page spanning tables by detecting repeated header rows.
- Returns clean pandas DataFrames ready for Excel export.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd
import pdfplumber

from logger import logger


# ── tuneable thresholds ────────────────────────────────────────────────────────
_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 4,
    "join_tolerance": 4,
    "edge_min_length": 10,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
}

# If line-based detection finds nothing, fall back to text-based heuristics
_TABLE_SETTINGS_TEXT = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 6,
    "join_tolerance": 6,
}

# BOQ column keywords used to detect header rows for multi-page stitching
_BOQ_HEADER_KEYWORDS = {
    "no", "item", "description", "unit", "qty", "quantity",
    "rate", "price", "amount", "total", "رقم", "وصف", "وحدة",
    "كمية", "سعر", "مبلغ", "الإجمالي",
}


class PdfPlumberExtractor:
    """
    Primary extractor for digitally-created BOQ and Datasheet PDFs.
    Attempts line-based table detection first; falls back to text-based.
    Merges multi-page tables that share the same header signature.
    """

    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        raw_tables: list[dict[str, Any]] = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = self._extract_page_tables(page, page_num)
                    raw_tables.extend(page_tables)
        except Exception as exc:
            logger.error(f"[pdfplumber] Failed to open PDF: {exc}")
            raise

        if not raw_tables:
            logger.warning("[pdfplumber] No tables found with line strategy.")
            return []

        merged = _merge_continuation_tables(raw_tables)
        logger.info(f"[pdfplumber] Extracted {len(raw_tables)} raw tables → {len(merged)} after merge")
        return merged

    # ── private helpers ────────────────────────────────────────────────────────

    def _extract_page_tables(
        self, page: pdfplumber.page.Page, page_num: int
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        # 1st attempt: line-based (best for BOQ with drawn borders)
        tables = page.extract_tables(_TABLE_SETTINGS)

        # 2nd attempt: text-based (for BOQ with whitespace-separated columns)
        if not tables:
            tables = page.extract_tables(_TABLE_SETTINGS_TEXT)

        for idx, raw in enumerate(tables):
            df = _raw_to_dataframe(raw)
            if df is None:
                continue

            title = _guess_table_title(page, idx)
            results.append({
                "title": title or f"Table (p.{page_num})",
                "page": page_num,
                "dataframe": df,
                "headers": [str(c) for c in df.columns],
                "rows": df.fillna("").astype(str).values.tolist(),
            })

        return results


# ── module-level helpers ───────────────────────────────────────────────────────

def _raw_to_dataframe(raw: list[list]) -> pd.DataFrame | None:
    """Convert pdfplumber raw table (list of lists) to a cleaned DataFrame."""
    if not raw or len(raw) < 2:
        return None

    # Normalise cells: replace None with empty string
    cleaned = [[str(cell).strip() if cell is not None else "" for cell in row] for row in raw]

    # Detect header row: first non-empty row
    header_row_idx = 0
    for i, row in enumerate(cleaned):
        if any(cell for cell in row):
            header_row_idx = i
            break

    headers = cleaned[header_row_idx]
    data_rows = cleaned[header_row_idx + 1:]

    if not data_rows:
        return None

    # Deduplicate column names
    seen: dict[str, int] = {}
    unique_headers: list[str] = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)

    # Pad / trim rows to header length
    n = len(unique_headers)
    data_rows = [r[:n] + [""] * max(0, n - len(r)) for r in data_rows]

    df = pd.DataFrame(data_rows, columns=unique_headers)
    df = df.dropna(how="all").reset_index(drop=True)

    # Drop rows that are entirely empty strings
    df = df[~df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1)]
    df = df.reset_index(drop=True)

    return df if not df.empty else None


def _guess_table_title(page: pdfplumber.page.Page, table_idx: int) -> str | None:
    """
    Try to find a caption above the table by looking at the text blocks
    immediately before the table's bounding box.
    """
    try:
        tables_meta = page.find_tables(_TABLE_SETTINGS)
        if table_idx >= len(tables_meta):
            return None

        table_bbox = tables_meta[table_idx].bbox  # (x0, top, x1, bottom)
        top_of_table = table_bbox[1]

        # Collect words above the table (within 40 pts)
        words = page.extract_words()
        caption_words = [
            w["text"] for w in words
            if w["bottom"] <= top_of_table and w["bottom"] >= top_of_table - 40
        ]
        caption = " ".join(caption_words).strip()
        return caption if len(caption) > 3 else None
    except Exception:
        return None


def _header_signature(df: pd.DataFrame) -> frozenset[str]:
    """Normalised set of column names — used to detect continuation tables."""
    return frozenset(
        re.sub(r"\s+", " ", str(c).lower().strip())
        for c in df.columns
        if str(c).strip()
    )


def _is_boq_header(df: pd.DataFrame) -> bool:
    sig = _header_signature(df)
    return bool(sig & _BOQ_HEADER_KEYWORDS)


def _merge_continuation_tables(
    tables: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Merge tables that span multiple pages.
    Two consecutive tables are merged when their header signatures match
    (i.e. the second table is a continuation of the first).
    """
    if not tables:
        return []

    merged: list[dict[str, Any]] = []
    current = tables[0]

    for nxt in tables[1:]:
        curr_sig = _header_signature(current["dataframe"])
        nxt_sig = _header_signature(nxt["dataframe"])

        # Same headers on consecutive pages → continuation
        if curr_sig == nxt_sig and nxt["page"] == current["page"] + 1:
            combined_df = pd.concat(
                [current["dataframe"], nxt["dataframe"]], ignore_index=True
            )
            current = {
                **current,
                "dataframe": combined_df,
                "rows": combined_df.fillna("").astype(str).values.tolist(),
                "title": current["title"],  # keep original title
            }
        else:
            merged.append(current)
            current = nxt

    merged.append(current)
    return merged
