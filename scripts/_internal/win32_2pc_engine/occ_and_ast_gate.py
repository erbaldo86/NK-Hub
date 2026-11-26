# -*- coding: utf-8 -*-
"""Gate pre-L1 OCC write-set case-folded e diff firme pubbliche AST via SignatureCollector."""

from __future__ import annotations

import ast
import difflib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from _internal.nk_common.commit_train_store import (
    casefold_win32_rel,
    compute_changed_files_range,
    read_commit_train_head,
)
from _internal.nk_common.lane_paths import is_lane_container_entry
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest


def _is_public_symbol(sym_key: str) -> bool:
    short = sym_key.split(".", 1)[-1].split("[", 1)[0]
    return short == "__init__" or not short.startswith("_")


def extract_public_signatures(source_code: str) -> Dict[str, Dict[str, Any]]:
    """Estrae le firme pubbliche di modulo/classe tramite SignatureCollector SSOT."""
    if not source_code.strip():
        return {}
    from _internal.ast_guard_validator.signature_collector import SignatureCollector

    tree = ast.parse(source_code)
    collector = SignatureCollector()
    collector.visit(tree)
    out: Dict[str, Dict[str, Any]] = {}
    for sym, snap in collector.signatures.items():
        if not _is_public_symbol(sym):
            continue
        out[sym] = {
            "is_async": snap.is_async,
            "posonly_args": list(snap.posonly_args),
            "pos_args": list(snap.pos_args),
            "vararg": snap.vararg,
            "kwonly_args": list(snap.kwonly_args),
            "kwarg": snap.kwarg,
            "defaults_count": int(snap.defaults_count),
            "kw_defaults_count": int(snap.kw_defaults_count),
            "annotations": dict(snap.annotations),
            "return_annotation": snap.return_annotation,
        }
    return out


def capture_public_signatures_snapshot(
    root: Path,
    rel_py_paths: Sequence[str],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Cattura le firme pubbliche T0 dei file .py monitorati (chiavi case-folded)."""
    base = Path(root).resolve()
    snap: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for raw_rel in rel_py_paths:
        cf = casefold_win32_rel(raw_rel)
        if not cf.endswith(".py"):
            continue
        fpath = base / raw_rel
        code = fpath.read_text(encoding="utf-8-sig") if fpath.is_file() else ""
        snap[cf] = extract_public_signatures(code)
    return snap


def collect_staged_write_set(
    staging_dir: Path,
    *,
    exclude_lanes: bool = False,
) -> Tuple[Set[str], Dict[str, Path]]:
    """Raccoglie write-set normalizzato case-folded e mappa Path dei file staged/deleted."""
    stg = Path(staging_dir)
    write_set: Set[str] = set()
    staged_map: Dict[str, Path] = {}
    if not stg.is_dir():
        return write_set, staged_map
    for fp in sorted(stg.rglob("*")):
        if not fp.is_file() or "__pycache__" in fp.parts or fp.name == ".gitkeep":
            continue
        rel_p = fp.relative_to(stg)
        if exclude_lanes and is_lane_container_entry(rel_p.parts):
            continue
        if rel_p.as_posix() == ".deleted_files.json":
            for del_rel in parse_deleted_files_manifest(fp):
                cf_d = casefold_win32_rel(del_rel)
                if cf_d:
                    write_set.add(cf_d)
            continue
        cf = casefold_win32_rel(rel_p.as_posix())
        if cf:
            write_set.add(cf)
            staged_map[cf] = fp
    return write_set, staged_map


def _build_conflict_unified_diff(
    root: Path, conflicts: List[str], staged_map: Dict[str, Path], canon_map: Dict[str, str],
) -> str:
    chunks: List[str] = []
    for cf in conflicts[:5]:
        canon = canon_map.get(cf, cf)
        prod_p = root / canon
        stg_p = staged_map.get(cf)
        prod_lines = prod_p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if prod_p.is_file() else []
        stg_lines = stg_p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if (stg_p and stg_p.is_file()) else []
        chunks.extend(difflib.unified_diff(prod_lines, stg_lines, fromfile=f"prod/{canon}", tofile=f"staging/{canon}", n=2))
    return "".join(chunks)[:4000]


def _detect_signature_drift(
    root: Path,
    changed_cf: Set[str],
    canon_map: Dict[str, str],
    base_signatures: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Tuple[List[str], str]:
    if not base_signatures:
        return [], ""
    norm_base = {casefold_win32_rel(k): v for k, v in base_signatures.items()}
    drift_syms: List[str] = []
    diff_lines: List[str] = []
    for cf in sorted(changed_cf):
        if not cf.endswith(".py") or cf not in norm_base:
            continue
        canon = canon_map.get(cf, cf)
        prod_p = root / canon
        cur_code = prod_p.read_text(encoding="utf-8-sig", errors="replace") if prod_p.is_file() else ""
        cur_sigs = extract_public_signatures(cur_code)
        for sym, old_sig in sorted(norm_base[cf].items()):
            new_sig = cur_sigs.get(sym)
            if new_sig != old_sig:
                drift_syms.append(f"{canon}::{sym}")
                diff_lines.append(f"--- {canon}::{sym} (T0) {old_sig}\n+++ {canon}::{sym} (T1) {new_sig}\n")
    return drift_syms, "".join(diff_lines)[:4000]


def evaluate_occ_and_ast_gate(
    root: Path,
    staging_dir: Path,
    *,
    base_seq: int,
    base_signatures: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    exclude_lanes: Optional[bool] = None,
    key_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Esegue controllo fail-fast pre-L1 per write conflict OCC e drift firme AST T0->T1."""
    res_root = Path(root).resolve()
    stg = Path(staging_dir)
    excl = (stg.name == ".staging") if exclude_lanes is None else bool(exclude_lanes)
    head = read_commit_train_head(res_root, key_path=key_path)
    head_seq = int(head.get("seq", 0))
    if head_seq <= int(base_seq):
        return {
            "passed": True,
            "status": "OK",
            "base_seq": int(base_seq),
            "head_seq": head_seq,
            "conflicting_files": [],
            "ast_drift_symbols": [],
            "unified_diff": "",
        }

    changed_cf, canon_map = compute_changed_files_range(res_root, int(base_seq), head_seq, key_path=key_path)
    write_set, staged_map = collect_staged_write_set(stg, exclude_lanes=excl)
    conflicts = sorted(write_set & changed_cf)
    if conflicts:
        return {
            "passed": False,
            "status": "OCC_WRITE_CONFLICT",
            "base_seq": int(base_seq),
            "head_seq": head_seq,
            "conflicting_files": [canon_map.get(c, c) for c in conflicts],
            "ast_drift_symbols": [],
            "unified_diff": _build_conflict_unified_diff(res_root, conflicts, staged_map, canon_map),
        }

    drift_syms, drift_diff = _detect_signature_drift(res_root, changed_cf, canon_map, base_signatures)
    if drift_syms:
        return {
            "passed": False,
            "status": "AST_CONTRACT_DRIFT",
            "base_seq": int(base_seq),
            "head_seq": head_seq,
            "conflicting_files": [],
            "ast_drift_symbols": drift_syms,
            "unified_diff": drift_diff,
        }

    return {
        "passed": True,
        "status": "OK",
        "base_seq": int(base_seq),
        "head_seq": head_seq,
        "conflicting_files": [],
        "ast_drift_symbols": [],
        "unified_diff": "",
    }
