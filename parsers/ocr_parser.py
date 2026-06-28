import fitz
import pytesseract
from PIL import Image
import io
from parsers.base_parser import BaseParser
from models_document import ParsedDocument

class OCRParser(BaseParser):
    def parse(self, pdf_path: str) -> ParsedDocument:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes()))
            # Support Arabic and English
            text = pytesseract.image_to_string(img, lang="ara+eng")
            full_text += text + "\n"
            
        doc.close()
        return ParsedDocument(
            doc_type="ocr",
            text=full_text,
            metadata={"pages": len(doc), "method": "Tesseract OCR"}
        )
