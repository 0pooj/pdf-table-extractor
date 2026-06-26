from __future__ import annotations

from typing import Any
from openpyxl import Workbook


def export_to_excel(tables: list[dict[str, Any]], output_path: str) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Table", "Rows", "Columns", "Sheet"])

    for i, table in enumerate(tables, start=1):
        df = table["dataframe"]
        sheet_name = f"Table_{i}"
        ws = wb.create_sheet(sheet_name)

        rows = df.values.tolist()
        headers = [str(c) for c in df.columns.tolist()]

        ws.append(headers)

        for row in rows:
            ws.append([("" if v is None else str(v)) for v in row])

        summary.append([i, len(rows), len(headers), sheet_name])

    wb.save(output_path)
