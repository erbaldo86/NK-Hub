"""Helper pure-stdlib per overlay .staging/[lanes/<id>/] su produzione."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from _internal.nk_common.lane_paths import (
    is_lane_container_entry,
    resolve_staging_dir,
    strip_staging_rel_parts,
)
from _internal.nk_common.staging_manifest import is_reparse_entry
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

_DEFAULT_ROOT_CANDIDATES: Tuple[str, ...] = ("scripts", "src_app", "tests")


def _norm_rel(rel_path: str) -> str:
    clean = rel_path.strip().replace("\\", "/")
    while clean.startswith("./"):
        clean = clean[2:]
    clean = clean.strip("/")
    return clean.lower() if os.name == "nt" else clean


def is_deleted_rel_path(rel_posix: str, deleted_norm: Set[str]) -> bool:
    """True se il percorso relativo o una sua directory padre figura in .deleted_files.json."""
    key = _norm_rel(rel_posix)
    if not key:
        return False
    return key in deleted_norm or any(key.startswith(f"{d}/") for d in deleted_norm)


def _is_dast_snapshot_root(parts: Tuple[str, ...], idx: int) -> bool:
    """True se il prefisso prima di .staging risiede in TEMP e ospita il marker DAST non-reparse."""
    snap_root = Path(*parts[:idx]).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    marker = snap_root / ".nk_dast_snapshot_marker"
    return snap_root.is_relative_to(temp_root) and marker.is_file() and not is_reparse_entry(marker)


def _resolve_explicit_overlay_roots(
    prod_root: Path, stage_arg: Optional[str], lane_arg: Optional[str]
) -> Tuple[Path, Path]:
    """Risolve (prod_root, stage_root) da --stage-dir o --lane-id."""
    stage_root, _lane = resolve_staging_dir(prod_root, lane_id=lane_arg, staging_dir=stage_arg)
    idx, _rel, _det_lane = strip_staging_rel_parts(stage_root.parts)
    if idx > 0 and not _is_dast_snapshot_root(stage_root.parts, idx):
        prod_root = Path(*stage_root.parts[:idx])
    return prod_root, stage_root


def resolve_overlay_roots(
    args: Any, scan_root: Path, raw_targets: Sequence[Tuple[str, bool]]
) -> Tuple[Path, Path]:
    """Individua (prod_root, stage_root) supportando --stage-dir e --lane-id."""
    prod_root = scan_root.resolve()
    stage_arg, lane_arg = getattr(args, "stage_dir", None), getattr(args, "lane_id", None)
    if stage_arg or lane_arg:
        return _resolve_explicit_overlay_roots(prod_root, stage_arg, lane_arg)
    stage_root = (prod_root / ".staging").resolve()
    if stage_root.is_dir():
        return prod_root, stage_root
    for rt, _req_dir in raw_targets:
        if rt.lower() == "all" or not rt.strip():
            continue
        rp = Path(rt).resolve()
        for anc in (rp, rp.parent, rp.parent.parent):
            if (anc / ".staging").is_dir():
                return anc, (anc / ".staging").resolve()
    return prod_root, stage_root


def load_deleted_manifest_set(stage_root: Path) -> Set[str]:
    """Carica e normalizza i path in .deleted_files.json tramite parse_deleted_files_manifest."""
    raw_items = parse_deleted_files_manifest(stage_root / ".deleted_files.json")
    return {n for n in (_norm_rel(it) for it in raw_items) if n}


def _iter_py_entries(sub: Optional[Path]) -> List[Path]:
    if sub is None or not sub.exists():
        return []
    if sub.is_file():
        return [sub] if sub.suffix == ".py" else []
    if sub.is_dir():
        return [f for f in sorted(sub.rglob("*.py")) if "__pycache__" not in f.parts]
    return []


def _add_prod_py_tree(
    prod_sub: Optional[Path],
    prod_root: Path,
    deleted_norm: Set[str],
    overlay_map: Dict[str, Path],
) -> None:
    """Registra file .py di produzione escludendo .staging e path in deleted_norm."""
    for f in _iter_py_entries(prod_sub):
        res = f.resolve()
        if not res.is_relative_to(prod_root):
            continue
        rel_p = res.relative_to(prod_root)
        rel_k = rel_p.as_posix()
        if ".staging" not in rel_p.parts and not is_deleted_rel_path(rel_k, deleted_norm):
            overlay_map[_norm_rel(rel_k)] = f


def _add_stg_py_tree(
    stg_sub: Optional[Path],
    stage_root: Path,
    deleted_norm: Set[str],
    overlay_map: Dict[str, Path],
) -> None:
    """Sovrappone file .py di staging su overlay_map saltando lanes/ in legacy."""
    excl_lanes = stage_root.name == ".staging"
    for f in _iter_py_entries(stg_sub):
        res = f.resolve()
        if not res.is_relative_to(stage_root):
            continue
        rel_p = res.relative_to(stage_root)
        if excl_lanes and is_lane_container_entry(rel_p.parts):
            continue
        rel_k = rel_p.as_posix()
        n_key = _norm_rel(rel_k)
        if is_deleted_rel_path(rel_k, deleted_norm):
            overlay_map.pop(n_key, None)
        else:
            overlay_map[n_key] = f


def _merge_subpath_py_overlay(
    prod_sub: Optional[Path],
    stg_sub: Optional[Path],
    prod_root: Path,
    stage_root: Path,
    deleted_norm: Set[str],
    overlay_map: Dict[str, Path],
) -> None:
    _add_prod_py_tree(prod_sub, prod_root, deleted_norm, overlay_map)
    _add_stg_py_tree(stg_sub, stage_root, deleted_norm, overlay_map)


def _collect_all_overlay(
    prod_root: Path,
    stage_root: Path,
    deleted_norm: Set[str],
    overlay_map: Dict[str, Path],
    targets_out: List[Path],
) -> None:
    """Raccoglie l'intero albero sovrapposto (scripts, src_app, tests + staging corrente)."""
    for cand in _DEFAULT_ROOT_CANDIDATES:
        prod_sub = prod_root / cand
        stg_sub = stage_root / cand
        if prod_sub.is_dir():
            targets_out.append(prod_sub)
        if stg_sub.is_dir():
            targets_out.append(stg_sub)
        _merge_subpath_py_overlay(
            prod_sub, stg_sub, prod_root, stage_root, deleted_norm, overlay_map
        )
    if stage_root.is_dir():
        _add_stg_py_tree(stage_root, stage_root, deleted_norm, overlay_map)


