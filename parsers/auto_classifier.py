import fitz
from parsers.boq_parser import BOQParser
from parsers.datasheet_parser import DatasheetParser
from parsers.catalog_parser import CatalogParser
from parsers.specsheet_parser import SpecSheetParser
from parsers.generic_parser import GenericParser
from parsers.ocr_parser import OCRParser
from models_document import ParsedDocument
from logger import logger

class AutoClassifier:
    def __init__(self):
        self.parsers = {
            "boq": BOQParser(),
            "datasheet": DatasheetParser(),
            "catalog": CatalogParser(),
            "specsheet": SpecSheetParser(),
            "generic": GenericParser(),
            "ocr": OCRParser()
        }

    def classify_and_extract(self, pdf_path: str, mode: str = "auto") -> ParsedDocument:
        if mode != "auto" and mode in self.parsers:
            logger.info(f"Using manually selected parser: {mode}")
            return self.parsers[mode].parse(pdf_path)

        # Auto-detection logic
        doc = fitz.open(pdf_path)
        text = ""
        for i in range(min(2, len(doc))):
            text += doc[i].get_text().lower()
        doc.close()

        selected_mode = "generic"
        if "bill of quantities" in text or "boq" in text or "item no" in text:
            selected_mode = "boq"
        elif "technical data" in text or "datasheet" in text or "siemens" in text or "schneider" in text:
            selected_mode = "datasheet"
        elif "catalog" in text or "ordering code" in text:
            selected_mode = "catalog"
        elif "specification" in text or "section" in text:
            selected_mode = "specsheet"
        
        if len(text.strip()) < 50:
            selected_mode = "ocr"

        logger.info(f"Auto-detected document type: {selected_mode}")
        doc_data = self.parsers[selected_mode].parse(pdf_path)
        doc_data.metadata["method"] = f"Auto-Classifier ({selected_mode})"
        return doc_data
