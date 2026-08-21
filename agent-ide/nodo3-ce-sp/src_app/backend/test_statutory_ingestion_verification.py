"""
Nodo 3 (Chronos & Kairos) — Statutory Ingestion & Limbo Queue CRV 3.0 Verification Test
Automated Ground Truth & Ratchet Test Runner for Worker Agents
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import json
import traceback

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from ingestion_parser_service import parse_file_bytes, IngestionResult

def run_verification_suite():
    print("======================================================================")
    print("🚀 NODO 3 CRV 3.0 VERIFICATION SUITE — STATUTORY INGESTION & LIMBO")
    print("======================================================================")

    downloads_dir = r"C:\Users\erbal\Downloads"
    test_files = [
        ("Zucchetti CSV", os.path.join(downloads_dir, "Bilancio_Export_Zucchetti_Omnia_2025.csv")),
        ("TeamSystem XML", os.path.join(downloads_dir, "Export_Profis_TeamSystem_Bilancio_2025.xml")),
        ("FatturaPA XML", os.path.join(downloads_dir, "FatturaPA_Zucchetti_Esempio_2025.xml"))
    ]

    total_tests = 0
    passed_tests = 0
    discrepancies = []

    for label, filepath in test_files:
        total_tests += 1
        print(f"\n🧪 [TEST {total_tests}] Verifico Ingestione per '{label}': {os.path.basename(filepath)}")
        
        if not os.path.exists(filepath):
            print(f"❌ FAIL: File di test non trovato al percorso: {filepath}")
            discrepancies.append({
                "test": label,
                "reason": f"File non trovato: {filepath}",
                "severity": "CRITICAL"
            })
            continue

        try:
            with open(filepath, "rb") as f:
                content = f.read()

            filename = os.path.basename(filepath)
            res: IngestionResult = parse_file_bytes(content, filename)

            # ASSERTION 1: Successo Ingestione
            if not res.is_success:
                print(f"❌ FAIL: Ingestione fallita per '{filename}'")
                discrepancies.append({"test": label, "reason": "is_success == False"})
                continue

            # ASSERTION 2: Target STP Auto-Ingestion Rate (Exceptions Queue <= 3)
            exc_count = len(res.exceptions_queue)
            extracted_ce = res.extracted_data.get("ce", {})
            ricavi = extracted_ce.get("ricaviVendite", [0.0])[0]
            
            print(f"   📊 Risultato Parser: Ricavi Vendite = €{ricavi:,.2f} | Eccezioni nel Limbo = {exc_count}")

            if exc_count > 3:
                print(f"⚠️ WARN: Troppe voci inviate al Limbo ({exc_count} > 3). STP Rate al di sotto del 90%.")
                discrepancies.append({
                    "test": label,
                    "reason": f"Eccezioni Limbo eccessive: {exc_count} voci nel limbo (target <= 3)",
                    "severity": "HIGH"
                })
            else:
                print(f"   ✅ STP Rate CONFORME (Auto-Ingestion >= 90%, Limbo <= 3 voci)")

            # ASSERTION 3: Presenza Dati Estratti CE
            if ricavi <= 0:
                print(f"❌ FAIL: Ricavi delle Vendite <= 0 per {filename}")
                discrepancies.append({"test": label, "reason": "Ricavi vendite <= 0"})
            else:
                print(f"   ✅ Dati CE Estratti Correttamente")

            passed_tests += 1

        except Exception as e:
            err_msg = str(e)
            stack = traceback.format_exc()
            print(f"❌ CRITICAL EXCEPTION durante l'esecuzione di {label}: {err_msg}")
            discrepancies.append({
                "test": label,
                "reason": f"Exception: {err_msg}",
                "stack": stack[:300]
            })

    print("\n----------------------------------------------------------------------")
    print(f"📊 ESITO VERIFICATION SUITE: {passed_tests}/{total_tests} Test Superati")
    print("----------------------------------------------------------------------")

    if discrepancies:
        print("⚠️ DISCREPANCY REPORT JSON (Reflexion Loop Input):")
        print(json.dumps({
            "status": "FAIL",
            "passed": passed_tests,
            "total": total_tests,
            "discrepancies": discrepancies,
            "reflexion_required": True
        }, indent=2, ensure_ascii=False))
        sys.exit(1)
    else:
        print("🎉 SUCCESS: Tutti i test di verifica sono stati superati al 100%! Exit Code 0.")
        sys.exit(0)

if __name__ == "__main__":
    run_verification_suite()
