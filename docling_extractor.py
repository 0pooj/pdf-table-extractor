"""
Docling-based table extractor.
Docling excels at structured documents (data sheets, spec tables, BOM tables).
"""
from __future__ import annotations

import pandas as pd
from typing import Any


class DoclingExtractor:
    def __init__(self):
        # Import lazily so the app starts even if docling isn't installed yet
        from docling.document_converter import DocumentConverter
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import PdfFormatOption

        options = PdfPipelineOptions()
        options.do_table_structure = True
        options.table_structure_options.do_cell_matching = True

        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options)
            }
        )

    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        """
        Returns a list of dicts:
          { "title": str, "page": int, "dataframe": pd.DataFrame }
        """
        result = self._converter.convert(pdf_path)
        doc = result.document

        tables = []
        for i, table in enumerate(doc.tables):
            try:
                df = table.export_to_dataframe()
                if df is None or df.empty:
                    continue
                df = _clean_dataframe(df)

                # Try to grab a caption / title from the document
                title = f"Table {i + 1}"
                if hasattr(table, "caption") and table.caption:
                    title = str(table.caption).strip() or title

                page_no = None
                if hasattr(table, "prov") and table.prov:
                    page_no = table.prov[0].page_no

                tables.append({"title": title, "page": page_no, "dataframe": df})
            except Exception as e:
                print(f"[Docling] Skipping table {i}: {e}")

        return tables


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace, drop fully-empty rows/columns."""
    df = df.applymap(lambda x: str(x).strip() if pd.notna(x) else x)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.reset_index(drop=True)
    return df