def _merge_existing_overlay_target(
    p: Path,
    p_res: Path,
    prod_root: Path,
    stage_root: Path,
    deleted_norm: Set[str],
    overlay_map: Dict[str, Path],
    targets_to_scan: List[Path],
) -> None:
    targets_to_scan.append(p)
    if p_res == stage_root:
        _collect_all_overlay(prod_root, stage_root, deleted_norm, overlay_map, targets_to_scan)
    elif stage_root.is_dir() and p_res.is_relative_to(stage_root):
        rel = p_res.relative_to(stage_root)
        _merge_subpath_py_overlay(prod_root / rel, p_res, prod_root, stage_root, deleted_norm, overlay_map)
    elif p_res.is_relative_to(prod_root):
        rel = p_res.relative_to(prod_root)
        _merge_subpath_py_overlay(p_res, stage_root / rel, prod_root, stage_root, deleted_norm, overlay_map)
    else:
        _add_prod_py_tree(p_res, p_res.parent, deleted_norm, overlay_map)


def _resolve_single_overlay_target(
    raw_target: str,
    require_dir: bool,
    has_explicit_non_stage: bool,
    prod_root: Path,
    stage_root: Path,
    deleted_norm: Set[str],
    overlay_map: Dict[str, Path],
    targets_to_scan: List[Path],
) -> Optional[str]:
    """Valida e risolve un singolo target in modalita --overlay-staging."""
    if not require_dir and raw_target.lower() == "all":
        _collect_all_overlay(prod_root, stage_root, deleted_norm, overlay_map, targets_to_scan)
        return None
    if not raw_target.strip():
        return "Empty target/stage-dir path provided."
    p = Path(raw_target)
    if require_dir:
        if not p.exists():
            return f"Path does not exist: {p}"
        if not p.is_dir():
            return f"Stage directory is not a directory: {p}"
        if not has_explicit_non_stage:
            _collect_all_overlay(prod_root, stage_root, deleted_norm, overlay_map, targets_to_scan)
        return None
    p_res = (p if p.is_absolute() else (Path.cwd() / p)).resolve()
    if not p.exists():
        if p_res.is_relative_to(prod_root):
            stg_only = stage_root / p_res.relative_to(prod_root)
            if stg_only.exists():
                targets_to_scan.append(stg_only)
                _merge_subpath_py_overlay(p_res, stg_only, prod_root, stage_root, deleted_norm, overlay_map)
                return None
        return f"Path does not exist: {p}"
    _merge_existing_overlay_target(
        p, p_res, prod_root, stage_root, deleted_norm, overlay_map, targets_to_scan
    )
    return None


