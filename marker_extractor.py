"""
Marker-based table extractor (fallback).
Marker converts the PDF to Markdown; we then parse markdown tables.
Good for scanned or image-heavy engineering PDFs where Docling struggles.
"""
from __future__ import annotations

import re
import io
import pandas as pd
from typing import Any


class MarkerExtractor:
    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        """
        Returns a list of dicts:
          { "title": str, "page": int | None, "dataframe": pd.DataFrame }
        """
        markdown_text = self._pdf_to_markdown(pdf_path)
        return self._parse_markdown_tables(markdown_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pdf_to_markdown(self, pdf_path: str) -> str:
        """Run marker-pdf and return full markdown string."""
        from marker.convert import convert_single_pdf
        from marker.models import load_all_models

        models = load_all_models()
        full_text, _, _ = convert_single_pdf(pdf_path, models)
        return full_text

    def _parse_markdown_tables(self, text: str) -> list[dict[str, Any]]:
        """
        Extract all GFM-style markdown tables from the converted text.
        Attempts to recover a caption from the line immediately before the table.
        """
        lines = text.splitlines()
        tables = []
        i = 0
        table_idx = 0

        while i < len(lines):
            line = lines[i]
            # Detect start of a markdown table (row beginning with |)
            if _is_table_row(line):
                table_lines = []
                caption_line = lines[i - 1].strip() if i > 0 else ""

                while i < len(lines) and _is_table_row(lines[i]):
                    table_lines.append(lines[i])
                    i += 1

                # Need at least header + separator + one data row
                if len(table_lines) < 3:
                    continue

                df = _table_lines_to_df(table_lines)
                if df is None or df.empty:
                    continue

                table_idx += 1
                title = caption_line if caption_line else f"Table {table_idx}"
                tables.append({"title": title, "page": None, "dataframe": df})
            else:
                i += 1

        return tables


# -----------------------------------------------------------------------
# Helpers (module-level)
# -----------------------------------------------------------------------

def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _table_lines_to_df(lines: list[str]) -> pd.DataFrame | None:
    """Parse GFM table lines into a DataFrame."""
    try:
        # Remove separator row (---|---|---)
        data_lines = [l for l in lines if not re.match(r"^\s*\|[-:| ]+\|\s*$", l)]
        if len(data_lines) < 2:
            return None

        def parse_row(line: str) -> list[str]:
            return [cell.strip() for cell in line.strip().strip("|").split("|")]

        headers = parse_row(data_lines[0])
        rows = [parse_row(l) for l in data_lines[1:]]

        # Pad/trim rows to header length
        n = len(headers)
        rows = [r[:n] + [""] * max(0, n - len(r)) for r in rows]

        df = pd.DataFrame(rows, columns=headers)
        df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        return df if not df.empty else None
    except Exception as e:
        print(f"[Marker] Table parse error: {e}")
        return None
