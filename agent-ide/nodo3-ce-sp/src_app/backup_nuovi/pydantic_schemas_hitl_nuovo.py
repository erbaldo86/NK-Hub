from pydantic import BaseModel, Field
from typing import List, Optional

class ExtractedValue(BaseModel):
    value: float
    confidence: float
    source_page: int
    source_snippet: str
    suggested_mapping: str
    description: str

class ExceptionItem(BaseModel):
    id: str
    description: str
    suggested_mapping: str
    year: int
    amount: float
    type: str
    confidence: Optional[float] = None

class YearFinancialOutput(BaseModel):
    year: int
    isQuadrato: bool = False
    ricavi: Optional[ExtractedValue] = None
    altri_ricavi: Optional[ExtractedValue] = None
    tot_ricavi: Optional[ExtractedValue] = None
    costi: Optional[ExtractedValue] = None
    tot_costi: Optional[ExtractedValue] = None

class ParsingResult(BaseModel):
    ledger: List[YearFinancialOutput]
    exceptions_queue: List[ExceptionItem]
