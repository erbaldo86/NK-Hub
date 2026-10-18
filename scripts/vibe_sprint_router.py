#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motore di routing Mode A/B/C/D per Nexus Keystone v3.5.0.
Calcola la reale profondita AST max_depth e applica la soglia <= 150 LOC per Mode C.
Supporta Mode D e risolve il dominio O(1) tramite nk_registry_manifest.json.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_WORKSPACE_ROOT = (
    _SCRIPT_DIR.parent.parent
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR.parent
)

MODE_D_KEYWORDS: Tuple[str, ...] = (
    "audit",
    "benchmark",
    "discovery",
    "ricerca",
    "analizza",
    "analisi",
    "quanti bandi",
    "copertura",
    "censimento",
    "mappatura",
    "esplora",
    "read-only",
    "readonly",
    "report analitico",
    "stato dell'arte",
)

MODE_D_LABEL: str = (
    "Mode D (Analytical Discovery & Benchmark - 100% Read-Only + MCP/Web)"
)

DOMAIN_TO_NATIVE_SUBAGENT: Dict[str, str] = {
    "DOM-01": "NK-Specifier-Agent",
    "DOM-02": "NK-Specifier-Agent",
    "DOM-03": "NK-Builder-Agent",
    "DOM-04": "NK-Security-DAST-Auditor",
    "DOM-05": "NK-Scribe-Agent",
}

