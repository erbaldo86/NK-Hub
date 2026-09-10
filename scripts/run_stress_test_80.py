"""
LabNK Bandi Intelligence — 80 Queries Real E2E Stress Test Runner
Nexus Keystone v1.1.0-Universal | Deterministic Test Utility.
Parses data/stress_test_queries_80.txt and executes 40 NLP + 40 Parametric queries against FastAPI server.
Supports full suite execution or batch-based execution (--batch 1|2|3|4|all).
"""

import sys
import os
import re
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Set UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

QUERIES_FILE = WORKSPACE_ROOT / "data" / "stress_test_queries_80.txt"
RESULTS_JSON = WORKSPACE_ROOT / "nk_tracking" / "reports_and_briefs" / "stress_test_80_results.json"
GROUND_TRUTH_JSON = WORKSPACE_ROOT / "data" / "web_ground_truth_80.json"


def parse_stress_queries(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parses data/stress_test_queries_80.txt into NLP and Parametric lists."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")

    # 1. Parse NLP queries: [NLP_XX] \n QUERY: ... \n TARGET: ...
    nlp_queries = []
    nlp_blocks = re.findall(
        r"\[(NLP_\d+)\]\s*\nQUERY:\s*(.+?)\s*\nTARGET:\s*(.+?)(?=(?:\r?\n){2}\[|###|\Z)",
        content,
        re.DOTALL
    )
    for qid, qtext, target in nlp_blocks:
        nlp_queries.append({
            "id": qid.strip(),
            "query": qtext.strip(),
            "target": target.strip()
        })

    # 2. Parse Parametric queries: [PARAM_XX] \n PAYLOAD: {...}
    param_queries = []
    param_blocks = re.findall(
        r"\[(PARAM_\d+)\]\s*\nPAYLOAD:\s*(\{.*?\})\s*(?=\n\[|\Z)",
        content,
        re.DOTALL
    )
    for qid, payload_str in param_blocks:
        try:
            payload = json.loads(payload_str.strip())
        except json.JSONDecodeError as err:
            print(f"[-] Error decoding JSON for {qid}: {err}")
            payload = {}
        param_queries.append({
            "id": qid.strip(),
            "payload": payload
        })

    return nlp_queries, param_queries


