import fitz
import pandas as pd
from typing import Any, List, Dict
from logger import logger

class BOQLayoutParser:
    """
    Precision Parser for the specific BOQ layout provided.
    Handles coordinate-based extraction and multi-line description merging.
    """
    def __init__(self):
        # Coordinates based on actual file analysis:
        # Item No: ~30-70
        # Description: ~72-350
        # Unit: ~350-375
        # Quantity: ~377-430
        # Rate: ~443-500
        # Amount: ~512+
        self.cols = [
            {"name": "Item No", "x_range": (0, 71)},
            {"name": "Description", "x_range": (71, 354)},
            {"name": "Unit", "x_range": (354, 376)},
            {"name": "Quantity", "x_range": (376, 442)},
            {"name": "Rate", "x_range": (442, 511)},
            {"name": "Amount", "x_range": (511, 1000)}
        ]

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        try:
            doc = fitz.open(pdf_path)
            all_rows = []
            
            for page_num, page in enumerate(doc):
                words = page.get_text("words")
                if not words: continue
                
                # Group by Y coordinate
                lines: Dict[int, List[tuple]] = {}
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
                    line_words = sorted(lines[y], key=lambda x: x[0])
                    
                    # Ignore headers and footers
                    row_text = " ".join([w[4] for w in line_words])
                    if "EPUTUKEZI" in row_text or "eputikezi@" in row_text: continue
                    if y < 60: continue # Header area
                    
                    row = [""] * 6
                    for w in line_words:
                        x0 = w[0]
                        text = w[4]
                        
                        # Map word to column based on X coordinate
                        for i, col in enumerate(self.cols):
                            if col["x_range"][0] <= x0 < col["x_range"][1]:
                                row[i] = (row[i] + " " + text).strip()
                                break
                    
                    # Basic cleanup
                    if any(row):
                        all_rows.append(row)

            if all_rows:
                df = pd.DataFrame(all_rows, columns=[c["name"] for c in self.cols])
                final_df = self._clean_and_merge(df)
                
                results.append({
                    "page": "All",
                    "title": "BOQ Extracted Data",
                    "dataframe": final_df,
                    "headers": final_df.columns.tolist(),
                    "rows": final_df.values.tolist()
                })
            doc.close()
        except Exception as e:
            logger.error(f"Custom BOQ Parser error: {e}")
            
        return results

    def _clean_and_merge(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge multi-line descriptions and filter noise.
        """
        merged = []
        current = None
        
        # Keywords to ignore
        ignore = ["Item", "No", "Quantity", "Rate", "Amount", "Brought Forward", "Carried Forward"]
        
        for _, row in df.iterrows():
            item_no = str(row["Item No"]).strip()
            desc = str(row["Description"]).strip()
            
            # Skip header rows
            if desc in ignore or item_no == "Item": continue
            if not any(row.values): continue
            
            # If we have an Item No, it's a new entry
            if item_no and any(c.isdigit() for c in item_no):
                if current: merged.append(current)
                current = row.tolist()
            elif current:
                # Continuation of description
                if desc:
                    current[1] = (current[1] + " " + desc).strip()
                # If Qty/Rate/Amount appear on a sub-line, fill them
                for i in range(2, 6):
                    if not current[i] and row[i]:
                        current[i] = row[i]
            else:
                # No current item, but we have text - could be a section header
                if desc:
                    current = row.tolist()
                    merged.append(current)
                    current = None
        
        if current: merged.append(current)
        
        # Final pass: remove empty rows and format numbers
        clean_data = []
        for r in merged:
            if not r[1]: continue # Skip if no description
            clean_data.append(r)
            
        return pd.DataFrame(clean_data, columns=df.columns)
