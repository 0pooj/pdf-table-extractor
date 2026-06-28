from dataclasses import dataclass, field
from typing import Any
import pandas as pd

@dataclass
class ParsedDocument:
    doc_type: str = "generic"
    text: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    key_values: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
