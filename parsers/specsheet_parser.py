import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from logger import logger

class SpecSheetParser(BaseParser):
    def can_handle(self, text: str) -> bool:
        keywords = ["specification", "section", "general requirements", "technical specification"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        # SpecSheet logic focuses on maintaining hierarchy
        results = []
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text = page.get_text("blocks")
                # Simple logic to extract section-like structures as tables
                data = []
                for b in text:
                    content = b[4].strip()
                    if content:
                        data.append([content])
                if data:
                    df = pd.DataFrame(data, columns=["Content"])
                    results.append({
                        "title": "Specification Content",
                        "dataframe": df,
                        "headers": df.columns.tolist(),
                        "rows": df.values.tolist()
                    })
            doc.close()
        except Exception as e:
            logger.error(f"SpecSheetParser error: {e}")
        return results
