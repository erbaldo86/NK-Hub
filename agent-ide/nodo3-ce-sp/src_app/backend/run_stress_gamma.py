import os
import sys
import csv
import json
from fastapi.testclient import TestClient

# Adjust path to import main_api_server
sys.path.append(os.path.dirname(__file__))

from main_api_server import app
from pydantic_schemas import HydratedState

client = TestClient(app)

CSV_DIR = r"C:\Users\erbal\Downloads\nk_stress_test_suite"

def map_desc_to_field(desc: str) -> str:
    mapping = {
        "Ricavi delle vendite e prestazioni": "ricaviVendite",
        "Altri ricavi e proventi": "altriRicavi",
        "Crediti verso clienti": "creditiClienti",
        "Cassa e banca": "cassa",
        "Costi per materie prime": "costiMaterieHosting",
        "Costi per servizi": "costiServiziMarketing",
        "Debiti verso fornitori": "debFornitori",
        "Costi del personale": "salariStipendi",
        "Debiti tributari": "debTrib",
        "Debiti previdenziali": "debPrev",
        "Dipendenti c/retribuzioni": "altriDebiti",
        "Ammortamenti immateriali": "ammImmateriali",
        "Ammortamenti materiali": "ammMateriali",
        "Fondo ammortamento immateriali": "immaterialiLorde",
        "Fondo ammortamento materiali": "materialiLorde",
    }
    return mapping.get(desc, "oneriDiversi")

def parse_csv_to_state(filepath: str, state: dict):
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            desc = row['descrizione']
            amount = float(row['importo'])
            tipo = row['tipo_voce']
            
            if tipo == "UNKNOWN" or "Anomalia" in desc:
                # Add to exceptions
                exc = {
                    "id": f"exc_{os.urandom(4).hex()}",
                    "description": desc,
                    "suggested_mapping": "B.14",
                    "year": 2025,
                    "amount": amount,
                    "type": "unmapped_text"
                }
                state["exceptions_queue"].append(exc)
            else:
                # Add to ledger
                field = map_desc_to_field(desc)
                op = {
                    "id": f"op_{os.urandom(4).hex()}",
                    "timestamp": 1234567890.0,
                    "action": "ADD",
                    "target_field": field,
                    "year": 2025,
                    "amount": amount,
                    "notes": f"Ingested from {os.path.basename(filepath)}"
                }
                state["ledger"].append(op)

def clean_state(state):
    if "base_data" in state and "ce" in state["base_data"]:
        if "subitems_map" in state["base_data"]["ce"] and state["base_data"]["ce"]["subitems_map"] is None:
            del state["base_data"]["ce"]["subitems_map"]
    return state

def main():
    try:
        # Step 1: Initialize base state
        state = {
            "base_data": {
                "base_year": 2025,
                "ce": {},
                "sp": {}
            },
            "exceptions_queue": [],
            "ledger": []
        }
        
        # Ingest 01 to 04
        for i in range(1, 5):
            filename = f"0{i}_step_*.csv"
            # Find the actual filename
            matched = [f for f in os.listdir(CSV_DIR) if f.startswith(f"0{i}_step")]
            if not matched:
                raise FileNotFoundError(f"File 0{i} not found")
            parse_csv_to_state(os.path.join(CSV_DIR, matched[0]), state)
            
        print("[+] Ingested 01-04 CSVs")
        
        # Verify ledger addition
        res = client.post("/api/v1/ledger/apply", json=clean_state(state))
        if res.status_code != 200:
            raise Exception(f"Apply ledger failed: {res.text}")
        state = res.json()["hydrated_state"]
        calc = res.json()["calculations"]["years"][0]
        print(f"[+] After 01-04: EBITDA: {calc['ebitda']}, IsQuadrato: {calc['isQuadrato']}")
        
        # Step 2: Resolve Anomaly from step 4
        exc = state["exceptions_queue"][0]
        payload = {
            "split": {
                "exception_id": exc["id"],
                "splits": {
                    "oneriDiversi": exc["amount"]
                }
            },
            "state": clean_state(state)
        }
        res = client.post("/api/v1/ledger/split", json=payload)
        if res.status_code != 200:
            raise Exception(f"Resolve anomaly failed: {res.text}")
        state = res.json()["hydrated_state"]
        print("[+] Anomaly resolved")
        
        # Step 3: Export state
        export_path = os.path.join(os.path.dirname(__file__), "export.nk")
        with open(export_path, 'w') as f:
            json.dump(state, f)
        print("[+] State exported to .nk")
        
        # Step 4: Reset memory and rehydrate
        state = None
        with open(export_path, 'r') as f:
            state = json.load(f)
        print("[+] State rehydrated")
        
        # Step 5: Ingest 05.csv
        matched = [f for f in os.listdir(CSV_DIR) if f.startswith("05_step")]
        parse_csv_to_state(os.path.join(CSV_DIR, matched[0]), state)
        res = client.post("/api/v1/ledger/apply", json=clean_state(state))
        state = res.json()["hydrated_state"]
        print("[+] Ingested 05.csv")
        
        # Step 6: Ingest 06.csv
        matched = [f for f in os.listdir(CSV_DIR) if f.startswith("06_step")]
        parse_csv_to_state(os.path.join(CSV_DIR, matched[0]), state)
        res = client.post("/api/v1/ledger/apply", json=clean_state(state))
        state = res.json()["hydrated_state"]
        print("[+] Ingested 06.csv (Storno)")
        calc = res.json()["calculations"]["years"][0]
        print(f"[+] Final: EBITDA: {calc['ebitda']}, IsQuadrato: {calc['isQuadrato']}")
        
        # Return success
        sys.exit(0)
    except Exception as e:
        print(f"[-] ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
