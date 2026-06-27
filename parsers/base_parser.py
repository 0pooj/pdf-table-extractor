from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseParser(ABC):
    """
    Abstract Base Class for all specialized parsers.
    Ensures a consistent interface across different document types.
    """
    @abstractmethod
    def extract(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Main extraction method to be implemented by each parser.
        Returns a list of table dictionaries.
        """
        pass

    @abstractmethod
    def can_handle(self, first_page_text: str) -> bool:
        """
        Check if this parser is suitable for the given document content.
        """
        pass
