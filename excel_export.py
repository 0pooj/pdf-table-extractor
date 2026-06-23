"""
Excel export — one sheet per extracted table, with light formatting.
"""
from __future__ import annotations

from typing import Any
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import (
    PatternFill,
    Font,
    Alignment,
    Border,
    Side,
    numbers,
)
from openpyxl.utils import get_column_letter


# Colour palette (engineering / blueprint feel)
HEADER_BG = "1E3A5F"   # dark navy
HEADER_FG = "FFFFFF"   # white
ALT_ROW_BG = "EFF3F8"  # light blue-grey
BORDER_COLOR = "B0C4DE" # steel blue


def export_to_excel(tables: list[dict[str, Any]], output_path: str) -> None:
    """
    Write all extracted tables to a single .xlsx file.

    Each table becomes its own worksheet. A summary sheet is added first.
    """
    wb = Workbook()
    # Remove the default empty sheet
    wb.remove(wb.active)

    # ── Summary sheet ─────────────────────────────────────────────────
    ws_summary = wb.create_sheet("Summary", 0)
    _write_summary(ws_summary, tables)

    # ── One sheet per table ───────────────────────────────────────────
    for i, table in enumerate(tables):
        df: pd.DataFrame = table["dataframe"]
        raw_title = table.get("title", f"Table {i + 1}")
        # Worksheet names: max 31 chars, no special chars
        sheet_name = _safe_sheet_name(raw_title, i + 1)
        ws = wb.create_sheet(sheet_name)
        _write_table_sheet(ws, df, raw_title, table.get("page"))

    wb.save(output_path)


# ───────────────────────────────────────────────────────────────────────
# Internal helpers
# ───────────────────────────────────────────────────────────────────────

def _write_summary(ws, tables: list[dict]) -> None:
    ws.title = "Summary"
    headers = ["#", "Table Title", "Page", "Rows", "Columns", "Sheet"]
    _write_header_row(ws, 1, headers)

    for i, t in enumerate(tables):
        df = t["dataframe"]
        page = t.get("page", "—") or "—"
        sheet = _safe_sheet_name(t.get("title", f"Table {i+1}"), i + 1)
        ws.append([i + 1, t.get("title", f"Table {i+1}"), page,
                   len(df), len(df.columns), sheet])
        _style_data_row(ws, i + 2, len(headers), i)

    _auto_width(ws)


def _write_table_sheet(ws, df: pd.DataFrame, title: str, page) -> None:
    # Title row
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(bold=True, size=12, color=HEADER_BG)
    if page:
        ws.cell(2, 1, f"Source page: {page}")
        ws.cell(2, 1).font = Font(italic=True, size=9, color="888888")
        data_start_row = 4
    else:
        data_start_row = 3

    # Header row
    _write_header_row(ws, data_start_row, list(df.columns))

    # Data rows
    for r_idx, row in enumerate(df.itertuples(index=False)):
        excel_row = data_start_row + 1 + r_idx
        for c_idx, value in enumerate(row):
            ws.cell(excel_row, c_idx + 1, value)
        _style_data_row(ws, excel_row, len(df.columns), r_idx)

    _auto_width(ws)
    ws.freeze_panes = ws.cell(data_start_row + 1, 1)


def _write_header_row(ws, row: int, headers: list[str]) -> None:
    fill = PatternFill("solid", fgColor=HEADER_BG)
    font = Font(bold=True, color=HEADER_FG, size=10)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row, col, header)
        cell.fill = fill
        cell.font = font
        cell.alignment = align
        cell.border = border

    ws.row_dimensions[row].height = 22


def _style_data_row(ws, row: int, ncols: int, data_index: int) -> None:
    bg = ALT_ROW_BG if data_index % 2 == 0 else "FFFFFF"
    fill = PatternFill("solid", fgColor=bg)
    thin = Side(style="thin", color=BORDER_COLOR)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    align = Alignment(vertical="center", wrap_text=False)

    for col in range(1, ncols + 1):
        cell = ws.cell(row, col)
        cell.fill = fill
        cell.border = border
        cell.alignment = align


def _auto_width(ws, max_width: int = 50) -> None:
    for col in ws.columns:
        try:
            max_len = max(
                len(str(cell.value)) if cell.value is not None else 0
                for cell in col
            )
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(
                max_len + 4, max_width
            )
        except Exception:
            pass


def _safe_sheet_name(title: str, fallback_index: int) -> str:
    """Produce a valid Excel sheet name (≤31 chars, no forbidden chars)."""
    forbidden = r"\/*?:[]]"
    name = title
    for ch in forbidden:
        name = name.replace(ch, " ")
    name = name.strip()[:31] or f"Table {fallback_index}"
    return name
