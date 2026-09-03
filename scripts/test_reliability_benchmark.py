"""Reliability Benchmark & Semantic Disambiguation Suite (16 Scenarios).
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence | Batch 2 Stress Loop.
"""

import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src_app.app import bootstrap_demo_service
from src_app.service.bandi_service import LabNKBandiService


RELIABILITY_TEST_CASES: List[Dict[str, Any]] = [
    # --- BATCH 1 (Q1 - Q8) ---
    {
        "id": "CASE_01_AMIANTO",
        "query": "amianto e rifacimento coperture",
        "expected_top1": ["INAIL-ISI-2026"],
        "description": "Bonifica amianto e sicurezza lavoro (INAIL ISI 2026)"
    },
    {
        "id": "CASE_02_FOTOVOLTAICO",
        "query": "fotovoltaico e solare imprese",
        "expected_top1": ["SICILIA-SOLAR-GREEN", "MIMIT-TRANS-5-0"],
        "description": "Autoconsumo solare / Transizione energetica"
    },
    {
        "id": "CASE_03_CAMPANIA_AI",
        "query": "startup intelligenza artificiale napoli",
        "expected_top1": ["CAMPANIA-AI-2026"],
        "description": "Startup AI & Software Campania (Napoli ITF33)"
    },
    {
        "id": "CASE_04_LOMBARDIA_DIGIT",
        "query": "voucher digitalizzazione pmi lombardia",
        "expected_top1": ["LOMBARDIA-DIGIT-2026"],
        "description": "Voucher Digitalizzazione PMI Lombardia"
    },
    {
        "id": "CASE_05_EMILIA_ROBOTICA",
        "query": "robotica e meccanica 4.0 emilia",
        "expected_top1": ["EMILIA-MECCANICA-4-0"],
        "description": "Meccanica Avanzata & Robotica Industriale Emilia-Romagna"
    },
    {
        "id": "CASE_06_PUGLIA_AGRITECH",
        "query": "agritech e droni agricoli puglia",
        "expected_top1": ["PUGLIA-AGRITECH-PRECISION"],
        "description": "Smart Agritech & Precision Farming Puglia"
    },
    {
        "id": "CASE_07_TOSCANA_MODA",
        "query": "moda e tessile toscana",
        "expected_top1": ["TOSCANA-MODA-TESSILE"],
        "description": "Moda, Tessile & Artigianato Artistico Toscana"
    },
    {
        "id": "CASE_08_MIMIT_BREVETTI",
        "query": "brevetti e proprietà intellettuale",
        "expected_top1": ["MIMIT-BREVETTI-PLUS"],
        "description": "Brevetti+ & Proprietà Intellettuale MIMIT"
    },
    # --- BATCH 2 (Q9 - Q16) ---
    {
        "id": "CASE_09_TOSCANA_BIOTECH",
        "query": "scienze della vita biotech e sperimentazione clinica toscana",
        "expected_top1": ["TOSCANA-BIOTECH-PHARMA"],
        "description": "Scienze della Vita, Biotech & Pharma Toscana"
    },
    {
        "id": "CASE_10_VENETO_TEM",
        "query": "temporary export manager e consulenza fiere veneto",
        "expected_top1": ["VENETO-CONSORZI-EXPORT"],
        "description": "Voucher TEM & Internazionalizzazione Consorzi Veneto"
    },
    {
        "id": "CASE_11_PIEMONTE_AUTO",
        "query": "riconversione automotive idrogeno e veicoli elettrici piemonte",
        "expected_top1": ["PIEMONTE-AUTOMOTIVE-EV"],
        "description": "Riconversione Automotive & Mobilità Elettrica Piemonte"
    },
    {
        "id": "CASE_12_VENETO_TURISMO",
        "query": "riqualificazione alberghi e strutture ricettive turismo veneto",
        "expected_top1": ["VENETO-TURISMO-2026"],
        "description": "Riqualificazione Strutture Ricettive & Turismo Veneto"
    },
    {
        "id": "CASE_13_ABRUZZO_AGRIFOOD",
        "query": "trasformazione agroalimentare e packaging sostenibile abruzzo",
        "expected_top1": ["ABRUZZO-FOOD-PROCESSING"],
        "description": "Sviluppo Rurale & Agroalimentare Qualità Abruzzo"
    },
    {
        "id": "CASE_14_FRIULI_LEGNO",
        "query": "innovazione filiera arredo design e legno friuli",
        "expected_top1": ["FRIULI-MANIFATTURA-LEGNO"],
        "description": "Innovazione Filiera Legno & Arredo Design Friuli"
    },
    {
        "id": "CASE_15_EU_DEEPTECH",
        "query": "deep tech horizon europe blended finance ed equity startup",
        "expected_top1": ["EU-HORIZON-EIC-ACCEL"],
        "description": "EIC Accelerator Horizon Europe (Deep Tech & Equity)"
    },
    {
        "id": "CASE_16_LAZIO_CYBER",
        "query": "cybersecurity audit infrastrutturale e migrazione cloud lazio",
        "expected_top1": ["LAZIO-CYBER-SECURITY"],
        "description": "Cyber Security & Cloud Migration PMI Lazio"
    }
]


