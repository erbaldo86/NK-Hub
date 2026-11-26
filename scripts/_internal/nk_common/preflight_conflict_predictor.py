# -*- coding: utf-8 -*-
"""Predittore pre-flight read-only di conflitti fisici e semantici AST tra lane."""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Set, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.lane_leases import list_active_leases
from _internal.nk_common.lane_paths import validate_lane_id
from _internal.nk_common.lane_registry import list_active_lanes
from _internal.nk_common.staging_manifest import is_reparse_entry

ConflictSeverity = Literal["DISJOINT", "SEMANTIC_COUPLED", "HARD_CONFLICT"]


class ConflictPredictionReport(BaseModel):
    """Esito read-only del predittore pre-flight su write-set e accoppiamenti AST."""

    model_config = ConfigDict(strict=True, extra="forbid")

    severity: ConflictSeverity = Field(description="Livello massimo di conflitto rilevato")
    hard_conflicts: List[Dict[str, Any]] = Field(default_factory=list, description="Sovrapposizioni fisiche dei percorsi")
    semantic_couplings: List[Dict[str, Any]] = Field(default_factory=list, description="Accoppiamenti import/simboli AST")
    active_lanes_checked: List[str] = Field(default_factory=list, description="Lane attive ispezionate")
    active_leases_count: int = Field(default=0, ge=0, description="Numero di lease runtime attive")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Durata analisi in millisecondi")


def _norm_rel(raw: str) -> str:
    return raw.strip().replace("\\", "/").lstrip("./").casefold()


def extract_python_imported_targets(source_code: str, *, file_rel: str = "") -> Dict[str, Any]:
    """Estrae moduli importati e simboli definiti via AST senza esecuzione."""
    from _internal.ast_guard_validator.signature_collector import SignatureCollector

    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        return {
            "file_rel": file_rel,
            "imported_modules": [],
            "imported_names": [],
            "defined_symbols": [],
            "parse_error": str(exc),
        }

    collector = SignatureCollector()
    collector.skip_unparse = True
    collector.visit(tree)

    imported_modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.casefold())
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.casefold())

    defined_syms = set(collector.signatures.keys()) | set(collector.classes) | set(collector.defined_globals)
    return {
        "file_rel": file_rel,
        "imported_modules": sorted(imported_modules),
        "imported_names": sorted(n.casefold() for n in collector.imported_names),
        "defined_symbols": sorted(s.casefold() for s in defined_syms),
        "parse_error": "",
    }


def _collect_lane_files(root: Path, lane_id: str, rec: Mapping[str, Any]) -> Tuple[Set[str], Dict[str, Path]]:
    """Raccoglie i percorsi dichiarati e i file reali staged della lane."""
    rel_map: Dict[str, Path] = {}
    declared: Set[str] = set()
    for raw in rec.get("declared_write_set") or ():
        if (norm := _norm_rel(str(raw))):
            declared.add(norm)
            cand = root / norm
            if cand.is_file() and not is_reparse_entry(cand):
                rel_map[norm] = cand

    lane_dir = root / ".staging" / "lanes" / lane_id
    if lane_dir.is_dir() and not is_reparse_entry(lane_dir):
        for w_root, dirs, files in os.walk(lane_dir, followlinks=False):
            w_p = Path(w_root)
            dirs[:] = [d for d in dirs if not is_reparse_entry(w_p / d)]
            for fn in files:
                if fn in (".gitkeep", ".deleted_files.json"):
                    continue
                fp = w_p / fn
                if is_reparse_entry(fp):
                    continue
                norm = fp.relative_to(lane_dir).as_posix().casefold()
                declared.add(norm)
                rel_map[norm] = fp
    return declared, rel_map


def _module_tokens_for_rel(rel_posix: str) -> Set[str]:
    clean = rel_posix.removesuffix(".py").replace("/", ".")
    parts = [p for p in clean.split(".") if p and p != "__init__"]
    tokens: Set[str] = set()
    for idx in range(len(parts)):
        tokens.add(".".join(parts[idx:]))
    if parts:
        tokens.add(parts[-1])
    return tokens


def _inspect_py_ast(fp: Path, rel_posix: str) -> Optional[Dict[str, Any]]:
    if not rel_posix.endswith(".py") or not fp.is_file() or is_reparse_entry(fp):
        return None
    try:
        src = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta = extract_python_imported_targets(src, file_rel=rel_posix)
    meta["module_tokens"] = _module_tokens_for_rel(rel_posix)
    return meta