def resolve_overlay_scan_files(
    raw_targets: List[Tuple[str, bool]],
    args: Any,
    scan_root: Path,
) -> Tuple[List[Path], List[Path], Path, Path, Set[str], Optional[str]]:
    """Risolve target e lista file .py in modalita --overlay-staging fail-closed."""
    prod_root, stage_root = resolve_overlay_roots(args, scan_root, raw_targets)
    try:
        deleted_norm = load_deleted_manifest_set(stage_root)
    except ValueError as exc:
        return [], [], prod_root, stage_root, set(), str(exc)

    overlay_map: Dict[str, Path] = {}
    targets_to_scan: List[Path] = []
    has_explicit_non_stage = any(not req_dir for _, req_dir in raw_targets)
    for raw_target, require_dir in raw_targets:
        err = _resolve_single_overlay_target(
            raw_target, require_dir, has_explicit_non_stage,
            prod_root, stage_root, deleted_norm, overlay_map, targets_to_scan,
        )
        if err:
            return [], [], prod_root, stage_root, deleted_norm, err
    py_files = sorted(dict.fromkeys(overlay_map.values()))
    return py_files, targets_to_scan, prod_root, stage_root, deleted_norm, None


def _iter_fe_subroots(
    target: Path, prod_root: Path, stage_root: Path
) -> List[Tuple[Path, Path, bool]]:
    t_res = target.resolve()
    if stage_root.is_dir() and t_res.is_relative_to(stage_root):
        return [(t_res, stage_root, True), (prod_root / t_res.relative_to(stage_root), prod_root, False)]
    if t_res.is_relative_to(prod_root):
        return [(t_res, prod_root, False), (stage_root / t_res.relative_to(prod_root), stage_root, True)]
    return [(t_res, t_res.parent, False)]


def _iter_fe_entries(sub: Path, ext_set: Set[str], skip_set: Set[str]) -> List[Path]:
    if not sub.exists():
        return []
    if sub.is_file():
        return [sub] if sub.suffix.lower() in ext_set else []
    if sub.is_dir():
        return [
            f for f in sorted(sub.rglob("*"))
            if f.is_file() and f.suffix.lower() in ext_set and not any(p in skip_set for p in f.parts)
        ]
    return []


def _merge_fe_entry(
    fpath: Path, base: Path, is_stg: bool, excl_lanes: bool, deleted_norm: Set[str], fe_map: Dict[str, Path]
) -> None:
    """Inserisce o rimuove un file Frontend nella mappa overlay gestendo lanes e tombstone."""
    res = fpath.resolve()
    if not res.is_relative_to(base):
        return
    rel_p = res.relative_to(base)
    if (not is_stg and ".staging" in rel_p.parts) or (is_stg and excl_lanes and is_lane_container_entry(rel_p.parts)):
        return
    rel_k = rel_p.as_posix()
    n_key = _norm_rel(rel_k)
    if is_deleted_rel_path(rel_k, deleted_norm):
        fe_map.pop(n_key, None)
    else:
        fe_map[n_key] = fpath


def collect_overlay_frontend_files(
    targets_to_scan: Sequence[Path],
    prod_root: Path,
    stage_root: Path,
    deleted_norm: Set[str],
    fe_exts: Sequence[str],
    skip_dirs: Sequence[str],
) -> List[Path]:
    """Costruisce la lista overlaid dei file Frontend sotto targets_to_scan."""
    fe_map: Dict[str, Path] = {}
    ext_set, skip_set = {e.lower() for e in fe_exts}, set(skip_dirs)
    excl_lanes = stage_root.name == ".staging"
    for target in targets_to_scan:
        for sub, base, is_stg in _iter_fe_subroots(target, prod_root, stage_root):
            for fpath in _iter_fe_entries(sub, ext_set, skip_set):
                _merge_fe_entry(fpath, base, is_stg, excl_lanes, deleted_norm, fe_map)
    return sorted(dict.fromkeys(fe_map.values()))
