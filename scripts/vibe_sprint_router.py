#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di routing Mode A/B/C per Nexus Keystone v3.0.0-STE100-Unified.
Calcola la reale profondita AST max_depth e applica la soglia <= 150 LOC per Mode C.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class _ASTDepthVisitor(ast.NodeVisitor):
    """Calcola la profondita massima di annidamento del flusso di controllo AST."""

    _CONTROL_NODES = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
    )

    def __init__(self) -> None:
        self.current_depth: int = 0
        self.max_depth: int = 0

    def generic_visit(self, node: ast.AST) -> None:
        is_branch = isinstance(node, self._CONTROL_NODES)
        if is_branch:
            self.current_depth += 1
            if self.current_depth > self.max_depth:
                self.max_depth = self.current_depth
        super().generic_visit(node)
        if is_branch:
            self.current_depth -= 1


class VibeSprintRouter:
    """Valuta il rischio strutturale AST e seleziona la modalita operativa (Mode A, B o C)."""

    MODE_C_MAX_LOC: int = 150

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        if workspace_root is None:
            self.workspace_root = Path(__file__).resolve().parent.parent
        else:
            self.workspace_root = Path(workspace_root).resolve()
        self.staging_dir = self.workspace_root / ".staging"

    def compute_ast_risk_score(
        self,
        source_code: str,
        filename: str = "snippet.py",
    ) -> Dict[str, Any]:
        """Calcola il punteggio di rischio AST (0.0 - 1.0) e la profondita max_depth."""
        if not filename.endswith(".py"):
            lines = [
                line.strip() for line in source_code.splitlines() if line.strip()
            ]
            loc = len(lines)
            risk = min(1.0, round(loc / 300.0, 2))
            eligible = risk <= 0.5 and loc <= self.MODE_C_MAX_LOC
            recommended_mode = "mode_c" if eligible else ("mode_b" if loc <= 300 else "mode_a")
            return {
                "risk_score": risk,
                "mode_eligible": eligible,
                "recommended_mode": recommended_mode,
                "max_depth": 0,
                "reason": f"Non-Python asset ({loc} LOC). Mode C eligible: {eligible}",
                "loc": loc,
            }

        try:
            tree = ast.parse(source_code, filename=filename)
        except SyntaxError as exc:
            return {
                "risk_score": 1.0,
                "mode_eligible": False,
                "recommended_mode": "mode_a",
                "max_depth": 0,
                "reason": f"SyntaxError in code: {exc}",
                "loc": len(source_code.splitlines()),
            }

        class_count = 0
        func_count = 0
        import_count = 0
        loc = len(source_code.splitlines())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_count += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_count += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                import_count += 1

        depth_visitor = _ASTDepthVisitor()
        depth_visitor.visit(tree)
        max_depth = depth_visitor.max_depth

        depth_penalty = min(0.25, max(0, max_depth - 2) * 0.05)
        risk = (
            min(0.35, (loc / 250.0) * 0.35)
            + min(0.25, class_count * 0.12)
            + min(0.15, import_count * 0.04)
            + min(0.10, func_count * 0.02)
            + depth_penalty
        )
        risk = round(min(1.0, risk), 2)
        eligible = risk <= 0.5 and loc <= self.MODE_C_MAX_LOC and max_depth <= 6

        if eligible:
            recommended_mode = "mode_c"
        elif risk <= 0.75 and loc <= 350:
            recommended_mode = "mode_b"
        else:
            recommended_mode = "mode_a"

        return {
            "risk_score": risk,
            "mode_eligible": eligible,
            "recommended_mode": recommended_mode,
            "loc": loc,
            "classes": class_count,
            "functions": func_count,
            "imports": import_count,
            "max_depth": max_depth,
            "reason": (
                "Safe for Mode C Vibe-Sprint"
                if eligible
                else "Exceeds Mode C risk threshold (requires Mode A/B)"
            ),
        }

    def generate_inline_micro_spec(
        self,
        target_file: str,
        change_intent: str,
        risk_info: Dict[str, Any],
    ) -> str:
        """Sintetizza una micro-specifica inline inferiore a 150 token."""
        capsule = self.load_prewarmed_capsule()
        capsule_summary = str(capsule.get("capsule_text", "")).strip()
        if not capsule_summary and isinstance(capsule.get("lessons"), list):
            capsule_summary = " | ".join(
                str(item.get("lesson", ""))
                for item in capsule["lessons"][:3]
                if isinstance(item, dict) and item.get("lesson")
            ).strip()
        spec = [
            f"[NK-VIBE-SPRINT-SPEC | Target: {target_file}]",
            f"Intent: {change_intent.strip()}",
            f"Risk Score: {risk_info.get('risk_score', 0.0)} | LOC: {risk_info.get('loc', 0)} | Max Depth: {risk_info.get('max_depth', 0)}",
            "Mode: Mode C (Fast Staging -> AST Guard -> Zero-Mock Verification -> 2PC Commit)",
            "Safety Invariant: Zero-Mock / Real fixture adherence.",
        ]
        if capsule_summary:
            spec.append(f"Tier-1 Capsule: {capsule_summary[:240]}")
        return "\n".join(spec)

    def load_prewarmed_capsule(self) -> Dict[str, Any]:
        """Carica la capsula di memoria Tier-1 pre-riscaldata se disponibile."""
        candidates = (
            self.staging_dir / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.workspace_root / "nk_tracking" / "memory" / "tier1_active_capsule.json",
        )
        for cand in candidates:
            if cand.exists():
                try:
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {
            "status": "EMPTY",
            "capsule_text": "",
            "token_count": 0,
            "token_cap": 350,
            "entries": [],
        }


