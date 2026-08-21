import json
import uuid
from typing import List, Dict, Any
from pydantic_schemas import ParsingResult, YearFinancialOutput, ExceptionItem, ExtractedValue
from civil_code_math_engine import check_quadratura

def mock_llm_parse_pdf(file_content: bytes) -> Dict[str, Any]:
    # In a real scenario, this uses an LLM with structured output to parse the PDF.
    # Here we mock the LLM output that might contain low confidence values.
    # We will pretend the LLM found 'Ricavi' with low confidence to test the Limbo.
    return {
        "ledger": [
            {
                "year": 2025,
                "isQuadrato": False,
                "ricavi": {
                    "value": 1000.0,
                    "confidence": 0.80, # < 0.85, should go to limbo
                    "source_page": 1,
                    "source_snippet": "Ricavi vendite 1000",
                    "suggested_mapping": "ricavi",
                    "description": "Ricavi netti"
                },
                "altri_ricavi": {
                    "value": 200.0,
                    "confidence": 0.95,
                    "source_page": 1,
                    "source_snippet": "Altri ricavi 200",
                    "suggested_mapping": "altri_ricavi",
                    "description": "Altri ricavi"
                },
                "tot_ricavi": {
                    "value": 1500.0, # Math delta: 1000 + 200 != 1500, but ricavi goes to limbo anyway.
                    "confidence": 0.90,
                    "source_page": 1,
                    "source_snippet": "Totale 1500",
                    "suggested_mapping": "tot_ricavi",
                    "description": "Totale ricavi"
                }
            }
        ]
    }

def process_document(file_content: bytes) -> ParsingResult:
    # 1. LLM parses the document
    raw_output = mock_llm_parse_pdf(file_content)
    
    exceptions = []
    processed_ledger = []
    
    # 2. Filter by confidence
    for raw_year in raw_output.get("ledger", []):
        year_obj = YearFinancialOutput(year=raw_year["year"])
        
        # Check each field
        for field in ["ricavi", "altri_ricavi", "tot_ricavi", "costi", "tot_costi"]:
            if field in raw_year and raw_year[field] is not None:
                val = raw_year[field]
                conf = val.get("confidence", 1.0)
                if conf < 0.85:
                    # Move to Limbo
                    exceptions.append(ExceptionItem(
                        id=str(uuid.uuid4()),
                        description=val.get("description", ""),
                        suggested_mapping=field,
                        year=raw_year["year"],
                        amount=val.get("value", 0.0),
                        type="unmapped_text",
                        confidence=conf
                    ))
                else:
                    # Keep in ledger
                    setattr(year_obj, field, ExtractedValue(**val))
                    
        # 3. Math Engine check
        math_exceptions = check_quadratura(year_obj)
        exceptions.extend(math_exceptions)
        
        processed_ledger.append(year_obj)
        
    return ParsingResult(ledger=processed_ledger, exceptions_queue=exceptions)
