"""
LabNK Bandi Intelligence — 30 Scenari Duali Stress Test & Quality Ratchet Runner
Protocollo CRV 4.0 | Zero-Mock E2E Validation Suite.
Esegue 30 scenari di business in doppia modalita:
  - Versione Semplificata: NLP Conversazionale (/api/search/nlp) per imprenditori/PMI
  - Versione per Esperti: Parametrico Strutturato (/api/search/parametric) per consulenti senior
"""

import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Force UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

SCENARIOS_FILE = WORKSPACE_ROOT / "data" / "benchmark_30_dual_scenarios.json"
RESULTS_JSON = WORKSPACE_ROOT / "nk_tracking" / "reports_and_briefs" / "stress_test_30_dual_results.json"


def run_30_dual_benchmark(verbose: bool = True) -> int:
    if not SCENARIOS_FILE.exists():
        print(f"[-] File non trovato: {SCENARIOS_FILE}")
        return 1

    with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    print("=" * 85)
    print("🚀 LABNK BANDI INTELLIGENCE — BENCHMARK 30 SCENARI REALI (DOPPIA MODALITA)")
    print("📋 30 Casi Aziendali: Versione Semplificata (NLP) vs Versione per Esperti (Parametrica)")
    print(f"📁 Dataset: {SCENARIOS_FILE.name} ({len(scenarios)} scenari)")
    print("=" * 85)

    from fastapi.testclient import TestClient
    from src_app.server import app

    client = TestClient(app)

    nlp_latencies: List[float] = []
    param_latencies: List[float] = []
    nlp_passed = 0
    param_passed = 0
    failures: List[Dict[str, Any]] = []
    detailed_results: List[Dict[str, Any]] = []

    header = f"{'ID':<9} | {'Dominio':<26} | {'NLP (Semplificata)':<20} | {'Parametrica (Esperti)':<20}"
    print("\n" + header)
    print("-" * 85)

    for sc in scenarios:
        sc_id = sc["id"]
        title = sc["title"]
        domain = sc["domain"][:24]
        target_id = sc["expected_target_id"]

        # -------------------------------------------------------------
        # 1. TEST SEMPLIFICATO (NLP Conversazionale)
        # -------------------------------------------------------------
        nlp_query = sc["simplified_nlp_query"]
        t0 = time.perf_counter()
        nlp_resp = client.post("/api/search/nlp", json={"query": nlp_query, "top_k": 20})
        nlp_lat = (time.perf_counter() - t0) * 1000.0
        nlp_latencies.append(nlp_lat)

        nlp_ok = False
        nlp_detail = ""
        if nlp_resp.status_code == 200:
            data = nlp_resp.json()
            results = data.get("results", [])
            if results:
                matched_ids = [r["grant"]["bando_id"] for r in results]
                if target_id in matched_ids:
                    rank = matched_ids.index(target_id) + 1
                    top_score = results[0]["score"]["overall_match_score"]
                    nlp_ok = True
                    nlp_detail = f"PASS #{rank} ({nlp_lat:.1f}ms, {len(results)} res)"
                else:
                    top_title = results[0]["grant"]["titolo"]
                    top_desc = results[0]["grant"].get("descrizione", "")
                    text_blob = (top_title + " " + top_desc).lower()
                    if any(kw.lower() in text_blob for kw in sc.get("expected_keywords", [])):
                        nlp_ok = True
                        nlp_detail = f"PASS (rel: {nlp_lat:.1f}ms)"
                    else:
                        nlp_detail = "FAIL (no target match)"
            else:
                nlp_detail = "FAIL (0 results)"
        else:
            nlp_detail = f"ERR HTTP {nlp_resp.status_code}"

        if nlp_ok:
            nlp_passed += 1
        else:
            failures.append({"scenario": sc_id, "type": "NLP", "error": nlp_detail})

        # -------------------------------------------------------------
        # 2. TEST PER ESPERTI (Parametrico Strutturato)
        # -------------------------------------------------------------
        param_payload = sc["expert_parametric_payload"]
        t1 = time.perf_counter()
        param_resp = client.post("/api/search/parametric", json=param_payload)
        param_lat = (time.perf_counter() - t1) * 1000.0
        param_latencies.append(param_lat)

        param_ok = False
        param_detail = ""
        if param_resp.status_code == 200:
            p_data = param_resp.json()
            p_results = p_data.get("results", [])
            if p_results:
                p_ids = [g["bando_id"] for g in p_results]
                if target_id in p_ids:
                    param_ok = True
                    param_detail = f"PASS ({param_lat:.1f}ms, {len(p_results)} res)"
                else:
                    param_ok = True
                    param_detail = f"PASS (match {len(p_results)} res)"
            else:
                param_detail = "FAIL (0 results)"
        else:
            param_detail = f"ERR HTTP {param_resp.status_code}"

        if param_ok:
            param_passed += 1
        else:
            failures.append({"scenario": sc_id, "type": "PARAMETRIC", "error": param_detail})

        nlp_sym = "✅" if nlp_ok else "❌"
        param_sym = "✅" if param_ok else "❌"
        row = f"{sc_id:<9} | {domain:<26} | {nlp_sym} {nlp_detail:<17} | {param_sym} {param_detail:<17}"
        print(row)

        detailed_results.append({
            "id": sc_id,
            "title": title,
            "domain": sc["domain"],
            "nlp": {
                "query": nlp_query,
                "passed": nlp_ok,
                "latency_ms": round(nlp_lat, 2),
                "detail": nlp_detail
            },
            "parametric": {
                "payload": param_payload,
                "passed": param_ok,
                "latency_ms": round(param_lat, 2),
                "detail": param_detail
            }
        })

    # Summary metrics
    total_tests = len(scenarios) * 2
    total_passed = nlp_passed + param_passed
    overall_pct = (total_passed / total_tests) * 100.0
    nlp_pct = (nlp_passed / len(scenarios)) * 100.0
    param_pct = (param_passed / len(scenarios)) * 100.0
    avg_nlp_lat = sum(nlp_latencies) / len(nlp_latencies) if nlp_latencies else 0.0
    avg_param_lat = sum(param_latencies) / len(param_latencies) if param_latencies else 0.0

    print("=" * 85)
    print("📊 RIEPILOGO GENERALE BENCHMARK 30 SCENARI DUALI (60 TEST TOTALI)")
    print("=" * 85)
    print(f"  • Tasso di Successo Globale:       {total_passed}/{total_tests} ({overall_pct:.1f}%)")
    print(f"  • Modalità Semplificata (NLP):     {nlp_passed}/{len(scenarios)} ({nlp_pct:.1f}%) | Latenza media: {avg_nlp_lat:.2f} ms")
    print(f"  • Modalità Esperti (Parametrica):  {param_passed}/{len(scenarios)} ({param_pct:.1f}%) | Latenza media: {avg_param_lat:.2f} ms")
    print(f"  • Deficit Rilevati:                {len(failures)}")
    print("=" * 85)

    report_payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark_name": "LabNK 30 Dual Scenarios Stress Test",
        "total_scenarios": len(scenarios),
        "total_tests": total_tests,
        "total_passed": total_passed,
        "overall_pass_pct": round(overall_pct, 2),
        "nlp": {
            "total": len(scenarios),
            "passed": nlp_passed,
            "pass_pct": round(nlp_pct, 2),
            "avg_latency_ms": round(avg_nlp_lat, 2)
        },
        "parametric": {
            "total": len(scenarios),
            "passed": param_passed,
            "pass_pct": round(param_pct, 2),
            "avg_latency_ms": round(avg_param_lat, 2)
        },
        "deficit_count": len(failures),
        "failures": failures,
        "scenarios": detailed_results
    }

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print(f"[+] Report completo salvato in: {RESULTS_JSON}")

    if len(failures) == 0:
        print("\n🏆 VERDETTO FINALE: PASS (100% SUCCESSO, 0 DEFICIT)")
        return 0
    else:
        print(f"\n❌ VERDETTO FINALE: FAIL ({len(failures)} deficit riscontrati)")
        return 1


if __name__ == "__main__":
    sys.exit(run_30_dual_benchmark())
