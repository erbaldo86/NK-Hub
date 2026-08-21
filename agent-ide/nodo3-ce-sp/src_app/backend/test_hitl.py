import os
import sys
import copy
from pprint import pprint
from fastapi.testclient import TestClient

# Add current dir to path
sys.path.append(os.path.dirname(__file__))

from main_api_server import app
from pydantic_schemas import HydratedState, FullFinancialInput, LedgerOperation, SplitRequest

client = TestClient(app)

def main():
    pdf_path = os.path.join(os.path.dirname(__file__), "..", "sample_data", "Bilancio_Simulato_Alfa_Spa.pdf")
    print(f"Testing with PDF: {pdf_path}")
    
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
        
    res = client.post("/api/v1/ingest/parse_pdf", files={"file": ("Bilancio_Simulato_Alfa_Spa.pdf", pdf_bytes, "application/pdf")})
    assert res.status_code == 200, f"Error: {res.text}"
    
    data = res.json()
    extracted = data["extracted_data"]
    exceptions = data["exceptions_queue"]
    
    print("\n[+] INGESTION RESULT")
    print(f"Exceptions found in Limbo: {len(exceptions)}")
    for exc in exceptions:
        print(f" - {exc['description']}: {exc['amount']} (Mapping suggest: {exc['suggested_mapping']})")
        
    # Construct Base Data
    base_data = {
        "base_year": extracted["detectedYear"],
        "ce": extracted["ce"],
        "sp": extracted["sp"]
    }
    
    state = {
        "base_data": base_data,
        "exceptions_queue": exceptions,
        "ledger": []
    }
    
    print("\n[+] Testing Ledger Apply (No changes)")
    res2 = client.post("/api/v1/ledger/apply", json=state)
    assert res2.status_code == 200, f"Error: {res2.text}"
    calc = res2.json()["calculations"]["years"][0]
    print(f"EBITDA: {calc['ebitda']}, UTILE: {calc['utileNetto']}, QUADRATO: {calc['isQuadrato']}")
    
    # Auto-resolve using Split Ledger
    print("\n[+] Auto-resolving exceptions via Ledger Split")
    for exc in exceptions:
        print(f"Splitting {exc['description']} -> {exc['suggested_mapping']}")
        
        target = "oneriDiversi"
        if "Ricavi" in exc["description"]:
            target = "altriRicavi"
        elif "SP" in exc["description"]:
            target = "altriDebiti"
            
        payload = {
            "split": {
                "exception_id": exc["id"],
                "splits": {
                    target: exc["amount"]
                }
            },
            "state": state
        }
        
        res3 = client.post("/api/v1/ledger/split", json=payload)
        assert res3.status_code == 200, f"Error: {res3.text}"
        state = res3.json()["hydrated_state"]
        
    print(f"\n[+] Ledger operations: {len(state['ledger'])}")
    for op in state['ledger']:
        print(f" - {op['action']} {op['amount']} to {op['target_field']}")
        
    print("\n[+] Testing Ledger Apply (After resolutions)")
    res4 = client.post("/api/v1/ledger/apply", json=state)
    assert res4.status_code == 200, f"Error: {res4.text}"
    calc = res4.json()["calculations"]["years"][0]
    print(f"EBITDA: {calc['ebitda']}, UTILE: {calc['utileNetto']}, QUADRATO: {calc['isQuadrato']}")
    
    # Test Undo
    if len(state['ledger']) > 0:
        print("\n[+] Testing Undo of last operation")
        op_id = state['ledger'][-1]['id']
        payload = {
            "undo": {
                "operation_id": op_id
            },
            "state": state
        }
        res5 = client.post("/api/v1/ledger/undo", json=payload)
        assert res5.status_code == 200, f"Error: {res5.text}"
        state = res5.json()["hydrated_state"]
        print(f"Ledger size after undo: {len(state['ledger'])}")
        calc = res5.json()["calculations"]["years"][0]
        print(f"EBITDA: {calc['ebitda']}, UTILE: {calc['utileNetto']}, QUADRATO: {calc['isQuadrato']}")
        
    print("\n[+] ALL TESTS PASSED SUCCESSFULLY")

if __name__ == "__main__":
    main()
