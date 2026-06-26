from __future__ import annotations

from typing import Any
from openpyxl import Workbook


def export_to_excel(tables: list[dict[str, Any]], output_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"

    ws.append(["Table", "Title", "Page", "Rows", "Columns", "Sheet"])

    for i, table in enumerate(tables, start=1):
        df = table["dataframe"].fillna("").astype(str)
        title = str(table.get("title", f"Table {i}"))
        page = table.get("page", "")
        sheet_name = f"Table_{i}"

        ws.append([i, title, page, len(df), len(df.columns), sheet_name])

        sheet = wb.create_sheet(sheet_name)

        sheet.append([str(c) for c in df.columns])

        for _, row in df.iterrows():
            sheet.append([str(v) for v in row.tolist()])

    wb.save(output_path)
