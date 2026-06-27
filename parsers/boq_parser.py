import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
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
        keywords = ["bill of quantities", "boq", "item no", "qty", "unit price"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        try:
            doc = fitz.open(pdf_path)
            all_rows = []
            for page in doc:
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
                
                for y in sorted(lines.keys()):
                    if y < 60: continue
                    line_words = sorted(lines[y], key=lambda x: x[0])
                    row = [""] * 6
                    for w in line_words:
                        x0 = w[0]
                        text = w[4]
                        for i, col in enumerate(self.cols):
                            if col["x_range"][0] <= x0 < col["x_range"][1]:
                                row[i] = (row[i] + " " + text).strip()
                                break
                    if any(row): all_rows.append(row)
            
            if all_rows:
                df = pd.DataFrame(all_rows, columns=[c["name"] for c in self.cols])
                final_df = self._merge_multiline(df)
                results.append({
                    "title": "BOQ Data",
                    "dataframe": final_df,
                    "headers": final_df.columns.tolist(),
                    "rows": final_df.values.tolist()
                })
            doc.close()
        except Exception as e:
            logger.error(f"BOQParser error: {e}")
        return results

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
                for i in range(2, 6):
                    if not current[i] and row[i]: current[i] = row[i]
            else:
                if row["Description"]:
                    current = row.tolist()
                    merged.append(current)
                    current = None
        if current: merged.append(current)
        return pd.DataFrame(merged, columns=df.columns)
