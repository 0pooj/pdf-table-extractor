import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from logger import logger

class DatasheetParser(BaseParser):
    def can_handle(self, text: str) -> bool:
        keywords = ["technical data", "datasheet", "ordering data", "specifications", "siemens", "schneider", "abb"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        try:
            doc = fitz.open(pdf_path)
            for page_num, page in enumerate(doc):
                # Use PyMuPDF's built-in table finder for datasheets
                tabs = page.find_tables()
                for i, tab in enumerate(tabs):
                    df = tab.to_pandas()
                    if not df.empty:
                        results.append({
                            "title": f"Datasheet Table {page_num+1}_{i+1}",
                            "dataframe": df,
                            "headers": df.columns.tolist(),
                            "rows": df.values.tolist(),
                            "page": page_num + 1
                        })
            doc.close()
        except Exception as e:
            logger.error(f"DatasheetParser error: {e}")
        return results
