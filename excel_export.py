from __future__ import annotations

from typing import Any
from openpyxl import Workbook


def export_to_excel(tables: list[dict[str, Any]], output_path: str) -> None:
    wb = Workbook()

    summary = wb.active
    summary.title = "Summary"
    summary.append(["Table", "Title", "Page", "Rows", "Columns", "Sheet"])

    for i, table in enumerate(tables, start=1):
        sheet_name = f"Table_{i}"

        headers = table.get("headers", [])
        rows = table.get("rows", [])

        summary.append([
            i,
            table.get("title", f"Table {i}"),
            table.get("page", ""),
            len(rows),
            len(headers),
            sheet_name,
        ])

        ws = wb.create_sheet(sheet_name)

        if headers:
            ws.append(headers)

        for row in rows:
            ws.append(row)

    wb.save(output_path)
