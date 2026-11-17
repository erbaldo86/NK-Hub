"""Analisi profondita AST, diff LOC, linter prompt e capsula Tier-1 pre-riscaldata."""

from __future__ import annotations

import ast
import difflib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from _internal.vibe_sprint_router.prompt_linter import lint_nk_prompt


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


def diff_changed_lines_impl(prod_lines: List[str], staged_lines: List[str]) -> int:
    """Conta le righe effettivamente modificate/aggiunte/rimosse tramite SequenceMatcher."""
    matcher = difflib.SequenceMatcher(None, prod_lines, staged_lines)
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)
    return changed


def estimate_changed_loc_impl(
    self,
    files: Optional[List[str]] = None,
    changed_lines: Optional[int] = None,
) -> int:
    """Stima le righe modificate dal parametro changed_lines o dal diff in staging."""
    if changed_lines is not None:
        return max(0, int(changed_lines))
    if not files:
        return 0
    total_loc = 0
    ws_resolved = self.workspace_root.resolve()
    stg_resolved = self.staging_dir.resolve()
    for file_arg in files:
        p = Path(file_arg)
        staged_p: Optional[Path] = None
        prod_p: Optional[Path] = None
        if not p.is_absolute():
            rel_parts = [pt for pt in p.parts if pt != ".staging"]
            rel_path = Path(*rel_parts) if rel_parts else p
            staged_p = self.staging_dir / rel_path
            prod_p = self.workspace_root / rel_path
        else:
            p_res = p.resolve()
            if ".staging" in p_res.parts:
                idx = list(p_res.parts).index(".staging")
                staged_p = p_res
                if idx + 1 < len(p_res.parts):
                    prod_p = Path(*p_res.parts[:idx]).joinpath(
                        *p_res.parts[idx + 1 :]
                    )
            else:
                try:
                    rel_to_ws = p_res.relative_to(ws_resolved)
                    staged_p = stg_resolved / rel_to_ws
                    prod_p = p_res
                except ValueError:
                    if p_res.exists() and p_res.is_file():
                        total_loc += len(
                            p_res.read_text(
                                encoding="utf-8", errors="replace"
                            ).splitlines()
                        )
                    continue

        if staged_p is not None and staged_p.exists() and staged_p.is_file():
            s_lines = staged_p.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if prod_p is not None and prod_p.exists() and prod_p.is_file():
                p_lines = prod_p.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                total_loc += self._diff_changed_lines(p_lines, s_lines)
            else:
                total_loc += len(s_lines)
    return total_loc


def validate_generated_prompt_impl(
    self, file_or_text: str, mode: str = "auto"
) -> Dict[str, Any]:
    """Valida un prompt generato (da file o testo) contro gli anti-pattern AP-1..AP-13."""
    raw_arg = (file_or_text or "").strip()
    text = raw_arg
    if raw_arg and len(raw_arg) < 512 and "\n" not in raw_arg:
        cand = Path(raw_arg)
        if not cand.is_absolute():
            cand_ws = self.workspace_root / raw_arg
            if cand_ws.exists() and cand_ws.is_file():
                cand = cand_ws
        if cand.exists() and cand.is_file():
            text = cand.read_text(encoding="utf-8", errors="replace")
    return lint_nk_prompt(text, mode=mode)


def compute_ast_risk_score_impl(
    self,
    source_code: str,
    filename: str = "snippet.py",
) -> Dict[str, Any]:
    """Calcola il punteggio di rischio AST (0.0 .. 1.0) e la profondita max_depth."""
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


def generate_inline_micro_spec_impl(
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


def load_prewarmed_capsule_impl(self, compact: bool = False) -> Dict[str, Any]:
    """Carica la capsula di memoria Tier-1 pre-riscaldata con fallback a memory_3tier."""
    candidates = (
        self.staging_dir / "nk_tracking" / "memory" / "tier1_active_capsule.json",
        self.workspace_root / "nk_tracking" / "memory" / "tier1_active_capsule.json",
        self.staging_dir
        / "nk_tracking"
        / "memory_3tier"
        / "tier1_active_capsule.json",
        self.workspace_root
        / "nk_tracking"
        / "memory_3tier"
        / "tier1_active_capsule.json",
    )
    for cand in candidates:
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if compact and isinstance(data.get("domains"), dict):
                        compacted = dict(data)
                        compacted_domains: Dict[str, Any] = {}
                        for dom_k, dom_v in data["domains"].items():
                            if isinstance(dom_v, dict) and int(dom_v.get("total_tokens", 0)) > 0:
                                dom_copy = {
                                    k: v
                                    for k, v in dom_v.items()
                                    if k != "context"
                                }
                                compacted_domains[dom_k] = dom_copy
                        compacted["domains"] = compacted_domains
                        return compacted
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


def format_compact_env_capsule_impl(self) -> str:
    """Formatta un blocco <env_capsule> deduplicato sotto i 280 token."""
    cap = self.load_prewarmed_capsule(compact=True)
    lessons = cap.get("lessons", [])
    lines = [
        "<env_capsule>",
        f"Working Directory: {self.workspace_root.as_posix()}",
        "ZERO_BLIND_VIEW_FILE: Usa read_file solo su path verificati in repo_map.md o structural_tree.md.",
        "MAX_WRITE_BATCH: Massimo 2 file lunghi o <= 3500 token di output per singolo step.",
    ]
    if isinstance(lessons, list):
        for item in lessons[:4]:
            if isinstance(item, dict) and item.get("lesson"):
                lines.append(f"- {str(item['lesson'])[:180]}")
    lines.append("</env_capsule>")
    return "\n".join(lines)


def generate_env_capsule_impl(self) -> str:
    """Alias pubblico per formattare il blocco <env_capsule> anti-stallo."""
    return self.format_compact_env_capsule()
