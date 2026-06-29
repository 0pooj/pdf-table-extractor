import fitz
import pytesseract
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import io
from parsers.base_parser import BaseParser
from models_document import ParsedDocument
from logger import logger

class OCRParser(BaseParser):
    def parse(self, pdf_path: str) -> ParsedDocument:
        doc = fitz.open(pdf_path)
        full_text = ""
        tables = []
        
        for page_num, page in enumerate(doc):
            # 1. High-res Rendering
            pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
            img_bytes = pix.tobytes()
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # 2. Image Preprocessing for better OCR
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            
            # 3. Extract Text (Arabic + English)
            text = pytesseract.image_to_string(thresh, lang="ara+eng")
            full_text += f"--- Page {page_num+1} ---\n{text}\n"
            
            # 4. Attempt Table Extraction from Image
            try:
                data = pytesseract.image_to_data(thresh, lang="ara+eng", output_type=pytesseract.Output.DICT)
                df = self._reconstruct_table_from_ocr(data)
                if not df.empty:
                    tables.append({
                        "title": f"OCR_Table_Page_{page_num+1}",
                        "dataframe": df,
                        "page": page_num + 1
                    })
            except Exception as e:
                logger.error(f"OCR Table extraction error on page {page_num+1}: {e}")
            
        doc.close()
        return ParsedDocument(
            doc_type="ocr",
            text=full_text,
            tables=tables,
            metadata={"pages": len(doc), "method": "Advanced OCR with OpenCV"}
        )

    def _reconstruct_table_from_ocr(self, data: dict) -> pd.DataFrame:
        """
        Groups OCR words into rows and columns based on spatial coordinates.
        """
        n_boxes = len(data['text'])
        rows = {}
        for i in range(n_boxes):
            if int(data['conf'][i]) < 30: continue  # Filter low confidence
            text = data['text'][i].strip()
            if not text: continue
            
            x, y = data['left'][i], data['top'][i]
            # Group by Y coordinate (rows)
            found_row = False
            for ry in rows:
                if abs(ry - y) < 15:  # Tolerance for row alignment
                    rows[ry].append((x, text))
                    found_row = True
                    break
            if not found_row:
                rows[y] = [(x, text)]
        
        if not rows: return pd.DataFrame()
        
        # Sort rows and words in rows
        sorted_rows = []
        for y in sorted(rows.keys()):
            row_data = sorted(rows[y], key=lambda x: x[0])
            sorted_rows.append([w[1] for w in row_data])
            
        return pd.DataFrame(sorted_rows)
