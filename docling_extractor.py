"""
Docling-based table extractor.
"""
from __future__ import annotations

from typing import Any
import pandas as pd


class DoclingExtractor:
    def __init__(self):
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
        from docling.datamodel.base_models import InputFormat

        options = PdfPipelineOptions()
        options.do_ocr = True
        options.ocr_options = TesseractCliOcrOptions(lang=["eng"])
        options.do_table_structure = True
        options.table_structure_options.do_cell_matching = True

        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options)
            }
        )

    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        result = self._converter.convert(pdf_path)
        doc = result.document

        tables = []

        for i, table in enumerate(doc.tables):
            try:
                df = table.export_to_dataframe()

                if df is None or df.empty:
                    continue

                df = _clean_dataframe(df)

                title = f"Table {i + 1}"
                page_no = None

                if hasattr(table, "caption") and table.caption:
                    title = str(table.caption).strip() or title

                if hasattr(table, "prov") and table.prov:
                    page_no = table.prov[0].page_no

                headers = [str(c) for c in df.columns]
                rows = df.fillna("").astype(str).values.tolist()

                tables.append({
                    "title": title,
                    "page": page_no,
                    "headers": headers,
                    "rows": rows,
                })

            except Exception as e:
                print(f"[Docling] Skipping table {i}: {e}")

        return tables


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.map(lambda x: str(x).strip() if pd.notna(x) else x)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.reset_index(drop=True)
    return df
