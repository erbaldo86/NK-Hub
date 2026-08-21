"""
Runtime Trace Inspector per NK-Oracle-Evaluator (CRV 3.0 GATE 3).
Intercetta le variabili e i salti condizionali in sandbox con Tail-Biased Truncation (<120 token per RULE-10.2).
"""

import sys
import json
import traceback

def inspect_execution_trace(trace_log_path: str, max_frames: int = 3) -> dict:
    """
    Esegue la Tail-Biased Truncation dei log di traccia runtime,
    estraendo solo gli ultimi N frame immediatamente precedenti al fallimento logico.
    """
    if not trace_log_path or not sys.exc_info()[0]:
        return {
            "status": "SUCCESS",
            "failing_trace_frames": [],
            "locals_snapshot": {},
            "token_count": 0
        }

    # Tail-Biased Truncation: seleziona solo gli ultimi N frame
    exc_type, exc_value, tb = sys.exc_info()
    frames = traceback.extract_tb(tb)[-max_frames:]
    
    formatted_frames = [
        f"{f.filename}:{f.lineno} in {f.name} -> {f.line}"
        for f in frames
    ]

    return {
        "status": "SUCCESS",
        "exception_type": str(exc_type.__name__) if exc_type else "None",
        "exception_message": str(exc_value) if exc_value else "",
        "failing_trace_frames": formatted_frames,
        "token_count": sum(len(f.split()) for f in formatted_frames)
    }

if __name__ == "__main__":
    print(json.dumps(inspect_execution_trace(""), indent=2))
