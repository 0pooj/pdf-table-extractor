import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from logger import logger

class CatalogParser(BaseParser):
    def can_handle(self, text: str) -> bool:
        keywords = ["catalogue", "catalog number", "ordering code", "product range", "price list"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        # Catalog logic focuses on identifying product codes and prices
        results = []
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                tabs = page.find_tables()
                for tab in tabs:
                    df = tab.to_pandas()
                    if not df.empty:
                        results.append({
                            "title": "Catalog Data",
                            "dataframe": df,
                            "headers": df.columns.tolist(),
                            "rows": df.values.tolist()
                        })
            doc.close()
        except Exception as e:
            logger.error(f"CatalogParser error: {e}")
        return results
