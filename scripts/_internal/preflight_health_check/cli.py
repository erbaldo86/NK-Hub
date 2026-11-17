# -*- coding: utf-8 -*-
"""Punto di ingresso CLI per preflight_health_check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from _internal.preflight_health_check.checker import PreflightHealthChecker


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il verificatore preflight di NK Hub Generation."""
    parser = argparse.ArgumentParser(
        description="Pre-Flight Health Check & Auto-Sanitizer NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Esegue la verifica in sola lettura senza modificare o cancellare file",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Directory radice del workspace da controllare",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il report diagnostico in formato JSON strutturato",
    )
    args = parser.parse_args(argv)

    root_path = Path(args.root).resolve() if args.root else None
    checker = PreflightHealthChecker(workspace_root=root_path)
    results = checker.run_full_check(auto_fix=not args.check_only)
    print(json.dumps(results, indent=2))
    return 0 if results["status"] in ("PASS", "HEALTHY_GREEN") else 1
