# -*- coding: utf-8 -*-
"""Loader stdlib pure-JSON per soglie di saturazione e file .deleted_files.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, Union

from _internal.nk_common.paths import normalize_rel_path, resolve_workspace_root
from _internal.nk_common.tas_ssot_io import parse_deleted_files_manifest

_THRESHOLDS_CANON_REL = Path("nk_genome/configs/saturation_thresholds.json")
_THRESHOLDS_CACHE: Dict[str, Tuple[int, int, Dict[str, Any]]] = {}


def _safe_pos_int(val: Any, default: int) -> int:
    """Converte un valore in intero positivo usando il valore predefinito su errore."""
    if isinstance(val, bool):
        return default
    try:
        parsed = int(val)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def clear_thresholds_cache() -> None:
    """Svuota la cache in memoria delle soglie di saturazione."""
    _THRESHOLDS_CACHE.clear()


def _alias_generation_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Garantisce la simmetria tra i profili generation e carbon nelle soglie."""
    out = copy.deepcopy(data)
    profiles = out.get("profiles")
    if isinstance(profiles, dict):
        carb = profiles.get("carbon")
        gen = profiles.get("generation")
        if isinstance(carb, dict) and not isinstance(gen, dict):
            profiles["generation"] = copy.deepcopy(carb)
        elif isinstance(gen, dict) and not isinstance(carb, dict):
            profiles["carbon"] = copy.deepcopy(gen)
    return out


def load_saturation_thresholds(
    thresholds_path: Optional[Path] = None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Carica saturation_thresholds.json in sola stdlib dal percorso canonico."""
    base_root = (
        Path(workspace_root).resolve()
        if workspace_root is not None
        else Path(resolve_workspace_root(__file__)).resolve()
    )
    if thresholds_path is not None:
        candidates = (Path(thresholds_path),)
    else:
        candidates = (
            base_root / ".staging" / _THRESHOLDS_CANON_REL,
            base_root / _THRESHOLDS_CANON_REL,
        )

    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            st = cand.stat()
            ckey = str(cand)
            cached = _THRESHOLDS_CACHE.get(ckey)
            if (
                cached is not None
                and cached[0] == st.st_mtime_ns
                and cached[1] == st.st_size
            ):
                return copy.deepcopy(cached[2])
            data = json.loads(cand.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                normalized = _alias_generation_profile(data)
                _THRESHOLDS_CACHE[ckey] = (st.st_mtime_ns, st.st_size, normalized)
                return copy.deepcopy(normalized)
        except Exception:
            continue
    return {}


def load_deleted_files(
    workspace_root: Optional[Union[str, Path]] = None,
    deleted_manifest: Optional[Union[str, Path]] = None,
) -> Set[str]:
    """Carica in modo fail-safe .deleted_files.json delegando al parser SSOT."""
    if deleted_manifest is not None:
        manifest_path = Path(deleted_manifest)
    else:
        base_root = (
            Path(workspace_root).resolve()
            if workspace_root is not None
            else Path(resolve_workspace_root(__file__)).resolve()
        )
        manifest_path = base_root / ".staging" / ".deleted_files.json"

    try:
        items = parse_deleted_files_manifest(manifest_path)
    except (OSError, ValueError):
        return set()
    return {norm for raw in items if (norm := normalize_rel_path(raw))}