def run_stress_suite(
    batch: str = "all",
    output_file: Optional[Path] = None,
    base_url: str = "http://127.0.0.1:8080"
) -> int:
    """Runs stress queries (full suite or specific batch) via FastAPI TestClient in-process or live HTTP."""
    if output_file is None:
        output_file = RESULTS_JSON

    nlp_all, param_all = parse_stress_queries(QUERIES_FILE)

    # Determine batch selection
    # Batch 1: NLP 01 - 20 (index 0..20)
    # Batch 2: NLP 21 - 40 (index 20..40)
    # Batch 3: PARAM 01 - 20 (index 0..20)
    # Batch 4: PARAM 21 - 40 (index 20..40)
    batch_str = str(batch).lower().strip()
    if batch_str == "1":
        nlp_list = nlp_all[0:20]
        param_list = []
        batch_title = "BATCH 1 (NLP 01 - 20)"
    elif batch_str == "2":
        nlp_list = nlp_all[20:40]
        param_list = []
        batch_title = "BATCH 2 (NLP 21 - 40)"
    elif batch_str == "3":
        nlp_list = []
        param_list = param_all[0:20]
        batch_title = "BATCH 3 (PARAMETRICHE 01 - 20)"
    elif batch_str == "4":
        nlp_list = []
        param_list = param_all[20:40]
        batch_title = "BATCH 4 (PARAMETRICHE 21 - 40)"
    else:
        nlp_list = nlp_all
        param_list = param_all
        batch_title = "SUITE COMPLETA 80 SCENARI (40 NLP + 40 PARAM)"

    print("=" * 80)
    print(f"🚀 LABNK BANDI INTELLIGENCE — STRESS TEST 80 SCENARI")
    print(f"📋 Esecuzione: {batch_title}")
    print(f"📁 Source: {QUERIES_FILE.name}")
    print("=" * 80)

    # In-process TestClient setup (fast, zero external port conflicts)
    from fastapi.testclient import TestClient
    from src_app.server import app
    client = TestClient(app)

    # Load Ground Truth metadata
    min_expected_default = 1
    if GROUND_TRUTH_JSON.exists():
        try:
            gt_data = json.loads(GROUND_TRUTH_JSON.read_text(encoding="utf-8"))
            min_expected_default = gt_data.get("min_expected_count", 1)
        except Exception:
            pass

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "batch": batch_str,
        "batch_title": batch_title,
        "total_queries": len(nlp_list) + len(param_list),
        "passed": 0,
        "deficits": 0,
        "failed_http": 0,
        "nlp_results": [],
        "param_results": []
    }

    # 1. Execute NLP Queries (if any in this batch)
    nlp_pass = 0
    nlp_deficits = 0
    if nlp_list:
        print(f"\n--- [QUERY NLP ({len(nlp_list)} Scenari)] ---")
        for item in nlp_list:
            t0 = time.perf_counter()
            try:
                resp = client.post("/api/search/nlp", json={"query": item["query"], "top_k": 20})
                latency_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    res_items = data.get("results", [])
                    res_count = len(res_items)
                    intent = data.get("intent", {})

                    if res_count == min_expected_default:
                        gt_verdict = "🟢 STESSI_RISULTATI (PASS)"
                        nlp_pass += 1
                    elif res_count > min_expected_default:
                        gt_verdict = "⭐ PIÙ_RISULTATI (EXCELLENT)"
                        nlp_pass += 1
                    else:
                        gt_verdict = "🔴 MENO_RISULTATI (DEFICIT)"
                        nlp_deficits += 1

                    top_title = res_items[0]["grant"]["titolo"][:40] if res_count > 0 else "NESSUN RISULTATO"
                    print(f"  [{'PASS' if res_count >= min_expected_default else 'FAIL'}] {item['id']} ({latency_ms:.1f}ms) -> {res_count} bandi [Top: '{top_title}...'] | {gt_verdict}")
                    results["nlp_results"].append({
                        "id": item["id"],
                        "status": "PASS" if res_count >= min_expected_default else "DEFICIT",
                        "latency_ms": round(latency_ms, 2),
                        "count": res_count,
                        "verdict": gt_verdict,
                        "target": item.get("target"),
                        "inferred_region": intent.get("inferred_region"),
                        "inferred_ateco": intent.get("inferred_ateco_codes")
                    })
                else:
                    print(f"  [ERROR_HTTP] {item['id']} -> HTTP {resp.status_code}: {resp.text[:100]}")
                    results["nlp_results"].append({
                        "id": item["id"], "status": "ERROR_HTTP", "error": resp.text[:150]
                    })
                    results["failed_http"] += 1
            except Exception as exc:
                print(f"  [EXCEPTION] {item['id']} -> {exc}")
                results["nlp_results"].append({
                    "id": item["id"], "status": "EXCEPTION", "error": str(exc)
                })
                results["failed_http"] += 1

    # 2. Execute Parametric Queries (if any in this batch)
    param_pass = 0
    param_deficits = 0
    if param_list:
        print(f"\n--- [QUERY PARAMETRICHE ({len(param_list)} Scenari)] ---")
        for item in param_list:
            t0 = time.perf_counter()
            try:
                resp = client.post("/api/search/parametric", json=item["payload"])
                latency_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    res_items = data.get("results", [])
                    count = data.get("count", len(res_items))

                    if count == min_expected_default:
                        gt_verdict = "🟢 STESSI_RISULTATI (PASS)"
                        param_pass += 1
                    elif count > min_expected_default:
                        gt_verdict = "⭐ PIÙ_RISULTATI (EXCELLENT)"
                        param_pass += 1
                    else:
                        gt_verdict = "🔴 MENO_RISULTATI (DEFICIT)"
                        param_deficits += 1

                    top_title = res_items[0]["titolo"][:40] if count > 0 else "NESSUN RISULTATO"
                    print(f"  [{'PASS' if count >= min_expected_default else 'FAIL'}] {item['id']} ({latency_ms:.1f}ms) -> {count} bandi filtrati [Top: '{top_title}...'] | {gt_verdict}")
                    results["param_results"].append({
                        "id": item["id"],
                        "status": "PASS" if count >= min_expected_default else "DEFICIT",
                        "latency_ms": round(latency_ms, 2),
                        "count": count,
                        "verdict": gt_verdict,
                        "payload": item.get("payload")
                    })
                else:
                    print(f"  [ERROR_HTTP] {item['id']} -> HTTP {resp.status_code}: {resp.text[:100]}")
                    results["param_results"].append({
                        "id": item["id"], "status": "ERROR_HTTP", "error": resp.text[:150]
                    })
                    results["failed_http"] += 1
            except Exception as exc:
                print(f"  [EXCEPTION] {item['id']} -> {exc}")
                results["param_results"].append({
                    "id": item["id"], "status": "EXCEPTION", "error": str(exc)
                })
                results["failed_http"] += 1

    total_pass = nlp_pass + param_pass
    total_deficits = nlp_deficits + param_deficits
    total_queries = len(nlp_list) + len(param_list)

    results["passed"] = total_pass
    results["deficits"] = total_deficits

    print("=" * 80)
    pct = (total_pass / total_queries * 100) if total_queries > 0 else 0.0
    print(f"📊 RISULTATI BATCH: {total_pass}/{total_queries} PASS ({pct:.1f}%) | DEFICIT: {total_deficits}")
    if nlp_list:
        print(f"   ↳ NLP: {nlp_pass}/{len(nlp_list)} PASS | {nlp_deficits} Deficit")
    if param_list:
        print(f"   ↳ Parametriche: {param_pass}/{len(param_list)} PASS | {param_deficits} Deficit")
    print("=" * 80)

    # Save results to JSON file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"📁 Report salvato in: {output_file}")

    return 0 if (total_deficits == 0 and results["failed_http"] == 0 and total_pass == total_queries) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="LabNK 80 Queries Stress Test Runner")
    parser.add_argument(
        "--batch",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "all"],
        help="Batch da eseguire: 1 (NLP 01-20), 2 (NLP 21-40), 3 (PARAM 01-20), 4 (PARAM 21-40), all (tutti gli 80 scenari)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Percorso file JSON di output (default: nk_tracking/reports_and_briefs/stress_test_80_results.json)"
    )
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else None
    return run_stress_suite(batch=args.batch, output_file=out_path)


if __name__ == "__main__":
    sys.exit(main())
