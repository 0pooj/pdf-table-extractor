import fitz
from parsers.base_parser import BaseParser
from models_document import ParsedDocument

class GenericParser(BaseParser):
    def parse(self, pdf_path: str) -> ParsedDocument:
        doc = fitz.open(pdf_path)
        full_text = ""
        tables = []
        
        for i, page in enumerate(doc):
            full_text += page.get_text()
            # Simple table extraction using PyMuPDF's find_tables
            try:
                tabs = page.find_tables()
                for j, tab in enumerate(tabs):
                    df = tab.to_pandas()
                    if not df.empty:
                        tables.append({
                            "title": f"Page_{i+1}_Table_{j+1}",
                            "page": i + 1,
                            "dataframe": df
                        })
            except:
                pass
                
        doc.close()
        return ParsedDocument(
            doc_type="generic",
            text=full_text,
            tables=tables,
            metadata={"pages": len(doc)}
        )
