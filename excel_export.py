"""
Excel export — professional formatting for BOQ and Datasheet tables.

Features:
  - Summary sheet with metadata (title, page, rows, cols, confidence, extractor).
  - Per-table sheets with styled headers (bold, coloured background, freeze panes).
  - Auto-fit column widths (capped at 60 chars to avoid overly wide columns).
  - Number detection: numeric cells are stored as floats for Excel calculations.
  - Sheet name sanitisation (Excel 31-char limit, forbidden characters removed).
  - Confidence score column in Summary sheet.
"""
from __future__ import annotations

import re
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

# ── colour palette ─────────────────────────────────────────────────────────────
_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")   # dark blue
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_SUMMARY_HEADER_FILL = PatternFill("solid", fgColor="2E75B6")  # medium blue
_SUMMARY_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_ALT_ROW_FILL = PatternFill("solid", fgColor="EBF3FB")  # light blue stripe
_BORDER_SIDE = Side(style="thin", color="BFBFBF")
_CELL_BORDER = Border(
    left=_BORDER_SIDE, right=_BORDER_SIDE,
    top=_BORDER_SIDE, bottom=_BORDER_SIDE,
)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=False)
_WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)


def export_to_excel(tables: list[dict[str, Any]], output_path: str) -> None:
    wb = Workbook()

    # ── Summary sheet ──────────────────────────────────────────────────────────
    summary = wb.active
    summary.title = "Summary"
    summary.row_dimensions[1].height = 22

    summary_headers = [
        "#", "Title", "Page", "Rows", "Columns", "Confidence (%)",
        "Extractor", "Sheet",
    ]
    summary.append(summary_headers)
    _style_header_row(summary, 1, len(summary_headers),
                      fill=_SUMMARY_HEADER_FILL, font=_SUMMARY_HEADER_FONT)

    used_sheet_names: set[str] = {"Summary"}

    for i, table in enumerate(tables, start=1):
        sheet_name = _make_sheet_name(table.get("title", f"Table {i}"), i, used_sheet_names)
        used_sheet_names.add(sheet_name)

        headers = table.get("headers", [])
        rows = table.get("rows", [])
        confidence = table.get("confidence", "")
        extractor = table.get("extractor_used", "")

        summary.append([
            i,
            table.get("title", f"Table {i}"),
            table.get("page", ""),
            len(rows),
            len(headers),
            confidence,
            extractor,
            sheet_name,
        ])

        # Alternate row shading in summary
        if i % 2 == 0:
            for col in range(1, len(summary_headers) + 1):
                summary.cell(row=i + 1, column=col).fill = _ALT_ROW_FILL

        # ── Per-table sheet ────────────────────────────────────────────────────
        ws = wb.create_sheet(sheet_name)
        _write_table_sheet(ws, table)

    # Auto-fit summary columns
    _autofit_columns(summary)
    summary.freeze_panes = "A2"

    wb.save(output_path)


# ── sheet writer ───────────────────────────────────────────────────────────────

def _write_table_sheet(ws, table: dict[str, Any]) -> None:
    headers = table.get("headers", [])
    rows = table.get("rows", [])

    # Header row (row 1)
    header_row_num = 1
    if headers:
        ws.append(headers)
        _style_header_row(ws, header_row_num, len(headers))
        ws.row_dimensions[header_row_num].height = 22

    # Data rows
    for row_idx, row in enumerate(rows, start=header_row_num + 1):
        converted = [_try_numeric(cell) for cell in row]
        ws.append(converted)
        ws.row_dimensions[row_idx].height = 18

        # Alternate row shading
        if (row_idx - header_row_num) % 2 == 0:
            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col)
                cell.fill = _ALT_ROW_FILL

        # Apply border and alignment to all cells in row
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.border = _CELL_BORDER
            cell.alignment = _WRAP

    # Freeze header row
    ws.freeze_panes = f"A{header_row_num + 1}"

    # Auto-fit columns
    _autofit_columns(ws, start_row=header_row_num)


# ── styling helpers ────────────────────────────────────────────────────────────

def _style_header_row(
    ws, row_num: int, num_cols: int,
    fill=_HEADER_FILL, font=_HEADER_FONT
) -> None:
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = fill
        cell.font = font
        cell.border = _CELL_BORDER
        cell.alignment = _CENTER


def _autofit_columns(ws, start_row: int = 1, max_width: int = 60) -> None:
    col_widths: dict[int, int] = {}
    for row in ws.iter_rows(min_row=start_row):
        for cell in row:
            if cell.value is not None:
                length = len(str(cell.value))
                col_widths[cell.column] = max(
                    col_widths.get(cell.column, 0), length
                )

    for col_idx, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = min(width + 2, max_width)


# ── sheet name sanitisation ────────────────────────────────────────────────────

_FORBIDDEN = re.compile(r"[\\/:*?\[\]]")


def _make_sheet_name(title: str, fallback_idx: int, used: set[str]) -> str:
    """
    Create a valid Excel sheet name:
    - Remove forbidden characters.
    - Truncate to 28 chars (leaving room for a numeric suffix).
    - Ensure uniqueness.
    """
    name = _FORBIDDEN.sub("", str(title)).strip()
    name = re.sub(r"\s+", " ", name)[:28] or f"Table_{fallback_idx}"

    if name not in used:
        return name

    # Append numeric suffix until unique
    for n in range(2, 1000):
        candidate = f"{name[:25]}_{n}"
        if candidate not in used:
            return candidate

    return f"Table_{fallback_idx}"


# ── numeric coercion ───────────────────────────────────────────────────────────

def _try_numeric(value: str) -> Any:
    """
    Try to convert a string cell to int or float so Excel treats it as a number.
    Preserves strings that look like codes (e.g. '1.2.3', 'A-01').
    """
    if not isinstance(value, str):
        return value
    v = value.strip().replace(",", "").replace(" ", "")
    if not v: return ""
    
    # Don't convert if it looks like an item number (e.g. 1.1, 2/3)
    if "." in v and v.count(".") > 1: return value
    if "/" in v: return value
    
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        pass
    return value
