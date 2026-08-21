"""
Quality Baseline Manager per NK TAS 3.0 / CRV 3.0 (GATE 5).
Gestisce il file quality_baseline.json con la regola Ratchet di non-regressione
e la Graceful Metric Degradation per i moduli opzionali disattivati.
"""

import sys
import json
import os
from datetime import datetime

BASELINE_FILENAME = "quality_baseline.json"


def load_baseline(baseline_path: str) -> dict:
    if os.path.exists(baseline_path):
        try:
            with open(baseline_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def create_default_baseline(project_name: str, metrics: dict) -> dict:
    return {
        "_version": "1.0",
        "project": project_name,
        "baseline_date": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "metrics": metrics,
        "ratchet_rule": "no_metric_may_worsen",
        "history": [
            {
                "timestamp": datetime.now().isoformat(),
                "metrics": metrics
            }
        ]
    }


def check_baseline_compliance(baseline_path: str, current_metrics: dict, project_name: str = "NK_Project") -> dict:
    """
    Verifica che nessuna metrica corrente sia regredita rispetto al baseline.
    Applica la Graceful Metric Degradation per dimensioni mancanti.
    """
    baseline = load_baseline(baseline_path)
    
    # Se il baseline non esiste, crealo al primo commit
    if not baseline:
        new_baseline = create_default_baseline(project_name, current_metrics)
        os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(new_baseline, f, indent=2)
        return {
            "status": "INITIALIZED",
            "verdict": "PASS",
            "message": f"Nuovo baseline di qualità inizializzato in {baseline_path}",
            "regressions": []
        }

    baseline_metrics = baseline.get("metrics", {})
    regressions = []

    # Valutazione per ciascuna metrica presente sia nel baseline che nei dati correnti (Graceful Degradation)
    for metric_key, current_val in current_metrics.items():
        if metric_key in baseline_metrics:
            base_info = baseline_metrics[metric_key]
            base_val = base_info.get("value") if isinstance(base_info, dict) else base_info
            direction = base_info.get("direction", "lower_is_better") if isinstance(base_info, dict) else "lower_is_better"

            if direction == "lower_is_better" and current_val > base_val:
                regressions.append({
                    "metric": metric_key,
                    "baseline_value": base_val,
                    "current_value": current_val,
                    "direction": direction,
                    "message": f"Metrica {metric_key} peggiorata: {base_val} -> {current_val} (atteso <= {base_val})"
                })
            elif direction == "higher_is_better" and current_val < base_val:
                regressions.append({
                    "metric": metric_key,
                    "baseline_value": base_val,
                    "current_value": current_val,
                    "direction": direction,
                    "message": f"Metrica {metric_key} regredita: {base_val} -> {current_val} (atteso >= {base_val})"
                })

    verdict = "FAIL" if len(regressions) > 0 else "PASS"

    return {
        "status": "SUCCESS",
        "verdict": verdict,
        "baseline_date": baseline.get("baseline_date"),
        "metrics_checked": len([k for k in current_metrics if k in baseline_metrics]),
        "regressions": regressions
    }


def update_baseline_metrics(baseline_path: str, new_metrics: dict) -> dict:
    """
    Aggiorna il baseline con le nuove metriche dopo un commit verificato.
    """
    baseline = load_baseline(baseline_path)
    if not baseline:
        return check_baseline_compliance(baseline_path, new_metrics)

    baseline["last_updated"] = datetime.now().isoformat()
    
    # Aggiorna i valori
    for k, v in new_metrics.items():
        if k in baseline["metrics"] and isinstance(baseline["metrics"][k], dict):
            baseline["metrics"][k]["value"] = v
        else:
            baseline["metrics"][k] = {"value": v, "direction": "lower_is_better"}

    baseline.setdefault("history", []).append({
        "timestamp": datetime.now().isoformat(),
        "metrics": new_metrics
    })

    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)

    return {
        "status": "UPDATED",
        "message": f"Quality Baseline aggiornato con successo in {baseline_path}"
    }


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        cmd = sys.argv[1]
        b_path = sys.argv[2]
        if cmd == "check" and len(sys.argv) >= 4:
            m_json = sys.argv[3]
            metrics = json.loads(m_json)
            res = check_baseline_compliance(b_path, metrics)
            print(json.dumps(res, indent=2))
        elif cmd == "update" and len(sys.argv) >= 4:
            m_json = sys.argv[3]
            metrics = json.loads(m_json)
            res = update_baseline_metrics(b_path, metrics)
            print(json.dumps(res, indent=2))
        else:
            print(json.dumps({"status": "ERROR", "message": "Comando non valido. Usa 'check' o 'update'."}))
    else:
        print(json.dumps({"status": "INFO", "usage": "python quality_baseline_manager.py check|update path/to/baseline.json '{\"metric\": 1}'"}))
