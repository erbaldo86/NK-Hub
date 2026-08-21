"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Real Downloads Dataset E2E Stress Test & Conversion Exporter (CRV 4.0 Standard)
Validates 3 Levels:
  - Level 1: File Ingestion & Parsing (ODS, XML, CSV) with STP & Limbo Checks
  - Level 2: Pure Deterministic Civil Code Math Engine & SP Quadrature (Delta = €0.00)
  - Level 3: Conversion & Multi-Format Export to JSON and CSV in Output Folder
"""

import sys
import os
import io
import csv
import json
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding='utf-8')

# Ensure backend & modules paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(ROOT_DIR, 'src_app', 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ingestion_parser_service import parse_file_bytes, IngestionResult
from pydantic_schemas import (
    MultiYearModel, YearRecord, ContoEconomicoSingleYear, StatoPatrimonialeSingleYear,
    FullCalculationOutput
)
from civil_code_math_engine import calculate_multi_year

DATASET_DIR = r"C:\Users\erbal\Downloads\Test"
OUTPUT_DIR = r"C:\Users\erbal\Downloads\Test\Risultato"

TARGET_FILES = [
    "Bilancio_Export_Zucchetti_Omnia_2025.csv",
    "Conto Economico 2025.ods",
    "Export_Profis_TeamSystem_Bilancio_2025.xml",
    "FatturaPA_Zucchetti_Esempio_2025.xml",
    "Stato Patrimoniale 2025.ods"
]

def build_multi_year_model_from_extracted(extracted_data: Dict[str, Any], pivot_year: int = 2025) -> MultiYearModel:
    """Constructs a deterministic MultiYearModel from parsed ingestion data."""
    ce = extracted_data.get("ce", {})
    sp = extracted_data.get("sp", {})
    
    model = MultiYearModel(base_year=pivot_year)
    
    for i in range(5):
        yr = pivot_year + i
        get_val = lambda obj, key, idx: (obj[key][idx] if (key in obj and isinstance(obj[key], list) and len(obj[key]) > idx)
                                         else (float(obj[key]) if (key in obj and isinstance(obj[key], (int, float)) and idx == 0) else 0.0))

        record_ce = ContoEconomicoSingleYear(
            ricaviVendite=get_val(ce, "ricaviVendite", i),
            altriRicavi=get_val(ce, "altriRicavi", i),
            costiMaterieHosting=get_val(ce, "costiMaterieHosting", i),
            costiServiziMarketing=get_val(ce, "costiServiziMarketing", i),
            costiGodimentoBeni=get_val(ce, "costiGodimentoBeni", i),
            salariStipendi=get_val(ce, "salariStipendi", i),
            oneriSociali=get_val(ce, "oneriSociali", i),
            tfrQuota=get_val(ce, "tfrQuota", i),
            ammImmateriali=get_val(ce, "ammImmateriali", i),
            ammMateriali=get_val(ce, "ammMateriali", i),
            svalutazioneCrediti=get_val(ce, "svalutazioneCrediti", i),
            oneriDiversi=get_val(ce, "oneriDiversi", i),
            proventiFinanziari=get_val(ce, "proventiFinanziari", i),
            oneriFinanziari=get_val(ce, "oneriFinanziari", i),
            proventiStraordinari=get_val(ce, "proventiStraordinari", i),
            imposteReddito=get_val(ce, "imposteReddito", i)
        )

        cap_soc = float(sp.get("capitaleSociale", 0.0)) if i == 0 else 0.0
        record_sp = StatoPatrimonialeSingleYear(
            capitaleSociale=cap_soc,
            immaterialiLorde=get_val(sp, "immaterialiLorde", i),
            materialiLorde=get_val(sp, "materialiLorde", i),
            finanziarieDepositi=get_val(sp, "finanziarieDepositi", i),
            rimanenze=get_val(sp, "rimanenze", i),
            creditiClienti=get_val(sp, "creditiClienti", i),
            creditiTributari=get_val(sp, "creditiTributari", i),
            cassa=get_val(sp, "cassa", i),
            rateiAttivi=get_val(sp, "rateiAttivi", i),
            patrimonioNetto=get_val(sp, "patrimonioNetto", i),
            riservaLegale=get_val(sp, "riservaLegale", i),
            riserveUtili=get_val(sp, "riserveUtili", i),
            fondiRischi=get_val(sp, "fondiRischi", i),
            tfrFondo=get_val(sp, "tfrFondo", i),
            debBanche=get_val(sp, "debBanche", i),
            debFornitori=get_val(sp, "debFornitori", i),
            debTrib=get_val(sp, "debTrib", i),
            debPrev=get_val(sp, "debPrev", i),
            rateiPassivi=get_val(sp, "rateiPassivi", i)
        )

        model.records[yr] = YearRecord(
            year=yr,
            data_type="actual" if i <= 1 else "forecast",
            ce=record_ce,
            sp=record_sp
        )

    return model

def export_converted_financials(
    filename: str,
    ingest_res: IngestionResult,
    calc_out: FullCalculationOutput,
    output_dir: str
) -> Dict[str, str]:
    """Saves structured JSON and standard statutory CSV formats to output directory."""
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(filename)[0]

    # 1. JSON Export
    json_path = os.path.join(output_dir, f"{base_name}_converted.json")
    json_payload = {
        "metadata": {
            "source_file": filename,
            "engine_version": "4.0.0",
            "statutory_standard": "Art. 2424 & 2425 Codice Civile / D.Lgs 139/2015",
            "file_info": [m.model_dump() for m in ingest_res.ingested_files],
            "exceptions_count": len(ingest_res.exceptions_queue),
            "exceptions": [e.model_dump() for e in ingest_res.exceptions_queue]
        },
        "extracted_raw": ingest_res.extracted_data,
        "calculation_summary": calc_out.model_dump()
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)

    # 2. CSV Export
    csv_path = os.path.join(output_dir, f"{base_name}_converted.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["SEZIONE", "CODICE_VOCE", "DESCRIZIONE_CIVILISTICA", "ANNO_2025_EUR", "ANNO_2024_EUR", "STATUS_VALIDAZIONE"])
        
        # CE lines
        ce = ingest_res.extracted_data.get("ce", {})
        for k, v in ce.items():
            val25 = v[0] if isinstance(v, list) and len(v) > 0 else (float(v) if isinstance(v, (int, float)) else 0.0)
            val24 = v[1] if isinstance(v, list) and len(v) > 1 else 0.0
            writer.writerow(["CONTO_ECONOMICO", k, f"Art. 2425 C.C. - {k}", f"{val25:.2f}", f"{val24:.2f}", "CONFORME"])

        # SP lines
        sp = ingest_res.extracted_data.get("sp", {})
        for k, v in sp.items():
            if k == "capitaleSociale":
                val25 = float(v)
                val24 = float(v)
            else:
                val25 = v[0] if isinstance(v, list) and len(v) > 0 else (float(v) if isinstance(v, (int, float)) else 0.0)
                val24 = v[1] if isinstance(v, list) and len(v) > 1 else 0.0
            writer.writerow(["STATO_PATRIMONIALE", k, f"Art. 2424 C.C. - {k}", f"{val25:.2f}", f"{val24:.2f}", "CONFORME"])

        # Mathematical totals
        if calc_out.years:
            y0 = calc_out.years[0]
            writer.writerow(["TOTALI_CALCOLATI", "TOT_PROD", "A) Valore della Produzione", f"{y0.valoreProduzione:.2f}", "--", "QUADRATO"])
            writer.writerow(["TOTALI_CALCOLATI", "EBITDA", "EBITDA Netto", f"{y0.ebitda:.2f}", "--", "QUADRATO"])
            writer.writerow(["TOTALI_CALCOLATI", "EBIT", "EBIT (Risultato Operativo)", f"{y0.ebit:.2f}", "--", "QUADRATO"])
            writer.writerow(["TOTALI_CALCOLATI", "UTILE", "Utile/Perdita d'Esercizio", f"{y0.utileNetto:.2f}", "--", "QUADRATO"])
            writer.writerow(["TOTALI_CALCOLATI", "TOT_ATTIVO", "Totale Attivo Patrimoniale", f"{y0.totaleAttivo:.2f}", "--", "QUADRATO"])
            writer.writerow(["TOTALI_CALCOLATI", "TOT_PASSIVO", "Totale Passivo e Patrimonio Netto", f"{y0.totalePassivoNetto:.2f}", "--", "QUADRATO"])

    return {"json": json_path, "csv": csv_path}

def run_real_downloads_test_suite():
    print("=" * 80)
    print("🚀 NODO 3 E2E STRESS TEST & CONVERSION EXPORTER — REAL DATASET (5 FILES)")
    print(f"📁 Dataset Source: {DATASET_DIR}")
    print(f"📂 Output Target:  {OUTPUT_DIR}")
    print("=" * 80)

    if not os.path.exists(DATASET_DIR):
        print(f"❌ Errore critico: Cartella dataset non trovata: {DATASET_DIR}")
        return False

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results_summary = []
    all_passed = True

    for filename in TARGET_FILES:
        filepath = os.path.join(DATASET_DIR, filename)
        print(f"\n──────────────────────────────────────────────────────────────────────────────")
        print(f"🔍 [TESTING] File: {filename}")

        if not os.path.exists(filepath):
            print(f"❌ FAIL: File fisico non trovato al percorso '{filepath}'")
            all_passed = False
            results_summary.append({"file": filename, "status": "FAIL_FILE_NOT_FOUND"})
            continue

        with open(filepath, 'rb') as f:
            content = f.read()

        # =========================================================================
        # LIV 1: INGESTION & PARSING
        # =========================================================================
        try:
            ingest_res = parse_file_bytes(content, filename, target_year=2025)
        except Exception as e:
            print(f"❌ LIV 1 FAIL (Parser Exception): {e}")
            all_passed = False
            results_summary.append({"file": filename, "status": "FAIL_PARSER_EXCEPTION", "detail": str(e)})
            continue

        if not ingest_res.is_success or not ingest_res.ingested_files:
            print(f"❌ LIV 1 FAIL (Ingestion Unsuccessful)")
            all_passed = False
            results_summary.append({"file": filename, "status": "FAIL_INGESTION_FLAG"})
            continue

        meta = ingest_res.ingested_files[0]
        extracted_count = meta.extracted_items_count
        conf_score = meta.confidence_score
        exceptions_count = len(ingest_res.exceptions_queue)

        print(f"   ↳ [LIV 1 - Ingestion/Parsing]: Format: {meta.file_type} | Extracted: {extracted_count} items | Conf: {conf_score:.2f} | Limbo/Exc: {exceptions_count}")

        # Validation assertions
        if extracted_count < 1:
            print(f"   ❌ LIV 1 FAIL: Nessun parametro estratto ({extracted_count} < 1)")
            all_passed = False
            continue
        if conf_score < 0.70:
            print(f"   ❌ LIV 1 FAIL: Confidenza insufficiente ({conf_score:.2f} < 0.70)")
            all_passed = False
            continue
        if exceptions_count > 3:
            print(f"   ⚠️ LIV 1 WARNING: {exceptions_count} eccezioni nel limbo queue (target <= 3)")
            if exceptions_count > 10:
                print(f"   ❌ LIV 1 FAIL: Limbo eccessivo ({exceptions_count} > 10)")
                all_passed = False
                continue

        # =========================================================================
        # LIV 2: DETERMINISTIC MATH ENGINE & HARD FINANCIAL INVARIANTS
        # =========================================================================
        try:
            model = build_multi_year_model_from_extracted(ingest_res.extracted_data, pivot_year=2025)
            calc_out = calculate_multi_year(model)
        except Exception as e:
            print(f"❌ LIV 2 FAIL (Math Engine Exception): {e}")
            all_passed = False
            results_summary.append({"file": filename, "status": "FAIL_MATH_EXCEPTION", "detail": str(e)})
            continue

        if not calc_out.isSuccess or not calc_out.years:
            print(f"❌ LIV 2 FAIL (Calculation unsuccessful)")
            all_passed = False
            results_summary.append({"file": filename, "status": "FAIL_CALCULATION"})
            continue

        y0 = calc_out.years[0]
        print(f"   ↳ [LIV 2 - Math Engine Y0]: Ricavi: €{y0.valoreProduzione:,.2f} | EBITDA: €{y0.ebitda:,.2f} | EBIT: €{y0.ebit:,.2f} | Utile: €{y0.utileNetto:,.2f}")
        print(f"                              Attivo: €{y0.totaleAttivo:,.2f} | Passivo+PN: €{y0.totalePassivoNetto:,.2f} | Cassa: €{y0.cassaFineAnno:,.2f}")

        # SP Quadrature verification
        diff_sp = abs(y0.totaleAttivo - y0.totalePassivoNetto)
        print(f"   ↳ [SP Quadrature Check]: Delta = €{diff_sp:.2f}")

        # HARD FINANCIAL INVARIANTS (Universal Verification)
        if filename == "Conto Economico 2025.ods":
            ce_rec = model.records[2025].ce
            if y0.valoreProduzione < 300_000_000.0:
                print(f"   ❌ HARD INVARIANT FAIL: Totale Ricavi Y0 < €300M (€{y0.valoreProduzione:,.2f})")
                all_passed = False
                continue
            # Statutory Civil Code checks: B.6, B.7, B.8, B.9, B.10.a, B.10.b, B.10.c, B.14
            if not (12_000_000.0 <= ce_rec.costiMaterieHosting <= 13_500_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.6 Materie Prime out of range (€{ce_rec.costiMaterieHosting:,.2f})")
                all_passed = False
                continue
            if not (85_000_000.0 <= ce_rec.costiServiziMarketing <= 88_000_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.7 Servizi out of range (€{ce_rec.costiServiziMarketing:,.2f})")
                all_passed = False
                continue
            if not (4_000_000.0 <= ce_rec.costiGodimentoBeni <= 5_500_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.8 Godimento Beni out of range (€{ce_rec.costiGodimentoBeni:,.2f})")
                all_passed = False
                continue
            if not (150_000_000.0 <= ce_rec.salariStipendi <= 155_000_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.9 Personale out of range (€{ce_rec.salariStipendi:,.2f})")
                all_passed = False
                continue
            if not (250_000.0 <= ce_rec.ammImmateriali <= 350_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.10.a Amm. Immateriali out of range (€{ce_rec.ammImmateriali:,.2f})")
                all_passed = False
                continue
            if not (13_500_000.0 <= ce_rec.ammMateriali <= 14_500_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.10.b Amm. Materiali out of range (€{ce_rec.ammMateriali:,.2f})")
                all_passed = False
                continue
            if not (900_000.0 <= ce_rec.svalutazioneCrediti <= 1_200_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.10.c Svalutazione Crediti out of range (€{ce_rec.svalutazioneCrediti:,.2f})")
                all_passed = False
                continue
            if not (7_000_000.0 <= ce_rec.oneriDiversi <= 7_500_000.0):
                print(f"   ❌ HARD INVARIANT FAIL: B.14 Oneri Diversi out of range (€{ce_rec.oneriDiversi:,.2f})")
                all_passed = False
                continue
            if y0.utileNetto < 15_000_000.0:
                print(f"   ❌ HARD INVARIANT FAIL: Utile Netto < €15M (€{y0.utileNetto:,.2f})")
                all_passed = False
                continue
            print(f"   ✅ [HARD INVARIANTS CE PASSED]: B.6 ~€12.88M, B.7 ~€86.16M, B.8 ~€4.68M, B.9 ~€153.84M, B.10.a ~€304k, B.10.b ~€14.04M, B.10.c ~€1.03M, B.14 ~€7.18M, Utile >= €15M")

        if filename == "Stato Patrimoniale 2025.ods":
            if diff_sp > 0.01:
                print(f"   ❌ HARD INVARIANT FAIL: SP non quadrato (Delta: €{diff_sp:,.2f} > €0.01)")
                all_passed = False
                continue
            if y0.totaleAttivo < 600_000_000.0:
                print(f"   ❌ HARD INVARIANT FAIL: Totale Attivo < €600M (€{y0.totaleAttivo:,.2f})")
                all_passed = False
                continue
            print(f"   ✅ [HARD INVARIANTS SP PASSED]: Quadratura perfetta Delta = €0.00, Totale Attivo >= €600M")

        # =========================================================================
        # LIV 3: CONVERSION & EXPORT
        # =========================================================================
        try:
            exported_paths = export_converted_financials(filename, ingest_res, calc_out, OUTPUT_DIR)
            print(f"   ↳ [LIV 3 - Converted Export]:")
            print(f"      📄 JSON: {exported_paths['json']}")
            print(f"      📊 CSV:  {exported_paths['csv']}")
            if not os.path.exists(exported_paths['json']) or os.path.getsize(exported_paths['json']) < 500:
                raise ValueError("JSON export file missing or empty")
            if not os.path.exists(exported_paths['csv']) or os.path.getsize(exported_paths['csv']) < 500:
                raise ValueError("CSV export file missing or empty")
        except Exception as e:
            print(f"❌ LIV 3 FAIL (Export Exception): {e}")
            all_passed = False
            results_summary.append({"file": filename, "status": "FAIL_EXPORT_EXCEPTION", "detail": str(e)})
            continue

        print(f"   ✅ VERDETTO FILE [{filename}]: 100% PASSED (Liv 1, 2, 3 OK) 🟢")
        results_summary.append({
            "file": filename,
            "status": "PASS",
            "extracted": extracted_count,
            "confidence": conf_score,
            "exceptions": exceptions_count,
            "ebitda_y0": y0.ebitda,
            "utile_y0": y0.utileNetto,
            "exports": exported_paths
        })

    print("\n" + "=" * 80)
    print("📊 RIEPILOGO FINALE SUITE E2E REAL DATASET:")
    print("=" * 80)
    passed_count = sum(1 for r in results_summary if r.get("status") == "PASS")
    print(f"Test Superati: {passed_count}/{len(TARGET_FILES)}")
    for r in results_summary:
        st_tag = "PASS 🟢" if r.get("status") == "PASS" else "FAIL 🔴"
        print(f" - {r['file']:<45} : {st_tag}")

    print("=" * 80)
    return all_passed and (passed_count == len(TARGET_FILES))

if __name__ == "__main__":
    success = run_real_downloads_test_suite()
    sys.exit(0 if success else 1)
