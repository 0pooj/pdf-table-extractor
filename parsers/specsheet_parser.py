import fitz
import pandas as pd
from typing import List, Dict, Any
from parsers.base_parser import BaseParser
from models_document import ParsedDocument
from logger import logger

class SpecSheetParser(BaseParser):
    def can_handle(self, text: str) -> bool:
        keywords = ["specification", "section", "general requirements", "technical specification"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def parse(self, pdf_path: str) -> ParsedDocument:
        full_text = ""
        sections = []
        
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                text = page.get_text()
                full_text += text
                
                # Heuristic for sections: Numbered sections
                lines = text.splitlines()
                for line in lines:
                    line = line.strip()
                    if line and line[0].isdigit() and "." in line[:5]:
                        sections.append({"title": line, "page": i+1})
            doc.close()
        except Exception as e:
            logger.error(f"SpecSheetParser error: {e}")
            
        return ParsedDocument(
            doc_type="specsheet",
            text=full_text,
            sections=sections,
            metadata={"pages": len(doc) if 'doc' in locals() else 0}
        )
