import fitz  # PyMuPDF
import pandas as pd
from typing import Any, List, Dict
from logger import logger

class BOQLayoutParser:
    """
    Specialised parser for BOQ files where text is fragmented into narrow virtual columns.
    It uses coordinate-based text reconstruction (Reflow) to merge split sentences.
    """
    def __init__(self, col_thresholds: List[float] = None):
        # Default BOQ column X-coordinates (approximate, will be auto-tuned)
        # Item | Description | Unit | Qty | Rate | Amount
        self.col_thresholds = col_thresholds or [0, 50, 350, 400, 450, 500]

    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        try:
            doc = fitz.open(pdf_path)
            all_rows = []
            
            for page_num, page in enumerate(doc):
                logger.info(f"[BOQ Parser] Processing page {page_num + 1}")
                
                # Get all words with their bounding boxes (x0, y0, x1, y1, word, block_no, line_no, word_no)
                words = page.get_words()
                if not words: continue
                
                # Group words into lines based on Y coordinate (with 3px tolerance)
                lines: Dict[int, List[tuple]] = {}
                for w in words:
                    y_coord = int(w[1]) # Use y0
                    found_line = False
                    for line_y in lines:
                        if abs(line_y - y_coord) < 3:
                            lines[line_y].append(w)
                            found_line = True
                            break
                    if not found_line:
                        lines[y_coord] = [w]
                
                # Process lines from top to bottom
                sorted_y = sorted(lines.keys())
                for y in sorted_y:
                    line_words = sorted(lines[y], key=lambda x: x[0]) # Sort by x0
                    
                    # Reconstruct row based on X coordinates
                    # We'll map words to standard BOQ columns
                    row = [""] * 6 # Item, Description, Unit, Qty, Rate, Amount
                    
                    description_parts = []
                    for w in line_words:
                        x0 = w[0]
                        text = w[4]
                        
                        # Logic to determine which column the word belongs to
                        # This is a simplified version, real BOQs might need dynamic column detection
                        if x0 < 50: # Item No
                            row[0] += " " + text
                        elif 50 <= x0 < 350: # Description (The fragmented part)
                            description_parts.append(text)
                        elif 350 <= x0 < 400: # Unit
                            row[2] += " " + text
                        elif 400 <= x0 < 450: # Qty
                            row[3] += " " + text
                        elif 450 <= x0 < 500: # Rate
                            row[4] += " " + text
                        else: # Amount
                            row[5] += " " + text
                    
                    # Merge fragmented description
                    row[1] = " ".join(description_parts).strip()
                    row = [c.strip() for c in row]
                    
                    # Only add rows that have at least some content in description or item no
                    if row[0] or row[1]:
                        all_rows.append(row)

            if all_rows:
                df = pd.DataFrame(all_rows, columns=["Item No", "Description", "Unit", "Quantity", "Rate", "Amount"])
                # Post-processing: Merge multi-line descriptions
                final_df = self._merge_multiline_descriptions(df)
                
                results.append({
                    "page": "All",
                    "title": "BOQ Extracted Table",
                    "dataframe": final_df,
                    "headers": final_df.columns.tolist(),
                    "rows": final_df.values.tolist()
                })
            
            doc.close()
        except Exception as e:
            logger.error(f"BOQ Layout Parser error: {e}")
            
        return results

    def _merge_multiline_descriptions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        In BOQs, a single item description often spans multiple rows.
        This merges rows where 'Item No' is empty into the previous row's description.
        """
        merged_rows = []
        current_row = None
        
        for _, row in df.iterrows():
            if row["Item No"]: # New item starts
                if current_row is not None:
                    merged_rows.append(current_row)
                current_row = row.tolist()
            else: # Continuation of previous description
                if current_row is not None:
                    current_row[1] += " " + str(row["Description"])
                    # Also try to capture Qty/Rate if they were on a different line (rare but happens)
                    for i in [2, 3, 4, 5]:
                        if not current_row[i] and row[i]:
                            current_row[i] = row[i]
                else:
                    # First row has no Item No, just start it
                    current_row = row.tolist()
        
        if current_row is not None:
            merged_rows.append(current_row)
            
        return pd.DataFrame(merged_rows, columns=df.columns)
