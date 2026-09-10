"""
LabNK Bandi Intelligence — 60 Queries Real E2E Stress Test Runner
Nexus Keystone v1.1.0-Universal | Deterministic Test Utility.
Parses data/stress_test_queries_60.txt and executes 30 NLP + 30 Parametric queries against FastAPI server.
"""

import sys
import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Set UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
staging_root = WORKSPACE_ROOT / ".staging"
if staging_root.exists():
    if str(staging_root) in sys.path:
        sys.path.remove(str(staging_root))
    sys.path.insert(0, str(staging_root))

QUERIES_FILE = WORKSPACE_ROOT / "data" / "stress_test_queries_60.txt"
RESULTS_JSON = WORKSPACE_ROOT / "nk_tracking" / "reports_and_briefs" / "stress_test_results.json"


def parse_stress_queries(file_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parses data/stress_test_queries_60.txt into NLP and Parametric lists."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    
    # 1. Parse NLP queries
    nlp_queries = []
    nlp_blocks = re.findall(r"\[(NLP_STRESS_\d+)\]\s*\nQUERY:\s*(.+?)\s*\nSTRESS_TARGET:\s*(.+?)\s*\nCRITERIO_SUCCESSO:\s*(.+?)(?=\n\n\[|\n\n###|\Z)", content, re.DOTALL)
    for qid, qtext, target, criteria in nlp_blocks:
        nlp_queries.append({
            "id": qid.strip(),
            "query": qtext.strip(),
            "target": target.strip(),
            "criteria": criteria.strip()
        })

    # 2. Parse Parametric queries
    param_queries = []
    param_blocks = re.findall(r"\[(PARAM_STRESS_\d+)\]\s*\nPAYLOAD:\s*(\{[^\r\n]+\})\s*\nSTRESS_TARGET:\s*(.+?)\s*\nATTESO:\s*(.+?)(?=(?:\r?\n){2}\[|\Z)", content, re.DOTALL)
    for qid, payload_str, target, expected in param_blocks:
        try:
            payload = json.loads(payload_str.strip())
        except json.JSONDecodeError:
            payload = {}
        param_queries.append({
            "id": qid.strip(),
            "payload": payload,
            "target": target.strip(),
            "expected": expected.strip()
        })

    return nlp_queries, param_queries


def run_stress_suite(base_url: str = "http://127.0.0.1:8080") -> int:
    """Runs all 60 stress queries via httpx (or fallback to TestClient if server not on port)."""
    nlp_list, param_list = parse_stress_queries(QUERIES_FILE)
    print("=" * 80)
    print(f"🚀 LABNK BANDI INTELLIGENCE — 60 QUERIES LIVE STRESS TEST")
    print(f"📁 Source: {QUERIES_FILE.name} (30 NLP + 30 Parametriche)")
    print("=" * 80)

    import httpx
    client = None
    use_live_http = False

    # Check if live server is reachable on base_url
    try:
        r = httpx.get(f"{base_url}/health", timeout=2.0)
        if r.status_code == 200:
            print(f"🟢 Server live rilevato su {base_url} (Health: OK)")
            client = httpx.Client(base_url=base_url, timeout=15.0)
            use_live_http = True
    except Exception:
        pass

    if not use_live_http:
        print(f"ℹ️ Server non in ascolto su {base_url}. Utilizzo FastAPI TestClient in-process.")
        from fastapi.testclient import TestClient
        from src_app.server import app
        client = TestClient(app)

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_queries": len(nlp_list) + len(param_list),
        "passed": 0,
        "failed": 0,
        "nlp_results": [],
        "param_results": []
    }

    # Load Web Ground Truth Table if present
    ground_truth_file = WORKSPACE_ROOT / "data" / "web_ground_truth_table.json"
    ground_truth_map = {}
    if ground_truth_file.exists():
        try:
            gt_data = json.loads(ground_truth_file.read_text(encoding="utf-8"))
            ground_truth_map = {item["id"]: item for item in gt_data.get("ground_truth_entries", [])}
            print(f"🌐 Tabella di Riscontro Web caricata: {len(ground_truth_map)} scenari di benchmark attivi.")
        except Exception:
            pass

    # 1. Execute 30 NLP Queries
    print("\n--- [SEZIONE 1: 30 QUERY NLP DI TESTO LIBERO] ---")
    nlp_pass = 0
    for item in nlp_list:
        t0 = time.perf_counter()
        try:
            resp = client.post("/api/search/nlp", json={"query": item["query"], "top_k": 10})
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                res_count = len(data.get("results", []))
                intent = data.get("intent", {})
                nlp_pass += 1
                
                # Riscontro Web Benchmark
                gt_verdict = "OK"
                gt_entry = ground_truth_map.get(item["id"])
                if gt_entry:
                    min_exp = gt_entry.get("min_expected_count", 1)
                    if res_count == min_exp:
                        gt_verdict = "🟢 STESSI_RISULTATI (OK)"
                    elif res_count > min_exp:
                        gt_verdict = "⭐ PIÙ_RISULTATI (OTTIMO)"
                    else:
                        gt_verdict = "🔴 MENO_RISULTATI (DEFICIT -> TRIGGER LOOP)"
                
                print(f"  [PASS] {item['id']} ({latency_ms:.1f}ms) -> {res_count} bandi | Riscontro: {gt_verdict}")
                results["nlp_results"].append({
                    "id": item["id"], "status": "PASS", "latency_ms": latency_ms,
                    "count": res_count, "web_ground_truth": gt_verdict
                })
            else:
                print(f"  [FAIL] {item['id']} -> HTTP {resp.status_code}: {resp.text[:100]}")
                results["nlp_results"].append({"id": item["id"], "status": "FAIL", "error": resp.text[:150]})
        except Exception as exc:
            print(f"  [ERROR] {item['id']} -> Exception: {exc}")
            results["nlp_results"].append({"id": item["id"], "status": "ERROR", "error": str(exc)})

    # 2. Execute 30 Parametric Queries
    print("\n--- [SEZIONE 2: 30 QUERY PARAMETRICHE AVANZATE CONSULENTE] ---")
    param_pass = 0
    for item in param_list:
        t0 = time.perf_counter()
        try:
            resp = client.post("/api/search/parametric", json=item["payload"])
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                count = data.get("count", 0)
                param_pass += 1

                # Riscontro Web Benchmark
                gt_verdict = "OK"
                gt_entry = ground_truth_map.get(item["id"])
                if gt_entry:
                    min_exp = gt_entry.get("min_expected_count", 1)
                    if count == min_exp:
                        gt_verdict = "🟢 STESSI_RISULTATI (OK)"
                    elif count > min_exp:
                        gt_verdict = "⭐ PIÙ_RISULTATI (OTTIMO)"
                    else:
                        gt_verdict = "🔴 MENO_RISULTATI (DEFICIT -> TRIGGER LOOP)"

                print(f"  [PASS] {item['id']} ({latency_ms:.1f}ms) -> {count} bandi filtrati | Riscontro: {gt_verdict}")
                results["param_results"].append({
                    "id": item["id"], "status": "PASS", "latency_ms": latency_ms,
                    "count": count, "web_ground_truth": gt_verdict
                })
            else:
                print(f"  [FAIL] {item['id']} -> HTTP {resp.status_code}: {resp.text[:100]}")
                results["param_results"].append({"id": item["id"], "status": "FAIL", "error": resp.text[:150]})
        except Exception as exc:
            print(f"  [ERROR] {item['id']} -> Exception: {exc}")
            results["param_results"].append({"id": item["id"], "status": "ERROR", "error": str(exc)})

    total_pass = nlp_pass + param_pass
    total_queries = len(nlp_list) + len(param_list)
    results["passed"] = total_pass
    results["failed"] = total_queries - total_pass

    print("=" * 80)
    print(f"📊 RISULTATI FINALI STRESS TEST: {total_pass}/{total_queries} PASS ({total_pass/total_queries*100:.1f}%)")
    print(f"   ↳ NLP Queries: {nlp_pass}/{len(nlp_list)} ({nlp_pass/len(nlp_list)*100:.1f}%)")
    print(f"   ↳ Parametriche: {param_pass}/{len(param_list)} ({param_pass/len(param_list)*100:.1f}%)")
    print("=" * 80)

    # Save results to JSON
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"📁 Report salvato in: {RESULTS_JSON}")

    return 0 if total_pass == total_queries else 1


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    sys.exit(run_stress_suite(url))
