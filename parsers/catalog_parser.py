import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from models_document import ParsedDocument
from logger import logger

class CatalogParser(BaseParser):
    def can_handle(self, text: str) -> bool:
        keywords = ["catalogue", "catalog number", "ordering code", "product range", "price list"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def parse(self, pdf_path: str) -> ParsedDocument:
        full_text = ""
        products = []
        tables = []
        
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                text = page.get_text()
                full_text += text
                
                # Heuristic for products: Lines with codes
                lines = text.splitlines()
                for line in lines:
                    if any(c.isdigit() for c in line) and any(c.isalpha() for c in line) and "-" in line:
                        products.append({"code": line.strip(), "page": i+1})
                
                # Tables
                tabs = page.find_tables()
                for j, tab in enumerate(tabs):
                    df = tab.to_pandas()
                    if not df.empty:
                        tables.append({
                            "title": f"Catalog_Table_{i+1}_{j+1}",
                            "dataframe": df,
                            "page": i + 1
                        })
            doc.close()
        except Exception as e:
            logger.error(f"CatalogParser error: {e}")
            
        return ParsedDocument(
            doc_type="catalog",
            text=full_text,
            products=products,
            tables=tables,
            metadata={"pages": len(doc) if 'doc' in locals() else 0}
        )
