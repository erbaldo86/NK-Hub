"""
LabNK Bandi Intelligence — Real Concurrency Stress Test Crosscheck
Nexus Keystone v1.1.0-Universal | Concurrency & Thread-Safety Validator.
Executes concurrent queries (NLP, Parametric, Catalog) against FastAPI server and GrantsRepository.
"""

import sys
import os
import json
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPTS_DIR.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fastapi.testclient import TestClient
from src_app.server import app, service
from run_stress_test_80 import parse_stress_queries, QUERIES_FILE

REPORT_PATH = WORKSPACE_ROOT / "nk_tracking" / "reports_and_briefs" / "concurrency_stress_test_results.json"


def run_concurrency_test(num_workers: int = 16, repeat_count: int = 2) -> Dict[str, Any]:
    print("=" * 80)
    print("🚀 LABNK REAL CONCURRENCY CROSS-CHECK — THREAD-SAFE VALIDATION")
    print(f"👥 Workers: {num_workers} concurrent threads")
    print("=" * 80)

    nlp_queries, param_queries = parse_stress_queries(QUERIES_FILE)
    client = TestClient(app)

    # Warmup
    client.post("/api/search/nlp", json={"query": "Test warmup startup", "top_k": 5})
    client.post("/api/search/parametric", json={"regione": "Lombardia"})

    # Prepare query tasks
    tasks = []
    # 40 NLP queries * repeat_count
    for i in range(repeat_count):
        for q in nlp_queries:
            tasks.append(("nlp", q))

    # 40 Param queries * repeat_count
    for i in range(repeat_count):
        for q in param_queries:
            tasks.append(("param", q))

    # Add concurrent catalog read & atomic swap tasks
    swap_counter = 0
    stop_swap_event = threading.Event()

    def concurrent_swapper():
        nonlocal swap_counter
        initial_grants = dict(service._repo._grants)
        while not stop_swap_event.is_set():
            time.sleep(0.01)  # Swap every 10ms
            service.swap_grants_atomic(initial_grants)
            swap_counter += 1

    swap_thread = threading.Thread(target=concurrent_swapper, daemon=True)
    swap_thread.start()

    results_lock = threading.Lock()
    nlp_latencies = []
    param_latencies = []
    errors = []
    successes = 0

    def execute_task(task_type: str, item: Dict[str, Any]):
        nonlocal successes
        t0 = time.perf_counter()
        try:
            if task_type == "nlp":
                resp = client.post("/api/search/nlp", json={"query": item["query"], "top_k": 20})
                lat_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    assert "results" in data
                    assert "intent" in data
                    with results_lock:
                        nlp_latencies.append(lat_ms)
                        successes += 1
                else:
                    with results_lock:
                        errors.append(f"NLP {item['id']} failed with status {resp.status_code}")
            elif task_type == "param":
                resp = client.post("/api/search/parametric", json=item["payload"])
                lat_ms = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    assert "results" in data
                    assert "count" in data
                    with results_lock:
                        param_latencies.append(lat_ms)
                        successes += 1
                else:
                    with results_lock:
                        errors.append(f"Param {item['id']} failed with status {resp.status_code}")
        except Exception as e:
            with results_lock:
                errors.append(f"Exception on {task_type} {item.get('id')}: {str(e)}")

    total_tasks = len(tasks)
    print(f"[*] Avvio esecuzione di {total_tasks} richieste concorrenti...")
    start_total = time.perf_counter()

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(execute_task, t_type, item) for t_type, item in tasks]
        for f in as_completed(futures):
            f.result()

    total_time = time.perf_counter() - start_total
    stop_swap_event.set()
    swap_thread.join(timeout=1.0)

    # Calculate metrics
    throughput = total_tasks / total_time if total_time > 0 else 0
    nlp_mean = statistics.mean(nlp_latencies) if nlp_latencies else 0
    nlp_median = statistics.median(nlp_latencies) if nlp_latencies else 0
    nlp_p95 = statistics.quantiles(nlp_latencies, n=20)[18] if len(nlp_latencies) >= 20 else max(nlp_latencies, default=0)
    nlp_min = min(nlp_latencies) if nlp_latencies else 0
    nlp_max = max(nlp_latencies) if nlp_latencies else 0

    param_mean = statistics.mean(param_latencies) if param_latencies else 0
    param_median = statistics.median(param_latencies) if param_latencies else 0
    param_p95 = statistics.quantiles(param_latencies, n=20)[18] if len(param_latencies) >= 20 else max(param_latencies, default=0)
    param_min = min(param_latencies) if param_latencies else 0
    param_max = max(param_latencies) if param_latencies else 0

    all_latencies = nlp_latencies + param_latencies
    overall_mean = statistics.mean(all_latencies) if all_latencies else 0
    overall_p95 = statistics.quantiles(all_latencies, n=20)[18] if len(all_latencies) >= 20 else max(all_latencies, default=0)

    print("\n" + "=" * 80)
    print("📊 RISULTATI BENCHMARK CONCORRENZA & THREAD SAFETY")
    print("=" * 80)
    print(f"Richieste Totali:      {total_tasks}")
    print(f"Successi:             {successes}/{total_tasks} ({successes/total_tasks*100:.1f}%)")
    print(f"Errori / Eccezioni:   {len(errors)}")
    print(f"Atomic Swaps eseguiti:{swap_counter} (in background senza bloccare letture)")
    print(f"Tempo Totale:         {total_time:.3f} s")
    print(f"Throughput:           {throughput:.1f} req/s")
    print("-" * 80)
    print(f"NLP Latency ({len(nlp_latencies)} req):")
    print(f"  Media:  {nlp_mean:.2f} ms")
    print(f"  Mediana:{nlp_median:.2f} ms")
    print(f"  P95:    {nlp_p95:.2f} ms")
    print(f"  Min/Max:{nlp_min:.2f} ms / {nlp_max:.2f} ms")
    print("-" * 80)
    print(f"Parametric Latency ({len(param_latencies)} req):")
    print(f"  Media:  {param_mean:.2f} ms")
    print(f"  Mediana:{param_median:.2f} ms")
    print(f"  P95:    {param_p95:.2f} ms")
    print(f"  Min/Max:{param_min:.2f} ms / {param_max:.2f} ms")
    print("-" * 80)
    print(f"Overall Mean Latency: {overall_mean:.2f} ms  (Target < 15 ms: {'✅ PASS' if overall_mean < 15 else '❌ FAIL'})")
    print(f"Overall P95 Latency:  {overall_p95:.2f} ms")
    print("=" * 80)

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "test_type": "Real Concurrency Cross-Check",
        "concurrency_workers": num_workers,
        "total_requests": total_tasks,
        "success_rate_pct": round(successes / total_tasks * 100, 2),
        "errors_count": len(errors),
        "errors": errors[:10],
        "atomic_swaps_during_test": swap_counter,
        "elapsed_seconds": round(total_time, 3),
        "throughput_req_per_sec": round(throughput, 1),
        "nlp_metrics": {
            "count": len(nlp_latencies),
            "mean_ms": round(nlp_mean, 2),
            "median_ms": round(nlp_median, 2),
            "p95_ms": round(nlp_p95, 2),
            "min_ms": round(nlp_min, 2),
            "max_ms": round(nlp_max, 2)
        },
        "parametric_metrics": {
            "count": len(param_latencies),
            "mean_ms": round(param_mean, 2),
            "median_ms": round(param_median, 2),
            "p95_ms": round(param_p95, 2),
            "min_ms": round(param_min, 2),
            "max_ms": round(param_max, 2)
        },
        "overall_metrics": {
            "mean_ms": round(overall_mean, 2),
            "p95_ms": round(overall_p95, 2),
            "target_under_15ms": overall_mean < 15.0
        }
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"📁 Report concorrenza salvato in: {REPORT_PATH}")

    return report_data