def load_prewarmed_capsule(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Funzione helper di modulo per caricare la capsula Tier-1 pre-riscaldata."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.load_prewarmed_capsule()


def run_test() -> int:
    """Esegue l'autotest rapido del router Mode C."""
    router = VibeSprintRouter()
    code_sample = '''
def calculate_vat(amount: float, rate: float = 0.22) -> float:
    """Calcola l'IVA per una transazione."""
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    return round(amount * rate, 2)
'''
    res = router.compute_ast_risk_score(code_sample, "tax_calculator.py")
    assert res["mode_eligible"] is True
    assert res["max_depth"] >= 2
    spec = router.generate_inline_micro_spec(
        "src_app/utils/tax.py",
        "Add VAT calculation",
        res,
    )
    assert "NK-VIBE-SPRINT-SPEC" in spec
    print(f"VibeSprintRouter test PASS: Risk {res['risk_score']} | Depth {res['max_depth']}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il router Mode A/B/C di Nexus Keystone."""
    parser = argparse.ArgumentParser(
        description="Router Mode A/B/C basato sul rischio AST per Nexus Keystone"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Esegue l'autotest rapido del router",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Vibe Sprint Change",
        help="Descrizione sintetica dell'intento di modifica",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Elenco dei file sorgente da valutare per il routing",
    )
    parser.add_argument(
        "--capsule",
        action="store_true",
        help="Include e stampa la capsula di memoria Tier-1 pre-riscaldata",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il verdetto di routing in formato JSON",
    )
    args = parser.parse_args(argv)

    if args.test:
        return run_test()

    router = VibeSprintRouter()
    if args.files:
        results: List[Dict[str, Any]] = []
        for file_arg in args.files:
            p = Path(file_arg)
            if not p.is_absolute():
                p = (router.workspace_root / p).resolve()
            if p.exists() and p.is_file():
                code = p.read_text(encoding="utf-8", errors="replace")
                info = router.compute_ast_risk_score(code, p.name)
            else:
                info = router.compute_ast_risk_score("", p.name)
            info["file"] = str(file_arg)
            info["micro_spec"] = router.generate_inline_micro_spec(
                str(file_arg),
                args.prompt,
                info,
            )
            results.append(info)
        payload: Dict[str, Any] = {"files": results}
        if args.capsule:
            payload["tier1_capsule"] = router.load_prewarmed_capsule()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for item in results:
                print(item["micro_spec"])
        return 0

    if args.capsule:
        cap = router.load_prewarmed_capsule()
        print(json.dumps(cap, indent=2))
        return 0

    print("VibeSprintRouter CLI ready. Use --test to validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
