# -*- coding: utf-8 -*-
"""Classe NKComplianceChecker e punto di ingresso CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _internal.nk_compliance_checker.rules_evaluator import (
    evaluate_compliance_scores,
    extract_session_identifier,
    lookup_rsi_telemetry_score,
    read_jsonl_dicts_reversed,
    score_from_rsi_record,
    valid_numeric_score,
)
from _internal.nk_compliance_checker.transcript_scan import (
    CANONICAL_AP_TABLE,
    COMPLIANCE_CHECKER_VERSION,
    DDI_DIRECT_STREAK_LIMIT,
    _workspace_root,
    find_active_transcript,
    reconfigure_streams,
    scan_transcript_metrics,
)


def _facade_find_active() -> Optional[Path]:
    """Rispetta eventuali monkeypatch su nk_compliance_checker.find_active_transcript."""
    mod = sys.modules.get("nk_compliance_checker") or sys.modules.get(
        "scripts.nk_compliance_checker"
    )
    fn = getattr(mod, "find_active_transcript", None) if mod is not None else None
    return fn() if callable(fn) else find_active_transcript()


class NKComplianceChecker:
    """Auditor forense di sessione Dual-Schema e calcolatore della scorecard."""

    VERSION: str = COMPLIANCE_CHECKER_VERSION
    DDI_DIRECT_STREAK_LIMIT: int = DDI_DIRECT_STREAK_LIMIT
    AP_CATALOG = CANONICAL_AP_TABLE

    def __init__(self, workspace_root: Optional[Path] = None):
        reconfigure_streams()
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )

    def _lookup_rsi_telemetry_score(
        self, transcript_file: Optional[Path] = None
    ) -> Tuple[bool, int | float]:
        """Cerca il punteggio RSI valido per la sessione corrente."""
        return lookup_rsi_telemetry_score(self.workspace_root, transcript_file)

    def audit_transcript(
        self, transcript_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Scansiona transcript.jsonl e calcola i punteggi della scorecard."""
        if transcript_path is None:
            active = _facade_find_active()
            if not active:
                return {
                    "status": "ERROR",
                    "message": "No transcript path provided and no active transcript found.",
                }
            transcript_file = active
        else:
            transcript_file = Path(transcript_path).resolve()

        if not transcript_file.exists():
            return {
                "status": "ERROR",
                "message": f"Transcript file not found: {transcript_file}",
            }

        records, counters = scan_transcript_metrics(transcript_file)
        return evaluate_compliance_scores(self, transcript_file, records, counters)


def main() -> int:
    """Punto di ingresso CLI per il verificatore di conformita NK Hub Generation."""
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="NK Hub Generation Hard Compliance Checker 1.0.0-Generation"
    )
    parser.add_argument("--transcript", type=str, default=None, help="Percorso di transcript.jsonl da sottoporre ad audit")
    parser.add_argument("--min-score", type=int, default=80, help="Punteggio minimo richiesto per uscire con codice 0")
    parser.add_argument("--json", action="store_true", help="Stampa il risultato strutturato in formato JSON")

    args = parser.parse_args()
    checker = NKComplianceChecker()

    transcript_target: Optional[Path] = None
    if args.transcript:
        transcript_target = Path(args.transcript)
    else:
        transcript_target = _facade_find_active()
        if not transcript_target:
            print("❌ [NK-COMPLIANCE] Error: No transcript specified and no active transcript could be detected.")
            return 1

    res = checker.audit_transcript(transcript_target)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        scores = res.get("scores", {})
        status_sym = "🟢" if res.get("status") == "PASS" else "🔴"
        print(f"{status_sym} [NK-COMPLIANCE] Status: {res.get('status')} | Composite: {scores.get('composite_score')}/100")
        print(f"  - Operational Score: {scores.get('operational_score')}/100")
        print(f"  - Procedural Score:  {scores.get('procedural_score')}/100")
        for adv in res.get("advisories", []):
            print(f"  [ADVISORY] {adv}")
        for penalty in res.get("penalties", []):
            print(f"  ⚠️ {penalty}")

    procedural = res.get("scores", {}).get("procedural_score", 0)
    composite = res.get("scores", {}).get("composite_score", 0)

    if composite < args.min_score or procedural < args.min_score or res.get("status") != "PASS":
        return 1
    return 0
