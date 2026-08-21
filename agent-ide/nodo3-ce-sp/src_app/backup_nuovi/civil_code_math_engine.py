from typing import List
import uuid
from pydantic_schemas import YearFinancialOutput, ExceptionItem

def check_quadratura(ledger_year: YearFinancialOutput) -> List[ExceptionItem]:
    exceptions = []
    
    ricavi_val = ledger_year.ricavi.value if ledger_year.ricavi else 0.0
    altri_val = ledger_year.altri_ricavi.value if ledger_year.altri_ricavi else 0.0
    tot_ricavi_val = ledger_year.tot_ricavi.value if ledger_year.tot_ricavi else 0.0
    
    if abs((ricavi_val + altri_val) - tot_ricavi_val) > 0.01:
        exceptions.append(ExceptionItem(
            id=str(uuid.uuid4()),
            description="Delta Ricavi: Somma di Ricavi e Altri Ricavi non coincide con Totale Ricavi",
            suggested_mapping="tot_ricavi",
            year=ledger_year.year,
            amount=abs((ricavi_val + altri_val) - tot_ricavi_val),
            type="math_delta"
        ))
        
    costi_val = ledger_year.costi.value if ledger_year.costi else 0.0
    tot_costi_val = ledger_year.tot_costi.value if ledger_year.tot_costi else 0.0
    
    if abs(costi_val - tot_costi_val) > 0.01:
        exceptions.append(ExceptionItem(
            id=str(uuid.uuid4()),
            description="Delta Costi: Costi non coincide con Totale Costi",
            suggested_mapping="tot_costi",
            year=ledger_year.year,
            amount=abs(costi_val - tot_costi_val),
            type="math_delta"
        ))
        
    ledger_year.isQuadrato = (len(exceptions) == 0)
    return exceptions
