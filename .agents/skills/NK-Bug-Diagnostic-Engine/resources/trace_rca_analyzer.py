"""
Trace-Guided RCA Analyzer per NK-Bug-Diagnostic-Engine (CRV 3.0).
Correla i log di runtime trace, le asserzioni di test e le discrepanze visive
per produrre la suggested_fix_area ed il root_cause_hint.
"""

import sys
import json

def analyze_trace_rca(trace_data: dict, discrepancy_data: dict) -> dict:
    """
    Correla la traccia di runtime con la discrepanza per identificare la causa radice.
    """
    failing_frames = trace_data.get("failing_trace_frames", [])
    expected = discrepancy_data.get("expected", {})
    actual = discrepancy_data.get("actual", {})

    suggested_fix = "Sconosciuta"
    if failing_frames:
        suggested_fix = failing_frames[-1]

    root_cause = f"Discrepanza tra atteso ({expected}) ed effettivo ({actual})"
    if "exception_message" in trace_data and trace_data["exception_message"]:
        root_cause += f" | Errore Runtime: {trace_data['exception_message']}"

    return {
        "status": "SUCCESS",
        "root_cause_hint": root_cause[:150],
        "suggested_fix_area": suggested_fix,
        "confidence": 0.88 if failing_frames else 0.60
    }

if __name__ == "__main__":
    sample_trace = {"failing_trace_frames": ["formatters.py:44 in format_currency"], "exception_message": "ValueError"}
    sample_disc = {"expected": "100", "actual": "None"}
    print(json.dumps(analyze_trace_rca(sample_trace, sample_disc), indent=2))