def run_reliability_benchmark() -> Tuple[int, int, List[Dict[str, Any]]]:
    """Esegue il benchmark di disambiguazione semantica e ranking top-1 su 16 scenari."""
    service: LabNKBandiService = bootstrap_demo_service()
    
    print("=" * 80)
    print("🚀 LABNK BANDI INTELLIGENCE — SUITE DI AFFIDABILITÀ & BENCHMARK (16/16)")
    print("   Protocollo CRV 4.0 | Zero-Mock | Hybrid Semantic & Lexical Boost")
    print("=" * 80)
    print(f"{'#':<3} | {'Caso / Intento':<36} | {'Top-1 Atteso':<24} | {'Top-1 Effettivo':<24} | {'Score':<6} | {'Esito'}")
    print("-" * 115)

    passed_count = 0
    total_count = len(RELIABILITY_TEST_CASES)
    results = []
    latencies = []

    for idx, test_case in enumerate(RELIABILITY_TEST_CASES, start=1):
        t0 = time.perf_counter()
        intent, ranked_grants, scores = service.search_nlp(test_case["query"])
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        actual_top1_id = ranked_grants[0].bando_id if ranked_grants else "NESSUN_RISULTATO"
        actual_top1_score = scores[0].overall_match_score if scores else 0.0
        expected_ids = test_case["expected_top1"]

        is_pass = actual_top1_id in expected_ids
        if is_pass:
            passed_count += 1
            status_str = "PASS 🟢"
        else:
            status_str = "FAIL 🔴"

        expected_str = "/".join(expected_ids)
        print(f"{idx:<3} | {test_case['description'][:36]:<36} | {expected_str[:24]:<24} | {actual_top1_id[:24]:<24} | {actual_top1_score:>5.1f}% | {status_str} ({elapsed_ms:.2f}ms)")
        
        results.append({
            "id": test_case["id"],
            "query": test_case["query"],
            "expected": expected_ids,
            "actual": actual_top1_id,
            "actual_title": ranked_grants[0].titolo if ranked_grants else "",
            "score": actual_top1_score,
            "passed": is_pass,
            "latency_ms": round(elapsed_ms, 2)
        })

    print("-" * 115)
    accuracy_pct = (passed_count / total_count) * 100
    avg_latency = sum(latencies) / len(latencies)
    print(f"📊 RISULTATO FINALE: {passed_count}/{total_count} CASI SUPERATI ({accuracy_pct:.1f}% ACCURACY | LATENZA MEDIA: {avg_latency:.2f}ms)")
    print("=" * 80)

    return passed_count, total_count, results


def main():
    passed, total, _ = run_reliability_benchmark()
    if passed == total:
        print(f"\n[OK] TUTTI GLI {total} CASI DELLA MATRICE DI AFFIDABILITÀ SONO STATI RISOLTI CORRETTAMENTE AL 1° POSTO!")
        sys.exit(0)
    else:
        print(f"\n[FAIL] Rilevati fallimenti nel benchmark ({passed}/{total} passati).")
        sys.exit(1)


if __name__ == "__main__":
    main()