def _check_semantic_pair(cand_meta: Dict[str, Any], lane_meta: Dict[str, Any], lane_id: str) -> Optional[Dict[str, Any]]:
    c_mods = set(cand_meta["imported_modules"])
    l_mods = set(lane_meta["imported_modules"])
    c_toks = set(cand_meta["module_tokens"])
    l_toks = set(lane_meta["module_tokens"])
    c_defs = set(cand_meta["defined_symbols"])
    l_defs = set(lane_meta["defined_symbols"])
    c_imps = set(cand_meta["imported_names"])
    l_imps = set(lane_meta["imported_names"])

    reason = ""
    if c_mods & l_toks:
        reason = f"candidate_imports_lane_module:{sorted(c_mods & l_toks)[0]}"
    elif l_mods & c_toks:
        reason = f"lane_imports_candidate_module:{sorted(l_mods & c_toks)[0]}"
    elif (c_imps & l_defs) and any(m.endswith(t) for m in c_mods for t in l_toks):
        reason = "symbol_contract_dependency"
    elif (l_imps & c_defs) and any(m.endswith(t) for m in l_mods for t in c_toks):
        reason = "reverse_symbol_dependency"
    if not reason:
        return None
    return {
        "lane_id": lane_id,
        "candidate_file": cand_meta["file_rel"],
        "lane_file": lane_meta["file_rel"],
        "reason": reason,
    }


def _analyze_single_lane(
    root: Path,
    norm_lid: str,
    rec: Mapping[str, Any],
    cand_set: Set[str],
    cand_ast_cache: Dict[str, Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Analizza conflitti fisici e semantici AST tra candidate_write_set e una singola lane attiva."""
    lane_rels, lane_files = _collect_lane_files(root, norm_lid, rec)
    overlap = sorted(cand_set & lane_rels)
    if overlap:
        return {"lane_id": norm_lid, "overlapping_paths": overlap}, []
    couplings: List[Dict[str, Any]] = []
    for l_rel, l_fp in sorted(lane_files.items()):
        if (l_meta := _inspect_py_ast(l_fp, l_rel)) is None:
            continue
        for c_meta in cand_ast_cache.values():
            if (coupling := _check_semantic_pair(c_meta, l_meta, norm_lid)) is not None:
                couplings.append(coupling)
    return None, couplings


def predict_lane_conflicts(
    repo_root: Union[str, Path],
    candidate_write_set: Sequence[str],
    *,
    exclude_lane_id: Optional[str] = None,
    active_lanes_override: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> ConflictPredictionReport:
    """Predice conflitti fisici e accoppiamenti AST in sola lettura rispetto alle lane attive."""
    t0 = time.perf_counter()
    root = Path(repo_root).resolve()
    excl = validate_lane_id(exclude_lane_id) if exclude_lane_id else None
    cand_set = {norm for raw in candidate_write_set if (norm := _norm_rel(str(raw)))}
    lanes_map = dict(active_lanes_override) if active_lanes_override is not None else list_active_lanes(root)
    leases = list_active_leases(root, prune_dead=False)

    checked: List[str] = []
    hard_conflicts: List[Dict[str, Any]] = []
    semantic_couplings: List[Dict[str, Any]] = []
    cand_ast_cache: Dict[str, Dict[str, Any]] = {}
    for rel in sorted(cand_set):
        if (meta := _inspect_py_ast(root / rel, rel)) is not None:
            cand_ast_cache[rel] = meta

    for raw_lid, rec in sorted(lanes_map.items()):
        norm_lid = validate_lane_id(raw_lid)
        if excl is not None and norm_lid == excl:
            continue
        checked.append(norm_lid)
        hard, couplings = _analyze_single_lane(root, norm_lid, rec, cand_set, cand_ast_cache)
        if hard is not None:
            hard_conflicts.append(hard)
        else:
            semantic_couplings.extend(couplings)

    severity: ConflictSeverity = (
        "HARD_CONFLICT" if hard_conflicts else ("SEMANTIC_COUPLED" if semantic_couplings else "DISJOINT")
    )
    return ConflictPredictionReport(
        severity=severity,
        hard_conflicts=hard_conflicts,
        semantic_couplings=semantic_couplings,
        active_lanes_checked=checked,
        active_leases_count=len(leases),
        duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
    )
