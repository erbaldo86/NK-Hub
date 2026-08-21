import json
import os
import time

def generate_discrepancy_report(
    task_id: str,
    target_component: str,
    expected_values: dict,
    actual_values: dict,
    error_trace: str = None
) -> dict:
    """
    Genera un Report JSON Strutturato di Discrepanza per guidare il Writer
    con informazioni chirurgiche anziché feedback generici.
    """
    discrepancies = []
    for key, exp_val in expected_values.items():
        act_val = actual_values.get(key)
        if act_val != exp_val:
            discrepancies.append({
                "field": key,
                "expected": exp_val,
                "actual": act_val,
                "delta": abs(exp_val - act_val) if isinstance(exp_val, (int, float)) and isinstance(act_val, (int, float)) else "N/A"
            })
            
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task_id": task_id,
        "component": target_component,
        "status": "FAIL" if discrepancies or error_trace else "PASS",
        "total_discrepancies": len(discrepancies),
        "discrepancies": discrepancies,
        "error_trace": error_trace
    }
    return report

if __name__ == "__main__":
    print("[NK-Oracle-Evaluator] Discrepancy Report Generator Ready.")
