import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from models_document import ParsedDocument
from logger import logger

class BOQParser(BaseParser):
    def __init__(self):
        self.cols = [
            {"name": "Item No", "x_range": (0, 71)},
            {"name": "Description", "x_range": (71, 354)},
            {"name": "Unit", "x_range": (354, 376)},
            {"name": "Quantity", "x_range": (376, 442)},
            {"name": "Rate", "x_range": (442, 511)},
            {"name": "Amount", "x_range": (511, 1000)}
        ]

    def can_handle(self, text: str) -> bool:
        keywords = ["bill of quantities", "boq", "item no", "quantity", "rate", "amount", "unit"]
        text_lower = text.lower()
        matches = [k for k in keywords if k in text_lower]
        return len(matches) >= 3

    def parse(self, pdf_path: str) -> ParsedDocument:
        full_text = ""
        tables = []
        try:
            doc = fitz.open(pdf_path)
            all_rows = []
            for page in doc:
                full_text += page.get_text()
                words = page.get_text("words")
                lines = {}
                for w in words:
                    y = int(w[1])
                    found = False
                    for ly in lines:
                        if abs(ly - y) < 3:
                            lines[ly].append(w)
                            found = True
                            break
                    if not found: lines[y] = [w]
                
                sorted_y = sorted(lines.keys())
                for y in sorted_y:
                    if y < 60: continue
                    line_words = sorted(lines[y], key=lambda x: x[0])
                    row = [""] * 6
                    for w in line_words:
                        x0 = w[0]
                        text = w[4]
                        for i, col in enumerate(self.cols):
                            xr = col["x_range"]
                            if xr[0] <= x0 < xr[1]:
                                row[i] = (row[i] + " " + text).strip()
                                break
                    if any(row): all_rows.append(row)
            
            if all_rows:
                df = pd.DataFrame(all_rows, columns=[c["name"] for c in self.cols])
                final_df = self._merge_multiline(df)
                tables.append({
                    "title": "BOQ Data",
                    "dataframe": final_df,
                    "page": 1
                })
            doc.close()
        except Exception as e:
            logger.error(f"BOQParser error: {e}")
            
        return ParsedDocument(
            doc_type="boq",
            text=full_text,
            tables=tables,
            metadata={"pages": len(doc) if 'doc' in locals() else 0}
        )

    def _merge_multiline(self, df: pd.DataFrame) -> pd.DataFrame:
        merged = []
        current = None
        for _, row in df.iterrows():
            item_no = str(row["Item No"]).strip()
            if item_no and any(c.isdigit() for c in item_no):
                if current: merged.append(current)
                current = row.tolist()
            elif current:
                current[1] = (current[1] + " " + str(row["Description"])).strip()
                col_names = ["Unit", "Quantity", "Rate", "Amount"]
                for i, col in enumerate(col_names, start=2):
                    if not current[i] and str(row[col]).strip():
                        current[i] = str(row[col]).strip()
            else:
                if str(row["Description"]).strip():
                    current = row.tolist()
                    merged.append(current)
                    current = None
        if current: merged.append(current)
        return pd.DataFrame(merged, columns=df.columns)