def run_full_concurrency_suite():
    workers_levels = [1, 4, 8, 16]
    suite_summary = []
    for w in workers_levels:
        res = run_concurrency_test(num_workers=w, repeat_count=1)
        suite_summary.append({
            "workers": w,
            "requests": res["total_requests"],
            "throughput_rps": res["throughput_req_per_sec"],
            "nlp_mean_ms": res["nlp_metrics"]["mean_ms"],
            "param_mean_ms": res["parametric_metrics"]["mean_ms"],
            "overall_mean_ms": res["overall_metrics"]["mean_ms"],
            "success_rate": res["success_rate_pct"]
        })
    print("\n" + "=" * 80)
    print("📈 SCALABILITY & CONCURRENCY SCALING SUMMARY (1 -> 16 WORKERS)")
    print("=" * 80)
    print(f"{'Workers':<8} | {'Throughput (rps)':<18} | {'Overall Mean':<14} | {'NLP Mean':<12} | {'Param Mean':<12} | {'Success'}")
    print("-" * 80)
    for s in suite_summary:
        print(f"{s['workers']:<8} | {s['throughput_rps']:<18.1f} | {s['overall_mean_ms']:<14.2f}ms | {s['nlp_mean_ms']:<12.2f}ms | {s['param_mean_ms']:<12.2f}ms | {s['success_rate']:.1f}%")
    print("=" * 80)

    # Save comprehensive report
    comprehensive_path = WORKSPACE_ROOT / "nk_tracking" / "reports_and_briefs" / "concurrency_scaling_matrix.json"
    with open(comprehensive_path, "w", encoding="utf-8") as f:
        json.dump({"matrix": suite_summary}, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    run_full_concurrency_suite()
