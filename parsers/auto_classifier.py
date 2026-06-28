import fitz
from typing import Type
from parsers.base_parser import BaseParser
from parsers.boq_parser import BOQParser
from parsers.datasheet_parser import DatasheetParser
from parsers.catalog_parser import CatalogParser
from parsers.specsheet_parser import SpecSheetParser
from logger import logger

class AutoClassifier:
    """
    Analyzes the document and routes it to the most suitable specialized parser.
    """
    def __init__(self):
        # Order matters: check most specific types first
        self.parsers = [
            BOQParser(),
            CatalogParser(),
            DatasheetParser(),
            SpecSheetParser()
        ]

    def classify_and_extract(self, pdf_path: str, forced_type: str = "auto") -> tuple[list, str]:
        # If user forced a specific type
        if forced_type != "auto":
            for p in self.parsers:
                if p.__class__.__name__.lower().replace("parser", "") == forced_type.lower():
                    logger.info(f"Using forced parser: {p.__class__.__name__}")
                    return p.extract(pdf_path), p.__class__.__name__

        # Auto-detection logic
        try:
            doc = fitz.open(pdf_path)
            # Analyze first two pages for classification
            sample_text = ""
            for i in range(min(2, len(doc))):
                sample_text += doc[i].get_text()
            doc.close()
            
            for p in self.parsers:
                if p.can_handle(sample_text):
                    logger.info(f"Auto-detected document type. Using: {p.__class__.__name__}")
                    return p.extract(pdf_path), p.__class__.__name__
            
            # Default to BOQParser if nothing matches (or we can add a GenericParser)
            logger.info("No specific parser matched. Defaulting to BOQParser.")
            return BOQParser().extract(pdf_path), "BOQParser (Default)"
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return [], "Error"
