import fitz
import re
from parsers.base_parser import BaseParser
from models_document import ParsedDocument
from logger import logger

class DatasheetParser(BaseParser):
    def can_handle(self, text: str) -> bool:
        keywords = ["technical data", "datasheet", "ordering data", "specifications", "siemens", "schneider", "abb"]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)

    def parse(self, pdf_path: str) -> ParsedDocument:
        full_text = ""
        key_values = []
        sections = []
        tables = []
        
        try:
            doc = fitz.open(pdf_path)
            kv_pattern = re.compile(r"([^:\n]+):\s*([^\n]+)")
            
            for i, page in enumerate(doc):
                text = page.get_text()
                full_text += text
                
                # Key-Values
                matches = kv_pattern.findall(text)
                for k, v in matches:
                    if len(k.strip()) < 50 and len(v.strip()) < 100:
                        key_values.append({"key": k.strip(), "value": v.strip(), "page": i+1})
                
                # Sections
                lines = text.splitlines()
                for line in lines:
                    if line.isupper() and len(line) > 5:
                        sections.append({"title": line.strip(), "page": i+1})
                
                # Tables
                tabs = page.find_tables()
                for j, tab in enumerate(tabs):
                    df = tab.to_pandas()
                    if not df.empty:
                        tables.append({
                            "title": f"Datasheet_Table_{i+1}_{j+1}",
                            "dataframe": df,
                            "page": i + 1
                        })
            doc.close()
        except Exception as e:
            logger.error(f"DatasheetParser error: {e}")
            
        return ParsedDocument(
            doc_type="datasheet",
            text=full_text,
            key_values=key_values,
            sections=sections,
            tables=tables,
            metadata={"pages": len(doc) if 'doc' in locals() else 0}
        )
