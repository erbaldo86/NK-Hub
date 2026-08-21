import sys
import os
import io
import json
import requests
import zipfile
import xml.etree.ElementTree as ET

# Configure UTF-8
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = r"g:\Il mio Drive\Antigravity\agent-ide\nodo3-ce-sp"
BACKEND_DIR = os.path.join(ROOT_DIR, "src_app", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ingestion_parser_service import parse_file_bytes, IngestionResult

ce_file = r"C:\Users\erbal\Downloads\Test\Conto Economico 2025.ods"
sp_file = r"C:\Users\erbal\Downloads\Test\Stato Patrimoniale 2025.ods"

print("=" * 80)
print("EMPIRICAL RECONCILIATION AUDIT: MODEL A vs MODEL B")
print("=" * 80)

# --------------------------------------------------------------------------
# 1. GROUND TRUTH FROM RAW ODS FILES
# --------------------------------------------------------------------------
def extract_raw_ods_table(file_path):
    with zipfile.ZipFile(file_path, 'r') as z:
        content_xml = z.read('content.xml')
    root = ET.fromstring(content_xml)
    ns = {'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0', 'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
    rows = []
    for row in root.findall('.//table:table-row', ns):
        cells = [''.join(c.itertext()).strip() for c in row.findall('.//table:table-cell', ns)]
        while cells and not cells[-1]: cells.pop()
        if cells:
            rows.append(cells)
    return rows

ce_raw = extract_raw_ods_table(ce_file)
sp_raw = extract_raw_ods_table(sp_file)

print(f"\n[1] RAW FILES INSPECTION:")
print(f"  - Conto Economico 2025.ods: {len(ce_raw)} non-empty rows")
print(f"  - Stato Patrimoniale 2025.ods: {len(sp_raw)} non-empty rows")

# --------------------------------------------------------------------------
# 2. INGESTION PARSER SERVICE EXECUTION (PYTHON ENGINE)
# --------------------------------------------------------------------------
with open(ce_file, 'rb') as f:
    ce_bytes = f.read()
with open(sp_file, 'rb') as f:
    sp_bytes = f.read()

res_ce = parse_file_bytes(ce_bytes, "Conto Economico 2025.ods", target_year=2025)
res_sp = parse_file_bytes(sp_bytes, "Stato Patrimoniale 2025.ods", target_year=2025)

print("\n[2] PYTHON BACKEND INGESTION RESULTS:")
print(f"  CE File -> is_success: {res_ce.is_success}, detected_years: {res_ce.detected_years}, pivot_year: {res_ce.pivot_year}")
print(f"  CE File -> exceptions_queue length: {len(res_ce.exceptions_queue)}")
print(f"  CE File -> detailedSubitems length: {len(res_ce.extracted_data.get('detailedSubitems', []))}")
print(f"  CE File -> Capitale Sociale in SP: €{res_ce.extracted_data.get('sp', {}).get('capitaleSociale', 0.0):,.2f}")

print(f"\n  SP File -> is_success: {res_sp.is_success}, detected_years: {res_sp.detected_years}, pivot_year: {res_sp.pivot_year}")
print(f"  SP File -> exceptions_queue length: {len(res_sp.exceptions_queue)}")
print(f"  SP File -> detailedSubitems length: {len(res_sp.extracted_data.get('detailedSubitems', []))}")
print(f"  SP File -> Capitale Sociale in SP: €{res_sp.extracted_data.get('sp', {}).get('capitaleSociale', 0.0):,.2f}")

# --------------------------------------------------------------------------
# 3. VERIFICATION OF MODEL B CLAIM 1 (OPEX CRUSHING & AMMORTAMENTI)
# --------------------------------------------------------------------------
print("\n[3] MODEL B - CLAIM 1: OPEX CRUSHING & ZEROING OF B.6, B.8, B.10.a, B.10.c")
ce_data = res_ce.extracted_data.get('ce', {})
print(f"  - B.6 (Materie Prime / costiMaterieHosting): €{ce_data.get('costiMaterieHosting', [0])[0]:,.2f}")
print(f"  - B.7 (Servizi / costiServiziMarketing):     €{ce_data.get('costiServiziMarketing', [0])[0]:,.2f}  <-- ABSORBS ALL 106.3M")
print(f"  - B.8 (Godimento Beni / costiGodimentoBeni): €{ce_data.get('costiGodimentoBeni', [0])[0]:,.2f}")
print(f"  - B.10.a (Amm. Immateriali / ammImmateriali): €{ce_data.get('ammImmateriali', [0])[0]:,.2f}")
print(f"  - B.10.b (Amm. Materiali / ammMateriali):     €{ce_data.get('ammMateriali', [0])[0]:,.2f}  <-- ABSORBS ALL 15.38M")
print(f"  - B.10.c (Svalutazione / svalutazioneCrediti): €{ce_data.get('svalutazioneCrediti', [0])[0]:,.2f}")

# Ground truth in ODS raw:
print("\n  ODS Ground Truth Breakdown for Gestione Corrente:")
for r in ce_raw:
    if any(k in r[0] for k in ['Acquisto materiale', 'libri', 'altri materiali', 'Variazione delle rimanenze', 'godimento beni', 'collaborazioni tecnico']):
        print(f"    Raw Row: {r[0]:<60} | 2025: {r[1]:>15}")

# --------------------------------------------------------------------------
# 4. FASTAPI LIVE SERVER TEST (HTTP POST /api/v1/ingest/parse_pdf)
# --------------------------------------------------------------------------
print("\n[4] FASTAPI LIVE HTTP ENDPOINT VERIFICATION (http://127.0.0.1:8000/api/v1/ingest/parse_pdf):")
try:
    files_payload = {'file': ('Conto Economico 2025.ods', ce_bytes, 'application/vnd.oasis.opendocument.spreadsheet')}
    resp = requests.post("http://127.0.0.1:8000/api/v1/ingest/parse_pdf", files=files_payload, data={'year': 2025})
    print(f"  FastAPI Status Code: {resp.status_code}")
    json_out = resp.json()
    print(f"  FastAPI Response has extracted_data: {'extracted_data' in json_out}")
    print(f"  FastAPI Exceptions count: {len(json_out.get('exceptions_queue', []))}")
    print(f"  FastAPI Comparative flag: {json_out.get('has_comparative_year')}")
    print(f"  FastAPI Detected years: {json_out.get('detected_years')}")
except Exception as e:
    print(f"  FastAPI Request Failed: {e}")
