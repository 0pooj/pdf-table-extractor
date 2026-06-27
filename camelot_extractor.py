import camelot
import pandas as pd
from typing import Any
from logger import logger

class CamelotExtractor:
    """
    Extractor using Camelot-py.
    Highly accurate for grid-based tables (Lattice) and text-alignment tables (Stream).
    """
    def extract(self, pdf_path: str) -> list[dict[str, Any]]:
        results = []
        try:
            # We try 'lattice' first as it's most accurate for BOQs with borders
            # If no tables found, we could try 'stream'
            logger.info(f"[Camelot] Extracting from {pdf_path} using lattice mode")
            tables = camelot.read_pdf(pdf_path, pages='all', flavor='lattice')
            
            if len(tables) == 0:
                logger.info(f"[Camelot] No lattice tables found, trying stream mode")
                tables = camelot.read_pdf(pdf_path, pages='all', flavor='stream')

            for i, table in enumerate(tables):
                df = table.df
                if df is not None and not df.empty:
                    # Clean headers: use first row as header if it looks like one
                    if len(df) > 1:
                        df.columns = df.iloc[0]
                        df = df[1:].reset_index(drop=True)
                    
                    results.append({
                        "page": table.page,
                        "title": f"Table {i+1} (p.{table.page})",
                        "dataframe": df,
                        "headers": [str(c) for c in df.columns],
                        "rows": df.values.tolist()
                    })
            
            logger.info(f"[Camelot] Extracted {len(results)} tables")
        except Exception as e:
            logger.error(f"Camelot extraction error: {e}")
            
        return results
