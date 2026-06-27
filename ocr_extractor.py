import pytesseract
import numpy as np
import cv2
from PIL import Image
import pandas as pd
from typing import Any
from logger import logger
from pymupdf_extractor import render_page_to_image

class OcrFallbackExtractor:
    """
    Advanced OCR Extractor with image preprocessing.
    Uses Tesseract with ara+eng support and custom column reconstruction.
    """
    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        import fitz
        results = []
        try:
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            doc.close()

            for page_num in range(num_pages):
                logger.info(f"[OCR] Processing page {page_num + 1}/{num_pages}")
                # Render page to high-res image
                img = render_page_to_image(pdf_path, page_num, dpi=300)
                
                # Preprocess image for better OCR
                processed_img = self._preprocess_image(img)
                
                # Get OCR data with bounding boxes
                data = pytesseract.image_to_data(processed_img, lang='ara+eng', output_type=pytesseract.Output.DICT)
                
                df = self._reconstruct_table_from_data(data)
                if df is not None and not df.empty:
                    results.append({
                        "page": page_num + 1,
                        "title": f"OCR Table (p.{page_num + 1})",
                        "dataframe": df,
                        "headers": [str(c) for c in df.columns],
                        "rows": df.values.tolist()
                    })
            
            logger.info(f"[OCR] Extracted {len(results)} tables via advanced OCR")
        except Exception as e:
            logger.error(f"OCR extraction error: {e}")
            
        return results

    def _preprocess_image(self, pil_img):
        """Enhance image for OCR: grayscale, thresholding, noise removal."""
        open_cv_image = np.array(pil_img)
        # Convert RGB to BGR
        if len(open_cv_image.shape) == 3:
            open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
        
        gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
        
        # Denoising
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # Thresholding
        thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        return Image.fromarray(thresh)

    def _reconstruct_table_from_data(self, data) -> pd.DataFrame | None:
        """Groups OCR text into rows and columns based on coordinates."""
        n_boxes = len(data['text'])
        lines = {}
        
        for i in range(n_boxes):
            conf = int(data['conf'][i])
            if conf < 30: continue 
            text = str(data['text'][i]).strip()
            if not text: continue
            
            top, left = data['top'][i], data['left'][i]
            
            # Group by vertical position (rows) with a small tolerance
            found_line = False
            for line_y in lines:
                if abs(line_y - top) < 15: 
                    lines[line_y].append({'text': text, 'left': left})
                    found_line = True
                    break
            if not found_line:
                lines[top] = [{'text': text, 'left': left}]
        
        if not lines: return None
        
        # Sort lines by Y coordinate
        sorted_y = sorted(lines.keys())
        
        # Identify columns by clustering X coordinates
        all_lefts = []
        for y in sorted_y:
            for word in lines[y]:
                all_lefts.append(word['left'])
        
        if not all_lefts: return None
        
        # Simple clustering for columns
        all_lefts.sort()
        clusters = []
        if all_lefts:
            curr_cluster = [all_lefts[0]]
            for x in all_lefts[1:]:
                if x - curr_cluster[-1] < 40: # 40px gap for same column
                    curr_cluster.append(x)
                else:
                    clusters.append(sum(curr_cluster)/len(curr_cluster))
                    curr_cluster = [x]
            clusters.append(sum(curr_cluster)/len(curr_cluster))
        
        # Reconstruct rows based on clusters
        final_rows = []
        for y in sorted_y:
            row = [""] * len(clusters)
            for word in lines[y]:
                # Find best cluster
                best_idx = 0
                min_dist = float('inf')
                for idx, c_x in enumerate(clusters):
                    dist = abs(word['left'] - c_x)
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = idx
                
                if row[best_idx]:
                    row[best_idx] += " " + word['text']
                else:
                    row[best_idx] = word['text']
            final_rows.append(row)
            
        if not final_rows: return None
        
        df = pd.DataFrame(final_rows)
        # Clean up: remove completely empty rows
        df = df[~df.apply(lambda r: all(str(v).strip() == "" for v in r), axis=1)]
        return df.reset_index(drop=True)
