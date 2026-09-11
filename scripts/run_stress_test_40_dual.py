"""
LabNK Bandi Intelligence — 40 Scenari Duali Stress Test & Quality Ratchet Runner
Protocollo CRV 4.0 | Zero-Mock E2E Validation Suite.
Esegue 40 scenari di business in doppia modalita (80 query simulate complessive):
  - Versione Semplificata: NLP Conversazionale (/api/search/nlp) per imprenditori/PMI
  - Versione per Esperti: Parametrico Strutturato (/api/search/parametric) per consulenti senior
Confronta in tempo reale le due modalità (coerenza semantica, latenze, top-k ranking).
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

SCENARIOS_FILE = WORKSPACE_ROOT / "data" / "benchmark_40_dual_scenarios.json"
RESULTS_JSON = WORKSPACE_ROOT / "nk_tracking" / "reports_and_briefs" / "stress_test_40_dual_results.json"


def run_40_dual_benchmark(verbose: bool = True) -> int:
    if not SCENARIOS_FILE.exists():
        print(f"[-] File non trovato: {SCENARIOS_FILE}")
        return 1

    with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    print("=" * 95)
    print("🚀 LABNK BANDI INTELLIGENCE — STRESS TEST 40 SCENARI REALI (DOPPIA MODALITA)")
    print("📋 40 Casi Aziendali: Versione Semplificata (NLP) vs Versione per Esperti (Parametrica)")
    print(f"📁 Dataset: {SCENARIOS_FILE.name} ({len(scenarios)} scenari = 80 query simulate)")
    print("=" * 95)

    from fastapi.testclient import TestClient
    from src_app.server import app

    client = TestClient(app)

    nlp_latencies: List[float] = []
    param_latencies: List[float] = []
    nlp_passed = 0
    param_passed = 0
    failures: List[Dict[str, Any]] = []
    detailed_results: List[Dict[str, Any]] = []

    header = f"{'ID':<8} | {'Dominio':<28} | {'NLP (Semplificata)':<25} | {'Parametrica (Esperti)':<25}"
    print()
    print(header)
    print("-" * 95)

    for sc in scenarios:
        sc_id = sc["id"]
        title = sc["title"]
        domain = sc["domain"][:26]
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
        nlp_rank = -1
        nlp_score = 0.0
        nlp_count = 0
        if nlp_resp.status_code == 200:
            data = nlp_resp.json()
            results = data.get("results", [])
            nlp_count = len(results)
            if results:
                matched_ids = [r["grant"]["bando_id"] for r in results]
                if target_id in matched_ids:
                    nlp_rank = matched_ids.index(target_id) + 1
                    nlp_score = results[nlp_rank - 1]["score"]["overall_match_score"]
                    nlp_ok = True
                    nlp_detail = f"PASS #{nlp_rank} ({nlp_lat:.1f}ms, {nlp_count} res)"
                else:
                    nlp_detail = f"FAIL (not in top {len(matched_ids)})"
                    failures.append({
                        "scenario": sc_id,
                        "mode": "simplified_nlp",
                        "reason": f"Target {target_id} non trovato nei primi {len(matched_ids)} risultati",
                        "top_matches": matched_ids[:3],
                    })
            else:
                nlp_detail = "FAIL (0 res)"
                failures.append({
                    "scenario": sc_id,
                    "mode": "simplified_nlp",
                    "reason": "Nessun risultato restituito dall'NLP search",
                })
        else:
            nlp_detail = f"ERR {nlp_resp.status_code}"
            failures.append({
                "scenario": sc_id,
                "mode": "simplified_nlp",
                "reason": f"HTTP {nlp_resp.status_code}: {nlp_resp.text[:100]}",
            })

        if nlp_ok:
            nlp_passed += 1

        # -------------------------------------------------------------
        # 2. TEST PER ESPERTI (Parametrico Strutturato)
        # -------------------------------------------------------------
        param_payload = sc["expert_parametric_payload"]
        t1 = time.perf_counter()
        param_resp = client.post("/api/search/parametric", json=param_payload)
        param_lat = (time.perf_counter() - t1) * 1000.0
        param_latencies.append(param_lat)

        param_ok = False
        param_rank = -1
        param_count = 0
        if param_resp.status_code == 200:
            data = param_resp.json()
            grants = data.get("results", data.get("grants", []))
            param_count = len(grants)
            if grants:
                matched_ids = [g["bando_id"] for g in grants]
                if target_id in matched_ids:
                    param_rank = matched_ids.index(target_id) + 1
                    param_ok = True
                    param_detail = f"PASS #{param_rank} ({param_lat:.1f}ms, {param_count} res)"
                else:
                    param_detail = f"FAIL (not in {len(matched_ids)} res)"
                    failures.append({
                        "scenario": sc_id,
                        "mode": "expert_parametric",
                        "reason": f"Target {target_id} non presente tra i {len(matched_ids)} bandi filtrati",
                        "returned": matched_ids[:3],
                    })
            else:
                param_detail = "FAIL (0 res)"
                failures.append({
                    "scenario": sc_id,
                    "mode": "expert_parametric",
                    "reason": "Nessun bando soddisfa i criteri parametrici",
                })
        else:
            param_detail = f"ERR {param_resp.status_code}"
            failures.append({
                "scenario": sc_id,
                "mode": "expert_parametric",
                "reason": f"HTTP {param_resp.status_code}: {param_resp.text[:100]}",
            })

        if param_ok:
            param_passed += 1

        status_flag = "🟢" if (nlp_ok and param_ok) else ("🟡" if (nlp_ok or param_ok) else "🔴")
        print(f"{status_flag} {sc_id:<6} | {domain:<28} | {nlp_detail:<25} | {param_detail:<25}")

        detailed_results.append({
            "scenario_id": sc_id,
            "title": title,
            "domain": sc["domain"],
            "target_id": target_id,
            "nlp": {
                "passed": nlp_ok,
                "rank": nlp_rank,
                "score": nlp_score,
                "latency_ms": round(nlp_lat, 2),
                "results_count": nlp_count,
            },
            "parametric": {
                "passed": param_ok,
                "rank": param_rank,
                "latency_ms": round(param_lat, 2),
                "results_count": param_count,
            },
            "dual_agreement": nlp_ok and param_ok,
        })

    # -----------------------------------------------------------------
    # RIEPILOGO & STATISTICHE COMPARATIVE
    # -----------------------------------------------------------------
    total_scenarios = len(scenarios)
    total_queries = total_scenarios * 2
    total_passed = nlp_passed + param_passed

    avg_nlp_lat = sum(nlp_latencies) / len(nlp_latencies) if nlp_latencies else 0.0
    avg_param_lat = sum(param_latencies) / len(param_latencies) if param_latencies else 0.0

    dual_perfect = sum(1 for d in detailed_results if d["dual_agreement"])

    print()
    print("=" * 95)
    print("📊 REPORT STRESS TEST 40 SCENARI REALI (ANALISI COMPARATIVA)")
    print("=" * 95)
    print(f"🎯 Scenari Totali:             {total_scenarios}")
    print(f"🔄 Query Simulate Totali:      {total_queries} (40 NLP Semplificate + 40 Parametriche)")
    print(f"🟢 Versione Semplificata (NLP): {nlp_passed}/{total_scenarios} PASS ({nlp_passed / total_scenarios * 100:.1f}%) | Latenza media: {avg_nlp_lat:.2f} ms")
    print(f"🟢 Versione Esperti (Param.):   {param_passed}/{total_scenarios} PASS ({param_passed / total_scenarios * 100:.1f}%) | Latenza media: {avg_param_lat:.2f} ms")
    print(f"🤝 Dual Agreement (Entrambi):   {dual_perfect}/{total_scenarios} ({dual_perfect / total_scenarios * 100:.1f}%)")
    print(f"⚡ Throughput Combinato:        {total_queries / ((sum(nlp_latencies) + sum(param_latencies)) / 1000.0):.1f} query/sec")
    print(f"❌ Fallimenti Complessivi:     {len(failures)}")

    report_payload = {
        "benchmark_name": "stress_test_40_dual",
        "total_scenarios": total_scenarios,
        "total_queries_simulated": total_queries,
        "simplified_nlp": {
            "passed": nlp_passed,
            "total": total_scenarios,
            "pass_rate_pct": round(nlp_passed / total_scenarios * 100, 2),
            "avg_latency_ms": round(avg_nlp_lat, 2),
            "p95_latency_ms": round(sorted(nlp_latencies)[int(len(nlp_latencies) * 0.95)], 2),
        },
        "expert_parametric": {
            "passed": param_passed,
            "total": total_scenarios,
            "pass_rate_pct": round(param_passed / total_scenarios * 100, 2),
            "avg_latency_ms": round(avg_param_lat, 2),
            "p95_latency_ms": round(sorted(param_latencies)[int(len(param_latencies) * 0.95)], 2),
        },
        "dual_agreement_pct": round(dual_perfect / total_scenarios * 100, 2),
        "failures_count": len(failures),
        "failures": failures,
        "detailed_results": detailed_results,
    }

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)

    print(f"📁 Telemetria esportata in: {RESULTS_JSON}")
    print("=" * 95)

    if failures:
        print()
        print("❌ DETTAGLIO FALLIMENTI RILEVATI:")
        for fail in failures:
            print(f"  - [{fail['scenario']}] Modalita: {fail['mode']} -> {fail['reason']}")
        return 1

    print()
    print("✅ CERTIFICAZIONE SUPERATA: 80/80 QUERY SIMULATE AL 100.0% PASS CON ZERO DEFICIT!")
    return 0


if __name__ == "__main__":
    exit_code = run_40_dual_benchmark()
    sys.exit(exit_code)
