import fitz
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from models_document import ParsedDocument
from logger import logger

class BOQParser(BaseParser):
    def __init__(self):
        # Default columns for BOQ - will be adjusted if headers are found
        self.default_cols = [
            {"name": "Item No", "x_range": (0, 75)},
            {"name": "Description", "x_range": (75, 350)},
            {"name": "Unit", "x_range": (350, 385)},
            {"name": "Quantity", "x_range": (385, 450)},
            {"name": "Rate", "x_range": (450, 520)},
            {"name": "Amount", "x_range": (520, 1000)}
        ]

    def parse(self, pdf_path: str) -> ParsedDocument:
        full_text = ""
        tables = []
        try:
            doc = fitz.open(pdf_path)
            all_rows = []
            
            for page_num, page in enumerate(doc):
                page_text = page.get_text()
                full_text += f"--- Page {page_num+1} ---\n{page_text}\n"
                
                # 1. Coordinate Analysis: Get all words with Bboxes
                words = page.get_text("words") # (x0, y0, x1, y1, "word", block_no, line_no, word_no)
                
                # 2. Reflow Algorithm: Group words into lines based on Y coordinate
                lines = {}
                for w in words:
                    y0, y1 = w[1], w[3]
                    mid_y = (y0 + y1) / 2
                    
                    found_line = False
                    for ly in lines:
                        if abs(ly - mid_y) < 4: # Tolerance for line alignment
                            lines[ly].append(w)
                            found_line = True
                            break
                    if not found_line:
                        lines[mid_y] = [w]
                
                # 3. Process lines in vertical order
                sorted_y = sorted(lines.keys())
                for y in sorted_y:
                    # Ignore headers/footers based on Y position
                    if y < 80 or y > 800: continue
                    
                    line_words = sorted(lines[y], key=lambda x: x[0])
                    row = [""] * 6
                    
                    for w in line_words:
                        x0, text = w[0], w[4]
                        # Clean artifacts
                        if text in ["|", "_", "Page", "of"]: continue
                        
                        # Map text to columns based on X coordinates
                        for i, col in enumerate(self.default_cols):
                            xr = col["x_range"]
                            if xr[0] <= x0 < xr[1]:
                                row[i] = (row[i] + " " + text).strip()
                                break
                    
                    # Filter out header-like rows
                    if "item" in row[0].lower() or "description" in row[1].lower(): continue
                    
                    if any(row):
                        all_rows.append(row)
            
            # 4. Multiline Merging: Merge rows belonging to the same Item No
            if all_rows:
                df = pd.DataFrame(all_rows, columns=[c["name"] for c in self.default_cols])
                final_df = self._merge_logic(df)
                
                tables.append({
                    "title": "BOQ_Extracted_Data",
                    "dataframe": final_df,
                    "page": 1
                })
            
            doc.close()
        except Exception as e:
            logger.error(f"BOQ Layout Parser error: {e}")
            
        return ParsedDocument(
            doc_type="boq",
            text=full_text,
            tables=tables,
            metadata={"pages": len(doc) if 'doc' in locals() else 0, "method": "BOQ Layout Parser (Reflow)"}
        )

    def _merge_logic(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Merges multiline descriptions and aligns data to the correct Item No.
        """
        merged_rows = []
        current_row = None
        
        for _, row in df.iterrows():
            item_no = str(row["Item No"]).strip()
            
            # New row starts if Item No has a digit (e.g., 1.1, 2, 3/A)
            is_new_item = item_no and any(c.isdigit() for c in item_no)
            
            if is_new_item:
                if current_row:
                    merged_rows.append(current_row)
                current_row = row.tolist()
            elif current_row:
                # This is a continuation of the previous row's description
                desc_cont = str(row["Description"]).strip()
                if desc_cont:
                    current_row[1] = (current_row[1] + " " + desc_cont).strip()
                
                # Also try to fill other numeric columns if they were empty
                for i in range(2, 6):
                    val = str(row.iloc[i]).strip()
                    if val and not str(current_row[i]).strip():
                        current_row[i] = val
            else:
                # First row doesn't have an item number? Start it anyway
                if any(str(v).strip() for v in row):
                    current_row = row.tolist()
        
        if current_row:
            merged_rows.append(current_row)
            
        return pd.DataFrame(merged_rows, columns=df.columns)