_RSI_AUDITOR_SKILLS = frozenset(
    {"NK-Oracle-Evaluator", "NK-State-Router", "NK-Plan-Aligner"}
)
_RSI_AUDITOR_KEYWORDS: Tuple[str, ...] = (
    "rsi",
    "oracolo",
    "oracle",
    "cold review",
    "ste100",
    "tetralogia",
)
_ROUTER_MANIFEST_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def _resolve_native_subagent(
    domain_id: str,
    matched_skill: Optional[str] = None,
    text: str = "",
) -> str:
    """Risolve il Sub-Agente Nativo instradando query RSI e Oracolo su NK-RSI-Auditor."""
    if matched_skill and matched_skill in _RSI_AUDITOR_SKILLS:
        return "NK-RSI-Auditor"
    text_low = (text or "").strip().lower()
    if text_low:
        tokens = set(
            "".join(ch if ch.isalnum() or ch == "_" else " " for ch in text_low).split()
        )
        for kw in _RSI_AUDITOR_KEYWORDS:
            if (" " in kw and kw in text_low) or kw in tokens:
                return "NK-RSI-Auditor"
    return DOMAIN_TO_NATIVE_SUBAGENT.get(domain_id, "NK-Builder-Agent")


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
    """Valuta il rischio strutturale AST e seleziona la modalita operativa (Mode A, B, C o D)."""

    MODE_C_MAX_LOC: int = 150
    DISCOVERY_KEYWORDS: Tuple[str, ...] = MODE_D_KEYWORDS

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        if workspace_root is None:
            self.workspace_root = _DEFAULT_WORKSPACE_ROOT
        else:
            self.workspace_root = Path(workspace_root).resolve()
        self.staging_dir = self.workspace_root / ".staging"

    def _load_registry_manifest(self) -> Dict[str, Any]:
        """Carica nk_registry_manifest.json da staging o root con cache statica O(1)."""
        candidates = (
            self.staging_dir / "nk_genome" / "nk_registry_manifest.json",
            self.workspace_root / "nk_genome" / "nk_registry_manifest.json",
            _DEFAULT_WORKSPACE_ROOT / ".staging" / "nk_genome" / "nk_registry_manifest.json",
            _DEFAULT_WORKSPACE_ROOT / "nk_genome" / "nk_registry_manifest.json",
        )
        for cand in candidates:
            if cand.exists() and cand.is_file():
                try:
                    st = cand.stat()
                    key = str(cand)
                    cached = _ROUTER_MANIFEST_CACHE.get(key)
                    if (
                        cached is not None
                        and cached[0] == st.st_mtime_ns
                        and cached[1] == st.st_size
                    ):
                        return cached[2]
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        _ROUTER_MANIFEST_CACHE[key] = (
                            st.st_mtime_ns,
                            st.st_size,
                            data,
                        )
                        return data
                except Exception:
                    pass
        return {}

    def resolve_domain_from_manifest(self, prompt: str) -> Dict[str, Any]:
        """Risolve in O(1) il dominio funzionale DOM-01..DOM-05 interrogando il manifesto SSOT."""
        text_lower = (prompt or "").strip().lower()
        manifest = self._load_registry_manifest()
        domains = manifest.get("domains", {})
        skills_index = manifest.get("skills_index", {})
        scripts_index = manifest.get("scripts_index", {})
        dispatch_table = manifest.get("intent_dispatch_table", {})

        # 1. Riferimento esplicito a ID dominio nel prompt (es. DOM-04)
        for dom_id, dom_meta in domains.items():
            if dom_id.lower() in text_lower or dom_meta.get("name", "").lower() in text_lower:
                primary_sk = dom_meta.get("primary_skill", "NK-Master-Hub")
                return {
                    "domain_id": dom_id,
                    "domain_name": dom_meta.get("name", ""),
                    "primary_skill": primary_sk,
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [dom_id],
                }

        # 2. Riferimento esplicito a una skill o script nel prompt
        for sk_name, sk_meta in skills_index.items():
            if sk_name.lower() in text_lower:
                dom_id = sk_meta.get("domain_id", "DOM-01")
                return {
                    "domain_id": dom_id,
                    "domain_name": sk_meta.get("domain_name", "GOV_AND_ROUTING"),
                    "primary_skill": sk_name,
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=sk_name, text=text_lower
                    ),
                    "matched_triggers": [sk_name],
                }

        for sc_name, sc_meta in scripts_index.items():
            stem = sc_name[:-3].lower() if sc_name.endswith(".py") else sc_name.lower()
            if sc_name.lower() in text_lower or stem in text_lower:
                dom_id = sc_meta.get("domain_id", "DOM-03")
                dom_meta = domains.get(dom_id, {})
                primary_sk = dom_meta.get("primary_skill", "NK-Python-Async-Builder")
                return {
                    "domain_id": dom_id,
                    "domain_name": sc_meta.get("domain_name", "BUILD_AND_HEAL"),
                    "primary_skill": primary_sk,
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [sc_name],
                }

        # 3. Punteggio keyword tramite domains e intent_dispatch_table
        tokens = set(
            "".join(ch if ch.isalnum() or ch == "_" else " " for ch in text_lower).split()
        )
        best_dom_id = ""
        best_score = 0
        best_triggers: List[str] = []

        for dom_id, dom_meta in domains.items():
            kws = dom_meta.get("keywords", [])
            hits = [
                kw
                for kw in kws
                if kw.lower() in tokens or (len(kw) >= 4 and kw.lower() in text_lower)
            ]
            if len(hits) > best_score:
                best_score = len(hits)
                best_dom_id = dom_id
                best_triggers = hits

        if best_dom_id and best_score > 0:
            dom_meta = domains[best_dom_id]
            primary_sk = dom_meta.get("primary_skill", "NK-Master-Hub")
            return {
                "domain_id": best_dom_id,
                "domain_name": dom_meta.get("name", ""),
                "primary_skill": primary_sk,
                "native_subagent": _resolve_native_subagent(
                    best_dom_id, matched_skill=primary_sk, text=text_lower
                ),
                "matched_triggers": best_triggers,
            }

        for kw, entry in dispatch_table.items():
            if kw in tokens or (len(kw) >= 4 and kw in text_lower):
                dom_id = entry.get("domain_id", "DOM-03")
                primary_sk = entry.get("primary_agent", "NK-Python-Async-Builder")
                return {
                    "domain_id": dom_id,
                    "domain_name": entry.get("domain_name", "BUILD_AND_HEAL"),
                    "primary_skill": primary_sk,
                    "native_subagent": _resolve_native_subagent(
                        dom_id, matched_skill=primary_sk, text=text_lower
                    ),
                    "matched_triggers": [kw],
                }

        is_disc = any(kw in text_lower for kw in self.DISCOVERY_KEYWORDS)
        if is_disc:
            return {
                "domain_id": "DOM-02",
                "domain_name": "IDEATION_AND_ARCH",
                "primary_skill": "NK-Ideator",
                "native_subagent": _resolve_native_subagent(
                    "DOM-02", matched_skill="NK-Ideator", text=text_lower
                ),
                "matched_triggers": [],
            }
        return {
            "domain_id": "DOM-03",
            "domain_name": "BUILD_AND_HEAL",
            "primary_skill": "NK-Python-Async-Builder",
            "native_subagent": _resolve_native_subagent(
                "DOM-03", matched_skill="NK-Python-Async-Builder", text=text_lower
            ),
            "matched_triggers": [],
        }

    def classify_prompt_intent(
        self,
        prompt: str,
        files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Classifica il prompt, attiva Mode D su discovery e arricchisce con domain_id."""
        text_lower = (prompt or "").strip().lower()
        has_code_files = bool(files and len(files) > 0)
        matched = [kw for kw in self.DISCOVERY_KEYWORDS if kw in text_lower]
        domain_info = self.resolve_domain_from_manifest(prompt)

        if matched and not has_code_files:
            return {
                "recommended_mode": "mode_d",
                "mode": MODE_D_LABEL,
                "mode_label": MODE_D_LABEL,
                "is_discovery": True,
                "read_only": True,
                "matched_keywords": matched,
                "primary_agent": "NK-Ideator",
                "native_subagent": "NK-Specifier-Agent",
                "fast_bypass_eligible": False,
                "domain_id": domain_info["domain_id"],
                "domain_name": domain_info["domain_name"],
                "tools_allowed": [
                    "view_file",
                    "search_web",
                    "read_url_content",
                    "call_mcp_tool",
                    "list_resources",
                    "read_resource",
                ],
                "prompt": prompt,
                "reason": (
                    f"Analytical discovery intent detected via keywords: {matched}"
                ),
            }

        return {
            "recommended_mode": "mode_c",
            "mode": "Mode A/B/C (Code & Specification Routing)",
            "mode_label": "Mode A/B/C (Code & Specification Routing)",
            "is_discovery": False,
            "read_only": False,
            "matched_keywords": matched,
            "primary_agent": "NK-Python-Async-Builder",
            "native_subagent": domain_info.get(
                "native_subagent",
                _resolve_native_subagent(
                    domain_info["domain_id"],
                    matched_skill=domain_info.get("primary_skill"),
                    text=text_lower,
                ),
            ),
            "fast_bypass_eligible": True,
            "domain_id": domain_info["domain_id"],
            "domain_name": domain_info["domain_name"],
            "tools_allowed": [],
            "prompt": prompt,
            "reason": "Standard implementation or file modification routing.",
        }

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
            recommended_mode = (
                "mode_c" if eligible else ("mode_b" if loc <= 300 else "mode_a")
            )
            return {
                "risk_score": risk,
                "mode_eligible": eligible,
                "fast_bypass_eligible": eligible,
                "native_subagent": "NK-Builder-Agent",
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
                "fast_bypass_eligible": False,
                "native_subagent": "NK-Builder-Agent",
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
            "fast_bypass_eligible": eligible,
            "native_subagent": "NK-Builder-Agent",
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
        """Carica la capsula di memoria Tier-1 pre-riscaldata con fallback a memory_3tier."""
        candidates = (
            self.staging_dir / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.workspace_root / "nk_tracking" / "memory" / "tier1_active_capsule.json",
            self.staging_dir / "nk_tracking" / "memory_3tier" / "tier1_active_capsule.json",
            self.workspace_root / "nk_tracking" / "memory_3tier" / "tier1_active_capsule.json",
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


def resolve_domain_from_manifest(
    prompt: str,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per risolvere il dominio O(1) dal manifesto SSOT."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.resolve_domain_from_manifest(prompt=prompt)


def classify_prompt_intent(
    prompt: str,
    files: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Funzione helper di modulo per classificare l'intento del prompt (Mode D vs A/B/C)."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.classify_prompt_intent(prompt=prompt, files=files)


def load_prewarmed_capsule(workspace_root: Optional[Path] = None) -> Dict[str, Any]:
    """Funzione helper di modulo per caricare la capsula Tier-1 pre-riscaldata."""
    router = VibeSprintRouter(workspace_root=workspace_root)
    return router.load_prewarmed_capsule()


def run_test() -> int:
    """Esegue l'autotest rapido del router Mode C e Mode D."""
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
    disc = router.classify_prompt_intent("Esegui audit e benchmark copertura bandi")
    assert disc["recommended_mode"] == "mode_d"
    assert "domain_id" in disc
    print(f"VibeSprintRouter test PASS: Risk {res['risk_score']} | Depth {res['max_depth']}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il router Mode A/B/C/D di Nexus Keystone."""
    parser = argparse.ArgumentParser(
        description="Router Mode A/B/C/D basato sul rischio AST e intento prompt per Nexus Keystone"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Esegue l'autotest rapido del router",
    )
    parser.add_argument(
        "--prompt",
        "--task",
        dest="prompt",
        type=str,
        default="Vibe Sprint Change",
        help="Descrizione sintetica dell'intento di modifica o discovery",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="Modalita operativa opzionale",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Elenco dei file sorgente da valutare per il routing",
    )
    parser.add_argument(
        "--discovery-check",
        action="store_true",
        help="Valuta l'intento del prompt per attivare Mode D Read-Only Discovery",
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

    intent = router.classify_prompt_intent(args.prompt, files=args.files)
    if args.discovery_check or intent["is_discovery"]:
        if args.capsule:
            intent["tier1_capsule"] = router.load_prewarmed_capsule()
        if args.json:
            print(json.dumps(intent, indent=2))
        else:
            print(
                f"[{intent['mode_label']}] | Mode: {intent['recommended_mode']} | "
                f"Agent: {intent['primary_agent']} | Domain: {intent['domain_id']}"
            )
        return 0

    if args.capsule:
        cap = router.load_prewarmed_capsule()
        print(json.dumps(cap, indent=2))
        return 0

    print("VibeSprintRouter CLI ready. Use --test to validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
